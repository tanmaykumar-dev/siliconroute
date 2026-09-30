/**
 * SiliconRoute Design Spec v2 — Metrics & Evidence System (.metric)
 * Fetches published manifest metrics, renders formatted values with precise unit rules,
 * and mounts interactive evidence popovers showing exact SQL, methods, and source IDs.
 */

export class MetricsSystem {
  constructor(apiClient) {
    this.api = apiClient;
    this.manifest = null;
    this.activePopover = null;
  }

  async load() {
    try {
      this.manifest = await this.api.fetchPublishedMetrics();
      this.renderAll();
      this.setupGlobalPopoverDismiss();
    } catch (err) {
      console.error("Failed loading published metrics:", err);
    }
  }

  getMetric(key) {
    if (!this.manifest || !this.manifest.metrics) return null;
    return this.manifest.metrics[key] || null;
  }

  formatValue(key, val, unit) {
    if (val === null || val === undefined) return "not available";
    if (typeof val === "string") return val;

    // Milliseconds precision rules
    if (unit === "ms") {
      if (val < 1) return `${val.toFixed(3)} ms`;
      if (val <= 100) return `${val.toFixed(2)} ms`;
      return `${val.toFixed(1)} ms`;
    }

    // Percentage precision rules
    if (unit === "%") {
      if (key.includes("regret")) {
        return `${val.toFixed(2)}%`;
      }
      return `${val.toFixed(1)}%`;
    }

    // Ratio precision rules
    if (unit === "x") {
      return `${val.toFixed(1)}×`;
    }

    // GFLOP/s and Bandwidth
    if (unit === "GFLOP/s" || unit === "GB/s") {
      return `${val.toFixed(1)} ${unit}`;
    }

    // Integer / counts
    if (Number.isInteger(val)) {
      return val.toLocaleString();
    }

    return `${val} ${unit || ""}`.trim();
  }

  renderAll() {
    const elements = document.querySelectorAll(".metric[data-metric]");
    elements.forEach((el) => {
      const key = el.dataset.metric;
      const m = this.getMetric(key);
      if (!m) {
        el.textContent = "not available";
        el.classList.add("metric-missing");
        return;
      }

      const formatted = this.formatValue(key, m.value, m.unit);
      el.textContent = formatted;

      // Add evidence popover trigger if flagged with data-evidence
      if (el.dataset.evidence === "true" && !el.nextElementSibling?.classList.contains("evidence-btn")) {
        const btn = this.createEvidenceButton(key, m);
        el.after(btn);
      }
    });
  }

  createEvidenceButton(key, metric) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "evidence-btn";
    btn.setAttribute("aria-label", `Show evidence for ${key}`);
    btn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>`;

    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      this.togglePopover(btn, key, metric);
    });

    return btn;
  }

  togglePopover(anchorBtn, key, metric) {
    if (this.activePopover) {
      this.activePopover.remove();
      this.activePopover = null;
    }

    const popover = document.createElement("div");
    popover.className = "evidence-popover-panel open";
    popover.innerHTML = `
      <div style="font-weight:600; margin-bottom:var(--space-2); color:var(--ink);">${key}</div>
      <div class="evidence-row">
        <span class="evidence-row-label">Value:</span>
        <span class="evidence-row-val">${metric.value} ${metric.unit || ""}</span>
      </div>
      <div class="evidence-row">
        <span class="evidence-row-label">Description:</span>
        <span style="color:var(--ink-2); font-size:12px;">${metric.description || "N/A"}</span>
      </div>
      <div class="evidence-row">
        <span class="evidence-row-label">Calculation Method:</span>
        <span class="evidence-row-val" style="color:var(--chip-dgpu);">${metric.method || "N/A"}</span>
      </div>
      ${metric.sql ? `
      <div class="evidence-row">
        <span class="evidence-row-label">Database SQL:</span>
        <span class="evidence-row-val" style="font-size:11px; color:var(--ink-3);">${metric.sql}</span>
      </div>` : ""}
    `;

    document.body.appendChild(popover);
    const rect = anchorBtn.getBoundingClientRect();
    popover.style.top = `${rect.bottom + window.scrollY + 6}px`;
    popover.style.left = `${Math.min(rect.left + window.scrollX, window.innerWidth - 330)}px`;

    this.activePopover = popover;
  }

  setupGlobalPopoverDismiss() {
    document.addEventListener("click", (e) => {
      if (this.activePopover && !this.activePopover.contains(e.target)) {
        this.activePopover.remove();
        this.activePopover = null;
      }
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && this.activePopover) {
        this.activePopover.remove();
        this.activePopover = null;
      }
    });
  }
}
