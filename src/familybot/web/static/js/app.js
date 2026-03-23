/* =====================================================
   FamilyBot Web UI — Core Application JavaScript
   ===================================================== */

// ── Toast Notifications ──────────────────────────────
const toastStack = (() => {
    let el = document.getElementById('toast-stack');
    if (!el) {
        el = document.createElement('div');
        el.id = 'toast-stack';
        el.className = 'toast-stack';
        document.body.appendChild(el);
    }
    return el;
})();

function showToast(message, type = 'info', duration = 4000) {
    const icons = { info: 'fa-info-circle', success: 'fa-check-circle', warning: 'fa-exclamation-triangle', danger: 'fa-times-circle' };
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<i class="fas ${icons[type] || icons.info}"></i><span>${message}</span>`;
    toastStack.appendChild(toast);
    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(24px)';
        toast.style.transition = 'all 0.2s ease';
        setTimeout(() => toast.remove(), 200);
    }, duration);
}

// Legacy alias used in some templates
function showAlert(msg, type) { showToast(msg, type === 'danger' ? 'danger' : type); }

// ── Loading Modal ─────────────────────────────────────
const loadingModal = (() => {
    let backdrop = document.getElementById('loading-modal');
    if (!backdrop) {
        backdrop = document.createElement('div');
        backdrop.id = 'loading-modal';
        backdrop.className = 'modal-backdrop';
        backdrop.innerHTML = `
            <div class="modal-box">
                <div class="spinner spinner-lg"></div>
                <div style="color:var(--text-dim);font-family:var(--font-mono);font-size:13px;" id="loading-msg">Processing...</div>
            </div>`;
        document.body.appendChild(backdrop);
    }
    return backdrop;
})();

function showLoading(show, msg = 'Processing...') {
    document.getElementById('loading-msg').textContent = msg;
    loadingModal.classList.toggle('show', show);
}

// ── Bot Status ────────────────────────────────────────
let _statusInterval = null;

async function loadBotStatus() {
    try {
        const r = await fetch('/api/status');
        const s = await r.json();

        // Update sidebar pill
        const pill = document.getElementById('sidebar-status');
        if (pill) {
            pill.className = 'status-pill ' + (s.online ? 'online' : 'offline');
            pill.querySelector('.label').textContent = s.online ? 'Online' : 'Offline';
        }

        // Update dashboard metrics if on dashboard page
        _setEl('bot-online-status', s.online ? 'Online' : 'Offline');
        _setEl('bot-uptime', s.uptime || '—');
        _setEl('discord-status', s.discord_connected ? 'Connected' : 'Disconnected');
        _setEl('websocket-status', s.websocket_active ? 'Active' : 'Inactive');
        _setEl('token-status', s.token_valid ? 'Valid' : 'Expired/Missing');

        // Color the metric values
        _colorEl('bot-online-status', s.online ? 'text-green' : 'text-red');
        _colorEl('discord-status', s.discord_connected ? 'text-green' : 'text-red');
        _colorEl('token-status', s.token_valid ? 'text-green' : 'text-yellow');

        return s;
    } catch (e) {
        console.warn('Status fetch failed:', e);
    }
}

async function refreshStatus() {
    await loadBotStatus();
    showToast('Status refreshed', 'info');
}

function startStatusPolling(interval = 30000) {
    loadBotStatus();
    _statusInterval = setInterval(loadBotStatus, interval);
    window.addEventListener('beforeunload', () => clearInterval(_statusInterval));
}

function _setEl(id, val) {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
}

function _colorEl(id, cls) {
    const el = document.getElementById(id);
    if (!el) return;
    el.classList.remove('text-green', 'text-red', 'text-yellow', 'text-accent');
    el.classList.add(cls);
}

// ── Cache Stats ───────────────────────────────────────
async function loadCacheStats() {
    try {
        const r = await fetch('/api/cache/stats');
        const s = await r.json();
        const labels = {
            game_details: { label: 'Game Details', icon: 'fa-gamepad' },
            user_games:   { label: 'User Games',   icon: 'fa-user' },
            wishlist:     { label: 'Wishlist',      icon: 'fa-heart' },
            family_library: { label: 'Family Lib', icon: 'fa-users' },
            itad_prices:  { label: 'Prices',        icon: 'fa-tag' },
            discord_users:{ label: 'Discord Users', icon: 'fa-discord' },
        };
        const grid = document.getElementById('cache-stats-grid');
        if (!grid) return;
        grid.innerHTML = '';
        Object.entries(labels).forEach(([key, meta]) => {
            grid.insertAdjacentHTML('beforeend', `
                <div class="stat-card">
                    <i class="fas ${meta.icon} stat-icon"></i>
                    <div class="stat-value">${(s[key] ?? 0).toLocaleString()}</div>
                    <div class="stat-label">${meta.label}</div>
                </div>`);
        });
    } catch (e) {
        console.warn('Cache stats fetch failed:', e);
    }
}

// ── Cache Purge ───────────────────────────────────────
async function purgeCache(type) {
    const labels = { all: 'all cache data', expired: 'expired entries' };
    if (!confirm(`Purge ${labels[type] || type}?`)) return;
    showLoading(true, 'Purging cache…');
    try {
        const r = await fetch(`/api/cache/purge?cache_type=${type}`, { method: 'POST' });
        const d = await r.json();
        showToast(d.message, d.success ? 'success' : 'danger');
        loadCacheStats();
    } catch (e) {
        showToast('Error purging cache', 'danger');
    } finally {
        showLoading(false);
    }
}

// ── Recent Games ──────────────────────────────────────
async function loadRecentGames() {
    const container = document.getElementById('recent-games');
    if (!container) return;
    try {
        const r = await fetch('/api/recent-games?limit=8');
        const games = await r.json();
        if (!games.length) {
            container.innerHTML = '<div class="empty-state"><i class="fas fa-gamepad"></i><h3>No games yet</h3><p>Games appear here when detected.</p></div>';
            return;
        }
        container.innerHTML = games.map(g => {
            const badges = [
                g.is_free && '<span class="badge badge-green">Free</span>',
                g.is_multiplayer && '<span class="badge badge-blue">Multiplayer</span>',
                g.is_coop && '<span class="badge badge-purple">Co-op</span>',
            ].filter(Boolean).join('');
            return `<div class="game-card">
                <div style="flex:1">
                    <div class="game-name">${g.name || 'Unknown'}</div>
                    <div class="game-meta">App ID: ${g.appid}</div>
                    ${badges ? `<div class="game-badges mt-1">${badges}</div>` : ''}
                </div>
                <a href="https://store.steampowered.com/app/${g.appid}" target="_blank" class="btn btn-secondary btn-sm">
                    <i class="fas fa-external-link-alt"></i>
                </a>
            </div>`;
        }).join('');
    } catch (e) {
        container.innerHTML = '<div class="empty-state"><i class="fas fa-exclamation-circle"></i><h3>Load failed</h3></div>';
    }
}

// ── Family Members ────────────────────────────────────
async function loadFamilyMembers(containerId = 'family-members') {
    const container = document.getElementById(containerId);
    if (!container) return;
    try {
        const r = await fetch('/api/family-members');
        const members = await r.json();
        if (!members.length) {
            container.innerHTML = '<div class="empty-state"><i class="fas fa-users"></i><h3>No members</h3><p>Add Steam IDs in config.yml</p></div>';
            return;
        }
        container.innerHTML = members.map(m => `
            <div class="member-card">
                <div>
                    <div class="member-name">${m.friendly_name}</div>
                    <div class="member-id">${m.steam_id}</div>
                </div>
                <div>${m.discord_id
                    ? '<span class="badge badge-blue"><i class="fab fa-discord"></i> Linked</span>'
                    : '<span class="badge badge-gray">Unlinked</span>'}</div>
            </div>`).join('');
        return members;
    } catch (e) {
        container.innerHTML = '<div class="empty-state"><i class="fas fa-exclamation-circle"></i><h3>Load failed</h3></div>';
    }
}

// ── Sidebar Mobile Toggle ─────────────────────────────
function initSidebar() {
    const sidebar  = document.getElementById('sidebar');
    const overlay  = document.getElementById('sidebar-overlay');
    const menuBtn  = document.getElementById('mobile-menu-btn');

    if (menuBtn && sidebar && overlay) {
        menuBtn.addEventListener('click', () => {
            sidebar.classList.toggle('open');
            overlay.classList.toggle('show');
        });
        overlay.addEventListener('click', () => {
            sidebar.classList.remove('open');
            overlay.classList.remove('show');
        });
    }
}

// ── Accordion ─────────────────────────────────────────
function initAccordions() {
    document.querySelectorAll('.accordion-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const body = btn.nextElementSibling;
            const isOpen = body.classList.contains('open');
            btn.classList.toggle('open', !isOpen);
            body.classList.toggle('open', !isOpen);
        });
    });
}

// ── Init ──────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    initSidebar();
    initAccordions();
    startStatusPolling();
});
