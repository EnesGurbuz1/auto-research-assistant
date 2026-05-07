"""
Dataset Explorer Agent - Veri setlerini otonom olarak inceleyen ve analiz eden ajan.
5 dakikada bir çalışarak katalogdaki veri setlerini web kazıma ile detaylandırır.
"""

import os
import json
import time
from pathlib import Path
from typing import Dict, Optional
from loguru import logger

from agents.llm_interface import LLMInterface

class DatasetExplorerAgent:
    """Veri setlerini otonom olarak kazıyan ve analiz eden ajan."""

    def __init__(self, config: dict, project_root: Path):
        self.config = config
        self.project_root = project_root
        
        # Model seçimi: Gemini 2.5 Flash Lite (Hızlı ve etkili kazıma analizi için)
        if "llm" not in self.config:
            self.config["llm"] = {}
        self.config["llm"]["model"] = "gemini-2.5-flash-lite"
        
        self.llm = LLMInterface(self.config)
        
        # SSD Dizinleri (Sembolik linkler üzerinden)
        self.output_dir = project_root / "data" / "datasets_deep_analysis"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.state_file = self.output_dir / "processing_state.json"
        self.dataset_catalog = self.output_dir / "explored_datasets_catalog.json"

    def _load_state(self) -> dict:
        if self.state_file.exists():
            return json.loads(self.state_file.read_text())
        return {"last_index": -1, "explored_names": []}

    def _save_state(self, state: dict):
        self.state_file.write_text(json.dumps(state, indent=2))

    def run_next(self, json_source: str):
        """Sıradaki veri setini incele."""
        source_path = Path(json_source)
        if not source_path.exists():
            logger.error(f"Kaynak bulunamadı: {json_source}")
            return

        datasets = json.loads(source_path.read_text())
        state = self._load_state()
        
        next_idx = state["last_index"] + 1
        if next_idx >= len(datasets):
            logger.info("Tüm veri setleri incelendi.")
            self._send_completion_notification("Veri Seti Keşfi", len(datasets))
            return

        ds = datasets[next_idx]
        ds_name = ds.get("name") or ds.get("title")
        
        logger.info(f"[{next_idx}] İnceleniyor: {ds_name}")

        ds = datasets[next_idx]
        ds_name = ds.get("name") or ds.get("title")
        
        logger.info(f"[{next_idx}] İnceleniyor: {ds_name}")

        # 1. Web İçeriği Edinme (Scrapling/WebFetch)
        web_content = self._fetch_dataset_info(ds.get("url"))
        
        # 2. Alaka ve Detay Analizi (Gemini 2.5 Flash Lite)
        analysis = self._analyze_dataset(ds, web_content)
        
        if analysis and analysis.get("is_useful"):
            self._save_analysis(ds, analysis)
            state["explored_names"].append(ds_name)
            logger.info(f"Veri seti faydalı bulundu ve kaydedildi: {ds_name}")
        else:
            logger.info(f"Veri seti elendi: {ds_name}")

        state["last_index"] = next_idx
        self._save_state(state)

    def _fetch_dataset_info(self, url: str) -> str:
        """Veri seti sayfasını kazı."""
        if not url:
            return ""
        
        logger.info(f"Web sayfası kazınıyor: {url}")
        
        # Öncelikli olarak scrapling (Eğer kütüphane varsa)
        try:
            from scrapling import Fetcher
            fetcher = Fetcher()
            page = fetcher.get(url)
            return page.text[:20000]
        except Exception:
            pass

        # Yedek yöntem: httpx ile basit fetch
        try:
            import httpx
            with httpx.Client(timeout=30, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()
                # Basit bir HTML temizleme (opsiyonel)
                return resp.text[:15000]
        except Exception as e:
            logger.warning(f"Fetch hatası: {e}")
            return ""

    def _analyze_dataset(self, ds: dict, web_content: str) -> dict:
        """Veri setini tez bağlamında analiz et."""
        prompt = (
            f"GÖREV: Aşağıdaki veri setini Enes'in 'Multi-Agent Grid Load Negotiation for EV Charging' tezi için incele.\n"
            f"Sadece sağlanan bilgilere dayan, ASLA HALÜSİNASYON YAPMA.\n\n"
            f"VERİ SETİ BİLGİLERİ:\n"
            f"İsim: {ds.get('name')}\n"
            f"Başlık: {ds.get('title')}\n"
            f"URL: {ds.get('url')}\n"
            f"Ham Açıklama: {ds.get('description')}\n\n"
            f"WEB SAYFASI İÇERİĞİ:\n{web_content[:10000]}\n\n"
            f"YANITINI ŞU JSON FORMATINDA VER:\n"
            f"{{\n"
            f"  \"is_useful\": true/false (Tez için doğrudan kullanılabilir mi?),\n"
            f"  \"reasoning\": \"Neden faydalı veya neden elendi?\",\n"
            f"  \"content_summary\": \"Veri setinde neler var? (Zaman serisi, kullanıcı verisi, şebeke yükü vb.)\",\n"
            f"  \"key_features\": [\"Özellik 1\", \"Özellik 2\"],\n"
            f"  \"data_format\": \"CSV, JSON, Parquet vb.\",\n"
            f"  \"potential_use_case\": \"Tezde tam olarak hangi analiz/simülasyon için kullanılabilir?\"\n"
            f"}}"
        )
        return self.llm.generate_json(prompt)

    def _save_analysis(self, ds: dict, analysis: dict):
        safe_name = "".join([c if c.isalnum() else "_" for c in ds.get('name', 'ds')])
        filename = f"ds_analysis_{safe_name}.json"
        result = {
            "meta": {
                "name": ds.get("name"),
                "url": ds.get("url"),
                "source": ds.get("source"),
                "processed_at": time.strftime("%Y-%m-%d %H:%M:%S")
            },
            "analysis": analysis
        }
        (self.output_dir / filename).write_text(json.dumps(result, ensure_ascii=False, indent=2))
        
        # Kataloğa ekle
        catalog = []
        if self.dataset_catalog.exists():
            catalog = json.loads(self.dataset_catalog.read_text())
        catalog.append({"name": ds.get("name"), "file": filename})
        self.dataset_catalog.write_text(json.dumps(catalog, indent=2))

    def _send_completion_notification(self, task_name: str, count: int):
        """İşlem bittiğinde bildirim gönder."""
        state = self._load_state()
        if state.get("completion_notified"):
            return

        message = f"🏁 *{task_name} İşlemi Tamamlandı!*\n\nListedeki toplam {count} kaynak başarıyla tarandı ve analiz edildi. Başka bir işlem kalmadı."
        try:
            import subprocess
            cmd = ["openclaw", "message", "send", "--target", "telegram:785866687", "--message", message]
            subprocess.run(cmd, check=False)
            state["completion_notified"] = True
            self._save_state(state)
        except Exception as e:
            logger.error(f"Bildirim gönderme hatası: {e}")
