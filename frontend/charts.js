/**
 * SiliconRoute Phase 6 Chart.js 4 Integration
 * Colors per .agents/rules/02-design.md:
 * - CPU: #D98A3D (copper)
 * - GPU0 (dml:0 / AMD Radeon): #3CCFA0 (mint)
 * - GPU1 (dml:1 / NVIDIA RTX): #6EA8FE (blue)
 * - NPU / RAM: #C77DFF (purple)
 */

const DEVICE_COLORS = {
  cpu: "#D98A3D",
  "dml:0": "#3CCFA0",
  "dml:1": "#6EA8FE",
  npu: "#C77DFF",
  ram: "#A78BFA",
  temp: "#F5C542",
  pstate: "#3CCFA0",
};

// Global chart font & color defaults
if (window.Chart) {
  Chart.defaults.color = "#9AA3B2";
  Chart.defaults.borderColor = "#232A37";
  Chart.defaults.font.family = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
  Chart.defaults.font.size = 11;
}

export class SiliconCharts {
  constructor() {
    this.liveCpuRam = null;
    this.liveGpuPowerTemp = null;
    this.liveGpuClockPstate = null;
    this.liveBattery = null;
    this.logLogChart = null;
    this.rawSampleChart = null;
    this.historyBuffer = [];
  }

  // ---------------------------------------------------------------------------
  // 1. Live Telemetry Charts Initialization
  // ---------------------------------------------------------------------------
  initLiveCharts() {
    const commonLineOptions = {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: {
          position: "top",
          labels: { boxWidth: 12, padding: 8, font: { size: 11 } },
        },
        tooltip: {
          mode: "index",
          intersect: false,
          backgroundColor: "#1A1F29",
          borderColor: "#2E3748",
          borderWidth: 1,
        },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { maxTicksLimit: 6, font: { family: "ui-monospace, monospace", size: 10 } },
        },
        y: {
          grid: { color: "rgba(35, 42, 55, 0.6)" },
          ticks: { font: { family: "ui-monospace, monospace", size: 10 } },
        },
      },
    };

    // 1. CPU & RAM %
    const ctxCpu = document.getElementById("chart-cpu-ram")?.getContext("2d");
    if (ctxCpu) {
      this.liveCpuRam = new Chart(ctxCpu, {
        type: "line",
        data: {
          labels: [],
          datasets: [
            {
              label: "CPU Usage %",
              data: [],
              borderColor: DEVICE_COLORS.cpu,
              backgroundColor: "rgba(217, 138, 61, 0.1)",
              borderWidth: 1.5,
              pointRadius: 0,
              tension: 0.2,
            },
            {
              label: "RAM Usage %",
              data: [],
              borderColor: DEVICE_COLORS.ram,
              backgroundColor: "rgba(167, 139, 250, 0.1)",
              borderWidth: 1.5,
              pointRadius: 0,
              tension: 0.2,
            },
          ],
        },
        options: {
          ...commonLineOptions,
          scales: {
            ...commonLineOptions.scales,
            y: { ...commonLineOptions.scales.y, min: 0, max: 100 },
          },
        },
      });
    }

    // 2. RTX Power (W) & Temp (°C)
    const ctxGpu = document.getElementById("chart-gpu-power-temp")?.getContext("2d");
    if (ctxGpu) {
      this.liveGpuPowerTemp = new Chart(ctxGpu, {
        type: "line",
        data: {
          labels: [],
          datasets: [
            {
              label: "RTX Power (W)",
              data: [],
              borderColor: DEVICE_COLORS["dml:1"],
              borderWidth: 1.5,
              pointRadius: 0,
              tension: 0.2,
              yAxisID: "yPower",
            },
            {
              label: "RTX Temp (°C)",
              data: [],
              borderColor: DEVICE_COLORS.temp,
              borderWidth: 1.5,
              pointRadius: 0,
              tension: 0.2,
              yAxisID: "yTemp",
            },
          ],
        },
        options: {
          ...commonLineOptions,
          scales: {
            ...commonLineOptions.scales,
            yPower: {
              type: "linear",
              position: "left",
              grid: { color: "rgba(35, 42, 55, 0.6)" },
              ticks: { font: { family: "ui-monospace, monospace" } },
              title: { display: true, text: "Power (W)", font: { size: 10 } },
              min: 0,
            },
            yTemp: {
              type: "linear",
              position: "right",
              grid: { drawOnChartArea: false },
              ticks: { font: { family: "ui-monospace, monospace" } },
              title: { display: true, text: "Temp (°C)", font: { size: 10 } },
              min: 30,
              max: 95,
            },
          },
        },
      });
    }

    // 3. RTX P-state & Clock (MHz)
    const ctxClock = document.getElementById("chart-gpu-clock")?.getContext("2d");
    if (ctxClock) {
      this.liveGpuClockPstate = new Chart(ctxClock, {
        type: "line",
        data: {
          labels: [],
          datasets: [
            {
              label: "SM Clock (MHz)",
              data: [],
              borderColor: DEVICE_COLORS["dml:1"],
              borderWidth: 1.5,
              pointRadius: 0,
              tension: 0.2,
              yAxisID: "yClock",
            },
            {
              label: "P-State",
              data: [],
              borderColor: DEVICE_COLORS.pstate,
              borderWidth: 1.5,
              pointRadius: 0,
              stepped: true,
              yAxisID: "yPstate",
            },
          ],
        },
        options: {
          ...commonLineOptions,
          scales: {
            ...commonLineOptions.scales,
            yClock: {
              type: "linear",
              position: "left",
              grid: { color: "rgba(35, 42, 55, 0.6)" },
              title: { display: true, text: "Clock (MHz)", font: { size: 10 } },
              min: 0,
            },
            yPstate: {
              type: "linear",
              position: "right",
              grid: { drawOnChartArea: false },
              title: { display: true, text: "P-State (0-8)", font: { size: 10 } },
              min: 0,
              max: 8,
              reverse: true, // P0 is max perf, P8 is idle sleep
            },
          },
        },
      });
    }

    // 4. Battery Discharge (W)
    const ctxBatt = document.getElementById("chart-battery")?.getContext("2d");
    if (ctxBatt) {
      this.liveBattery = new Chart(ctxBatt, {
        type: "line",
        data: {
          labels: [],
          datasets: [
            {
              label: "Battery Discharge (W)",
              data: [],
              borderColor: "#EDEFF3",
              backgroundColor: "rgba(237, 239, 243, 0.08)",
              borderWidth: 1.5,
              pointRadius: 0,
              tension: 0.2,
            },
          ],
        },
        options: {
          ...commonLineOptions,
          scales: {
            ...commonLineOptions.scales,
            y: { ...commonLineOptions.scales.y, min: 0 },
          },
        },
      });
    }
  }

  updateLiveTelemetry(samples) {
    const maxPoints = 60;
    const labels = samples.map((s) => s.ts.substring(11, 19));

    // 1. CPU & RAM
    if (this.liveCpuRam) {
      this.liveCpuRam.data.labels = labels;
      this.liveCpuRam.data.datasets[0].data = samples.map((s) => s.cpu_pct ?? 0);
      this.liveCpuRam.data.datasets[1].data = samples.map((s) => s.ram_pct ?? 0);
      this.liveCpuRam.update();
    }

    // 2. GPU Power & Temp
    if (this.liveGpuPowerTemp) {
      this.liveGpuPowerTemp.data.labels = labels;
      this.liveGpuPowerTemp.data.datasets[0].data = samples.map((s) => s.gpu_power_w ?? null);
      this.liveGpuPowerTemp.data.datasets[1].data = samples.map((s) => s.gpu_temp_c ?? null);
      this.liveGpuPowerTemp.update();
    }

    // 3. GPU Clock & P-State
    if (this.liveGpuClockPstate) {
      this.liveGpuClockPstate.data.labels = labels;
      this.liveGpuClockPstate.data.datasets[0].data = samples.map((s) => s.gpu_clock_sm_mhz ?? null);
      this.liveGpuClockPstate.data.datasets[1].data = samples.map((s) => s.gpu_pstate ?? null);
      this.liveGpuClockPstate.update();
    }

    // 4. Battery Discharge
    if (this.liveBattery) {
      this.liveBattery.data.labels = labels;
      this.liveBattery.data.datasets[0].data = samples.map((s) => s.discharge_w ?? 0);
      this.liveBattery.update();
    }
  }

  // ---------------------------------------------------------------------------
  // 2. Log-Log Latency vs Model Size Chart
  // ---------------------------------------------------------------------------
  renderLogLogChart(chartData, onPointClickCallback) {
    const ctx = document.getElementById("chart-log-log")?.getContext("2d");
    if (!ctx) return;

    if (this.logLogChart) {
      this.logLogChart.destroy();
    }

    const datasets = [];

    // 1. Scatter points for measured runs per device
    for (const [devKey, runs] of Object.entries(chartData.runs || {})) {
      const color = DEVICE_COLORS[devKey] || "#EDEFF3";
      datasets.push({
        type: "scatter",
        label: `${devKey.toUpperCase()} Measured`,
        data: runs.map((r) => ({
          x: r.params,
          y: r.median_ms,
          run_id: r.run_id,
          model_name: r.model_name,
          weight_mb: r.weight_mb,
          inner_loop_k: r.inner_loop_k,
        })),
        backgroundColor: color,
        borderColor: color,
        pointRadius: 5,
        pointHoverRadius: 8,
      });
    }

    // 2. Fitted smooth curve lines
    for (const [devKey, curvePoints] of Object.entries(chartData.curves || {})) {
      const color = DEVICE_COLORS[devKey] || "#EDEFF3";
      datasets.push({
        type: "line",
        label: `${devKey.toUpperCase()} Fitted Curve`,
        data: curvePoints.map((p) => ({
          x: p.params,
          y: p.pred_ms,
        })),
        borderColor: color,
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.1,
        fill: false,
      });
    }

    this.logLogChart = new Chart(ctx, {
      data: { datasets },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: "top",
            labels: { boxWidth: 12, padding: 12, font: { size: 11 } },
          },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const pt = ctx.raw;
                if (pt.run_id) {
                  return `${ctx.dataset.label}: ${pt.model_name} | ${pt.y.toFixed(3)} ms | (Click to inspect samples)`;
                }
                return `${ctx.dataset.label}: ${pt.y.toFixed(3)} ms`;
              },
            },
          },
        },
        scales: {
          x: {
            type: "logarithmic",
            title: { display: true, text: "Model Parameters (log scale)", font: { weight: "600" } },
            grid: { color: "rgba(35, 42, 55, 0.6)" },
            ticks: {
              font: { family: "ui-monospace, monospace" },
              callback: (val) => Number(val).toLocaleString(),
            },
          },
          y: {
            type: "logarithmic",
            title: { display: true, text: "Median Latency in ms (log scale)", font: { weight: "600" } },
            grid: { color: "rgba(35, 42, 55, 0.6)" },
            ticks: {
              font: { family: "ui-monospace, monospace" },
              callback: (val) => Number(val).toFixed(2) + " ms",
            },
          },
        },
        onClick: (evt, elements) => {
          if (!elements.length) return;
          const el = elements[0];
          const rawPt = datasets[el.datasetIndex].data[el.index];
          if (rawPt && rawPt.run_id && onPointClickCallback) {
            onPointClickCallback(rawPt.run_id);
          }
        },
      },
    });
  }

  // ---------------------------------------------------------------------------
  // 3. Raw Timing Samples Dot Chart (Inspector Modal)
  // ---------------------------------------------------------------------------
  renderRawSamplesChart(runData) {
    const ctx = document.getElementById("chart-raw-samples")?.getContext("2d");
    if (!ctx) return;

    if (this.rawSampleChart) {
      this.rawSampleChart.destroy();
    }

    const rawSamples = typeof runData.raw_ms_json === "string"
      ? JSON.parse(runData.raw_ms_json)
      : (runData.raw_ms_json || []);

    const scatterData = rawSamples.map((val, idx) => ({ x: idx + 1, y: val }));
    const color = DEVICE_COLORS[runData.device_key] || "#D98A3D";

    this.rawSampleChart = new Chart(ctx, {
      type: "scatter",
      data: {
        datasets: [
          {
            label: "Inference Sample (ms)",
            data: scatterData,
            backgroundColor: color,
            borderColor: color,
            pointRadius: 4,
            pointHoverRadius: 6,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => `Sample #${ctx.raw.x}: ${ctx.raw.y.toFixed(4)} ms`,
            },
          },
        },
        scales: {
          x: {
            type: "linear",
            title: { display: true, text: "Sample Sequence (1 to N)" },
            grid: { color: "rgba(35, 42, 55, 0.6)" },
            ticks: { stepSize: 5, font: { family: "ui-monospace, monospace" } },
          },
          y: {
            title: { display: true, text: "Latency (ms)" },
            grid: { color: "rgba(35, 42, 55, 0.6)" },
            ticks: {
              font: { family: "ui-monospace, monospace" },
              callback: (val) => Number(val).toFixed(3) + " ms",
            },
          },
        },
      },
    });
  }
}
