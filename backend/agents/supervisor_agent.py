import json
from datetime import datetime, date
from database.models import LeaveType, LeaveRequest, LeaveRequestDay, Employee, LeaveBalance, LeavePolicy
from sqlalchemy import extract, func

class SupervisorAgent:
    """
    Supervisor Agent
    Responsibility: Main orchestrator. Runs an agentic LLM loop by passing specialist
    agents as tools to the LLM. Collects inputs/outputs and logs traces to the database.
    If the LLM or network fails, gracefully falls back to a deterministic python validation pipeline.
    """
    def __init__(
        self,
        employee_agent,
        leave_balance_agent,
        calendar_agent,
        leave_policy_agent,
        leave_overlap_agent,
        team_agent,
        decision_agent,
        approval_agent,
        notification_agent,
        audit_agent,
        llm_service
    ):
        self.employee_agent = employee_agent
        self.leave_balance_agent = leave_balance_agent
        self.calendar_agent = calendar_agent
        self.leave_policy_agent = leave_policy_agent
        self.leave_overlap_agent = leave_overlap_agent
        self.team_agent = team_agent
        self.decision_agent = decision_agent
        self.approval_agent = approval_agent
        self.notification_agent = notification_agent
        self.audit_agent = audit_agent
        self.llm_service = llm_service

    def execute(
        self,
        employee_id: int,
        text: str,
        db
    ):
        supervisor_start = datetime.now()
        input_payload = {
            "employee_id": employee_id,
            "text": text
        }
        
        # State tracking variable
        loop_context = {
            "current_leave_request_id": None,
            "validation_result": None
        }

        # Definition of tools
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_employee_profile",
                    "description": "Retrieve the profile details of the employee, including full name, email, department, manager, and active status.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "employee_id": {"type": "integer"}
                        },
                        "required": ["employee_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_calendar",
                    "description": "Analyze the start and end dates to calculate requested days, count working days (excluding holidays/weekends), and output specific day breakdowns.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "start_date": {"type": "string", "description": "Start date in YYYY-MM-DD format"},
                            "end_date": {"type": "string", "description": "End date in YYYY-MM-DD format"}
                        },
                        "required": ["start_date", "end_date"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_leave_balance",
                    "description": "Fetch the employee's current leave balance (allocated, used, pending, remaining) for a specific leave type ID.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "employee_id": {"type": "integer"},
                            "leave_type_id": {"type": "integer"}
                        },
                        "required": ["employee_id", "leave_type_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_leave_policy",
                    "description": "Retrieve leave policy constraints (notice period, medical certificate required threshold, auto-approval days, etc.) for a specific leave type ID.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "leave_type_id": {"type": "integer"}
                        },
                        "required": ["leave_type_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_leave_overlap",
                    "description": "Check if the employee has any existing overlapping leave requests within the requested date range.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "employee_id": {"type": "integer"},
                            "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                            "end_date": {"type": "string", "description": "YYYY-MM-DD"}
                        },
                        "required": ["employee_id", "start_date", "end_date"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_team_availability",
                    "description": "Calculate department absence rates during the requested date range and check if department threshold is exceeded.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "department_id": {"type": "integer"},
                            "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                            "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                            "threshold_percent": {"type": "number", "description": "Department absence threshold percent"}
                        },
                        "required": ["department_id", "start_date", "end_date", "threshold_percent"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "make_leave_decision",
                    "description": "Execute deterministic validation rules to determine the recommendation status: Approved, Rejected, or Pending Manager Approval.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "data_json": {"type": "string", "description": "JSON serialized validation facts containing keys: employee_active, remaining_balance, working_days, notice_days, min_notice_days, medical_certificate_after_days, allow_half_day, has_half_day, auto_approval_max_days, overlap_found, threshold_exceeded, monthly_limit_exceeded"}
                        },
                        "required": ["data_json"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "resolve_leave_type_id",
                    "description": "Look up and resolve a leave type's numerical ID by its name or keyword (e.g. Casual Leave, Sick Leave).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "leave_type_name": {"type": "string", "description": "Name or keyword of the leave type"}
                        },
                        "required": ["leave_type_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "create_leave_request_record",
                    "description": "Persist the validated leave request and daily calendar records to the database. Returns the generated leave_request_id.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "employee_id": {"type": "integer"},
                            "leave_type_id": {"type": "integer"},
                            "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                            "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                            "requested_days": {"type": "number"},
                            "reason": {"type": "string"},
                            "status": {"type": "string", "description": "Determined status e.g. Approved, Pending Manager Approval"},
                            "agent_decision": {"type": "string"},
                            "agent_reason": {"type": "string"}
                        },
                        "required": ["employee_id", "leave_type_id", "start_date", "end_date", "requested_days", "reason", "status", "agent_decision", "agent_reason"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "create_approval_task",
                    "description": "Create a manager approval record for the request in the database if manager sign-off is required.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "leave_request_id": {"type": "integer"},
                            "manager_id": {"type": "integer"}
                        },
                        "required": ["leave_request_id", "manager_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "send_notification",
                    "description": "Log/send notification to the employee regarding their request's status.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "employee_id": {"type": "integer"},
                            "leave_request_id": {"type": "integer"},
                            "subject": {"type": "string"},
                            "message": {"type": "string"}
                        },
                        "required": ["employee_id", "leave_request_id", "subject", "message"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_monthly_limit",
                    "description": "Calculate if the current request exceeds the department limit of 5 days in a single month for the employee.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "employee_id": {"type": "integer"},
                            "leave_type_id": {"type": "integer"},
                            "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                            "end_date": {"type": "string", "description": "YYYY-MM-DD"}
                        },
                        "required": ["employee_id", "leave_type_id", "start_date", "end_date"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "submit_validation_result",
                    "description": "Terminate the agent loop and submit the final request status, requested days, and remaining balance details.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "status": {"type": "string", "description": "Approved, Pending Manager Approval, Rejected"},
                            "reason": {"type": "string", "description": "Reason details"},
                            "requested_days": {"type": "number"},
                            "remaining_balance": {"type": "number"},
                            "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                            "end_date": {"type": "string", "description": "YYYY-MM-DD"}
                        },
                        "required": ["status", "reason", "requested_days", "remaining_balance", "start_date", "end_date"]
                    }
                }
            }
        ]

        try:
            # Fetch Context for LLM (Balances, Policies, History, Teammates, Pending requests, and Holidays)
            context_str = self._get_context_str(employee_id, db)

            messages = [
                {
                    "role": "system", 
                    "content": (
                        f"You are the LeaveDesk Orchestrator Agent. Today's date is: {date.today().strftime('%Y-%m-%d')}.\n"
                        f"Your goal is to validate and process a leave request for an employee by coordinating specialist tools.\n\n"
                        f"Context:\n{context_str}\n\n"
                        f"You MUST call the tools in the correct order to validate and resolve the leave request:\n"
                        f"1. Resolve the leave type ID using `resolve_leave_type_id`.\n"
                        f"2. Get the employee profile with `get_employee_profile` to find the manager and department.\n"
                        f"3. Parse dates and check calendar details (working days, weekends, holidays) with `check_calendar`.\n"
                        f"4. Check the leave balance with `get_leave_balance`.\n"
                        f"5. Get the policy constraints with `get_leave_policy`.\n"
                        f"6. Check for overlapping requests with `check_leave_overlap`.\n"
                        f"7. Check team availability using `check_team_availability` (use the `team_threshold` percentage from the policy).\n"
                        f"8. Skip monthly limit check (no monthly limit applies).\n"
                        f"9. Construct a facts JSON and run `make_leave_decision` to decide status.\n"
                        f"10. If status is Approved or Pending Manager Approval, call `create_leave_request_record` to save the request.\n"
                        f"11. If status is Pending Manager Approval, also call `create_approval_task`.\n"
                        f"12. Call `send_notification` to notify the user.\n"
                        f"13. Finally, call `submit_validation_result` to terminate and return the final results.\n\n"
                        f"If the user's message is a general inquiry (such as asking about their leave balances, leave policies, past leave history, pending requests, teammates' leaves, or upcoming holidays), you do not need to call any validation tools. Just read the relevant section in the Context block above and reply directly to the user in friendly conversational text."
                    )
                },
                {
                    "role": "user", 
                    "content": f"User ID: {employee_id}\nRequest Text: {text}"
                }
            ]

            resolved_leave_type_id = None
            resolved_start_date = None
            max_steps = 15
            step = 0

            while step < max_steps:
                step += 1
                
                # Call LLM
                response = self.llm_service.client.chat.completions.create(
                    model=self.llm_service.model_name,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    max_tokens=300
                )
                
                msg = response.choices[0].message
                messages.append(msg)
                
                # Check for direct text response
                if not msg.tool_calls:
                    # Log the Supervisor execution itself
                    supervisor_end = datetime.now()
                    self.audit_agent.execute(
                        agent_name="SupervisorAgent",
                        input_data=input_payload,
                        output_data={"response": msg.content},
                        status="Success",
                        db=db,
                        started_at=supervisor_start,
                        completed_at=supervisor_end
                    )
                    return {
                        "success": True,
                        "response": msg.content
                    }
                
                # Execute tool calls
                for tc in msg.tool_calls:
                    tool_name = tc.function.name
                    args = json.loads(tc.function.arguments)
                    
                    if args:
                        if args.get("leave_type_id"):
                            try:
                                resolved_leave_type_id = int(args.get("leave_type_id"))
                            except:
                                pass
                        if args.get("start_date"):
                            resolved_start_date = args.get("start_date")
                    
                    tool_start = datetime.now()
                    tool_result = {}
                    agent_name_for_audit = None
                    
                    # Route to specific tool logic
                    if tool_name == "resolve_leave_type_id":
                        name_val = args.get("leave_type_name", "Casual Leave")
                        lt_record = db.query(LeaveType).filter(LeaveType.LeaveTypeName.ilike(f"%{name_val}%")).first()
                        if not lt_record:
                            lt_record = db.query(LeaveType).filter(LeaveType.LeaveTypeCode.ilike(f"%{name_val}%")).first()
                        if lt_record:
                            tool_result = {"leave_type_id": lt_record.LeaveTypeId, "leave_type_name": lt_record.LeaveTypeName}
                            resolved_leave_type_id = lt_record.LeaveTypeId
                        else:
                            tool_result = {"error": f"Could not resolve leave type '{name_val}'"}
                    
                    elif tool_name == "get_employee_profile":
                        agent_name_for_audit = "EmployeeProfileAgent"
                        tool_result = self.employee_agent.execute(args.get("employee_id"), db)
                        
                    elif tool_name == "check_calendar":
                        agent_name_for_audit = "CalendarAgent"
                        s_date = datetime.strptime(args.get("start_date"), "%Y-%m-%d").date()
                        e_date = datetime.strptime(args.get("end_date"), "%Y-%m-%d").date()
                        tool_result = self.calendar_agent.execute(s_date, e_date, db)
                        
                    elif tool_name == "get_leave_balance":
                        agent_name_for_audit = "LeaveBalanceAgent"
                        tool_result = self.leave_balance_agent.execute(args.get("employee_id"), args.get("leave_type_id"), db)
                        
                    elif tool_name == "get_leave_policy":
                        agent_name_for_audit = "LeavePolicyAgent"
                        tool_result = self.leave_policy_agent.execute(args.get("leave_type_id"), db)
                        
                    elif tool_name == "check_leave_overlap":
                        agent_name_for_audit = "LeaveOverlapAgent"
                        s_date = datetime.strptime(args.get("start_date"), "%Y-%m-%d").date()
                        e_date = datetime.strptime(args.get("end_date"), "%Y-%m-%d").date()
                        tool_result = self.leave_overlap_agent.execute(args.get("employee_id"), s_date, e_date, db)
                        
                    elif tool_name == "check_team_availability":
                        agent_name_for_audit = "TeamAvailabilityAgent"
                        s_date = datetime.strptime(args.get("start_date"), "%Y-%m-%d").date()
                        e_date = datetime.strptime(args.get("end_date"), "%Y-%m-%d").date()
                        tool_result = self.team_agent.execute(
                            args.get("department_id"),
                            s_date,
                            e_date,
                            args.get("threshold_percent"),
                            db
                        )
                        
                    elif tool_name == "check_monthly_limit":
                        try:
                            s_date = datetime.strptime(args.get("start_date"), "%Y-%m-%d").date()
                            e_date = datetime.strptime(args.get("end_date"), "%Y-%m-%d").date()
                            cal_res = self.calendar_agent.execute(s_date, e_date, db)
                            days_list = cal_res["days"]
                            
                            has_half_day = "half" in text.lower()
                            if has_half_day:
                                for day in days_list:
                                    if not day["is_weekend"] and not day["is_holiday"]:
                                        day["leave_days"] = 0.5
                            
                            # Monthly limit removed — no cap applies
                            monthly_limit_exceeded = False
                            
                            tool_result = {"success": True, "monthly_limit_exceeded": monthly_limit_exceeded}
                        except Exception as e:
                            tool_result = {"error": f"Failed checking monthly limit: {str(e)}"}
                        
                    elif tool_name == "make_leave_decision":
                        agent_name_for_audit = "LeaveDecisionAgent"
                        facts = json.loads(args.get("data_json"))
                        if "notice_days" not in facts:
                            facts["notice_days"] = 10
                            
                        # Query if employee has met/exceeded approved requests count limit in the same calendar month
                        has_previous = False
                        approved_count = 0
                        limit = 1
                        if resolved_leave_type_id and resolved_start_date:
                            try:
                                req_date = datetime.strptime(resolved_start_date, "%Y-%m-%d").date()
                                approved_count = db.query(LeaveRequest).filter(
                                    LeaveRequest.EmployeeId == employee_id,
                                    LeaveRequest.LeaveTypeId == resolved_leave_type_id,
                                    LeaveRequest.Status == "Approved",
                                    extract('month', LeaveRequest.StartDate) == req_date.month,
                                    extract('year', LeaveRequest.StartDate) == req_date.year
                                ).count()
                                
                                policy = db.query(LeavePolicy).filter(
                                    LeavePolicy.LeaveTypeId == resolved_leave_type_id,
                                    LeavePolicy.IsActive == True
                                ).first()
                                limit = policy.AutoApprovalMaxRequestsPerMonth if (policy and policy.AutoApprovalMaxRequestsPerMonth is not None) else 1
                                
                                if approved_count >= limit:
                                    has_previous = True
                            except Exception as ex:
                                print(f"Error checking previous approvals in LLM tool execution: {ex}")
                                
                        facts["has_previous_approved_in_month"] = has_previous
                        facts["approved_requests_count_in_month"] = approved_count
                        facts["auto_approval_max_requests_per_month"] = limit
                        tool_result = self.decision_agent.execute(facts)
                        
                    elif tool_name == "create_leave_request_record":
                        try:
                            s_date = datetime.strptime(args.get("start_date"), "%Y-%m-%d").date()
                            e_date = datetime.strptime(args.get("end_date"), "%Y-%m-%d").date()
                            
                            leave_request = LeaveRequest(
                                EmployeeId=args.get("employee_id"),
                                LeaveTypeId=args.get("leave_type_id"),
                                StartDate=s_date,
                                EndDate=e_date,
                                RequestedDays=args.get("requested_days"),
                                Reason=args.get("reason"),
                                Status=args.get("status"),
                                AgentDecision=args.get("agent_decision"),
                                AgentReason=args.get("agent_reason")
                            )
                            db.add(leave_request)
                            db.commit()
                            db.refresh(leave_request)
                            
                            loop_context["current_leave_request_id"] = leave_request.LeaveRequestId
                            
                            cal_res = self.calendar_agent.execute(s_date, e_date, db)
                            days_list = cal_res["days"]
                            has_half_day = "half" in text.lower() or "half" in args.get("reason", "").lower()
                            
                            for day in days_list:
                                day_type = "FullDay"
                                leave_days = 1.0
                                if has_half_day and not day["is_weekend"] and not day["is_holiday"]:
                                    day_type = "FirstHalf"
                                    leave_days = 0.5
                                    
                                db_day = LeaveRequestDay(
                                    LeaveRequestId=leave_request.LeaveRequestId,
                                    LeaveDate=day["date"],
                                    LeaveDays=leave_days,
                                    DayType=day_type,
                                    IsWeekend=day["is_weekend"],
                                    IsHoliday=day["is_holiday"]
                                )
                                db.add(db_day)
                            db.commit()
                            
                            if args.get("status") == "Pending Manager Approval":
                                self.leave_balance_agent.update_balance(
                                    employee_id=args.get("employee_id"),
                                    leave_type_id=args.get("leave_type_id"),
                                    requested_days=args.get("requested_days"),
                                    action="CreatePending",
                                    db=db
                                )
                            elif args.get("status") == "Approved":
                                self.leave_balance_agent.update_balance(
                                    employee_id=args.get("employee_id"),
                                    leave_type_id=args.get("leave_type_id"),
                                    requested_days=args.get("requested_days"),
                                    action="ApproveDirect",
                                    db=db
                                )
                            

                            emp = db.query(Employee).filter(Employee.EmployeeId == args.get("employee_id")).first()
                            emp_name = emp.FullName if emp else "An employee"
                            emp_email = emp.Email if emp else ""
                            status = args.get("status")

                            if status == "Pending Manager Approval":
                                # Notify only the employee and their manager
                                manager_notif_msg = (
                                    f"{emp_name} ({emp_email}) has submitted a leave request for "
                                    f"{args.get('requested_days')} day(s) from {args.get('start_date')} to {args.get('end_date')}. "
                                    f"Please review and approve or reject."
                                )
                                if emp and emp.ManagerId:
                                    self.notification_agent.execute(
                                        employee_id=emp.ManagerId,
                                        leave_request_id=leave_request.LeaveRequestId,
                                        subject=f"Action Required: Leave Request from {emp_name}",
                                        message=manager_notif_msg,
                                        db=db
                                    )

                            elif status == "Approved":
                                # Notify ALL other active employees
                                other_employees = db.query(Employee).filter(
                                    Employee.EmployeeId != args.get("employee_id"),
                                    Employee.IsActive == 1
                                ).all()
                                for other_emp in other_employees:
                                    self.notification_agent.execute(
                                        employee_id=other_emp.EmployeeId,
                                        leave_request_id=leave_request.LeaveRequestId,
                                        subject=f"Leave Approved: {emp_name} ({args.get('requested_days')} day(s))",
                                        message=(
                                            f"{emp_name} ({emp_email}) has an approved leave for "
                                            f"{args.get('requested_days')} day(s) from {args.get('start_date')} to {args.get('end_date')}."
                                        ),
                                        db=db
                                    )

                            
                            tool_result = {"success": True, "leave_request_id": leave_request.LeaveRequestId}
                        except Exception as e:
                            db.rollback()
                            tool_result = {"error": f"Failed creating leave request: {str(e)}"}
                            
                    elif tool_name == "create_approval_task":
                        agent_name_for_audit = "ApprovalAgent"
                        tool_result = self.approval_agent.execute(
                            leave_request_id=args.get("leave_request_id"),
                            manager_id=args.get("manager_id"),
                            db=db
                        )
                        
                    elif tool_name == "send_notification":
                        agent_name_for_audit = "NotificationAgent"
                        tool_result = self.notification_agent.execute(
                            employee_id=args.get("employee_id"),
                            leave_request_id=args.get("leave_request_id"),
                            subject=args.get("subject"),
                            message=args.get("message"),
                            db=db
                        )
                        
                    elif tool_name == "submit_validation_result":
                        loop_context["validation_result"] = args
                        tool_result = {"success": True}
                        
                    tool_end = datetime.now()
                    if agent_name_for_audit:
                        self.audit_agent.execute(
                            agent_name=agent_name_for_audit,
                            input_data=args,
                            output_data=tool_result,
                            status="Success" if "error" not in tool_result else "Failed",
                            db=db,
                            leave_request_id=loop_context["current_leave_request_id"],
                            started_at=tool_start,
                            completed_at=tool_end
                        )
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(tool_result)
                    })
                
                if loop_context["validation_result"] is not None:
                    break
            
            v_res = loop_context["validation_result"]
            if not v_res:
                return {
                    "success": False,
                    "message": "Orchestrator error: LLM finished executing without submitting final result."
                }
                
            supervisor_end = datetime.now()
            output_payload = {
                "status": v_res["status"],
                "reason": v_res.get("reason"),
                "requested_days": v_res["requested_days"],
                "remaining_balance": v_res["remaining_balance"]
            }
            self.audit_agent.execute(
                agent_name="SupervisorAgent",
                input_data=input_payload,
                output_data=output_payload,
                status="Success",
                db=db,
                leave_request_id=loop_context["current_leave_request_id"],
                started_at=supervisor_start,
                completed_at=supervisor_end
            )
            
            # Compute weekends/holidays for the final result
            try:
                s_date = datetime.strptime(v_res["start_date"], "%Y-%m-%d").date()
                e_date = datetime.strptime(v_res["end_date"], "%Y-%m-%d").date()
                cal_res = self.calendar_agent.execute(s_date, e_date, db)
                weekend_dates = [str(d["date"]) for d in cal_res["days"] if d["is_weekend"]]
                holiday_dates = [str(d["date"]) for d in cal_res["days"] if d["is_holiday"]]
            except Exception:
                weekend_dates = []
                holiday_dates = []

            return {
                "success": True,
                "status": v_res["status"],
                "reason": v_res.get("reason"),
                "requested_days": v_res["requested_days"],
                "remaining_balance": v_res["remaining_balance"],
                "start_date": v_res["start_date"],
                "end_date": v_res["end_date"],
                "weekend_dates": weekend_dates,
                "holiday_dates": holiday_dates
            }

        except Exception as e:
            print(f"Supervisor LLM execution failed, falling back to deterministic pipeline. Error: {e}")
            return self._execute_fallback_deterministic(employee_id, text, db, supervisor_start, input_payload)

    def _execute_fallback_deterministic(self, employee_id: int, text: str, db, supervisor_start, input_payload):
        # 1. Run LLM Extraction (with its internal fallback)
        try:
            # Fetch Context for LLM (Balances, Policies, History, Teammates, Pending requests, and Holidays)
            context_str = self._get_context_str(employee_id, db)

            llm_result = self.llm_service.process_chat(text, context_str)
            if llm_result.get("intent") == "general_inquiry":
                return {
                    "success": True,
                    "response": llm_result.get("chat_response", "I could not generate a response.")
                }
                
            llm_details = llm_result.get("leave_details", {})
            
            extracted_start = llm_details.get("start_date")
            extracted_end = llm_details.get("end_date")
            extracted_type = llm_details.get("leave_type", "Casual Leave")
            extracted_reason = llm_details.get("reason", "")

            if not extracted_start or not extracted_end:
                return {
                    "success": False,
                    "message": "Fallback: Could not determine start or end dates."
                }

            lt_record = db.query(LeaveType).filter(LeaveType.LeaveTypeName.ilike(f"%{extracted_type}%")).first()
            if not lt_record:
                return {
                    "success": False,
                    "message": f"Fallback: Unrecognized leave type: '{extracted_type}'"
                }
            leave_type_id = lt_record.LeaveTypeId

            start_date = datetime.strptime(extracted_start, "%Y-%m-%d").date()
            end_date = datetime.strptime(extracted_end, "%Y-%m-%d").date()

            # Employee profile check
            emp_result = self.employee_agent.execute(employee_id, db)
            if not emp_result.get("success"):
                return {"success": False, "message": emp_result.get("message")}

            # Calendar check
            cal_result = self.calendar_agent.execute(start_date, end_date, db)
            has_half_day = "half" in text.lower()
            working_days = cal_result["working_days"]
            days_list = cal_result["days"]

            if has_half_day:
                for day in days_list:
                    if not day["is_weekend"] and not day["is_holiday"]:
                        day["day_type"] = "FirstHalf"
                        day["leave_days"] = 0.5
                working_days = 0.5 * working_days

            # Leave Balance
            bal_result = self.leave_balance_agent.execute(employee_id, leave_type_id, db)
            if not bal_result.get("success"):
                return {"success": False, "message": bal_result.get("message")}

            if working_days == 0:
                return {
                    "success": True,
                    "status": "No Action Required",
                    "reason": "All selected dates fall on weekends or holidays (0 working days). No request submitted.",
                    "requested_days": 0,
                    "remaining_balance": bal_result["remaining_days"]
                }

            # Leave Policy
            pol_result = self.leave_policy_agent.execute(leave_type_id, db)
            if not pol_result.get("success"):
                return {"success": False, "message": pol_result.get("message")}

            # Overlap
            overlap_result = self.leave_overlap_agent.execute(employee_id, start_date, end_date, db)
            if not overlap_result.get("success"):
                return {"success": False, "message": overlap_result.get("message")}

            # Team Availability
            team_result = self.team_agent.execute(
                department_id=emp_result["department_id"],
                start_date=start_date,
                end_date=end_date,
                threshold_percent=pol_result["team_threshold"],
                db=db
            )
            if not team_result.get("success"):
                return {"success": False, "message": team_result.get("message")}

            # Notice
            today_date = date.today()
            notice_days = (start_date - today_date).days

            # Monthly Limit removed — no cap applies
            monthly_limit_exceeded = False

            # Check for previous approved requests of the same type in the same calendar month
            has_previous_approved = False
            approved_count = 0
            limit = 1
            try:
                approved_count = db.query(LeaveRequest).filter(
                    LeaveRequest.EmployeeId == employee_id,
                    LeaveRequest.LeaveTypeId == leave_type_id,
                    LeaveRequest.Status == "Approved",
                    extract('month', LeaveRequest.StartDate) == start_date.month,
                    extract('year', LeaveRequest.StartDate) == start_date.year
                ).count()
                
                policy = db.query(LeavePolicy).filter(
                    LeavePolicy.LeaveTypeId == leave_type_id,
                    LeavePolicy.IsActive == True
                ).first()
                limit = policy.AutoApprovalMaxRequestsPerMonth if (policy and policy.AutoApprovalMaxRequestsPerMonth is not None) else 1
                
                if approved_count >= limit:
                    has_previous_approved = True
            except Exception as ex:
                print(f"Error checking previous approvals in fallback: {ex}")

            # Decision Agent
            decision_data = {
                "employee_active": emp_result["is_active"] == 1 or emp_result["is_active"] is True,
                "remaining_balance": bal_result["remaining_days"],
                "working_days": working_days,
                "notice_days": notice_days,
                "min_notice_days": pol_result["min_notice_days"],
                "medical_certificate_after_days": pol_result["medical_certificate_after_days"],
                "allow_half_day": pol_result["allow_half_day"],
                "has_half_day": has_half_day,
                "auto_approval_max_days": pol_result["auto_approval_max_days"],
                "overlap_found": overlap_result["overlap_found"],
                "threshold_exceeded": team_result["threshold_exceeded"],
                "monthly_limit_exceeded": monthly_limit_exceeded,
                "has_previous_approved_in_month": has_previous_approved,
                "approved_requests_count_in_month": approved_count,
                "auto_approval_max_requests_per_month": limit
            }

            decision_result = self.decision_agent.execute(decision_data)

            # DB persistence
            leave_request = LeaveRequest(
                EmployeeId=employee_id,
                LeaveTypeId=leave_type_id,
                StartDate=start_date,
                EndDate=end_date,
                RequestedDays=working_days,
                Reason=extracted_reason,
                Status=decision_result["status"],
                AgentDecision=decision_result["decision"],
                AgentReason=decision_result.get("reason")
            )
            db.add(leave_request)
            db.commit()
            db.refresh(leave_request)

            for day in days_list:
                db_day = LeaveRequestDay(
                    LeaveRequestId=leave_request.LeaveRequestId,
                    LeaveDate=day["date"],
                    LeaveDays=day.get("leave_days", 1.0),
                    DayType=day.get("day_type", "FullDay"),
                    IsWeekend=day["is_weekend"],
                    IsHoliday=day["is_holiday"]
                )
                db.add(db_day)
            db.commit()

            leave_request_id = leave_request.LeaveRequestId

            # Balance update
            if decision_result["status"] == "Pending Manager Approval":
                self.leave_balance_agent.update_balance(employee_id, leave_type_id, working_days, "CreatePending", db)
            elif decision_result["status"] == "Approved":
                self.leave_balance_agent.update_balance(employee_id, leave_type_id, working_days, "ApproveDirect", db)


            emp = db.query(Employee).filter(Employee.EmployeeId == employee_id).first()
            emp_name = emp.FullName if emp else "An employee"
            emp_email = emp.Email if emp else ""

            if decision_result["status"] == "Pending Manager Approval":
                # Notify only the manager
                if emp_result.get("manager_id"):
                    self.notification_agent.execute(
                        employee_id=emp_result["manager_id"],
                        leave_request_id=leave_request.LeaveRequestId,
                        subject=f"Action Required: Leave Request from {emp_name}",
                        message=(
                            f"{emp_name} ({emp_email}) has submitted a leave request for "
                            f"{working_days} day(s) from {extracted_start} to {extracted_end}. "
                            f"Please review and approve or reject."
                        ),
                        db=db
                    )

            elif decision_result["status"] == "Approved":
                # Notify ALL other active employees
                other_employees = db.query(Employee).filter(
                    Employee.EmployeeId != employee_id,
                    Employee.IsActive == 1
                ).all()
                for other_emp in other_employees:
                    self.notification_agent.execute(
                        employee_id=other_emp.EmployeeId,
                        leave_request_id=leave_request.LeaveRequestId,
                        subject=f"Leave Approved: {emp_name} ({working_days} day(s))",
                        message=(
                            f"{emp_name} ({emp_email}) has an approved leave for "
                            f"{working_days} day(s) from {extracted_start} to {extracted_end}."
                        ),
                        db=db
                    )

            # Approval Task
            if decision_result["status"] == "Pending Manager Approval" and emp_result["manager_id"]:
                self.approval_agent.execute(leave_request_id, emp_result["manager_id"], db)

            # Notification
            notif_msg = f"Your leave request for {working_days} days is {decision_result['status']}."
            if decision_result.get("reason"):
                notif_msg += f" Reason: {decision_result['reason']}."
            self.notification_agent.execute(employee_id, leave_request_id, "Leave Request Status Updated", notif_msg, db)

            # Audit trace logs for intermediate agent steps
            self.audit_agent.execute("EmployeeProfileAgent", {"employee_id": employee_id}, emp_result, "Success", db, leave_request_id)
            self.audit_agent.execute("CalendarAgent", {"start_date": str(start_date), "end_date": str(end_date)}, cal_result, "Success", db, leave_request_id)
            self.audit_agent.execute("LeaveBalanceAgent", {"employee_id": employee_id, "leave_type_id": leave_type_id}, bal_result, "Success", db, leave_request_id)
            self.audit_agent.execute("LeavePolicyAgent", {"leave_type_id": leave_type_id}, pol_result, "Success", db, leave_request_id)
            self.audit_agent.execute("LeaveOverlapAgent", {"employee_id": employee_id, "start_date": str(start_date), "end_date": str(end_date)}, overlap_result, "Success", db, leave_request_id)
            self.audit_agent.execute("TeamAvailabilityAgent", {"department_id": emp_result["department_id"], "start_date": str(start_date), "end_date": str(end_date)}, team_result, "Success", db, leave_request_id)
            self.audit_agent.execute("LeaveDecisionAgent", decision_data, decision_result, decision_result["status"], db, leave_request_id)

            # Supervisor audit log
            self.audit_agent.execute(
                agent_name="SupervisorAgent",
                input_data=input_payload,
                output_data={
                    "status": decision_result["status"],
                    "reason": decision_result.get("reason"),
                    "requested_days": working_days,
                    "remaining_balance": bal_result["remaining_days"] - (working_days if decision_result["status"] != "Rejected" else 0)
                },
                status="Success",
                db=db,
                leave_request_id=leave_request_id,
                started_at=supervisor_start,
                completed_at=datetime.now()
            )

            latest_balance = self.leave_balance_agent.execute(employee_id, leave_type_id, db)
            remaining_bal = latest_balance["remaining_days"] if latest_balance.get("success") else bal_result["remaining_days"]

            # Extract weekends and holidays from the pre-computed days_list
            weekend_dates = [str(d["date"]) for d in days_list if d["is_weekend"]]
            holiday_dates = [str(d["date"]) for d in days_list if d["is_holiday"]]

            return {
                "success": True,
                "status": decision_result["status"],
                "reason": decision_result.get("reason"),
                "requested_days": working_days,
                "remaining_balance": remaining_bal,
                "start_date": str(start_date),
                "end_date": str(end_date),
                "weekend_dates": weekend_dates,
                "holiday_dates": holiday_dates
            }
        except Exception as fallback_err:
            db.rollback()
            return {
                "success": False,
                "message": f"Orchestrator fallback error: {str(fallback_err)}"
            }

    def _get_context_str(self, employee_id: int, db) -> str:
        # Fetch Balances
        balances = db.query(LeaveBalance, LeaveType).join(LeaveType, LeaveBalance.LeaveTypeId == LeaveType.LeaveTypeId).filter(LeaveBalance.EmployeeId == employee_id).all()
        agg_balances = {}
        for bal, lt in balances:
            name = lt.LeaveTypeName.lower().replace(" leave", "")
            if name not in agg_balances:
                agg_balances[name] = 0
            agg_balances[name] += float(bal.AllocatedDays - bal.UsedDays)
        
        context_str = "Employee Balances:\n"
        for k, v in agg_balances.items():
            context_str += f"- {k.title()} Leave: {v} days remaining\n"
        
        # Fetch Policies
        policies = db.query(LeavePolicy, LeaveType).join(LeaveType, LeavePolicy.LeaveTypeId == LeaveType.LeaveTypeId).filter(LeavePolicy.IsActive == True).all()
        unique_policies = {}
        for p, lt in policies:
            name = lt.LeaveTypeName
            if name not in unique_policies:
                unique_policies[name] = (p, lt)
        
        context_str += "\nCompany Leave Policy:\n"
        for name, (p, lt) in unique_policies.items():
            context_str += f"- {name}: "
            if lt.AnnualLimit:
                context_str += f"Annual Limit: {lt.AnnualLimit} days. "
            if p.MinNoticeDays > 0:
                context_str += f"Requires {p.MinNoticeDays} days advance notice. "
            if p.AutoApprovalMaxDays:
                context_str += f"Auto-approved up to {p.AutoApprovalMaxDays} days."
            context_str += "\n"

        # Fetch Recent Leave History
        history = db.query(LeaveRequest, LeaveType).join(
            LeaveType, LeaveRequest.LeaveTypeId == LeaveType.LeaveTypeId
        ).filter(
            LeaveRequest.EmployeeId == employee_id
        ).order_by(LeaveRequest.StartDate.desc()).limit(5).all()
        
        context_str += "\nEmployee Recent Leave History:\n"
        if history:
            for req, lt in history:
                context_str += f"- {lt.LeaveTypeName}: from {req.StartDate} to {req.EndDate} ({req.RequestedDays} days) - Status: {req.Status}\n"
        else:
            context_str += "- No past leave requests found.\n"

        # Fetch Pending Leave Requests
        emp = db.query(Employee).filter(Employee.EmployeeId == employee_id).first()
        if emp:
            if emp.Role == "manager":
                pending_reqs = db.query(LeaveRequest, Employee, LeaveType).join(
                    Employee, LeaveRequest.EmployeeId == Employee.EmployeeId
                ).join(
                    LeaveType, LeaveRequest.LeaveTypeId == LeaveType.LeaveTypeId
                ).filter(
                    Employee.ManagerId == employee_id,
                    LeaveRequest.Status == "Pending Manager Approval"
                ).all()
                
                context_str += "\nPending Requests to Approve:\n"
                if pending_reqs:
                    for req, requester, lt in pending_reqs:
                        context_str += f"- Request ID {req.LeaveRequestId} by {requester.FullName}: {lt.LeaveTypeName} from {req.StartDate} to {req.EndDate} ({req.RequestedDays} days) - Status: {req.Status}\n"
                else:
                    context_str += "- No pending requests to approve.\n"
            else:
                pending_reqs = db.query(LeaveRequest, LeaveType).join(
                    LeaveType, LeaveRequest.LeaveTypeId == LeaveType.LeaveTypeId
                ).filter(
                    LeaveRequest.EmployeeId == employee_id,
                    LeaveRequest.Status == "Pending Manager Approval"
                ).all()
                
                context_str += "\nYour Pending Requests:\n"
                if pending_reqs:
                    for req, lt in pending_reqs:
                        context_str += f"- {lt.LeaveTypeName}: from {req.StartDate} to {req.EndDate} ({req.RequestedDays} days) - Status: {req.Status}\n"
                else:
                    context_str += "- No pending requests found.\n"

            # Fetch Teammate History
            if emp.DepartmentId is not None:
                team_history = db.query(LeaveRequest, Employee, LeaveType).join(
                    Employee, LeaveRequest.EmployeeId == Employee.EmployeeId
                ).join(
                    LeaveType, LeaveRequest.LeaveTypeId == LeaveType.LeaveTypeId
                ).filter(
                    Employee.DepartmentId == emp.DepartmentId,
                    Employee.EmployeeId != employee_id,
                    LeaveRequest.Status.in_(["Approved", "Pending Manager Approval"])
                ).order_by(LeaveRequest.StartDate.desc()).limit(5).all()
                
                context_str += "\nTeam/Teammates Recent Leave History:\n"
                if team_history:
                    for req, teammate, lt in team_history:
                        context_str += f"- {teammate.FullName}: {lt.LeaveTypeName} from {req.StartDate} to {req.EndDate} ({req.RequestedDays} days) - Status: {req.Status}\n"
                else:
                    context_str += "- No teammates leave requests found.\n"

        # Fetch Holidays
        from database.models import Holiday
        holidays = db.query(Holiday).filter(
            Holiday.HolidayDate >= date.today()
        ).order_by(Holiday.HolidayDate.asc()).limit(10).all()
        
        context_str += "\nUpcoming Company Holidays:\n"
        if holidays:
            for h in holidays:
                context_str += f"- {h.HolidayName}: {h.HolidayDate}\n"
        else:
            context_str += "- No upcoming holidays found.\n"

        return context_str
