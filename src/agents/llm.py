"""
Ortak LLM yardımcısı — google-genai SDK (Gemini 2.5 Flash).
"""

import os
import json
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

import google.generativeai as genai

MODEL = "gemini-2.5-flash"

_configured = False


def _ensure_configured():
    global _configured
    if _configured:
        return

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY ortam değişkeni ayarlanmamış!")

    genai.configure(api_key=api_key)
    _configured = True


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=20), reraise=True)
def generate(prompt: str, system: str = "", temperature: float = 0.3) -> str:
    """LLM'den metin yanıtı üret."""
    _ensure_configured()

    generation_config = genai.types.GenerationConfig(
        temperature=temperature,
        max_output_tokens=8192,
    )

    full_prompt = f"{system}\n\n---\n\n{prompt}" if system else prompt
    model = genai.GenerativeModel(MODEL)
    response = model.generate_content(full_prompt, generation_config=generation_config)
    return response.text or ""


def generate_json(prompt: str, system: str = "") -> dict:
    """LLM'den JSON formatında yanıt üret ve parse et."""
    json_hint = (
        "\n\nYANITINI SADECE GEÇERLİ JSON OLARAK VER. "
        "Markdown kod bloğu, açıklama veya başka metin ekleme. "
        "Yalnızca ham JSON objesi."
    )
    raw = generate(prompt + json_hint, system=system, temperature=0.1)
    import re
    cleaned = raw.strip()
    cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned)
    cleaned = re.sub(r'\s*```$', '', cleaned)
    cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Son geçerli } veya ]'ye kadar kes ve kapat
        for ch in ("}", "]"):
            idx = cleaned.rfind(ch)
            if idx > 0:
                candidate = cleaned[: idx + 1]
                opens = candidate.count("{") - candidate.count("}")
                opens_sq = candidate.count("[") - candidate.count("]")
                candidate += "]" * max(0, opens_sq) + "}" * max(0, opens)
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    continue
        logger.error(f"JSON parse başarısız. Ham yanıt: {raw[:300]}")
        return {}
