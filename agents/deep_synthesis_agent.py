"""
Deep Synthesis Agent - Makaleleri 5 dakikada bir analiz edip sentezleyen otonom ajan.
"""

import os
import json
import time
import yaml
from pathlib import Path
from typing import List, Dict, Optional
from loguru import logger

from agents.llm_interface import LLMInterface
from tools.pdf_downloader import PDFDownloader
from tools.pdf_parser import PDFParser

class DeepSynthesisAgent:
    """Makaleleri otonom olarak inceleyen ve sentezleyen ajan."""

    def __init__(self, config: dict, project_root: Path):
        self.config = config
        self.project_root = project_root
        
        # Model zorlaması: gemini-2.5-pro
        if "llm" not in self.config:
            self.config["llm"] = {}
        self.config["llm"]["model"] = "gemini-2.5-pro"
        
        self.llm = LLMInterface(self.config)
        self.downloader = PDFDownloader(self.config, project_root)
        self.parser = PDFParser()
        
        # Dizinler
        self.output_dir = project_root / "data" / "papers" / "autonomous_synthesis"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.state_file = self.output_dir / "processing_state.json"
        self.synthesis_catalog = self.output_dir / "synthesis_catalog.json"

    def _load_state(self) -> dict:
        if self.state_file.exists():
            return json.loads(self.state_file.read_text())
        return {"last_index": -1, "processed_ids": []}

    def _save_state(self, state: dict):
        self.state_file.write_text(json.dumps(state, indent=2))

    def run_next(self, json_source: str):
        """Sıradaki makaleyi işle."""
        source_path = Path(json_source)
        if not source_path.exists():
            logger.error(f"Kaynak bulunamadı: {json_source}")
            return

        papers = json.loads(source_path.read_text())
        state = self._load_state()
        
        next_idx = state["last_index"] + 1
        if next_idx >= len(papers):
            logger.info("Tüm makaleler işlendi.")
            # İşlem bittiğinde bildirim gönder
            self._send_completion_notification("Makale Sentez", len(papers))
            return

        paper = papers[next_idx]
        paper_id = paper.get("paper_id") or paper.get("title")
        
        logger.info(f"[{next_idx}] İşleniyor: {paper.get('title')}")

        paper = papers[next_idx]
        paper_id = paper.get("paper_id") or paper.get("title")
        
        logger.info(f"[{next_idx}] İşleniyor: {paper.get('title')}")

        # 1. Alaka Kontrolü (Relevance Check)
        if not self._is_relevant(paper):
            logger.info(f"Makale elendi (alakasız): {paper.get('title')}")
            state["last_index"] = next_idx
            self._save_state(state)
            return

        # 2. İçerik Edinme (PDF veya Abstract)
        content, source_type = self._get_content(paper)
        if not content:
            logger.warning("İçerik edinilemedi, atlanıyor.")
            state["last_index"] = next_idx
            self._save_state(state)
            return

        # 3. Sentezleme
        synthesis = self._synthesize(paper, content, source_type)
        if synthesis:
            self._save_synthesis(paper, synthesis, source_type)
            state["processed_ids"].append(paper_id)

        state["last_index"] = next_idx
        self._save_state(state)
        logger.info(f"Makale başarıyla sentezlendi: {paper.get('title')}")

    def _is_relevant(self, paper: dict) -> bool:
        """Makalenin tezle alakalı olup olmadığını kontrol et."""
        prompt = (
            f"Aşağıdaki makale 'Multi-Agent Grid Load Negotiation for EV Charging' konusuyla doğrudan alakalı mı?\n"
            f"Başlık: {paper.get('title')}\n"
            f"Abstract: {paper.get('abstract')}\n\n"
            f"Sadece 'EV', 'Charging', 'Multi-agent', 'Smart Grid', 'Load Management', 'Negotiation' "
            f"gibi konuları içeriyorsa 'EVET' de. Alakasızsa 'HAYIR' de. Sadece tek kelime yanıt ver."
        )
        response = self.llm.generate(prompt).strip().upper()
        return "EVET" in response or "YES" in response

    def _get_content(self, paper: dict):
        title = paper.get("title")
        pdf_url = paper.get("pdf_url")
        
        if pdf_url:
            filename = f"paper_{hash(title)}.pdf"
            pdf_path = self.downloader.download(pdf_url, filename)
            if pdf_path:
                text = self.parser.extract_text(pdf_path)
                if len(text) > 500:
                    return text, "FULL_PDF"
        
        abstract = paper.get("abstract")
        if abstract:
            return abstract, "ABSTRACT_ONLY"
            
        return None, None

    def _synthesize(self, paper: dict, content: str, source_type: str) -> Optional[dict]:
        """Kesinlikle orijinal metne sadık kalarak sentezle."""
        prompt = (
            f"GÖREV: Aşağıdaki metni objektif bir şekilde sentezle. HALÜSİNASYON YASAKTIR. "
            f"Sadece metinde geçen bilgileri kullan. Teknik terimleri koru.\n\n"
            f"BAĞLAM: Enes'in 'Multi-Agent Grid Load Negotiation for EV Charging' tezi.\n\n"
            f"MAKALE ({source_type}):\n{content[:15000]}\n\n"
            f"ŞU FORMATTA YANIT VER (JSON):\n"
            f"{{\n"
            f"  \"objective\": \"Çalışmanın amacı nedir?\",\n"
            f"  \"methodology\": \"Hangi yöntem/algoritma kullanılmış?\",\n"
            f"  \"key_findings\": [\"Bulgu 1\", \"Bulgu 2\"],\n"
            f"  \"grid_impact\": \"Şebeke etkileşimi nasıl ele alınmış?\",\n"
            f"  \"negotiation_aspect\": \"Pazarlık/Anlaşma mekanizması var mı, nasıl?\",\n"
            f"  \"verbatim_quotes\": [\"Metinden doğrudan önemli bir cümle 1\", \"Cümle 2\"]\n"
            f"}}"
        )
        return self.llm.generate_json(prompt)

    def _save_synthesis(self, paper: dict, synthesis: dict, source_type: str):
        filename = f"synthesis_{hash(paper.get('title'))}.json"
        result = {
            "meta": {
                "title": paper.get("title"),
                "authors": paper.get("authors"),
                "year": paper.get("year"),
                "source_type": source_type,
                "processed_at": time.strftime("%Y-%m-%d %H:%M:%S")
            },
            "synthesis": synthesis
        }
        (self.output_dir / filename).write_text(json.dumps(result, ensure_ascii=False, indent=2))
        
        # Kataloğa ekle
        catalog = []
        if self.synthesis_catalog.exists():
            catalog = json.loads(self.synthesis_catalog.read_text())
        catalog.append({"title": paper.get("title"), "file": filename})
        self.synthesis_catalog.write_text(json.dumps(catalog, indent=2))

    def _send_completion_notification(self, task_name: str, count: int):
        """İşlem bittiğinde bildirim gönder."""
        state = self._load_state()
        if state.get("completion_notified"):
            return

        message = f"🏁 *{task_name} İşlemi Tamamlandı!*\n\nListedeki toplam {count} kaynak başarıyla tarandı ve analiz edildi. Başka bir işlem kalmadı."
        try:
            # openclaw message send yerine subprocess ile CLI üzerinden bildirim
            import subprocess
            cmd = ["openclaw", "message", "send", "--target", "telegram:785866687", "--message", message]
            subprocess.run(cmd, check=False)
            state["completion_notified"] = True
            self._save_state(state)
        except Exception as e:
            logger.error(f"Bildirim gönderme hatası: {e}")
