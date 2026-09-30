/**
 * SiliconRoute Theme Manager
 * Single source of truth for dashboard light / dark theme toggle and persistence.
 * docs/DESIGN_SPEC.md Section 6 & 10.
 */

export function setupTheme() {
  const saved = localStorage.getItem("siliconroute_theme") || "light";
  document.documentElement.setAttribute("data-theme", saved);
  document.body.setAttribute("data-theme", saved);

  const toggleBtn = document.getElementById("theme-toggle-btn");
  if (toggleBtn) {
    toggleBtn.addEventListener("click", () => {
      const current = document.documentElement.getAttribute("data-theme") || "light";
      const next = current === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      document.body.setAttribute("data-theme", next);
      localStorage.setItem("siliconroute_theme", next);
      window.dispatchEvent(new CustomEvent("themechange", { detail: { theme: next } }));
    });
  }
}

// Immediately set attribute on module load to prevent theme flash
try {
  const initial = localStorage.getItem("siliconroute_theme") || "light";
  document.documentElement.setAttribute("data-theme", initial);
} catch {
  // Ignore in non-browser contexts
}
