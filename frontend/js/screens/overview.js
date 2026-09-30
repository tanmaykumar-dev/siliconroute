/**
 * SiliconRoute Modern SaaS Overview Screen Controller
 * Manages executive KPI stats, interactive scaling curve chart,
 * hardware routing copilot execution, and live decision feeds.
 */

import { getChartTheme, getDeviceChartProps } from "../charts/theme.js";
import { downloadDecisionsCsv } from "../export_csv.js";

export class OverviewScreen {
  constructor(apiClient, metricsSystem) {
    this.api = apiClient;
    this.metrics = metricsSystem;
    this.scalingChart = null;
    this.family = "mlp";
    this.batch = 1;
    this.isChartLoaded = false;
  }

  async init() {
    this.setupRouteForm();
    this.setupEvidenceButton();
    this.setupChartControls();
    this.setupAdditionalActions();
    await Promise.all([
      this.loadRecentDecisions(),
      this.loadScalingChart(),
    ]);
  }

  async onActivate() {
    await Promise.all([
      this.loadRecentDecisions(),
      this.loadScalingChart(),
    ]);
  }

  setupEvidenceButton() {
    const btn = document.getElementById("overview-evidence-btn");
    if (btn) {
      btn.addEventListener("click", () => {
        window.location.hash = "#/evidence";
      });
    }
  }

  setupAdditionalActions() {
    // "View all" decisions button
    document.getElementById("overview-view-all-decisions-btn")?.addEventListener("click", () => {
      window.location.hash = "#/results";
    });

    // "Route & verify" button
    document.getElementById("btn-overview-verify")?.addEventListener("click", () => {
      const routerScreen = window.SiliconRouteApp?.screens?.router;
      if (routerScreen && typeof routerScreen.handleRouteVerify === "function") {
        routerScreen.handleRouteVerify();
      } else {
        window.location.hash = "#/router";
      }
    });

    // "Export CSV" button
    document.getElementById("btn-overview-export-csv")?.addEventListener("click", () => {
      downloadDecisionsCsv(this.api);
    });
  }

  setupChartControls() {
    const selFam = document.getElementById("overview-chart-family-select");
    const selBatch = document.getElementById("overview-chart-batch-select");
    const btnToggle = document.getElementById("btn-toggle-overview-chart-table");

    if (selFam) {
      selFam.addEventListener("change", (e) => {
        this.family = e.target.value;
        this.loadScalingChart();
      });
    }

    if (selBatch) {
      selBatch.addEventListener("change", (e) => {
        this.batch = parseInt(e.target.value, 10);
        this.loadScalingChart();
      });
    }

    if (btnToggle) {
      btnToggle.addEventListener("click", () => {
        const wrap = document.getElementById("table-wrap-overview-scaling");
        if (!wrap) return;
        const isHidden = wrap.style.display === "none";
        wrap.style.display = isHidden ? "block" : "none";
        btnToggle.textContent = isHidden ? "Hide data" : "Show data";
      });
    }
  }

  async loadScalingChart() {
    const ctx = document.getElementById("chart-overview-scaling")?.getContext("2d");
    if (!ctx) return;

    try {
      const data = await this.api.fetchScalingData(this.family, this.batch);
      this.renderScalingChart(ctx, data);
      this.renderScalingTable(data);
    } catch (err) {
      console.error("Failed loading overview scaling chart:", err);
    }
  }

  renderScalingChart(ctx, chartData) {
    if (this.scalingChart) {
      this.scalingChart.destroy();
    }

    const t = getChartTheme();
    const datasets = [];

    // Measured points & lines
    for (const [devKey, runs] of Object.entries(chartData.runs || {})) {
      const p = getDeviceChartProps(devKey);
      const points = runs.map(r => ({
        x: r.param_count || r.weight_bytes || 1,
        y: r.median_ms,
        modelName: r.model_name,
      })).sort((a, b) => a.x - b.x);

      datasets.push({
        label: p.label,
        data: points,
        borderColor: p.color,
        backgroundColor: p.color,
        pointStyle: p.pointStyle,
        pointRadius: 5,
        pointHoverRadius: 7,
        borderWidth: 2,
        tension: 0.15,
        showLine: true,
      });
    }

    this.scalingChart = new Chart(ctx, {
      type: "scatter",
      data: { datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: {
          duration: 400,
          easing: "easeOutQuart",
        },
        interaction: {
          mode: "nearest",
          intersect: false,
        },
        scales: {
          x: {
            type: "logarithmic",
            title: {
              display: true,
              text: "Model Size (Parameters / Bytes)",
              color: t.ink2,
              font: { size: 11, weight: "600" },
            },
            grid: { color: t.rule },
            ticks: { color: t.ink3, font: { size: 10 } },
          },
          y: {
            type: "logarithmic",
            title: {
              display: true,
              text: "Median Latency (ms)",
              color: t.ink2,
              font: { size: 11, weight: "600" },
            },
            grid: { color: t.rule },
            ticks: { color: t.ink3, font: { size: 10 } },
          },
        },
        plugins: {
          legend: {
            position: "top",
            labels: {
              usePointStyle: true,
              boxWidth: 8,
              font: { size: 12, weight: "600" },
              color: t.ink,
            },
          },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const raw = ctx.raw;
                return `${ctx.dataset.label}: ${raw.y != null ? raw.y.toFixed(3) : 'n/a'} ms (${raw.modelName || 'model'})`;
              },
            },
          },
        },
      },
    });
  }

  renderScalingTable(chartData) {
    const tbody = document.getElementById("tbody-overview-scaling");
    if (!tbody || !chartData.runs) return;

    const cpuRuns = chartData.runs["cpu"] || [];
    const igpuRuns = chartData.runs["dml:0"] || [];
    const dgpuRuns = chartData.runs["dml:1"] || [];

    const map = new Map();
    cpuRuns.forEach(r => map.set(r.model_name, { name: r.model_name, params: r.param_count, cpu: r.median_ms }));
    igpuRuns.forEach(r => {
      const e = map.get(r.model_name) || { name: r.model_name, params: r.param_count };
      e.igpu = r.median_ms;
      map.set(r.model_name, e);
    });
    dgpuRuns.forEach(r => {
      const e = map.get(r.model_name) || { name: r.model_name, params: r.param_count };
      e.dgpu = r.median_ms;
      map.set(r.model_name, e);
    });

    tbody.innerHTML = Array.from(map.values()).map(row => `
      <tr>
        <td><strong>${row.name}</strong></td>
        <td>${row.params ? row.params.toLocaleString() : "n/a"}</td>
        <td class="num">${row.cpu != null ? row.cpu.toFixed(3) : "n/a"}</td>
        <td class="num">${row.igpu != null ? row.igpu.toFixed(3) : "n/a"}</td>
        <td class="num">${row.dgpu != null ? row.dgpu.toFixed(3) : "n/a"}</td>
      </tr>
    `).join("");
  }

  setupRouteForm() {
    const form = document.getElementById("overview-route-form");
    if (!form) return;

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const modelKey = document.getElementById("overview-model-select")?.value || "mlp_256w_4l";
      const batch = parseInt(document.getElementById("overview-batch-select")?.value || "1", 10);
      const workload = document.getElementById("overview-workload-select")?.value || "sustained";
      const goal = document.getElementById("overview-goal-select")?.value || "fastest";

      try {
        const models = await this.api.getModels();
        const matched = models.find(m => m.name === modelKey) || models[0];
        const modelId = matched ? matched.id : 1;

        const decision = await this.api.routeModel({
          ai_model_id: modelId,
          batch,
          workload,
          mode: goal,
        });

        // Notify socket strip & global listeners
        window.dispatchEvent(new CustomEvent("routedecision", { detail: decision }));
        await this.loadRecentDecisions();
      } catch (err) {
        console.error("Failed routing task from overview:", err);
      }
    });
  }

  async loadRecentDecisions() {
    const tbody = document.getElementById("tbody-overview-recent-decisions");
    if (!tbody) return;

    try {
      const decisions = await this.api.getDecisions(6);
      if (!decisions || !decisions.length) {
        tbody.innerHTML = `
          <tr>
            <td colspan="4" style="text-align: center; color: var(--ink-3); padding: 16px;">No decisions yet. Route a task to see it here.</td>
          </tr>
        `;
        return;
      }

      tbody.innerHTML = decisions.slice(0, 5).map(d => {
        const timeMs = d.predicted_latency_ms != null ? `${d.predicted_latency_ms.toFixed(3)} ms` : "n/a";
        const modelName = d.model_name || (d.model ? d.model.name : `Model #${d.ai_model_id}`);
        const chipLabel = d.chosen_device_key || `Device #${d.chosen_device_id}`;
        const workload = d.workload || "sustained";

        return `
          <tr>
            <td><strong>${modelName}</strong> · b${d.batch}</td>
            <td><span class="tag tag-neutral">${workload}</span></td>
            <td><span class="tag tag-verified">${chipLabel}</span></td>
            <td class="num">${timeMs}</td>
          </tr>
        `;
      }).join("");
    } catch (err) {
      console.error("Failed loading recent decisions for overview:", err);
    }
  }
}
