from database.models import LeavePolicy

class LeavePolicyAgent:
    """
    Leave Policy Agent
    Responsibility: Get active leave policies.
    """
    def execute(
        self,
        leave_type_id,
        db
    ):
        policy = (
            db.query(LeavePolicy)
            .filter(
                LeavePolicy.LeaveTypeId == leave_type_id,
                LeavePolicy.IsActive == True
            )
            .first()
        )

        if not policy:
            return {
                "success": False,
                "message": "Policy Not Found"
            }

        return {
            "success": True,
            "min_notice_days": policy.MinNoticeDays,
            "auto_approval_max_days": float(policy.AutoApprovalMaxDays) if policy.AutoApprovalMaxDays is not None else None,
            "auto_approval_max_requests_per_month": policy.AutoApprovalMaxRequestsPerMonth if policy.AutoApprovalMaxRequestsPerMonth is not None else 1,
            "allow_half_day": policy.AllowHalfDay,
            "team_threshold": float(policy.TeamLeaveThresholdPercent) if policy.TeamLeaveThresholdPercent is not None else None,
            "medical_certificate_after_days": float(policy.MedicalCertificateAfterDays) if policy.MedicalCertificateAfterDays is not None else None
        }
