/**
 * SiliconRoute Design Spec v3: "Red Bench" Overview Screen (Section 6.1)
 * Statement block, strategy comparison table, quick route form, recent decisions, findings.
 */

export class OverviewScreen {
  constructor(apiClient, metricsSystem) {
    this.api = apiClient;
    this.metrics = metricsSystem;
    this.models = [];
  }

  async init() {
    this.setupRouteForm();
    this.setupEvidenceButton();
    await this.loadRecentDecisions();
  }

  async onActivate() {
    await this.loadRecentDecisions();
  }

  setupEvidenceButton() {
    const btn = document.getElementById("overview-evidence-btn");
    if (btn) {
      btn.addEventListener("click", () => {
        window.location.hash = "#/evidence";
      });
    }
  }

  setupRouteForm() {
    const form = document.getElementById("overview-route-form");
    if (!form) return;

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const modelKey = document.getElementById("overview-model-select")?.value || "mlp_256w_4l";
      const batch = parseInt(document.getElementById("overview-batch-select")?.value || "1", 10);
      const workload = document.getElementById("overview-workload-select")?.value || "sustained";
      const goal = document.getElementById("overview-goal-select")?.value || "fastest";

      try {
        const models = await this.api.getModels();
        const matched = models.find(m => m.name === modelKey) || models[0];
        const modelId = matched ? matched.id : 1;

        const decision = await this.api.routeModel({
          ai_model_id: modelId,
          batch,
          workload,
          mode: goal,
        });

        // Notify socket strip & global listeners
        window.dispatchEvent(new CustomEvent("routedecision", { detail: decision }));
        await this.loadRecentDecisions();
      } catch (err) {
        console.error("Failed routing task from overview:", err);
      }
    });
  }

  async loadRecentDecisions() {
    const tbody = document.getElementById("tbody-overview-recent-decisions");
    if (!tbody) return;

    try {
      const decisions = await this.api.getDecisions(10);
      if (!decisions || !decisions.length) {
        tbody.innerHTML = `
          <tr>
            <td colspan="7" style="text-align: center; color: var(--ink-3);">No decisions yet. Route a task to see it here.</td>
          </tr>
        `;
        return;
      }

      tbody.innerHTML = decisions.slice(0, 8).map(d => {
        const timeMs = d.predicted_latency_ms != null ? `${d.predicted_latency_ms.toFixed(3)} ms` : "n/a";
        const modelName = d.model_name || (d.model ? d.model.name : `Model #${d.ai_model_id}`);
        const chipLabel = d.chosen_device_key || `Device #${d.chosen_device_id}`;
        const workload = d.workload || "sustained";

        return `
          <tr>
            <td>#${d.id}</td>
            <td><strong>${modelName}</strong></td>
            <td class="num">${d.batch}</td>
            <td>${workload}</td>
            <td><strong>${chipLabel}</strong></td>
            <td class="num">${timeMs}</td>
            <td style="max-width: 320px; font-size: 13px;">${d.reason || ""}</td>
          </tr>
        `;
      }).join("");
    } catch (err) {
      console.error("Failed loading recent decisions for overview:", err);
    }
  }
}
