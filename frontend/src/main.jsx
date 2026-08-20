import React from "react";
import { createRoot } from "react-dom/client";
import ChatWidget from "./ChatWidget.jsx";
import widgetStyles from "./widget.css?inline";

function injectStyles() {
  if (document.getElementById("skapa-chatbot-styles")) return;
  const style = document.createElement("style");
  style.id = "skapa-chatbot-styles";
  style.textContent = widgetStyles;
  document.head.appendChild(style);
}

function init(options = {}) {
  injectStyles();
  const container = document.createElement("div");
  container.id = "skapa-chatbot-root";
  document.body.appendChild(container);
  createRoot(container).render(<ChatWidget {...options} />);
}

// Exposé globalement pour un montage manuel : SkapaChatbot.init({...})
window.SkapaChatbot = { init };

// Auto-montage si le <script> porte les attributs data-*
const currentScript = document.currentScript;
if (currentScript && currentScript.dataset.autoInit !== "false") {
  init({
    apiUrl: currentScript.dataset.apiUrl || "http://localhost:5000/api",
    siteId: currentScript.dataset.siteId || "",
    title: currentScript.dataset.title || "Assistant",
    primaryColor: currentScript.dataset.color || "#4f46e5",
  });
}
