class LeaveDecisionAgent:
    """
    Leave Decision Agent
    Responsibility: Executes deterministic business logic rules to approve, reject,
    or route leave requests to manager approval.
    """
    def execute(self, data):
        # 1. Hard Rejections
        if not data.get("employee_active"):
            return {
                "decision": "Rejected",
                "status": "Rejected",
                "reason": "Employee is inactive"
            }

        if data.get("overlap_found"):
            return {
                "decision": "Rejected",
                "status": "Rejected",
                "reason": "Overlapping Leave Request"
            }

        if data.get("threshold_exceeded"):
            return {
                "decision": "ManualReview",
                "status": "Pending Manager Approval",
                "reason": "Department leave threshold exceeded."
            }

        # Monthly limit removed — no cap applies; monthly_limit_exceeded is always False

        max_days_per_request = data.get("max_days_per_request")
        if max_days_per_request is not None and data.get("working_days", 0) > max_days_per_request:
            return {
                "decision": "ManualReview",
                "status": "Pending Manager Approval",
                "reason": f"The requested leave exceeds the maximum allowed days per request of {int(max_days_per_request)} for this leave type."
            }

        if data.get("remaining_balance", 0) < data.get("working_days", 0):
            return {
                "decision": "ManualReview",
                "status": "Pending Manager Approval",
                "reason": "Insufficient leave balance (routed for Loss of Pay / Manual Review)."
            }

        # 2. Policy Violations (ManualReview)
        # Check Notice Period
        notice_days = data.get("notice_days", 0)
        min_notice_days = data.get("min_notice_days", 0)
        if notice_days < min_notice_days:
            return {
                "decision": "ManualReview",
                "status": "Pending Manager Approval",
                "reason": f"Notice period of {notice_days} days is less than the required {min_notice_days} days."
            }

        # Check Medical Certificate Requirement
        medical_cert_after = data.get("medical_certificate_after_days")
        if medical_cert_after is not None and data.get("working_days", 0) > medical_cert_after:
            return {
                "decision": "ManualReview",
                "status": "Pending Manager Approval",
                "reason": f"Medical certificate required for Sick Leave exceeding {int(medical_cert_after)} days."
            }

        # Check Half Day Allowance
        if data.get("has_half_day") and not data.get("allow_half_day"):
            return {
                "decision": "ManualReview",
                "status": "Pending Manager Approval",
                "reason": "Half-day leaves are not supported for this leave type."
            }

        # 3. Manager Approval Requirement (Pending)
        # Uses AutoApprovalMaxDays from the database policy table to dynamically determine the auto-approval limit
        working_days = data.get("working_days", 0)
        auto_approval_max = data.get("auto_approval_max_days")
        if auto_approval_max is not None and working_days > auto_approval_max:
            return {
                "decision": "Pending",
                "status": "Pending Manager Approval",
                "reason": f"Leave request for {working_days} day(s) exceeds the Auto Approval Limit of {auto_approval_max} day(s) for this leave type."
            }

        # 4. Monthly Auto-Approval Count Cap
        if data.get("has_previous_approved_in_month"):
            limit = data.get("auto_approval_max_requests_per_month", 1)
            count = data.get("approved_requests_count_in_month", 0)
            return {
                "decision": "ManualReview",
                "status": "Pending Manager Approval",
                "reason": f"Leave request exceeds the monthly auto-approval frequency limit of {limit} request(s) for this leave type (you already have {count} approved request(s) this month)."
            }

        # 5. Auto-Approved (AutoApproved)
        return {
            "decision": "AutoApproved",
            "status": "Approved",
            "reason": "All validation checks passed successfully."
        }
