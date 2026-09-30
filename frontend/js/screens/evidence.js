/**
 * SiliconRoute Design Spec v3: "Red Bench" Evidence Screen (Section 6.6)
 * Frozen database verification, manifest metadata, searchable metric browser,
 * raw samples browser, identity audit, and reproduction commands with Copy buttons.
 */

import { toast } from "../components/toast.js";

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
      await this.loadIdentityAudit();
    } catch (err) {
      console.error("Failed to load evidence metrics:", err);
    }
  }

  renderMetadata(meta) {
    const elSha = document.getElementById("evidence-db-sha256");
    const elSize = document.getElementById("evidence-db-size");
    const elCommit = document.getElementById("evidence-git-commit");
    const elDate = document.getElementById("evidence-manifest-date");

    if (elSha) elSha.textContent = meta.database_sha256 || "n/a";
    if (elSize) {
      const bytes = meta.database_size_bytes || 0;
      elSize.textContent = `${(bytes / 1024).toFixed(1)} KB (${bytes.toLocaleString()} bytes)`;
    }
    if (elCommit) {
      const commit = meta.git_commit || "n/a";
      elCommit.textContent = commit.slice(0, 10);
      elCommit.title = commit;
    }
    if (elDate) {
      elDate.textContent = meta.date ? new Date(meta.date).toISOString().replace("T", " ").slice(0, 19) + " UTC" : "n/a";
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
      tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding:var(--space-24); color:var(--ink-3);">No matching metrics found.</td></tr>`;
      return;
    }

    const slice = items.slice(0, 100);
    tbody.innerHTML = slice.map((m) => {
      let valDisplay = m.value;
      if (typeof m.value === "number") {
        valDisplay = Number.isInteger(m.value) ? m.value.toLocaleString() : m.value.toFixed(4);
      }
      const sqlOrMethod = m.sql ? `<code style="font-family:var(--font-mono); font-size:11px;">${this.escapeHtml(m.sql)}</code>` : `<span style="font-family:var(--font-mono); font-size:11px;">${this.escapeHtml(m.method || "n/a")}</span>`;

      return `
        <tr>
          <td style="font-family:var(--font-mono); font-size:12px; font-weight:600;">${this.escapeHtml(m.key)}</td>
          <td class="num">${valDisplay}</td>
          <td>${this.escapeHtml(m.unit || "")}</td>
          <td style="font-size:12px; max-width:320px; overflow:hidden; text-overflow:ellipsis;">${sqlOrMethod}</td>
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
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:var(--space-16); color:var(--ink-3);">No matching benchmark runs.</td></tr>`;
      return;
    }

    tbody.innerHTML = runs.map(r => `
      <tr>
        <td class="num">#${r.id}</td>
        <td>${this.escapeHtml(r.provider_used)}</td>
        <td class="num">${r.batch}</td>
        <td class="num" style="font-weight:600;">${r.median_ms.toFixed(3)} ms</td>
        <td class="num">${(r.spread * 100).toFixed(1)}%</td>
        <td class="num">${(r.cv * 100).toFixed(1)}%</td>
        <td style="text-align:right;">
          <button type="button" class="btn btn-secondary btn-sm run-inspect-btn" data-run-id="${r.id}" data-test="show-raw-samples">
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

  async loadIdentityAudit() {
    const tbody = document.getElementById("evidence-identity-tbody");
    if (!tbody) return;

    try {
      const suspects = await this.api.fetchIdentitySuspects();
      if (!suspects || !suspects.length) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; color:var(--ink-3); padding:var(--space-16);">No suspect runs flagged in database.</td></tr>`;
        return;
      }

      tbody.innerHTML = suspects.map(s => `
        <tr>
          <td class="num">#${s.id}</td>
          <td>${this.escapeHtml(s.device_key)}</td>
          <td><span class="tag">identity swap</span></td>
          <td>${this.escapeHtml(s.physics_note || "DirectML DXGI adapter index swap")}</td>
          <td style="text-align:right;"><button type="button" class="btn-text" data-test="show-raw-samples" onclick="window.SiliconRouteApp?.modal?.open(${s.id})">Inspect</button></td>
        </tr>
      `).join("");
    } catch (err) {
      console.warn("Could not load identity audit:", err);
    }
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
          toast.show("Copied command to clipboard.");
          setTimeout(() => {
            btn.textContent = original;
          }, 2000);
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
