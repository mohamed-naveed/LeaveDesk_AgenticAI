# 🗓️ LeaveDesk — Employee Leave Management (Agentic AI)

An intelligent employee leave management system powered by a multi-agent AI pipeline. Employees can apply for leave via natural language chat, and the system automatically validates, decides, routes for approval, and notifies all stakeholders — all driven by AI agents.

---

## ✨ Features

- 💬 **Natural Language Leave Requests** — Chat with the AI to apply for leave ("I need sick leave from July 10 to July 12")
- 🤖 **Multi-Agent Pipeline** — Supervisor, Decision, Calendar, Policy, Overlap, Team Availability, Notification, and Audit agents work together
- ✅ **Automatic Approval / Routing** — Short leaves get auto-approved; complex ones route to the manager
- 👨‍💼 **Manager Admin Portal** — Approve or reject leave requests with one click
- 🔔 **Team-Wide Notifications** — On approval, the employee, manager, and all teammates are notified with leave dates
- 📊 **Audit Logs** — Every agent action is logged for full traceability
- 🔐 **JWT Authentication** — Secure login for employees and managers
- 🌐 **Gemini 2.5 Flash via OpenRouter** — LLM backbone for intent classification and leave parsing
- 🔄 **LLM Fallback Mechanism** — Automatically falls back to deterministic python/regex validation if the LLM fails or hits token limits (e.g., code 402/401)
- 👨‍💼 **Manager AI Queries** — Managers can query their list of managed employees, see balances (all or specific), and view past leave histories (all or specific)

---

## 🏗️ Architecture

```
frontend/
├── index.html          # Single-page app shell
├── app.js              # All UI logic, API calls, chat interface
└── styles.css          # Custom CSS (glassmorphism, dark mode)

backend/
├── main.py             # FastAPI app entry point (serves frontend + API)
├── requirements.txt    # Python dependencies
├── agents/
│   ├── supervisor_agent.py         # Orchestrates the full pipeline (LLM + deterministic)
│   ├── leave_decision_agent.py     # Rule-based approval/rejection/routing
│   ├── calendar_agent.py           # Working days, weekends, holidays
│   ├── leave_policy_agent.py       # Policy constraints per leave type
│   ├── leave_overlap_agent.py      # Detects overlapping requests
│   ├── team_availability_agent.py  # Team threshold check
│   ├── approval_agent.py           # Manager approval processing
│   ├── notification_agent.py       # Saves notifications to DB
│   ├── audit_agent.py              # Logs agent execution steps
│   ├── employee_profile_agent.py   # Employee info lookup
│   └── leave_balance_agent.py      # Balance checks and updates
├── routes/
│   └── api_routes.py   # All REST API endpoints
├── services/
│   ├── llm_service.py  # OpenRouter / Gemini 2.5 Flash integration
│   └── auth_service.py # JWT + bcrypt authentication
├── database/
│   ├── connection.py   # SQLAlchemy DB setup
│   └── models.py       # ORM models (Employee, LeaveRequest, Notification, etc.)
└── schemas/            # Pydantic request/response schemas
```

---

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- MySQL running locally
- [OpenRouter](https://openrouter.ai) API key

### 1. Clone the Repository

```bash
git clone https://github.com/mohamed-naveed/LeaveDesk_AgenticAI.git
cd LeaveDesk_AgenticAI
```

### 2. Set Up the Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure Environment Variables

Create a `.env` file in the **root** of the project:

```env
DATABASE_URL=mysql+pymysql://root:YOUR_PASSWORD@localhost/leave_db
OPENAI_API_KEY=sk-or-v1-YOUR_OPENROUTER_KEY
JWT_SECRET_KEY=your-secret-key
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_MODEL_NAME=google/gemini-2.5-flash
```

> ⚠️ **Never commit `.env` to version control. It is excluded via `.gitignore`.**

### 4. Set Up the Database

Create the `leave_db` MySQL database and run your schema migrations. Ensure the `Employee`, `LeaveRequest`, `LeaveBalance`, `LeaveType`, `Notification`, and related tables exist.

### 5. Run the Server

```bash
cd backend
source venv/bin/activate
uvicorn main:app --reload
```

Visit **http://localhost:8000** in your browser.

---

## 🔑 Default Credentials

| Role     | Email                  | Password  |
|----------|------------------------|-----------|
| Employee | employee1@company.com  | pass123   |
| Manager  | manager@company.com    | pass123   |

*(Update via the `/api/auth/setup-password` endpoint if needed)*

---

## 🌐 API Endpoints

| Method | Endpoint                    | Description                         |
|--------|-----------------------------|-------------------------------------|
| POST   | `/api/login`                | Login and get session               |
| POST   | `/api/chat`                 | Send a natural language leave request |
| GET    | `/api/leave-balances`       | Get employee leave balances         |
| GET    | `/api/my-leave-requests`    | Get employee's own requests         |
| GET    | `/api/leave-requests`       | Get all requests (admin)            |
| POST   | `/api/manage-request`       | Approve / Reject a request (admin)  |
| GET    | `/api/notifications`        | Get notifications for an employee   |
| GET    | `/api/employees`            | List all employees                  |
| GET    | `/api/audit-logs`           | View agent execution audit logs     |
| POST   | `/api/admin/reset-db`       | Reset all leave data (dev/demo)     |

---

## 🤖 Agent Pipeline (Leave Application Flow)

```
User Chat Message
      │
      ▼
LLMService (Gemini 2.5 Flash via OpenRouter)
  ├── Intent: general_inquiry → direct response
  └── Intent: apply_leave → SupervisorAgent
            │
            ├── EmployeeProfileAgent   → validate employee
            ├── LeaveBalanceAgent      │ check available days
            ├── CalendarAgent          │ compute working days
            ├── LeavePolicyAgent       │ get policy constraints
            ├── LeaveOverlapAgent      │ detect conflicts
            ├── TeamAvailabilityAgent  │ check team threshold
            ├── LeaveDecisionAgent     → Approve / Reject / ManualReview
            ├── ApprovalAgent          → save request + approval task
            ├── NotificationAgent      → notify employee (+ team if approved)
            └── AuditAgent             → log every step
```

---

## 📦 Tech Stack

| Layer      | Technology                        |
|------------|-----------------------------------|
| Frontend   | HTML, Vanilla CSS, JavaScript     |
| Backend    | Python, FastAPI, SQLAlchemy       |
| Database   | MySQL                             |
| AI / LLM   | Google Gemini 2.5 Flash (via OpenRouter) |
| Auth       | JWT + bcrypt                      |
| Server     | Uvicorn (ASGI)                    |

---

## 📄 License

MIT License — free to use, modify, and distribute.
