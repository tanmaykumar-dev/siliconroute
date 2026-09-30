/**
 * SiliconRoute Design Spec v2 — Router Screen (Section 6.4)
 * Multi-objective routing, candidate evaluation, transparent rules justification,
 * and the animated SVG Routing Trace signature element.
 */

export class RouterScreen {
  constructor(apiClient) {
    this.api = apiClient;
    this.models = [];
    this.devices = [];
    this.lastDecision = null;
    this.isLoaded = false;
  }

  async init() {
    this.setupControls();
  }

  async onActivate() {
    if (!this.isLoaded) {
      await this.loadInitialMetadata();
      this.isLoaded = true;
    }
  }

  async loadInitialMetadata() {
    try {
      const [models, devices] = await Promise.all([
        this.api.fetchModels(),
        this.api.fetchDevices(),
      ]);
      this.models = models;
      this.devices = devices;
      this.populateModelSelect();
      this.handleRouteTask(false); // initial recommendation
    } catch (err) {
      console.error("Failed loading router metadata:", err);
    }
  }

  populateModelSelect() {
    const sel = document.getElementById("router-model-select");
    if (!sel || !this.models.length) return;
    sel.innerHTML = this.models.map(m => {
      const mb = (m.weight_bytes / (1024 * 1024)).toFixed(1);
      return `<option value="${m.id}">${m.name} (${mb} MB)</option>`;
    }).join("");
  }

  setupControls() {
    const btnRoute = document.getElementById("btn-router-execute");
    const btnVerify = document.getElementById("btn-router-verify");
    const selModel = document.getElementById("router-model-select");
    const selBatch = document.getElementById("router-batch-select");
    const selWorkload = document.getElementById("router-workload-select");
    const selGoal = document.getElementById("router-goal-select");
    const inpBudget = document.getElementById("router-budget-input");
    const chkExplore = document.getElementById("router-explore-check");

    [selModel, selBatch, selWorkload, selGoal, inpBudget, chkExplore].forEach(el => {
      if (el) {
        el.addEventListener("change", () => this.handleRouteTask(false));
      }
    });

    if (btnRoute) {
      btnRoute.addEventListener("click", () => this.handleRouteTask(false));
    }

    if (btnVerify) {
      btnVerify.addEventListener("click", () => this.handleRouteVerify());
    }
  }

  async handleRouteTask(verify = false) {
    const modelId = parseInt(document.getElementById("router-model-select")?.value, 10);
    const batch = parseInt(document.getElementById("router-batch-select")?.value || "1", 10);
    const workload = document.getElementById("router-workload-select")?.value || "sustained";
    const mode = document.getElementById("router-goal-select")?.value || "fastest";
    const budgetVal = parseFloat(document.getElementById("router-budget-input")?.value);
    const powerBudget = isNaN(budgetVal) ? null : budgetVal;
    const allowExplore = document.getElementById("router-explore-check")?.checked || false;

    if (!modelId) return;

    try {
      const dec = await this.api.routeModel({
        ai_model_id: modelId,
        batch,
        workload,
        mode,
        power_budget_w: powerBudget,
        allow_explore: allowExplore,
        verify,
      });

      this.lastDecision = dec;
      this.renderDecision(dec);
      this.drawRoutingTrace(dec);
    } catch (err) {
      console.error("Routing error:", err);
    }
  }

  handleRouteVerify() {
    const confirmed = window.confirm("This runs a short benchmark on all chips (about 10–30 seconds). Continue?");
    if (confirmed) {
      this.handleRouteTask(true);
    }
  }

  renderDecision(dec) {
    const badgeEl = document.getElementById("router-chosen-badge");
    const reasonEl = document.getElementById("router-reason-text");
    const rulesList = document.getElementById("router-rules-list");
    const tbody = document.getElementById("router-candidates-body");

    const dev = this.devices.find(d => d.id === dec.chosen_device_id) || { label: dec.chosen_device_key, key: dec.chosen_device_key };
    const devKey = (dec.chosen_device_key || dev.key || "cpu").toUpperCase();

    if (badgeEl) {
      badgeEl.innerHTML = `
        <span class="chip-label chip-${devKey.toLowerCase() === 'cpu' ? 'cpu' : devKey.toLowerCase().includes('0') ? 'igpu' : 'dgpu'}">
          <strong>${devKey}</strong> — ${dev.label}
        </span>
      `;
    }

    if (reasonEl) {
      reasonEl.textContent = dec.reason;
    }

    if (rulesList) {
      if (dec.context_rules && dec.context_rules.length) {
        rulesList.innerHTML = dec.context_rules.map(r => `<li>${r}</li>`).join("");
      } else {
        rulesList.innerHTML = "<li>Nominal hardware operating environment.</li>";
      }
    }

    if (tbody && dec.candidates) {
      tbody.innerHTML = dec.candidates.map(c => {
        const isChosen = c.device_id === dec.chosen_device_id;
        const predMs = (c.effective_latency_ms || c.predicted_latency_ms || 0).toFixed(3);
        const wakeStr = c.wake_penalty_ms > 0 ? `+${c.wake_penalty_ms.toFixed(3)} ms` : "0.000 ms";
        const scoreStr = c.score !== undefined ? c.score.toFixed(3) : "n/a";
        const statusClass = c.is_excluded ? "pill-bad" : "pill-ok";
        const statusText = c.is_excluded ? c.excluded_reason : "eligible";

        return `
          <tr style="${isChosen ? 'background-color: var(--plate-raised); font-weight:600;' : ''}">
            <td><strong>${c.device_key.toUpperCase()}</strong> ${isChosen ? '★ CHOSEN' : ''}</td>
            <td class="font-mono text-right" style="color:${isChosen ? 'var(--ok)' : 'var(--ink)'};">${predMs} ms</td>
            <td class="text-center"><span class="pill pill-info">${c.source}</span></td>
            <td class="font-mono text-right">${wakeStr}</td>
            <td class="font-mono text-right">${scoreStr}</td>
            <td><span class="pill ${statusClass}">${statusText}</span></td>
          </tr>
        `;
      }).join("");
    }
  }

  drawRoutingTrace(dec) {
    const traceSvg = document.getElementById("routing-trace-svg");
    const chosenKey = dec.chosen_device_key;

    // Highlight socket strip tile
    document.querySelectorAll(".socket-tile").forEach(tile => {
      tile.classList.remove("chosen", "dimmed");
      const isChosen = tile.dataset.deviceKey === chosenKey;
      if (isChosen) {
        tile.classList.add("chosen");
        const lat = tile.querySelector(".socket-predicted-latency");
        const chosenCand = dec.candidates?.find(c => c.device_id === dec.chosen_device_id);
        const latVal = chosenCand ? (chosenCand.effective_latency_ms || chosenCand.predicted_latency_ms) : null;
        if (lat && latVal) lat.textContent = `${latVal.toFixed(3)} ms (chosen)`;
      } else {
        tile.classList.add("dimmed");
      }
    });

    if (!traceSvg) return;

    // SVG trace path animation
    const taskBox = document.getElementById("trace-task-source");
    const destBox = document.getElementById("trace-task-dest");
    if (!taskBox || !destBox) return;

    const tRect = taskBox.getBoundingClientRect();
    const dRect = destBox.getBoundingClientRect();
    const containerRect = traceSvg.getBoundingClientRect();

    const startX = tRect.right - containerRect.left;
    const startY = tRect.top + tRect.height / 2 - containerRect.top;
    const endX = dRect.left - containerRect.left;
    const endY = dRect.top + dRect.height / 2 - containerRect.top;

    const midX = (startX + endX) / 2;
    const pathD = `M ${startX} ${startY} C ${midX} ${startY}, ${midX} ${endY}, ${endX} ${endY}`;

    traceSvg.innerHTML = `
      <path d="${pathD}" fill="none" stroke="var(--ok)" stroke-width="2.5" stroke-dasharray="8 4" stroke-linecap="round">
        <animate attributeName="stroke-dashoffset" from="40" to="0" dur="600ms" repeatCount="1" />
      </path>
    `;
  }
}
