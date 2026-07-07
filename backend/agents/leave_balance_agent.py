from database.models import LeaveBalance

class LeaveBalanceAgent:
    """
    Leave Balance Agent
    Responsibility: Retrieve and adjust leave balances in the leave_balances table.
    """
    def execute(
        self,
        employee_id: int,
        leave_type_id: int,
        db
    ):
        balance = (
            db.query(LeaveBalance)
            .filter(
                LeaveBalance.EmployeeId == employee_id,
                LeaveBalance.LeaveTypeId == leave_type_id
            )
            .first()
        )

        if not balance:
            return {
                "success": False,
                "message": "Balance Not Found"
            }

        return {
            "success": True,
            "allocated_days": float(balance.AllocatedDays),
            "used_days": float(balance.UsedDays),
            "pending_days": float(balance.PendingDays),
            "remaining_days": float(balance.RemainingDays)
        }

    def update_balance(
        self,
        employee_id: int,
        leave_type_id: int,
        requested_days: float,
        action: str,  # 'CreatePending', 'Approve', 'Reject', 'ApproveDirect'
        db
    ):
        used_delta = 0.0
        pending_delta = 0.0

        if action == "CreatePending":
            pending_delta = requested_days
        elif action == "Approve":
            used_delta = requested_days
            pending_delta = -requested_days
        elif action == "Reject":
            pending_delta = -requested_days
        elif action == "ApproveDirect":
            used_delta = requested_days

        balance = (
            db.query(LeaveBalance)
            .filter(
                LeaveBalance.EmployeeId == employee_id,
                LeaveBalance.LeaveTypeId == leave_type_id
            )
            .first()
        )

        if balance:
            balance.UsedDays = float(balance.UsedDays) + used_delta
            balance.PendingDays = float(balance.PendingDays) + pending_delta
            db.commit()
            db.refresh(balance)

        if not balance:
            return {
                "success": False,
                "message": "Leave balance record not found"
            }

        return {
            "success": True,
            "allocated_days": float(balance.AllocatedDays),
            "used_days": float(balance.UsedDays),
            "pending_days": float(balance.PendingDays),
            "remaining_days": float(balance.RemainingDays)
        }
