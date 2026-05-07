"""
Fact Checker - Bulguların doğrulanması aracı.
LLM kullanarak synthesis bulgularını kaynaklarına karşı kontrol eder.

Doğruluk Seviyeleri:
- VERIFIED: İddia açıkça kaynaklarda geçiyor
- INFERENCE: İddia kaynaktan çıkartılabilir (dolaylı kanıt)
- HALLUCINATION: İddia kaynaklarda hiç yoktur
"""

import json
from typing import Dict, List, Any, Optional
from loguru import logger

from agents.llm_interface import LLMInterface


class FactChecker:
    """Raporlardaki iddaları kaynaklar karşında doğrulayan araç."""

    def __init__(self, config: dict):
        self.llm = LLMInterface(config)
        self.config = config

    def verify_synthesis(
        self,
        synthesis: Dict[str, Any],
        literature: List[Dict],
        patents: List[Dict],
        datasets: List[Dict],
    ) -> Dict[str, Any]:
        """
        Tüm synthesis bulgularını doğrula.
        
        Returns:
            verified_synthesis: Doğrulama detayları eklenmiş synthesis
        """
        verified_synthesis = synthesis.copy()
        verification_stats = {
            "verified": 0,
            "inference": 0,
            "hallucination": 0,
            "unverifiable": 0,
            "total_claims": 0,
        }

        # Tüm kaynakları indeks'le
        all_sources = literature + patents
        source_map = {i: src for i, src in enumerate(all_sources)}

        # Gap analysis doğrulaması
        logger.info("Gap analizi doğrulanıyor...")
        if "gap_analysis" in synthesis:
            for category in ["solved", "unsolved", "opportunities"]:
                if category in synthesis["gap_analysis"]:
                    claims = synthesis["gap_analysis"][category]
                    if isinstance(claims, list):
                        for i, claim_obj in enumerate(claims):
                            if isinstance(claim_obj, dict) and "claim" in claim_obj:
                                # İlgili kaynakları bul
                                source_indices = claim_obj.get("source_indices", [])
                                relevant_sources = [
                                    source_map[idx]
                                    for idx in source_indices
                                    if idx in source_map
                                ]

                                # Doğrula
                                verification = self._verify_single_claim(
                                    claim_obj["claim"], relevant_sources
                                )
                                synthesis["gap_analysis"][category][i][
                                    "_verification"
                                ] = verification

                                # İstatistik güncelle
                                verification_stats["total_claims"] += 1
                                verification_stats[verification["status"]] += 1

        # Trend analysis doğrulaması
        logger.info("Trend analizi doğrulanıyor...")
        if "trend_analysis" in synthesis:
            for category in ["methodology_shift", "tech_trends", "scale_changes", "focus_shifts"]:
                if category in synthesis["trend_analysis"]:
                    items = synthesis["trend_analysis"][category]
                    if isinstance(items, list):
                        for i, item_obj in enumerate(items):
                            if isinstance(item_obj, dict) and "description" in item_obj:
                                source_indices = item_obj.get("source_indices", [])
                                relevant_sources = [
                                    source_map[idx]
                                    for idx in source_indices
                                    if idx in source_map
                                ]

                                verification = self._verify_single_claim(
                                    item_obj["description"], relevant_sources
                                )
                                synthesis["trend_analysis"][category][i][
                                    "_verification"
                                ] = verification

                                verification_stats["total_claims"] += 1
                                verification_stats[verification["status"]] += 1

        # Actor mapping doğrulaması
        logger.info("Aktör haritası doğrulanıyor...")
        if "actor_map" in synthesis:
            for category in ["academic_groups", "companies", "key_researchers", "countries"]:
                if category in synthesis["actor_map"]:
                    items = synthesis["actor_map"][category]
                    if isinstance(items, list):
                        for i, item_obj in enumerate(items):
                            if isinstance(item_obj, dict) and "name" in item_obj:
                                source_indices = item_obj.get("source_indices", [])
                                relevant_sources = [
                                    source_map[idx]
                                    for idx in source_indices
                                    if idx in source_map
                                ]

                                # Aktör doğrulaması (daha hafif)
                                verification = self._verify_actor(
                                    category, item_obj["name"], relevant_sources
                                )
                                synthesis["actor_map"][category][i]["_verification"] = verification

                                verification_stats["total_claims"] += 1
                                verification_stats[verification["status"]] += 1

        verified_synthesis["_verification_stats"] = verification_stats
        return verified_synthesis

    def _verify_single_claim(self, claim: str, sources: List[Dict]) -> Dict[str, Any]:
        """
        Tek bir iddayı doğrula.

        Args:
            claim: Doğrulanacak iddia
            sources: İlgili kaynaklar

        Returns:
            {
                "status": "verified|inference|hallucination|unverifiable",
                "confidence": 0.0-1.0,
                "explanation": "Neden bu status?",
                "evidence": "Kaynaktan hangi kanıt?"
            }
        """
        if not sources:
            return {
                "status": "unverifiable",
                "confidence": 0.0,
                "explanation": "Kaynak belirtilmemiş",
                "evidence": None,
            }

        # Kaynakları özetle
        sources_text = "\n".join(
            [
                f"- {src.get('title', 'Bilinmiyor')} ({src.get('year', '?')}) - {src.get('abstract', '')[:300]}"
                for src in sources[:5]  # İlk 5 kaynakla sınırla (token tasarrufu)
            ]
        )

        system_prompt = """Sen bir akademik doğrulama aracısın. 
Verilen bir iddianın kaynaklarda doğru olup olmadığını kontrol edersin.

Yanıtlarında şu kategorilerden birini seç:
1. VERIFIED: İddia açıkça kaynaklarda geçiyor (% 80+)
2. INFERENCE: İddia kaynaktan çıkartılabilir ama dolaylı (% 50-80)
3. HALLUCINATION: İddia kaynaklarda yok (% 0-50)
4. UNVERIFIABLE: Kaynaklar yetersiz

Profesyonel ve dikkatli ol. Hallüsinasyon riskini minize et."""

        prompt = f"""KONTROL ETMEM GEREKEN İDDİA:
"{claim}"

KAYNAKLAR:
{sources_text}

Soru: Bu iddia yukarıdaki kaynaklarda?

Yanıtı JSON formatında ver:
{{
    "status": "verified|inference|hallucination|unverifiable",
    "confidence": 0.0 ile 1.0 arasında (4 ondalık),
    "explanation": "Status seçiminin nedeni (1-2 cümle)",
    "evidence": "Kaynaktan direkt alıntı veya bulunmazsa null"
}}

Sadece JSON döndür, başka metin yok."""

        try:
            result = self.llm.generate_json(prompt, system_prompt)

            # Validasyon
            if isinstance(result, dict):
                # Status doğrula
                if result.get("status") not in [
                    "verified",
                    "inference",
                    "hallucination",
                    "unverifiable",
                ]:
                    result["status"] = "unverifiable"

                # Confidence doğrula
                try:
                    conf = float(result.get("confidence", 0.5))
                    result["confidence"] = max(0.0, min(1.0, conf))
                except (ValueError, TypeError):
                    result["confidence"] = 0.5

                return result
            else:
                return {
                    "status": "unverifiable",
                    "confidence": 0.0,
                    "explanation": "LLM yanıt vermedi",
                    "evidence": None,
                }
        except Exception as e:
            logger.error(f"Doğrulama hatası: {e}")
            return {
                "status": "unverifiable",
                "confidence": 0.0,
                "explanation": f"Teknik hata: {str(e)[:50]}",
                "evidence": None,
            }

    def _verify_actor(
        self, category: str, actor_name: str, sources: List[Dict]
    ) -> Dict[str, Any]:
        """Aktör (kişi, kurum, şirket) doğrulaması."""
        if not sources:
            return {
                "status": "unverifiable",
                "confidence": 0.0,
                "explanation": "Kaynak belirtilmemiş",
                "evidence": None,
            }

        sources_text = "\n".join(
            [
                f"- {src.get('title', 'Bilinmiyor')} ({src.get('year', '?')}) - Yazarlar: {src.get('authors', '?')[:100]}"
                for src in sources[:3]
            ]
        )

        system_prompt = """Sen bir akademik doğrulama aracısın.
Aktörleri (üniversiteler, araştırmacılar, şirketler) kaynaklarda kontrol edersin.
Çok kesin ve yan doğru olma ihtimaline saygı duyma."""

        prompt = f"""KATEGORİ: {category}
AKTÖR ADI: {actor_name}

KAYNAKLAR:
{sources_text}

Soru: Bu aktör ({category}: {actor_name}) bu kaynaklarda bahsediliyor mu?

Yanıtı JSON:
{{
    "status": "verified|inference|hallucination|unverifiable",
    "confidence": 0.0 ile 1.0,
    "explanation": "Bulundu mu? Nasıl bulundu?",
    "evidence": "Kaynaktan alıntı veya null"
}}"""

        try:
            result = self.llm.generate_json(prompt, system_prompt)
            if isinstance(result, dict):
                if result.get("status") not in [
                    "verified",
                    "inference",
                    "hallucination",
                    "unverifiable",
                ]:
                    result["status"] = "unverifiable"
                try:
                    conf = float(result.get("confidence", 0.5))
                    result["confidence"] = max(0.0, min(1.0, conf))
                except (ValueError, TypeError):
                    result["confidence"] = 0.5
                return result
            else:
                return {
                    "status": "unverifiable",
                    "confidence": 0.0,
                    "explanation": "LLM yanıt vermedi",
                    "evidence": None,
                }
        except Exception as e:
            logger.error(f"Aktör doğrulama hatası: {e}")
            return {
                "status": "unverifiable",
                "confidence": 0.0,
                "explanation": f"Teknik hata",
                "evidence": None,
            }

    def get_verification_summary(self, stats: Dict[str, int]) -> str:
        """Doğrulama istatistiklerinin özeti."""
        total = stats.get("total_claims", 0)
        if total == 0:
            return "Doğrulanacak bulgu yok."

        verified = stats.get("verified", 0)
        inference = stats.get("inference", 0)
        hallucination = stats.get("hallucination", 0)
        unverifiable = stats.get("unverifiable", 0)

        verified_pct = (verified / total) * 100 if total > 0 else 0
        inference_pct = (inference / total) * 100 if total > 0 else 0
        hallucination_pct = (hallucination / total) * 100 if total > 0 else 0

        return f"""\n**Doğrulama Özeti:**
- Toplam bulgu: {total}
- ✅ Doğrulanmış: {verified} ({verified_pct:.1f}%)
- ⚠️  Çıkartılabilir: {inference} ({inference_pct:.1f}%)
- ❌ Hallüsinasyon: {hallucination} ({hallucination_pct:.1f}%)
- ❓ Kontrol edilemez: {unverifiable}

**Doğruluk Oranı: {(verified + inference) / total * 100 if total > 0 else 0:.1f}%** {verified} verified + {inference} inference"""
