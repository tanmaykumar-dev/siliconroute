/**
 * SiliconRoute Design Spec v3: Metrics & Evidence System (.metric)
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
      return `${val.toFixed(1)}x`;
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
    btn.className = "btn-text evidence-btn";
    btn.setAttribute("aria-label", `Show evidence for ${key}`);
    btn.setAttribute("data-test", "evidence-popover-btn");
    btn.textContent = "Show evidence";

    const trigger = (e) => {
      e.stopPropagation();
      this.togglePopover(btn, key, metric);
    };

    btn.addEventListener("click", trigger);
    btn.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        trigger(e);
      }
    });

    return btn;
  }

  togglePopover(anchorBtn, key, metric) {
    if (this.activePopover) {
      const wasSame = this.activePopover.dataset.key === key;
      this.activePopover.remove();
      this.activePopover = null;
      if (wasSame) return;
    }

    const popover = document.createElement("div");
    popover.className = "evidence-popover open";
    popover.dataset.key = key;
    popover.setAttribute("role", "dialog");
    popover.setAttribute("aria-label", `Evidence for ${key}`);

    const sqlBlock = metric.sql ? `
      <div class="evidence-row" style="margin-top: 8px;">
        <span class="evidence-row-label">Database SQL:</span>
        <pre class="evidence-sql" style="background:var(--paper); padding:6px; border:1px solid var(--rule); font-family:var(--font-mono); font-size:11px; overflow-x:auto; margin-top:4px;">${metric.sql}</pre>
      </div>` : "";

    const idBlock = metric.ids || metric.run_ids || metric.decision_ids ? `
      <div class="evidence-row" style="margin-top: 6px;">
        <span class="evidence-row-label">Source IDs:</span>
        <span style="font-family:var(--font-mono); font-size:11px;">${metric.ids || metric.run_ids || metric.decision_ids}</span>
      </div>` : "";

    popover.innerHTML = `
      <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:8px; border-bottom:1px solid var(--rule); padding-bottom:4px;">
        <span style="font-family:var(--font-mono); font-size:12px; font-weight:700; color:var(--ink);">${key}</span>
        <button type="button" class="popover-close-btn" data-test="btn-close-popover" style="border:none; background:none; cursor:pointer; font-size:16px; line-height:1; color:var(--ink-2);" aria-label="Close evidence">×</button>
      </div>
      <div class="evidence-row" style="margin-bottom: 6px;">
        <span class="evidence-row-label">Published Value:</span>
        <span style="font-family:var(--font-mono); font-weight:700; color:var(--ink);">${metric.value} ${metric.unit || ""}</span>
      </div>
      <div class="evidence-row" style="margin-bottom: 6px;">
        <span class="evidence-row-label">Description:</span>
        <span style="color:var(--ink-2); font-size:12px; line-height:1.4;">${metric.description || "Empirical measurement from SQLite database."}</span>
      </div>
      <div class="evidence-row" style="margin-bottom: 6px;">
        <span class="evidence-row-label">Calculation Method:</span>
        <span style="font-size:12px; color:var(--red-deep); font-weight:600;">${metric.method || "Direct SQL query"}</span>
      </div>
      ${sqlBlock}
      ${idBlock}
    `;

    const closeBtn = popover.querySelector(".popover-close-btn");
    if (closeBtn) {
      closeBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        popover.remove();
        this.activePopover = null;
        anchorBtn.focus();
      });
    }

    document.body.appendChild(popover);
    const rect = anchorBtn.getBoundingClientRect();
    popover.style.position = "absolute";
    popover.style.top = `${rect.bottom + window.scrollY + 6}px`;
    popover.style.left = `${Math.min(rect.left + window.scrollX, window.innerWidth - 380)}px`;
    popover.style.zIndex = "1000";

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
