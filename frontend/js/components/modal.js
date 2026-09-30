/**
 * SiliconRoute Design Spec v3: Raw Samples Modal (Section 7.6)
 * Sharp sheet with 1px ink border, stats row, sample plot, text list toggle,
 * focus trap, Esc closes, focus returns.
 */

import { getChartTheme, getDeviceChartProps } from "../charts/theme.js";

export class RawSamplesModal {
  constructor(apiClient) {
    this.api = apiClient;
    this.modalEl = null;
    this.chart = null;
    this.previousFocus = null;
    this.currentRun = null;
    this.showList = false;
  }

  init() {
    this.modalEl = document.getElementById("modal-raw-samples");
    if (!this.modalEl) return;

    // Close button
    const closeBtn = this.modalEl.querySelector(".modal-close-btn");
    if (closeBtn) {
      closeBtn.addEventListener("click", () => this.close());
    }

    // Backdrop click
    this.modalEl.addEventListener("click", (e) => {
      if (e.target === this.modalEl) {
        this.close();
      }
    });

    // Keyboard trap & Escape
    window.addEventListener("keydown", (e) => {
      if (!this.isOpen()) return;

      if (e.key === "Escape") {
        e.preventDefault();
        this.close();
        return;
      }

      if (e.key === "Tab") {
        this.trapFocus(e);
      }
    });

    // Toggle sample list
    const toggleListBtn = document.getElementById("modal-samples-toggle-list");
    if (toggleListBtn) {
      toggleListBtn.addEventListener("click", () => {
        this.showList = !this.showList;
        toggleListBtn.textContent = this.showList ? "Hide sample list" : "Show sample list";
        const listEl = document.getElementById("modal-samples-list-view");
        if (listEl) {
          listEl.style.display = this.showList ? "block" : "none";
        }
      });
    }
  }

  isOpen() {
    return this.modalEl && this.modalEl.classList.contains("active");
  }

  trapFocus(e) {
    const focusable = this.modalEl.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    if (!focusable.length) return;

    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }

  async open(runId) {
    this.previousFocus = document.activeElement;
    if (!this.modalEl) this.init();
    if (!this.modalEl) return;

    this.modalEl.classList.add("active");
    this.modalEl.setAttribute("aria-hidden", "false");

    // Reset list view
    this.showList = false;
    const toggleListBtn = document.getElementById("modal-samples-toggle-list");
    if (toggleListBtn) toggleListBtn.textContent = "Show sample list";
    const listEl = document.getElementById("modal-samples-list-view");
    if (listEl) listEl.style.display = "none";

    // Set loading state
    const titleEl = document.getElementById("modal-run-title");
    if (titleEl) titleEl.textContent = `Loading run #${runId}...`;

    try {
      const run = await this.api.fetchRun(runId);
      this.currentRun = run;
      this.renderRun(run);

      const closeBtn = this.modalEl.querySelector(".modal-close-btn");
      if (closeBtn) closeBtn.focus();
    } catch (err) {
      console.error("Failed to load run details:", err);
      if (titleEl) titleEl.textContent = `Run #${runId}: error loading data`;
    }
  }

  close() {
    if (!this.modalEl) return;
    this.modalEl.classList.remove("active");
    this.modalEl.setAttribute("aria-hidden", "true");

    if (this.chart) {
      this.chart.destroy();
      this.chart = null;
    }

    if (this.previousFocus && typeof this.previousFocus.focus === "function") {
      this.previousFocus.focus();
    }
  }

  renderRun(run) {
    const titleEl = document.getElementById("modal-run-title");
    if (titleEl) {
      titleEl.textContent = `Run #${run.id}: ${run.provider_used} (Batch ${run.batch})`;
    }

    // Stats row
    const statMedian = document.getElementById("modal-stat-median");
    const statP10P90 = document.getElementById("modal-stat-p10p90");
    const statSpread = document.getElementById("modal-stat-spread");
    const statCv = document.getElementById("modal-stat-cv");
    const statInnerK = document.getElementById("modal-stat-inner-k");

    if (statMedian) statMedian.textContent = `${run.median_ms.toFixed(3)} ms`;
    if (statP10P90) statP10P90.textContent = `${run.p10_ms.toFixed(3)} / ${run.p90_ms.toFixed(3)} ms`;
    if (statSpread) statSpread.textContent = `${(run.spread * 100).toFixed(2)}%`;
    if (statCv) statCv.textContent = `${(run.cv * 100).toFixed(2)}%`;
    if (statInnerK) statInnerK.textContent = String(run.inner_loop_k || 1);

    // Parse samples
    let samples = [];
    try {
      samples = typeof run.raw_ms_json === "string" ? JSON.parse(run.raw_ms_json) : (run.raw_ms_json || []);
    } catch (e) {
      samples = [];
    }

    this.renderChart(samples, run);
    this.renderTextList(samples);
  }

  renderChart(samples, run) {
    const canvas = document.getElementById("chart-modal-samples");
    if (!canvas) return;

    if (this.chart) {
      this.chart.destroy();
    }

    const devProps = getDeviceChartProps(run.provider_used || "default");
    const points = samples.map((val, idx) => ({ x: idx + 1, y: val }));

    this.chart = new Chart(canvas.getContext("2d"), {
      type: "scatter",
      data: {
        datasets: [
          {
            label: "Timed sample (ms)",
            data: points,
            backgroundColor: devProps.color,
            borderColor: devProps.color,
            pointStyle: devProps.pointStyle,
            pointRadius: 4,
            showLine: false,
          },
          {
            label: "Median",
            data: [{ x: 1, y: run.median_ms }, { x: samples.length, y: run.median_ms }],
            borderColor: "var(--ink)",
            borderDash: [4, 4],
            borderWidth: 1.5,
            pointRadius: 0,
            showLine: true,
          },
        ],
      },
      options: {
        animation: false,
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: {
            title: { display: true, text: "Sample sequence number" },
            ticks: { font: { family: "'JetBrains Mono', monospace", size: 10 } },
          },
          y: {
            title: { display: true, text: "Latency (ms)" },
            ticks: { font: { family: "'JetBrains Mono', monospace", size: 10 } },
          },
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => `Sample #${ctx.parsed.x}: ${ctx.parsed.y.toFixed(3)} ms`,
            },
          },
        },
      },
    });
  }

  renderTextList(samples) {
    const listEl = document.getElementById("modal-samples-list-view");
    if (!listEl) return;

    if (!samples.length) {
      listEl.innerHTML = "<p class='ink-3' style='font-size:12px;'>No raw samples available.</p>";
      return;
    }

    const items = samples.map((s, i) => `<tr><td class="td-num">${i + 1}</td><td class="td-num">${s.toFixed(4)} ms</td></tr>`).join("");
    listEl.innerHTML = `
      <div style="max-height: 180px; overflow-y: auto; margin-top: 12px; border: 1px solid var(--rule);">
        <table class="bench-table" style="width: 100%; font-size: 12px;">
          <thead>
            <tr>
              <th style="width: 80px;">Index</th>
              <th>Measured latency</th>
            </tr>
          </thead>
          <tbody>
            ${items}
          </tbody>
        </table>
      </div>
    `;
  }
}
