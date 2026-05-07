"""
Synthesis Agent - Sentez ve analiz ajanı.
Toplanan verileri analiz eder, gap analizi yapar, trendleri tespit eder.
Danışman hocanın 3 temel sorusuna cevap üretir.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from loguru import logger
from rich.console import Console

from agents.orchestrator import Orchestrator
from skills.fact_checker import FactChecker

console = Console()


class SynthesisAgent(Orchestrator):
    """Sentez ve gap analizi ajanı."""

    def __init__(self, config: dict, project_root: Path):
        super().__init__(config, project_root)

    def run(
        self,
        literature: Optional[List[Dict]] = None,
        patents: Optional[List[Dict]] = None,
        datasets: Optional[List[Dict]] = None,
    ) -> Dict[str, Any]:
        """Tüm verileri sentezle ve gap analizi üret."""
        self.start_time = datetime.now()
        
        # Veri yoksa diskten yükle
        if literature is None:
            literature = self._load_latest("papers/scholar_results")
        if patents is None:
            patents = self._load_latest("patents")
        if datasets is None:
            datasets = self._load_latest("datasets_catalog")

        synthesis = {}

        # 1. Gap Analizi — "Çözülmüş ne var, çözülmemiş ne var?"
        console.print("  [dim]→ Gap analizi yapılıyor...[/dim]")
        synthesis["gap_analysis"] = self._gap_analysis(literature, patents)

        # 2. Aktör Haritası — "Kim çalışıyor, hangi gruplar, hangi şirketler?"
        console.print("  [dim]→ Aktör haritası çıkarılıyor...[/dim]")
        synthesis["actor_map"] = self._actor_mapping(literature, patents)

        # 3. Trend Tespiti — "2-3 yıl önce ile bugün arasında ne değişti?"
        console.print("  [dim]→ Trend analizi yapılıyor...[/dim]")
        synthesis["trend_analysis"] = self._trend_analysis(literature)

        # 4. Veri Seti Değerlendirmesi
        console.print("  [dim]→ Veri seti değerlendirmesi yapılıyor...[/dim]")
        synthesis["dataset_assessment"] = self._dataset_assessment(datasets)

        # 5. Araştırma Soruları Önerisi
        console.print("  [dim]→ Araştırma soruları üretiliyor...[/dim]")
        synthesis["research_questions"] = self._generate_research_questions(synthesis)

        # 6. Doğrulama (Fact-Check) — Hallüsinasyon kontrolü
        console.print("  [dim]→ Bulgular doğrulanıyor (Fact-Check)...[/dim]")
        fact_checker = FactChecker(self.config)
        verified_synthesis = fact_checker.verify_synthesis(
            synthesis, literature, patents
        )
        synthesis = verified_synthesis

        # Sentezi kaydet
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.save_results("summaries", f"synthesis_{timestamp}.json", synthesis)

        console.print("  [green]✓ Synthesis doğrulanarak kayıt edildi[/green]")
        return synthesis

    def _gap_analysis(self, literature: List[Dict], patents: List[Dict]) -> Dict:
        """Danışman sorusu #1: Çözülmüş ne var, çözülmemiş ne var?"""
        try:
            system_prompt = self.llm.load_system_prompt("synthesis_system", self.project_root)
            
            lit_summary, lit_originals = self._summarize_list_with_indices(literature, 30)
            pat_summary, pat_originals = self._summarize_list_with_indices(patents, 10)
            
            # Tüm kaynakları bir listeye koy (indeks takibi için)
            all_sources = lit_originals + pat_originals
            
            prompt = f"""Aşağıdaki akademik çalışmalar ve patentler ışığında, "Multi-Agent Grid Load Negotiation for EV Charging" alanında:

1. ÇÖZÜLMÜŞ PROBLEMLER: Ne tür problemler zaten çözülmüş?
2. ÇÖZÜLMEMIŞ PROBLEMLER: Hangi boşluklar (gap) hâlâ mevcut?
3. FIRSATLAR: Hangi alanlarda yeni katkı yapılabilir?

HER bir iddiayı JSON'da "claim" alanına yaz, ve onu destekleyen kaynakların INDEX numaralarını "source_indices" dizisine ekle.

LİTERATÜR (İndeks 0-{len(lit_originals)-1}):
{json.dumps(lit_summary, ensure_ascii=False)}

PATENTLER (İndeks {len(lit_originals)}-{len(all_sources)-1}):
{json.dumps(pat_summary, ensure_ascii=False)}

JSON formatında yanıt ver, HER bir item için source_indices dizisi olsun:
{{
    "solved": [{{"claim": "...", "source_indices": [0, 5, 12]}}],
    "unsolved": [{{"claim": "...", "source_indices": [2, 8]}}],
    "opportunities": [{{"claim": "...", "source_indices": [1, 3, 15]}}]
}}"""
            
            result = self.llm.generate_json(prompt, system_prompt)
            
            # Orijinal nesneleri kaynakça referansıyla sakla
            if isinstance(result, dict):
                result["_source_references"] = all_sources
            
            return result
        except Exception as e:
            logger.error(f"Gap analizi hatası: {e}")
            return {"solved": [], "unsolved": [], "opportunities": [], "error": str(e)}

    def _actor_mapping(self, literature: List[Dict], patents: List[Dict]) -> Dict:
        """Danışman sorusu #2: Kim çalışıyor, hangi gruplar, hangi şirketler?"""
        try:
            system_prompt = self.llm.load_system_prompt("synthesis_system", self.project_root)
            
            lit_summary, lit_originals = self._summarize_list_with_indices(literature, 30)
            pat_summary, pat_originals = self._summarize_list_with_indices(patents, 10)
            
            all_sources = lit_originals + pat_originals
            
            prompt = f"""Aşağıdaki akademik çalışmalar ve patentlerden, bu alandaki aktörleri çıkar:

1. AKADEMİK GRUPLAR: Hangi üniversiteler/laboratuvarlar çalışıyor?
2. ŞİRKETLER: Hangi şirketler patent almış veya yayın yapmış?
3. ANAHTAR ARAŞTIRMACILAR: En çok alıntı yapılan yazarlar kimler?
4. ÜLKE DAĞILIMI: Hangi ülkeler bu alanda aktif?

HER bulguyu destekleyen kaynakların INDEX numaralarını "source_indices" dizisine koy.

LİTERATÜR (İndeks 0-{len(lit_originals)-1}):
{json.dumps(lit_summary, ensure_ascii=False)}

PATENTLER (İndeks {len(lit_originals)}-{len(all_sources)-1}):
{json.dumps(pat_summary, ensure_ascii=False)}

JSON formatında yanıt ver:
{{
    "academic_groups": [{{"name": "...", "source_indices": [0, 5]}}],
    "companies": [{{"name": "...", "source_indices": [2, 8]}}],
    "key_researchers": [{{"name": "...", "source_indices": [1, 3]}}],
    "countries": [{{"name": "...", "source_indices": [0, 1, 2]}}]
}}"""
            
            result = self.llm.generate_json(prompt, system_prompt)
            
            if isinstance(result, dict):
                result["_source_references"] = all_sources
            
            return result
        except Exception as e:
            logger.error(f"Aktör haritası hatası: {e}")
            return {"academic_groups": [], "companies": [], "key_researchers": [], "countries": [], "error": str(e)}

    def _trend_analysis(self, literature: List[Dict]) -> Dict:
        """Danışman sorusu #3: 2-3 yıl önce ile bugün arasında ne değişti?"""
        try:
            system_prompt = self.llm.load_system_prompt("synthesis_system", self.project_root)
            
            lit_summary, lit_originals = self._summarize_list_with_indices(literature, 30)
            
            prompt = f"""Aşağıdaki akademik çalışmaları yıllara göre analiz et.
"Multi-Agent EV Charging" alanında 2022-2023 ile 2024-2026 arasında:

1. METODOLOJİ DEĞİŞİMİ: Kullanılan yöntemler nasıl değişti?
2. TEKNOLOJİ TRENDLERİ: Hangi yeni teknolojiler (LLM, RL, federated learning vb.) girdi?
3. ÖLÇEK DEĞİŞİMİ: Çalışmaların ölçeği nasıl değişti?
4. FOKUS KAYMALARI: Araştırma odağı nereden nereye kaydı?

HER trend açıklamasını destekleyen kaynakların INDEX numaralarını "source_indices" dizisine koy.

LİTERATÜR (İndeks 0-{len(lit_originals)-1}):
{json.dumps(lit_summary, ensure_ascii=False)}

JSON formatında yanıt ver:
{{
    "methodology_shift": [{{"description": "...", "source_indices": [0, 5, 10]}}],
    "tech_trends": [{{"description": "...", "source_indices": [2, 8]}}],
    "scale_changes": [{{"description": "...", "source_indices": [1, 3, 15]}}],
    "focus_shifts": [{{"description": "...", "source_indices": [0, 1, 2, 3]}}]
}}"""
            
            result = self.llm.generate_json(prompt, system_prompt)
            
            if isinstance(result, dict):
                result["_source_references"] = lit_originals
            
            return result
        except Exception as e:
            logger.error(f"Trend analizi hatası: {e}")
            return {"methodology_shift": [], "tech_trends": [], "scale_changes": [], "focus_shifts": [], "error": str(e)}

    def _dataset_assessment(self, datasets: List[Dict]) -> Dict:
        """Veri setlerinin tez çalışması için değerlendirmesi."""
        try:
            system_prompt = self.llm.load_system_prompt("synthesis_system", self.project_root)
            
            ds_summary, ds_originals = self._summarize_list_with_indices(datasets, 20)
            
            prompt = f"""Aşağıdaki veri setlerini "Multi-Agent Grid Load Negotiation for EV Charging" tez konusu açısından değerlendir:

1. DOĞRUDAN KULLANILABILIR: Hangileri doğrudan deneylerde kullanılabilir?
2. UYARLANARAK KULLANILABİLİR: Hangileri adapte edilerek kullanılabilir?
3. EKSİK VERİ: Ne tür veri seti oluşturulması gerekebilir?

HER öneril için veri seti indexlerini "dataset_indices" dizisine koy.

VERİ SETLERİ (İndeks 0-{len(ds_originals)-1}):
{json.dumps(ds_summary, ensure_ascii=False)}

JSON formatında yanıt ver:
{{
    "directly_usable": [{{"dataset_name": "...", "dataset_indices": [0, 5], "reason": "..."}}],
    "adaptable": [{{"dataset_name": "...", "dataset_indices": [2, 8], "adaptation": "..."}}],
    "missing_data": [{{"type": "...", "description": "..."}}]
}}"""
            
            result = self.llm.generate_json(prompt, system_prompt)
            
            if isinstance(result, dict):
                result["_dataset_references"] = ds_originals
            
            return result
        except Exception as e:
            logger.error(f"Veri seti değerlendirmesi hatası: {e}")
            return {"directly_usable": [], "adaptable": [], "missing_data": [], "error": str(e)}

    def _generate_research_questions(self, synthesis: Dict) -> List[str]:
        """Gap analizine dayanarak araştırma soruları öner."""
        try:
            system_prompt = self.llm.load_system_prompt("synthesis_system", self.project_root)
            
            prompt = f"""Aşağıdaki gap analizi ve trend analizine dayanarak,
"Multi-Agent Grid Load Negotiation for EV Charging" konusunda
5-7 adet potansiyel araştırma sorusu öner.

GAP ANALİZİ:
{json.dumps(synthesis.get('gap_analysis', {}), ensure_ascii=False)}

TREND ANALİZİ:
{json.dumps(synthesis.get('trend_analysis', {}), ensure_ascii=False)}

JSON array formatında döndür: ["soru1", "soru2", ...]"""
            
            return self.llm.generate_json(prompt, system_prompt)
        except Exception as e:
            logger.error(f"Araştırma soruları hatası: {e}")
            return []

    def _summarize_list(self, items: List[Dict], max_items: int) -> List[Dict]:
        """Listeyi özetleyerek kısalt."""
        summarized = []
        for item in items[:max_items]:
            summary = {
                "title": item.get("title", ""),
                "year": item.get("year", ""),
                "authors": item.get("authors", "")[:100] if isinstance(item.get("authors"), str) else "",
                "abstract": (item.get("abstract", "") or "")[:300],
                "source": item.get("source", ""),
            }
            summarized.append(summary)
        return summarized
    
    def _summarize_list_with_indices(self, items: List[Dict], max_items: int) -> tuple:
        """Listeyi özetleyerek kısalt ve orijinal indisleri tut.
        
        Returns:
            (summarized_list, original_items) tuple - özetler ve orijinal nesneler
        """
        summarized = []
        original_items = []
        for idx, item in enumerate(items[:max_items]):
            summary = {
                "index": idx,
                "title": item.get("title", ""),
                "year": item.get("year", ""),
                "authors": item.get("authors", "")[:100] if isinstance(item.get("authors"), str) else "",
                "abstract": (item.get("abstract", "") or "")[:300],
                "source": item.get("source", ""),
            }
            summarized.append(summary)
            original_items.append(item)
        return summarized, original_items

    def _load_latest(self, subdir: str) -> List[Dict]:
        """Belirtilen dizindeki en son JSON dosyasını yükle."""
        data_dir = self.project_root / "data" / subdir
        if not data_dir.exists():
            return []
        
        json_files = sorted(data_dir.glob("*.json"), reverse=True)
        if not json_files:
            return []
        
        try:
            with open(json_files[0], "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception:
            return []
