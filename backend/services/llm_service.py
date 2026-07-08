from openai import OpenAI
import json
from datetime import date


class LLMService:
    """
    LLM Service — multi-provider chain, NO hardcoded Python fallback.
    If all LLM providers fail the user gets a clear error message.
    """

    def __init__(self, api_key: str):
        import os
        self.api_key = api_key
        self.providers = []

        # Primary provider
        primary_key = api_key or os.getenv("OPENAI_API_KEY", "")
        primary_url = os.getenv("OPENAI_BASE_URL", "")
        primary_model = os.getenv("OPENAI_MODEL_NAME", "google/gemini-2.5-flash")
        if primary_key and primary_key != "mock-key":
            c = OpenAI(api_key=primary_key, base_url=primary_url) if primary_url else OpenAI(api_key=primary_key)
            self.providers.append({"name": "Primary", "client": c, "model": primary_model})

        # Fallback provider
        fallback_key = os.getenv("FALLBACK_LLM_API_KEY", "")
        fallback_url = os.getenv("FALLBACK_LLM_BASE_URL", "")
        fallback_model = os.getenv("FALLBACK_LLM_MODEL_NAME", "")
        if fallback_key and fallback_key not in ("", "gsk_your_groq_api_key_here") and fallback_model:
            fc = OpenAI(api_key=fallback_key, base_url=fallback_url) if fallback_url else OpenAI(api_key=fallback_key)
            self.providers.append({"name": "Fallback", "client": fc, "model": fallback_model})

        # Backward-compat
        if self.providers:
            self.client = self.providers[0]["client"]
            self.model_name = self.providers[0]["model"]
        else:
            self.client = OpenAI(api_key="mock-key")
            self.model_name = primary_model

    def _call_provider(self, provider, messages, tools=None, max_tokens=300):
        kwargs = {"model": provider["model"], "messages": messages, "max_tokens": max_tokens}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        return provider["client"].chat.completions.create(**kwargs)

    def process_chat(self, text: str, context_str: str) -> dict:
        """Try each LLM provider in order. If all fail, return a clear error — no Python fallback."""
        current_date = date.today().strftime("%Y-%m-%d")

        tools = [
            {
                "type": "function",
                "function": {
                    "name": "apply_leave",
                    "description": "Call ONLY when the user explicitly wants to apply for a leave of absence.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "leave_type": {"type": "string", "description": "Type of leave (Casual Leave, Sick Leave, Earned Leave, etc.)"},
                            "start_date": {"type": "string", "description": "Start date YYYY-MM-DD"},
                            "end_date": {"type": "string", "description": "End date YYYY-MM-DD"},
                            "reason": {"type": "string", "description": "Reason for leave"},
                        },
                        "required": ["leave_type", "start_date", "end_date", "reason"],
                    },
                },
            }
        ]

        system_prompt = (
            f"You are LeaveDesk AI — a smart leave management assistant.\n"
            f"Today's date is {current_date}.\n\n"
            f"RULES:\n"
            f"1. When the user wants to APPLY for leave → call the `apply_leave` tool.\n"
            f"   Resolve relative dates (tomorrow, next week, next Friday, in N days) using today's date.\n"
            f"   If no leave type is mentioned, ask the user to specify it — do NOT guess.\n"
            f"2. For all other questions (balance, policy, history, holidays, profile) → answer concisely from the context.\n"
            f"3. Be friendly, direct, and professional.\n\n"
            f"=== Employee Context ===\n{context_str}"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ]

        last_error = None
        for provider in self.providers:
            try:
                print(f"[LLM] Trying {provider['name']} ({provider['model']})")
                response = self._call_provider(provider, messages, tools=tools, max_tokens=300)
                msg = response.choices[0].message
                if msg.tool_calls:
                    args = json.loads(msg.tool_calls[0].function.arguments)
                    print(f"[LLM] {provider['name']} -> apply_leave")
                    return {"intent": "apply_leave", "leave_details": args}
                else:
                    print(f"[LLM] {provider['name']} -> general_inquiry")
                    return {"intent": "general_inquiry", "chat_response": msg.content}
            except Exception as e:
                last_error = e
                print(f"[LLM] {provider['name']} FAILED: {e}")

        # All providers failed — return friendly error, NO hardcoded Python logic
        print(f"[LLM] All providers failed: {last_error}")
        err_str = str(last_error)
        if "402" in err_str:
            hint = " OpenRouter credits exhausted — please top up at openrouter.ai/settings/credits or add a FALLBACK_LLM_API_KEY in .env."
        elif "401" in err_str:
            hint = " Invalid API key — check OPENAI_API_KEY in .env."
        elif "429" in err_str:
            hint = " Rate limit hit — please wait a moment and try again."
        else:
            hint = " Please try again shortly or contact your administrator."

        return {
            "intent": "general_inquiry",
            "chat_response": f"⚠️ The AI service is temporarily unavailable.{hint}",
        }
