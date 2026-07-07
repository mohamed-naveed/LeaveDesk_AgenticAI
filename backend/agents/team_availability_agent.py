from database.models import Employee, LeaveRequest

class TeamAvailabilityAgent:
    """
    Team Availability Agent
    Responsibility: Check team absence threshold per department and date range.
    """
    def execute(
        self,
        department_id,
        start_date,
        end_date,
        threshold_percent,
        db
    ):
        total_employees = (
            db.query(Employee)
            .filter(
                Employee.DepartmentId == department_id,
                Employee.IsActive == True
            )
            .count()
        )

        leave_count = (
            db.query(LeaveRequest.EmployeeId)
            .join(Employee, LeaveRequest.EmployeeId == Employee.EmployeeId)
            .filter(
                Employee.DepartmentId == department_id,
                LeaveRequest.Status.in_(["Approved", "Pending Manager Approval"]),
                LeaveRequest.StartDate <= end_date,
                LeaveRequest.EndDate >= start_date
            )
            .distinct()
            .count()
        )

        if total_employees == 0:
            return {
                "success": False,
                "message": "No active employees"
            }

        absence_percent = (leave_count / total_employees) * 100

        return {
            "success": True,
            "total_employees": total_employees,
            "employees_on_leave": leave_count,
            "absence_percent": round(absence_percent, 2),
            "threshold_exceeded": absence_percent > threshold_percent
        }
