(function () {
    const theme = localStorage.getItem('theme') ||
        (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    document.documentElement.setAttribute('theme', theme);

    function syncThemeSwitch() {
        const dark = document.documentElement.getAttribute('theme') === 'dark';
        document.querySelectorAll('.theme-switcher').forEach(function (button) {
            button.setAttribute('aria-pressed', String(dark));
        });
    }
    document.addEventListener('DOMContentLoaded', syncThemeSwitch);
    document.addEventListener('htmx:load', syncThemeSwitch);
})();
