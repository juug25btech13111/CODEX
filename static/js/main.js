// Dark Mode Toggle Logic
const themeToggleBtn = document.getElementById('theme-toggle');
const darkIcon = document.getElementById('theme-toggle-dark-icon');
const lightIcon = document.getElementById('theme-toggle-light-icon');

// Change the icons inside the button based on previous settings
if (localStorage.getItem('color-theme') === 'dark' || !('color-theme' in localStorage)) {
    darkIcon?.classList.add('hidden');
    lightIcon?.classList.remove('hidden');
    document.documentElement.classList.add('dark');
} else {
    lightIcon?.classList.add('hidden');
    darkIcon?.classList.remove('hidden');
    document.documentElement.classList.remove('dark');
}

if (themeToggleBtn) {
    themeToggleBtn.addEventListener('click', function() {
        // toggle icons inside button
        darkIcon.classList.toggle('hidden');
        lightIcon.classList.toggle('hidden');

        // if set via local storage previously
        if (localStorage.getItem('color-theme')) {
            if (localStorage.getItem('color-theme') === 'light') {
                document.documentElement.classList.add('dark');
                localStorage.setItem('color-theme', 'dark');
            } else {
                document.documentElement.classList.remove('dark');
                localStorage.setItem('color-theme', 'light');
            }

        // if NOT set via local storage previously
        } else {
            if (document.documentElement.classList.contains('dark')) {
                document.documentElement.classList.remove('dark');
                localStorage.setItem('color-theme', 'light');
            } else {
                document.documentElement.classList.add('dark');
                localStorage.setItem('color-theme', 'dark');
            }
        }
    });
}

// Sidebar Toggle Mobile
const sidebarToggles = document.querySelectorAll('.sidebar-toggle-btn');
const sidebar = document.getElementById('sidebar');

if (sidebar) {
    sidebarToggles.forEach(btn => {
        btn.addEventListener('click', () => {
            sidebar.classList.toggle('-translate-x-full');
        });
    });
}

// Fade out alerts
setTimeout(() => {
    const alerts = document.querySelectorAll('.alert-auto-dismiss');
    alerts.forEach(alert => {
        alert.style.transition = "opacity 0.5s ease";
        alert.style.opacity = "0";
        setTimeout(() => alert.remove(), 500);
    });
}, 5000);
