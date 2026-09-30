/**
 * SiliconRoute Design Spec v3: "Red Bench" Chart Theme
 * Pinned Chart.js defaults: zero radius, no animation, token colors only.
 */

export function getComputedToken(tokenName) {
  return getComputedStyle(document.documentElement).getPropertyValue(tokenName).trim();
}

export function getChartTheme() {
  const isDark = document.documentElement.getAttribute("data-theme") === "dark" ||
                 document.body.getAttribute("data-theme") === "dark";
  return {
    paper: getComputedToken("--paper") || (isDark ? "#0F1117" : "#F3F4F6"),
    sheet: getComputedToken("--sheet") || (isDark ? "#181B24" : "#FFFFFF"),
    rule: getComputedToken("--rule") || (isDark ? "#262B36" : "#E5E7EB"),
    ink: isDark ? "#EDEDE8" : (getComputedToken("--ink") || "#111827"),
    ink2: isDark ? "#B4B4AC" : (getComputedToken("--ink-2") || "#4B5563"),
    ink3: isDark ? "#8C8C84" : (getComputedToken("--ink-3") || "#9CA3AF"),
    red: getComputedToken("--red") || "#9B2A3C",
    redDeep: getComputedToken("--red-deep") || "#9B2A3C",
    redWash: getComputedToken("--red-wash") || (isDark ? "#2A1A1D" : "#F5EAEB"),
    cpu: getComputedToken("--chip-cpu") || (isDark ? "#D99A45" : "#D97706"),
    igpu: getComputedToken("--chip-igpu") || (isDark ? "#4FB3A4" : "#0D9488"),
    dgpu: getComputedToken("--chip-dgpu") || (isDark ? "#7F9CF0" : "#2563EB"),
    npu: getComputedToken("--chip-npu") || (isDark ? "#A9BC4C" : "#7C3AED"),
  };
}

export function applyChartDefaults() {
  if (!window.Chart) return;
  const t = getChartTheme();

  Chart.defaults.animation = {
    duration: 350,
    easing: "easeOutQuart",
  };
  Chart.defaults.color = t.ink2;
  Chart.defaults.borderColor = t.rule;
  Chart.defaults.font.family = "'IBM Plex Sans', -apple-system, sans-serif";
  Chart.defaults.font.size = 11;

  // Grid styling
  Chart.defaults.scale.grid = {
    color: t.rule,
    borderColor: t.rule,
    tickColor: t.rule,
  };

  // Tooltip styling
  Chart.defaults.plugins.tooltip.backgroundColor = t.sheet;
  Chart.defaults.plugins.tooltip.titleColor = t.ink;
  Chart.defaults.plugins.tooltip.bodyColor = t.ink2;
  Chart.defaults.plugins.tooltip.borderColor = t.rule;
  Chart.defaults.plugins.tooltip.borderWidth = 1;
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.cornerRadius = 6;
  Chart.defaults.plugins.tooltip.titleFont = { family: "'IBM Plex Sans', sans-serif", weight: "600", size: 12 };
  Chart.defaults.plugins.tooltip.bodyFont = { family: "'IBM Plex Mono', monospace", size: 11 };
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
