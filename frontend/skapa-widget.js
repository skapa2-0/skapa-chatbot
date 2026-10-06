/**
 * Widget de chat Skapa — à coller sur n'importe quel site.
 *
 * Utilisation :
 *   <script
 *     src="https://ton-domaine.com/skapa-widget.js"
 *     data-api-url="https://ton-api.com"
 *     data-site-url="https://mon-site.com"
 *     data-title="Assistant"
 *     data-color="#5b3fd4"
 *   ></script>
 *
 * Aucune dépendance externe, pas de build : un seul fichier JS pur.
 */
(function () {
  "use strict";

  var currentScript = document.currentScript;
  // Accepte "https://api.com" comme "https://api.com/chat" (le README utilisait
  // la 2e forme, ce qui produisait des appels vers /chat/chat -> 404)
  var API_URL  = (currentScript.getAttribute("data-api-url")  || "http://localhost:8000")
    .replace(/\/+$/, "").replace(/\/chat$/, "");
  var SITE_URL = currentScript.getAttribute("data-site-url")  || "";
  var TITLE    = currentScript.getAttribute("data-title")     || "Assistant";
  var ACCENT   = currentScript.getAttribute("data-color")     || "#5b3fd4";

  /* ── Styles ── */
  var style = document.createElement("style");
  style.textContent =
    "#skapa-bubble{position:fixed;bottom:24px;right:24px;width:56px;height:56px;" +
    "border-radius:50%;background:" + ACCENT + ";color:white;border:none;" +
    "font-size:22px;cursor:pointer;box-shadow:0 6px 20px rgba(0,0,0,.22);z-index:999999;" +
    "display:flex;align-items:center;justify-content:center;transition:transform .15s}" +
    "#skapa-bubble:hover{transform:scale(1.08)}" +
    "#skapa-panel{position:fixed;bottom:92px;right:24px;width:340px;max-width:90vw;" +
    "max-height:min(480px,70dvh);background:#f7f8fa;border-radius:16px;" +
    "box-shadow:0 16px 40px rgba(0,0,0,.18);display:none;flex-direction:column;" +
    "overflow:hidden;font-family:system-ui,sans-serif;z-index:999999;border:1px solid #e2e5ef}" +
    "#skapa-panel.open{display:flex}" +
    "#skapa-header{background:" + ACCENT + ";color:white;padding:14px 16px;" +
    "font-weight:700;font-size:.95rem;flex-shrink:0}" +
    "#skapa-messages{flex:1;overflow-y:auto;padding:14px 12px 8px;background:#eef0f7;scroll-behavior:smooth}" +
    ".skapa-msg{margin-bottom:10px;max-width:84%;}" +
    ".skapa-msg .bub{border-radius:14px;padding:9px 12px;font-size:.88rem;line-height:1.5;word-break:break-word}" +
    ".skapa-msg.user{margin-left:auto}.skapa-msg.user .bub{background:" + ACCENT + ";color:#fff;border-bottom-right-radius:4px}" +
    ".skapa-msg.bot .bub{background:#edf0f7;color:#141827;border-bottom-left-radius:4px}" +
    ".skapa-msg.error .bub{background:#fde8e8;color:#991b1b}" +
    ".skapa-typing{display:inline-flex;gap:5px;align-items:center;padding:9px 12px;" +
    "border-radius:14px;border-bottom-left-radius:4px;background:#edf0f7}" +
    ".skapa-typing span{width:7px;height:7px;border-radius:50%;background:#8892aa;" +
    "animation:st 1.2s infinite ease-in-out}" +
    ".skapa-typing span:nth-child(2){animation-delay:.16s}" +
    ".skapa-typing span:nth-child(3){animation-delay:.32s}" +
    "@keyframes st{0%,80%,100%{transform:translateY(0);opacity:.5}40%{transform:translateY(-5px);opacity:1}}" +
    "#skapa-form{display:flex;border-top:1px solid #e2e5ef;background:#f7f8fa;padding:8px}" +
    "#skapa-input{flex:1;border:1.5px solid #e2e5ef;border-radius:10px;padding:8px 11px;" +
    "font-size:.88rem;outline:none;background:#fff;color:#141827;transition:border-color .15s}" +
    "#skapa-input:focus{border-color:" + ACCENT + "}" +
    "#skapa-form button{border:none;background:" + ACCENT + ";color:white;padding:0 14px;" +
    "border-radius:10px;cursor:pointer;margin-left:6px;font-weight:700;font-size:.85rem;" +
    "transition:opacity .15s}" +
    "#skapa-form button:hover{opacity:.9}" +
    "#skapa-form button:focus-visible{outline:3px solid " + ACCENT + ";outline-offset:2px}";
  document.head.appendChild(style);

  /* ── DOM ── */
  var bubble = document.createElement("button");
  bubble.id = "skapa-bubble";
  bubble.setAttribute("aria-label", "Ouvrir le chat");
  bubble.setAttribute("aria-expanded", "false");
  bubble.innerHTML =
    '<svg viewBox="0 0 24 24" fill="currentColor" width="24" height="24" aria-hidden="true">' +
    '<path d="M6 18.5V7.2A2.2 2.2 0 0 1 8.2 5h7.6A2.2 2.2 0 0 1 18 7.2v5.6A2.2 2.2 0 0 1 15.8 15H9.7L6 18.5Z"/>' +
    '</svg>';

  var panel = document.createElement("div");
  panel.id = "skapa-panel";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", TITLE);
  panel.innerHTML =
    '<div id="skapa-header"></div>' +
    '<div id="skapa-messages"></div>' +
    '<form id="skapa-form">' +
      '<input id="skapa-input" type="text" placeholder="Posez votre question…" autocomplete="off" aria-label="Votre message"/>' +
      '<button type="submit">Envoyer</button>' +
    "</form>";

  panel.querySelector("#skapa-header").textContent = TITLE;
  document.body.appendChild(bubble);
  document.body.appendChild(panel);

  var history = [];
  var messagesEl = panel.querySelector("#skapa-messages");
  var form       = panel.querySelector("#skapa-form");
  var input      = panel.querySelector("#skapa-input");

  /* ── Helpers ── */
  function addMsg(text, who) {
    var wrap = document.createElement("div");
    wrap.className = "skapa-msg " + who;
    var bub = document.createElement("div");
    bub.className = "bub";
    bub.textContent = text;
    wrap.appendChild(bub);
    messagesEl.appendChild(wrap);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return wrap;
  }

  function addTyping() {
    var wrap = document.createElement("div");
    wrap.className = "skapa-msg bot";
    var t = document.createElement("div");
    t.className = "skapa-typing";
    t.innerHTML = "<span></span><span></span><span></span>";
    wrap.appendChild(t);
    messagesEl.appendChild(wrap);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return wrap;
  }

  /* ── Toggle ── */
  bubble.addEventListener("click", function () {
    var isOpen = panel.classList.toggle("open");
    bubble.setAttribute("aria-expanded", String(isOpen));
    bubble.setAttribute("aria-label", isOpen ? "Fermer le chat" : "Ouvrir le chat");
    if (isOpen) input.focus();
  });

  /* ── Submit ── */
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var text = input.value.trim();
    if (!text) return;
    input.value = "";

    addMsg(text, "user");
    var typingEl = addTyping();

    var body = { message: text, history: history.slice(-6) };
    if (SITE_URL) body.site_url = SITE_URL;

    fetch(API_URL + "/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(function (res) {
        if (!res.ok) return res.json().then(function (d) { throw new Error(d.error || "HTTP " + res.status); });
        return res.json();
      })
      .then(function (data) {
        typingEl.remove();
        var reply = data.reply || "Aucune réponse reçue.";
        addMsg(reply, "bot");
        history.push({ role: "user", content: text }, { role: "assistant", content: reply });
        history = history.slice(-12);
      })
      .catch(function (err) {
        typingEl.remove();
        addMsg("Erreur : " + (err.message || "Connexion impossible."), "error");
      });
  });
})();
