/**
 * SiliconRoute Design Spec v2 — Live Telemetry Screen (Section 6.2)
 * Stacked full-width time series charts (CPU/RAM, RTX Power/Temp, SM Clock/P-State, Battery)
 * with 120-second rolling window and accessible data table toggles.
 */

import { getChartTheme, getDeviceChartProps } from "../charts/theme.js";

export class LiveScreen {
  constructor() {
    this.charts = {};
    this.maxPoints = 120;
    this.labels = [];
    this.isInitialized = false;

    window.addEventListener("themechange", () => this.updateChartThemes());
    window.addEventListener("telemetrysample", (e) => this.pushSample(e.detail));
  }

  init() {
    if (this.isInitialized) return;
    this.initCharts();
    this.setupTableToggles();
    this.isInitialized = true;
  }

  onActivate() {
    if (!this.isInitialized) {
      this.init();
    }
    Object.values(this.charts).forEach(c => c && c.update("none"));
  }

  initCharts() {
    const t = getChartTheme();

    // 1. CPU & RAM Chart
    const ctxCpu = document.getElementById("chart-live-cpu-ram")?.getContext("2d");
    if (ctxCpu) {
      this.charts.cpuRam = new Chart(ctxCpu, {
        type: "line",
        data: {
          labels: this.labels,
          datasets: [
            {
              label: "CPU Usage (%)",
              data: [],
              borderColor: t.cpu,
              backgroundColor: "transparent",
              borderWidth: 1.5,
              pointRadius: 0,
              tension: 0.1,
              yAxisID: "y",
            },
            {
              label: "RAM Usage (%)",
              data: [],
              borderColor: t.ink2,
              backgroundColor: "transparent",
              borderWidth: 1.5,
              borderDash: [4, 4],
              pointRadius: 0,
              tension: 0.1,
              yAxisID: "y",
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          scales: {
            x: { display: true, ticks: { maxTicksLimit: 8, font: { family: "'JetBrains Mono', monospace", size: 10 } } },
            y: { min: 0, max: 100, title: { display: true, text: "Usage (%)" } },
          },
        },
      });
    }

    // 2. RTX Power & Temperature
    const ctxGpu = document.getElementById("chart-live-gpu-pwr-temp")?.getContext("2d");
    if (ctxGpu) {
      this.charts.gpuPwrTemp = new Chart(ctxGpu, {
        type: "line",
        data: {
          labels: this.labels,
          datasets: [
            {
              label: "RTX 5070 Power (W)",
              data: [],
              borderColor: t.dgpu,
              borderWidth: 1.5,
              pointRadius: 0,
              tension: 0.1,
              yAxisID: "y",
            },
            {
              label: "RTX 5070 Temp (°C)",
              data: [],
              borderColor: t.warn,
              borderWidth: 1.5,
              borderDash: [3, 3],
              pointRadius: 0,
              tension: 0.1,
              yAxisID: "y1",
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          scales: {
            x: { display: true, ticks: { maxTicksLimit: 8, font: { family: "'JetBrains Mono', monospace", size: 10 } } },
            y: { min: 0, max: 120, title: { display: true, text: "Power (W)" } },
            y1: { min: 0, max: 100, position: "right", grid: { drawOnChartArea: false }, title: { display: true, text: "Temp (°C)" } },
          },
        },
      });
    }

    // 3. RTX SM Clock
    const ctxClock = document.getElementById("chart-live-gpu-clock")?.getContext("2d");
    if (ctxClock) {
      this.charts.gpuClock = new Chart(ctxClock, {
        type: "line",
        data: {
          labels: this.labels,
          datasets: [
            {
              label: "SM Clock (MHz)",
              data: [],
              borderColor: t.dgpu,
              borderWidth: 1.5,
              pointRadius: 0,
              tension: 0.1,
              yAxisID: "y",
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          scales: {
            x: { display: true, ticks: { maxTicksLimit: 8, font: { family: "'JetBrains Mono', monospace", size: 10 } } },
            y: { min: 0, title: { display: true, text: "Clock (MHz)" } },
          },
        },
      });
    }

    // 4. Battery Discharge Rate
    const ctxBatt = document.getElementById("chart-live-battery")?.getContext("2d");
    if (ctxBatt) {
      this.charts.battery = new Chart(ctxBatt, {
        type: "line",
        data: {
          labels: this.labels,
          datasets: [
            {
              label: "Discharge Rate (W)",
              data: [],
              borderColor: t.ok,
              borderWidth: 1.5,
              pointRadius: 0,
              tension: 0.1,
              yAxisID: "y",
            },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          animation: false,
          scales: {
            x: { display: true, ticks: { maxTicksLimit: 8, font: { family: "'JetBrains Mono', monospace", size: 10 } } },
            y: { min: 0, title: { display: true, text: "Rate (W)" } },
          },
        },
      });
    }
  }

  pushSample(sample) {
    if (!this.isInitialized) return;

    const timeStr = sample.timestamp ? sample.timestamp.split("T")[1]?.slice(0, 8) : "";
    this.labels.push(timeStr);
    if (this.labels.length > this.maxPoints) this.labels.shift();

    // CPU & RAM
    if (this.charts.cpuRam) {
      const d = this.charts.cpuRam.data.datasets;
      d[0].data.push(sample.cpu_percent || 0);
      d[1].data.push(sample.ram_percent || 0);
      if (d[0].data.length > this.maxPoints) d[0].data.shift();
      if (d[1].data.length > this.maxPoints) d[1].data.shift();
      this.charts.cpuRam.update("none");
    }

    // RTX Power & Temp
    if (this.charts.gpuPwrTemp) {
      const d = this.charts.gpuPwrTemp.data.datasets;
      d[0].data.push(sample.nvml_power_w || 0);
      d[1].data.push(sample.nvml_temp_c || 0);
      if (d[0].data.length > this.maxPoints) d[0].data.shift();
      if (d[1].data.length > this.maxPoints) d[1].data.shift();
      this.charts.gpuPwrTemp.update("none");
    }

    // RTX SM Clock
    if (this.charts.gpuClock) {
      const d = this.charts.gpuClock.data.datasets;
      d[0].data.push(sample.nvml_clock_mhz || 0);
      if (d[0].data.length > this.maxPoints) d[0].data.shift();
      this.charts.gpuClock.update("none");
    }

    // Battery
    if (this.charts.battery) {
      const d = this.charts.battery.data.datasets;
      d[0].data.push(sample.battery_discharge_w || 0);
      if (d[0].data.length > this.maxPoints) d[0].data.shift();
      this.charts.battery.update("none");
    }
  }

  setupTableToggles() {
    document.querySelectorAll(".chart-table-toggle-btn").forEach(btn => {
      btn.addEventListener("click", () => {
        const tableId = btn.dataset.tableTarget;
        const tbl = document.getElementById(tableId);
        if (tbl) {
          const isHidden = tbl.style.display === "none";
          tbl.style.display = isHidden ? "block" : "none";
          btn.textContent = isHidden ? "Hide accessible data table" : "Show accessible data table";
        }
      });
    });
  }

  updateChartThemes() {
    const t = getChartTheme();
    if (this.charts.cpuRam) {
      this.charts.cpuRam.data.datasets[0].borderColor = t.cpu;
      this.charts.cpuRam.data.datasets[1].borderColor = t.ink2;
      this.charts.cpuRam.update("none");
    }
    if (this.charts.gpuPwrTemp) {
      this.charts.gpuPwrTemp.data.datasets[0].borderColor = t.dgpu;
      this.charts.gpuPwrTemp.data.datasets[1].borderColor = t.warn;
      this.charts.gpuPwrTemp.update("none");
    }
    if (this.charts.gpuClock) {
      this.charts.gpuClock.data.datasets[0].borderColor = t.dgpu;
      this.charts.gpuClock.update("none");
    }
    if (this.charts.battery) {
      this.charts.battery.data.datasets[0].borderColor = t.ok;
      this.charts.battery.update("none");
    }
  }
}
