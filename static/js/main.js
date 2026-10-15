// main.js — students will add JavaScript here as features are built

// ------------------------------------------------------------------ //
// Theme toggle                                                        //
// ------------------------------------------------------------------ //
// The initial theme is applied by the inline script in base.html.

(function () {
    var root = document.documentElement;
    var toggle = document.getElementById('theme-toggle');
    var systemDark = window.matchMedia('(prefers-color-scheme: dark)');

    function getSaved() {
        try { return localStorage.getItem('theme'); } catch (e) { return null; }
    }

    function applyTheme(theme) {
        root.setAttribute('data-theme', theme);
        if (toggle) {
            var label = theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode';
            toggle.setAttribute('aria-label', label);
            toggle.setAttribute('title', label);
        }
    }

    applyTheme(root.getAttribute('data-theme') === 'dark' ? 'dark' : 'light');

    if (toggle) {
        toggle.addEventListener('click', function () {
            var next = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
            applyTheme(next);
            try { localStorage.setItem('theme', next); } catch (e) {}
        });
    }

    // Follow system theme changes until the user picks a theme explicitly
    systemDark.addEventListener('change', function (e) {
        var saved = getSaved();
        if (saved !== 'light' && saved !== 'dark') {
            applyTheme(e.matches ? 'dark' : 'light');
        }
    });
})();
