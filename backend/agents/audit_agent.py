import json
from datetime import date, datetime
from database.models import AgentExecutionLog

class DateEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        return super().default(obj)

class AuditAgent:
    """
    Audit Agent
    Responsibility: Log trace actions and execution metrics of other agents directly to the database.
    """
    def execute(
        self,
        agent_name,
        input_data,
        output_data,
        status,
        db,
        leave_request_id=None,
        error_message=None,
        started_at=None,
        completed_at=None
    ):
        log = AgentExecutionLog(
            AgentName=agent_name,
            InputData=json.dumps(input_data, cls=DateEncoder),
            OutputData=json.dumps(output_data, cls=DateEncoder),
            ExecutionStatus=status,
            LeaveRequestId=leave_request_id,
            ErrorMessage=error_message,
            StartedAt=started_at,
            CompletedAt=completed_at
        )
        db.add(log)
        db.commit()

        return {
            "success": True
        }
