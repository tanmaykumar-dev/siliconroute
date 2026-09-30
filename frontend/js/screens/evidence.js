/**
 * SiliconRoute Design Spec v2 — Evidence Screen (Section 6.6)
 * Frozen database verification, searchable metric browser, raw samples browser,
 * identity audit documentation, and reproduction instructions with copy buttons.
 */

export class EvidenceScreen {
  constructor(apiClient, rawSamplesModal) {
    this.api = apiClient;
    this.modal = rawSamplesModal;
    this.metricsData = null;
    this.allMetrics = [];
    this.isLoaded = false;
  }

  async init() {
    this.setupSearch();
    this.setupReproduceButtons();
    this.setupRawSamplesBrowser();
  }

  async onActivate() {
    if (!this.isLoaded) {
      await this.loadEvidence();
      this.isLoaded = true;
    }
  }

  async loadEvidence() {
    try {
      this.metricsData = await this.api.fetchPublishedMetrics();
      this.renderMetadata(this.metricsData.metadata || {});
      this.setupMetricsList(this.metricsData.metrics || {});
      await this.populateBrowserDropdowns();
    } catch (err) {
      console.error("Failed to load evidence metrics:", err);
    }
  }

  renderMetadata(meta) {
    const elSha = document.getElementById("evidence-db-sha256");
    const elSize = document.getElementById("evidence-db-size");
    const elCommit = document.getElementById("evidence-git-commit");
    const elDate = document.getElementById("evidence-manifest-date");

    if (elSha) elSha.textContent = meta.database_sha256 || "—";
    if (elSize) {
      const bytes = meta.database_size_bytes || 0;
      elSize.textContent = `${(bytes / 1024).toFixed(1)} KB (${bytes.toLocaleString()} bytes)`;
    }
    if (elCommit) {
      const commit = meta.git_commit || "—";
      elCommit.textContent = commit.slice(0, 10);
      elCommit.title = commit;
    }
    if (elDate) {
      elDate.textContent = meta.date ? new Date(meta.date).toLocaleString() : "—";
    }
  }

  setupMetricsList(metricsObj) {
    this.allMetrics = Object.entries(metricsObj).map(([key, item]) => ({
      key,
      ...item,
    }));
    this.renderMetricsTable(this.allMetrics);
  }

  setupSearch() {
    const input = document.getElementById("evidence-metric-search");
    if (!input) return;

    input.addEventListener("input", (e) => {
      const q = e.target.value.toLowerCase().trim();
      if (!q) {
        this.renderMetricsTable(this.allMetrics);
        return;
      }
      const filtered = this.allMetrics.filter((m) =>
        m.key.toLowerCase().includes(q) ||
        (m.description && m.description.toLowerCase().includes(q)) ||
        (m.method && m.method.toLowerCase().includes(q))
      );
      this.renderMetricsTable(filtered);
    });
  }

  renderMetricsTable(items) {
    const tbody = document.getElementById("evidence-metrics-tbody");
    if (!tbody) return;

    if (!items.length) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding:var(--space-6); color:var(--ink-3);">No matching metrics found.</td></tr>`;
      return;
    }

    // Render up to 100 items to keep DOM performant
    const slice = items.slice(0, 100);
    tbody.innerHTML = slice.map((m) => {
      let valDisplay = m.value;
      if (typeof m.value === "number") {
        valDisplay = Number.isInteger(m.value) ? m.value.toLocaleString() : m.value.toFixed(4);
      }
      const sqlOrMethod = m.sql ? `<code class="td-mono">${this.escapeHtml(m.sql)}</code>` : `<span class="td-mono">${this.escapeHtml(m.method || "—")}</span>`;

      return `
        <tr>
          <td class="td-mono" style="font-size:12px; color:var(--ink); font-weight:500;">${this.escapeHtml(m.key)}</td>
          <td class="td-num td-mono" style="font-size:12.5px; font-weight:600;">${valDisplay}</td>
          <td style="font-size:12px; color:var(--ink-2);">${this.escapeHtml(m.unit || "")}</td>
          <td style="font-size:11.5px; max-width:320px; overflow:hidden; text-overflow:ellipsis;">${sqlOrMethod}</td>
          <td style="font-size:12px; color:var(--ink-2);">${this.escapeHtml(m.description || "")}</td>
        </tr>
      `;
    }).join("");
  }

  async populateBrowserDropdowns() {
    try {
      const [models, devices] = await Promise.all([
        this.api.fetchModels(),
        this.api.fetchDevices(),
      ]);

      const selModel = document.getElementById("evidence-filter-model");
      const selDevice = document.getElementById("evidence-filter-device");

      if (selModel && Array.isArray(models)) {
        selModel.innerHTML = `<option value="">All models</option>` +
          models.map(m => `<option value="${m.id}">${m.name} (${m.family})</option>`).join("");
      }

      if (selDevice && Array.isArray(devices)) {
        selDevice.innerHTML = `<option value="">All devices</option>` +
          devices.map(d => `<option value="${d.id}">${d.label} (${d.kind})</option>`).join("");
      }
    } catch (err) {
      console.warn("Could not populate evidence filter dropdowns:", err);
    }
  }

  setupRawSamplesBrowser() {
    const btnSearch = document.getElementById("evidence-search-runs-btn");
    if (!btnSearch) return;

    btnSearch.addEventListener("click", async () => {
      const modelId = document.getElementById("evidence-filter-model")?.value || null;
      const deviceId = document.getElementById("evidence-filter-device")?.value || null;
      const batch = document.getElementById("evidence-filter-batch")?.value || null;

      let url = "/api/runs?limit=50";
      if (modelId) url += `&model_id=${modelId}`;
      if (deviceId) url += `&device_id=${deviceId}`;
      if (batch) url += `&batch=${batch}`;

      try {
        const runs = await this.api.get(url);
        this.renderRunsTable(runs);
      } catch (err) {
        console.error("Failed to fetch runs:", err);
      }
    });
  }

  renderRunsTable(runs) {
    const tbody = document.getElementById("evidence-runs-tbody");
    if (!tbody) return;

    if (!runs.length) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:var(--space-4); color:var(--ink-3);">No matching benchmark runs.</td></tr>`;
      return;
    }

    tbody.innerHTML = runs.map(r => `
      <tr>
        <td class="td-num td-mono">#${r.id}</td>
        <td>${this.escapeHtml(r.provider_used)}</td>
        <td class="td-num">${r.batch}</td>
        <td class="td-num td-mono" style="font-weight:600;">${r.median_ms.toFixed(3)} ms</td>
        <td class="td-num td-mono">${(r.spread * 100).toFixed(1)}%</td>
        <td class="td-num td-mono">${(r.cv * 100).toFixed(1)}%</td>
        <td style="text-align:right;">
          <button class="btn btn-secondary btn-sm run-inspect-btn" data-run-id="${r.id}">
            Inspect samples
          </button>
        </td>
      </tr>
    `).join("");

    tbody.querySelectorAll(".run-inspect-btn").forEach(btn => {
      btn.addEventListener("click", (e) => {
        const runId = parseInt(e.currentTarget.getAttribute("data-run-id"), 10);
        if (this.modal) this.modal.open(runId);
      });
    });
  }

  setupReproduceButtons() {
    const copyBtns = document.querySelectorAll(".code-copy-btn");
    copyBtns.forEach(btn => {
      btn.addEventListener("click", () => {
        const codeId = btn.getAttribute("data-code-target");
        const codeEl = document.getElementById(codeId);
        if (!codeEl) return;

        const text = codeEl.innerText.trim();
        navigator.clipboard.writeText(text).then(() => {
          const original = btn.textContent;
          btn.textContent = "Copied";
          setTimeout(() => {
            btn.textContent = original;
          }, 1500);
        }).catch(err => console.error("Clipboard copy failed:", err));
      });
    });
  }

  escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
}
