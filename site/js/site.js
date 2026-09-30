/**
 * SiliconRoute Website Logic
 * Loads local data/manifest.json, data/content.json, and data/build.json.
 * Renders .metric elements, draws hero routing trace, and attaches copy buttons.
 */

document.addEventListener("DOMContentLoaded", async () => {
  await loadAndRenderSite();
  setupCodeCopyButtons();
  drawHeroRoutingTrace();
});

async function loadAndRenderSite() {
  try {
    const [manifestRes, contentRes, buildRes] = await Promise.all([
      fetch("data/manifest.json"),
      fetch("data/content.json"),
      fetch("data/build.json"),
    ]);

    const manifest = await manifestRes.json();
    const content = await contentRes.json();
    const build = await buildRes.json();

    renderMetrics(manifest.metrics || {});
    renderBuildInfo(build);
    renderContent(content);
  } catch (err) {
    console.error("Failed loading site data:", err);
  }
}

function formatValue(key, val, unit) {
  if (val === null || val === undefined) return "not available";
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
  if (unit === "x") return `${val.toFixed(1)}×`;
  if (unit === "GFLOP/s" || unit === "GB/s") return `${val.toFixed(1)} ${unit}`;
  if (Number.isInteger(val)) return val.toLocaleString();

  return `${val} ${unit || ""}`.trim();
}

function renderMetrics(metrics) {
  document.querySelectorAll(".metric[data-metric]").forEach(el => {
    const key = el.dataset.metric;
    const m = metrics[key];
    if (!m) {
      el.textContent = "not available";
      return;
    }
    el.textContent = formatValue(key, m.value, m.unit);
  });
}

function renderBuildInfo(build) {
  const elSha = document.getElementById("build-db-sha");
  const elCommit = document.getElementById("build-git-commit");

  if (elSha) elSha.textContent = build.database_sha256 || "—";
  if (elCommit && build.git_commit) {
    elCommit.textContent = build.git_commit.slice(0, 10);
  }
}

function renderContent(content) {
  // Render limitations
  const limList = document.getElementById("site-limitations-list");
  if (limList && Array.isArray(content.limitations)) {
    limList.innerHTML = content.limitations.map(item => `<li>${escapeHtml(item)}</li>`).join("");
  }

  // Render How this was built
  const builtList = document.getElementById("site-how-built-container");
  if (builtList && Array.isArray(content.how_this_was_built)) {
    builtList.innerHTML = content.how_this_was_built.map(p => `
      <p style="margin-bottom:var(--space-3); line-height:1.6; color:var(--ink-2); font-size:14px;">
        ${escapeHtml(p)}
      </p>
    `).join("");
  }
}

function drawHeroRoutingTrace() {
  const svg = document.getElementById("hero-trace-svg");
  const sourceBox = document.getElementById("hero-task-box");
  const destBox = document.getElementById("hero-dest-box");

  if (!svg || !sourceBox || !destBox) return;

  const sRect = sourceBox.getBoundingClientRect();
  const dRect = destBox.getBoundingClientRect();
  const cRect = svg.getBoundingClientRect();

  const startX = sRect.right - cRect.left;
  const startY = sRect.top + sRect.height / 2 - cRect.top;
  const endX = dRect.left - cRect.left;
  const endY = dRect.top + dRect.height / 2 - cRect.top;

  const midX = (startX + endX) / 2;
  const pathD = `M ${startX} ${startY} C ${midX} ${startY}, ${midX} ${endY}, ${endX} ${endY}`;

  svg.innerHTML = `
    <path d="${pathD}" fill="none" stroke="var(--ok)" stroke-width="2.5" stroke-dasharray="8 4" stroke-linecap="round">
      <animate attributeName="stroke-dashoffset" from="40" to="0" dur="800ms" repeatCount="1" />
    </path>
  `;
}

function setupCodeCopyButtons() {
  document.querySelectorAll(".code-copy-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      const targetId = btn.getAttribute("data-code-target");
      const codeEl = document.getElementById(targetId);
      if (!codeEl) return;

      navigator.clipboard.writeText(codeEl.innerText.trim()).then(() => {
        const orig = btn.textContent;
        btn.textContent = "Copied";
        setTimeout(() => { btn.textContent = orig; }, 1500);
      }).catch(err => console.error("Copy failed:", err));
    });
  });
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
