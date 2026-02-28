(function () {

    const theme = localStorage.getItem('theme') ||
        (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
            
    document.documentElement.setAttribute('theme', theme);
            
    if (window.htmx) {
        htmx.onLoad(function() {
            const themeSwitch = document.querySelector('.theme-switcher input[type="checkbox"]');
            if (themeSwitch) {
                themeSwitch.checked = (theme === 'dark');
            }
        });
    }
    
})();