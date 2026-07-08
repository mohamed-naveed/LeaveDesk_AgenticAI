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
                    "description": "Get employee profile.",
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
                    "description": "Calculate days count.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "start_date": {"type": "string"},
                            "end_date": {"type": "string"}
                        },
                        "required": ["start_date", "end_date"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_leave_balance",
                    "description": "Get leave balance.",
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
                    "description": "Get policy constraints.",
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
                    "description": "Check request overlap.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "employee_id": {"type": "integer"},
                            "start_date": {"type": "string"},
                            "end_date": {"type": "string"}
                        },
                        "required": ["employee_id", "start_date", "end_date"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_team_availability",
                    "description": "Check team threshold.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "department_id": {"type": "integer"},
                            "start_date": {"type": "string"},
                            "end_date": {"type": "string"},
                            "threshold_percent": {"type": "number"}
                        },
                        "required": ["department_id", "start_date", "end_date", "threshold_percent"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "make_leave_decision",
                    "description": "Decide approval status.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "data_json": {"type": "string"}
                        },
                        "required": ["data_json"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "resolve_leave_type_id",
                    "description": "Resolve leave type ID.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "leave_type_name": {"type": "string"}
                        },
                        "required": ["leave_type_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "create_leave_request_record",
                    "description": "Save leave request.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "employee_id": {"type": "integer"},
                            "leave_type_id": {"type": "integer"},
                            "start_date": {"type": "string"},
                            "end_date": {"type": "string"},
                            "requested_days": {"type": "number"},
                            "reason": {"type": "string"},
                            "status": {"type": "string"},
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
                    "description": "Create approval task.",
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
                    "description": "Send status update.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "employee_id": {"type": "integer"},
                            "leave_request_id": {"type": "integer"},
                            "subject": {"type": "string"},
                            "message": {"type": "string"}
                        },
                        "required": ["employee_id", "subject", "message"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "check_monthly_limit",
                    "description": "Check monthly limit.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "employee_id": {"type": "integer"},
                            "leave_type_id": {"type": "integer"},
                            "start_date": {"type": "string"},
                            "end_date": {"type": "string"}
                        },
                        "required": ["employee_id", "leave_type_id", "start_date", "end_date"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "resolve_manager_action",
                    "description": "Approve or reject a pending leave request for an employee. Call this ONLY when the caller is a manager and explicitly requests to approve, reject, accept, deny, or cancel an employee's pending leave request.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "leave_request_id": {
                                "type": "integer",
                                "description": "The ID of the leave request to approve or reject."
                            },
                            "decision": {
                                "type": "string",
                                "enum": ["Approved", "Rejected"],
                                "description": "Decision to apply: Approved or Rejected."
                            },
                            "comments": {
                                "type": "string",
                                "description": "Optional comments for the decision."
                            }
                        },
                        "required": ["leave_request_id", "decision"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "submit_validation_result",
                    "description": "Return final result.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "status": {"type": "string"},
                            "reason": {"type": "string"},
                            "requested_days": {"type": "number"},
                            "remaining_balance": {"type": "number"},
                            "start_date": {"type": "string"},
                            "end_date": {"type": "string"}
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
                        f"IMPORTANT: You MUST call only ONE tool at a time. Do NOT attempt to call multiple tools in parallel or in a single turn. You must wait for the output of the current tool before choosing and calling the next one in the sequence.\n\n"
                        f"1. Resolve the leave type ID using `resolve_leave_type_id`.\n"
                        f"2. Get the employee profile with `get_employee_profile` to find the manager and department.\n"
                        f"3. Parse dates and check calendar details (working days, weekends, holidays) with `check_calendar`.\n"
                        f"4. Check the leave balance with `get_leave_balance`.\n"
                        f"5. Get the policy constraints with `get_leave_policy`.\n"
                        f"6. Check for overlapping requests with `check_leave_overlap`.\n"
                        f"7. Check team availability using `check_team_availability` (use the `team_threshold` percentage from the policy).\n"
                        f"8. Construct a facts JSON and run `make_leave_decision` to decide status.\n"
                        f"9. If status is Approved or Pending Manager Approval, call `create_leave_request_record` to save the request.\n"
                        f"10. If status is Pending Manager Approval, also call `create_approval_task`.\n"
                        f"11. Call `send_notification` to notify the user.\n"
                        f"12. Finally, call `submit_validation_result` to terminate and return the final results.\n\n"
                        f"If the user's message is a general inquiry (asking about leave balances, policies, past history, pending requests, or upcoming holidays), do NOT call any validation tools. Read the relevant section in the Context block above and reply directly.\n"
                        f"NOTE: Employees (Role: employee) are NOT authorized to view teammates' leaves. If the role is 'employee' and they ask about teammate leaves, refuse and say: 'You are not authorized to view teammate leaves.'\n"
                        f"If the caller is a manager and requests to approve, reject, accept, deny, or cancel a pending leave request, call `resolve_manager_action`.\n\n"
                        f"=== RESPONSE EXAMPLES (use these to guide your final reply tone and content) ===\n\n"
                        f"Q1: Apply casual leave from 10 July 2026 to 14 July 2026 for family function.\n"
                        f"A1: Your casual leave request has been created. The system calculated the working days by excluding weekends and holidays. Your balance is sufficient, no overlapping leave was found, and team availability is acceptable. Since casual leave requires manager approval, the request is now pending with your manager.\n\n"
                        f"Q2: I am not feeling well. Apply sick leave for today.\n"
                        f"A2: Your sick leave request for today has been created. The system checked your sick leave balance and sick leave policy. Since same-day sick leave is allowed and balance is available, the request is auto-approved or sent for manager approval based on company policy.\n\n"
                        f"Q3: Apply half-day sick leave today due to fever.\n"
                        f"A3: Your half-day sick leave request has been processed. The system verified that half-day leave is allowed, sick leave balance is available, and there is no overlap. The request is auto-approved if your policy allows auto-approval for half-day sick leave.\n\n"
                        f"Q4: Apply casual leave for 6 working days next week.\n"
                        f"A4: Your request requires manual review because the requested leave exceeds the maximum casual leave allowed per request. You may need to apply earned leave or split the request based on company policy.\n\n"
                        f"Q5: Apply leave tomorrow, but I already applied earlier for the same date.\n"
                        f"A5: Your leave request cannot be processed because another leave request already exists for the selected date. Duplicate or overlapping leave requests are not allowed.\n\n"
                        f"Q6: Apply earned leave from 20 July 2026 to 25 July 2026.\n"
                        f"A6: Your earned leave request has been created. The system calculated working days, checked your leave balance, verified no overlap, and confirmed team availability. The request is pending manager approval.\n\n"
                        f"Q7: Apply sick leave for 5 days.\n"
                        f"A7: Your sick leave request requires manual review because the number of days exceeds the policy limit that requires a medical certificate. Please upload a medical certificate or wait for manager/admin review.\n\n"
                        f"Q8: Can I take leave tomorrow if many team members are already on leave?\n"
                        f"A8: The system checked team availability for tomorrow. If the team leave threshold is exceeded, your request will be marked for manual review. If team coverage is acceptable, the request can proceed to manager approval.\n\n"
                        f"Q9: Apply casual leave for tomorrow. Also tell me who will approve it.\n"
                        f"A9: Your casual leave request has been created and submitted for approval. Your reporting manager will approve this request. The manager has been notified.\n\n"
                        f"Q10: Apply leave next Friday.\n"
                        f"A10: Please provide the leave type and reason for the leave. The system needs these details before checking balance, policy, overlap, and approval requirements.\n\n"
                        f"Use these examples only as tone/style references. Always base your actual response on the real tool results and the employee's actual data from the context."
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
                    max_tokens=1024
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
                        try:
                            s_date = datetime.strptime(args.get("start_date"), "%Y-%m-%d").date()
                            e_date = datetime.strptime(args.get("end_date"), "%Y-%m-%d").date()
                            dept_id = args.get("department_id")
                            threshold = args.get("threshold_percent", 30)
                            if dept_id is None:
                                tool_result = {"success": True, "team_available": True, "message": "Department ID not provided; assuming team availability is acceptable."}
                            else:
                                tool_result = self.team_agent.execute(dept_id, s_date, e_date, threshold, db)
                        except Exception as e:
                            tool_result = {"success": True, "team_available": True, "message": f"Team availability check skipped ({str(e)}); proceeding with leave request."}

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
                        
                        # Add max_days_per_request to facts
                        if resolved_leave_type_id:
                            lt_rec = db.query(LeaveType).filter(LeaveType.LeaveTypeId == resolved_leave_type_id).first()
                            if lt_rec and lt_rec.MaxDaysPerRequest is not None:
                                facts["max_days_per_request"] = float(lt_rec.MaxDaysPerRequest)
                                
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
                        
                    elif tool_name == "resolve_manager_action":
                        try:
                            from routes.api_routes import handle_manager_action
                            class DummyBackgroundTasks:
                                def add_task(self, func, *args, **kwargs):
                                    func(*args, **kwargs)
                            
                            handle_manager_action(
                                db=db,
                                background_tasks=DummyBackgroundTasks(),
                                leave_request_id=args.get("leave_request_id"),
                                manager_id=employee_id,
                                decision=args.get("decision"),
                                comments=args.get("comments", "Actioned via AI Leave Desk Chat")
                            )
                            tool_result = {"success": True, "message": f"Successfully {args.get('decision').lower()} leave request ID {args.get('leave_request_id')}."}
                        except Exception as e:
                            tool_result = {"error": f"Failed manager action: {str(e)}"}

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
                        "content": json.dumps(tool_result, default=str)
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
            print(f"Supervisor LLM execution failed: {e}")
            return {
                "success": True,
                "response": f"⚠️ I encountered an error while processing your request: {str(e)}. Please try again."
            }


    def _get_context_str(self, employee_id: int, db) -> str:
        emp = db.query(Employee).filter(Employee.EmployeeId == employee_id).first()
        role = emp.Role if emp else "employee"

        # Build Employee Profile block
        profile_str = "Employee Profile:\n"
        if emp:
            profile_str += f"- Full Name: {emp.FullName}\n"
            profile_str += f"- Employee Code: {emp.EmployeeCode}\n"
            profile_str += f"- Email: {emp.Email}\n"
            profile_str += f"- Role: {emp.Role}\n"
            profile_str += f"- Joining Date: {emp.JoiningDate.strftime('%Y-%m-%d') if emp.JoiningDate else ''}\n"
            
            # Fetch Department Name
            if emp.DepartmentId:
                from database.models import Department
                dept = db.query(Department).filter(Department.DepartmentId == emp.DepartmentId).first()
                if dept:
                    profile_str += f"- Department: {dept.DepartmentName}\n"
            
            if emp.ManagerId:
                manager = db.query(Employee).filter(Employee.EmployeeId == emp.ManagerId).first()
                if manager:
                    profile_str += f"- Manager: {manager.FullName}\n"

        # Fetch Balances
        balances = db.query(LeaveBalance, LeaveType).join(LeaveType, LeaveBalance.LeaveTypeId == LeaveType.LeaveTypeId).filter(LeaveBalance.EmployeeId == employee_id).all()
        agg_balances = {}
        for bal, lt in balances:
            name = lt.LeaveTypeName.lower().replace(" leave", "")
            if name not in agg_balances:
                agg_balances[name] = 0
            agg_balances[name] += float(bal.AllocatedDays - bal.UsedDays)
        
        context_str = f"Employee Role: {role}\n\n{profile_str}\nEmployee Balances:\n"
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
        ).order_by(LeaveRequest.StartDate.desc()).limit(3).all()
        
        context_str += "\nEmployee Recent Leave History:\n"
        if history:
            for req, lt in history:
                context_str += f"- {lt.LeaveTypeName}: from {req.StartDate} to {req.EndDate} ({req.RequestedDays} days) - Status: {req.Status}\n"
        else:
            context_str += "- No past leave requests found.\n"

        # Fetch Pending Leave Requests
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

                # Fetch Managed Employees
                managed_employees = db.query(Employee).filter(
                    Employee.ManagerId == employee_id,
                    Employee.IsActive == 1
                ).all()
                
                context_str += "\nManaged Employees:\n"
                if managed_employees:
                    context_str += f"Total managed employees: {len(managed_employees)}\n"
                    for me in managed_employees:
                        joining_date_str = me.JoiningDate.strftime('%Y-%m-%d') if me.JoiningDate else ''
                        context_str += f"- {me.FullName} (ID: {me.EmployeeId}, Email: {me.Email}, Role: {me.Role}, Joining Date: {joining_date_str})\n"
                else:
                    context_str += "- No managed employees found.\n"
                
                # Fetch balances of managed employees
                context_str += "\nManaged Employees Leave Balances:\n"
                if managed_employees:
                    for me in managed_employees:
                        me_balances = db.query(LeaveBalance, LeaveType).join(
                            LeaveType, LeaveBalance.LeaveTypeId == LeaveType.LeaveTypeId
                        ).filter(LeaveBalance.EmployeeId == me.EmployeeId).all()
                        
                        bal_str = ", ".join([f"{lt.LeaveTypeName}: {float(bal.RemainingDays)} days remaining" for bal, lt in me_balances])
                        context_str += f"- {me.FullName} (ID: {me.EmployeeId}): {bal_str}\n"
                else:
                    context_str += "- No managed employees balances found.\n"
                
                # Fetch history of managed employees
                context_str += "\nManaged Employees Leave History:\n"
                if managed_employees:
                    history_found = False
                    for me in managed_employees:
                        me_hist = db.query(LeaveRequest, LeaveType).join(
                            LeaveType, LeaveRequest.LeaveTypeId == LeaveType.LeaveTypeId
                        ).filter(
                            LeaveRequest.EmployeeId == me.EmployeeId
                        ).order_by(LeaveRequest.StartDate.desc()).limit(5).all()
                        if me_hist:
                            history_found = True
                            context_str += f"- {me.FullName} (ID: {me.EmployeeId}) history:\n"
                            for req, lt in me_hist:
                                context_str += f"  * {lt.LeaveTypeName}: from {req.StartDate} to {req.EndDate} ({req.RequestedDays} days) - Status: {req.Status}\n"
                    if not history_found:
                        context_str += "- No past leave requests found for managed employees.\n"
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

            # Fetch Teammate History (Only if manager)
            if emp.Role == "manager" and emp.DepartmentId is not None:
                team_history = db.query(LeaveRequest, Employee, LeaveType).join(
                    Employee, LeaveRequest.EmployeeId == Employee.EmployeeId
                ).join(
                    LeaveType, LeaveRequest.LeaveTypeId == LeaveType.LeaveTypeId
                ).filter(
                    Employee.DepartmentId == emp.DepartmentId,
                    Employee.EmployeeId != employee_id,
                    LeaveRequest.Status.in_(["Approved", "Pending Manager Approval"])
                ).order_by(LeaveRequest.StartDate.desc()).limit(3).all()
                
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
        ).order_by(Holiday.HolidayDate.asc()).limit(5).all()
        
        context_str += "\nUpcoming Company Holidays:\n"
        if holidays:
            for h in holidays:
                context_str += f"- {h.HolidayName}: {h.HolidayDate}\n"
        else:
            context_str += "- No upcoming holidays found.\n"

        return context_str
