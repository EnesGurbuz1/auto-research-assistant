"""
LLM Interface - Google Gemini API ile iletişim katmanı.
Tüm ajanlar bu arayüz üzerinden LLM'e erişir.
"""

import os
import json
from pathlib import Path
from typing import Optional
from loguru import logger

try:
    import google.generativeai as genai
except ImportError:
    genai = None

from tenacity import retry, stop_after_attempt, wait_exponential


class LLMInterface:
    """Google Gemini API wrapper - tüm ajanlar için ortak LLM erişim katmanı."""

    def __init__(self, config: dict):
        self.config = config.get("llm", {})
        requested_model = self.config.get("model", "gemini-3.1-pro")
        
        # Öncelikli modeller ve fallback sırası
        self.model_candidates = [
            requested_model,
            "gemini-2.5-pro",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
        ]
        # Tekrar edenleri temizle ve sırayı koru
        seen = set()
        self.model_candidates = [x for x in self.model_candidates if not (x in seen or seen.add(x))]
        
        self.model_name = self.model_candidates[0]
        self.temperature = self.config.get("temperature", 0.3)
        self.max_tokens = self.config.get("max_tokens", 8192)
        
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            logger.warning("GEMINI_API_KEY ayarlanmamış! LLM çağrıları başarısız olacak.")
        
        if genai:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel(self.model_name)
            logger.info(f"LLM modeli aktif: {self.model_name}")
        else:
            logger.error("google-generativeai kütüphanesi yüklü değil!")
            self.model = None

    def _switch_to_next_model(self) -> bool:
        """Mevcut model geçersizse sıradaki modele geç."""
        if self.model_name not in self.model_candidates:
            return False

        current_idx = self.model_candidates.index(self.model_name)
        if current_idx >= len(self.model_candidates) - 1:
            return False

        next_model = self.model_candidates[current_idx + 1]
        self.model_name = next_model
        self.model = genai.GenerativeModel(self.model_name) if genai else None
        logger.warning(f"LLM modeli fallback ile değiştirildi: {self.model_name}")
        return True

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True
    )
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> str:
        """LLM'den yanıt üret."""
        if not self.model:
            raise RuntimeError("LLM modeli başlatılamamış.")

        temp = temperature or self.temperature
        tokens = max_tokens or self.max_tokens

        generation_config = genai.types.GenerationConfig(
            temperature=temp,
            max_output_tokens=tokens,
        )

        if system_prompt:
            full_prompt = f"{system_prompt}\n\n---\n\n{prompt}"
        else:
            full_prompt = prompt

        logger.debug(f"LLM çağrısı: model={self.model_name}, temp={temp}, prompt_len={len(full_prompt)}")

        try:
            response = self.model.generate_content(
                full_prompt,
                generation_config=generation_config,
            )
        except Exception as e:
            err = str(e).lower()
            # Hata kodları: 429 (rate limit), 400 (context limit), 404/503 (model/service)
            fallback_errors = [
                "not found", "not supported", "model", 
                "limit", "exhausted", "quota", "resource"
            ]
            
            should_fallback = any(msg in err for msg in fallback_errors)
            
            if should_fallback and self._switch_to_next_model() and self.model:
                logger.info(f"Hata sonrası fallback modele geçiliyor: {self.model_name}")
                response = self.model.generate_content(
                    full_prompt,
                    generation_config=generation_config,
                )
            else:
                raise
        
        result = response.text
        logger.debug(f"LLM yanıtı: {len(result)} karakter")
        return result

    def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> dict:
        """LLM'den JSON formatında yanıt üret ve parse et."""
        json_instruction = (
            "\n\nYANITINI MUTLAKA GEÇERLİ JSON FORMATINDA VER. "
            "Başka hiçbir metin ekleme, sadece JSON objesi döndür. "
            "Kısa ve öz tut, gereksiz uzun açıklamalar yapma."
        )
        
        # JSON yanıtları için daha yüksek token limiti
        raw = self.generate(prompt + json_instruction, system_prompt, max_tokens=16384)
        
        # JSON bloğunu temizle
        cleaned = raw.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()
        
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            # Truncated JSON kurtarma: açık parantezleri kapatmayı dene
            logger.warning(f"JSON parse hatası, kurtarma deneniyor: {e}")
            fixed = self._try_fix_truncated_json(cleaned)
            if fixed is not None:
                logger.info("Truncated JSON başarıyla kurtarıldı")
                return fixed
            logger.error(f"JSON kurtarılamadı.\nHam yanıt: {raw[:500]}")
            return {}

    def _try_fix_truncated_json(self, text: str):
        """Kesilmiş JSON'ı kurtarmayı dene."""
        # Son tamamlanmış JSON öğesine kadar kes
        for end_char in ['}', ']']:
            idx = text.rfind(end_char)
            if idx > 0:
                candidate = text[:idx+1]
                # Eksik kapanış parantezlerini ekle
                open_braces = candidate.count('{') - candidate.count('}')
                open_brackets = candidate.count('[') - candidate.count(']')
                candidate += ']' * max(0, open_brackets) + '}' * max(0, open_braces)
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    continue
        return None

    def load_system_prompt(self, prompt_name: str, project_root: Path) -> str:
        """prompts/ dizininden sistem prompt'u yükle."""
        prompt_file = project_root / "prompts" / f"{prompt_name}.md"
        if prompt_file.exists():
            return prompt_file.read_text(encoding="utf-8")
        logger.warning(f"Prompt dosyası bulunamadı: {prompt_file}")
        return ""
