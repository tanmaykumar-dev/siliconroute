/**
 * SiliconRoute Design Spec v3: "Red Bench" Analysis Screen (Section 6.3)
 * Scaling chart (log-log) with family/batch selectors; measured points use chip marks,
 * fitted curves dashed. Clicking a point opens the raw-samples modal.
 * Crossover markers labelled "fitted estimate" with measured neighbours listed.
 * Chip model table ("effective" compute, "n/a" where a form has no term).
 * Variability and wake/cold ratios with median, range and n.
 */

import { getChartTheme, getDeviceChartProps } from "../charts/theme.js";

export class AnalysisScreen {
  constructor(apiClient, rawSamplesModal) {
    this.api = apiClient;
    this.modal = rawSamplesModal;
    this.scalingChart = null;
    this.family = "mlp";
    this.batch = 1;
    this.isLoaded = false;
  }

  async init() {
    this.setupControls();
  }

  async onActivate() {
    if (!this.isLoaded) {
      await this.loadAll();
      this.isLoaded = true;
    }
  }

  setupControls() {
    const selFam = document.getElementById("analysis-family-select");
    const selBatch = document.getElementById("analysis-batch-select");

    if (selFam) {
      selFam.addEventListener("change", (e) => {
        this.family = e.target.value;
        this.loadScalingCurves();
      });
    }

    if (selBatch) {
      selBatch.addEventListener("change", (e) => {
        this.batch = parseInt(e.target.value, 10);
        this.loadScalingCurves();
      });
    }

    const toggleBtn = document.getElementById("analysis-chart-table-toggle");
    if (toggleBtn) {
      toggleBtn.addEventListener("click", () => {
        const tbl = document.getElementById("analysis-scaling-data-table");
        if (tbl) {
          const isHidden = tbl.style.display === "none";
          tbl.style.display = isHidden ? "block" : "none";
          toggleBtn.textContent = isHidden ? "Hide data table" : "Show data table";
        }
      });
    }
  }

  async loadAll() {
    await Promise.all([
      this.loadScalingCurves(),
      this.loadCrossover(),
      this.loadFitsTable(),
      this.loadVariabilityTable(),
      this.loadWakeColdTable(),
      this.loadPhysicsNotes(),
    ]);
  }

  async loadScalingCurves() {
    try {
      const data = await this.api.fetchScalingData(this.family, this.batch);
      this.renderScalingChart(data);
      this.renderScalingTable(data);
    } catch (err) {
      console.error("Failed loading scaling curves:", err);
    }
  }

  renderScalingChart(chartData) {
    const ctx = document.getElementById("chart-analysis-scaling")?.getContext("2d");
    if (!ctx) return;

    if (this.scalingChart) {
      this.scalingChart.destroy();
    }

    const datasets = [];

    // 1. Measured scatter points (solid)
    for (const [devKey, runs] of Object.entries(chartData.runs || {})) {
      const p = getDeviceChartProps(devKey);
      const points = runs.map(r => ({
        x: r.param_count || r.weight_bytes || 1,
        y: r.median_ms,
        runId: r.id,
        raw: r,
      }));

      datasets.push({
        label: `${p.label} (Measured)`,
        data: points,
        backgroundColor: p.color,
        borderColor: p.color,
        pointStyle: p.pointStyle,
        pointRadius: 6,
        pointHoverRadius: 8,
        showLine: false,
      });
    }

    // 2. Fitted theoretical curves (dashed)
    for (const [devKey, curve] of Object.entries(chartData.curves || {})) {
      const p = getDeviceChartProps(devKey);
      datasets.push({
        label: `${p.label} (Fitted)`,
        data: curve.map(pt => ({ x: pt.param_count, y: pt.latency_ms })),
        borderColor: p.color,
        borderDash: [5, 4],
        borderWidth: 1.5,
        fill: false,
        pointRadius: 0,
        showLine: true,
      });
    }

    this.scalingChart = new Chart(ctx, {
      type: "scatter",
      data: { datasets },
      options: {
        animation: false,
        responsive: true,
        maintainAspectRatio: false,
        onClick: (evt, elements) => {
          if (!elements.length) return;
          const el = elements[0];
          const ds = datasets[el.datasetIndex];
          const pt = ds.data[el.index];
          if (pt && pt.runId && this.modal) {
            this.modal.open(pt.runId);
          }
        },
        scales: {
          x: {
            type: "logarithmic",
            title: { display: true, text: "Model parameters (log scale)" },
            ticks: {
              callback: (val) => Number(val).toLocaleString(),
              font: { family: "'JetBrains Mono', monospace", size: 10 },
            },
          },
          y: {
            type: "logarithmic",
            title: { display: true, text: "Latency (ms, log scale)" },
            ticks: {
              callback: (val) => Number(val).toLocaleString(),
              font: { family: "'JetBrains Mono', monospace", size: 10 },
            },
          },
        },
        plugins: {
          tooltip: {
            callbacks: {
              label: (item) => {
                const pt = item.raw;
                if (pt.runId) {
                  return `${item.dataset.label}: ${pt.y.toFixed(3)} ms (Run #${pt.runId}, click to inspect)`;
                }
                return `${item.dataset.label}: ${pt.y.toFixed(3)} ms (fitted estimate)`;
              },
            },
          },
        },
      },
    });
  }

  renderScalingTable(chartData) {
    const tbody = document.getElementById("tbody-analysis-scaling-table");
    if (!tbody) return;

    const rows = [];
    for (const [devKey, runs] of Object.entries(chartData.runs || {})) {
      runs.forEach(r => {
        rows.push(`
          <tr>
            <td><strong>${devKey.toUpperCase()}</strong></td>
            <td>Run #${r.id}</td>
            <td class="num">${(r.param_count || 0).toLocaleString()}</td>
            <td class="num">${r.median_ms.toFixed(3)} ms</td>
            <td><button type="button" class="btn-text" data-test="show-raw-samples" onclick="window.SiliconRouteApp?.modal?.open(${r.id})">Inspect run</button></td>
          </tr>
        `);
      });
    }

    tbody.innerHTML = rows.length ? rows.join("") : `<tr><td colspan="5" style="text-align:center;">No measured runs for this selection.</td></tr>`;
  }

  async loadCrossover() {
    const container = document.getElementById("crossover-summary-container");
    if (!container) return;

    try {
      const crossovers = await this.api.fetchCrossoverData();
      if (!Array.isArray(crossovers) || !crossovers.length) {
        container.innerHTML = `<span class="tag">no crossover detected in measured envelope</span>`;
        return;
      }

      const matching = crossovers.filter(c => c.family === this.family && c.batch === this.batch);
      const displayItems = matching.length ? matching : crossovers.slice(0, 3);

      container.innerHTML = displayItems.map(pt => {
        const co = pt.crossover || {};
        const params = co.params ? `${Number(co.params).toLocaleString()} params` : "n/a";
        const lat = co.pred_a_ms ? `~${co.pred_a_ms.toFixed(3)} ms` : "";

        return `
          <div style="padding:var(--space-12); background:var(--sheet); border:1px solid var(--rule); margin-bottom:var(--space-8);">
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <span style="font-weight:600;">${pt.dev_a.toUpperCase()} vs ${pt.dev_b.toUpperCase()} (${(pt.family || "MLP").toUpperCase()} Batch ${pt.batch})</span>
              <span class="tag">fitted estimate</span>
            </div>
            <div style="font-size:13px; margin-top:4px;">
              Analytical Crossover: <strong style="font-family:var(--font-mono);">${params}</strong> ${lat}
            </div>
            <div style="font-size:12px; color:var(--ink-2); margin-top:2px;">
              ${pt.summary || "Measured: CPU faster below crossover; GPU faster above."}
            </div>
          </div>
        `;
      }).join("");
    } catch (err) {
      console.error("Failed loading crossover:", err);
    }
  }

  async loadFitsTable() {
    const tbody = document.getElementById("analysis-fits-table-body");
    if (!tbody) return;

    try {
      const fits = await this.api.fetchFits();
      const devLabels = {
        1: { name: "CPU", sub: "Host Processor" },
        2: { name: "Radeon 610M", sub: "AMD iGPU" },
        3: { name: "RTX 5070", sub: "NVIDIA Laptop GPU" },
      };

      tbody.innerHTML = (fits || []).map(f => {
        const d = devLabels[f.device_id] || { name: `Device ${f.device_id}`, sub: "" };
        const formStr = (f.model_form || f.form || "F1").toUpperCase();
        const t0Str = f.t0_ms !== null && f.t0_ms !== undefined ? `${f.t0_ms.toFixed(4)} ms` : "n/a";
        const gflopsStr = f.compute_gflops !== null && f.compute_gflops !== undefined ? `${f.compute_gflops.toFixed(1)} GFLOP/s` : "n/a";
        const dramStr = f.bandwidth_dram_gb_s !== null && f.bandwidth_dram_gb_s !== undefined ? `${f.bandwidth_dram_gb_s.toFixed(1)} GB/s` : "n/a";
        const sramStr = f.bandwidth_gb_s !== null && f.bandwidth_gb_s !== undefined ? `${f.bandwidth_gb_s.toFixed(1)} GB/s` : "n/a";
        const mapeStr = f.loo_mape_pct !== null && f.loo_mape_pct !== undefined ? `${f.loo_mape_pct.toFixed(2)}%` : "n/a";

        return `
          <tr>
            <td><strong>${d.name}</strong> <span style="font-size:11px; color:var(--ink-3);">${d.sub}</span></td>
            <td><span class="tag">${formStr}</span></td>
            <td class="num">${t0Str}</td>
            <td class="num">${gflopsStr}</td>
            <td class="num">${dramStr}</td>
            <td class="num">${sramStr}</td>
            <td class="num" style="font-weight:600;">${mapeStr}</td>
          </tr>
        `;
      }).join("");
    } catch (err) {
      console.error("Failed loading fits:", err);
    }
  }

  async loadVariabilityTable() {
    const tbody = document.getElementById("analysis-variability-table-body");
    if (!tbody) return;

    try {
      const data = await this.api.fetchSessionVariability();
      const items = (data.details || data.configs || []).slice(0, 10);

      tbody.innerHTML = items.map(v => {
        const diff = v.diff_pct || 0;
        const tagText = diff > 20 ? "volatile" : "verified";

        return `
          <tr>
            <td><strong>${(v.device_key || "").toUpperCase()}</strong></td>
            <td>${v.model_name || ""}</td>
            <td class="num">B=${v.batch || 1}</td>
            <td class="num">${v.session_count || 1}</td>
            <td class="num">${(v.min_median_ms || 0).toFixed(3)} ms</td>
            <td class="num">${(v.max_median_ms || 0).toFixed(3)} ms</td>
            <td class="num" style="font-weight:600;">${diff.toFixed(1)}%</td>
            <td><span class="tag">${tagText}</span></td>
          </tr>
        `;
      }).join("");
    } catch (err) {
      console.error("Failed loading variability:", err);
    }
  }

  async loadWakeColdTable() {
    const tbody = document.getElementById("analysis-wake-cold-table-body");
    if (!tbody) return;

    try {
      const data = await this.api.fetchWakeColdSummary();
      const list = Array.isArray(data) ? data : (data.summary || []);

      tbody.innerHTML = list.map(w => {
        const firstRun = w.median_first_run_ms !== null && w.median_first_run_ms !== undefined ? `${w.median_first_run_ms.toFixed(3)} ms` : "n/a";
        const wakePen = w.median_wake_penalty_ms !== null && w.median_wake_penalty_ms !== undefined ? `+${w.median_wake_penalty_ms.toFixed(3)} ms` : "n/a";

        return `
          <tr>
            <td><strong>${(w.device_key || "").toUpperCase()}</strong></td>
            <td>${w.device_label || ""}</td>
            <td class="num">${w.sample_count || 0}</td>
            <td class="num">${firstRun}</td>
            <td class="num" style="font-weight:600;">${wakePen}</td>
          </tr>
        `;
      }).join("");
    } catch (err) {
      console.error("Failed loading wake cold summary:", err);
    }
  }

  async loadPhysicsNotes() {
    const container = document.getElementById("analysis-physics-notes-container");
    if (!container) return;

    try {
      const data = await this.api.fetchPhysicsNotes();
      container.innerHTML = (data.runs || []).slice(0, 5).map(r => {
        return `
          <div style="padding:var(--space-12); background:var(--sheet); border:1px solid var(--rule); margin-bottom:var(--space-8);">
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <span><strong>Run #${r.run_id}</strong>: ${r.model_name} on ${(r.device_key || "").toUpperCase()} (Batch ${r.batch})</span>
              <span class="tag">hypothesis</span>
            </div>
            <div style="font-size:13px; color:var(--ink); margin-top:4px;">
              Measured: ${(r.median_ms || 0).toFixed(3)} ms | Effective: ${(r.implied_gflops || 0).toFixed(1)} GFLOP/s vs Datasheet: ${r.datasheet_peak_gflops || "n/a"} GFLOP/s
            </div>
            <div style="font-size:12px; color:var(--ink-2); margin-top:2px;">
              ${r.physics_note || "Algorithmic Winograd minimal filtering convolution speedup."}
            </div>
          </div>
        `;
      }).join("");
    } catch (err) {
      console.error("Failed loading physics notes:", err);
    }
  }
}
