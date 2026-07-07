from database.models import LeaveRequest

class LeaveOverlapAgent:
    """
    Leave Overlap Agent
    Responsibility: Check for overlapping approved/pending requests.
    """
    def execute(
        self,
        employee_id,
        start_date,
        end_date,
        db
    ):
        overlaps = (
            db.query(LeaveRequest)
            .filter(
                LeaveRequest.EmployeeId == employee_id,
                LeaveRequest.Status.in_(["Approved", "Pending Manager Approval"]),
                LeaveRequest.StartDate <= end_date,
                LeaveRequest.EndDate >= start_date
            )
            .all()
        )

        if overlaps:
            return {
                "success": True,
                "overlap_found": True,
                "count": len(overlaps),
                "message": "Overlapping leave exists"
            }

        return {
            "success": True,
            "overlap_found": False,
            "count": 0
        }