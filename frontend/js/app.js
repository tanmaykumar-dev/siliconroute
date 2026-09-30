/**
 * SiliconRoute Design Spec v3: "Red Bench" Application Entrypoint
 * Light theme only. Initializes Socket Strip, Router, Metrics, Telemetry, and Screens.
 */

import { ClientRouter } from "./router.js";
import { api } from "./api.js";
import { TelemetryService } from "./telemetry.js";
import { MetricsSystem } from "./metrics.js";
import { RawSamplesModal } from "./components/modal.js";
import { SocketStrip } from "./components/socket_strip.js";

import { OverviewScreen } from "./screens/overview.js";
import { LiveScreen } from "./screens/live.js";
import { AnalysisScreen } from "./screens/analysis.js";
import { RouterScreen } from "./screens/router.js";
import { ResultsScreen } from "./screens/results.js";
import { EvidenceScreen } from "./screens/evidence.js";
import { AboutScreen } from "./screens/about.js";

document.addEventListener("DOMContentLoaded", async () => {
  // 1. Metrics & Evidence System (Section 9)
  const metrics = new MetricsSystem(api);

  // 2. Raw Samples Modal (Section 7.6)
  const modal = new RawSamplesModal(api);
  modal.init();

  // 3. Socket Strip (Section 4)
  const socketStrip = new SocketStrip(api);
  await socketStrip.init();

  // 4. Screen Controllers
  const screens = {
    overview: new OverviewScreen(api, metrics),
    live: new LiveScreen(),
    analysis: new AnalysisScreen(api, modal),
    router: new RouterScreen(api),
    results: new ResultsScreen(api),
    evidence: new EvidenceScreen(api, modal),
    about: new AboutScreen(api),
  };

  // Initialize each screen controller
  await Promise.all([
    screens.overview.init(),
    screens.live.init(),
    screens.analysis.init(),
    screens.router.init(),
    screens.results.init(),
    screens.evidence.init(),
    screens.about.init(),
  ]);

  // 5. Client Router (Section 5, handles hash navigation & keyboard shortcuts)
  const router = new ClientRouter(
    ["overview", "live", "analysis", "router", "results", "evidence", "about"],
    "overview"
  );

  window.addEventListener("screenchange", (e) => {
    const screenName = e.detail.screen;
    if (screens[screenName] && typeof screens[screenName].onActivate === "function") {
      screens[screenName].onActivate();
    }
  });

  // Activate initial screen
  const initialScreen = router.currentScreen || "overview";
  if (screens[initialScreen] && typeof screens[initialScreen].onActivate === "function") {
    screens[initialScreen].onActivate();
  }

  // 6. Fetch published manifest metrics and resolve all .metric elements
  await metrics.load();

  // 7. Telemetry & SSE Service (connects to live 1 Hz background sampler)
  const telemetry = new TelemetryService(api);
  telemetry.start();

  // Expose for testing and verification scripts
  window.SiliconRouteApp = {
    router,
    metrics,
    telemetry,
    modal,
    socketStrip,
    screens,
  };

  // 8. Global Keyboard Shortcuts Sheet & Help Modal
  setupShortcutsSheet();
});

function setupShortcutsSheet() {
  const btnHelp = document.getElementById("btn-shortcuts-help");
  const modal = document.getElementById("modal-shortcuts");
  const closeBtn = modal?.querySelector(".modal-close-btn");

  if (!modal) return;

  const openSheet = () => {
    modal.classList.add("active");
    modal.setAttribute("aria-hidden", "false");
  };

  const closeSheet = () => {
    modal.classList.remove("active", "open");
    modal.setAttribute("aria-hidden", "true");
  };

  if (btnHelp) {
    btnHelp.addEventListener("click", openSheet);
  }

  if (closeBtn) {
    closeBtn.addEventListener("click", closeSheet);
  }

  modal.addEventListener("click", (e) => {
    if (e.target === modal) closeSheet();
  });

  window.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal.classList.contains("active")) {
      closeSheet();
    }
    if (e.key === "?" && !["INPUT", "SELECT", "TEXTAREA"].includes(document.activeElement?.tagName)) {
      openSheet();
    }
  });
}
