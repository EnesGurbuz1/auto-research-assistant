"""
Ortak LLM yardımcısı — google-genai SDK (Gemini 2.0 Flash).
"""

import os
import json
from typing import Optional
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from google import genai
from google.genai import types

MODEL = "gemini-2.5-flash"

_client: Optional[genai.Client] = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY ortam değişkeni ayarlanmamış!")
        _client = genai.Client(api_key=api_key)
    return _client


@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=20), reraise=True)
def generate(prompt: str, system: str = "", temperature: float = 0.3) -> str:
    """LLM'den metin yanıtı üret."""
    client = _get_client()

    contents = [types.Content(role="user", parts=[types.Part(text=prompt)])]
    config = types.GenerateContentConfig(
        temperature=temperature,
        max_output_tokens=8192,
        system_instruction=system if system else None,
    )

    response = client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=config,
    )
    return response.text or ""


def generate_json(prompt: str, system: str = "") -> dict:
    """LLM'den JSON formatında yanıt üret ve parse et."""
    json_hint = (
        "\n\nYANITINI SADECE GEÇERLİ JSON OLARAK VER. "
        "Markdown kod bloğu, açıklama veya başka metin ekleme. "
        "Yalnızca ham JSON objesi."
    )
    raw = generate(prompt + json_hint, system=system, temperature=0.1)
    cleaned = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
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
