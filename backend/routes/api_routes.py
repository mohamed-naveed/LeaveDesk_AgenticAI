import os
from fastapi import APIRouter, Depends, HTTPException, Body, BackgroundTasks, Header, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session
from database.connection import get_db
from database.models import Employee, LeaveBalance, LeaveType, LeaveRequest, AgentExecutionLog
from schemas.leave_request_schema import LeaveApplyRequest, LeaveApplyResponse
from schemas.manager_action_schema import ManagerActionRequest, ManagerDecisionRequest
from schemas.auth_schema import LoginRequest, LoginResponse, EmployeeMeResponse
from services.auth_service import verify_password, create_access_token, decode_access_token, hash_password

import bcrypt

# Import all agents
from agents.employee_profile_agent import EmployeeProfileAgent
from agents.leave_balance_agent import LeaveBalanceAgent
from agents.calendar_agent import CalendarAgent
from agents.leave_policy_agent import LeavePolicyAgent
from agents.leave_overlap_agent import LeaveOverlapAgent
from agents.team_availability_agent import TeamAvailabilityAgent
from agents.leave_decision_agent import LeaveDecisionAgent
from agents.approval_agent import ApprovalAgent
from agents.notification_agent import NotificationAgent
from agents.audit_agent import AuditAgent
from agents.supervisor_agent import SupervisorAgent

from services.llm_service import LLMService

router = APIRouter()

# Instantiate LLMService globally using the environment key
api_key = os.getenv("OPENAI_API_KEY", "")
llm_service = LLMService(api_key)


# ==========================================
# 1. Authentication Routes
# ==========================================

def get_current_employee(authorization: str = Header(...), db: Session = Depends(get_db)):
    """Dependency to extract and validate JWT from Authorization header."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header format")

    token = authorization.split(" ", 1)[1]
    payload = decode_access_token(token)

    if payload is None:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    employee_id = payload.get("employee_id")
    if employee_id is None:
        raise HTTPException(status_code=401, detail="Token missing employee_id")

    employee = db.query(Employee).filter(Employee.EmployeeId == employee_id).first()
    if not employee:
        raise HTTPException(status_code=401, detail="Employee not found")

    return employee

@router.post("/auth/login", response_model=LoginResponse, tags=["Authentication"])
def auth_login(request: LoginRequest, db: Session = Depends(get_db)):
    employee = db.query(Employee).filter(Employee.Email == request.email).first()
    if not employee:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not employee.PasswordHash:
        raise HTTPException(status_code=401, detail="Account not set up. Please contact admin.")

    if not verify_password(request.password, employee.PasswordHash):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(data={
        "employee_id": employee.EmployeeId,
        "email": employee.Email,
        "role": "admin" if employee.Role == "manager" else (employee.Role or "employee")
    })

    return LoginResponse(
        access_token=token,
        employee_id=employee.EmployeeId,
        full_name=employee.FullName,
        email=employee.Email,
        role="admin" if employee.Role == "manager" else (employee.Role or "employee")
    )

@router.get("/auth/me", response_model=EmployeeMeResponse, tags=["Authentication"])
def get_me(current_employee: Employee = Depends(get_current_employee)):
    return EmployeeMeResponse(
        employee_id=current_employee.EmployeeId,
        employee_code=current_employee.EmployeeCode,
        full_name=current_employee.FullName,
        email=current_employee.Email,
        department_id=current_employee.DepartmentId,
        manager_id=current_employee.ManagerId,
        role=current_employee.Role or "employee"
    )

@router.post("/auth/setup-password", tags=["Authentication"])
def setup_password(email: str, password: str, db: Session = Depends(get_db)):
    employee = db.query(Employee).filter(Employee.Email == email).first()
    if not employee:
        raise HTTPException(status_code=404, detail="Employee not found")

    employee.PasswordHash = hash_password(password)
    db.commit()
    return {"message": f"Password set for {employee.FullName} ({email})"}


# WebSocket routes removed


# ==========================================
# 3. Dashboard & Chat System Routes
# ==========================================

@router.post("/api/login")
def login(payload: dict = Body(...), db: Session = Depends(get_db)):
    email = payload.get("email")
    password = payload.get("password")
    
    emp = db.query(Employee).filter(Employee.Email == email).first()
    if not emp:
        raise HTTPException(status_code=401, detail="Invalid email or password")
        
    if not emp.PasswordHash or not bcrypt.checkpw(password.encode('utf-8'), emp.PasswordHash.encode('utf-8')):
        raise HTTPException(status_code=401, detail="Invalid email or password")
        
    return {
        "id": emp.EmployeeId,
        "name": emp.FullName,
        "department": emp.DepartmentId,
        "is_active": True,
        "role": "admin" if emp.Role == "manager" else emp.Role
    }

@router.get("/api/leave-balances")
def get_leave_balances(employee_id: int, db: Session = Depends(get_db)):
    balances = db.query(LeaveBalance, LeaveType).join(LeaveType, LeaveBalance.LeaveTypeId == LeaveType.LeaveTypeId).filter(LeaveBalance.EmployeeId == employee_id).all()
    
    agg_balances = {}
    for bal, lt in balances:
        name = lt.LeaveTypeName.lower().replace(" leave", "")
        if name not in agg_balances:
            agg_balances[name] = 0
        agg_balances[name] += (bal.AllocatedDays - bal.UsedDays)
        
    result = [{"leave_type": k, "balance": v} for k, v in agg_balances.items()]
    return result

@router.get("/api/my-leave-requests")
def my_leave_requests(employee_id: int, db: Session = Depends(get_db)):
    reqs = db.query(LeaveRequest, LeaveType).join(LeaveType, LeaveRequest.LeaveTypeId == LeaveType.LeaveTypeId).filter(LeaveRequest.EmployeeId == employee_id).all()
    result = []
    status_map = {
        "Pending Manager Approval": "pending_manager",
        "Approved": "approved",
        "Rejected": "rejected",
        "Cancelled": "cancelled"
    }
    for r, lt in reqs:
        mapped_status = status_map.get(r.Status, r.Status.lower().replace(" ", "_"))
        result.append({
            "id": r.LeaveRequestId,
            "leave_type": lt.LeaveTypeName.lower().replace(" leave", ""),
            "start_date": str(r.StartDate),
            "end_date": str(r.EndDate),
            "reason": r.Reason,
            "status": mapped_status
        })
    return result

@router.post("/api/chat")
async def chat(payload: dict = Body(...), db: Session = Depends(get_db)):
    employee_id = payload.get("employee_id")
    message = payload.get("message")
    
    emp_agent = EmployeeProfileAgent()
    bal_agent = LeaveBalanceAgent()
    cal_agent = CalendarAgent()
    pol_agent = LeavePolicyAgent()
    ovr_agent = LeaveOverlapAgent()
    team_agent = TeamAvailabilityAgent()
    dec_agent = LeaveDecisionAgent()
    app_agent = ApprovalAgent()
    not_agent = NotificationAgent()
    aud_agent = AuditAgent()

    supervisor = SupervisorAgent(
        employee_agent=emp_agent,
        leave_balance_agent=bal_agent,
        calendar_agent=cal_agent,
        leave_policy_agent=pol_agent,
        leave_overlap_agent=ovr_agent,
        team_agent=team_agent,
        decision_agent=dec_agent,
        approval_agent=app_agent,
        notification_agent=not_agent,
        audit_agent=aud_agent,
        llm_service=llm_service
    )

    result = supervisor.execute(
        employee_id=employee_id,
        text=message,
        db=db
    )
    
    # Pass the LLM response directly — no hardcoded templates
    msg = (
        result.get("response")
        or result.get("chat_response")
        or result.get("message")
        or "Your request has been processed."
    )

    if not result.get("success", True):
        msg = result.get("message") or "Failed to process your request. Please try again."

    return {"response": msg}


@router.get("/api/leave-requests")
def all_leave_requests(db: Session = Depends(get_db)):
    reqs = db.query(LeaveRequest, Employee, LeaveType)\
             .join(Employee, LeaveRequest.EmployeeId == Employee.EmployeeId)\
             .join(LeaveType, LeaveRequest.LeaveTypeId == LeaveType.LeaveTypeId)\
             .all()
    result = []
    for r, emp, lt in reqs:
        result.append({
            "request_id": r.LeaveRequestId,
            "employee_name": emp.FullName,
            "department": emp.DepartmentId,
            "leave_type": lt.LeaveTypeName.lower().replace(" leave", ""),
            "start_date": str(r.StartDate),
            "end_date": str(r.EndDate),
            "reason": r.Reason,
            "status": r.Status,
            "agent_decision": r.AgentDecision,
            "agent_reason": r.AgentReason
        })
    return result

@router.get("/api/employees")
def all_employees(db: Session = Depends(get_db)):
    emps = db.query(Employee).all()
    result = []
    for emp in emps:
        result.append({
            "id": emp.EmployeeId,
            "name": emp.FullName,
            "email": emp.Email,
            "department": emp.DepartmentId,
            "role": "admin" if emp.Role == "manager" else emp.Role
        })
    return result

@router.get("/api/audit-logs")
def get_audit_logs(db: Session = Depends(get_db)):
    import json
    results = db.query(
        AgentExecutionLog, 
        Employee.FullName
    ).outerjoin(
        LeaveRequest, AgentExecutionLog.LeaveRequestId == LeaveRequest.LeaveRequestId
    ).outerjoin(
        Employee, LeaveRequest.EmployeeId == Employee.EmployeeId
    ).order_by(
        AgentExecutionLog.StartedAt.desc()
    ).limit(100).all()
    
    result = []
    for log, employee_name in results:
        emp_name = employee_name
        if not emp_name and log.InputData:
            try:
                input_json = json.loads(log.InputData)
                emp_id = input_json.get("employee_id")
                if emp_id:
                    emp_record = db.query(Employee).filter(Employee.EmployeeId == emp_id).first()
                    if emp_record:
                        emp_name = emp_record.FullName
            except Exception:
                pass
                
        result.append({
            "log_id": log.AgentExecutionLogId,
            "timestamp": str(log.StartedAt),
            "agent": log.AgentName,
            "employee_name": emp_name,
            "input": log.InputData,
            "output": log.OutputData,
            "status": log.ExecutionStatus
        })
    return result

@router.get("/api/audit-logs/{leave_request_id}")
def get_audit_logs_for_request(leave_request_id: int, db: Session = Depends(get_db)):
    logs = db.query(AgentExecutionLog).filter(
        AgentExecutionLog.LeaveRequestId == leave_request_id
    ).order_by(AgentExecutionLog.StartedAt.asc()).all()
    
    result = []
    for log in logs:
        result.append({
            "log_id": log.AgentExecutionLogId,
            "timestamp": str(log.StartedAt),
            "agent": log.AgentName,
            "input": log.InputData,
            "output": log.OutputData,
            "status": log.ExecutionStatus
        })
    return result

@router.post("/api/manage-request")
async def manage_request(payload: dict = Body(...), db: Session = Depends(get_db)):
    request_id = payload.get("request_id")
    status = payload.get("status")
    manager_id = 10

    app_agent = ApprovalAgent()
    bal_agent = LeaveBalanceAgent()
    not_agent = NotificationAgent()
    aud_agent = AuditAgent()

    leave_req = db.query(LeaveRequest).filter(LeaveRequest.LeaveRequestId == request_id).first()
    if not leave_req:
        return {"success": False, "detail": "Leave request not found"}

    approval_result = app_agent.process_manager_action(
        leave_request_id=request_id,
        manager_id=manager_id,
        decision=status,
        comments=f"Actioned from Admin Portal as {status}",
        db=db
    )

    action_type = "Approve" if status == "Approved" else "Reject"
    bal_agent.update_balance(
        employee_id=leave_req.EmployeeId,
        leave_type_id=leave_req.LeaveTypeId,
        requested_days=float(leave_req.RequestedDays),
        action=action_type,
        db=db
    )

    # Fetch requester and leave type details for rich notifications
    requester = db.query(Employee).filter(Employee.EmployeeId == leave_req.EmployeeId).first()
    req_name = requester.FullName if requester else "An employee"
    req_days = float(leave_req.RequestedDays)
    start = leave_req.StartDate
    end = leave_req.EndDate
    leave_type_obj = db.query(LeaveType).filter(LeaveType.LeaveTypeId == leave_req.LeaveTypeId).first()
    leave_type_name = leave_type_obj.LeaveTypeName if leave_type_obj else "Leave"

    # 1. Notify the requesting employee
    if status == "Approved":
        employee_msg = (
            f"Your {leave_type_name} request for {req_days} day(s) "
            f"from {start} to {end} has been Approved by the manager."
        )
    else:
        employee_msg = (
            f"Your {leave_type_name} request for {req_days} day(s) "
            f"from {start} to {end} has been {status} by the manager."
        )
    not_agent.execute(
        employee_id=leave_req.EmployeeId,
        leave_request_id=request_id,
        subject=f"Leave {status}: {leave_type_name} ({start} to {end})",
        message=employee_msg,
        db=db
    )

    if status == "Approved":
        team_msg = (
            f"{req_name} has an approved {leave_type_name} "
            f"for {req_days} day(s) from {start} to {end}. "
            f"Please plan accordingly."
        )

        # 2. Notify the manager who approved
        not_agent.execute(
            employee_id=manager_id,
            leave_request_id=request_id,
            subject=f"Leave Approved: {req_name} ({start} to {end})",
            message=team_msg,
            db=db
        )

        # 3. Notify all other active employees (teammates)
        other_employees = db.query(Employee).filter(
            Employee.EmployeeId != leave_req.EmployeeId,
            Employee.EmployeeId != manager_id,
            Employee.IsActive == 1
        ).all()
        for other_emp in other_employees:
            not_agent.execute(
                employee_id=other_emp.EmployeeId,
                leave_request_id=request_id,
                subject=f"Team Update: {req_name} on leave ({start} to {end})",
                message=team_msg,
                db=db
            )

    aud_agent.execute(
        agent_name="ApprovalAgent",
        input_data={"leave_request_id": request_id, "manager_id": manager_id, "decision": status},
        output_data=approval_result,
        status="Success",
        db=db
    )

    return {"success": True}


@router.post("/api/cancel-request")
def cancel_request(payload: dict = Body(...), db: Session = Depends(get_db)):
    request_id = payload.get("request_id")
    leave_req = db.query(LeaveRequest).filter(LeaveRequest.LeaveRequestId == request_id).first()
    if leave_req and leave_req.Status == "Pending Manager Approval":
        leave_req.Status = "Cancelled"
        db.commit()
    return {"success": True}


# ==========================================
# 4. Legacy API Endpoints (Backward Compatibility)
# ==========================================

@router.post("/api/leave/apply", response_model=LeaveApplyResponse)
def apply_leave(request: LeaveApplyRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    emp_agent = EmployeeProfileAgent()
    bal_agent = LeaveBalanceAgent()
    cal_agent = CalendarAgent()
    pol_agent = LeavePolicyAgent()
    ovr_agent = LeaveOverlapAgent()
    team_agent = TeamAvailabilityAgent()
    dec_agent = LeaveDecisionAgent()
    app_agent = ApprovalAgent()
    not_agent = NotificationAgent()
    aud_agent = AuditAgent()

    supervisor = SupervisorAgent(
        employee_agent=emp_agent,
        leave_balance_agent=bal_agent,
        calendar_agent=cal_agent,
        leave_policy_agent=pol_agent,
        leave_overlap_agent=ovr_agent,
        team_agent=team_agent,
        decision_agent=dec_agent,
        approval_agent=app_agent,
        notification_agent=not_agent,
        audit_agent=aud_agent,
        llm_service=llm_service
    )

    result = supervisor.execute(
        employee_id=request.employee_id,
        text=request.request_text,
        db=db
    )

    if not result.get("success", True) or "message" in result:
        raise HTTPException(status_code=400, detail=result.get("message", "Request execution failed"))

# WebSocket notification removed

    return {
        "status": result["status"],
        "reason": result.get("reason"),
        "requested_days": int(result["requested_days"]),
        "remaining_balance": float(result["remaining_balance"])
    }

def handle_manager_action(db: Session, background_tasks: BackgroundTasks, leave_request_id: int, manager_id: int, decision: str, comments: str):
    app_agent = ApprovalAgent()
    bal_agent = LeaveBalanceAgent()
    not_agent = NotificationAgent()
    aud_agent = AuditAgent()

    leave_req = db.query(LeaveRequest).filter(LeaveRequest.LeaveRequestId == leave_request_id).first()
    if not leave_req:
        raise HTTPException(status_code=404, detail="Leave request not found")

    approval_result = app_agent.process_manager_action(
        leave_request_id=leave_request_id,
        manager_id=manager_id,
        decision=decision,
        comments=comments,
        db=db
    )

    action_type = "Approve" if decision == "Approved" else "Reject"
    bal_agent.update_balance(
        employee_id=leave_req.EmployeeId,
        leave_type_id=leave_req.LeaveTypeId,
        requested_days=float(leave_req.RequestedDays),
        action=action_type,
        db=db
    )

    notif_msg = f"Manager {manager_id} has resolved your request as: {decision}. Comments: {comments}."
    not_agent.execute(
        employee_id=leave_req.EmployeeId,
        leave_request_id=leave_request_id,
        subject="Manager Action Applied",
        message=notif_msg,
        db=db
    )

    # If approved, notify all other active employees
    if decision == "Approved":
        requester = db.query(Employee).filter(Employee.EmployeeId == leave_req.EmployeeId).first()
        req_name = requester.FullName if requester else "An employee"
        req_email = requester.Email if requester else ""
        req_days = float(leave_req.RequestedDays)
        other_employees = db.query(Employee).filter(
            Employee.EmployeeId != leave_req.EmployeeId,
            Employee.EmployeeId != manager_id,
            Employee.IsActive == 1
        ).all()
        for other_emp in other_employees:
            not_agent.execute(
                employee_id=other_emp.EmployeeId,
                leave_request_id=leave_request_id,
                subject=f"Leave Approved: {req_name} ({req_days} day(s))",
                message=(
                    f"{req_name} ({req_email}) has an approved leave for "
                    f"{req_days} day(s) from {leave_req.StartDate} to {leave_req.EndDate}."
                ),
                db=db
            )

    input_data = {
        "leave_request_id": leave_request_id,
        "manager_id": manager_id,
        "decision": decision,
        "comments": comments
    }
    aud_agent.execute(
        agent_name="ApprovalAgent",
        input_data=input_data,
        output_data=approval_result,
        status="Success",
        db=db
    )

    # WebSocket notification removed

    return {"success": True, "status": decision}

@router.post("/api/leave/manager-action")
def manager_action(request: ManagerActionRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    return handle_manager_action(
        db=db,
        background_tasks=background_tasks,
        leave_request_id=request.leave_request_id,
        manager_id=request.manager_id,
        decision=request.decision,
        comments=request.comments
    )

@router.post("/api/manager/approve")
def manager_approve(request: ManagerDecisionRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    return handle_manager_action(
        db=db,
        background_tasks=background_tasks,
        leave_request_id=request.leave_request_id,
        manager_id=request.manager_id,
        decision="Approved",
        comments=request.comments
    )

@router.post("/api/manager/reject")
def manager_reject(request: ManagerDecisionRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    return handle_manager_action(
        db=db,
        background_tasks=background_tasks,
        leave_request_id=request.leave_request_id,
        manager_id=request.manager_id,
        decision="Rejected",
        comments=request.comments
    )

@router.get("/api/manager/pending/{manager_id}")
def get_pending_manager_leaves(manager_id: int, db: Session = Depends(get_db)):
    results = db.query(LeaveRequest, Employee.FullName)\
                .join(Employee, LeaveRequest.EmployeeId == Employee.EmployeeId)\
                .filter(
                    Employee.ManagerId == manager_id,
                    LeaveRequest.Status == "Pending Manager Approval"
                ).all()
    response = []
    for req, full_name in results:
        response.append({
            "leave_request_id": req.LeaveRequestId,
            "employee_id": req.EmployeeId,
            "employee_name": full_name,
            "start_date": str(req.StartDate),
            "end_date": str(req.EndDate),
            "requested_days": int(req.RequestedDays)
        })
    return response

@router.get("/api/employee/history/{employee_id}")
def get_employee_leave_history(employee_id: int, db: Session = Depends(get_db)):
    results = db.query(LeaveRequest, LeaveType).join(
        LeaveType, LeaveRequest.LeaveTypeId == LeaveType.LeaveTypeId
    ).filter(
        LeaveRequest.EmployeeId == employee_id
    ).all()
    response = []
    for req, lt in results:
        response.append({
            "leave_request_id": req.LeaveRequestId,
            "start_date": str(req.StartDate),
            "end_date": str(req.EndDate),
            "requested_days": float(req.RequestedDays),
            "leave_type": lt.LeaveTypeName,
            "reason": req.Reason or "",
            "status": req.Status
        })
    return response

@router.get("/api/notifications")
def get_my_notifications(employee_id: int, db: Session = Depends(get_db)):
    from database.models import Notification
    notifs = db.query(Notification).filter(
        Notification.EmployeeId == employee_id
    ).order_by(Notification.CreatedAt.desc()).limit(50).all()
    
    result = []
    for n in notifs:
        result.append({
            "notification_id": n.NotificationId,
            "subject": n.Subject,
            "message": n.Message,
            "status": n.Status,
            "sent_at": str(n.SentAt) if n.SentAt else str(n.CreatedAt),
            "created_at": str(n.CreatedAt)
        })
    return result

@router.post("/api/admin/reset-db")
def reset_database(db: Session = Depends(get_db)):
    from database.models import LeaveApproval, LeaveRequestDay, LeaveRequest, AgentExecutionLog, LeaveBalance, Notification
    try:
        # Delete from child tables first to respect foreign keys
        db.query(Notification).delete()
        db.query(LeaveApproval).delete()
        db.query(LeaveRequestDay).delete()
        db.query(AgentExecutionLog).delete()
        db.query(LeaveRequest).delete()
        
        # Reset all leave balances back to default values
        db.query(LeaveBalance).update({
            LeaveBalance.UsedDays: 0,
            LeaveBalance.PendingDays: 0
        }, synchronize_session=False)
        
        db.commit()
        return {"success": True, "message": "Database reset successfully."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database reset failed: {str(e)}")
