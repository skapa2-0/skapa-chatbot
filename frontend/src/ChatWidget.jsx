import React, { useRef, useState } from "react";

export default function ChatWidget({
  apiUrl = "http://localhost:5000/api",
  siteId = "",
  title = "Assistant",
  primaryColor = "#4f46e5",
}) {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState([
    { role: "bot", text: "Bonjour ! Posez-moi une question, je réponds à partir du contenu du site." },
  ]);
  const bottomRef = useRef(null);

  const scrollToBottom = () => {
    setTimeout(() => bottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
  };

  const sendMessage = async () => {
    const question = input.trim();
    if (!question || loading) return;

    setMessages((prev) => [...prev, { role: "user", text: question }]);
    setInput("");
    setLoading(true);
    scrollToBottom();

    try {
      const res = await fetch(`${apiUrl}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, site_id: siteId }),
      });
      const data = await res.json();
      const text = res.ok ? data.answer : data.error || "Une erreur est survenue.";
      setMessages((prev) => [...prev, { role: "bot", text }]);
    } catch {
      setMessages((prev) => [...prev, { role: "bot", text: "Impossible de contacter le serveur." }]);
    } finally {
      setLoading(false);
      scrollToBottom();
    }
  };

  const onKeyDown = (e) => {
    if (e.key === "Enter") sendMessage();
  };

  return (
    <div className="skapa-widget" style={{ "--skapa-color": primaryColor }}>
      {open && (
        <div className="skapa-panel">
          <div className="skapa-header">
            <span>{title}</span>
            <button className="skapa-close" onClick={() => setOpen(false)} aria-label="Fermer">
              ×
            </button>
          </div>

          <div className="skapa-messages">
            {messages.map((m, i) => (
              <div key={i} className={`skapa-message skapa-${m.role}`}>
                {m.text}
              </div>
            ))}
            {loading && <div className="skapa-message skapa-bot skapa-typing">…</div>}
            <div ref={bottomRef} />
          </div>

          <div className="skapa-input-row">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Votre question..."
              disabled={loading}
            />
            <button onClick={sendMessage} disabled={loading}>
              Envoyer
            </button>
          </div>
        </div>
      )}

      <button className="skapa-bubble" onClick={() => setOpen((o) => !o)} aria-label="Ouvrir le chat">
        {open ? "×" : "💬"}
      </button>
    </div>
  );
}
