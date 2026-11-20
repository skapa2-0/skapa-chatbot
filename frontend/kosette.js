/* kosette.js — petits comportements des ajouts visuels (n'utilise pas app.js) */
document.querySelectorAll('[data-scroll-to-analyse]').forEach((btn) => {
  btn.addEventListener('click', () => {
    const card = document.getElementById('connectCard');
    if (card) card.scrollIntoView({ behavior: 'smooth', block: 'center' });
    const input = document.getElementById('siteUrlInput');
    if (input) setTimeout(() => input.focus({ preventScroll: true }), 450);
  });
});
