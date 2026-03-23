/* =====================================================
   FamilyBot Web UI — Admin Panel JavaScript
   ===================================================== */

document.addEventListener('DOMContentLoaded', () => {
    initAdminButtons();
    loadMembersDropdown();
});

function clearOutput() {
    const out = document.getElementById('command-output');
    out.innerHTML = '<span style="color:var(--text-muted)">// Waiting for command…</span>';
}

function appendOutput(html) {
    const out = document.getElementById('command-output');
    if (out.querySelector('span[style*="Waiting"]')) out.innerHTML = '';
    out.insertAdjacentHTML('beforeend', html);
    out.scrollTop = out.scrollHeight;
}

function initAdminButtons() {
    // Direct endpoint buttons (database population, cache purge)
    document.querySelectorAll('.admin-btn').forEach(btn => {
        btn.addEventListener('click', async function () {
            const label = this.textContent.trim();
            const endpoint = this.dataset.endpoint;
            const method = this.dataset.method || 'POST';

            setAllButtons(true);
            appendOutput(`<div class="t-info">› ${label}…</div>`);

            try {
                const r = await fetch(endpoint, { method });
                const d = await r.json();
                const cls = d.success ? 't-success' : 't-error';
                appendOutput(`<div class="${cls}">${formatOutput(d.message)}</div><br>`);
                showToast(d.success ? 'Done' : 'Failed', d.success ? 'success' : 'danger');
            } catch (e) {
                appendOutput(`<div class="t-error">Error: ${e.message}</div><br>`);
                showToast('Request failed', 'danger');
            } finally {
                setAllButtons(false);
            }
        });
    });

    // Plugin action buttons
    document.querySelectorAll('.plugin-btn').forEach(btn => {
        btn.addEventListener('click', async function () {
            const command = this.dataset.command;
            const label = this.textContent.trim();

            let url = `/api/admin/plugin-action?command_name=${command}`;
            if (command === 'force_deals') {
                const target = document.getElementById('deals-target-user')?.value;
                if (target) url += `&target_user=${encodeURIComponent(target)}`;
            }

            setAllButtons(true);
            appendOutput(`<div class="t-info">› ${label}…</div>`);

            try {
                const r = await fetch(url, { method: 'POST' });
                const d = await r.json();
                const cls = d.success ? 't-success' : 't-error';
                appendOutput(`<div class="${cls}">${formatOutput(d.message)}</div><br>`);
                showToast(d.success ? 'Command complete' : 'Command failed', d.success ? 'success' : 'danger');
            } catch (e) {
                appendOutput(`<div class="t-error">Error: ${e.message}</div><br>`);
                showToast('Request failed', 'danger');
            } finally {
                setAllButtons(false);
            }
        });
    });
}

async function loadMembersDropdown() {
    const sel = document.getElementById('deals-target-user');
    if (!sel) return;
    try {
        const r = await fetch('/api/family-members');
        const members = await r.json();
        sel.innerHTML = '<option value="">All Family Members</option>';
        members.forEach(m => {
            const opt = document.createElement('option');
            opt.value = m.friendly_name;
            opt.textContent = m.friendly_name;
            sel.appendChild(opt);
        });
    } catch (e) { /* dropdown stays with "All" option */ }
}

function setAllButtons(disabled) {
    document.querySelectorAll('.admin-btn, .plugin-btn').forEach(btn => {
        btn.disabled = disabled;
    });
}

function formatOutput(msg) {
    if (!msg) return '';
    // Escape HTML, then convert markdown-ish formatting
    const escaped = msg
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');

    return escaped
        .replace(/\n/g, '<br>')
        .replace(/\*\*(.*?)\*\*/g, '<strong style="color:var(--text)">$1</strong>')
        .replace(/~~(.*?)~~/g, '<del>$1</del>')
        .replace(/(https?:\/\/[^\s&]+)/g, '<a href="$1" target="_blank" style="color:var(--accent)">$1</a>');
}
