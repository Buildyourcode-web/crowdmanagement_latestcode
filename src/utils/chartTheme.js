// Chart Theme helper for ECharts (Dark / Light mode support)

export function getChartTheme(theme = "dark") {
  const isLight = theme === "light";

  return {
    isLight,
    textStyle: {
      color: isLight ? "#475569" : "#8b949e",
      fontFamily: "Inter, -apple-system, sans-serif",
      fontSize: 11,
    },
    tooltip: {
      backgroundColor: isLight ? "#ffffff" : "#141920",
      borderColor: isLight ? "#cbd5e1" : "#252d38",
      borderWidth: 1,
      textStyle: {
        color: isLight ? "#0f172a" : "#dce8f0",
        fontSize: 11,
      },
      extraCssText: isLight
        ? "box-shadow: 0 4px 12px rgba(0,0,0,0.1); border-radius: 4px;"
        : "box-shadow: 0 4px 12px rgba(0,0,0,0.6); border-radius: 4px;",
    },
    axisLine: {
      lineStyle: {
        color: isLight ? "#cbd5e1" : "#252d38",
      },
    },
    splitLine: {
      lineStyle: {
        color: isLight ? "#e2e8f0" : "#1e2730",
      },
    },
    axisLabelColor: isLight ? "#64748b" : "#4a6070",
    legendText: {
      color: isLight ? "#334155" : "#8b949e",
    },
    primaryColor: isLight ? "#0284c7" : "#58a6ff",
    secondaryColor: isLight ? "#ca8a04" : "#e3b341",
    dangerColor: isLight ? "#dc2626" : "#f85149",
    successColor: isLight ? "#16a34a" : "#3fb950",
  };
}
