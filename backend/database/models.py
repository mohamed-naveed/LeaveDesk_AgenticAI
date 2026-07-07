from sqlalchemy import Column, Integer, String, Date, DateTime, Numeric, Boolean, ForeignKey, Text, BigInteger, Computed, func
from database.connection import Base

class Department(Base):
    __tablename__ = "departments"

    DepartmentId = Column(Integer, primary_key=True, autoincrement=True)
    DepartmentName = Column(String(100), nullable=False, unique=True)
    DepartmentHeadId = Column(Integer, nullable=True)
    IsActive = Column(Boolean, nullable=False, default=True)
    CreatedAt = Column(DateTime, nullable=False, server_default=func.now())

class Employee(Base):
    __tablename__ = "employees"

    EmployeeId = Column(Integer, primary_key=True, autoincrement=True)
    EmployeeCode = Column(String(30), nullable=False, unique=True)
    FullName = Column(String(150), nullable=False)
    Email = Column(String(150), nullable=False, unique=True)
    DepartmentId = Column(Integer, ForeignKey("departments.DepartmentId"), nullable=True)
    ManagerId = Column(Integer, ForeignKey("employees.EmployeeId"), nullable=True)
    JoiningDate = Column(Date, nullable=True)
    PasswordHash = Column(String(255), nullable=True)
    Role = Column(String(20), nullable=False, default="employee")
    IsActive = Column(Boolean, nullable=False, default=True)
    CreatedAt = Column(DateTime, nullable=False, server_default=func.now())
    UpdatedAt = Column(DateTime, nullable=True)

class LeaveType(Base):
    __tablename__ = "leave_types"

    LeaveTypeId = Column(Integer, primary_key=True, autoincrement=True)
    LeaveTypeCode = Column(String(20), nullable=False, unique=True)
    LeaveTypeName = Column(String(100), nullable=False)
    AnnualLimit = Column(Numeric(5, 2), nullable=False, default=0)
    MaxDaysPerRequest = Column(Numeric(5, 2), nullable=True)
    RequiresApproval = Column(Boolean, nullable=False, default=True)
    IsPaid = Column(Boolean, nullable=False, default=True)
    IsActive = Column(Boolean, nullable=False, default=True)
    CreatedAt = Column(DateTime, nullable=False, server_default=func.now())

class LeavePolicy(Base):
    __tablename__ = "leave_policies"

    LeavePolicyId = Column(Integer, primary_key=True, autoincrement=True)
    LeaveTypeId = Column(Integer, ForeignKey("leave_types.LeaveTypeId"), nullable=False)
    MinNoticeDays = Column(Integer, nullable=False, default=0)
    MedicalCertificateAfterDays = Column(Numeric(5, 2), nullable=True)
    AllowHalfDay = Column(Boolean, nullable=False, default=False)
    TeamLeaveThresholdPercent = Column(Numeric(5, 2), nullable=True)
    AutoApprovalMaxDays = Column(Numeric(5, 2), nullable=True)
    EffectiveFrom = Column(Date, nullable=False)
    EffectiveTo = Column(Date, nullable=True)
    IsActive = Column(Boolean, nullable=False, default=True)
    CreatedAt = Column(DateTime, nullable=False, server_default=func.now())

class LeaveBalance(Base):
    __tablename__ = "leave_balances"

    LeaveBalanceId = Column(Integer, primary_key=True, autoincrement=True)
    EmployeeId = Column(Integer, ForeignKey("employees.EmployeeId"), nullable=False)
    LeaveTypeId = Column(Integer, ForeignKey("leave_types.LeaveTypeId"), nullable=False)
    LeaveYear = Column(Integer, nullable=False)
    AllocatedDays = Column(Numeric(5, 2), nullable=False, default=0)
    UsedDays = Column(Numeric(5, 2), nullable=False, default=0)
    PendingDays = Column(Numeric(5, 2), nullable=False, default=0)
    RemainingDays = Column(Numeric(5, 2), Computed("AllocatedDays - UsedDays - PendingDays"))
    UpdatedAt = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

class Holiday(Base):
    __tablename__ = "holidays"

    HolidayId = Column(Integer, primary_key=True, autoincrement=True)
    HolidayDate = Column(Date, nullable=False)
    HolidayName = Column(String(200), nullable=False)
    Location = Column(String(100), nullable=True)
    IsOptional = Column(Boolean, nullable=False, default=False)
    CreatedAt = Column(DateTime, nullable=False, server_default=func.now())

class LeaveRequest(Base):
    __tablename__ = "leave_requests"

    LeaveRequestId = Column(Integer, primary_key=True, autoincrement=True)
    EmployeeId = Column(Integer, ForeignKey("employees.EmployeeId"), nullable=False)
    LeaveTypeId = Column(Integer, ForeignKey("leave_types.LeaveTypeId"), nullable=False)
    StartDate = Column(Date, nullable=False)
    EndDate = Column(Date, nullable=False)
    RequestedDays = Column(Numeric(5, 2), nullable=False)
    Reason = Column(String(1000), nullable=True)
    Status = Column(String(30), nullable=False, default="Pending")
    DecisionSource = Column(String(30), nullable=True)
    ManagerId = Column(Integer, ForeignKey("employees.EmployeeId"), nullable=True)
    AgentDecision = Column(String(50), nullable=True)
    AgentReason = Column(Text, nullable=True)
    CreatedAt = Column(DateTime, nullable=False, server_default=func.now())
    UpdatedAt = Column(DateTime, nullable=True)

class LeaveRequestDay(Base):
    __tablename__ = "leave_request_days"

    LeaveRequestDayId = Column(Integer, primary_key=True, autoincrement=True)
    LeaveRequestId = Column(Integer, ForeignKey("leave_requests.LeaveRequestId"), nullable=False)
    LeaveDate = Column(Date, nullable=False)
    DayType = Column(String(20), nullable=False, default="FullDay")
    LeaveDays = Column(Numeric(3, 1), nullable=False, default=1.0)
    IsHoliday = Column(Boolean, nullable=False, default=False)
    IsWeekend = Column(Boolean, nullable=False, default=False)

class LeaveApproval(Base):
    __tablename__ = "leave_approvals"

    LeaveApprovalId = Column(Integer, primary_key=True, autoincrement=True)
    LeaveRequestId = Column(Integer, ForeignKey("leave_requests.LeaveRequestId"), nullable=False)
    ApproverEmployeeId = Column(Integer, ForeignKey("employees.EmployeeId"), nullable=False)
    ApprovalLevel = Column(Integer, nullable=False, default=1)
    Decision = Column(String(30), nullable=False, default="Pending")
    Comments = Column(String(1000), nullable=True)
    ActionAt = Column(DateTime, nullable=True)
    CreatedAt = Column(DateTime, nullable=False, server_default=func.now())

class AgentExecutionLog(Base):
    __tablename__ = "agent_execution_logs"

    AgentExecutionLogId = Column(BigInteger, primary_key=True, autoincrement=True)
    LeaveRequestId = Column(Integer, ForeignKey("leave_requests.LeaveRequestId"), nullable=True)
    AgentName = Column(String(100), nullable=False)
    InputData = Column(Text, nullable=True)
    OutputData = Column(Text, nullable=True)
    ExecutionStatus = Column(String(30), nullable=False)
    ErrorMessage = Column(Text, nullable=True)
    StartedAt = Column(DateTime, nullable=False, server_default=func.now())
    CompletedAt = Column(DateTime, nullable=True)

class Notification(Base):
    __tablename__ = "notifications"

    NotificationId = Column(Integer, primary_key=True, autoincrement=True)
    EmployeeId = Column(Integer, ForeignKey("employees.EmployeeId"), nullable=False)
    LeaveRequestId = Column(Integer, ForeignKey("leave_requests.LeaveRequestId"), nullable=True)
    NotificationType = Column(String(30), nullable=False)
    Subject = Column(String(300), nullable=False)
    Message = Column(Text, nullable=False)
    Status = Column(String(30), nullable=False, default="Pending")
    SentAt = Column(DateTime, nullable=True)
    CreatedAt = Column(DateTime, nullable=False, server_default=func.now())
