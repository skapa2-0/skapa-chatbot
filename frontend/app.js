/**
 * Skapa Chatbot — page de démo (carte « Connecter un site » + bulle de chat)
 *
 * Corrections :
 *  - BUG PRINCIPAL : SITE_URL était une constante lue au chargement. Après
 *    « Analyser et adapter », window.SKAPA_SITE_URL changeait mais la bulle
 *    continuait d'envoyer site_url = null -> elle répondait avec TOUTE la
 *    base (tous sites mélangés). Le site actif est maintenant un état lu à
 *    chaque message, mémorisé dans le navigateur.
 *  - Le bouton envoyait la requête sans token admin -> 401 systématique.
 *    Le token est demandé une fois (si le serveur l'exige) puis gardé
 *    pour la session.
 *  - Le scraping tourne en tâche de fond côté serveur : on suit la
 *    progression (pages analysées) au lieu d'attendre une requête qui
 *    finissait en timeout.
 *  - Historique de conversation envoyé (questions de relance) + liens
 *    vers les pages sources sous chaque réponse.
 */

// ── Config ──────────────────────────────────────────────────────────────────
const API_URL = (window.SKAPA_API_URL || 'http://localhost:8000').replace(/\/+$/, '');
const POLL_MS = 1200;

// ── Stockage navigateur (peut être indisponible : navigation privée…) ───────
const store = {
  get(k, session = false) {
    try { return (session ? sessionStorage : localStorage).getItem(k); } catch { return null; }
  },
  set(k, v, session = false) {
    try { (session ? sessionStorage : localStorage).setItem(k, v); } catch { /* ignore */ }
  },
  del(k, session = false) {
    try { (session ? sessionStorage : localStorage).removeItem(k); } catch { /* ignore */ }
  },
};

// ── État ────────────────────────────────────────────────────────────────────
const state = {
  // Site actif : fixé par l'intégration (window.SKAPA_SITE_URL) ou par la dernière analyse
  siteUrl: window.SKAPA_SITE_URL || store.get('skapa_site_url') || null,
  siteName: store.get('skapa_site_name') || null,
  adminToken: window.SKAPA_ADMIN_TOKEN || store.get('skapa_admin_token', true) || '',
  history: [],          // [{role, content}] — derniers échanges envoyés au backend
  sending: false,
};

// ── DOM ─────────────────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);
const chatToggle = $('chatToggle');
const chatPanel = $('chatPanel');
const closeBtn = $('closeBtn');
const messagesEl = $('messages');
const chipsWrap = $('chips');
const form = $('chatForm');
const input = $('messageInput');
const chatName = $('chatName');
const chatAvatar = $('chatAvatar');

const siteUrlInput = $('siteUrlInput');
const analyseBtn = $('analyseBtn');
const analyseProgress = $('analyseProgress');
const analyseError = $('analyseError');
const siteStatus = $('siteStatus');
const statusAvatar = $('statusAvatar');
const statusName = $('statusName');
const statusUrl = $('statusUrl');
const statPages = $('statPages');
const statReady = $('statReady');

const CHIPS = [
  'Quelles sont les formations disponibles ?',
  'Prix et tarifs',
  'Disponibilités',
  'Comment vous contacter ?',
];

const BTN_IDLE_HTML = analyseBtn.innerHTML;

// ── Helpers ─────────────────────────────────────────────────────────────────

function normalizeInputUrl(raw) {
  let url = (raw || '').trim();
  if (!url) return null;
  if (!/^https?:\/\//i.test(url)) url = `https://${url}`;
  try {
    const u = new URL(url);
    if (!u.hostname.includes('.') && u.hostname !== 'localhost') return null;
    return u.href;
  } catch {
    return null;
  }
}

function hostOf(url) {
  try { return new URL(url).hostname.replace(/^www\./, ''); } catch { return url; }
}

function nameFromDomain(domain) {
  const base = domain.split('.')[0].replace(/[-_]/g, ' ');
  return base.replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Gras (**x**) + URLs cliquables, sans jamais injecter de HTML (pas de XSS). */
function parseBotText(rawText) {
  const fragment = document.createDocumentFragment();
  const tokens = rawText.split(/(\*\*[^*]+\*\*|https?:\/\/[^\s<>()\[\]]+[^\s<>().,;:!?\[\]])/g);
  for (const token of tokens) {
    if (!token) continue;
    if (token.startsWith('**') && token.endsWith('**') && token.length > 4) {
      const b = document.createElement('strong');
      b.textContent = token.slice(2, -2);
      fragment.appendChild(b);
    } else if (/^https?:\/\//.test(token)) {
      const a = document.createElement('a');
      a.href = token;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      a.textContent = token;
      fragment.appendChild(a);
    } else {
      fragment.appendChild(document.createTextNode(token));
    }
  }
  return fragment;
}

// ── SVG icons (vectoriels, sans dépendance externe) ─────────────────────────
const ICONS = {
  bot:
    '<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">' +
    '<path d="M6 18.5V7.2A2.2 2.2 0 0 1 8.2 5h7.6A2.2 2.2 0 0 1 18 7.2v5.6A2.2 2.2 0 0 1 15.8 15H9.7L6 18.5Z"/>' +
    '<circle cx="9.5" cy="10" r="1"/><circle cx="14.5" cy="10" r="1"/>' +
    '</svg>',
  cap:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<path d="M22 10 12 5 2 10l10 5 10-5Z"/>' +
    '<path d="M6 12v5a6 6 0 0 0 12 0v-5"/>' +
    '</svg>',
  refresh:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<path d="M21 12a9 9 0 1 1-3.5-7.1"/>' +
    '<path d="M21 4v5h-5"/>' +
    '</svg>',
  chevron:
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
    '<polyline points="9 6 15 12 9 18"/>' +
    '</svg>',
};

/**
 * Détecte une liste structurée dans la réponse du bot et la segmente en
 * { intro, items[{title, meta, badge?}], count }.
 * Retourne null si moins de 2 éléments de liste sont détectés.
 */
function parseStructuredResponse(rawText) {
  const normalized = rawText.replace(/\r\n/g, '\n');
  // Puces markdown fréquentes: *, -, •, 1. / 1)
  const bulletRe = /(?:^|\n)\s*(?:[*\-•]|\d+[.)])\s+([^\n]+)/g;
  const items = [];
  let firstMatchIdx = -1;
  let m;
  while ((m = bulletRe.exec(normalized)) !== null) {
    if (firstMatchIdx === -1) firstMatchIdx = m.index + m[0].indexOf(m[1]) - 2;
    const raw = m[1].trim();
    if (!raw || raw.length > 180) continue; // trop long = probablement une phrase
    items.push(parseItemLine(raw));
  }
  if (items.length < 2) return null;

  // Tout ce qui précède la première puce = intro
  const intro = normalized
    .slice(0, Math.max(0, firstMatchIdx))
    .replace(/\n+$/, '')
    .trim();

  return { intro, items, count: items.length };
}

/** Extrait titre + sous-titre d'une ligne de puce. */
function parseItemLine(line) {
  // Badge éventuel: "(POPULAIRE)" ou "[POPULAIRE]" ou "— POPULAIRE" en fin
  let badge = null;
  const badgeMatch = line.match(/[\s(\[—–\-]+(POPULAIRE|NOUVEAU|RECOMMANDÉ|TOP)[\s)\]]*$/i);
  if (badgeMatch) {
    badge = badgeMatch[1].toUpperCase();
    line = line.slice(0, badgeMatch.index).trim();
  }

  // Pattern 1: **Titre** — meta  OU  **Titre** : meta
  let mm = line.match(/^\*\*([^*]+)\*\*\s*[—–:·\-]?\s*(.*)$/);
  if (mm) return { title: mm[1].trim(), meta: cleanMeta(mm[2]), badge };

  // Pattern 2: Titre — meta  (séparateur typographique au milieu)
  mm = line.match(/^(.+?)\s+[—–]\s+(.+)$/);
  if (mm) return { title: stripFormatting(mm[1]), meta: cleanMeta(mm[2]), badge };

  // Pattern 3: Titre : meta
  mm = line.match(/^([^:]{3,80}):\s+(.+)$/);
  if (mm) return { title: stripFormatting(mm[1]), meta: cleanMeta(mm[2]), badge };

  // Fallback: pas de séparation claire
  return { title: stripFormatting(line), meta: '', badge };
}

function stripFormatting(s) {
  return s.replace(/\*\*/g, '').trim();
}
function cleanMeta(s) {
  return stripFormatting(s).replace(/\s*\.$/, '');
}

/** Choisit l'icône selon le contenu du titre. */
function pickIcon(title) {
  const t = title.toLowerCase();
  if (/conseil|contact|parler|aide|rdv|rendez/.test(t)) return ICONS.refresh;
  return ICONS.cap; // par défaut: diplôme (formations)
}

/** Crée un bouton carte interactif. */
function buildActionCard({ title, meta, badge }, onClick) {
  const card = document.createElement('button');
  card.type = 'button';
  card.className = 'action-card';
  card.setAttribute('aria-label', title + (meta ? ' — ' + meta : ''));

  const iconWrap = document.createElement('div');
  iconWrap.className = 'action-card__icon';
  iconWrap.innerHTML = pickIcon(title);

  const body = document.createElement('div');
  body.className = 'action-card__body';
  const titleEl = document.createElement('div');
  titleEl.className = 'action-card__title';
  titleEl.textContent = title;
  body.appendChild(titleEl);
  if (meta) {
    const metaEl = document.createElement('div');
    metaEl.className = 'action-card__meta';
    metaEl.textContent = meta;
    body.appendChild(metaEl);
  }

  const chev = document.createElement('span');
  chev.className = 'action-card__chevron';
  chev.innerHTML = ICONS.chevron;

  card.append(iconWrap, body, chev);

  if (badge) {
    const b = document.createElement('span');
    b.className = 'action-card__badge';
    b.textContent = badge;
    card.appendChild(b);
  }

  if (typeof onClick === 'function') card.addEventListener('click', onClick);
  return card;
}

/** Mot pluralisé pour le compteur sous les cartes. */
function pluralLabel(count, items) {
  const t = items.map((i) => (i.title + ' ' + i.meta).toLowerCase()).join(' ');
  if (/formation|cours|module/.test(t)) return `${count} formation${count > 1 ? 's' : ''} correspondent`;
  if (/produit|offre/.test(t))         return `${count} offre${count > 1 ? 's' : ''} correspondent`;
  return `${count} résultat${count > 1 ? 's' : ''}`;
}

function scrollToBottom() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

/** role = 'bot' | 'user' | 'system' | 'error' */
function addMessage(text, role = 'bot', sources = [], extraCards = null) {
  const wrapper = document.createElement('div');
  wrapper.className = `message ${role}`;

  // --- Avatar bot à gauche (uniquement pour les messages bot/erreur) ---
  if (role === 'bot' || role === 'error') {
    const avatar = document.createElement('div');
    avatar.className = 'bot-avatar';
    avatar.innerHTML = ICONS.bot;
    wrapper.appendChild(avatar);
  }

  // --- Contenu (bulle + cartes éventuelles) ---
  const content = document.createElement('div');
  content.className = role === 'bot' || role === 'error' ? 'bot-content' : '';

  // Parsing structuré pour messages bot uniquement
  let parsed = null;
  if (role === 'bot') parsed = parseStructuredResponse(text);

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  if (parsed) {
    // Si la liste a été détectée: la bulle ne contient que l'intro
    const introText = parsed.intro || 'Voici les options disponibles :';
    bubble.appendChild(parseBotText(introText));
  } else if (role === 'bot') {
    bubble.appendChild(parseBotText(text));
  } else {
    bubble.textContent = text;
  }
  content.appendChild(bubble);

  // --- Cartes d'actions (depuis parsing ou fournies explicitement) ---
  const cards = extraCards || (parsed ? parsed.items : null);
  if (cards && cards.length) {
    const cardsWrap = document.createElement('div');
    cardsWrap.className = 'action-cards';
    for (const item of cards) {
      cardsWrap.appendChild(
        buildActionCard(item, () => {
          const query = item.query || item.title;
          sendMessage(query);
        })
      );
    }
    content.appendChild(cardsWrap);

    // Footer de synthèse si plus de 2 cartes
    if (cards.length >= 2 && parsed) {
      const footer = document.createElement('div');
      footer.className = 'cards-footer';
      footer.textContent = pluralLabel(cards.length, cards);
      content.appendChild(footer);
    }
  }

  // --- Sources sous la bulle ---
  if (role === 'bot' && sources.length) {
    const list = document.createElement('div');
    list.className = 'sources';
    for (const s of sources) {
      const a = document.createElement('a');
      a.href = s.url;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      a.title = s.url;
      a.textContent = (s.title || s.url).split(/\s[|–—]\s/)[0];
      list.appendChild(a);
    }
    content.appendChild(list);
  }

  if (role === 'bot' || role === 'error') wrapper.appendChild(content);
  else wrapper.appendChild(bubble);

  messagesEl.appendChild(wrapper);
  scrollToBottom();
  return wrapper;
}

function addTyping() {
  const wrapper = document.createElement('div');
  wrapper.className = 'message bot';

  const avatar = document.createElement('div');
  avatar.className = 'bot-avatar';
  avatar.innerHTML = ICONS.bot;
  wrapper.appendChild(avatar);

  const content = document.createElement('div');
  content.className = 'bot-content';
  const indicator = document.createElement('div');
  indicator.className = 'typing';
  indicator.setAttribute('aria-label', "L'assistant écrit…");
  for (let i = 0; i < 3; i++) indicator.appendChild(document.createElement('span'));
  content.appendChild(indicator);
  wrapper.appendChild(content);

  messagesEl.appendChild(wrapper);
  scrollToBottom();
  return wrapper;
}

function renderChips() {
  chipsWrap.replaceChildren();
  for (const label of CHIPS) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'chip';
    btn.textContent = label;
    btn.addEventListener('click', () => sendMessage(label));
    chipsWrap.appendChild(btn);
  }
}

function welcomeText() {
  const name = state.siteName || (state.siteUrl ? hostOf(state.siteUrl) : null);
  return state.siteUrl
    ? `Bonjour, je suis **Ada**, l'assistante de ${name}.\n\nJe connais maintenant le site. Comment puis-je vous aider aujourd'hui ?`
    : 'Bonjour ! Je suis votre assistant. Analysez d\'abord un site avec « Analyser et adapter », puis posez-moi vos questions.';
}

/** Cartes d'actions proposées dès l'accueil (quand un site est analysé). */
function welcomeActionCards() {
  return [
    { title: 'Voir les formations',  meta: 'Explorer le catalogue', query: 'Quelles sont les formations disponibles ?' },
    { title: 'Être conseillé',       meta: 'Parler de votre projet', query: 'J\'aimerais être conseillé sur mon projet.' },
  ];
}

/** Réinitialise la conversation (nouveau site analysé). */
function resetConversation() {
  state.history = [];
  messagesEl.replaceChildren();
  if (state.siteUrl) {
    addMessage(welcomeText(), 'bot', [], welcomeActionCards());
  } else {
    addMessage(welcomeText(), 'bot');
  }
  renderChips();
}

function applySiteBranding() {
  const name = state.siteName || (state.siteUrl ? nameFromDomain(hostOf(state.siteUrl)) : 'Skapa');
  chatName.textContent = `Assistant ${name}`;
  chatAvatar.textContent = name.charAt(0).toUpperCase();
}

function showSiteCard({ name, url, pages, ready = true }) {
  const domain = hostOf(url);
  statusAvatar.textContent = (name || domain).charAt(0).toUpperCase();
  statusName.textContent = name || nameFromDomain(domain);
  statusUrl.textContent = domain;
  statPages.textContent = pages ?? '—';
  statReady.textContent = ready ? '100 %' : '0 %';
  siteStatus.hidden = false;
}

function setActiveSite(url, name) {
  state.siteUrl = url;
  state.siteName = name || nameFromDomain(hostOf(url));
  store.set('skapa_site_url', url);
  store.set('skapa_site_name', state.siteName);
  applySiteBranding();
  resetConversation();
}

// ── Chat ────────────────────────────────────────────────────────────────────

async function sendMessage(question) {
  question = (question || '').trim();
  if (!question || state.sending) return;
  state.sending = true;

  addMessage(question, 'user');
  chipsWrap.replaceChildren();
  const typingEl = addTyping();

  try {
    const body = { message: question, history: state.history.slice(-6) };
    if (state.siteUrl) {
      body.site_url = state.siteUrl;            // <- lu à chaque envoi (le bug venait d'ici)
      if (state.siteName) body.platform_name = state.siteName;
    }

    const res = await fetch(`${API_URL}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);

    const reply = data.reply || 'Aucune réponse reçue.';
    typingEl.remove();
    addMessage(reply, 'bot', data.sources || []);
    state.history.push({ role: 'user', content: question }, { role: 'assistant', content: reply });
    state.history = state.history.slice(-12);
  } catch (err) {
    typingEl.remove();
    const msg = err instanceof TypeError
      ? `Impossible de joindre l'API (${API_URL}). Le backend est-il démarré ?`
      : err.message;
    addMessage(`Erreur : ${msg}`, 'error');
  } finally {
    state.sending = false;
  }
}

// ── Ouverture / fermeture ───────────────────────────────────────────────────

let welcomed = false;
function openChat() {
  chatPanel.classList.add('open');
  chatToggle.classList.add('is-open');
  chatToggle.setAttribute('aria-expanded', 'true');
  chatToggle.setAttribute('aria-label', 'Fermer le chat');
  if (!welcomed) {
    welcomed = true;
    resetConversation();
  }
  input.focus();
}

function closeChat() {
  chatPanel.classList.remove('open');
  chatToggle.classList.remove('is-open');
  chatToggle.setAttribute('aria-expanded', 'false');
  chatToggle.setAttribute('aria-label', 'Ouvrir le chat');
}

chatToggle.addEventListener('click', () => {
  chatPanel.classList.contains('open') ? closeChat() : openChat();
});
closeBtn.addEventListener('click', closeChat);
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && chatPanel.classList.contains('open')) closeChat();
});

form.addEventListener('submit', (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  sendMessage(text);
});

// ── Analyser et adapter ─────────────────────────────────────────────────────

function setBusy(busy, label = 'Analyse en cours…') {
  analyseBtn.disabled = busy;
  siteUrlInput.disabled = busy;
  if (busy) {
    analyseBtn.replaceChildren();
    const spinner = document.createElement('div');
    spinner.className = 'btn-spinner';
    analyseBtn.append(spinner, document.createTextNode(` ${label}`));
  } else {
    analyseBtn.innerHTML = BTN_IDLE_HTML;
  }
}

function showError(msg) {
  analyseError.textContent = msg;
  analyseError.hidden = !msg;
}

function showProgress(msg) {
  analyseProgress.textContent = msg || '';
  analyseProgress.hidden = !msg;
}

async function postScrape(url) {
  const headers = { 'Content-Type': 'application/json' };
  if (state.adminToken) headers.Authorization = `Bearer ${state.adminToken}`;
  return fetch(`${API_URL}/api/scrape/run`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ url }),
  });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const POLL_TIMEOUT_MS = 10 * 60 * 1000; // 10 minutes max

async function pollJob(jobId) {
  const deadline = Date.now() + POLL_TIMEOUT_MS;
  for (;;) {
    if (Date.now() > deadline) throw new Error("L'analyse a dépassé le délai maximum (10 min). Réessayez sur un site moins volumineux.");
    await sleep(POLL_MS);
    let res;
    try {
      res = await fetch(`${API_URL}/api/scrape/status/${encodeURIComponent(jobId)}`);
    } catch {
      continue; // coupure réseau passagère : on réessaie
    }
    const job = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(job.error || `HTTP ${res.status}`);

    if (job.status === 'running' || job.status === 'queued') {
      const n = job.pages_done || 0;
      setBusy(true, n ? `Analyse… ${n} page${n > 1 ? 's' : ''}` : 'Analyse en cours…');
      showProgress(job.current_url ? `Lecture : ${job.current_url}` : 'Démarrage du crawl…');
      continue;
    }
    if (job.status === 'success') return job.result;
    throw new Error(job.error || "L'analyse a échoué.");
  }
}

async function analyse() {
  showError('');
  const url = normalizeInputUrl(siteUrlInput.value);
  if (!url) {
    siteUrlInput.classList.add('input-error');
    siteUrlInput.focus();
    showError('Adresse invalide. Exemple : https://skapa-academy.fr');
    setTimeout(() => siteUrlInput.classList.remove('input-error'), 2000);
    return;
  }
  siteUrlInput.value = url;
  setBusy(true);
  showProgress('Connexion au site…');

  try {
    let res = await postScrape(url);

    // Le serveur exige le token admin : on le demande une seule fois
    if (res.status === 401) {
      const token = window.prompt(
        'Token administrateur requis pour analyser un site (ADMIN_TOKEN du fichier backend/.env) :'
      );
      if (!token) throw new Error('Analyse annulée : token administrateur requis.');
      state.adminToken = token.trim();
      res = await postScrape(url);
      if (res.status === 401) {
        state.adminToken = '';
        store.del('skapa_admin_token', true);
        throw new Error('Token administrateur invalide.');
      }
      store.set('skapa_admin_token', state.adminToken, true);
    }

    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);

    const result = data.job_id ? await pollJob(data.job_id) : data;

    const siteUrl = result.site_url || url;
    const name = result.site_title || nameFromDomain(hostOf(siteUrl));
    showSiteCard({ name, url: siteUrl, pages: result.pages_scraped });
    setActiveSite(siteUrl, name);
    siteStatus.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    if (!chatPanel.classList.contains('open')) openChat();
  } catch (err) {
    const msg = err instanceof TypeError
      ? `Impossible de joindre l'API (${API_URL}). Le backend est-il démarré ?`
      : err.message;
    showError(`Erreur lors de l'analyse : ${msg}`);
  } finally {
    setBusy(false);
    showProgress('');
  }
}

analyseBtn.addEventListener('click', analyse);
siteUrlInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') { e.preventDefault(); analyse(); }
});

// ── Init : restaure le dernier site analysé s'il est toujours indexé ───────

async function restoreSite() {
  applySiteBranding();
  if (!state.siteUrl) return;
  siteUrlInput.value = state.siteUrl;
  try {
    const res = await fetch(`${API_URL}/api/site?url=${encodeURIComponent(state.siteUrl)}`);
    const data = await res.json();
    if (res.ok && data.indexed) {
      showSiteCard({ name: state.siteName, url: state.siteUrl, pages: data.pages ?? '—' });
    } else if (res.ok && !window.SKAPA_SITE_URL) {
      // base vidée / autre serveur : on oublie ce site
      state.siteUrl = null;
      state.siteName = null;
      store.del('skapa_site_url');
      store.del('skapa_site_name');
      applySiteBranding();
    }
  } catch { /* API éteinte : on garde l'état, l'erreur s'affichera au premier message */ }
}

renderChips();
restoreSite();
