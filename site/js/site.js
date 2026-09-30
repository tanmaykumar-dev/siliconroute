/**
 * SiliconRoute Website Logic: "Field Report" (Design Spec final, revision 2)
 * Handles metrics population, interactive decision figure, dashboard routing check,
 * copy buttons, and mobile menu overlay.
 */

document.addEventListener("DOMContentLoaded", async () => {
  await loadAndRenderSite();
  setupDecisionFigure();
  setupDashboardButtons();
  setupCopyButtons();
  setupMobileMenu();
});

let siteManifest = null;

async function loadAndRenderSite() {
  try {
    const [manifestRes, contentRes, buildRes, snapdragonRes, contactRes] = await Promise.all([
      fetch("data/manifest.json").catch(() => null),
      fetch("data/content.json").catch(() => null),
      fetch("data/build.json").catch(() => null),
      fetch("data/snapdragon_status.json").catch(() => null),
      fetch("data/contact.json").catch(() => null),
    ]);

    if (manifestRes && manifestRes.ok) {
      siteManifest = await manifestRes.json();
      renderMetrics(siteManifest.metrics || {});
      updateDecisionBars("small");
    }

    if (buildRes && buildRes.ok) {
      const build = await buildRes.json();
      renderBuildInfo(build);
    }

    if (contentRes && contentRes.ok) {
      const content = await contentRes.json();
      renderContent(content);
    }

    if (snapdragonRes && snapdragonRes.ok) {
      const snap = await snapdragonRes.json();
      renderSnapdragon(snap);
    }

    if (contactRes && contactRes.ok) {
      const contact = await contactRes.json();
      renderContact(contact);
    }
  } catch (err) {
    console.error("Failed loading site data:", err);
  }
}

function formatValue(key, val, unit) {
  if (val === null || val === undefined) return "not published";
  if (typeof val === "string") return val;

  if (unit === "ms") {
    if (val < 1) return `${val.toFixed(3)} ms`;
    if (val <= 100) return `${val.toFixed(2)} ms`;
    return `${val.toFixed(1)} ms`;
  }
  if (unit === "%") {
    if (key.includes("regret")) return `${val.toFixed(2)}%`;
    return `${val.toFixed(1)}%`;
  }
  if (unit === "x") return `${val.toFixed(1)}x`;
  if (unit === "GFLOP/s" || unit === "GB/s") return `${val.toFixed(1)} ${unit}`;
  if (unit === "params") {
    if (val >= 1000000) return `${(val / 1000000).toFixed(1)}M params`;
    return `${val.toLocaleString()} params`;
  }
  if (Number.isInteger(val)) return val.toLocaleString();

  return `${val} ${unit || ""}`.trim();
}

function renderMetrics(metrics) {
  document.querySelectorAll(".metric[data-metric]").forEach(el => {
    const key = el.dataset.metric;
    const m = metrics[key];
    if (!m) {
      el.textContent = "not published";
      return;
    }
    el.textContent = formatValue(key, m.value, m.unit);
  });
}

function renderBuildInfo(build) {
  const elSha = document.getElementById("build-db-sha");
  const elCommit = document.getElementById("build-git-commit");

  if (elSha) elSha.textContent = build.database_sha256 || "n/a";
  if (elCommit && build.git_commit) {
    elCommit.textContent = build.git_commit.slice(0, 10);
  }
}

function renderContent(content) {
  const builtList = document.getElementById("site-built-list");
  if (builtList && Array.isArray(content.how_this_was_built)) {
    builtList.innerHTML = content.how_this_was_built.map(item => `<li>${formatMarkdown(item)}</li>`).join("");
  }
}

function renderSnapdragon(snap) {
  const statusEl = document.getElementById("snapdragon-status-text");
  const testingEl = document.getElementById("snapdragon-testing-text");
  if (statusEl && snap.status) statusEl.textContent = snap.status;
  if (testingEl && snap.testing) testingEl.textContent = snap.testing;
}

function renderContact(contact) {
  const emailEls = document.querySelectorAll(".contact-email-text");
  emailEls.forEach(el => { el.textContent = contact.email || "tanmayjha54321@gmail.com"; });

  const mailtoBtn = document.querySelector("[data-test='contact-mailto']");
  if (mailtoBtn && contact.email) {
    mailtoBtn.setAttribute("href", `mailto:${contact.email}`);
  }

  const profileBtn = document.querySelector("[data-test='contact-github-profile']");
  if (profileBtn && contact.github_profile) {
    profileBtn.setAttribute("href", contact.github_profile);
  }

  const repoBtn = document.querySelector("[data-test='contact-repo']");
  if (repoBtn && contact.repository) {
    repoBtn.setAttribute("href", contact.repository);
  }
}

function formatMarkdown(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
}

/* Section 03 Interactive Decision Figure */
function setupDecisionFigure() {
  const segmentBtns = document.querySelectorAll(".segmented-control button[data-workload]");
  segmentBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      segmentBtns.forEach(b => {
        b.classList.remove("active");
        b.setAttribute("aria-pressed", "false");
      });
      btn.classList.add("active");
      btn.setAttribute("aria-pressed", "true");
      updateDecisionBars(btn.dataset.workload);
    });
  });

  const toggleBtn = document.getElementById("btn-toggle-decision-data");
  const tableWrap = document.getElementById("decision-table-wrap");
  if (toggleBtn && tableWrap) {
    toggleBtn.addEventListener("click", () => {
      const isHidden = tableWrap.classList.contains("hidden");
      tableWrap.classList.toggle("hidden", !isHidden);
      toggleBtn.textContent = isHidden ? "Hide data" : "Show data";
    });
  }

  const resultsToggleBtn = document.getElementById("btn-toggle-results-data");
  const resultsTableWrap = document.getElementById("results-table-wrap");
  if (resultsToggleBtn && resultsTableWrap) {
    resultsToggleBtn.addEventListener("click", () => {
      const isHidden = resultsTableWrap.classList.contains("hidden");
      resultsTableWrap.classList.toggle("hidden", !isHidden);
      resultsToggleBtn.textContent = isHidden ? "Hide data" : "Show data";
    });
  }
}

function updateDecisionBars(workload) {
  const explanationEl = document.getElementById("decision-explanation");
  const barsContainer = document.getElementById("decision-bars");
  if (!barsContainer) return;

  let cpuMs, igpuMs, dgpuMs, chosen, explanation;

  if (workload === "small") {
    // MLP-256 batch 1
    cpuMs = 0.017;
    igpuMs = 0.089;
    dgpuMs = 0.142;
    chosen = "cpu";
    explanation = "SiliconRoute routes MLP-256 batch 1 to CPU: cache residency yields 8.4x lower latency than discrete GPU.";
  } else if (workload === "large") {
    // MLP-3072 batch 1 sustained
    cpuMs = 4.20;
    igpuMs = 2.15;
    dgpuMs = 0.655;
    chosen = "dgpu";
    explanation = "SiliconRoute routes MLP-3072 batch 1 to RTX 5070: compute density overcomes dispatch overhead for a 6.4x speedup.";
  } else {
    // Cold start (Decision 144)
    cpuMs = 215.8;
    igpuMs = 385.2;
    dgpuMs = 219.9;
    chosen = "cpu";
    explanation = "SiliconRoute routes cold-start single inference to CPU: discrete GPU PCIe wake penalty (335.7x overhead) negates accelerator advantage.";
  }

  if (explanationEl) explanationEl.textContent = explanation;

  const chips = [
    { id: "cpu", name: "AMD Ryzen 5 7520U", class: "cpu", ms: cpuMs },
    { id: "igpu", name: "AMD Radeon 610M", class: "igpu", ms: igpuMs },
    { id: "dgpu", name: "NVIDIA RTX 5070", class: "dgpu", ms: dgpuMs },
    { id: "npu", name: "Qualcomm NPU", class: "npu", ms: null },
  ];

  // Log scale calculation (min 0.01 to max 500)
  const logMin = Math.log10(0.01);
  const logMax = Math.log10(500);

  barsContainer.innerHTML = chips.map(chip => {
    const isChosen = chip.id === chosen;
    const msText = chip.ms !== null ? `${chip.ms.toFixed(3)} ms` : "not yet measured";
    let widthPct = 0;
    if (chip.ms !== null) {
      const logVal = Math.log10(Math.max(chip.ms, 0.01));
      widthPct = Math.min(100, Math.max(5, ((logVal - logMin) / (logMax - logMin)) * 100));
    }

    return `
      <div class="chip-bar-row">
        <div class="chip-label-cell">
          <span class="chip-square chip-square-${chip.class}"></span>
          <span>${chip.name}</span>
          ${isChosen ? '<span class="chosen-badge">chosen</span>' : ''}
        </div>
        <div class="bar-track">
          <div class="bar-fill ${isChosen ? 'bar-fill-chosen' : ''}" style="width: ${widthPct}%;"></div>
        </div>
        <div class="chip-value-cell">${msText}</div>
      </div>
    `;
  }).join("");
}

/* Section 6 Dashboard Navigation Check */
function setupDashboardButtons() {
  const handler = async (e) => {
    e.preventDefault();
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 800);
      const res = await fetch("/api/system", { signal: controller.signal });
      clearTimeout(timeoutId);
      if (res.ok) {
        window.open("/app", "_blank");
        return;
      }
    } catch {
      // Local server not answering or timed out
    }
    window.location.href = "dashboard.html";
  };

  const navBtn = document.getElementById("nav-dashboard-btn");
  if (navBtn) navBtn.addEventListener("click", handler);

  const heroBtn = document.getElementById("btn-open-dashboard");
  if (heroBtn) heroBtn.addEventListener("click", handler);
}

/* Copy Buttons */
function setupCopyButtons() {
  document.querySelectorAll(".code-copy-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-code-target");
      const codeEl = document.getElementById(targetId);
      if (!codeEl) return;

      const text = codeEl.innerText.trim();
      navigator.clipboard.writeText(text).then(() => {
        const orig = btn.textContent;
        btn.textContent = "Copied";
        setTimeout(() => { btn.textContent = orig; }, 2000);
      }).catch(() => {
        btn.textContent = "Copy failed, select the text";
        setTimeout(() => { btn.textContent = "Copy"; }, 2000);
      });
    });
  });

  const emailCopyBtn = document.getElementById("btn-copy-email");
  if (emailCopyBtn) {
    emailCopyBtn.addEventListener("click", () => {
      const email = "tanmayjha54321@gmail.com";
      navigator.clipboard.writeText(email).then(() => {
        const orig = emailCopyBtn.textContent;
        emailCopyBtn.textContent = "Copied";
        setTimeout(() => { emailCopyBtn.textContent = orig; }, 2000);
      }).catch(() => {
        emailCopyBtn.textContent = "Copy failed, select the text";
        setTimeout(() => { emailCopyBtn.textContent = "Copy email"; }, 2000);
      });
    });
  }
}

/* Mobile Menu Overlay */
function setupMobileMenu() {
  const overlay = document.getElementById("mobile-menu-overlay");
  const openBtn = document.getElementById("btn-open-menu");
  const closeBtn = document.getElementById("btn-close-menu");

  if (!overlay || !openBtn || !closeBtn) return;

  const openMenu = () => {
    overlay.classList.add("active");
    closeBtn.focus();
    document.addEventListener("keydown", handleKeydown);
  };

  const closeMenu = () => {
    overlay.classList.remove("active");
    openBtn.focus();
    document.removeEventListener("keydown", handleKeydown);
  };

  const handleKeydown = (e) => {
    if (e.key === "Escape") closeMenu();
  };

  openBtn.addEventListener("click", openMenu);
  closeBtn.addEventListener("click", closeMenu);

  overlay.querySelectorAll("a").forEach(link => {
    link.addEventListener("click", closeMenu);
  });
}
