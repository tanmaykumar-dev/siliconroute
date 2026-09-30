/**
 * SiliconRoute Design Spec v2 — Chart.js Theme & Palette Adapter
 * Synchronizes Chart.js global defaults with CSS tokens and chip glyph identities.
 */

export function getComputedToken(tokenName) {
  return getComputedStyle(document.documentElement).getPropertyValue(tokenName).trim();
}

export function getChartTheme() {
  return {
    line: getComputedToken("--line"),
    lineStrong: getComputedToken("--line-strong"),
    ink: getComputedToken("--ink"),
    ink2: getComputedToken("--ink-2"),
    ink3: getComputedToken("--ink-3"),
    plate: getComputedToken("--plate"),
    plateRaised: getComputedToken("--plate-raised"),
    cpu: getComputedToken("--chip-cpu"),
    igpu: getComputedToken("--chip-igpu"),
    dgpu: getComputedToken("--chip-dgpu"),
    npu: getComputedToken("--chip-npu"),
    ok: getComputedToken("--ok"),
    warn: getComputedToken("--warn"),
    bad: getComputedToken("--bad"),
    na: getComputedToken("--na"),
  };
}

export function applyChartDefaults() {
  if (!window.Chart) return;
  const t = getChartTheme();

  Chart.defaults.color = t.ink2;
  Chart.defaults.borderColor = t.line;
  Chart.defaults.font.family = "'Archivo', system-ui, sans-serif";
  Chart.defaults.font.size = 12;

  // Grid styling
  Chart.defaults.scale.grid = {
    color: t.line,
    borderColor: t.lineStrong,
    tickColor: t.line,
  };

  // Tooltip styling
  Chart.defaults.plugins.tooltip.backgroundColor = t.plateRaised;
  Chart.defaults.plugins.tooltip.titleColor = t.ink;
  Chart.defaults.plugins.tooltip.bodyColor = t.ink2;
  Chart.defaults.plugins.tooltip.borderColor = t.lineStrong;
  Chart.defaults.plugins.tooltip.borderWidth = 1;
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.cornerRadius = 6;
  Chart.defaults.plugins.tooltip.titleFont = { weight: "600", size: 12.5 };
  Chart.defaults.plugins.tooltip.bodyFont = { family: "'JetBrains Mono', monospace", size: 12 };
}

export function getDeviceChartProps(devKey) {
  const t = getChartTheme();
  switch (devKey) {
    case "cpu":
      return {
        label: "CPU (Ryzen 7 7730U)",
        color: t.cpu,
        pointStyle: "rect",
        borderDash: [],
      };
    case "dml:0":
      return {
        label: "iGPU (Radeon 610M)",
        color: t.igpu,
        pointStyle: "triangle",
        borderDash: [],
      };
    case "dml:1":
      return {
        label: "dGPU (RTX 5070)",
        color: t.dgpu,
        pointStyle: "circle",
        borderDash: [],
      };
    default:
      return {
        label: devKey,
        color: t.ink3,
        pointStyle: "circle",
        borderDash: [],
      };
  }
}
