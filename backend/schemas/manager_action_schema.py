from pydantic import BaseModel

class ManagerActionRequest(BaseModel):
    leave_request_id: int
    manager_id: int
    decision: str  # 'Approved' or 'Rejected'
    comments: str

class ManagerDecisionRequest(BaseModel):
    leave_request_id: int
    manager_id: int
    comments: str
