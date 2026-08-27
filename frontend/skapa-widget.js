/**
 * Widget de chat Skapa - a coller sur n'importe quel site.
 *
 * Utilisation :
 *   <script
 *     src="https://ton-domaine.com/skapa-widget.js"
 *     data-api-url="https://ton-api.com/chat"
 *     data-title="Assistant Skapa"
 *   ></script>
 *
 * Aucune dependance externe, pas de build : un seul fichier JS pur.
 */
(function () {
  "use strict";

  var currentScript = document.currentScript;
  var API_URL = currentScript.getAttribute("data-api-url") || "http://localhost:8000/chat";
  var TITLE = currentScript.getAttribute("data-title") || "Assistant";
  var ACCENT = currentScript.getAttribute("data-color") || "#1f6feb";

  var style = document.createElement("style");
  style.textContent = `
    #skapa-bubble {
      position: fixed; bottom: 20px; right: 20px; width: 56px; height: 56px;
      border-radius: 50%; background: ${ACCENT}; color: white; border: none;
      font-size: 24px; cursor: pointer; box-shadow: 0 4px 14px rgba(0,0,0,.2);
      z-index: 999999;
    }
    #skapa-panel {
      position: fixed; bottom: 90px; right: 20px; width: 340px; max-width: 90vw;
      height: 460px; max-height: 70vh; background: white; border-radius: 12px;
      box-shadow: 0 8px 30px rgba(0,0,0,.2); display: none; flex-direction: column;
      overflow: hidden; font-family: system-ui, sans-serif; z-index: 999999;
    }
    #skapa-panel.open { display: flex; }
    #skapa-header {
      background: ${ACCENT}; color: white; padding: 12px 16px; font-weight: 600;
    }
    #skapa-messages {
      flex: 1; overflow-y: auto; padding: 12px; font-size: 14px; line-height: 1.4;
    }
    .skapa-msg { margin-bottom: 10px; max-width: 85%; padding: 8px 12px; border-radius: 10px; }
    .skapa-msg.user { background: #eee; margin-left: auto; }
    .skapa-msg.bot { background: ${ACCENT}22; }
    #skapa-form { display: flex; border-top: 1px solid #eee; }
    #skapa-input {
      flex: 1; border: none; padding: 10px; font-size: 14px; outline: none;
    }
    #skapa-form button {
      border: none; background: ${ACCENT}; color: white; padding: 0 16px; cursor: pointer;
    }
  `;
  document.head.appendChild(style);

  var bubble = document.createElement("button");
  bubble.id = "skapa-bubble";
  bubble.textContent = "💬";

  var panel = document.createElement("div");
  panel.id = "skapa-panel";
  panel.innerHTML =
    '<div id="skapa-header">' + TITLE + '</div>' +
    '<div id="skapa-messages"></div>' +
    '<form id="skapa-form">' +
      '<input id="skapa-input" type="text" placeholder="Pose ta question..." autocomplete="off" />' +
      '<button type="submit">Envoyer</button>' +
    '</form>';

  document.body.appendChild(bubble);
  document.body.appendChild(panel);

  var messages = panel.querySelector("#skapa-messages");
  var form = panel.querySelector("#skapa-form");
  var input = panel.querySelector("#skapa-input");

  bubble.addEventListener("click", function () {
    panel.classList.toggle("open");
  });

  function addMessage(text, who) {
    var el = document.createElement("div");
    el.className = "skapa-msg " + who;
    el.textContent = text;
    messages.appendChild(el);
    messages.scrollTop = messages.scrollHeight;
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var text = input.value.trim();
    if (!text) return;

    addMessage(text, "user");
    input.value = "";

    var loadingEl = document.createElement("div");
    loadingEl.className = "skapa-msg bot";
    loadingEl.textContent = "...";
    messages.appendChild(loadingEl);
    messages.scrollTop = messages.scrollHeight;

    fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    })
      .then(function (res) { return res.json(); })
      .then(function (data) {
        loadingEl.textContent = data.reply || "Desole, je n'ai pas de reponse.";
      })
      .catch(function () {
        loadingEl.textContent = "Erreur de connexion au serveur.";
      });
  });
})();
