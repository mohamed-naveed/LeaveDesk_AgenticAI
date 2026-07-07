from pydantic import BaseModel
from typing import Optional

class LeaveApplyRequest(BaseModel):
    employee_id: int
    request_text: str

class LeaveApplyResponse(BaseModel):
    status: str
    reason: Optional[str] = None
    requested_days: int
    remaining_balance: float
