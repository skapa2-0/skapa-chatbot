"""
Génération de la réponse : Ollama (local, défaut), Anthropic Claude, Groq ou Gemini.

LLM_PROVIDER=ollama     -> OLLAMA_BASE_URL / OLLAMA_MODEL
LLM_PROVIDER=anthropic  -> ANTHROPIC_API_KEY / ANTHROPIC_MODEL
LLM_PROVIDER=groq       -> GROQ_API_KEY / GROQ_MODEL
LLM_PROVIDER=gemini     -> GEMINI_API_KEY / GEMINI_MODEL
"""

import os
import time

import requests

from app import config


class LLMError(RuntimeError):
    pass


def _ollama_chat(system_prompt, messages):
    msgs = [{"role": "system", "content": system_prompt}, *messages]

    # Essai cloud (gpt-oss:20b, think=low, 15 s). Fallback silencieux sur local.
    api_key = os.getenv("OLLAMA_API_KEY")
    if api_key:
        try:
            resp = requests.post(
                "https://ollama.com/api/chat",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "gpt-oss:20b",
                    "stream": False,
                    "think": "low",
                    "messages": msgs,
                    "options": {"temperature": 0.2, "num_ctx": config.OLLAMA_NUM_CTX},
                },
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json()["message"]["content"].strip()
        except (requests.RequestException, KeyError, ValueError):
            pass  # bascule sur le local

    payload = {
        "model": "llama3.2:1b",
        "stream": False,
        "messages": msgs,
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
            "Modèle Ollama 'llama3.2:1b' introuvable. "
            "Lancez : ollama pull llama3.2:1b"
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


def _groq_chat(system_prompt, messages):
    if not config.GROQ_API_KEY:
        raise LLMError("GROQ_API_KEY manquante (LLM_PROVIDER=groq).")
    msgs = [{"role": "system", "content": system_prompt}, *messages]
    last_exc = None
    for attempt in range(3):
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {config.GROQ_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": config.GROQ_MODEL,
                    "messages": msgs,
                    "temperature": 0.2,
                    "max_tokens": 1024,
                },
                timeout=config.LLM_TIMEOUT,
            )
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("retry-after", 15))
                wait = min(retry_after, 30)
                time.sleep(wait)
                last_exc = requests.exceptions.HTTPError(resp.status_code, response=resp)
                continue
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
            if not content:
                raise LLMError("Le modèle Groq a renvoyé une réponse vide.")
            return content
        except requests.exceptions.HTTPError as exc:
            detail = ""
            try:
                detail = resp.json().get("error", {}).get("message", "")
            except ValueError:
                pass
            raise LLMError(f"Erreur API Groq : {exc} {detail}".strip())
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError(f"Réponse Groq inattendue : {exc}")
        except requests.RequestException as exc:
            raise LLMError(f"Impossible de joindre l'API Groq : {exc}")
    raise LLMError("Groq : limite de débit atteinte, veuillez réessayer dans quelques secondes.")


def _gemini_chat(system_prompt, messages):
    if not config.GEMINI_API_KEY:
        raise LLMError("GEMINI_API_KEY manquante (LLM_PROVIDER=gemini).")
    contents = []
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": m["content"]}]})
    try:
        resp = requests.post(
            # Clé dans un en-tête, PAS dans l'URL : sinon elle apparaît dans le
            # message d'erreur, renvoyé au navigateur par /chat.
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{config.GEMINI_MODEL}:generateContent",
            headers={"x-goog-api-key": config.GEMINI_API_KEY},
            json={
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "contents": contents,
                "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1024},
            },
            timeout=config.LLM_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except requests.exceptions.HTTPError as exc:
        detail = ""
        try:
            detail = resp.json().get("error", {}).get("message", "")
        except ValueError:
            pass
        raise LLMError(f"Erreur API Gemini : {exc} {detail}".strip())
    except (KeyError, IndexError, ValueError) as exc:
        raise LLMError(f"Réponse Gemini inattendue : {exc}")
    except requests.RequestException as exc:
        raise LLMError(f"Impossible de joindre l'API Gemini : {exc}")


def chat(system_prompt, messages):
    """messages : [{"role": "user"|"assistant", "content": str}, ...] (finit par user)."""
    if config.LLM_PROVIDER == "anthropic":
        return _anthropic_chat(system_prompt, messages)
    if config.LLM_PROVIDER == "groq":
        return _groq_chat(system_prompt, messages)
    if config.LLM_PROVIDER == "gemini":
        return _gemini_chat(system_prompt, messages)
    return _ollama_chat(system_prompt, messages)


def describe():
    if config.LLM_PROVIDER == "anthropic":
        return f"anthropic:{config.ANTHROPIC_MODEL}"
    if config.LLM_PROVIDER == "groq":
        return f"groq:{config.GROQ_MODEL}"
    if config.LLM_PROVIDER == "gemini":
        return f"gemini:{config.GEMINI_MODEL}"
    return f"ollama:{config.OLLAMA_MODEL}"