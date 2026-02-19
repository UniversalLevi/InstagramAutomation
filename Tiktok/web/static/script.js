// Global JavaScript utilities for TikTok web

function formatDate(dateString) {
    if (!dateString) return 'N/A';
    return new Date(dateString).toLocaleString();
}

function showNotification(message, type = 'info') {
    var notification = document.createElement('div');
    notification.className = 'notification notification-' + type;
    notification.textContent = message;
    var bg = type === 'success' ? '#d4edda' : type === 'error' ? '#f8d7da' : '#d1ecf1';
    var fg = type === 'success' ? '#155724' : type === 'error' ? '#721c24' : '#0c5460';
    notification.style.cssText = 'position:fixed;top:20px;right:20px;padding:1rem 1.5rem;background:' + bg + ';color:' + fg + ';border-radius:4px;box-shadow:0 2px 8px rgba(0,0,0,0.2);z-index:10000;max-width:320px;';
    document.body.appendChild(notification);
    setTimeout(function() { notification.remove(); }, 4000);
}
