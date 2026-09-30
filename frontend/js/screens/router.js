/**
 * SiliconRoute Design Spec v3: "Red Bench" Router Screen (Section 6.4)
 * Form + "Route task" + "Route and verify on hardware" (confirmation dialog first).
 * Result: chosen chip, predicted time with source, plain-English reason, rules applied,
 * candidates table (chip, predicted, source, penalty, score, eligibility with reason).
 * Exploration checkbox off by default.
 */

import { toast } from "../components/toast.js";

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
      this.handleRouteTask(false);
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

      // Dispatch to socket strip & trigger toast
      window.dispatchEvent(new CustomEvent("routedecision", { detail: dec }));
      const chipKey = (dec.chosen_device_key || "CPU").toUpperCase();
      toast.show(`Task routed to ${chipKey}.`);
    } catch (err) {
      console.error("Routing error:", err);
    }
  }

  handleRouteVerify() {
    const confirmed = window.confirm("This runs a short benchmark on every chip, about 10 to 30 seconds. Continue?");
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
        <span class="tag tag-verified" style="font-size:14px; padding:4px 8px;">
          <strong>${devKey}</strong>: ${dev.label}
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
        const statusText = c.is_excluded ? c.excluded_reason : "eligible";

        return `
          <tr class="${isChosen ? 'highlight' : ''}">
            <td><strong>${c.device_key.toUpperCase()}</strong> ${isChosen ? '<span class="tag tag-verified" style="margin-left:4px;">CHOSEN</span>' : ''}</td>
            <td class="num">${predMs} ms</td>
            <td><span class="tag">${c.source}</span></td>
            <td class="num">${wakeStr}</td>
            <td class="num">${scoreStr}</td>
            <td><span class="tag">${statusText}</span></td>
          </tr>
        `;
      }).join("");
    }
  }
}
