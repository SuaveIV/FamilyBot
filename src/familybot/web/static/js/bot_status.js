// Global variables for bot status
let refreshInterval;

// Load bot status
async function loadBotStatus() {
    try {
        const response = await fetch('/api/status');
        const status = await response.json();
        
        // Update status indicator
        const indicator = document.getElementById('bot-status-indicator');
        if (indicator) { // Check if indicator exists on the page
            if (status.online) {
                indicator.className = 'status-indicator status-online';
                indicator.innerHTML = '<span class="status-dot"></span><span>Online</span>';
            } else {
                indicator.className = 'status-indicator status-offline';
                indicator.innerHTML = '<span class="status-dot"></span><span>Offline</span>';
            }
        }

        // Update detailed status metrics if they exist (only on dashboard)
        if (document.getElementById('bot-online-status')) {
            document.getElementById('bot-online-status').textContent = status.online ? 'Online' : 'Offline';
            document.getElementById('bot-uptime').textContent = status.uptime || '-';
            document.getElementById('discord-status').textContent = status.discord_connected ? 'Connected' : 'Disconnected';
            document.getElementById('websocket-status').textContent = status.websocket_active ? 'Active' : 'Inactive';
        }
    } catch (error) {
        console.error('Error loading bot status:', error);
    }
}

// Refresh status
async function refreshStatus() {
    await loadBotStatus();
    // Assuming showAlert is defined globally or included in each page
    if (typeof showAlert === 'function') {
        showAlert('Status refreshed', 'info');
    }
}

// Start auto-refresh
function startAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval); // Clear any existing interval
    }
    refreshInterval = setInterval(async () => {
        await loadBotStatus();
    }, 30000); // Refresh every 30 seconds
}

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    if (refreshInterval) {
        clearInterval(refreshInterval);
    }
});

// Initial load and auto-refresh start when the DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    loadBotStatus();
    startAutoRefresh();
});
