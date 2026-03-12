/**
 * Shared Notification Component
 * Auto-polls for unread count, shows badge, supports "Tất cả" / "Chưa đọc" filter tabs.
 * Self-contained: injects its own CSS so no external stylesheet dependency needed.
 */

// ── Inject CSS ──────────────────────────────────────────────────────────────
(function injectNotifCSS() {
    if (document.getElementById('notif-component-css')) return;
    const style = document.createElement('style');
    style.id = 'notif-component-css';
    style.textContent = `
        .notif-dropdown {
            display: none;
            position: absolute;
            top: 100%;
            left: 0;
            width: 320px;
            background: white;
            border-radius: 12px;
            box-shadow: 0 8px 30px rgba(0,0,0,0.18);
            max-height: 420px;
            overflow-y: auto;
            z-index: 100;
            margin-top: 8px;
        }
        .notif-header {
            padding: 0.65rem 0.875rem;
            border-bottom: 1px solid #e2e8f0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .notif-header strong {
            color: #1e293b;
            font-size: 0.875rem;
        }
        .notif-header a {
            font-size: 0.75rem;
            color: #3b82f6;
            text-decoration: none;
        }
        .notif-tabs {
            display: flex;
            gap: 0;
            padding: 0.375rem 0.75rem;
            border-bottom: 1px solid #f1f5f9;
        }
        .notif-tab {
            padding: 0.3rem 0.75rem;
            font-size: 0.75rem;
            font-weight: 500;
            color: #64748b;
            background: transparent;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-family: inherit;
            transition: all 0.15s;
        }
        .notif-tab:hover {
            color: #1e293b;
            background: #f1f5f9;
        }
        .notif-tab.active {
            color: white;
            background: #3b82f6;
        }
        .notif-item {
            display: flex;
            gap: 0.5rem;
            padding: 0.5rem 0.75rem;
            border-radius: 8px;
            margin: 2px 0.375rem;
            cursor: pointer;
            transition: background 0.15s;
        }
        .notif-item:hover {
            background: #f1f5f9;
        }
        .notif-item.unread {
            background: rgba(59,130,246,0.06);
        }
        .notif-icon {
            font-size: 1rem;
            flex-shrink: 0;
            margin-top: 1px;
        }
        .notif-content {
            flex: 1;
            min-width: 0;
        }
        .notif-title {
            font-size: 0.8125rem;
            font-weight: 600;
            color: #1e293b;
        }
        .notif-item:not(.unread) .notif-title {
            font-weight: 400;
        }
        .notif-msg {
            font-size: 0.75rem;
            color: #64748b;
            margin-top: 1px;
            overflow: hidden;
            text-overflow: ellipsis;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
        }
        .notif-time {
            font-size: 0.625rem;
            color: #94a3b8;
            margin-top: 2px;
        }
        #notifBadge {
            display: none;
            position: absolute;
            top: -4px;
            right: -6px;
            background: #ef4444;
            color: white;
            font-size: 0.55rem;
            font-weight: 700;
            padding: 1px 4px;
            border-radius: 10px;
            min-width: 14px;
            text-align: center;
        }
    `;
    document.head.appendChild(style);
})();

// ── State ───────────────────────────────────────────────────────────────────
let notifOpen = false;
let notifFilter = 'all'; // 'all' or 'unread'
let allNotifications = [];

function toggleNotifDropdown() {
    notifOpen = !notifOpen;
    document.getElementById('notifDropdown').style.display = notifOpen ? 'block' : 'none';
    if (notifOpen) loadNotifications();
}

// Close dropdown when clicking outside
document.addEventListener('click', function (e) {
    const bell = document.getElementById('notifBell');
    const dropdown = document.getElementById('notifDropdown');
    if (bell && dropdown && !bell.contains(e.target) && !dropdown.contains(e.target)) {
        notifOpen = false;
        dropdown.style.display = 'none';
    }
});

function setNotifFilter(filter) {
    notifFilter = filter;
    document.querySelectorAll('.notif-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.filter === filter);
    });
    renderNotifList();
}

function renderNotifList() {
    const list = document.getElementById('notifList');
    const filtered = notifFilter === 'unread'
        ? allNotifications.filter(n => !n.is_read)
        : allNotifications;

    if (filtered.length === 0) {
        list.innerHTML = '<div style="text-align:center;padding:1.5rem 1rem;color:#94a3b8;font-size:0.8125rem;">Không có thông báo</div>';
        return;
    }

    list.innerHTML = filtered.slice(0, 20).map(n => {
        const icon = n.title.includes('duyệt') ? '✅' : n.title.includes('từ chối') ? '❌' : n.title.includes('Role') ? '👤' : '🔔';
        return `<div class="notif-item ${n.is_read ? '' : 'unread'}" onclick="${n.link ? `window.location.href='${n.link}'` : ''}">
            <div class="notif-icon">${icon}</div>
            <div class="notif-content">
                <div class="notif-title">${n.title}</div>
                <div class="notif-msg">${n.message}</div>
                <div class="notif-time">${new Date(n.created_at).toLocaleString('vi-VN')}</div>
            </div>
        </div>`;
    }).join('');
}

async function loadNotifications() {
    try {
        const res = await fetch('/api/v1/notifications');
        if (!res.ok) return;
        const data = await res.json();
        allNotifications = data.notifications || [];

        const badge = document.getElementById('notifBadge');
        badge.textContent = data.unread_count;
        badge.style.display = data.unread_count > 0 ? 'inline-block' : 'none';

        renderNotifList();
    } catch (e) { }
}

async function markAllRead() {
    await fetch('/api/v1/notifications/mark-read', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' });
    loadNotifications();
}

async function pollNotifCount() {
    try {
        const res = await fetch('/api/v1/notifications/unread-count');
        if (!res.ok) return;
        const data = await res.json();
        const badge = document.getElementById('notifBadge');
        if (badge) {
            badge.textContent = data.unread_count;
            badge.style.display = data.unread_count > 0 ? 'inline-block' : 'none';
        }
    } catch (e) { }
}

// Auto-poll: immediately on load, then every 30 seconds
setTimeout(pollNotifCount, 500);
setInterval(pollNotifCount, 30000);
