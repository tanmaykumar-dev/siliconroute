/**
 * SiliconRoute Design Spec v3: Socket Strip Component (Section 4)
 * Signature full-width strip under top bar. Columns separated by 1px rules.
 * Highlights chosen socket with solid --red fill on routing decisions.
 */

export class SocketStrip {
  constructor(api) {
    this.api = api;
    this.container = document.getElementById("socket-strip");
    this.devices = [];
    this.deviceSockets = new Map(); // dev.id -> DOM element
  }

  async init() {
    if (!this.container) return;
    try {
      this.devices = await this.api.getDevices();
    } catch (err) {
      console.error("Failed to load devices for socket strip:", err);
      this.devices = [];
    }

    this.render();
    this.bindEvents();
  }

  getChipMark(kind, vendor, label) {
    const k = (kind || "").toLowerCase();
    const l = (label || "").toLowerCase();
    if (k === "cpu" || l.includes("cpu") || l.includes("ryzen")) {
      return { mark: "■", cls: "cpu", defaultLabel: "CPU" };
    }
    if (k === "npu" || l.includes("npu") || l.includes("hexagon")) {
      return { mark: "◆", cls: "npu", defaultLabel: "Hexagon NPU" };
    }
    if (k === "dgpu" || l.includes("rtx") || l.includes("geforce") || l.includes("discrete")) {
      return { mark: "●", cls: "dgpu", defaultLabel: "RTX 5070 Laptop" };
    }
    // Default to integrated GPU
    return { mark: "▲", cls: "igpu", defaultLabel: "Radeon 610M" };
  }

  render() {
    this.container.innerHTML = "";
    this.deviceSockets.clear();

    if (!this.devices.length) {
      // Fallback default sockets per spec
      this.devices = [
        { id: 1, key: "cpu", label: "CPU", kind: "cpu", is_available: true },
        { id: 2, key: "dml:0", label: "Radeon 610M", kind: "igpu", is_available: true },
        { id: 3, key: "dml:1", label: "RTX 5070 Laptop", kind: "dgpu", is_available: true },
      ];
    }

    // Filter to available devices or show up to 4
    const validDevices = this.devices.filter(d => d.is_available !== false);

    validDevices.forEach(dev => {
      const { mark, cls } = this.getChipMark(dev.kind, dev.vendor, dev.label);
      const isVerified = dev.vendor_id || dev.key === "cpu";

      const socketEl = document.createElement("div");
      socketEl.className = "socket-item socket-card";
      socketEl.dataset.deviceId = dev.id;
      socketEl.dataset.deviceKey = dev.key;

      socketEl.innerHTML = `
        <div class="socket-header">
          <div class="socket-name-group">
            <span class="socket-mark ${cls}">${mark}</span>
            <span class="socket-label">${dev.label || dev.key}</span>
          </div>
          <span class="tag ${isVerified ? 'tag-verified' : 'tag-hypothesis'}">
            ${isVerified ? 'verified' : 'unverified'}
          </span>
        </div>
        <div class="socket-live-metrics" id="socket-telemetry-${dev.id}">
          <span class="sock-load">load: --%</span>, 
          <span class="sock-power">power: -- W</span>, 
          <span class="sock-temp">temp: -- °C</span>, 
          <span class="sock-clock">clock: -- MHz</span>
        </div>
        <div class="socket-prediction" id="socket-prediction-${dev.id}">
          ready
        </div>
      `;

      this.container.appendChild(socketEl);
      this.deviceSockets.set(dev.id, socketEl);
    });
  }

  bindEvents() {
    // Listen for live telemetry
    window.addEventListener("telemetry", (e) => {
      this.updateTelemetry(e.detail);
    });

    // Listen for routing decisions
    window.addEventListener("routedecision", (e) => {
      this.applyDecision(e.detail);
    });
  }

  updateTelemetry(telemetry) {
    if (!telemetry) return;

    // Update top bar telemetry
    const topbar = document.getElementById("topbar-telemetry");
    if (topbar) {
      const powerScheme = telemetry.power_scheme || (telemetry.is_charging ? "plugged in" : "on battery");
      const battPct = telemetry.battery_pct != null ? `battery ${telemetry.battery_pct}%` : "battery n/a";
      topbar.innerHTML = `
        <span>${powerScheme}</span>
        <span class="telemetry-divider">|</span>
        <span>${battPct}</span>
        <span class="telemetry-divider">|</span>
        <span>live</span>
      `;
    }

    // Update per-socket metrics
    this.devices.forEach(dev => {
      const telWrap = document.getElementById(`socket-telemetry-${dev.id}`);
      if (!telWrap) return;

      const k = (dev.kind || "").toLowerCase();
      const l = (dev.label || "").toLowerCase();

      let loadStr = "load: not available";
      let powerStr = "power: not available";
      let tempStr = "temp: not available";
      let clockStr = "clock: not available";

      if (k === "cpu" || l.includes("cpu")) {
        if (telemetry.cpu_util_pct != null) loadStr = `load: ${telemetry.cpu_util_pct.toFixed(0)}%`;
      } else if (l.includes("rtx") || k === "dgpu") {
        if (telemetry.gpu_util_pct != null) loadStr = `load: ${telemetry.gpu_util_pct.toFixed(0)}%`;
        if (telemetry.gpu_power_w != null) powerStr = `power: ${telemetry.gpu_power_w.toFixed(1)} W`;
        if (telemetry.gpu_temp_c != null) tempStr = `temp: ${telemetry.gpu_temp_c.toFixed(0)} °C`;
        if (telemetry.gpu_clock_sm_mhz != null) clockStr = `clock: ${telemetry.gpu_clock_sm_mhz} MHz`;
      }

      telWrap.innerHTML = `
        <span class="sock-load">${loadStr}</span>, 
        <span class="sock-power">${powerStr}</span>, 
        <span class="sock-temp">${tempStr}</span>, 
        <span class="sock-clock">${clockStr}</span>
      `;
    });
  }

  applyDecision(decision) {
    if (!decision) return;

    const chosenId = decision.chosen_device_id;
    const candidates = decision.candidates || [];

    this.deviceSockets.forEach((socketEl, devId) => {
      const isChosen = devId === chosenId;
      const predEl = document.getElementById(`socket-prediction-${devId}`);

      // Find candidate score/latency
      const cand = candidates.find(c => c.device_id === devId);
      const latencyMs = cand ? (cand.final_score_ms || cand.predicted_latency_ms) : null;
      const latText = latencyMs != null ? `${latencyMs.toFixed(3)} ms` : "n/a";

      if (isChosen) {
        socketEl.classList.add("chosen");
        if (predEl) predEl.textContent = `chosen (${latText})`;
      } else {
        socketEl.classList.remove("chosen");
        if (predEl) predEl.textContent = latText;
      }
    });
  }
}
