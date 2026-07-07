from datetime import datetime
from database.models import Notification

class NotificationAgent:
    """
    Notification Agent
    Responsibility: Create notification records in the database directly.
    """
    def execute(
        self,
        employee_id,
        leave_request_id,
        subject,
        message,
        db
    ):
        notification = Notification(
            EmployeeId=employee_id,
            LeaveRequestId=leave_request_id,
            NotificationType="Email",
            Subject=subject,
            Message=message,
            Status="Pending",
            SentAt=datetime.now()
        )
        db.add(notification)
        db.commit()

        return {
            "success": True,
            "notification_id": notification.NotificationId
        }
