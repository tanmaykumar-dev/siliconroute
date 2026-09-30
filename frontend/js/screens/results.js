/**
 * SiliconRoute Design Spec v2 — Results Screen (Section 6.5)
 * Published hardware evaluation (Decisions 117-140 and 141-148),
 * regret bar chart on log scale, and earlier evaluation (93-116).
 */

import { getChartTheme } from "../charts/theme.js";

export class ResultsScreen {
  constructor(apiClient) {
    this.api = apiClient;
    this.isLoaded = false;
    this.regretChart = null;

    window.addEventListener("themechange", () => this.updateChartTheme());
  }

  async init() {}

  async onActivate() {
    if (!this.isLoaded) {
      await this.loadEvaluationData();
      this.isLoaded = true;
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
      const p90Str = d.p90_regret_pct !== undefined ? `${d.p90_regret_pct.toFixed(2)}%` : "N/A";
      return `
        <tr style="${r.isSr ? 'background-color: rgba(76, 199, 135, 0.08); font-weight:600;' : ''}">
          <td style="color:${r.isSr ? 'var(--ok)' : 'var(--ink)'};">${r.name}</td>
          <td class="font-mono text-center">${d.wins}/${d.total}</td>
          <td class="font-mono text-right" style="color:${r.isSr ? 'var(--ok)' : 'var(--ink)'}; font-weight:600;">${d.accuracy_pct.toFixed(1)}%</td>
          <td class="font-mono text-right">${d.mean_regret_pct.toFixed(2)}%</td>
          <td class="font-mono text-right">${p90Str}</td>
        </tr>
      `;
    }).join("");

    if (includeOrt) {
      html += `
        <tr>
          <td style="color:var(--ink-3);">ORT ExecutionProviderDevicePolicy</td>
          <td colspan="4"><span class="pill pill-na" title="ORT ExecutionProviderDevicePolicy was not executed on physical hardware; result would be assumed, not measured">not available</span></td>
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
          <tr style="${st.isSr ? 'font-weight:600;' : ''}">
            ${idx === 0 ? `<td rowspan="4" style="vertical-align:middle; font-weight:700; border-right:1px solid var(--line);">${wl.toUpperCase()} <br><span style="font-size:11px; color:var(--ink-3);">(${d.total} decs)</span></td>` : ''}
            <td style="color:${st.isSr ? 'var(--ok)' : 'var(--ink)'};">${st.name}</td>
            <td class="font-mono text-center">${st.wins}/${st.total}</td>
            <td class="font-mono text-right" style="color:${st.isSr ? 'var(--ok)' : 'var(--ink)'};">${st.acc.toFixed(1)}%</td>
            <td class="font-mono text-right">${st.reg.toFixed(2)}%</td>
            <td class="font-mono text-right">${st.p90 !== undefined ? st.p90.toFixed(2) + '%' : 'N/A'}</td>
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
    const srReg = stats.siliconroute?.mean_regret_pct || 1.75;
    const cpuReg = stats.baselines?.always_cpu?.mean_regret_pct || 113.06;
    const rtxReg = stats.baselines?.always_rtx?.mean_regret_pct || 304.93;
    const fitReg = stats.baselines?.fit_only_router?.mean_regret_pct || 31.42;

    this.regretChart = new Chart(ctx, {
      type: "bar",
      data: {
        labels: ["SiliconRoute", "Fit-Only", "Always-CPU", "Always-RTX"],
        datasets: [
          {
            label: "Mean Regret / Slowdown (%)",
            data: [srReg, fitReg, cpuReg, rtxReg],
            backgroundColor: [t.ok, t.lineStrong, t.lineStrong, t.lineStrong],
            borderWidth: 0,
            borderRadius: 4,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: {
            type: "logarithmic",
            title: { display: true, text: "Mean Regret % (Log Scale)" },
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
  }

  updateChartTheme() {
    if (this.regretChart) {
      const t = getChartTheme();
      this.regretChart.data.datasets[0].backgroundColor = [t.ok, t.lineStrong, t.lineStrong, t.lineStrong];
      this.regretChart.update("none");
    }
  }
}
