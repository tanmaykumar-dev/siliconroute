/**
 * SiliconRoute Phase 6 Dashboard Main Application
 * Connects vanilla JS UI to FastAPI backend endpoints via REST and SSE.
 */

import { SiliconCharts } from "./charts.js";

class SiliconApp {
  constructor() {
    this.charts = new SiliconCharts();
    this.activeTab = "live";
    this.telemetryBuffer = [];
    this.sseSource = null;
    this.models = [];
    this.devices = [];
    this.systemInfo = null;

    // Analysis options
    this.analysisFamily = "mlp";
    this.analysisBatch = 1;

    // Router state
    this.routerModelId = null;
    this.routerBatch = 1;
    this.routerMode = "fastest";
    this.routerWorkload = "sustained";
    this.routerPowerBudget = null;
    this.routerExplore = true;
  }

  async init() {
    this.setupTabNavigation();
    this.charts.initLiveCharts();

    await this.loadInitialMetadata();
    this.connectTelemetryStream();

    this.setupAnalysisControls();
    this.setupRouterControls();
    this.setupModalControls();

    // Load initial tab content
    await this.loadAnalysisData();
    await this.loadRouterEvaluationStats();
  }

  // ---------------------------------------------------------------------------
  // Tab Navigation
  // ---------------------------------------------------------------------------
  setupTabNavigation() {
    const tabs = document.querySelectorAll(".nav-tab");
    tabs.forEach((tab) => {
      tab.addEventListener("click", () => {
        const targetId = tab.dataset.tab;
        this.switchTab(targetId);
      });
    });
  }

  switchTab(tabId) {
    this.activeTab = tabId;
    document.querySelectorAll(".nav-tab").forEach((t) => {
      t.classList.toggle("active", t.dataset.tab === tabId);
    });
    document.querySelectorAll(".tab-pane").forEach((pane) => {
      pane.classList.toggle("active", pane.id === `tab-${tabId}`);
    });

    if (tabId === "analysis") {
      this.loadAnalysisData();
    } else if (tabId === "router") {
      this.getRouterRecommendation();
      this.loadRouterEvaluationStats();
    }
  }

  // ---------------------------------------------------------------------------
  // Initial Metadata (System info & Devices)
  // ---------------------------------------------------------------------------
  async loadInitialMetadata() {
    try {
      const [sysRes, devRes, modRes] = await Promise.all([
        fetch("/api/system").then((r) => r.json()),
        fetch("/api/devices").then((r) => r.json()),
        fetch("/api/models").then((r) => r.json()),
      ]);

      this.systemInfo = sysRes;
      this.devices = devRes;
      this.models = modRes;

      this.renderTopStatusChips();
      this.renderDevicePanel();
      this.populateRouterModelsDropdown();
    } catch (err) {
      console.error("Failed loading initial system metadata:", err);
    }
  }

  renderTopStatusChips() {
    const sys = this.systemInfo;
    if (!sys) return;

    const sysChip = document.getElementById("chip-system");
    if (sysChip) {
      sysChip.textContent = `${sys.cpu_name} | ${sys.ram_gb} GB RAM`;
    }

    const pwrChip = document.getElementById("chip-power");
    if (pwrChip) {
      pwrChip.textContent = sys.plugged_in ? "AC Power Connected" : `On Battery (${sys.battery?.percent || 0}%)`;
    }
  }

  renderDevicePanel() {
    const container = document.getElementById("devices-panel-cards");
    if (!container) return;

    container.innerHTML = this.devices
      .map((d) => {
        const vendor = d.vendor || (d.kind === "cpu" ? "AMD / x86" : "Unknown");
        const vendorId = d.vendor_id || (d.kind === "cpu" ? "N/A" : "Unknown");
        const luid = d.luid || "N/A";
        const badgeClass = d.key === "cpu" ? "badge-cpu" : d.key === "dml:0" ? "badge-dml0" : "badge-dml1";

        return `
          <div class="kpi-card">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom: 0.25rem;">
              <span class="badge-device ${badgeClass}">${d.key.toUpperCase()}</span>
              <span style="font-size:0.75rem; color:${d.is_available ? "var(--mint)" : "var(--muted)"};">
                ${d.is_available ? "● Available" : "○ Offline"}
              </span>
            </div>
            <div style="font-weight:600; font-size:0.95rem; color:var(--text);">${d.label}</div>
            <div style="margin-top:0.5rem; display:flex; flex-direction:column; gap:0.2rem; font-size:0.75rem; color:var(--muted);" class="td-mono">
              <div>Vendor: <strong style="color:var(--text);">${vendor}</strong> (${vendorId})</div>
              <div>DXGI LUID: <strong style="color:var(--text);">${luid}</strong></div>
              <div>ORT Provider: <strong style="color:var(--text);">${d.provider}</strong></div>
            </div>
          </div>
        `;
      })
      .join("");
  }

  // ---------------------------------------------------------------------------
  // Live Telemetry (SSE & Buffer)
  // ---------------------------------------------------------------------------
  connectTelemetryStream() {
    if (this.sseSource) {
      this.sseSource.close();
    }

    const sseDot = document.getElementById("sse-status-dot");
    const sseText = document.getElementById("sse-status-text");

    // Fetch initial ring buffer samples
    fetch("/api/telemetry?seconds=60")
      .then((r) => r.json())
      .then((samples) => {
        if (Array.isArray(samples)) {
          this.telemetryBuffer = samples;
          this.charts.updateLiveTelemetry(this.telemetryBuffer);
          if (samples.length > 0) {
            this.updateLiveKpis(samples[samples.length - 1]);
          }
        }
      })
      .catch((err) => console.warn("Initial telemetry fetch failed:", err));

    this.sseSource = new EventSource("/api/telemetry/stream");

    this.sseSource.onopen = () => {
      if (sseDot) sseDot.className = "status-dot online";
      if (sseText) sseText.textContent = "Live Telemetry: 1 Hz Stream Active";
    };

    this.sseSource.onmessage = (event) => {
      try {
        const sample = JSON.parse(event.data);
        this.telemetryBuffer.push(sample);
        if (this.telemetryBuffer.length > 60) {
          this.telemetryBuffer.shift();
        }
        this.charts.updateLiveTelemetry(this.telemetryBuffer);
        this.updateLiveKpis(sample);
      } catch (e) {
        console.error("Error parsing SSE sample:", e);
      }
    };

    this.sseSource.onerror = () => {
      if (sseDot) sseDot.className = "status-dot warning";
      if (sseText) sseText.textContent = "Telemetry Reconnecting...";
    };
  }

  updateLiveKpis(sample) {
    if (!sample) return;

    // CPU %
    const elCpu = document.getElementById("kpi-cpu-pct");
    if (elCpu) elCpu.textContent = `${sample.cpu_pct.toFixed(1)}%`;

    // CPU Freq: Windows static base clock per Hard Rule 1
    const elCpuFreq = document.getElementById("kpi-cpu-freq");
    if (elCpuFreq) {
      if (sample.cpu_freq_mhz === null || sample.cpu_freq_mhz === undefined) {
        elCpuFreq.innerHTML = `<span class="pill-na" data-tooltip="On Windows, psutil reports static base clock rather than live boost clock; SiliconRoute stores NULL instead of fake constants per Hard Rule 1.">not available</span>`;
      } else {
        elCpuFreq.textContent = `${sample.cpu_freq_mhz.toFixed(0)} MHz`;
      }
    }

    // RAM %
    const elRam = document.getElementById("kpi-ram-pct");
    if (elRam) elRam.textContent = `${sample.ram_pct.toFixed(1)}%`;

    // RTX Power
    const elGpuPower = document.getElementById("kpi-gpu-power");
    if (elGpuPower) {
      elGpuPower.textContent = sample.gpu_power_w !== null ? `${sample.gpu_power_w.toFixed(1)} W` : "N/A";
    }

    // AMD iGPU Power: Not available
    const elIgpuPower = document.getElementById("kpi-igpu-power");
    if (elIgpuPower) {
      elIgpuPower.innerHTML = `<span class="pill-na" data-tooltip="DirectML provides no hardware power sensor for AMD APU iGPU; SiliconRoute never guesses or approximates power per Hard Rule 1.">not available</span>`;
    }

    // RTX Temp
    const elGpuTemp = document.getElementById("kpi-gpu-temp");
    if (elGpuTemp) {
      elGpuTemp.textContent = sample.gpu_temp_c !== null ? `${sample.gpu_temp_c.toFixed(0)} °C` : "N/A";
    }

    // RTX P-state
    const elPstate = document.getElementById("kpi-gpu-pstate");
    if (elPstate) {
      elPstate.textContent = sample.gpu_pstate !== null ? `P${sample.gpu_pstate}` : "N/A";
    }

    // SM Clock
    const elClock = document.getElementById("kpi-gpu-clock");
    if (elClock) {
      elClock.textContent = sample.gpu_clock_sm_mhz !== null ? `${sample.gpu_clock_sm_mhz} MHz` : "N/A";
    }

    // Battery Discharge
    const elBatt = document.getElementById("kpi-battery-discharge");
    if (elBatt) {
      if (sample.plugged_in) {
        elBatt.innerHTML = `<span style="font-size:1.1rem; color:var(--mint); font-weight:600;">Plugged In (AC)</span>`;
      } else if (sample.discharge_w !== null) {
        elBatt.textContent = `${sample.discharge_w.toFixed(2)} W`;
      } else {
        elBatt.innerHTML = `<span class="pill-na" data-tooltip="Battery DischargeRate WMI sensor not returning rate while charging.">not available</span>`;
      }
    }
  }

  // ---------------------------------------------------------------------------
  // Analysis Tab Operations
  // ---------------------------------------------------------------------------
  setupAnalysisControls() {
    const selFamily = document.getElementById("analysis-family-select");
    const selBatch = document.getElementById("analysis-batch-select");

    if (selFamily) {
      selFamily.addEventListener("change", (e) => {
        this.analysisFamily = e.target.value;
        this.loadAnalysisData();
      });
    }

    if (selBatch) {
      selBatch.addEventListener("change", (e) => {
        this.analysisBatch = parseInt(e.target.value, 10);
        this.loadAnalysisData();
      });
    }
  }

  async loadAnalysisData() {
    try {
      // 1. Chart Data
      const chartRes = await fetch(
        `/api/analysis/chart-data?family=${this.analysisFamily}&batch=${this.analysisBatch}`
      ).then((r) => r.json());

      this.charts.renderLogLogChart(chartRes, (runId) => this.openRunInspector(runId));

      // 2. Fits physical parameters table
      this.renderPhysicalFitsTable(chartRes.fits);

      // 3. Crossover table
      const crossovers = await fetch("/api/analysis/crossovers-all").then((r) => r.json());
      this.renderCrossoversTable(crossovers);

      // 4. Variability table
      const variability = await fetch("/api/analysis/variability").then((r) => r.json());
      this.renderVariabilityTable(variability);

      // 5. Wake & Cold-Start table
      const wakeCold = await fetch("/api/analysis/wake-cold").then((r) => r.json());
      this.renderWakeColdTable(wakeCold);

      // 6. Physics Notes
      const physics = await fetch("/api/analysis/physics-notes").then((r) => r.json());
      this.renderPhysicsNotesTable(physics);
    } catch (err) {
      console.error("Failed loading analysis data:", err);
    }
  }

  renderPhysicalFitsTable(fits) {
    const tbody = document.getElementById("table-fits-body");
    if (!tbody || !fits) return;

    tbody.innerHTML = Object.entries(fits)
      .map(([devKey, f]) => {
        const badgeClass = devKey === "cpu" ? "badge-cpu" : devKey === "dml:0" ? "badge-dml0" : "badge-dml1";
        const dramText = (f.model_form === "f4_family" || devKey === "dml:1" || f.dram_bandwidth_gb_s === null || f.dram_bandwidth_gb_s === undefined)
          ? "n/a"
          : `${f.dram_bandwidth_gb_s.toFixed(1)} GB/s`;
        const vramText = f.sram_bandwidth_gb_s
          ? (devKey === "dml:1" ? `${f.sram_bandwidth_gb_s.toFixed(1)} GB/s (VRAM)` : `${f.sram_bandwidth_gb_s.toFixed(1)} GB/s`)
          : "n/a";
        return `
          <tr>
            <td><span class="badge-device ${badgeClass}">${devKey.toUpperCase()}</span></td>
            <td>${f.model_form || "F1 (affine)"}</td>
            <td class="td-mono text-right">${f.t0_ms.toFixed(4)} ms</td>
            <td class="td-mono text-right">${f.compute_gflops.toFixed(1)} GFLOP/s <span style="font-size:0.75rem; color:var(--muted);">(effective)</span></td>
            <td class="td-mono text-right">${dramText}</td>
            <td class="td-mono text-right">${vramText}</td>
            <td class="td-mono text-right">${f.loo_mape_pct !== null ? f.loo_mape_pct.toFixed(1) + "%" : "N/A"}</td>
          </tr>
        `;
      })
      .join("");
  }

  renderCrossoversTable(crossovers) {
    const tbody = document.getElementById("table-crossover-body");
    if (!tbody) return;

    tbody.innerHTML = crossovers
      .map((c) => {
        const co = c.crossover;
        const switchedBadge = co ? (co.switched_to === "cpu" ? "badge-cpu" : co.switched_to === "dml:0" ? "badge-dml0" : "badge-dml1") : "";
        const outcomeHtml = co
          ? `<span class="badge-device ${switchedBadge}">${co.switched_to.toUpperCase()} becomes faster</span>`
          : `<span style="color:var(--muted);">${c.summary}</span>`;
        return `
          <tr>
            <td style="font-weight:600;">${c.dev_a.toUpperCase()} vs ${c.dev_b.toUpperCase()}</td>
            <td>${c.family.toUpperCase()}</td>
            <td class="td-mono text-center">B=${c.batch}</td>
            <td class="td-mono text-right">${co ? Number(co.params).toLocaleString() + " params" : "None in range"}</td>
            <td class="td-mono text-right">${co ? "Width " + co.width : "N/A"}</td>
            <td>${outcomeHtml}</td>
          </tr>
        `;
      })
      .join("");
  }

  renderVariabilityTable(variability) {
    const summaryTbody = document.getElementById("table-variability-summary-body");
    if (summaryTbody) {
      summaryTbody.innerHTML = variability.summary
        .map((s) => {
          const badgeClass = s.device_key === "cpu" ? "badge-cpu" : s.device_key === "dml:0" ? "badge-dml0" : "badge-dml1";
          return `
            <tr>
              <td><span class="badge-device ${badgeClass}">${s.device_key.toUpperCase()}</span></td>
              <td>${s.device_label}</td>
              <td class="td-mono text-right" style="font-weight:700; color:var(--text);">+/-${s.volatility_band_pct.toFixed(1)}%</td>
              <td class="td-mono text-right">${s.multi_session_configs_count} configs</td>
              <td style="color:var(--muted); font-size:0.8rem;">${s.description}</td>
            </tr>
          `;
        })
        .join("");
    }

    const detailsTbody = document.getElementById("table-variability-details-body");
    if (detailsTbody) {
      detailsTbody.innerHTML = variability.details
        .slice(0, 15) // Top 15 multi-session configs
        .map((d) => {
          const sessStr = Object.entries(d.sessions)
            .map(([sid, med]) => `S${sid}: ${med.toFixed(3)}ms`)
            .join(", ");
          return `
            <tr>
              <td><span class="badge-device ${d.device_key === "cpu" ? "badge-cpu" : d.device_key === "dml:0" ? "badge-dml0" : "badge-dml1"}">${d.device_key}</span></td>
              <td>${d.model_name}</td>
              <td class="td-mono text-center">B=${d.batch}</td>
              <td class="td-mono text-center">${d.session_count}</td>
              <td class="td-mono text-right">${d.min_median_ms.toFixed(3)} ms</td>
              <td class="td-mono text-right">${d.max_median_ms.toFixed(3)} ms</td>
              <td class="td-mono text-right" style="color: ${d.diff_pct > 20 ? "var(--warning)" : "var(--mint)"}; font-weight:600;">${d.diff_pct.toFixed(1)}%</td>
              <td class="td-mono" style="font-size:0.75rem; color:var(--muted);">${sessStr}</td>
            </tr>
          `;
        })
        .join("");
    }
  }

  renderWakeColdTable(wakeCold) {
    const tbody = document.getElementById("table-wake-cold-body");
    if (!tbody) return;

    tbody.innerHTML = (wakeCold.summary || [])
      .map((w) => {
        const badgeClass = w.device_key === "cpu" ? "badge-cpu" : w.device_key === "dml:0" ? "badge-dml0" : "badge-dml1";
        const p8Text = w.p8_sleep_penalty_ms !== undefined ? `+${w.p8_sleep_penalty_ms.toFixed(3)} ms (P8 sleep)` : "N/A";
        return `
          <tr>
            <td><span class="badge-device ${badgeClass}">${w.device_key.toUpperCase()}</span></td>
            <td>${w.device_label}</td>
            <td class="td-mono text-right">${w.sample_count}</td>
            <td class="td-mono text-right">${w.median_first_run_ms !== null ? w.median_first_run_ms.toFixed(3) + " ms" : "N/A"}</td>
            <td class="td-mono text-right" style="font-weight:600; color:var(--text);">${w.median_wake_penalty_ms !== null ? "+" + w.median_wake_penalty_ms.toFixed(3) + " ms" : "N/A"}</td>
            <td class="td-mono text-right" style="color:var(--muted); font-size:0.8rem;">${p8Text}</td>
          </tr>
        `;
      })
      .join("");
  }

  renderPhysicsNotesTable(physics) {
    const tbody = document.getElementById("table-physics-notes-body");
    if (!tbody) return;

    tbody.innerHTML = (physics.runs || [])
      .map((r) => {
        const badgeClass = r.device_key === "dml:0" ? "badge-dml0" : "badge-dml1";
        return `
          <tr style="cursor:pointer;" onclick="window.__app.openRunInspector(${r.run_id})">
            <td class="td-mono" style="font-weight:600; color:var(--accent-copper);">#${r.run_id}</td>
            <td class="td-mono">S${r.session_id}</td>
            <td><span class="badge-device ${badgeClass}">${r.device_key}</span></td>
            <td>${r.model_name}</td>
            <td class="td-mono text-center">B=${r.batch}</td>
            <td class="td-mono text-right">${r.median_ms.toFixed(3)} ms</td>
            <td class="td-mono text-right" style="font-weight:700; color:var(--mint);">${r.implied_gflops.toFixed(1)} GFLOP/s <span style="font-size:0.75rem; color:var(--muted);">(effective)</span></td>
            <td class="td-mono text-right" style="color:var(--muted);">${r.datasheet_peak_gflops} GFLOP/s <span style="font-size:0.7rem;">[datasheet, not measured]</span></td>
            <td style="font-size:0.8rem; color:${r.identity_suspect ? "var(--error)" : "var(--text)"};">${r.physics_note || "Algorithmic Winograd speedup"}</td>
          </tr>
        `;
      })
      .join("");
  }

  // ---------------------------------------------------------------------------
  // Run Raw Timing Samples Inspector Modal
  // ---------------------------------------------------------------------------
  setupModalControls() {
    const overlay = document.getElementById("modal-run-inspector");
    const closeBtn = document.getElementById("modal-close-btn");

    if (closeBtn) {
      closeBtn.addEventListener("click", () => {
        if (overlay) overlay.classList.remove("open");
      });
    }

    if (overlay) {
      overlay.addEventListener("click", (e) => {
        if (e.target === overlay) {
          overlay.classList.remove("open");
        }
      });
    }
  }

  async openRunInspector(runId) {
    try {
      const res = await fetch(`/api/runs/${runId}`);
      if (!res.ok) {
        alert(`Run #${runId} not found`);
        return;
      }
      const run = await res.json();

      // Find model & device metadata
      const dev = this.devices.find((d) => d.id === run.device_id) || { key: "unknown", label: "Unknown Device" };
      const model = this.models.find((m) => m.id === run.ai_model_id) || { name: `Model #${run.ai_model_id}` };

      run.device_key = dev.key;
      run.device_label = dev.label;
      run.model_name = model.name;

      document.getElementById("modal-run-id").textContent = `#${run.id}`;
      document.getElementById("modal-model-name").textContent = `${model.name} (Batch ${run.batch})`;
      document.getElementById("modal-device-badge").innerHTML = `<span class="badge-device ${dev.key === "cpu" ? "badge-cpu" : dev.key === "dml:0" ? "badge-dml0" : "badge-dml1"}">${dev.key.toUpperCase()} - ${dev.label}</span>`;

      // Crucial requirement: Prominently display inner_loop_k!
      const kVal = run.inner_loop_k !== null && run.inner_loop_k !== undefined ? run.inner_loop_k : 1;
      document.getElementById("modal-inner-loop-k").textContent = `inner_loop_k = ${kVal}`;

      document.getElementById("modal-median-ms").textContent = `${run.median_ms.toFixed(4)} ms`;
      document.getElementById("modal-p10-ms").textContent = run.p10_ms !== null ? `${run.p10_ms.toFixed(4)} ms` : "N/A";
      document.getElementById("modal-p90-ms").textContent = run.p90_ms !== null ? `${run.p90_ms.toFixed(4)} ms` : "N/A";

      // Compute spread as Math.max(...samples) - Math.min(...samples)
      let sampleSpread = null;
      let rawSamples = [];
      try {
        rawSamples = JSON.parse(run.raw_ms_json || "[]");
      } catch (e) {
        rawSamples = [];
      }
      if (rawSamples.length > 0) {
        sampleSpread = Math.max(...rawSamples) - Math.min(...rawSamples);
      } else if (run.max_ms !== null && run.min_ms !== null) {
        sampleSpread = run.max_ms - run.min_ms;
      }
      document.getElementById("modal-spread-ms").textContent = sampleSpread !== null ? `${sampleSpread.toFixed(4)} ms` : "N/A";
      document.getElementById("modal-cv").textContent = run.cv !== null ? `${(run.cv * 100).toFixed(2)}%` : "N/A";

      this.charts.renderRawSamplesChart(run);

      const overlay = document.getElementById("modal-run-inspector");
      if (overlay) overlay.classList.add("open");
    } catch (err) {
      console.error("Error opening run inspector:", err);
    }
  }

  // ---------------------------------------------------------------------------
  // Router Tab Operations
  // ---------------------------------------------------------------------------
  populateRouterModelsDropdown() {
    const sel = document.getElementById("router-model-select");
    if (!sel || !this.models.length) return;

    sel.innerHTML = this.models
      .map((m) => {
        const mb = (m.weight_bytes / (1024 * 1024)).toFixed(2);
        return `<option value="${m.id}">${m.name} (${m.family.toUpperCase()}, ${mb} MB)</option>`;
      })
      .join("");

    this.routerModelId = this.models[0].id;
  }

  setupRouterControls() {
    const selModel = document.getElementById("router-model-select");
    const selBatch = document.getElementById("router-batch-select");
    const selMode = document.getElementById("router-mode-select");
    const selWorkload = document.getElementById("router-workload-select");
    const inpBudget = document.getElementById("router-budget-input");
    const chkExplore = document.getElementById("router-explore-check");
    const btnVerify = document.getElementById("btn-run-verify");

    if (selModel) {
      selModel.addEventListener("change", (e) => {
        this.routerModelId = parseInt(e.target.value, 10);
        this.getRouterRecommendation();
      });
    }

    if (selBatch) {
      selBatch.addEventListener("change", (e) => {
        this.routerBatch = parseInt(e.target.value, 10);
        this.getRouterRecommendation();
      });
    }

    if (selMode) {
      selMode.addEventListener("change", (e) => {
        this.routerMode = e.target.value;
        this.getRouterRecommendation();
      });
    }

    if (selWorkload) {
      selWorkload.addEventListener("change", (e) => {
        this.routerWorkload = e.target.value;
        this.getRouterRecommendation();
      });
    }

    if (inpBudget) {
      inpBudget.addEventListener("input", (e) => {
        const val = parseFloat(e.target.value);
        this.routerPowerBudget = isNaN(val) ? null : val;
        this.getRouterRecommendation();
      });
    }

    if (chkExplore) {
      chkExplore.addEventListener("change", (e) => {
        this.routerExplore = e.target.checked;
        this.getRouterRecommendation();
      });
    }

    if (btnVerify) {
      btnVerify.addEventListener("click", () => {
        this.executeRouterVerification();
      });
    }
  }

  async getRouterRecommendation() {
    if (!this.routerModelId) return;

    const payload = {
      ai_model_id: this.routerModelId,
      batch: this.routerBatch,
      mode: this.routerMode,
      workload: this.routerWorkload,
      power_budget_w: this.routerPowerBudget,
      allow_explore: this.routerExplore,
      verify: false,
    };

    try {
      const res = await fetch("/api/route", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json();
        console.error("Router error:", err);
        return;
      }

      const dec = await res.json();
      this.renderDecisionCard(dec);
    } catch (err) {
      console.error("Failed fetching router recommendation:", err);
    }
  }

  renderDecisionCard(dec) {
    const badgeClass = dec.chosen_device_key === "cpu" ? "badge-cpu" : dec.chosen_device_key === "dml:0" ? "badge-dml0" : "badge-dml1";
    const dev = this.devices.find((d) => d.id === dec.chosen_device_id) || { label: dec.chosen_device_key };

    document.getElementById("router-chosen-badge").innerHTML = `<span class="badge-device ${badgeClass}" style="font-size:1.1rem; padding:0.35rem 0.85rem;">${dec.chosen_device_key.toUpperCase()} - ${dev.label}</span>`;
    document.getElementById("router-reason-text").textContent = dec.reason;

    const rulesEl = document.getElementById("router-rules-list");
    if (rulesEl) {
      if (dec.context_rules && dec.context_rules.length) {
        rulesEl.innerHTML = dec.context_rules.map((r) => `<li>${r}</li>`).join("");
      } else {
        rulesEl.innerHTML = "<li>Standard nominal hardware operating environment.</li>";
      }
    }

    // Candidates table
    const tbody = document.getElementById("table-candidates-body");
    if (tbody && dec.candidates) {
      tbody.innerHTML = dec.candidates
        .map((c) => {
          const isChosen = c.device_id === dec.chosen_device_id;
          const cBadge = c.device_key === "cpu" ? "badge-cpu" : c.device_key === "dml:0" ? "badge-dml0" : "badge-dml1";
          const wakeStr = c.wake_penalty_ms > 0 ? `+${c.wake_penalty_ms.toFixed(3)} ms` : "0.000 ms";
          const predStr = (c.effective_latency_ms || c.predicted_latency_ms || 0).toFixed(3) + " ms";

          return `
            <tr style="${isChosen ? "background-color: rgba(217, 138, 61, 0.08); font-weight:600;" : ""}">
              <td><span class="badge-device ${cBadge}">${c.device_key.toUpperCase()}</span> ${isChosen ? "★ CHOSEN" : ""}</td>
              <td>${c.device_label}</td>
              <td class="td-mono text-right" style="color:${isChosen ? "var(--accent-copper)" : "var(--text)"};">${predStr}</td>
              <td class="td-mono text-center" style="font-size:0.75rem;"><span style="background:var(--pill-bg); padding:0.15rem 0.45rem; border-radius:3px;">${c.source}</span></td>
              <td class="td-mono text-right" style="color:var(--muted);">${wakeStr}</td>
              <td class="td-mono text-right">${c.score !== undefined ? c.score.toFixed(3) : "N/A"}</td>
              <td style="color:${c.is_excluded ? "var(--error)" : "var(--mint)"}; font-size:0.8rem;">${c.is_excluded ? c.excluded_reason : "Eligible"}</td>
            </tr>
          `;
        })
        .join("");
    }
  }

  async executeRouterVerification() {
    const btn = document.getElementById("btn-run-verify");
    const statusBox = document.getElementById("router-verify-result-box");
    if (!this.routerModelId) return;

    if (btn) {
      btn.disabled = true;
      btn.textContent = "Running Benchmark Verification on Hardware...";
    }

    const payload = {
      ai_model_id: this.routerModelId,
      batch: this.routerBatch,
      mode: this.routerMode,
      workload: this.routerWorkload,
      power_budget_w: this.routerPowerBudget,
      allow_explore: this.routerExplore,
      verify: true,
    };

    try {
      const res = await fetch("/api/route", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const err = await res.json();
        alert(`Verification failed: ${err.detail || "Hardware benchmark conflict"}`);
        return;
      }

      const dec = await res.json();
      this.renderDecisionCard(dec);

      // Display verification results
      if (statusBox) {
        statusBox.style.display = "block";
        const isWin = dec.was_best;
        const bestDev = this.devices.find((d) => d.id === dec.best_device_id_actual) || { key: "Unknown" };

        statusBox.innerHTML = `
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.75rem;">
            <div style="font-weight:700; font-size:1.05rem;">Verification Benchmark Complete</div>
            <span class="${isWin ? "badge-win" : "badge-loss"}">${isWin ? "OPTIMAL CHOICE (WIN)" : "SUBOPTIMAL (LOSS)"}</span>
          </div>
          <div class="grid-3" style="margin-bottom:0.75rem;">
            <div>
              <span class="kpi-label">Actual Chosen Latency:</span>
              <div class="td-mono" style="font-size:1.3rem; font-weight:700; color:var(--text);">${dec.actual_ms.toFixed(3)} ms</div>
            </div>
            <div>
              <span class="kpi-label">Physically Best Device:</span>
              <div class="td-mono" style="font-size:1.3rem; font-weight:700; color:var(--mint);">${bestDev.key.toUpperCase()}</div>
            </div>
            <div>
              <span class="kpi-label">Slowdown / Regret:</span>
              <div class="td-mono" style="font-size:1.3rem; font-weight:700; color:${dec.regret_pct > 0 ? "var(--warning)" : "var(--mint)"};">${dec.regret_pct.toFixed(2)}%</div>
            </div>
          </div>
        `;
      }
    } catch (err) {
      console.error("Verification execution error:", err);
      alert(`Verification error: ${err.message}`);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "Run & Verify on Hardware";
      }
    }
  }

  async loadRouterEvaluationStats() {
    try {
      // Specifically query Phase 5.3 evaluation decisions 93 to 116
      const stats = await fetch("/api/decisions/stats?ids=93-116").then((r) => r.json());
      const decisions = await fetch("/api/decisions?limit=30").then((r) => r.json());

      this.renderEvaluationOverallTable(stats);
      this.renderEvaluationWorkloadsTable(stats.per_workload);
      this.renderDecisionsLogTable(decisions.filter((d) => d.id >= 93 && d.id <= 116));
    } catch (err) {
      console.error("Failed loading router evaluation stats:", err);
    }
  }

  renderEvaluationOverallTable(stats) {
    const tbody = document.getElementById("table-eval-overall-body");
    if (!tbody || !stats.siliconroute) return;

    const rows = [
      {
        name: "SiliconRoute (Measured-First + Dynamic)",
        data: stats.siliconroute,
        isSr: true,
      },
      {
        name: "Fit-Only Router (Formula without Lookups)",
        data: stats.baselines.fit_only_router,
      },
      {
        name: "Always-CPU Baseline",
        data: stats.baselines.always_cpu,
      },
      {
        name: "Always-RTX Baseline",
        data: stats.baselines.always_rtx,
      },
    ];

    tbody.innerHTML = rows
      .map((r) => {
        const d = r.data;
        return `
          <tr style="${r.isSr ? "background-color: rgba(60, 207, 160, 0.08); font-weight:700;" : ""}">
            <td style="color:${r.isSr ? "var(--mint)" : "var(--text)"};">${r.name}</td>
            <td class="td-mono text-center">${d.wins}/${d.total}</td>
            <td class="td-mono text-right" style="color:${r.isSr ? "var(--mint)" : "var(--text)"};">${d.accuracy_pct.toFixed(1)}%</td>
            <td class="td-mono text-right">${d.mean_regret_pct.toFixed(2)}%</td>
            <td class="td-mono text-right">${d.p90_regret_pct.toFixed(2)}%</td>
          </tr>
        `;
      })
      .join("") + `
        <tr>
          <td style="color:var(--muted);">ORT ExecutionProviderDevicePolicy</td>
          <td colspan="4" style="color:var(--muted); font-size:0.8rem;">
            <span class="pill-na" data-tooltip="ORT ExecutionProviderDevicePolicy was not executed on physical hardware; result would be assumed, not measured">not available</span>
          </td>
        </tr>
      `;
  }

  renderEvaluationWorkloadsTable(perWl) {
    const tbody = document.getElementById("table-eval-workloads-body");
    if (!tbody || !perWl) return;

    const workloads = ["sustained", "idle_loaded", "cold_start"];
    let html = "";

    workloads.forEach((wl) => {
      const data = perWl[wl];
      if (!data) return;

      const strategies = [
        { name: "SiliconRoute", wins: data.wins, total: data.total, acc: data.accuracy_pct, reg: data.mean_regret_pct, p90: data.p90_regret_pct, isSr: true },
        { name: "Always-CPU", wins: data.always_cpu.wins, total: data.total, acc: data.always_cpu.accuracy_pct, reg: data.always_cpu.mean_regret_pct, p90: data.always_cpu.p90_regret_pct },
        { name: "Always-RTX", wins: data.always_rtx.wins, total: data.total, acc: data.always_rtx.accuracy_pct, reg: data.always_rtx.mean_regret_pct, p90: data.always_rtx.p90_regret_pct },
        { name: "Fit-Only", wins: data.fit_only.wins, total: data.total, acc: data.fit_only.accuracy_pct, reg: data.fit_only.mean_regret_pct, p90: data.fit_only.p90_regret_pct },
      ];

      strategies.forEach((st, idx) => {
        html += `
          <tr style="${st.isSr ? "font-weight:600;" : ""}">
            ${idx === 0 ? `<td rowspan="4" style="vertical-align:middle; font-weight:700; border-right:1px solid var(--border);">${wl.toUpperCase()} <br><span style="font-size:0.75rem; color:var(--muted);">(${data.total} decs)</span></td>` : ""}
            <td style="color:${st.isSr ? "var(--mint)" : "var(--text)"};">${st.name}</td>
            <td class="td-mono text-center">${st.wins}/${st.total}</td>
            <td class="td-mono text-right" style="color:${st.isSr ? "var(--mint)" : "var(--text)"};">${st.acc.toFixed(1)}%</td>
            <td class="td-mono text-right">${st.reg.toFixed(2)}%</td>
            <td class="td-mono text-right">${st.p90.toFixed(2)}%</td>
          </tr>
        `;
      });
    });

    tbody.innerHTML = html;
  }

  renderDecisionsLogTable(decs) {
    const tbody = document.getElementById("table-decisions-log-body");
    if (!tbody) return;

    tbody.innerHTML = decs
      .sort((a, b) => b.id - a.id)
      .map((d) => {
        const ctx = typeof d.context_json === "string" ? JSON.parse(d.context_json) : (d.context_json || {});
        const wl = ctx.workload || "sustained";
        const chosenDev = this.devices.find((dev) => dev.id === d.chosen_device_id) || { key: "cpu" };
        const bestDev = this.devices.find((dev) => dev.id === d.best_device_id_actual) || { key: "cpu" };
        const model = this.models.find((m) => m.id === d.ai_model_id) || { name: `Model #${d.ai_model_id}` };

        return `
          <tr>
            <td class="td-mono" style="font-weight:600; color:var(--accent-copper);">#${d.id}</td>
            <td>${model.name}</td>
            <td class="td-mono text-center">B=${d.batch}</td>
            <td class="td-mono text-center"><span style="background:var(--pill-bg); padding:0.15rem 0.45rem; border-radius:3px; font-size:0.75rem;">${wl}</span></td>
            <td><span class="badge-device ${chosenDev.key === "cpu" ? "badge-cpu" : chosenDev.key === "dml:0" ? "badge-dml0" : "badge-dml1"}">${chosenDev.key}</span></td>
            <td class="td-mono text-right">${d.actual_ms ? d.actual_ms.toFixed(3) + " ms" : "N/A"}</td>
            <td><span class="badge-device ${bestDev.key === "cpu" ? "badge-cpu" : bestDev.key === "dml:0" ? "badge-dml0" : "badge-dml1"}">${bestDev.key}</span></td>
            <td class="text-center"><span class="${d.was_best ? "badge-win" : "badge-loss"}">${d.was_best ? "WIN" : "LOSS"}</span></td>
            <td class="td-mono text-right" style="color:${d.regret_pct > 0 ? "var(--warning)" : "var(--mint)"};">${d.regret_pct !== null ? d.regret_pct.toFixed(1) + "%" : "0.0%"}</td>
          </tr>
        `;
      })
      .join("");
  }
}

// Instantiate and attach globally for onclick handlers
window.__app = new SiliconApp();
if (document.readyState === "loading") {
  window.addEventListener("DOMContentLoaded", () => {
    window.__app.init();
  });
} else {
  window.__app.init();
}

