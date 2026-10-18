"""Benchmark Ollama et autres providers LLM.

Mesure la latence et le débit (tokens/sec) pour plusieurs modèles.
"""

import os
import statistics
import time

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv("/opt/chatbot/backend/.env", override=True)


PROMPT = (
    "Explique en 5 phrases pourquoi les benchmarks sont utiles pour comparer "
    "des modèles de langage et comment mesurer la latence et le débit."
)
RUNS = 5
TIMEOUT = 120
MAX_TOKENS = 150  # borne commune pour que les latences soient comparables


# ── 1. Liste des modèles disponibles ───────────────────────────────────────
def list_ollama_cloud_models():
    api_key = os.getenv("OLLAMA_API_KEY")
    r = requests.get(
        "https://ollama.com/api/tags",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )
    print("Ollama cloud /api/tags:", r.status_code)
    if r.status_code != 200:
        print(r.text[:300])
        return None
    df = pd.DataFrame(r.json().get("models", []))
    print(df[["name", "size"]] if "name" in df.columns else df)
    return df


def list_groq_models():
    key = os.getenv("GROQ_API_KEY")
    r = requests.get(
        "https://api.groq.com/openai/v1/models",
        headers={"Authorization": f"Bearer {key}"},
        timeout=30,
    )
    print("Groq /v1/models:", r.status_code)
    if r.status_code != 200:
        print(r.text[:300])
        return None
    return [m["id"] for m in r.json().get("data", []) if m.get("active")]


def list_gemini_models():
    key = os.getenv("GEMINI_API_KEY")
    r = requests.get(
        "https://generativelanguage.googleapis.com/v1beta/models",
        headers={"x-goog-api-key": key},
        timeout=30,
    )
    print("Gemini /v1beta/models:", r.status_code)
    if r.status_code != 200:
        print(r.text[:300])
        return None
    return [
        m["name"].removeprefix("models/")
        for m in r.json().get("models", [])
        if "generateContent" in m.get("supportedGenerationMethods", [])
    ]


# ── 2. Callers par provider ────────────────────────────────────────────────
# Chaque caller retourne un dict:
#   - "text": contenu généré
#   - "tokens": nombre de tokens générés (eval_count / completion_tokens)
#   - "gen_duration_s": temps de génération pur (hors load/prompt), si dispo
#   - "load_s", "prompt_eval_s": pour Ollama
#   - "thinking_chars": taille du reasoning (Ollama message.thinking)
# ou {"error": "..."} en cas d'échec.


def _http_error(r: requests.Response) -> dict:
    return {"error": f"HTTP {r.status_code}: {r.text[:300]}"}


def call_ollama_local(model, prompt, max_tokens):
    r = requests.post(
        "http://localhost:11434/api/chat",
        json={
            "model": model,
            "stream": False,
            "messages": [{"role": "user", "content": prompt}],
            "options": {"num_predict": max_tokens},
        },
        timeout=TIMEOUT,
    )
    if r.status_code != 200:
        return _http_error(r)
    data = r.json()
    msg = data.get("message", {}) or {}
    return {
        "text": msg.get("content", ""),
        "tokens": data.get("eval_count", 0),
        "gen_duration_s": data.get("eval_duration", 0) / 1e9,
        "load_s": data.get("load_duration", 0) / 1e9,
        "prompt_eval_s": data.get("prompt_eval_duration", 0) / 1e9,
        "thinking_chars": len(msg.get("thinking", "") or ""),
    }


def call_ollama_cloud(model, prompt, max_tokens):
    key = os.getenv("OLLAMA_API_KEY")
    r = requests.post(
        "https://ollama.com/api/chat",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": model,
            "stream": False,
            "messages": [{"role": "user", "content": prompt}],
            "options": {"num_predict": max_tokens},
        },
        timeout=TIMEOUT,
    )
    if r.status_code != 200:
        return _http_error(r)
    data = r.json()
    msg = data.get("message", {}) or {}
    return {
        "text": msg.get("content", ""),
        "tokens": data.get("eval_count", 0),
        "gen_duration_s": data.get("eval_duration", 0) / 1e9,
        "load_s": data.get("load_duration", 0) / 1e9,
        "prompt_eval_s": data.get("prompt_eval_duration", 0) / 1e9,
        "thinking_chars": len(msg.get("thinking", "") or ""),
    }


def call_groq(model, prompt, max_tokens):
    key = os.getenv("GROQ_API_KEY")
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
        },
        timeout=TIMEOUT,
    )
    if r.status_code != 200:
        return _http_error(r)
    data = r.json()
    return {
        "text": data["choices"][0]["message"]["content"],
        "tokens": data.get("usage", {}).get("completion_tokens", 0),
    }


def call_anthropic(model, prompt, max_tokens):
    key = os.getenv("ANTHROPIC_API_KEY")
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=TIMEOUT,
    )
    if r.status_code != 200:
        return _http_error(r)
    data = r.json()
    text = "".join(b.get("text", "") for b in data.get("content", []))
    return {
        "text": text,
        "tokens": data.get("usage", {}).get("output_tokens", 0),
    }


def call_gemini(model, prompt, max_tokens):
    key = os.getenv("GEMINI_API_KEY")
    r = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        headers={"x-goog-api-key": key, "content-type": "application/json"},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens},
        },
        timeout=TIMEOUT,
    )
    if r.status_code != 200:
        return _http_error(r)
    data = r.json()
    candidates = data.get("candidates") or [{}]
    parts = (candidates[0].get("content") or {}).get("parts") or [{}]
    text = parts[0].get("text", "") if parts else ""
    return {
        "text": text,
        "tokens": data.get("usageMetadata", {}).get("candidatesTokenCount", 0),
    }


CALLERS = {
    "ollama_local": call_ollama_local,
    "ollama_cloud": call_ollama_cloud,
    "groq":         call_groq,
    "anthropic":    call_anthropic,
    "gemini":       call_gemini,
}


# ── 3. Modèles à benchmarker ───────────────────────────────────────────────
# IDs mis à jour depuis /v1/models (Groq) et /v1beta/models (Gemini).
MODELS = [
    ("ollama_local", "llama3.2:1b",                "ollama-local llama3.2:1b"),
    ("ollama_cloud", "gpt-oss:20b",                "ollama-cloud gpt-oss:20b"),
    ("groq",         "openai/gpt-oss-20b",         "groq gpt-oss-20b"),
    ("groq",         "openai/gpt-oss-120b",        "groq gpt-oss-120b"),
    ("anthropic",    "claude-haiku-4-5-20251001",  "anthropic claude-haiku-4-5"),
    ("gemini",       "gemini-2.5-flash",           "gemini-2.5-flash"),
]


# ── 4. Boucle de benchmark ─────────────────────────────────────────────────
def benchmark(provider, model, prompt, max_tokens=MAX_TOKENS, runs=RUNS):
    caller = CALLERS[provider]
    latencies = []
    token_counts = []
    gen_durations = []
    load_times = []
    prompt_times = []
    thinking_sizes = []
    error = None

    for _ in range(runs):
        t0 = time.perf_counter()
        result = caller(model, prompt, max_tokens)
        elapsed = time.perf_counter() - t0
        if "error" in result:
            error = result["error"]
            break
        latencies.append(elapsed)
        token_counts.append(result.get("tokens", 0))
        if "gen_duration_s" in result:
            gen_durations.append(result["gen_duration_s"])
            load_times.append(result.get("load_s", 0.0))
            prompt_times.append(result.get("prompt_eval_s", 0.0))
            thinking_sizes.append(result.get("thinking_chars", 0))

    if error or not latencies:
        return {"provider": provider, "model": model, "error": error or "no runs"}

    avg_lat = statistics.mean(latencies)
    avg_tok = statistics.mean(token_counts)

    # Pour Ollama on utilise eval_count / eval_duration (débit de génération pur).
    # Pour les APIs OpenAI-compat on utilise completion_tokens / latence totale,
    # faute d'un timing serveur isolant la génération.
    if gen_durations and sum(gen_durations) > 0:
        gen_tps = sum(token_counts) / sum(gen_durations)
    else:
        gen_tps = avg_tok / avg_lat if avg_lat else 0.0

    row = {
        "provider":         provider,
        "model":            model,
        "avg_latency_s":    round(avg_lat, 3),
        "median_latency_s": round(statistics.median(latencies), 3),
        "p95_latency_s":    round(float(np.percentile(latencies, 95)), 3),
        "avg_tokens":       round(avg_tok, 1),
        "tokens_per_sec":   round(gen_tps, 2),
        "runs":             len(latencies),
    }
    if gen_durations:
        row["avg_gen_s"]        = round(statistics.mean(gen_durations), 3)
        row["avg_load_s"]       = round(statistics.mean(load_times), 3)
        row["avg_prompt_eval_s"] = round(statistics.mean(prompt_times), 3)
        row["avg_thinking_chars"] = int(round(statistics.mean(thinking_sizes)))
    return row


def benchmark_all_providers():
    results = []
    for provider, model, label in MODELS:
        print(f"→ {label} ...", end=" ", flush=True)
        r = benchmark(provider, model, PROMPT)
        results.append(r)
        if "error" in r:
            print(f"ERREUR : {r['error']}")
        else:
            print(f"{r['avg_latency_s']}s | {r['tokens_per_sec']} tok/s | {r['avg_tokens']} tok")

    df = pd.DataFrame(results)
    if "error" in df.columns:
        df_ok = df[df["error"].isna()]
    else:
        df_ok = df
    df_sorted = df_ok.sort_values("tokens_per_sec", ascending=False).reset_index(drop=True)
    print("\n", df_sorted.to_string(index=False))

    df_sorted.to_csv("benchmark_results.csv", index=False)
    print("Sauvegardé : benchmark_results.csv")
    return df_sorted


if __name__ == "__main__":
    print("=== Modèles disponibles ===")
    list_ollama_cloud_models()
    print("Groq:", list_groq_models())
    print("Gemini:", list_gemini_models())

    print("\n=== Benchmark multi-providers ===")
    benchmark_all_providers()
