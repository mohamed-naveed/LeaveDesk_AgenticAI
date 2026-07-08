from openai import OpenAI
import json
import re
from datetime import date, datetime, timedelta

class LLMService:
    """
    LLM Service
    Responsibility: Parse natural language leave requests into structured JSON parameters.
    Uses OpenAI's tool calling feature to extract structured parameters.
    """
    def __init__(self, api_key: str):
        self.api_key = api_key
        import os
        base_url = os.getenv("OPENAI_BASE_URL")
        self.model_name = os.getenv("OPENAI_MODEL_NAME", "google/gemini-2.5-flash")
        # Avoid crash if key is empty/mock
        if base_url:
            self.client = OpenAI(api_key=api_key or "mock-key", base_url=base_url)
        else:
            self.client = OpenAI(api_key=api_key or "mock-key")

    def process_chat(self, text: str, context_str: str) -> dict:
        """
        Classifies user intent and returns either a direct answer or extracted leave details.
        """
        current_date = date.today().strftime("%Y-%m-%d")
        
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "apply_leave",
                    "description": "Trigger this function ONLY when the user explicitly wants to apply for or request a leave of absence.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "leave_type": {
                                "type": "string",
                                "description": "Type of leave (e.g. Casual Leave, Sick Leave, Annual Leave)."
                            },
                            "start_date": {
                                "type": "string",
                                "description": "Start date in YYYY-MM-DD format."
                            },
                            "end_date": {
                                "type": "string",
                                "description": "End date in YYYY-MM-DD format."
                            },
                            "reason": {
                                "type": "string",
                                "description": "Reason for the leave."
                            }
                        },
                        "required": ["leave_type", "start_date", "end_date", "reason"]
                    }
                }
            }
        ]

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system", 
                        "content": (
                            f"You are a helpful LeaveDesk AI assistant. Today's date is: {current_date}.\n"
                            f"You MUST use today's date to resolve relative dates like 'tomorrow', 'next week', 'in 5 days', etc. into YYYY-MM-DD format.\n"
                            f"If the user wants to apply for a leave (or has provided leave details), you MUST use the `apply_leave` tool to parse the parameters.\n"
                            f"If the user asks a question, answer it conversationally based on the context provided.\n\n"
                            f"Context:\n{context_str}"
                        )
                    },
                    {"role": "user", "content": text}
                ],
                tools=tools,
                tool_choice="auto",
                max_tokens=50
            )

            msg = response.choices[0].message
            if msg.tool_calls:
                arguments = json.loads(msg.tool_calls[0].function.arguments)
                return {
                    "intent": "apply_leave",
                    "leave_details": arguments
                }
            else:
                return {
                    "intent": "general_inquiry",
                    "chat_response": msg.content
                }
                
        except Exception as e:
            print(f"LLM Error: {e}. Trying lightweight RAG LLM call.")
            rag_response = self._rag_llm_call(text, context_str)
            if rag_response:
                return {
                    "intent": "general_inquiry",
                    "chat_response": rag_response
                }
            print("RAG LLM call also failed. Falling back to _fallback_process_chat.")
            return self._fallback_process_chat(text, context_str)

    def _rag_llm_call(self, text: str, context_str: str) -> str:
        try:
            # A very minimal LLM query (no tools, max_tokens=35) to stay within tiny credit limits
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are LeaveDesk AI. Answer the user's question using the context. Keep it extremely brief (under 1 sentence).\n\n"
                            f"Context:\n{context_str}"
                        )
                    },
                    {"role": "user", "content": text}
                ],
                max_tokens=35
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"RAG LLM call failed: {e}")
            return None

    def _fallback_process_chat(self, text: str, context_str: str) -> dict:
        text_lower = text.lower()
        
        is_manager = "employee role: manager" in context_str.lower()
        if is_manager:
            def extract_section(context: str, start_header: str, end_headers: list) -> str:
                lines = context.split("\n")
                capture = False
                captured_lines = []
                for line in lines:
                    if line.strip().lower() == start_header.lower() or line.strip().lower().startswith(start_header.lower()):
                        capture = True
                        captured_lines.append(line)
                        continue
                    if capture:
                        if any(line.strip().lower().startswith(eh.lower()) for eh in end_headers):
                            break
                        captured_lines.append(line)
                return "\n".join(captured_lines).strip()

            # Extract managed employees list from context
            employees = []
            me_section = extract_section(context_str, "Managed Employees:", ["Managed Employees Leave Balances:"])
            for line in me_section.split("\n"):
                if line.startswith("- "):
                    match = re.search(r"-\s+(.*?)\s+\(ID:\s*(\d+)", line)
                    if match:
                        name = match.group(1).strip()
                        eid = match.group(2).strip()
                        employees.append({"id": eid, "name": name, "name_lower": name.lower()})

            specific_employee = None
            for emp_info in employees:
                if emp_info["name_lower"] in text_lower or emp_info["id"] in text_lower:
                    specific_employee = emp_info
                    break

            is_employee_list_query = any(w in text_lower for w in ["who are my employees", "who all are", "list of employees", "list employees", "my employees", "number of employees", "no of employees", "my team", "team members", "who is in my team", "all the employees", "all employees", "show employees", "show the employees"])
            if is_employee_list_query:
                me_section = extract_section(context_str, "Managed Employees:", ["Managed Employees Leave Balances:", "Managed Employees Leave History:", "Upcoming Company Holidays:"])
                return {
                    "intent": "general_inquiry",
                    "chat_response": f"Here is the list of your managed employees:\n{me_section}"
                }

            # Check if query is about a specific employee's id/email/profile info
            is_info_query = any(w in text_lower for w in ["id", "code", "email", "profile", "details"])
            if specific_employee and is_info_query:
                me_section = extract_section(context_str, "Managed Employees:", ["Managed Employees Leave Balances:"])
                matching_line = None
                for line in me_section.split("\n"):
                    if f"ID: {specific_employee['id']}" in line or specific_employee["name"] in line:
                        matching_line = line
                        break
                if matching_line:
                    return {
                        "intent": "general_inquiry",
                        "chat_response": f"Here are the details for {specific_employee['name']}:\n{matching_line.strip('- ')}"
                    }

            is_balance_query = any(w in text_lower for w in ["balance", "balances", "how much"])
            is_personal = "my" in text_lower or "do i" in text_lower or "i have" in text_lower or "for me" in text_lower or "my own" in text_lower
            if is_balance_query and not is_personal:
                bal_section = extract_section(context_str, "Managed Employees Leave Balances:", ["Managed Employees Leave History:", "Upcoming Company Holidays:"])
                if specific_employee:
                    matching_line = None
                    for line in bal_section.split("\n"):
                        if f"(ID: {specific_employee['id']})" in line or specific_employee["name"] in line:
                            matching_line = line
                            break
                    if matching_line:
                        return {
                            "intent": "general_inquiry",
                            "chat_response": f"Here is the leave balance for {specific_employee['name']}:\n{matching_line}"
                        }
                    else:
                        return {
                            "intent": "general_inquiry",
                            "chat_response": f"I couldn't find leave balances for employee {specific_employee['name']}."
                        }
                else:
                    return {
                        "intent": "general_inquiry",
                        "chat_response": f"Here are the leave balances for all your managed employees:\n{bal_section}"
                    }

            is_history_query = any(w in text_lower for w in ["history", "past", "last", "previous", "applied", "request", "requests"])
            if is_history_query and not is_personal:
                hist_section = extract_section(context_str, "Managed Employees Leave History:", ["Upcoming Company Holidays:"])
                if specific_employee:
                    captured_block = []
                    capture = False
                    for line in hist_section.split("\n"):
                        if line.startswith("- ") and (f"(ID: {specific_employee['id']})" in line or specific_employee["name"] in line):
                            capture = True
                            captured_block.append(line)
                            continue
                        if capture:
                            if line.startswith("- ") or "No past leave" in line:
                                break
                            captured_block.append(line)
                    if captured_block:
                        return {
                            "intent": "general_inquiry",
                            "chat_response": f"Here is the leave history for {specific_employee['name']}:\n" + "\n".join(captured_block)
                        }
                    else:
                        return {
                            "intent": "general_inquiry",
                            "chat_response": f"I couldn't find any past leave history for employee {specific_employee['name']}."
                        }
                else:
                    return {
                        "intent": "general_inquiry",
                        "chat_response": f"Here is the leave history for your managed employees:\n{hist_section}"
                    }

        # RAG-style query fallbacks for employees and managers
        if "manager" in text_lower and not is_manager:
            for line in context_str.split("\n"):
                if line.strip().lower().startswith("- manager:"):
                    manager_name = line.split(":", 1)[1].strip()
                    return {
                        "intent": "general_inquiry",
                        "chat_response": f"Your manager is {manager_name}."
                    }
            return {
                "intent": "general_inquiry",
                "chat_response": "I couldn't find your manager in your employee profile."
            }

        if any(w in text_lower for w in ["employee code", "my code", "employee_code", "employee id", "my id", "employee_id"]):
            for line in context_str.split("\n"):
                if line.strip().lower().startswith("- employee code:"):
                    code = line.split(":", 1)[1].strip()
                    return {
                        "intent": "general_inquiry",
                        "chat_response": f"Your employee code/ID is {code}."
                    }
            return {
                "intent": "general_inquiry",
                "chat_response": "I couldn't find your employee code in your employee profile."
            }

        if any(w in text_lower for w in ["join", "joining"]):
            for line in context_str.split("\n"):
                if line.strip().lower().startswith("- joining date:"):
                    jdate = line.split(":", 1)[1].strip()
                    return {
                        "intent": "general_inquiry",
                        "chat_response": f"You joined the company on {jdate}."
                    }
            return {
                "intent": "general_inquiry",
                "chat_response": "I couldn't find your joining date in your employee profile."
            }

        if any(w in text_lower for w in ["status of", "my leave requests", "my requests", "applied leaves"]):
            history_lines = []
            capture = False
            for line in context_str.split("\n"):
                if "Employee Recent Leave History:" in line or "Your Pending Requests:" in line:
                    capture = True
                    history_lines.append(line)
                    continue
                if capture:
                    if line.strip() == "" or "Company Leave Policy:" in line or "Upcoming Company Holidays:" in line:
                        break
                    history_lines.append(line)
            if history_lines:
                return {
                    "intent": "general_inquiry",
                    "chat_response": "Here is the status of your recent leave requests:\n" + "\n".join(history_lines)
                }
            return {
                "intent": "general_inquiry",
                "chat_response": "No past or pending leave requests found."
            }

        if "last approved" in text_lower:
            for line in context_str.split("\n"):
                if "status: approved" in line.lower() and "recent leave history" not in line.lower():
                    return {
                        "intent": "general_inquiry",
                        "chat_response": f"Your last approved leave was: {line.strip('- ')}"
                    }
            return {
                "intent": "general_inquiry",
                "chat_response": "You don't have any approved leave requests in your recent history."
            }

        if "holiday" in text_lower or "holidays" in text_lower:
            holiday_lines = []
            capture = False
            for line in context_str.split("\n"):
                if "Upcoming Company Holidays:" in line:
                    capture = True
                    holiday_lines.append(line)
                    continue
                if capture:
                    if line.strip() == "" or "Company Leave Policy:" in line or "Employee Balances:" in line:
                        break
                    holiday_lines.append(line)
            if holiday_lines:
                return {
                    "intent": "general_inquiry",
                    "chat_response": "Here are the upcoming company holidays:\n" + "\n".join(holiday_lines)
                }
            return {
                "intent": "general_inquiry",
                "chat_response": "No upcoming company holidays found."
            }

        if "email" in text_lower:
            for line in context_str.split("\n"):
                if line.strip().lower().startswith("- email:"):
                    email = line.split(":", 1)[1].strip()
                    return {
                        "intent": "general_inquiry",
                        "chat_response": f"Your email ID is {email}."
                    }
            return {
                "intent": "general_inquiry",
                "chat_response": "I couldn't find your email details in your profile."
            }

        if "department" in text_lower:
            for line in context_str.split("\n"):
                if line.strip().lower().startswith("- department:"):
                    dept_name = line.split(":", 1)[1].strip()
                    return {
                        "intent": "general_inquiry",
                        "chat_response": f"You are in the {dept_name} department."
                    }
            return {
                "intent": "general_inquiry",
                "chat_response": "I couldn't find your department details in your profile."
            }
        
        # Check if the user is attempting to apply for a leave
        has_question_kw = any(w in text_lower for w in ["history", "past", "last", "previous", "holiday", "holidays", "policy", "policies", "olicies", "rule", "rules", "balance", "balances", "how much", "remaining", "pending", "approval", "limit", "limits", "manager", "code", "join", "joining", "status", "request", "requests", "show", "list", "who", "when", "what", "where", "email", "department"])
        is_applying = (
            any(w in text_lower for w in ["apply", "appply", "aply", "applying", "request", "want", "need", "take", "book", "tomorrow", "starting", "in ", "day", "leave"]) 
            or any(lt in text_lower for lt in ["casual", "sick", "annual", "unpaid"])
        ) and not has_question_kw
        
        if is_applying:
            current_date = date.today().isoformat()
            for line in context_str.split("\n"):
                if "current date is" in line.lower() or "today's date is" in line.lower():
                    match = re.search(r"\d{4}-\d{2}-\d{2}", line)
                    if match:
                        current_date = match.group(0)
                        break
            
            details = self._fallback_parse(text, current_date)
            return {
                "intent": "apply_leave",
                "leave_details": details
            }
            
        # Check if the user is asking about teammate/team leaves (unauthorized for regular employees)
        is_team_query = any(w in text_lower for w in ["team", "teammate", "teammates", "colleague", "colleagues", "others", "other"])
        is_employee = "employee role: employee" in context_str.lower()
        
        if is_team_query and is_employee:
            return {
                "intent": "general_inquiry",
                "chat_response": "You are not authorized to view teammate leaves. Employees can only view their own leave balances and past leaves."
            }
            
        # 1. Pending Approvals/Requests query
        if "pending" in text_lower or "approval" in text_lower:
            pending_lines = []
            capture = False
            for line in context_str.split("\n"):
                if "Pending Requests to Approve" in line or "Your Pending Requests" in line:
                    capture = True
                    pending_lines.append(line)
                    continue
                if capture:
                    if line.strip() == "" or "Employee Recent Leave History" in line or "Company Leave Policy" in line:
                        break
                    pending_lines.append(line)
            
            if pending_lines and not any("No pending requests" in l for l in pending_lines):
                pending_text = "\n".join(pending_lines)
                return {
                    "intent": "general_inquiry",
                    "chat_response": f"Here are the active pending requests retrieved from the database:\n{pending_text}"
                }
            else:
                return {
                    "intent": "general_inquiry",
                    "chat_response": "I checked the database. There are currently no pending leave requests awaiting approval."
                }
                
        # 3. Policy & Balance query
        if any(w in text_lower for w in ["policy", "policies", "rule", "rules", "balance", "balances", "how much", "do i have", "limit", "limits", "remaining"]) and "history" not in text_lower:
            balance_lines = []
            policy_lines = []
            current_section = None
            for line in context_str.split("\n"):
                if "Employee Balances:" in line:
                    current_section = "balances"
                    continue
                elif "Company Leave Policy:" in line:
                    current_section = "policy"
                    continue
                elif "Employee Recent Leave History:" in line or "Pending Requests to Approve" in line:
                    current_section = None
                
                if current_section == "balances" and line.startswith("-"):
                    balance_lines.append(line)
                elif current_section == "policy" and line.startswith("-"):
                    policy_lines.append(line)
            
            show_balances = any(w in text_lower for w in ["balance", "balances", "how much", "remaining"])
            show_policies = any(w in text_lower for w in ["policy", "policies", "rule", "rules", "limit", "limits"])
            
            if not show_balances and not show_policies:
                show_balances = True
                show_policies = True
                
            response_msg = "Here is the dynamic data retrieved from the database:\n\n"
            if show_balances and balance_lines:
                response_msg += "**Your Leave Balances:**\n" + "\n".join(balance_lines) + "\n\n"
            if show_policies and policy_lines:
                response_msg += "**Leave Policies:**\n" + "\n".join(policy_lines)
            
            return {
                "intent": "general_inquiry",
                "chat_response": response_msg.strip()
            }
            
        # 2. Leave History query (Personal or Teammates)
        if any(w in text_lower for w in ["history", "last leave", "past leave", "applied", "previous", "leaves", "leave", "request", "requests"]):
            is_team_query = any(w in text_lower for w in ["team", "teammate", "teammates", "colleague", "colleagues", "others", "other"])
            
            history_lines = []
            capture = False
            
            section_header = "Team/Teammates Recent Leave History:" if is_team_query else "Employee Recent Leave History:"
            
            for line in context_str.split("\n"):
                if section_header in line:
                    capture = True
                    history_lines.append(line)
                    continue
                if capture:
                    if line.strip() == "" or "Pending Requests" in line or "Company Leave Policy" in line or "Employee Balances" in line or "Upcoming Company Holidays" in line:
                        break
                    history_lines.append(line)
            
            if history_lines and not any("No teammates leave requests" in l or "No past leave requests" in l for l in history_lines):
                history_text = "\n".join(history_lines)
                subject_type = "team's leave history" if is_team_query else "leave history"
                return {
                    "intent": "general_inquiry",
                    "chat_response": f"Here is the {subject_type} retrieved from the database:\n{history_text}"
                }
            else:
                subject_type = "teammate leave records" if is_team_query else "recent leave requests"
                return {
                    "intent": "general_inquiry",
                    "chat_response": f"I couldn't find any {subject_type} in the database history."
                }
            
        # 4. Excluded weekends / overlaps
        if "overlap" in text_lower or "conflict" in text_lower:
            return {
                "intent": "general_inquiry",
                "chat_response": "For calendar conflicts or overlap reports, please refer to the team dashboard or history."
            }

        # 5. Holiday query
        if "holiday" in text_lower or "holidays" in text_lower:
            holiday_lines = []
            capture = False
            for line in context_str.split("\n"):
                if "Upcoming Company Holidays:" in line:
                    capture = True
                    holiday_lines.append(line)
                    continue
                if capture:
                    if line.strip() == "" or "Company Leave Policy" in line or "Employee Balances" in line:
                        break
                    holiday_lines.append(line)
            
            if holiday_lines and not any("No upcoming holidays" in l for l in holiday_lines):
                holiday_text = "\n".join(holiday_lines)
                return {
                    "intent": "general_inquiry",
                    "chat_response": f"Here are the upcoming company holidays retrieved from the database:\n{holiday_text}"
                }
            else:
                return {
                    "intent": "general_inquiry",
                    "chat_response": "I checked the database. There are currently no upcoming company holidays found."
                }
            
        # 6. Block creation/storage when LLM is down (prevent default apply_leave)
        return {
            "intent": "general_inquiry",
            "chat_response": (
                "The AI Chat service is temporarily offline (401 Unauthorized). "
                "Applying for leaves via chat is disabled at the moment, and no new requests will be stored in the database. "
                "However, you can still query your current balances, history, or policies by typing 'balance' or 'history'."
            )
        }

    def _fallback_parse(self, text: str, current_date: str) -> dict:
        """
        Regex-based parsing rules for standard phrases to ensure testing works with mock keys.
        """
        res = {
            "leave_type": "Casual Leave",
            "start_date": "",
            "end_date": "",
            "reason": "Personal reason"
        }
        
        lower_text = text.lower()
        
        # Match leave type
        if "sick" in lower_text:
            res["leave_type"] = "Sick Leave"
        elif "annual" in lower_text:
            res["leave_type"] = "Annual Leave"
        elif "unpaid" in lower_text:
            res["leave_type"] = "Unpaid Leave"
        else:
            res["leave_type"] = "Casual Leave"

        # Match reason
        for delimiter in ["for ", "due to ", "because of "]:
            if delimiter in lower_text:
                parts = text.split(delimiter)
                if len(parts) > 1:
                    res["reason"] = parts[-1].strip().capitalize()
                    break

        # Match dates
        months = {
            "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
            "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12
        }
        
        dates_found = re.findall(r"\d{4}-\d{2}-\d{2}", text)
        if len(dates_found) >= 2:
            res["start_date"] = dates_found[0]
            res["end_date"] = dates_found[1]
        elif len(dates_found) == 1:
            res["start_date"] = dates_found[0]
            res["end_date"] = dates_found[0]
        else:
            # Handle text dates like "july 10 to july 15" or "july 10 to 15"
            pattern = r"(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec)\s+(\d{1,2})"
            matches = re.findall(pattern, lower_text)
            y = datetime.strptime(current_date, "%Y-%m-%d").year
            if len(matches) >= 2:
                m1, d1 = matches[0]
                m2, d2 = matches[1]
                res["start_date"] = f"{y}-{months[m1]:02d}-{int(d1):02d}"
                res["end_date"] = f"{y}-{months[m2]:02d}-{int(d2):02d}"
            elif len(matches) == 1:
                m1, d1 = matches[0]
                # Check for "july 10 to 15" style
                to_match = re.search(rf"{m1}\s+{d1}\s+(?:to|through|until|-)\s+(\d{1,2})", lower_text)
                if to_match:
                    d2 = to_match.group(1)
                    res["start_date"] = f"{y}-{months[m1]:02d}-{int(d1):02d}"
                    res["end_date"] = f"{y}-{months[m1]:02d}-{int(d2):02d}"
                else:
                    res["start_date"] = f"{y}-{months[m1]:02d}-{int(d1):02d}"
                    res["end_date"] = f"{y}-{months[m1]:02d}-{int(d1):02d}"
            elif "tomorrow" in lower_text:
                today_dt = datetime.strptime(current_date, "%Y-%m-%d")
                tomorrow_dt = today_dt + timedelta(days=1)
                res["start_date"] = tomorrow_dt.strftime("%Y-%m-%d")
                
                duration_match = re.search(r"for\s+(\d+)\s+days?", lower_text)
                if duration_match:
                    duration = int(duration_match.group(1))
                    end_dt = tomorrow_dt + timedelta(days=duration - 1)
                    res["end_date"] = end_dt.strftime("%Y-%m-%d")
                else:
                    res["end_date"] = tomorrow_dt.strftime("%Y-%m-%d")
                res["reason"] = "Sick"
            elif "in " in lower_text:
                in_days_match = re.search(r"(?:starting\s+)?in\s+(\d+)\s+days?", lower_text)
                if in_days_match:
                    days_offset = int(in_days_match.group(1))
                    today_dt = datetime.strptime(current_date, "%Y-%m-%d")
                    start_dt = today_dt + timedelta(days=days_offset)
                    res["start_date"] = start_dt.strftime("%Y-%m-%d")
                    
                    duration_match = re.search(r"for\s+(\d+)\s+days?", lower_text)
                    if duration_match:
                        duration = int(duration_match.group(1))
                        end_dt = start_dt + timedelta(days=duration - 1)
                        res["end_date"] = end_dt.strftime("%Y-%m-%d")
                    else:
                        res["end_date"] = start_dt.strftime("%Y-%m-%d")
                else:
                    res["start_date"] = current_date
                    res["end_date"] = current_date
            else:
                # Default fallback
                res["start_date"] = current_date
                res["end_date"] = current_date

        return res

    def extract_leave_details(self, text: str, current_date: str = None) -> dict:
        if not current_date:
            current_date = date.today().isoformat()

        # Check for mock key first
        if not self.api_key or self.api_key.startswith("mock"):
            return self._fallback_parse(text, current_date)

        try:
            # Define tool function specification
            tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "apply_leave",
                        "description": "Record a structured leave request extracted from natural language input.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "leave_type": {
                                    "type": "string",
                                    "enum": ["Casual Leave", "Sick Leave", "Annual Leave", "Unpaid Leave"],
                                    "description": "Category/type of leave request."
                                },
                                "start_date": {
                                    "type": "string",
                                    "description": "Start date in YYYY-MM-DD format."
                                },
                                "end_date": {
                                    "type": "string",
                                    "description": "End date in YYYY-MM-DD format. If single day request, matches start_date."
                                },
                                "reason": {
                                    "type": "string",
                                    "description": "Extracted reason or explanation."
                                }
                            },
                            "required": ["leave_type", "start_date", "end_date", "reason"]
                        }
                    }
                }
            ]

            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": f"You are a corporate leave parsing assistant. Today's date is: {current_date}."},
                    {"role": "user", "content": text}
                ],
                tools=tools,
                tool_choice={"type": "function", "function": {"name": "apply_leave"}},
                max_tokens=100
            )

            tool_calls = response.choices[0].message.tool_calls
            if tool_calls:
                arguments = json.loads(tool_calls[0].function.arguments)
                return arguments
            
            raise ValueError("LLM failed to call the apply_leave function.")
        except Exception as e:
            raise e
