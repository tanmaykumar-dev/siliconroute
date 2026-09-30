/**
 * SiliconRoute Design Spec v3: "Red Bench" Chart Theme
 * Pinned Chart.js defaults: zero radius, no animation, token colors only.
 */

export function getComputedToken(tokenName) {
  return getComputedStyle(document.documentElement).getPropertyValue(tokenName).trim();
}

export function getChartTheme() {
  return {
    paper: getComputedToken("--paper") || "#F2F2F0",
    sheet: getComputedToken("--sheet") || "#FAFAF8",
    rule: getComputedToken("--rule") || "#D6D6D2",
    ink: getComputedToken("--ink") || "#141414",
    ink2: getComputedToken("--ink-2") || "#4A4A4A",
    ink3: getComputedToken("--ink-3") || "#757575",
    red: getComputedToken("--red") || "#E1461E",
    redDeep: getComputedToken("--red-deep") || "#B8330F",
    redWash: getComputedToken("--red-wash") || "#F7E4DD",
    cpu: getComputedToken("--chip-cpu") || "#141414",
    igpu: getComputedToken("--chip-igpu") || "#8A8A8A",
    dgpu: getComputedToken("--chip-dgpu") || "#E1461E",
    npu: getComputedToken("--chip-npu") || "#B8330F",
  };
}

export function applyChartDefaults() {
  if (!window.Chart) return;
  const t = getChartTheme();

  Chart.defaults.animation = false;
  Chart.defaults.color = t.ink2;
  Chart.defaults.borderColor = t.rule;
  Chart.defaults.font.family = "'Archivo', sans-serif";
  Chart.defaults.font.size = 12;

  // Grid styling (Section 8: gridlines --rule)
  Chart.defaults.scale.grid = {
    color: t.rule,
    borderColor: t.ink,
    tickColor: t.rule,
  };

  // Tooltip styling (Section 8: chip name, value with unit, source; sharp 0 radius)
  Chart.defaults.plugins.tooltip.backgroundColor = t.sheet;
  Chart.defaults.plugins.tooltip.titleColor = t.ink;
  Chart.defaults.plugins.tooltip.bodyColor = t.ink2;
  Chart.defaults.plugins.tooltip.borderColor = t.ink;
  Chart.defaults.plugins.tooltip.borderWidth = 1;
  Chart.defaults.plugins.tooltip.padding = 8;
  Chart.defaults.plugins.tooltip.cornerRadius = 0;
  Chart.defaults.plugins.tooltip.titleFont = { family: "'Archivo', sans-serif", weight: "600", size: 12 };
  Chart.defaults.plugins.tooltip.bodyFont = { family: "'JetBrains Mono', monospace", size: 11 };
}

export function getDeviceChartProps(devKey) {
  const t = getChartTheme();
  switch (devKey) {
    case "cpu":
      return {
        label: "CPU",
        mark: "■",
        color: t.cpu,
        pointStyle: "rect",
        borderDash: [],
      };
    case "dml:0":
      return {
        label: "AMD Radeon 610M",
        mark: "▲",
        color: t.igpu,
        pointStyle: "triangle",
        borderDash: [],
      };
    case "dml:1":
      return {
        label: "NVIDIA RTX 5070",
        mark: "●",
        color: t.dgpu,
        pointStyle: "circle",
        borderDash: [],
      };
    case "npu":
      return {
        label: "Qualcomm Hexagon NPU",
        mark: "◆",
        color: t.npu,
        pointStyle: "rectRot",
        borderDash: [],
      };
    default:
      return {
        label: devKey,
        mark: "■",
        color: t.ink3,
        pointStyle: "rect",
        borderDash: [],
      };
  }
}
