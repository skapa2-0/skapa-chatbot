// admin.js — espace administration Skapa Chatbot
const $ = id => document.getElementById(id);
const TOKEN_KEY = 'skapa_admin_token';
const getToken = () => sessionStorage.getItem(TOKEN_KEY);

async function api(path, opts = {}) {
  const r = await fetch(API_URL + path, {
    ...opts,
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken()}` },
  }).catch(() => null);
  if (!r) return null;
  if (r.status === 401) { logout(); return null; }
  return r;
}

// ── Auth ──────────────────────────────────────────────────────────────────────
function logout() {
  sessionStorage.removeItem(TOKEN_KEY);
  $('adminApp').hidden = true;
  $('loginView').hidden = false;
}

async function login() {
  const t = $('tokenInput').value.trim();
  $('loginError').textContent = '';
  if (!t) return;
  sessionStorage.setItem(TOKEN_KEY, t);
  const r = await api('/api/sites');
  if (!r || !r.ok) {
    sessionStorage.removeItem(TOKEN_KEY);
    $('loginError').textContent = 'Token invalide.';
    return;
  }
  boot(await r.json());
}

function boot(sites) {
  $('loginView').hidden = true;
  $('adminApp').hidden = false;
  sites.forEach(s => {
    const o = document.createElement('option');
    o.value = s.domain; o.textContent = s.domain;
    $('domainSelect').appendChild(o);
  });
  loadSites(sites);
  loadStats();
}

// ── Navigation ────────────────────────────────────────────────────────────────
function switchView(name) {
  $('viewDashboard').hidden = name !== 'dashboard';
  $('viewSites').hidden = name !== 'sites';
  document.querySelectorAll('.nav-btn[data-view]').forEach(b =>
    b.classList.toggle('active', b.dataset.view === name));
}

// ── Dashboard ─────────────────────────────────────────────────────────────────
async function loadStats() {
  const domain = $('domainSelect').value;
  const days = $('daysSelect').value;
  const r = await api(`/api/stats?domain=${encodeURIComponent(domain)}&days=${days}`);
  if (r && r.ok) renderStats(await r.json());
}

function mkCard(lbl, val) {
  const el = document.createElement('div');
  el.className = 'stat-card';
  el.innerHTML = '<div class="stat-card-label"></div><div class="stat-card-value"></div>';
  el.children[0].textContent = lbl;
  el.children[1].textContent = val;
  return el;
}

function renderStats(d) {
  const avg = d.questions_per_day.length
    ? (d.total_questions / d.questions_per_day.length).toFixed(1) : '—';
  $('statCards').replaceChildren(
    mkCard('Questions / jour', avg),
    mkCard('Réponse moy.', d.avg_ms ? d.avg_ms + ' ms' : '—'),
    mkCard('Réponse p95', d.p95_ms ? d.p95_ms + ' ms' : '—'),
    mkCard('Taux d\'erreur', d.total_questions ? (d.error_rate * 100).toFixed(1) + '%' : '—'),
    mkCard('Satisfaction', d.satisfaction != null ? Math.round(d.satisfaction * 100) + '%' : '—'),
  );

  // Graphique en barres CSS
  const bc = $('barChart');
  bc.replaceChildren();
  const max = Math.max(...d.questions_per_day.map(x => x.count), 1);
  d.questions_per_day.forEach(({ date, count }) => {
    const bar = document.createElement('div');
    bar.className = 'bar';
    bar.style.height = (count / max * 100) + '%';
    const lbl = document.createElement('span');
    lbl.className = 'bar-label'; lbl.textContent = date.slice(5);
    bar.appendChild(lbl); bc.appendChild(bar);
  });

  // Satisfaction 👍/👎
  const sr = $('satisfactionRow');
  sr.replaceChildren();
  if (d.satisfaction != null) {
    const pct = Math.round(d.satisfaction * 100);
    const row = document.createElement('div'); row.className = 'vote-row';
    const track = document.createElement('div'); track.className = 'vote-track';
    const fill = document.createElement('div'); fill.className = 'vote-fill'; fill.style.width = pct + '%';
    track.appendChild(fill);
    const txt = document.createElement('span');
    txt.textContent = `👍 ${pct}%  👎 ${100 - pct}%`;
    row.append(track, txt); sr.appendChild(row);
  }

  // Clics par action
  const ct = $('clicksTable');
  ct.replaceChildren();
  if (d.clicks_by_action.length) {
    const tbl = document.createElement('table');
    const hdr = tbl.insertRow();
    ['Action', 'Clics'].forEach(h => { const th = document.createElement('th'); th.textContent = h; hdr.appendChild(th); });
    d.clicks_by_action.forEach(({ action, count }) => {
      const tr = tbl.insertRow();
      tr.insertCell().textContent = action;
      tr.insertCell().textContent = count;
    });
    ct.appendChild(tbl);
  }
  $('noDataMsg').textContent = d.total_questions ? '' : 'Aucune question n\'est enregistrée pour cette période.';
}

// ── Sites ─────────────────────────────────────────────────────────────────────
function loadSites(sites) {
  const tbody = $('sitesBody');
  tbody.replaceChildren();
  sites.forEach(site => {
    const tr = document.createElement('tr');
    [site.domain, site.site_title || '—', site.pages || 0, (site.updated_at || '').slice(0, 10)].forEach(v => {
      tr.insertCell().textContent = v;
    });
    // Bouton Réanalyser
    const btn = document.createElement('button');
    btn.className = 'btn-action'; btn.textContent = 'Réanalyser';
    btn.onclick = () => reanalyse(site.domain, btn);
    tr.insertCell().appendChild(btn);
    // Code widget à copier
    const origin = location.origin;
    const snippet = `<script src="${origin}/skapa-widget.js" data-api-url="${origin}" data-site-url="https://${site.domain}" async><\/script>`;
    const code = document.createElement('code'); code.className = 'widget-code'; code.textContent = snippet;
    const copyBtn = document.createElement('button'); copyBtn.className = 'btn-action'; copyBtn.textContent = 'Copier';
    copyBtn.onclick = () => { navigator.clipboard.writeText(snippet); copyBtn.textContent = '✓'; setTimeout(() => { copyBtn.textContent = 'Copier'; }, 1500); };
    const widTd = tr.insertCell(); widTd.append(code, copyBtn);
    tbody.appendChild(tr);
  });
}

async function reanalyse(domain, btn) {
  btn.disabled = true; btn.textContent = '…';
  const r = await api('/api/scrape/run', { method: 'POST', body: JSON.stringify({ url: 'https://' + domain }) });
  if (!r || !r.ok) { btn.textContent = 'Réanalyser'; btn.disabled = false; return; }
  const { job_id } = await r.json();
  for (let i = 0; i < 120; i++) {
    await new Promise(res => setTimeout(res, 2000));
    const s = await api(`/api/scrape/status/${job_id}`);
    if (!s) break;
    const job = await s.json();
    if (job.status === 'success') { btn.textContent = 'Réanalyser'; btn.disabled = false; refreshSites(); return; }
    if (job.status === 'error') { btn.textContent = 'Erreur'; btn.disabled = false; return; }
    btn.textContent = `${job.pages_done || 0} pages…`;
  }
  btn.textContent = 'Réanalyser'; btn.disabled = false;
}

async function refreshSites() {
  const r = await api('/api/sites');
  if (r && r.ok) loadSites(await r.json());
}

// ── Ajout d'un site ───────────────────────────────────────────────────────────
$('addSiteBtn').onclick = () => { $('addSiteForm').hidden = !$('addSiteForm').hidden; };
$('submitAddSite').onclick = async () => {
  const url = $('newSiteUrl').value.trim();
  const msg = $('addSiteMsg');
  if (!url) return;
  msg.textContent = 'Analyse en cours…';
  const r = await api('/api/scrape/run', { method: 'POST', body: JSON.stringify({ url }) });
  if (!r || !r.ok) { msg.textContent = 'Erreur.'; return; }
  msg.textContent = 'Lancé ✓ — analyse en cours';
  setTimeout(refreshSites, 10000);
};

// ── Initialisation ────────────────────────────────────────────────────────────
$('loginBtn').onclick = login;
$('tokenInput').addEventListener('keydown', e => e.key === 'Enter' && login());
$('logoutBtn').onclick = logout;
document.querySelectorAll('.nav-btn[data-view]').forEach(b => { b.onclick = () => switchView(b.dataset.view); });
$('domainSelect').onchange = loadStats;
$('daysSelect').onchange = loadStats;
if (getToken()) api('/api/sites').then(r => r && r.ok && r.json().then(boot));
