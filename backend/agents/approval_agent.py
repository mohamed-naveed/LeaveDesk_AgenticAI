from database.models import LeaveApproval, LeaveRequest

class ApprovalAgent:
    """
    Approval Agent
    Responsibility: Create manager approval task records and process manager actions directly.
    """
    def execute(
        self,
        leave_request_id,
        manager_id,
        db
    ):
        approval = LeaveApproval(
            LeaveRequestId=leave_request_id,
            ApproverEmployeeId=manager_id,
            Decision="Pending"
        )
        db.add(approval)
        db.commit()
        db.refresh(approval)

        return {
            "success": True,
            "approval_id": approval.LeaveApprovalId,
            "status": approval.Decision
        }

    def process_manager_action(
        self,
        leave_request_id,
        manager_id,
        decision,
        comments,
        db
    ):
        approval = db.query(LeaveApproval).filter(
            LeaveApproval.LeaveRequestId == leave_request_id,
            LeaveApproval.ApproverEmployeeId == manager_id
        ).first()

        if approval:
            approval.Decision = decision
            approval.Comments = comments
            db.commit()

        req = db.query(LeaveRequest).filter(LeaveRequest.LeaveRequestId == leave_request_id).first()
        if req:
            req.Status = decision
            db.commit()

        return {
            "success": True,
            "status": decision
        }
