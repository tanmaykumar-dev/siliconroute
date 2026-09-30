/**
 * SiliconRoute Design Spec v3: Toast System (Section 7.8)
 * Bottom-left, solid ink block, white text, 4 seconds duration, dismissible.
 */

export class ToastSystem {
  constructor() {
    this.container = null;
  }

  init() {
    this.container = document.getElementById("toast-container");
    if (!this.container) {
      this.container = document.createElement("div");
      this.container.id = "toast-container";
      this.container.className = "toast-container";
      this.container.setAttribute("aria-live", "polite");
      document.body.appendChild(this.container);
    }
  }

  show(message, durationMs = 4000) {
    if (!this.container) this.init();

    const toast = document.createElement("div");
    toast.className = "toast";
    toast.setAttribute("role", "status");

    const textSpan = document.createElement("span");
    textSpan.textContent = message;
    toast.appendChild(textSpan);

    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "toast-close-btn";
    closeBtn.setAttribute("aria-label", "Dismiss notification");
    closeBtn.textContent = "×";
    closeBtn.addEventListener("click", () => {
      toast.remove();
    });
    toast.appendChild(closeBtn);

    this.container.appendChild(toast);

    if (durationMs > 0) {
      setTimeout(() => {
        if (toast.parentElement) {
          toast.remove();
        }
      }, durationMs);
    }
  }
}

export const toast = new ToastSystem();
