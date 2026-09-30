/**
 * SiliconRoute Design Spec v3: "Red Bench" Live Telemetry Screen (Section 6.2)
 * Stacked full-width charts sharing one time axis: utilisation, power, temperature,
 * clock and sleep state, battery discharge. Each chart: "Show data table" toggle.
 * Unavailable series show the "not available" tag with the API's reason.
 */

import { getChartTheme } from "../charts/theme.js";

export class LiveScreen {
  constructor() {
    this.charts = {};
    this.maxPoints = 120;
    this.labels = [];
    this.isInitialized = false;

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
              label: "CPU utilisation (%)",
              data: [],
              borderColor: t.cpu,
              backgroundColor: "transparent",
              borderWidth: 1.5,
              pointRadius: 0,
              tension: 0,
              yAxisID: "y",
            },
            {
              label: "RAM utilisation (%)",
              data: [],
              borderColor: t.ink2,
              backgroundColor: "transparent",
              borderWidth: 1.5,
              borderDash: [4, 4],
              pointRadius: 0,
              tension: 0,
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
            y: { min: 0, max: 100, title: { display: true, text: "Utilisation (%)" } },
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
              label: "RTX 5070 power (W)",
              data: [],
              borderColor: t.dgpu,
              backgroundColor: "transparent",
              borderWidth: 1.5,
              pointRadius: 0,
              tension: 0,
              yAxisID: "y",
            },
            {
              label: "RTX 5070 temperature (°C)",
              data: [],
              borderColor: t.redDeep,
              backgroundColor: "transparent",
              borderWidth: 1.5,
              borderDash: [3, 3],
              pointRadius: 0,
              tension: 0,
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
            y1: { min: 0, max: 100, position: "right", grid: { drawOnChartArea: false }, title: { display: true, text: "Temperature (°C)" } },
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
              label: "SM clock (MHz)",
              data: [],
              borderColor: t.dgpu,
              backgroundColor: "transparent",
              borderWidth: 1.5,
              pointRadius: 0,
              tension: 0,
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
              label: "Discharge rate (W)",
              data: [],
              borderColor: t.ink,
              backgroundColor: "transparent",
              borderWidth: 1.5,
              pointRadius: 0,
              tension: 0,
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
            y: { min: 0, title: { display: true, text: "Discharge rate (W)" } },
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
          btn.textContent = isHidden ? "Hide data table" : "Show data table";
        }
      });
    });
  }
}
