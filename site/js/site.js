/**
 * SiliconRoute Website Logic: Red Bench (Design Spec v3 Section 10)
 * Loads local data/manifest.json, data/content.json, and data/build.json.
 * Renders .metric elements, populates limitations and disclosure, attaches copy buttons.
 */

document.addEventListener("DOMContentLoaded", async () => {
  await loadAndRenderSite();
  setupCodeCopyButtons();
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
      el.textContent = "not available";
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
  const limList = document.getElementById("site-limitations-list");
  if (limList && Array.isArray(content.limitations)) {
    limList.innerHTML = content.limitations.map(item => `<li>${formatMarkdown(item)}</li>`).join("");
  }

  const builtList = document.getElementById("site-built-list");
  if (builtList && Array.isArray(content.how_this_was_built)) {
    builtList.innerHTML = content.how_this_was_built.map(item => `<li>${formatMarkdown(item)}</li>`).join("");
  }
}

function formatMarkdown(str) {
  if (!str) return "";
  const escaped = escapeHtml(str);
  return escaped.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
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
