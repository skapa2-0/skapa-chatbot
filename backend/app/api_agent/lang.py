"""Détection simple de la langue du visiteur (sans dépendance externe).

Le modèle d'IA a tendance à répondre dans la langue du contexte plutôt que
dans celle du visiteur. On détecte donc la langue côté code et on l'impose
explicitement dans le prompt.
"""

import re

_WORDS = {
    "en": "the you your what how do does is are can i we our training trainings course courses "
          "offer price prices where when which with for and to of in have about there".split(),
    "fr": "le les des vous votre vos quel quelle quels quelles comment est sont je nous du pour "
          "avec et où quand prix formation formations proposez avez cours".split(),
    "es": "el los las usted ustedes qué cómo cuál cuáles dónde cuándo es son hay para con y "
          "precio precios formación formaciones ofrecen tienen curso cursos".split(),
    "de": "der die das sie ihr was wie wo wann ist sind ich wir ein eine für mit und zu von im "
          "preis kurse bieten".split(),
    "it": "il lo gli voi cosa come dove quando sono per con di prezzo corsi offrite".split(),
    "pt": "você vocês como onde quando são um uma para com preço cursos oferecem".split(),
}
_SETS = {lang: set(words) for lang, words in _WORDS.items()}

LANGUAGE_NAMES = {
    "en": "anglais (English)",
    "fr": "français",
    "es": "espagnol (español)",
    "de": "allemand (Deutsch)",
    "it": "italien (italiano)",
    "pt": "portugais (português)",
}


def detect_language(text):
    """Code de langue ("en", "fr"...) ou None si la langue n'est pas claire."""
    if not text:
        return None
    low = text.lower()
    tokens = re.findall(r"[a-zà-ÿ']+", low)
    scores = {lang: sum(1 for token in tokens if token in words)
              for lang, words in _SETS.items()}
    if "¿" in text or "¡" in text or "ñ" in low:
        scores["es"] += 2
    if re.search(r"[àâçèêëîïôûùœ]", low):
        scores["fr"] += 1
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best, best_score = ranked[0]
    if best_score == 0 or best_score == ranked[1][1]:
        return None
    return best


def visitor_language(message, history=()):
    """Langue du message ; pour un message court, reprend le dernier message clair."""
    lang = detect_language(message)
    if lang:
        return lang
    for item in reversed(list(history)):
        if item.get("role") == "user":
            lang = detect_language(item.get("content", ""))
            if lang:
                return lang
    return None
