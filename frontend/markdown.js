/**
 * Rendu Markdown minimal et SÛR pour les réponses du bot.
 * Gère : paragraphes, retours à la ligne, listes (- * • / 1.), titres (#),
 * **gras**, liens [texte](url) et URLs nues.
 * Aucun innerHTML : tout passe par createElement / textContent (pas de XSS).
 */
(function () {
  const INLINE_RE = /(\*\*[^*\n]+\*\*|\[[^\]\n]+\]\(https?:\/\/[^)\s]+\)|https?:\/\/[^\s<>()\[\]"']+)/g;
  const BULLET_RE = /^\s*(?:[-*•]|(\d+)[.)])\s+(.*)$/;

  /** Libellé court pour une URL affichée seule : domaine + chemin. */
  function shortUrl(url) {
    try {
      const u = new URL(url);
      const path = u.pathname.replace(/\/$/, '');
      return u.hostname.replace(/^www\./, '') + (path.length > 40 ? path.slice(0, 40) + '…' : path);
    } catch { return url; }
  }

  function link(url, label) {
    const a = document.createElement('a');
    a.href = url;
    a.target = '_blank';
    a.rel = 'noopener noreferrer';
    a.textContent = label;
    return a;
  }

  function inline(text) {
    const frag = document.createDocumentFragment();
    for (const tok of text.split(INLINE_RE)) {
      if (!tok) continue;
      let m;
      if (tok.startsWith('**') && tok.endsWith('**') && tok.length > 4) {
        const b = document.createElement('strong');
        b.textContent = tok.slice(2, -2);
        frag.appendChild(b);
      } else if ((m = tok.match(/^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/))) {
        const label = /^https?:\/\//.test(m[1]) ? shortUrl(m[2]) : m[1];
        frag.appendChild(link(m[2], label));
      } else if (/^https?:\/\//.test(tok)) {
        const url = tok.replace(/[.,;:!?»]+$/, '');
        frag.appendChild(link(url, shortUrl(url)));
        if (url.length < tok.length) frag.appendChild(document.createTextNode(tok.slice(url.length)));
      } else {
        frag.appendChild(document.createTextNode(tok));
      }
    }
    return frag;
  }

  function renderMarkdown(text) {
    const frag = document.createDocumentFragment();
    const lines = String(text || '').replace(/\r\n/g, '\n').split('\n');
    let para = [];
    let list = null;

    const flushPara = () => {
      if (!para.length) return;
      const p = document.createElement('p');
      para.forEach((ln, i) => {
        if (i) p.appendChild(document.createElement('br'));
        p.appendChild(inline(ln));
      });
      frag.appendChild(p);
      para = [];
    };
    const flushList = () => { if (list) { frag.appendChild(list); list = null; } };

    for (const raw of lines) {
      const line = raw.trimEnd();
      const bullet = line.match(BULLET_RE);
      if (bullet) {
        flushPara();
        const tag = bullet[1] ? 'ol' : 'ul';
        if (!list || list.tagName.toLowerCase() !== tag) { flushList(); list = document.createElement(tag); }
        const li = document.createElement('li');
        li.appendChild(inline(bullet[2]));
        list.appendChild(li);
      } else if (!line.trim()) {
        flushPara();
        flushList();
      } else if (/^#{1,6}\s+/.test(line)) {
        flushPara();
        flushList();
        const p = document.createElement('p');
        const s = document.createElement('strong');
        s.appendChild(inline(line.replace(/^#{1,6}\s+/, '')));
        p.appendChild(s);
        frag.appendChild(p);
      } else {
        flushList();
        para.push(line.trim());
      }
    }
    flushPara();
    flushList();
    return frag;
  }

  window.renderMarkdown = renderMarkdown;
})();
