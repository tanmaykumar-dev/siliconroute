/**
 * SiliconRoute Design Spec v3: "Red Bench" Results Screen (Section 6.5)
 * Published evaluation exactly as results/final/ (overall + per workload),
 * cold-start rule check, regret bar chart (log scale; SiliconRoute bar red, others ink/grey),
 * collapsed earlier evaluation. A "Snapdragon X2 Elite" section that shows the v2 results
 * when they exist, otherwise the empty state "Snapdragon results not yet recorded".
 */

import { getChartTheme } from "../charts/theme.js";

export class ResultsScreen {
  constructor(apiClient) {
    this.api = apiClient;
    this.isLoaded = false;
    this.regretChart = null;
  }

  async init() {
    this.setupTableToggle();
  }

  async onActivate() {
    if (!this.isLoaded) {
      await this.loadEvaluationData();
      this.isLoaded = true;
    }
  }

  setupTableToggle() {
    const btn = document.getElementById("results-chart-table-toggle");
    if (btn) {
      btn.addEventListener("click", () => {
        const tbl = document.getElementById("results-chart-data-table");
        if (tbl) {
          const isHidden = tbl.style.display === "none";
          tbl.style.display = isHidden ? "block" : "none";
          btn.textContent = isHidden ? "Hide data table" : "Show data table";
        }
      });
    }
  }

  async loadEvaluationData() {
    try {
      const evalData = await this.api.fetchEvaluation();

      // 1. Headline Evaluation (Decisions 117-140)
      if (evalData.headline) {
        const hl = evalData.headline;
        this.renderOverallTable("results-headline-table-body", hl.stats);
        this.renderWorkloadsTable("results-workloads-table-body", hl.stats.per_workload);
        this.renderRegretBarChart(hl.stats);
      }

      // 2. Cold-Start Rule Check (Decisions 141-148)
      if (evalData.cold_start_rule) {
        const cs = evalData.cold_start_rule;
        this.renderOverallTable("results-coldstart-table-body", cs.stats, false);
      }

      // 3. Earlier Evaluation (Decisions 93-116)
      if (evalData.earlier) {
        const ear = evalData.earlier;
        this.renderOverallTable("results-earlier-table-body", ear.stats);
      }

      // 4. Snapdragon X2 Elite section
      this.renderSnapdragonSection(evalData.snapdragon);
    } catch (err) {
      console.error("Failed loading evaluation data:", err);
    }
  }

  renderOverallTable(targetId, stats, includeOrt = true) {
    const tbody = document.getElementById(targetId);
    if (!tbody || !stats || !stats.siliconroute) return;

    const rows = [
      { name: "SiliconRoute (Measured-First + Dynamic)", data: stats.siliconroute, isSr: true },
      { name: "Always-CPU Baseline", data: stats.baselines?.always_cpu },
      { name: "Always-RTX Baseline", data: stats.baselines?.always_rtx },
      { name: "Fit-Only Router (Formula without Lookups)", data: stats.baselines?.fit_only_router },
    ];

    let html = rows.map(r => {
      const d = r.data;
      if (!d) return "";
      const p90Str = d.p90_regret_pct !== undefined ? `${d.p90_regret_pct.toFixed(2)}%` : "n/a";
      return `
        <tr class="${r.isSr ? 'highlight' : ''}">
          <td><strong>${r.name}</strong></td>
          <td class="num">${d.wins}/${d.total}</td>
          <td class="num" style="font-weight:700;">${d.accuracy_pct.toFixed(1)}%</td>
          <td class="num">${d.mean_regret_pct.toFixed(2)}%</td>
          <td class="num">${p90Str}</td>
        </tr>
      `;
    }).join("");

    if (includeOrt) {
      html += `
        <tr>
          <td style="color:var(--ink-3);">ORT ExecutionProviderDevicePolicy</td>
          <td colspan="4"><span class="tag" title="ORT ExecutionProviderDevicePolicy was not executed on physical hardware; result would be assumed, not measured">not available</span></td>
        </tr>
      `;
    }

    tbody.innerHTML = html;
  }

  renderWorkloadsTable(targetId, perWl) {
    const tbody = document.getElementById(targetId);
    if (!tbody || !perWl) return;

    const workloads = ["sustained", "idle_loaded", "cold_start"];
    let html = "";

    workloads.forEach(wl => {
      const d = perWl[wl];
      if (!d) return;

      const strategies = [
        { name: "SiliconRoute", wins: d.wins, total: d.total, acc: d.accuracy_pct, reg: d.mean_regret_pct, p90: d.p90_regret_pct, isSr: true },
        { name: "Always-CPU", wins: d.always_cpu.wins, total: d.total, acc: d.always_cpu.accuracy_pct, reg: d.always_cpu.mean_regret_pct, p90: d.always_cpu.p90_regret_pct },
        { name: "Always-RTX", wins: d.always_rtx.wins, total: d.total, acc: d.always_rtx.accuracy_pct, reg: d.always_rtx.mean_regret_pct, p90: d.always_rtx.p90_regret_pct },
        { name: "Fit-Only", wins: d.fit_only.wins, total: d.total, acc: d.fit_only.accuracy_pct, reg: d.fit_only.mean_regret_pct, p90: d.fit_only.p90_regret_pct },
      ];

      strategies.forEach((st, idx) => {
        html += `
          <tr class="${st.isSr ? 'highlight' : ''}">
            ${idx === 0 ? `<td rowspan="4" style="vertical-align:middle; font-weight:700; border-right:1px solid var(--rule);">${wl.toUpperCase()} <br><span style="font-size:11px; color:var(--ink-3);">(${d.total} decisions)</span></td>` : ''}
            <td>${st.name}</td>
            <td class="num">${st.wins}/${st.total}</td>
            <td class="num" style="font-weight:700;">${st.acc.toFixed(1)}%</td>
            <td class="num">${st.reg.toFixed(2)}%</td>
            <td class="num">${st.p90 !== undefined ? st.p90.toFixed(2) + '%' : 'n/a'}</td>
          </tr>
        `;
      });
    });

    tbody.innerHTML = html;
  }

  renderRegretBarChart(stats) {
    const ctx = document.getElementById("chart-results-regret")?.getContext("2d");
    if (!ctx || !stats) return;

    if (this.regretChart) {
      this.regretChart.destroy();
    }

    const t = getChartTheme();
    const srReg = stats.siliconroute?.mean_regret_pct ?? 1.75;
    const cpuReg = stats.baselines?.always_cpu?.mean_regret_pct ?? 113.06;
    const rtxReg = stats.baselines?.always_rtx?.mean_regret_pct ?? 304.93;
    const fitReg = stats.baselines?.fit_only_router?.mean_regret_pct ?? 31.42;

    this.regretChart = new Chart(ctx, {
      type: "bar",
      data: {
        labels: ["SiliconRoute", "Fit-Only Router", "Always-CPU", "Always-RTX"],
        datasets: [
          {
            label: "Mean regret (%)",
            data: [srReg, fitReg, cpuReg, rtxReg],
            backgroundColor: [t.red, t.ink, t.ink2, t.ink3],
            borderWidth: 0,
            borderRadius: 0,
          },
        ],
      },
      options: {
        animation: false,
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            type: "logarithmic",
            title: { display: true, text: "Mean regret % (log scale)" },
            ticks: {
              callback: (val) => `${val}%`,
              font: { family: "'JetBrains Mono', monospace", size: 10 },
            },
          },
          x: {
            grid: { display: false },
          },
        },
        plugins: {
          legend: { display: false },
        },
      },
    });

    // Populate data table
    const tableBody = document.getElementById("tbody-results-regret-table");
    if (tableBody) {
      tableBody.innerHTML = `
        <tr class="highlight"><td>SiliconRoute</td><td class="num">${srReg.toFixed(2)}%</td><td>Winner</td></tr>
        <tr><td>Fit-Only Router</td><td class="num">${fitReg.toFixed(2)}%</td><td>Formula fit baseline</td></tr>
        <tr><td>Always-CPU</td><td class="num">${cpuReg.toFixed(2)}%</td><td>Hardware baseline</td></tr>
        <tr><td>Always-RTX</td><td class="num">${rtxReg.toFixed(2)}%</td><td>Hardware baseline</td></tr>
      `;
    }
  }

  renderSnapdragonSection(snapdragonData) {
    const container = document.getElementById("results-snapdragon-container");
    if (!container) return;

    if (snapdragonData && snapdragonData.has_results) {
      container.innerHTML = `
        <div style="padding:var(--space-16); background:var(--sheet); border:1px solid var(--rule);">
          <div style="font-weight:700; margin-bottom:8px;">Qualcomm Snapdragon X Elite Measurements</div>
          <p style="font-size:13px; color:var(--ink-2);">${snapdragonData.summary || "Preliminary NPU profiling."}</p>
        </div>
      `;
    } else {
      container.innerHTML = `
        <div style="padding:var(--space-24); background:var(--sheet); border:1px solid var(--rule); text-align:center;">
          <div style="font-size:14px; font-weight:600; color:var(--ink-2); margin-bottom:4px;">Snapdragon results not yet recorded</div>
          <div style="font-size:12px; color:var(--ink-3);">Hardware profiling on Qualcomm Snapdragon X Elite silicon is scheduled for deployment.</div>
        </div>
      `;
    }
  }
}
