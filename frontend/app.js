const chatToggle = document.getElementById('chatToggle');
const chatPanel = document.getElementById('chatPanel');
const closeBtn = document.getElementById('closeBtn');
const messages = document.getElementById('messages');
const chipsWrap = document.getElementById('chips');
const form = document.getElementById('chatForm');
const input = document.getElementById('messageInput');

const DATA = [
  {
    id: 1,
    title: 'IA & Développement',
    meta: '6 semaines • En ligne',
    description: 'Programme immersif pour apprendre à créer des solutions IA et des applications utiles.',
    price: 'À partir de 990 €',
    duration: '6 semaines',
    format: '100% en ligne',
    availability: '3 places restantes',
    url: 'https://example.com/formation-ia-developpement'
  },
  {
    id: 2,
    title: 'Product Builder Vibe Coder',
    meta: '4 semaines • Mentorat',
    description: 'Construis rapidement des MVP, prototypes et produits concrets avec un accompagnement de mentor.',
    price: 'À partir de 1 290 €',
    duration: '4 semaines',
    format: 'Mentorat individuel',
    availability: '2 sessions disponibles',
    url: 'https://example.com/product-builder-vibe-coder'
  },
  {
    id: 3,
    title: 'RAG & Bases de connaissances avec MCP',
    meta: '5 semaines • Live sessions',
    description: 'Apprends à concevoir des assistants contextuels et des systèmes de recherche avancés.',
    price: 'À partir de 1 490 €',
    duration: '5 semaines',
    format: 'Sessions live + exercices',
    availability: 'Nouvelle session en octobre',
    url: 'https://example.com/rag-mcp'
  },
  {
    id: 4,
    title: 'Data & Automations',
    meta: '3 semaines • Atelier pratique',
    description: 'Automatise tes tâches et exploite les données pour gagner du temps et livrer plus vite.',
    price: 'À partir de 850 €',
    duration: '3 semaines',
    format: 'Atelier + exercices',
    availability: 'Inscription ouverte',
    url: 'https://example.com/data-automations'
  }
];

const CHIPS = ['Quelles sont les formations ?', 'Prix', 'Disponibilité', 'Contact'];
let activeDetail = null;

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function renderMessage(text, role = 'bot', isSystem = false) {
  const wrapper = document.createElement('div');
  wrapper.className = `message ${role}`;
  if (isSystem) wrapper.classList.add('system');

  const bubble = document.createElement('div');
  bubble.className = 'bubble';

  if (role === 'bot' && !isSystem) {
    const formatted = text
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/(https?:\/\/[^\s<]+)/g, '<a href="$1" target="_blank" rel="noopener noreferrer">$1</a>');
    bubble.innerHTML = formatted;
  } else {
    bubble.textContent = text;
  }

  wrapper.appendChild(bubble);
  messages.appendChild(wrapper);
  messages.scrollTop = messages.scrollHeight;
  return wrapper;
}

function renderTyping() {
  const wrapper = document.createElement('div');
  wrapper.className = 'message bot';
  const typing = document.createElement('div');
  typing.className = 'typing';
  typing.innerHTML = '<span></span><span></span><span></span>';
  wrapper.appendChild(typing);
  messages.appendChild(wrapper);
  messages.scrollTop = messages.scrollHeight;
  return wrapper;
}

function renderChips() {
  chipsWrap.innerHTML = '';
  CHIPS.forEach((label) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'chip';
    btn.textContent = label;
    btn.addEventListener('click', () => {
      input.value = label;
      form.requestSubmit();
    });
    chipsWrap.appendChild(btn);
  });
}

function renderListCards() {
  const listWrapper = document.createElement('div');
  listWrapper.className = 'list-block';

  DATA.forEach((item) => {
    const card = document.createElement('div');
    card.className = 'list-card';
    card.innerHTML = `
      <div class="list-card__content">
        <div class="list-card__title">${escapeHtml(item.title)}</div>
        <div class="list-card__meta">${escapeHtml(item.meta)}</div>
      </div>
      <div class="list-card__chevron">›</div>
    `;
    card.addEventListener('click', () => showDetail(item));
    listWrapper.appendChild(card);
  });

  return listWrapper;
}

function renderDetail(item) {
  const panel = document.createElement('div');
  panel.className = 'detail-panel';

  panel.innerHTML = `
    <div class="detail-back" data-back="true">
      <span>←</span>
      <span>Retour à la liste</span>
    </div>
    <h3 class="detail-content__title">${escapeHtml(item.title)}</h3>
    <div class="detail-grid">
      <div class="detail-item">
        <div class="detail-item__label">Prix</div>
        <div class="detail-item__value">${escapeHtml(item.price)}</div>
      </div>
      <div class="detail-item">
        <div class="detail-item__label">Durée</div>
        <div class="detail-item__value">${escapeHtml(item.duration)}</div>
      </div>
      <div class="detail-item">
        <div class="detail-item__label">Format</div>
        <div class="detail-item__value">${escapeHtml(item.format)}</div>
      </div>
      <div class="detail-item">
        <div class="detail-item__label">Disponibilité</div>
        <div class="detail-item__value">${escapeHtml(item.availability)}</div>
      </div>
      <div class="detail-item">
        <div class="detail-item__label">Description</div>
        <div class="detail-item__value">${escapeHtml(item.description)}</div>
      </div>
    </div>
    <a class="detail-cta" href="${item.url}" target="_blank" rel="noopener noreferrer">Découvrir la formation</a>
  `;

  panel.querySelector('[data-back="true"]').addEventListener('click', () => {
    activeDetail = null;
    refreshConversation();
  });

  return panel;
}

function showDetail(item) {
  activeDetail = item;
  refreshConversation();
}

function buildResponseForQuestion(question) {
  const q = question.toLowerCase();
  const keywords = {
    price: /(prix|tarif|coût|cout|budget)/i,
    availability: /(disponib|session|date|inscription|planning)/i,
    contact: /(contact|renseign|appel|rdv|demande)/i,
    training: /(formation|programme|cours|apprendre)/i
  };

  let text = 'Voici les formations disponibles :';
  if (keywords.price.test(q)) text = 'Voici les formations avec leurs tarifs et modalités de paiement :';
  if (keywords.availability.test(q)) text = 'Voici les formations encore disponibles et leurs prochaines sessions :';
  if (keywords.contact.test(q)) text = 'Voici les programmes les plus demandés, et vous pouvez contacter l’équipe pour avoir plus d’informations :';
  if (keywords.training.test(q)) text = 'Voici les formations les plus demandées :';

  return { text, items: DATA };
}

function refreshConversation() {
  messages.innerHTML = '';

  const intro = document.createElement('div');
  intro.className = 'message bot';
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.innerHTML = 'Bonjour ! Je peux vous aider à découvrir nos formations. <strong>Choisissez une option ci-dessous</strong> ou posez votre question.';
  intro.appendChild(bubble);
  messages.appendChild(intro);

  const chipContainer = document.createElement('div');
  chipContainer.className = 'chip-row';
  const chip = document.createElement('button');
  chip.type = 'button';
  chip.className = 'chip';
  chip.textContent = 'Quelle sont les formations disponibles';
  chip.addEventListener('click', () => {
    input.value = chip.textContent;
    form.requestSubmit();
  });
  chipContainer.appendChild(chip);
  messages.appendChild(chipContainer);

  if (activeDetail) {
    messages.appendChild(renderDetail(activeDetail));
    return;
  }

  const response = document.createElement('div');
  response.className = 'message bot';
  const responseBubble = document.createElement('div');
  responseBubble.className = 'bubble';
  responseBubble.textContent = 'Voici les formations disponibles :';
  response.appendChild(responseBubble);
  messages.appendChild(response);

  const list = renderListCards();
  messages.appendChild(list);
}

function sendQuestion(question) {
  renderMessage(question, 'user');
  const typing = renderTyping();

  setTimeout(() => {
    typing.remove();
    const reply = buildResponseForQuestion(question);
    if (activeDetail) activeDetail = null;

    const replyBlock = document.createElement('div');
    replyBlock.className = 'message bot';
    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    bubble.textContent = reply.text;
    replyBlock.appendChild(bubble);
    messages.appendChild(replyBlock);

    const list = renderListCards();
    messages.appendChild(list);
    messages.scrollTop = messages.scrollHeight;
  }, 700);
}

if (chatToggle && chatPanel) {
  chatToggle.addEventListener('click', () => {
    chatPanel.classList.toggle('open');
  });
}

if (closeBtn) {
  closeBtn.addEventListener('click', () => {
    chatPanel.classList.remove('open');
  });
}

if (form && input && chatPanel && messages) {
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const value = input.value.trim();
    if (!value) return;
    sendQuestion(value);
    input.value = '';
  });
}

renderChips();
refreshConversation();
