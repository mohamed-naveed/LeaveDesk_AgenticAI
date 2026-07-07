from pydantic import BaseModel
from typing import Optional

class LoginRequest(BaseModel):
    email: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    employee_id: int
    full_name: str
    email: str
    role: str

class EmployeeMeResponse(BaseModel):
    employee_id: int
    employee_code: str
    full_name: str
    email: str
    department_id: Optional[int] = None
    manager_id: Optional[int] = None
    role: str
