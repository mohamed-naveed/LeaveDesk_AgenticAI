from database.models import Employee

class EmployeeProfileAgent:
    """
    Employee Profile Agent
    Responsibility: Get employee profile and active status.
    """
    def execute(
        self,
        employee_id,
        db
    ):
        employee = (
            db.query(Employee)
            .filter(Employee.EmployeeId == employee_id)
            .first()
        )

        if not employee:
            return {
                "success": False,
                "message": "Employee Not Found"
            }

        return {
            "success": True,
            "employee_id": employee.EmployeeId,
            "manager_id": employee.ManagerId,
            "department_id": employee.DepartmentId,
            "is_active": employee.IsActive
        }
