/**
 * SiliconRoute Design Spec v2 — Theme Management
 * Manages light / dark theme switching, localStorage persistence ('sr-theme'),
 * and dispatches 'themechange' events for Chart.js and dynamic SVG elements.
 */

const THEME_STORAGE_KEY = "sr-theme";

export class ThemeManager {
  constructor(defaultTheme = "dark") {
    this.defaultTheme = defaultTheme;
    this.currentTheme = this.resolveInitialTheme();
    this.applyTheme(this.currentTheme);
  }

  resolveInitialTheme() {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === "light" || stored === "dark") {
      return stored;
    }
    if (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) {
      return "light";
    }
    return this.defaultTheme;
  }

  applyTheme(theme) {
    this.currentTheme = theme;
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(THEME_STORAGE_KEY, theme);

    // Update theme toggle icon if button exists
    const btn = document.getElementById("btn-theme-toggle");
    if (btn) {
      btn.setAttribute("aria-label", `Switch to ${theme === "dark" ? "light" : "dark"} theme`);
      const icon = btn.querySelector("svg");
      if (icon) {
        icon.innerHTML = theme === "dark"
          ? `<circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line>`
          : `<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>`;
      }
    }

    // Broadcast theme change for Chart.js dynamic palette update
    window.dispatchEvent(new CustomEvent("themechange", { detail: { theme } }));
  }

  toggle() {
    const next = this.currentTheme === "dark" ? "light" : "dark";
    this.applyTheme(next);
    return next;
  }
}
