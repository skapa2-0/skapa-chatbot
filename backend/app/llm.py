"""
Génération de la réponse : Ollama (local, défaut) ou Anthropic Claude.

LLM_PROVIDER=ollama     -> OLLAMA_BASE_URL / OLLAMA_MODEL
LLM_PROVIDER=anthropic  -> ANTHROPIC_API_KEY / ANTHROPIC_MODEL
"""

import requests

from app import config


class LLMError(RuntimeError):
    pass


def _ollama_chat(system_prompt, messages):
    payload = {
        "model": config.OLLAMA_MODEL,
        "stream": False,
        "messages": [{"role": "system", "content": system_prompt}, *messages],
        # num_ctx : Ollama tronque à 2048 tokens par défaut -> le contexte RAG
        # était coupé et le modèle « oubliait » les infos du site.
        "options": {"temperature": 0.2, "num_ctx": config.OLLAMA_NUM_CTX},
    }
    try:
        resp = requests.post(f"{config.OLLAMA_BASE_URL}/api/chat", json=payload,
                             timeout=config.LLM_TIMEOUT)
    except requests.exceptions.ConnectionError:
        raise LLMError(
            f"Impossible de joindre Ollama sur {config.OLLAMA_BASE_URL}. "
            "Vérifiez qu'Ollama est démarré (`ollama serve`)."
        )
    except requests.exceptions.Timeout:
        raise LLMError("Ollama met trop de temps à répondre (modèle trop lourd pour la machine ?).")
    if resp.status_code == 404:
        raise LLMError(
            f"Modèle Ollama '{config.OLLAMA_MODEL}' introuvable. "
            f"Lancez : ollama pull {config.OLLAMA_MODEL}"
        )
    try:
        resp.raise_for_status()
        return resp.json()["message"]["content"].strip()
    except requests.exceptions.HTTPError as exc:
        raise LLMError(f"Ollama a renvoyé une erreur HTTP : {exc}")
    except (KeyError, ValueError) as exc:
        raise LLMError(f"Réponse Ollama inattendue : {exc}")


def _anthropic_chat(system_prompt, messages):
    if not config.ANTHROPIC_API_KEY:
        raise LLMError("ANTHROPIC_API_KEY manquante (LLM_PROVIDER=anthropic).")
    try:
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": config.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": config.ANTHROPIC_MODEL,
                "max_tokens": 1024,
                "temperature": 0.2,
                "system": system_prompt,
                "messages": messages,
            },
            timeout=config.LLM_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return "".join(b.get("text", "") for b in data.get("content", [])).strip()
    except requests.exceptions.HTTPError as exc:
        detail = ""
        try:
            detail = resp.json().get("error", {}).get("message", "")
        except ValueError:
            pass
        raise LLMError(f"Erreur API Anthropic : {exc} {detail}".strip())
    except requests.RequestException as exc:
        raise LLMError(f"Impossible de joindre l'API Anthropic : {exc}")


def chat(system_prompt, messages):
    """messages : [{"role": "user"|"assistant", "content": str}, ...] (finit par user)."""
    if config.LLM_PROVIDER == "anthropic":
        return _anthropic_chat(system_prompt, messages)
    return _ollama_chat(system_prompt, messages)


def describe():
    if config.LLM_PROVIDER == "anthropic":
        return f"anthropic:{config.ANTHROPIC_MODEL}"
    return f"ollama:{config.OLLAMA_MODEL}"
