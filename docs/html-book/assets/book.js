window.addEventListener("DOMContentLoaded", () => {
  if (!window.mermaid) {
    console.error("Mermaid failed to load.");
    return;
  }

  window.mermaid.initialize({
    startOnLoad: true,
    theme: "base",
    securityLevel: "loose",
    themeVariables: {
      primaryColor: "#f3e5cf",
      primaryBorderColor: "#8b4513",
      primaryTextColor: "#2a2218",
      lineColor: "#7a5a36",
      secondaryColor: "#fffaf0",
      tertiaryColor: "#efe0ca",
      fontFamily: '"LXGW WenKai", "PingFang SC", sans-serif',
    },
  });
});
