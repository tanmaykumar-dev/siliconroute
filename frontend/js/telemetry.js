/**
 * SiliconRoute Design Spec v2 : Telemetry & Socket Strip Service
 * Connects to live SSE stream, updates top bar chips, socket tiles,
 * and maintains 60-second load sparklines for each chip.
 */

export class TelemetryService {
  constructor(apiClient) {
    this.api = apiClient;
    this.sseSource = null;
    this.history = {
      cpu: [],
      "dml:0": [],
      "dml:1": [],
    };
    this.maxHistory = 60;
  }

  start() {
    this.sseSource = this.api.connectTelemetryStream(
      (sample) => this.handleSample(sample),
      (err) => this.handleError(err)
    );
  }

  handleSample(sample) {
    // 1. Update Top Bar status chips
    const chipLive = document.getElementById("chip-live-status");
    if (chipLive) {
      chipLive.innerHTML = `<span class="pill pill-ok">live</span>`;
    }

    const chipBatt = document.getElementById("chip-battery-status");
    if (chipBatt && sample.battery_pct !== null && sample.battery_pct !== undefined) {
      const plugged = sample.plugged_in ? "plugged in" : "on battery";
      chipBatt.textContent = `${sample.battery_pct.toFixed(0)}% (${plugged})`;
    }

    // 2. Buffer history for sparklines
    const cpuLoad = sample.cpu_percent !== null && sample.cpu_percent !== undefined ? sample.cpu_percent : 0;
    const gpuLoad = sample.nvml_gpu_percent !== null && sample.nvml_gpu_percent !== undefined ? sample.nvml_gpu_percent : 0;

    this.pushHistory("cpu", cpuLoad);
    this.pushHistory("dml:1", gpuLoad);
    this.pushHistory("dml:0", 0); // DirectML iGPU utilization not directly exposed by OS

    // 3. Update Socket Tiles
    this.updateCpuSocket(sample);
    this.updateDml0Socket(sample);
    this.updateDml1Socket(sample);

    // 4. Draw sparklines
    this.drawSparkline("sparkline-cpu", this.history["cpu"], "var(--chip-cpu)");
    this.drawSparkline("sparkline-dml1", this.history["dml:1"], "var(--chip-dgpu)");
    this.drawSparkline("sparkline-dml0", this.history["dml:0"], "var(--chip-igpu)");

    // Broadcast sample for Live screen charts
    window.dispatchEvent(new CustomEvent("telemetrysample", { detail: sample }));
  }

  pushHistory(key, val) {
    if (!this.history[key]) this.history[key] = [];
    this.history[key].push(val);
    if (this.history[key].length > this.maxHistory) {
      this.history[key].shift();
    }
  }

  updateCpuSocket(sample) {
    const el = document.getElementById("socket-cpu-metrics");
    if (!el) return;
    const load = sample.cpu_percent !== null && sample.cpu_percent !== undefined ? `${sample.cpu_percent.toFixed(0)}%` : "not available";
    el.innerHTML = `
      <span>load <strong>${load}</strong></span>
      <span class="pill pill-na" title="Windows does not expose per-chip power for this CPU">pwr n/a</span>
    `;
  }

  updateDml0Socket(sample) {
    const el = document.getElementById("socket-dml0-metrics");
    if (!el) return;
    el.innerHTML = `
      <span class="pill pill-na" title="Windows DirectML compute adapter sensor not available">sensors n/a</span>
    `;
  }

  updateDml1Socket(sample) {
    const el = document.getElementById("socket-dml1-metrics");
    if (!el) return;

    const pwr = sample.nvml_power_w !== null && sample.nvml_power_w !== undefined ? `${sample.nvml_power_w.toFixed(1)} W` : "n/a";
    const temp = sample.nvml_temp_c !== null && sample.nvml_temp_c !== undefined ? `${sample.nvml_temp_c}°C` : "n/a";
    const pstate = sample.nvml_pstate !== null && sample.nvml_pstate !== undefined ? sample.nvml_pstate : "";
    const clk = sample.nvml_clock_mhz !== null && sample.nvml_clock_mhz !== undefined ? `${sample.nvml_clock_mhz} MHz` : "";

    el.innerHTML = `
      <span>pwr <strong>${pwr}</strong></span>
      <span>temp <strong>${temp}</strong></span>
      ${clk ? `<span>${clk}</span>` : ""}
      ${pstate ? `<span class="pill pill-info">${pstate}</span>` : ""}
    `;
  }

  drawSparkline(canvasId, values, strokeColor) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || values.length < 2) return;
    const ctx = canvas.getContext("2d");
    const w = canvas.width;
    const h = canvas.height;

    ctx.clearRect(0, 0, w, h);
    ctx.strokeStyle = strokeColor;
    ctx.lineWidth = 1.5;
    ctx.beginPath();

    const max = 100;
    const step = w / (this.maxHistory - 1);

    values.forEach((v, idx) => {
      const x = idx * step;
      const y = h - (Math.min(v, max) / max) * (h - 4) - 2;
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });

    ctx.stroke();
  }

  handleError(err) {
    const chipLive = document.getElementById("chip-live-status");
    if (chipLive) {
      chipLive.innerHTML = `<span class="pill pill-warn" title="Connecting to live telemetry stream...">connecting</span>`;
    }
  }
}
