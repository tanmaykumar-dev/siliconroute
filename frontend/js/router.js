/**
 * SiliconRoute Design Spec v2 : Client Screen Router
 * Manages screen activation via hash routing (#/overview, #/live, etc.)
 * and keyboard navigation ('g o', 'g l', arrow keys, '?').
 */

export class ClientRouter {
  constructor(screens, defaultScreen = "overview") {
    this.screens = screens;
    this.defaultScreen = defaultScreen;
    this.currentScreen = null;
    this.gSequence = false;
    this.gTimeout = null;

    this.init();
  }

  init() {
    window.addEventListener("hashchange", () => this.handleHashChange());
    this.setupRailNavigation();
    this.setupKeyboardShortcuts();
    this.handleHashChange();
  }

  handleHashChange() {
    const raw = window.location.hash.replace("#/", "").trim();
    const screenId = this.screens.includes(raw) ? raw : this.defaultScreen;
    this.navigate(screenId, false);
  }

  navigate(screenId, updateHash = true) {
    if (this.currentScreen === screenId) return;

    this.currentScreen = screenId;
    if (updateHash) {
      window.location.hash = `#/${screenId}`;
    }

    // Toggle active screen panel
    document.querySelectorAll(".screen-container").forEach((el) => {
      const match = el.id === `screen-${screenId}`;
      el.classList.toggle("active", match);
      if (match) {
        el.removeAttribute("hidden");
      } else {
        el.setAttribute("hidden", "true");
      }
    });

    // Toggle rail button active state
    document.querySelectorAll(".rail-item-btn").forEach((btn) => {
      const match = btn.dataset.screen === screenId;
      btn.classList.toggle("active", match);
      btn.setAttribute("aria-current", match ? "page" : "false");
    });

    // Dispatch event so active screen can load its content/charts
    window.dispatchEvent(new CustomEvent("screenchange", { detail: { screen: screenId } }));
  }

  setupRailNavigation() {
    document.querySelectorAll(".rail-item-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const target = btn.dataset.screen;
        if (target) this.navigate(target);
      });
    });
  }

  setupKeyboardShortcuts() {
    document.addEventListener("keydown", (e) => {
      // Ignore if user is inside an input, select, or textarea
      if (["INPUT", "SELECT", "TEXTAREA"].includes(e.target.tagName)) return;

      // Handle '?' to toggle keyboard shortcuts sheet
      if (e.key === "?" && !e.ctrlKey && !e.metaKey) {
        e.preventDefault();
        const sheet = document.getElementById("modal-shortcuts");
        if (sheet) {
          const isOpen = sheet.classList.contains("active") || sheet.classList.contains("open");
          sheet.classList.toggle("active", !isOpen);
          sheet.classList.remove("open");
        }
        return;
      }

      if (e.key === "Escape") {
        const sheet = document.getElementById("modal-shortcuts");
        if (sheet) {
          sheet.classList.remove("active", "open");
        }
      }

      // Handle 'g' sequence prefix
      if (e.key === "g" && !this.gSequence) {
        this.gSequence = true;
        clearTimeout(this.gTimeout);
        this.gTimeout = setTimeout(() => {
          this.gSequence = false;
        }, 1200);
        return;
      }

      if (this.gSequence) {
        this.gSequence = false;
        clearTimeout(this.gTimeout);
        const map = {
          o: "overview",
          l: "live",
          a: "analysis",
          r: "router",
          s: "results",
          e: "evidence",
        };
        const dest = map[e.key.toLowerCase()];
        if (dest) {
          e.preventDefault();
          this.navigate(dest);
        }
      }
    });
  }
}
