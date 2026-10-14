/**
 * SiliconRoute Live Telemetry Screen (Section 6.2)
 * Live 1 Hz charts streaming across CPU, integrated GPU, and discrete GPU sensors:
 * - Processor Utilisation (%)
 * - Power Draw (W)
 * - GPU Temperature (°C)
 * - SM Clock (MHz) & P-State
 */

import { getChartTheme } from "../charts/theme.js";

export class LiveScreen {
  constructor() {
    this.charts = {};
    this.maxPoints = 60;
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

    // 1. Processor Utilisation (%)
    const ctxUtil = (document.getElementById("chart-live-util") || document.getElementById("chart-live-cpu-ram"))?.getContext("2d");
    if (ctxUtil) {
      this.charts.util = new Chart(ctxUtil, {
        type: "line",
        data: {
          labels: this.labels,
          datasets: [
            {
              label: "CPU utilisation (%)",
              data: [],
              borderColor: t.cpu,
              backgroundColor: "transparent",
              borderWidth: 2,
              pointRadius: 0,
              tension: 0.1,
              yAxisID: "y",
            },
            {
              label: "RTX 5070 GPU (%)",
              data: [],
              borderColor: t.dgpu,
              backgroundColor: "transparent",
              borderWidth: 2,
              pointRadius: 0,
              tension: 0.1,
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
            y: { min: 0, max: 100, title: { display: true, text: "Utilisation (%)" } },
          },
        },
      });
    }

    // 2. Power Draw (W)
    const ctxPower = (document.getElementById("chart-live-power") || document.getElementById("chart-live-gpu-pwr-temp"))?.getContext("2d");
    if (ctxPower) {
      this.charts.power = new Chart(ctxPower, {
        type: "line",
        data: {
          labels: this.labels,
          datasets: [
            {
              label: "RTX 5070 power (W)",
              data: [],
              borderColor: t.dgpu,
              backgroundColor: "transparent",
              borderWidth: 2,
              pointRadius: 0,
              tension: 0.1,
              yAxisID: "y",
            },
            {
              label: "Battery discharge (W)",
              data: [],
              borderColor: t.ink,
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
            y: { min: 0, max: 120, title: { display: true, text: "Power (W)" } },
          },
        },
      });
    }

    // 3. GPU Temperature (°C)
    const ctxTemp = document.getElementById("chart-live-temp")?.getContext("2d");
    if (ctxTemp) {
      this.charts.temp = new Chart(ctxTemp, {
        type: "line",
        data: {
          labels: this.labels,
          datasets: [
            {
              label: "RTX 5070 temperature (°C)",
              data: [],
              borderColor: t.redDeep,
              backgroundColor: "transparent",
              borderWidth: 2,
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
            y: { min: 20, max: 95, title: { display: true, text: "Temperature (°C)" } },
          },
        },
      });
    }

    // 4. SM Clock (MHz) & P-State
    const ctxClock = (document.getElementById("chart-live-clock") || document.getElementById("chart-live-gpu-clock"))?.getContext("2d");
    if (ctxClock) {
      this.charts.clock = new Chart(ctxClock, {
        type: "line",
        data: {
          labels: this.labels,
          datasets: [
            {
              label: "SM clock (MHz)",
              data: [],
              borderColor: t.dgpu,
              backgroundColor: "transparent",
              borderWidth: 2,
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
  }

  pushSample(sample) {
    if (!this.isInitialized) return;

    const timeStr = sample.timestamp ? sample.timestamp.split("T")[1]?.slice(0, 8) : "";
    this.labels.push(timeStr);
    if (this.labels.length > this.maxPoints) this.labels.shift();

    // 1. Utilisation
    if (this.charts.util) {
      const d = this.charts.util.data.datasets;
      d[0].data.push(sample.cpu_percent || 0);
      d[1].data.push(sample.nvml_gpu_percent || 0);
      d[2].data.push(sample.ram_percent || 0);
      d.forEach(ds => {
        if (ds.data.length > this.maxPoints) ds.data.shift();
      });
      this.charts.util.update("none");

      const tb = document.getElementById("tbody-live-util");
      if (tb) {
        tb.innerHTML = `<tr><td>${timeStr}</td><td class="num">${(sample.cpu_percent || 0).toFixed(1)}%</td><td class="num">${(sample.nvml_gpu_percent || 0).toFixed(1)}%</td></tr>` + tb.innerHTML;
        if (tb.children.length > 10) tb.removeChild(tb.lastChild);
      }
    }

    // 2. Power
    if (this.charts.power) {
      const d = this.charts.power.data.datasets;
      d[0].data.push(sample.nvml_power_w || 0);
      d[1].data.push(sample.battery_discharge_w || 0);
      d.forEach(ds => {
        if (ds.data.length > this.maxPoints) ds.data.shift();
      });
      this.charts.power.update("none");

      const tb = document.getElementById("tbody-live-power");
      if (tb) {
        tb.innerHTML = `<tr><td>${timeStr}</td><td class="num">${(sample.nvml_power_w || 0).toFixed(1)} W</td><td>Active</td></tr>` + tb.innerHTML;
        if (tb.children.length > 10) tb.removeChild(tb.lastChild);
      }
    }

    // 3. Temperature
    if (this.charts.temp) {
      const d = this.charts.temp.data.datasets;
      d[0].data.push(sample.nvml_temp_c || 0);
      d.forEach(ds => {
        if (ds.data.length > this.maxPoints) ds.data.shift();
      });
      this.charts.temp.update("none");

      const tb = document.getElementById("tbody-live-temp");
      if (tb) {
        tb.innerHTML = `<tr><td>${timeStr}</td><td class="num">${(sample.nvml_temp_c || 0).toFixed(1)} °C</td></tr>` + tb.innerHTML;
        if (tb.children.length > 10) tb.removeChild(tb.lastChild);
      }
    }

    // 4. Clock
    if (this.charts.clock) {
      const d = this.charts.clock.data.datasets;
      d[0].data.push(sample.nvml_clock_mhz || 0);
      d.forEach(ds => {
        if (ds.data.length > this.maxPoints) ds.data.shift();
      });
      this.charts.clock.update("none");

      const tb = document.getElementById("tbody-live-clock");
      if (tb) {
        const pstate = sample.nvml_pstate !== undefined && sample.nvml_pstate !== null ? `P${sample.nvml_pstate}` : "--";
        tb.innerHTML = `<tr><td>${timeStr}</td><td class="num">${Math.round(sample.nvml_clock_mhz || 0)} MHz</td><td class="num">${pstate}</td></tr>` + tb.innerHTML;
        if (tb.children.length > 10) tb.removeChild(tb.lastChild);
      }
    }
  }

  setupTableToggles() {
    document.querySelectorAll(".chart-table-toggle").forEach(btn => {
      btn.addEventListener("click", () => {
        const targetId = btn.dataset.target;
        const tbl = document.getElementById(targetId);
        if (tbl) {
          const isHidden = (tbl.style.display === "none" || !tbl.style.display);
          tbl.style.display = isHidden ? "block" : "none";
          btn.textContent = isHidden ? "Hide data table" : "Show data table";
        }
      });
    });
  }
}
