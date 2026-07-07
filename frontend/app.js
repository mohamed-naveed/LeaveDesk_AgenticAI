// State System
let currentUser = null;
let currentSocket = null;
let activeView = 'dashboard';
let balances = [];
let myRequests = [];
let pendingApprovals = [];
let resolvedApprovals = [];
let auditLogs = [];
let employeesList = [];

// API Configuration
const API_BASE = '/api';

// On Load Initialization
document.addEventListener('DOMContentLoaded', () => {
    initApp();
});

// App Entrypoint
function initApp() {
    // Check localStorage session
    const savedUser = localStorage.getItem('user_session');
    if (savedUser) {
        currentUser = JSON.parse(savedUser);
        showWorkspace();
    } else {
        showScreen('login-screen');
    }

    // Set up Login form
    const loginForm = document.getElementById('login-form');
    loginForm.addEventListener('submit', handleLogin);

    // Set up credential quick-select shortcut tags
    const credTags = document.querySelectorAll('.cred-tag');
    credTags.forEach(tag => {
        tag.addEventListener('click', (e) => {
            e.preventDefault();
            document.getElementById('login-email').value = tag.getAttribute('data-email');
            document.getElementById('login-password').value = tag.getAttribute('data-password');
            // Auto submit
            loginForm.dispatchEvent(new Event('submit'));
        });
    });

    // Chat view event listeners
    document.getElementById('chat-send-btn').addEventListener('click', sendChatMessage);
    document.getElementById('chat-input').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') sendChatMessage();
    });

    // Chat suggestion chips
    const suggestions = document.querySelectorAll('.suggestion-chip');
    suggestions.forEach(chip => {
        chip.addEventListener('click', () => {
            document.getElementById('chat-input').value = chip.textContent;
            sendChatMessage();
        });
    });

    // Setup review modal actions
    document.getElementById('modal-close-btn').addEventListener('click', closeReviewModal);
    document.getElementById('modal-cancel-btn').addEventListener('click', closeReviewModal);
    document.getElementById('btn-refresh-audit').addEventListener('click', fetchAuditLogs);

    // Setup employee detail modal actions
    const empCloseBtn = document.getElementById('emp-modal-close-btn');
    if (empCloseBtn) empCloseBtn.addEventListener('click', closeEmployeeDetailModal);
    const empCloseActionBtn = document.getElementById('emp-modal-close-action-btn');
    if (empCloseActionBtn) empCloseActionBtn.addEventListener('click', closeEmployeeDetailModal);

    // Setup reset database button listener
    const resetBtn = document.getElementById('btn-reset-db');
    if (resetBtn) {
        resetBtn.addEventListener('click', async () => {
            const confirmed = confirm("Are you sure you want to reset the database? This will permanently delete all leave requests, approvals, and agent execution logs.");
            if (!confirmed) return;

            resetBtn.disabled = true;
            resetBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Resetting...`;

            try {
                const res = await fetch(`${API_BASE}/admin/reset-db`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' }
                });

                if (!res.ok) {
                    const data = await res.json();
                    throw new Error(data.detail || 'Reset failed');
                }

                showToast('Database Reset', 'The database was reset successfully. All requests, approvals, and logs have been cleared.', 'success');
                
                // Refresh active manager views
                if (currentUser && currentUser.role === 'admin') {
                    if (activeView === 'manager-approvals') {
                        fetchManagerPendingRequests();
                    } else if (activeView === 'manager-audit') {
                        fetchAuditLogs();
                    }
                }
            } catch (err) {
                showToast('Reset Failed', err.message, 'warning');
            } finally {
                resetBtn.disabled = false;
                resetBtn.innerHTML = `<i class="fa-solid fa-trash-can"></i> Reset Database`;
            }
        });
    }

    // Dashboard quick actions
    document.getElementById('btn-quick-chat').addEventListener('click', () => switchView('employee-chat'));
    document.getElementById('btn-quick-history').addEventListener('click', () => switchView('employee-history'));

    // Manager approvals tabs
    document.getElementById('btn-show-pending').addEventListener('click', () => {
        document.getElementById('btn-show-pending').classList.add('active');
        document.getElementById('btn-show-resolved').classList.remove('active');
        document.getElementById('manager-pending-section').style.display = 'block';
        document.getElementById('manager-resolved-section').style.display = 'none';
    });

    document.getElementById('btn-show-resolved').addEventListener('click', () => {
        document.getElementById('btn-show-resolved').classList.add('active');
        document.getElementById('btn-show-pending').classList.remove('active');
        document.getElementById('manager-pending-section').style.display = 'none';
        document.getElementById('manager-resolved-section').style.display = 'block';
        fetchManagerPendingRequests();
    });
}

// Route to Screen views
function showScreen(screenId) {
    document.querySelectorAll('.screen').forEach(scr => {
        scr.classList.remove('active');
    });
    document.getElementById(screenId).classList.add('active');
}

// Login Handler
async function handleLogin(e) {
    e.preventDefault();
    const email = document.getElementById('login-email').value;
    const password = document.getElementById('login-password').value;

    const loginBtn = document.querySelector('.login-btn');
    loginBtn.disabled = true;
    loginBtn.innerHTML = `<span>Logging in...</span> <i class="fa-solid fa-spinner fa-spin"></i>`;

    try {
        const res = await fetch(`${API_BASE}/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });

        if (!res.ok) {
            const data = await res.json();
            throw new Error(data.detail || 'Login failed');
        }

        const data = await res.json();
        currentUser = data;
        localStorage.setItem('user_session', JSON.stringify(currentUser));
        showWorkspace();
    } catch (err) {
        showToast('Login Failed', err.message, 'warning');
        loginBtn.disabled = false;
        loginBtn.innerHTML = `<span>Login Securely</span> <i class="fa-solid fa-arrow-right"></i>`;
    }
}

// Workspace Setup
function showWorkspace() {
    showScreen('app-screen');
    
    // Set Profile details in Sidebar
    document.getElementById('user-name').textContent = currentUser.name;
    document.getElementById('user-role').textContent = currentUser.role === 'admin' ? 'Manager' : 'Employee';
    document.getElementById('user-avatar').textContent = currentUser.name.split(' ').map(n => n[0]).join('');

    // Toggle admin action buttons
    const resetDbBtn = document.getElementById('btn-reset-db');
    if (resetDbBtn) {
        resetDbBtn.style.display = currentUser.role === 'admin' ? 'flex' : 'none';
    }

    // Render navigation links based on user role
    renderSidebarNav();

    // Load initial view data
    if (currentUser.role === 'admin') {
        switchView('manager-approvals');
    } else {
        switchView('dashboard');
    }

    // Bind logout button
    document.getElementById('logout-btn').addEventListener('click', handleLogout);
}

// Side Navigation render
function renderSidebarNav() {
    const navList = document.getElementById('nav-list');
    navList.innerHTML = '';

    if (currentUser.role === 'admin') {
        navList.appendChild(createNavItem('manager-approvals', 'fa-solid fa-square-check', 'Pending Approvals'));
        navList.appendChild(createNavItem('employee-chat', 'fa-solid fa-comments', 'Chat with LeaveDesk AI'));
        navList.appendChild(createNavItem('manager-employees', 'fa-solid fa-users', 'Employees List'));
        navList.appendChild(createNavItem('manager-audit', 'fa-solid fa-terminal', 'Agent Decison Stream'));
        navList.appendChild(createNavItem('notifications', 'fa-solid fa-bell', 'Notifications'));
    } else {
        navList.appendChild(createNavItem('dashboard', 'fa-solid fa-grid-2', 'Dashboard'));
        navList.appendChild(createNavItem('employee-chat', 'fa-solid fa-comments', 'Chat with LeaveDesk AI'));
        navList.appendChild(createNavItem('employee-history', 'fa-solid fa-history', 'My Leave History'));
        navList.appendChild(createNavItem('notifications', 'fa-solid fa-bell', 'Notifications'));
    }

    // Set active class link
    document.querySelectorAll('.nav-link-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            const view = btn.getAttribute('data-view');
            switchView(view);
        });
    });
}

function createNavItem(viewId, iconClass, label) {
    const li = document.createElement('li');
    li.className = 'nav-item';
    li.id = `nav-${viewId}`;
    li.innerHTML = `
        <button class="nav-link nav-link-btn" data-view="${viewId}">
            <i class="${iconClass}"></i>
            <span>${label}</span>
        </button>
    `;
    return li;
}

// View Controller Switching
function switchView(viewId) {
    activeView = viewId;
    
    // Update active nav links
    document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));
    const activeNav = document.getElementById(`nav-${viewId}`);
    if (activeNav) activeNav.classList.add('active');

    // Update Subviews visibility
    document.querySelectorAll('.sub-view').forEach(view => {
        view.classList.remove('active');
    });

    const activeViewEl = document.getElementById(`view-${viewId}`);
    if (activeViewEl) activeViewEl.classList.add('active');

    // Update headers text dynamically
    const viewTitle = document.getElementById('view-title');
    const viewSubtitle = document.getElementById('view-subtitle');

    if (viewId === 'dashboard') {
        viewTitle.textContent = 'Welcome, ' + currentUser.name.split(' ')[0];
        viewSubtitle.textContent = 'Quick overview of your current leave balances';
        fetchEmployeeBalances();
    } else if (viewId === 'employee-chat') {
        viewTitle.textContent = 'LeaveDesk AI Conversation';
        viewSubtitle.textContent = 'Tell the AI Agent in natural language when you need leave';
        initChatWindow();
    } else if (viewId === 'employee-history') {
        viewTitle.textContent = 'Your Leave History';
        viewSubtitle.textContent = 'List of all submitted requests and status updates';
        fetchEmployeeRequests();
    } else if (viewId === 'manager-approvals') {
        viewTitle.textContent = 'Pending Team Requests';
        viewSubtitle.textContent = 'Review leave requests submitted by subordinates';
        fetchManagerPendingRequests();
    } else if (viewId === 'manager-audit') {
        viewTitle.textContent = 'Agent Action Stream';
        viewSubtitle.textContent = 'Live stream of what the specialist AI agents are checking';
        fetchAuditLogs();
    } else if (viewId === 'manager-employees') {
        viewTitle.textContent = 'Team Directory';
        viewSubtitle.textContent = 'Overview of all active employees';
        fetchEmployeesList();
    } else if (viewId === 'notifications') {
        viewTitle.textContent = 'Your Notifications';
        viewSubtitle.textContent = 'Stay updated with your leave request notifications';
        fetchNotifications();
    }
}



// Toast Popup Notification Handler
function showToast(title, message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    
    let iconClass = 'fa-solid fa-circle-info';
    if (type === 'success') iconClass = 'fa-solid fa-circle-check';
    if (type === 'warning') iconClass = 'fa-solid fa-triangle-exclamation';

    toast.innerHTML = `
        <div class="toast-icon"><i class="${iconClass}"></i></div>
        <div class="toast-details">
            <h4>${title}</h4>
            <p>${message}</p>
        </div>
        <button class="toast-close">&times;</button>
    `;

    container.appendChild(toast);

    toast.querySelector('.toast-close').addEventListener('click', () => {
        toast.style.animation = 'fadeOut 0.2s forwards';
        setTimeout(() => toast.remove(), 200);
    });

    // Auto dismiss after 5 seconds
    setTimeout(() => {
        if (toast.parentElement) {
            toast.style.animation = 'fadeOut 0.2s forwards';
            setTimeout(() => toast.remove(), 200);
        }
    }, 5000);
}

// --- API ACTIONS / REQUESTS ---

// 1. Fetch Employee Balances
async function fetchEmployeeBalances() {
    try {
        const res = await fetch(`${API_BASE}/leave-balances?employee_id=${currentUser.id}`);
        if (!res.ok) throw new Error('Failed to load balances');
        balances = await res.ok ? await res.json() : [];
        renderBalancesDashboard();
    } catch (err) {
        console.error(err);
    }
}

function renderBalancesDashboard() {
    const container = document.getElementById('balance-container');
    container.innerHTML = '';

    const typesMap = {
        'casual': { title: 'Casual Leave', limit: 10, icon: 'fa-solid fa-umbrella-beach' },
        'sick': { title: 'Sick Leave', limit: 10, icon: 'fa-solid fa-stethoscope' }
    };

    if (balances.length === 0) {
        container.innerHTML = `<div class="text-secondary padding-md">No balances loaded.</div>`;
        return;
    }

    balances.forEach(b => {
        const config = typesMap[b.leave_type] || { title: b.leave_type.toUpperCase(), limit: 30, icon: 'fa-solid fa-briefcase' };
        const percent = Math.min(100, Math.max(0, (b.balance / config.limit) * 100));
        
        const card = document.createElement('div');
        card.className = `balance-card ${b.leave_type}`;
        card.innerHTML = `
            <div class="balance-card-glow"></div>
            <div class="balance-header">
                <h3>${config.title}</h3>
                <div class="balance-icon"><i class="${config.icon}"></i></div>
            </div>
            <div class="balance-value">
                <h2>${b.balance}</h2>
                <p>Days Available</p>
            </div>
            <div class="balance-progress-bar">
                <div class="balance-progress-fill" style="width: ${percent}%"></div>
            </div>
        `;
        container.appendChild(card);
    });
}

// 2. Fetch Employee Leave Requests List
async function fetchEmployeeRequests() {
    try {
        const res = await fetch(`${API_BASE}/my-leave-requests?employee_id=${currentUser.id}`);
        if (!res.ok) throw new Error('Failed to load history');
        myRequests = await res.json();
        renderMyRequestsTable();
    } catch (err) {
        console.error(err);
    }
}

function renderMyRequestsTable() {
    const tbody = document.getElementById('my-requests-body');
    tbody.innerHTML = '';

    if (myRequests.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" class="text-secondary text-center">No leave requests found.</td></tr>`;
        return;
    }

    // Sort requests by ID desc
    myRequests.sort((a, b) => b.id - a.id);

    myRequests.forEach(req => {
        const tr = document.createElement('tr');
        
        let badgeClass = 'pending_manager';
        let statusText = 'Pending Approval';
        if (req.status === 'approved') { badgeClass = 'approved'; statusText = 'Approved'; }
        if (req.status === 'rejected') { badgeClass = 'rejected'; statusText = 'Rejected'; }
        if (req.status === 'cancelled') { badgeClass = 'cancelled'; statusText = 'Cancelled'; }

        // Cancel button visible only for pending manager requests
        const actionHtml = req.status === 'pending_manager' 
            ? `<button class="btn-action cancel" onclick="cancelLeaveRequest(${req.id})">Cancel</button>` 
            : `<span class="text-secondary font-sm">Closed</span>`;

        tr.innerHTML = `
            <td><strong class="text-primary">${req.leave_type.toUpperCase()}</strong></td>
            <td>${req.start_date}</td>
            <td>${req.end_date}</td>
            <td><span class="text-secondary">${req.reason || 'N/A'}</span></td>
            <td><span class="status-pill ${badgeClass}">${statusText}</span></td>
            <td class="text-right">${actionHtml}</td>
        `;
        tbody.appendChild(tr);
    });
}

// 3. Cancel Leave Request
async function cancelLeaveRequest(requestId) {
    if (!confirm('Are you sure you want to cancel this leave request?')) return;

    try {
        const res = await fetch(`${API_BASE}/cancel-request`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ request_id: requestId })
        });

        if (!res.ok) throw new Error('Failed to cancel request');
        showToast('Success', 'Leave request cancelled successfully', 'success');
        fetchEmployeeRequests();
    } catch (err) {
        showToast('Error', err.message, 'warning');
    }
}

// 4. Fetch Manager Pending Requests
async function fetchManagerPendingRequests() {
    try {
        const res = await fetch(`${API_BASE}/leave-requests`);
        if (!res.ok) throw new Error('Failed to load requests');
        const allReqs = await res.json();
        
        // Filter requests for Pending Manager Approval
        pendingApprovals = allReqs.filter(r => r.status === 'Pending Manager Approval');
        renderPendingRequests();

        // Filter resolved requests (Approved, Rejected, AutoApproved)
        resolvedApprovals = allReqs.filter(r => r.status === 'Approved' || r.status === 'Rejected');
        renderResolvedRequests();
    } catch (err) {
        console.error(err);
    }
}

function renderResolvedRequests() {
    const body = document.getElementById('manager-resolved-body');
    body.innerHTML = '';

    if (resolvedApprovals.length === 0) {
        body.innerHTML = `<tr><td colspan="5" class="text-center text-secondary padding-md">No actioned leave history found.</td></tr>`;
        return;
    }

    resolvedApprovals.forEach(req => {
        const tr = document.createElement('tr');
        const statusClass = req.status.toLowerCase().replace(/\s+/g, '-');
        
        tr.innerHTML = `
            <td>
                <div style="font-weight: 600;">${req.employee_name}</div>
                <div style="font-size: 11px;" class="text-secondary">Dept ID: ${req.department}</div>
            </td>
            <td><span class="type-badge ${req.leave_type || 'casual'}">${req.leave_type ? req.leave_type.toUpperCase() : 'CASUAL'}</span></td>
            <td>${req.start_date}</td>
            <td>${req.end_date}</td>
            <td><span class="status-badge ${statusClass}">${req.status}</span></td>
        `;
        body.appendChild(tr);
    });
}

function renderPendingRequests() {
    const container = document.getElementById('pending-requests-container');
    container.innerHTML = '';

    if (pendingApprovals.length === 0) {
        container.innerHTML = `<div class="text-secondary padding-md text-center">No pending leave requests requiring review.</div>`;
        return;
    }

    pendingApprovals.forEach(req => {
        const card = document.createElement('div');
        card.className = 'pending-card';
        
        // Check Agent recommendation type
        const agentRec = req.agent_decision || 'ManualReview';
        const recReason = req.agent_reason || 'Requires supervisor alignment evaluation.';
        const recClass = agentRec === 'AutoApproved' ? '' : 'manual_review';
        const recTitle = agentRec === 'AutoApproved' ? 'Agent Approved Check' : 'Agent Flags Flagged';

        const initials = req.employee_name.split(' ').map(n => n[0]).join('');

        card.innerHTML = `
            <div class="pending-card-header">
                <div class="pending-card-avatar">${initials}</div>
                <div class="pending-card-header-info">
                    <h4>${req.employee_name}</h4>
                    <span>Department ID: ${req.department}</span>
                </div>
            </div>
            
            <div class="pending-details">
                <div class="pending-details-row">
                    <span class="pending-details-label">Date Range:</span>
                    <span class="pending-details-val">${req.start_date} to ${req.end_date}</span>
                </div>
                <div class="pending-details-row">
                    <span class="pending-details-label">Reason:</span>
                    <span class="pending-details-val">${req.reason || 'N/A'}</span>
                </div>
            </div>

            <div class="agent-recommendation-box ${recClass}">
                <h5><i class="fa-solid fa-robot"></i> ${recTitle}</h5>
                <p>${recReason}</p>
            </div>

            <div class="pending-actions">
                <button class="btn-reject" onclick="openReviewModal(${req.request_id}, 'Rejected')">Reject</button>
                <button class="btn-approve" onclick="openReviewModal(${req.request_id}, 'Approved')">Approve</button>
            </div>
        `;
        container.appendChild(card);
    });
}

// 5. Fetch Audit Decision Logs Stream
async function fetchAuditLogs() {
    try {
        const res = await fetch(`${API_BASE}/leave-requests`);
        if (!res.ok) throw new Error('Failed to load leave requests');
        const requests = await res.json();
        renderAuditRequests(requests);
    } catch (err) {
        console.error(err);
    }
}

function renderAuditRequests(requests) {
    const container = document.getElementById('audit-logs-container');
    container.innerHTML = '';

    if (requests.length === 0) {
        container.innerHTML = `<div class="text-secondary padding-md text-center">No leave requests found to audit.</div>`;
        return;
    }

    // Sort requests by ID descending (latest first)
    requests.sort((a, b) => b.request_id - a.request_id);

    requests.forEach(req => {
        const item = document.createElement('div');
        item.className = 'audit-request-card';
        item.style.cssText = 'background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 20px; margin-bottom: 16px; transition: all var(--ease);';
        
        let statusClass = 'pending_manager';
        if (req.status.toLowerCase() === 'approved') statusClass = 'approved';
        if (req.status.toLowerCase() === 'rejected') statusClass = 'rejected';
        if (req.status.toLowerCase() === 'cancelled') statusClass = 'cancelled';

        item.innerHTML = `
            <div class="audit-request-header" style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 12px; margin-bottom: 14px;">
                <div>
                    <h3 style="font-size: 15px; font-weight: 700; color: var(--slate); margin: 0; display: flex; align-items: center; gap: 8px;">
                        ${req.employee_name}
                        <span class="role-badge" style="background: var(--teal-light); color: var(--teal); font-size: 10px; font-weight: 700; border-radius: 4px; padding: 2px 6px;">Dept: ${req.department_id || 'N/A'}</span>
                    </h3>
                    <p style="font-size: 12px; color: var(--text-secondary); margin: 4px 0 0 0;">${req.employee_email}</p>
                </div>
                <div style="display: flex; align-items: center; gap: 10px;">
                    <span class="status-pill ${statusClass}">${req.status}</span>
                </div>
            </div>
            <div class="audit-request-details" style="font-size: 13px; color: var(--text); margin-bottom: 16px; display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px;">
                <div><strong>Leave Type:</strong> ${req.leave_type}</div>
                <div><strong>Requested Days:</strong> ${req.requested_days}</div>
                <div><strong>Start Date:</strong> ${req.start_date}</div>
                <div><strong>End Date:</strong> ${req.end_date}</div>
                <div style="grid-column: 1 / -1;"><strong>Reason:</strong> ${req.reason || 'N/A'}</div>
            </div>
            
            <button class="timeline-details-btn" id="audit-btn-${req.request_id}" onclick="toggleAuditTrace(${req.request_id})" style="border: 1px solid var(--border); background: var(--canvas); cursor: pointer; padding: 8px 12px; border-radius: var(--radius); font-size: 12px; font-weight: 600; display: flex; align-items: center; gap: 6px; color: var(--text);">
                <i class="fa-solid fa-magnifying-glass-chart" style="color: var(--teal);"></i> View Agent Execution Trace <i class="fa-solid fa-chevron-down" style="margin-left: auto;"></i>
            </button>
            
            <div class="audit-trace-container" id="audit-trace-${req.request_id}" style="display: none; margin-top: 16px; padding-top: 16px; border-top: 1px dashed var(--border);">
                <div class="text-secondary font-sm text-center"><i class="fa-solid fa-spinner fa-spin"></i> Fetching agent logs...</div>
            </div>
        `;
        container.appendChild(item);
    });
}

async function toggleAuditTrace(requestId) {
    const traceContainer = document.getElementById(`audit-trace-${requestId}`);
    const btn = document.getElementById(`audit-btn-${requestId}`);
    if (!traceContainer || !btn) return;

    if (traceContainer.style.display === 'block') {
        traceContainer.style.display = 'none';
        btn.querySelector('.fa-chevron-down').className = 'fa-solid fa-chevron-down';
        return;
    }

    traceContainer.style.display = 'block';
    btn.querySelector('.fa-chevron-down').className = 'fa-solid fa-chevron-up';

    try {
        const res = await fetch(`${API_BASE}/audit-logs/${requestId}`);
        if (!res.ok) throw new Error('Failed to load logs');
        const logs = await res.json();

        traceContainer.innerHTML = '';

        if (logs.length === 0) {
            traceContainer.innerHTML = `<div class="text-secondary font-sm text-center padding-sm">No trace logs recorded for this request.</div>`;
            return;
        }

        const timeline = document.createElement('div');
        timeline.className = 'timeline-container';
        timeline.style.cssText = 'padding-left: 20px; border-left: 2px solid var(--border); position: relative; margin-top: 10px; margin-left: 10px;';

        logs.forEach(log => {
            const item = document.createElement('div');
            const isSuccess = log.status.toLowerCase() === 'success' || log.status.toLowerCase() === 'approved' || log.status.toLowerCase() === 'autoapproved';
            item.className = 'timeline-item';
            item.style.cssText = 'position: relative; margin-bottom: 20px;';

            const iconClass = isSuccess ? 'fa-solid fa-check-circle' : 'fa-solid fa-circle-exclamation';
            const iconColor = isSuccess ? 'var(--success)' : 'var(--danger)';

            let cleanInput = log.input;
            let cleanOutput = log.output;
            try {
                if (typeof log.input === 'string') cleanInput = JSON.stringify(JSON.parse(log.input), null, 2);
            } catch (e) {}
            try {
                if (typeof log.output === 'string') cleanOutput = JSON.stringify(JSON.parse(log.output), null, 2);
            } catch (e) {}

            item.innerHTML = `
                <div class="timeline-icon" style="position: absolute; left: -31px; top: 0; width: 20px; height: 20px; border-radius: 50%; background: var(--surface); display: flex; align-items: center; justify-content: center; font-size: 14px; color: ${iconColor};">
                    <i class="${iconClass}"></i>
                </div>
                <div class="timeline-content" style="background: var(--canvas); border: 1px solid var(--border); border-radius: var(--radius); padding: 12px 16px;">
                    <div class="timeline-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; gap: 10px;">
                        <h5 style="font-size: 13px; font-weight: 600; color: var(--slate); margin: 0;">${log.agent}</h5>
                        <span class="timeline-time" style="font-size: 11px; color: var(--text-muted);">${log.timestamp}</span>
                    </div>
                    <div class="timeline-body" style="font-size: 12px; color: var(--text); margin-bottom: 8px;">
                        <strong>Status:</strong> ${log.status}
                    </div>
                    <button class="timeline-details-btn" onclick="toggleTraceDetail(${log.log_id})" style="border: none; background: none; color: var(--teal); font-weight: 600; font-size: 11px; cursor: pointer; padding: 0; display: flex; align-items: center; gap: 4px;">
                        <span>View JSON payload</span> <i class="fa-solid fa-chevron-down"></i>
                    </button>
                    <div class="timeline-expanded-data" id="trace-detail-${log.log_id}" style="display: none; margin-top: 10px; font-family: monospace; font-size: 11px; background: var(--surface); border: 1px solid var(--border); padding: 10px; border-radius: var(--radius); white-space: pre-wrap; word-break: break-all; color: var(--text-secondary);">
Input:
${cleanInput}

Output:
${cleanOutput}
                    </div>
                </div>
            `;
            timeline.appendChild(item);
        });

        traceContainer.appendChild(timeline);
    } catch (err) {
        console.error(err);
        traceContainer.innerHTML = `<div class="text-danger font-sm text-center padding-sm">Error loading trace logs: ${err.message}</div>`;
    }
}

function toggleTraceDetail(logId) {
    const el = document.getElementById(`trace-detail-${logId}`);
    const btn = el.previousElementSibling;
    if (!el || !btn) return;
    
    const icon = btn.querySelector('.fa-chevron-down') || btn.querySelector('.fa-chevron-up');
    if (el.style.display === 'block') {
        el.style.display = 'none';
        if (icon) icon.className = 'fa-solid fa-chevron-down';
    } else {
        el.style.display = 'block';
        if (icon) icon.className = 'fa-solid fa-chevron-up';
    }
}

function toggleTimelineDetail(logId) {
    const el = document.getElementById(`audit-detail-${logId}`);
    const btn = el.previousElementSibling;
    if (el.style.display === 'block') {
        el.style.display = 'none';
        btn.classList.remove('expanded');
    } else {
        el.style.display = 'block';
        btn.classList.add('expanded');
    }
}

// 6. Fetch Employees Directory List
async function fetchEmployeesList() {
    try {
        const res = await fetch(`${API_BASE}/employees`);
        if (!res.ok) throw new Error('Failed to load employees');
        employeesList = await res.json();
        renderEmployeesGrid();
    } catch (err) {
        console.error(err);
    }
}

function renderEmployeesGrid() {
    const container = document.getElementById('employees-list-container');
    container.innerHTML = '';

    if (employeesList.length === 0) {
        container.innerHTML = `<div class="text-secondary padding-md text-center">No employee records available.</div>`;
        return;
    }

    employeesList.forEach(emp => {
        const card = document.createElement('div');
        card.className = 'employee-card';
        const initials = emp.name.split(' ').map(n => n[0]).join('');

        card.innerHTML = `
            <div class="employee-card-avatar">${initials}</div>
            <h3>${emp.name}</h3>
            <p>${emp.email}</p>
            <span class="role-badge">${emp.role.toUpperCase()}</span>
            <p class="text-muted font-sm">Department ID: ${emp.department || 'N/A'}</p>
        `;
        card.addEventListener('click', () => openEmployeeDetailModal(emp));
        container.appendChild(card);
    });
}

function openEmployeeDetailModal(emp) {
    const modal = document.getElementById('employee-detail-modal');
    if (!modal) return;

    const initials = emp.name.split(' ').map(n => n[0]).join('');
    document.getElementById('emp-modal-avatar').textContent = initials;
    document.getElementById('emp-modal-name').textContent = emp.name;
    document.getElementById('emp-modal-email').textContent = emp.email;

    const pendingBody = document.getElementById('emp-modal-pending-leaves');
    const approvedBody = document.getElementById('emp-modal-approved-leaves');

    pendingBody.innerHTML = `<tr><td colspan="6" class="text-center text-secondary"><i class="fa-solid fa-spinner fa-spin"></i> Loading...</td></tr>`;
    approvedBody.innerHTML = `<tr><td colspan="5" class="text-center text-secondary"><i class="fa-solid fa-spinner fa-spin"></i> Loading...</td></tr>`;

    modal.classList.add('active');

    fetch(`${API_BASE}/employee/history/${emp.id}`)
        .then(res => {
            if (!res.ok) throw new Error('Failed to load history');
            return res.json();
        })
        .then(history => {
            pendingBody.innerHTML = '';
            approvedBody.innerHTML = '';

            const pending = history.filter(r => r.status.toLowerCase().includes('pending'));
            const approved = history.filter(r => r.status.toLowerCase() === 'approved');

            if (pending.length === 0) {
                pendingBody.innerHTML = `<tr><td colspan="6" class="text-center text-secondary">No pending requests.</td></tr>`;
            } else {
                pending.forEach(r => {
                    const tr = document.createElement('tr');
                    let statusClass = 'pending_manager';
                    if (r.status.toLowerCase().includes('reject')) statusClass = 'rejected';
                    if (r.status.toLowerCase().includes('cancel')) statusClass = 'cancelled';
                    
                    tr.innerHTML = `
                        <td>${r.start_date}</td>
                        <td>${r.end_date}</td>
                        <td><span class="role-badge" style="background: var(--teal-light); color: var(--teal); font-size: 10px; font-weight: 700; border-radius: 4px; padding: 2px 6px;">${r.leave_type.toUpperCase()}</span></td>
                        <td>${r.requested_days}</td>
                        <td><span class="status-pill ${statusClass}">${r.status}</span></td>
                        <td><span class="font-sm text-secondary">${r.reason || 'N/A'}</span></td>
                    `;
                    pendingBody.appendChild(tr);
                });
            }

            if (approved.length === 0) {
                approvedBody.innerHTML = `<tr><td colspan="5" class="text-center text-secondary">No approved leaves.</td></tr>`;
            } else {
                approved.forEach(r => {
                    const tr = document.createElement('tr');
                    tr.innerHTML = `
                        <td>${r.start_date}</td>
                        <td>${r.end_date}</td>
                        <td><span class="role-badge" style="background: var(--success-bg); color: var(--success); font-size: 10px; font-weight: 700; border-radius: 4px; padding: 2px 6px;">${r.leave_type.toUpperCase()}</span></td>
                        <td>${r.requested_days}</td>
                        <td><span class="font-sm text-secondary">${r.reason || 'N/A'}</span></td>
                    `;
                    approvedBody.appendChild(tr);
                });
            }
        })
        .catch(err => {
            console.error(err);
            pendingBody.innerHTML = `<tr><td colspan="6" class="text-center text-danger">Error loading history.</td></tr>`;
            approvedBody.innerHTML = `<tr><td colspan="5" class="text-center text-danger">Error loading history.</td></tr>`;
        });
}

function closeEmployeeDetailModal() {
    document.getElementById('employee-detail-modal').classList.remove('active');
}

// --- REVIEW MODAL HANDLERS ---
let activeReviewRequestId = null;
let activeReviewDecision = null;

function openReviewModal(requestId, decision) {
    activeReviewRequestId = requestId;
    activeReviewDecision = decision;

    const modal = document.getElementById('review-modal');
    const req = pendingApprovals.find(r => r.request_id === requestId);
    
    if (!req) return;

    // Display summary
    const summary = document.getElementById('modal-request-summary');
    summary.innerHTML = `
        <div><strong>Employee:</strong> ${req.employee_name}</div>
        <div><strong>Leave range:</strong> ${req.start_date} to ${req.end_date}</div>
        <div><strong>Reason:</strong> ${req.reason || 'N/A'}</div>
        <div><strong>Decision applied:</strong> <span class="status-pill ${decision === 'Approved' ? 'approved' : 'rejected'}">${decision}</span></div>
    `;

    document.getElementById('modal-comments').value = '';
    
    // Set colors based on decision
    const approveBtn = document.getElementById('modal-approve-btn');
    const rejectBtn = document.getElementById('modal-reject-btn');

    if (decision === 'Approved') {
        approveBtn.style.display = 'block';
        rejectBtn.style.display = 'none';
    } else {
        approveBtn.style.display = 'none';
        rejectBtn.style.display = 'block';
    }

    modal.classList.add('active');
}

function closeReviewModal() {
    document.getElementById('review-modal').classList.remove('active');
    activeReviewRequestId = null;
    activeReviewDecision = null;
}

// Bind modal resolve buttons
document.getElementById('modal-approve-btn').addEventListener('click', () => resolveRequest('Approved'));
document.getElementById('modal-reject-btn').addEventListener('click', () => resolveRequest('Rejected'));

async function resolveRequest(decision) {
    const comments = document.getElementById('modal-comments').value;

    try {
        const res = await fetch(`${API_BASE}/manage-request`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                request_id: activeReviewRequestId,
                status: decision,
                comments: comments || `Actioned as ${decision}`
            })
        });

        if (!res.ok) throw new Error('Failed to resolve request');
        showToast('Resolved successfully', `Request has been marked as ${decision}`, 'success');
        closeReviewModal();
        fetchManagerPendingRequests();
    } catch (err) {
        showToast('Error', err.message, 'warning');
    }
}


// --- CHAT DIALOGUE HANDLERS ---
let chatLog = [];

function initChatWindow() {
    const scrollEl = document.getElementById('chat-messages');
    scrollEl.innerHTML = '';
    
    // Initial greeting
    chatLog = [
        {
            role: 'agent',
            message: `Hello ${currentUser.name.split(' ')[0]}, I am your LeaveDesk AI assistant. How can I help you today? You can apply for leave or check your policies.`,
            time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        }
    ];

    chatLog.forEach(msg => appendMessageBubble(msg));
}

function appendMessageBubble(msg) {
    const container = document.getElementById('chat-messages');
    const bubble = document.createElement('div');
    bubble.className = `chat-msg ${msg.role}`;
    
    bubble.innerHTML = `
        <div class="msg-bubble">${msg.message}</div>
        <span class="msg-meta">${msg.time}</span>
    `;

    container.appendChild(bubble);
    container.scrollTop = container.scrollHeight;
}

async function sendChatMessage() {
    const input = document.getElementById('chat-input');
    const text = input.value.trim();
    if (!text) return;

    input.value = '';

    // Render user message bubble
    const userMsg = {
        role: 'user',
        message: text,
        time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    };
    chatLog.push(userMsg);
    appendMessageBubble(userMsg);

    // Render typing indicator
    const container = document.getElementById('chat-messages');
    const typingBubble = document.createElement('div');
    typingBubble.className = 'chat-msg agent typing-msg';
    typingBubble.innerHTML = `
        <div class="msg-bubble">
            <div class="typing-indicator">
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
                <div class="typing-dot"></div>
            </div>
        </div>
    `;
    container.appendChild(typingBubble);
    container.scrollTop = container.scrollHeight;

    try {
        const res = await fetch(`${API_BASE}/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                employee_id: currentUser.id,
                message: text
            })
        });

        if (!res.ok) throw new Error('API server error');
        
        const data = await res.json();
        
        // Remove typing indicator
        typingBubble.remove();

        const agentMsg = {
            role: 'agent',
            message: data.response,
            time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        };
        chatLog.push(agentMsg);
        appendMessageBubble(agentMsg);
        
        // Refresh balance count in background if request was processed
        fetchEmployeeBalances();
    } catch (err) {
        typingBubble.remove();
        const errMsg = {
            role: 'agent',
            message: 'Sorry, I encountered an error communicating with the agent server. Please make sure the backend is active.',
            time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
        };
        chatLog.push(errMsg);
        appendMessageBubble(errMsg);
    }
}


// Notifications Management
let userNotifications = [];

async function fetchNotifications() {
    try {
        const res = await fetch(`${API_BASE}/notifications?employee_id=${currentUser.id}`);
        if (!res.ok) throw new Error('Failed to fetch notifications');
        userNotifications = await res.json();
        renderNotifications();
    } catch (err) {
        console.error(err);
        const container = document.getElementById('notifications-list-container');
        if (container) {
            container.innerHTML = `<div class="text-danger padding-md text-center">Error loading notifications: ${err.message}</div>`;
        }
    }
}

function renderNotifications() {
    const container = document.getElementById('notifications-list-container');
    if (!container) return;
    
    container.innerHTML = '';
    
    if (userNotifications.length === 0) {
        container.innerHTML = `<div class="text-secondary padding-md text-center">No notifications available.</div>`;
        return;
    }
    
    userNotifications.forEach(n => {
        const card = document.createElement('div');
        card.className = 'notification-card';
        card.style.cssText = 'background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 18px; margin-bottom: 12px; display: flex; align-items: flex-start; gap: 14px; transition: all var(--ease);';
        
        let iconClass = 'fa-solid fa-bell';
        let iconColor = 'var(--teal)';
        
        const subjLower = n.subject.toLowerCase();
        if (subjLower.includes('approved')) {
            iconClass = 'fa-solid fa-circle-check';
            iconColor = 'var(--success)';
        } else if (subjLower.includes('reject')) {
            iconClass = 'fa-solid fa-circle-xmark';
            iconColor = 'var(--danger)';
        } else if (subjLower.includes('pending') || subjLower.includes('notice')) {
            iconClass = 'fa-solid fa-circle-exclamation';
            iconColor = 'var(--warning)';
        }
        
        card.innerHTML = `
            <div style="font-size: 20px; color: ${iconColor}; margin-top: 2px;">
                <i class="${iconClass}"></i>
            </div>
            <div style="flex: 1;">
                <h4 style="margin: 0; font-size: 14px; font-weight: 700; color: var(--slate);">${n.subject}</h4>
                <p style="margin: 6px 0 0 0; font-size: 13px; color: var(--text-secondary); line-height: 1.4;">${n.message}</p>
                <div style="margin-top: 8px; font-size: 11px; color: var(--text-muted);">${n.sent_at}</div>
            </div>
        `;
        container.appendChild(card);
    });
}

// Logout handler
function handleLogout() {
    localStorage.removeItem('user_session');
    currentUser = null;
    if (currentSocket) {
        currentSocket.close();
        currentSocket = null;
    }
    const resetDbBtn = document.getElementById('btn-reset-db');
    if (resetDbBtn) resetDbBtn.style.display = 'none';
    showScreen('login-screen');
}
