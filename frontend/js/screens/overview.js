/**
 * SiliconRoute Design Spec v2 — Overview Screen (Section 6.1)
 * 20-second summary: quick router query, 4 published evaluation tiles,
 * 4 key findings with evidence popovers, and recent decisions table.
 */

export class OverviewScreen {
  constructor(apiClient, metricsSystem) {
    this.api = apiClient;
    this.metrics = metricsSystem;
    this.models = [];
  }

  async init() {
    this.setupAskControls();
    await this.loadRecentDecisions();
  }

  async onActivate() {
    await this.loadRecentDecisions();
  }

  setupAskControls() {
    const selModel = document.getElementById("ask-model-select");
    const btnRoute = document.getElementById("btn-ask-route");

    if (selModel && !selModel.children.length) {
      this.api.fetchModels().then((models) => {
        this.models = models;
        selModel.innerHTML = models
          .map((m) => `<option value="${m.id}">${m.name}</option>`)
          .join("");
      }).catch(err => console.error("Error loading models for Ask box:", err));
    }

    if (btnRoute) {
      btnRoute.addEventListener("click", () => this.handleAskRoute());
    }
  }

  async handleAskRoute() {
    const modelId = parseInt(document.getElementById("ask-model-select")?.value, 10);
    const batch = parseInt(document.getElementById("ask-batch-select")?.value || "1", 10);
    const workload = document.getElementById("ask-workload-select")?.value || "sustained";
    const mode = document.getElementById("ask-mode-select")?.value || "fastest";
    const resultBox = document.getElementById("ask-result-display");

    if (!modelId) return;

    try {
      const dec = await this.api.routeModel({
        ai_model_id: modelId,
        batch,
        workload,
        mode,
        allow_explore: false,
        verify: false,
      });

      if (resultBox) {
        resultBox.style.display = "block";
        const devKey = dec.chosen_device_key.toUpperCase();
        resultBox.innerHTML = `
          <div style="display:flex; align-items:center; justify-content:space-between;">
            <div>
              <span>Recommended Chip: <strong>${devKey}</strong></span>
              <span style="margin-left:8px; font-size:12px; color:var(--ink-2);">${dec.reason}</span>
            </div>
            <a href="#/router" style="font-size:12.5px; font-weight:500;">Open in Router →</a>
          </div>
        `;
      }

      // Highlight the chosen socket tile in the socket strip
      this.highlightChosenSocket(dec.chosen_device_key, dec.actual_ms || dec.candidates?.find(c => c.device_id === dec.chosen_device_id)?.effective_latency_ms);
    } catch (err) {
      console.error("Ask route error:", err);
    }
  }

  highlightChosenSocket(chosenKey, latencyMs) {
    document.querySelectorAll(".socket-tile").forEach(tile => {
      tile.classList.remove("chosen", "dimmed");
      const isMatch = tile.dataset.deviceKey === chosenKey;
      if (isMatch) {
        tile.classList.add("chosen");
        const latEl = tile.querySelector(".socket-predicted-latency");
        if (latEl && latencyMs) latEl.textContent = `${latencyMs.toFixed(3)} ms (chosen)`;
      } else {
        tile.classList.add("dimmed");
      }
    });
  }

  async loadRecentDecisions() {
    const tbody = document.getElementById("overview-recent-decisions-body");
    if (!tbody) return;

    try {
      const decisions = await this.api.fetchDecisions(8, 0);
      if (!decisions || !decisions.length) {
        tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; color:var(--ink-3); padding:var(--space-6);">No decisions logged yet. Route a task above to see it here.</td></tr>`;
        return;
      }

      tbody.innerHTML = decisions.map(d => {
        const ctx = typeof d.context_json === "string" ? JSON.parse(d.context_json || "{}") : (d.context_json || {});
        const wl = ctx.workload || "sustained";
        const devKey = (d.chosen_device_key || "cpu").toUpperCase();
        const win = d.was_best ? `<span class="pill pill-ok">win</span>` : d.was_best === false ? `<span class="pill pill-bad">loss</span>` : `<span class="pill pill-na">unverified</span>`;
        const regret = d.regret_pct !== null && d.regret_pct !== undefined ? `${d.regret_pct.toFixed(2)}%` : "N/A";
        const timeStr = d.ts ? d.ts.split("T")[1]?.slice(0, 8) : "";

        return `
          <tr>
            <td class="font-mono" style="color:var(--chip-cpu); font-weight:600;">#${d.id}</td>
            <td class="font-mono text-small">${timeStr}</td>
            <td>Model #${d.ai_model_id}</td>
            <td class="font-mono text-center">B=${d.batch}</td>
            <td class="text-center"><span class="pill pill-info">${wl}</span></td>
            <td><strong>${devKey}</strong></td>
            <td class="text-center">${win}</td>
            <td class="font-mono text-right" style="color:${d.regret_pct > 0 ? "var(--warn)" : "var(--ok)"};">${regret}</td>
          </tr>
        `;
      }).join("");
    } catch (err) {
      console.error("Failed loading recent decisions:", err);
    }
  }
}
