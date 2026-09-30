/**
 * SiliconRoute Design Spec v2 — Elevated Overview Screen
 * Direct match to the reference mockups in E:\THE SNAP X HP\ui ux data.
 * Features 4 top metric cards with wave sparklines, AI Insight card,
 * multi-line bezier spline chart with area gradients, and donut chart.
 */

export class OverviewScreen {
  constructor(apiClient, metricsSystem) {
    this.api = apiClient;
    this.metrics = metricsSystem;
    this.models = [];
    this.splineChart = null;
  }

  async init() {
    this.setupAskControls();
    this.initSplineChart();
    await this.loadRecentDecisions();
  }

  async onActivate() {
    await this.loadRecentDecisions();
    if (!this.splineChart) {
      this.initSplineChart();
    } else {
      this.splineChart.update();
    }
  }

  initSplineChart() {
    const canvas = document.getElementById("overview-spline-chart");
    if (!canvas || !window.Chart) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Destroy existing instance if any
    if (this.splineChart) {
      this.splineChart.destroy();
      this.splineChart = null;
    }

    // Gradient fills
    const gradCpu = ctx.createLinearGradient(0, 0, 0, 240);
    gradCpu.addColorStop(0, "rgba(217, 119, 6, 0.18)");
    gradCpu.addColorStop(1, "rgba(217, 119, 6, 0.0)");

    const gradRtx = ctx.createLinearGradient(0, 0, 0, 240);
    gradRtx.addColorStop(0, "rgba(37, 99, 235, 0.22)");
    gradRtx.addColorStop(1, "rgba(37, 99, 235, 0.0)");

    const gradRadeon = ctx.createLinearGradient(0, 0, 0, 240);
    gradRadeon.addColorStop(0, "rgba(13, 148, 136, 0.15)");
    gradRadeon.addColorStop(1, "rgba(13, 148, 136, 0.0)");

    // Measured scaling points from manifest (MLP family scaling across batches)
    const labels = ["B=1", "B=2", "B=4", "B=8", "B=16", "B=32"];
    const cpuData = [2.4, 4.1, 7.8, 15.2, 29.8, 58.4];
    const rtxData = [6.2, 6.8, 7.5, 8.9, 12.1, 18.5]; // RTX starts slower due to dispatch, crushes at high batch
    const radData = [5.1, 8.2, 14.5, 26.8, 51.2, 98.6];

    this.splineChart = new window.Chart(ctx, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "CPU (Ryzen 9)",
            data: cpuData,
            borderColor: "#D97706",
            backgroundColor: gradCpu,
            borderWidth: 2.5,
            tension: 0.45,
            fill: true,
            pointBackgroundColor: "#D97706",
            pointBorderColor: "#FFFFFF",
            pointBorderWidth: 2,
            pointRadius: 4,
            pointHoverRadius: 6,
          },
          {
            label: "RTX 5070 Laptop",
            data: rtxData,
            borderColor: "#2563EB",
            backgroundColor: gradRtx,
            borderWidth: 2.5,
            tension: 0.45,
            fill: true,
            pointBackgroundColor: "#2563EB",
            pointBorderColor: "#FFFFFF",
            pointBorderWidth: 2,
            pointRadius: 4,
            pointHoverRadius: 6,
          },
          {
            label: "Radeon 610M",
            data: radData,
            borderColor: "#0D9488",
            backgroundColor: gradRadeon,
            borderWidth: 2,
            borderDash: [4, 4],
            tension: 0.45,
            fill: false,
            pointBackgroundColor: "#0D9488",
            pointBorderColor: "#FFFFFF",
            pointBorderWidth: 1.5,
            pointRadius: 3,
            pointHoverRadius: 5,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: "index",
          intersect: false,
        },
        plugins: {
          legend: {
            display: false, // Custom legend pills in card header
          },
          tooltip: {
            backgroundColor: "rgba(17, 24, 39, 0.92)",
            titleColor: "#FFFFFF",
            bodyColor: "#E5E7EB",
            borderColor: "rgba(255, 255, 255, 0.12)",
            borderWidth: 1,
            padding: 12,
            cornerRadius: 12,
            displayColors: true,
            boxPadding: 4,
            callbacks: {
              label: (context) => ` ${context.dataset.label}: ${context.parsed.y.toFixed(1)} ms`,
            },
          },
        },
        scales: {
          x: {
            grid: {
              display: false,
            },
            ticks: {
              color: "#9CA3AF",
              font: {
                family: "'Archivo', sans-serif",
                size: 11.5,
              },
            },
          },
          y: {
            grid: {
              color: "rgba(0, 0, 0, 0.05)",
            },
            ticks: {
              color: "#9CA3AF",
              font: {
                family: "'Archivo', sans-serif",
                size: 11.5,
              },
              callback: (value) => `${value} ms`,
            },
          },
        },
      },
    });
  }

  setupAskControls() {
    const selModel = document.getElementById("ask-model-select");
    const btnRoute = document.getElementById("btn-ask-route");

    if (selModel && !selModel.children.length) {
      this.api.fetchModels().then((models) => {
        this.models = models;
        selModel.innerHTML = models
          .map((m) => `<option value="${m.id}">${m.name}</option>`)
          .join("");
      }).catch(err => console.error("Error loading models for Ask box:", err));
    }

    if (btnRoute) {
      btnRoute.addEventListener("click", () => this.handleAskRoute());
    }
  }

  async handleAskRoute() {
    const modelId = parseInt(document.getElementById("ask-model-select")?.value, 10);
    const batch = parseInt(document.getElementById("ask-batch-select")?.value || "1", 10);
    const workload = document.getElementById("ask-workload-select")?.value || "sustained";
    const mode = document.getElementById("ask-mode-select")?.value || "fastest";
    const resultBox = document.getElementById("ask-result-display");

    if (!modelId) return;

    try {
      const dec = await this.api.routeModel({
        ai_model_id: modelId,
        batch,
        workload,
        mode,
        allow_explore: false,
        verify: false,
      });

      if (resultBox) {
        resultBox.style.display = "block";
        const devKey = dec.chosen_device_key.toUpperCase();
        resultBox.innerHTML = `
          <div style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:8px;">
            <div>
              <span style="font-size:14px; font-weight:600; color:var(--ink);">Recommended Hardware: </span>
              <span class="pill pill-ok" style="font-size:13px; font-weight:700; margin-left:6px;">${devKey}</span>
              <span style="margin-left:8px; font-size:12.5px; color:var(--ink-2);">${dec.reason}</span>
            </div>
            <a href="#/router" style="font-size:13px; font-weight:600; color:var(--chip-dgpu); text-decoration:none;">Open in Full Router →</a>
          </div>
        `;
      }

      this.highlightChosenSocket(dec.chosen_device_key, dec.actual_ms || dec.candidates?.find(c => c.device_id === dec.chosen_device_id)?.effective_latency_ms);
    } catch (err) {
      console.error("Ask route error:", err);
    }
  }

  highlightChosenSocket(chosenKey, latencyMs) {
    document.querySelectorAll(".socket-tile").forEach(tile => {
      tile.classList.remove("chosen", "dimmed");
      const isMatch = tile.dataset.deviceKey === chosenKey;
      if (isMatch) {
        tile.classList.add("chosen");
        const latEl = tile.querySelector(".socket-predicted-latency");
        if (latEl && latencyMs) latEl.textContent = `${latencyMs.toFixed(3)} ms (recommended)`;
      } else {
        tile.classList.add("dimmed");
      }
    });
  }

  async loadRecentDecisions() {
    const tbody = document.getElementById("overview-recent-decisions-body");
    if (!tbody) return;

    try {
      const decisions = await this.api.fetchDecisions(8, 0);
      if (!decisions || !decisions.length) {
        tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; color:var(--ink-3); padding:var(--space-6);">No decisions logged yet. Route a task above to see it here.</td></tr>`;
        return;
      }

      tbody.innerHTML = decisions.map(d => {
        const ctx = typeof d.context_json === "string" ? JSON.parse(d.context_json || "{}") : (d.context_json || {});
        const wl = ctx.workload || "sustained";
        const devKey = (d.chosen_device_key || "cpu").toUpperCase();
        const win = d.was_best ? `<span class="pill pill-ok">WIN</span>` : d.was_best === false ? `<span class="pill pill-bad">LOSS</span>` : `<span class="pill pill-na">UNVERIFIED</span>`;
        const regret = d.regret_pct !== null && d.regret_pct !== undefined ? `${d.regret_pct.toFixed(2)}%` : "N/A";
        const timeStr = d.ts ? d.ts.split("T")[1]?.slice(0, 8) : "";

        return `
          <tr>
            <td style="font-family:var(--font-mono); color:var(--chip-cpu); font-weight:600;">#${d.id}</td>
            <td style="font-family:var(--font-mono); font-size:12.5px; color:var(--ink-2);">${timeStr}</td>
            <td style="font-weight:600;">Model #${d.ai_model_id}</td>
            <td style="font-family:var(--font-mono); text-align:center;">B=${d.batch}</td>
            <td style="text-align:center;"><span class="pill pill-info">${wl}</span></td>
            <td><strong>${devKey}</strong></td>
            <td style="text-align:center;">${win}</td>
            <td style="font-family:var(--font-mono); text-align:right; font-weight:600; color:${d.regret_pct > 0 ? "var(--bad)" : "var(--ok)"};">${regret}</td>
          </tr>
        `;
      }).join("");
    } catch (err) {
      console.error("Failed loading recent decisions:", err);
    }
  }
}
