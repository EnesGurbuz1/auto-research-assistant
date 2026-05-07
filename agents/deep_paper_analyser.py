"""
Deep Paper Analyser - Makaleleri derinlemesine analiz eden ajan.
JSON listesindeki makaleleri indirir, okur ve tez bağlamında değerlendirir.
"""

import os
import json
import time
from pathlib import Path
from typing import List, Dict, Optional
from loguru import logger
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from agents.llm_interface import LLMInterface
from tools.pdf_downloader import PDFDownloader
from tools.pdf_parser import PDFParser

console = Console()

class DeepPaperAnalyser:
    """Makaleleri derinlemesine analiz eden ajan."""

    def __init__(self, config: dict, project_root: Path):
        self.config = config
        self.project_root = project_root
        self.llm = LLMInterface(config)
        self.downloader = PDFDownloader(config, project_root)
        self.parser = PDFParser()
        
        # Çıktı dizini
        self.output_dir = project_root / "data" / "papers" / "deep_analysis"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Sistem prompt'u
        self.system_prompt = self.llm.load_system_prompt("deep_analyser_system", project_root)
        if not self.system_prompt:
            self.system_prompt = (
                "Sen kıdemli bir akademik araştırma asistanısın. Görevin, verilen makale metnini "
                "Enes'in 'Multi-Agent Grid Load Negotiation for EV Charging' başlıklı tezi bağlamında "
                "analiz etmektir. Makalenin yöntemlerini, bulgularını ve Enes'in çalışması için "
                "nasıl bir temel oluşturabileceğini veya hangi boşlukları bıraktığını belirle."
            )

    def analyze_json_file(self, json_path: str, limit: int = 10):
        """JSON dosyasındaki makaleleri analiz et."""
        path = Path(json_path)
        if not path.exists():
            logger.error(f"JSON dosyası bulunamadı: {json_path}")
            return

        with open(path, "r", encoding="utf-8") as f:
            papers = json.load(f)

        # Analiz edilecekleri seç (pdf_url olanlar öncelikli veya ilk N tane)
        to_analyze = [p for p in papers if p.get("pdf_url")]
        if not to_analyze:
            to_analyze = papers[:limit]
        else:
            to_analyze = to_analyze[:limit]

        console.print(f"[bold green]🚀 {len(to_analyze)} makale için derin analiz başlatılıyor...[/bold green]")

        results = []
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]Makaleler işleniyor...", total=len(to_analyze))
            
            for paper in to_analyze:
                title = paper.get("title", "Adsız Makale")
                progress.update(task, description=f"[cyan]Analiz ediliyor: {title[:50]}...")
                
                analysis = self.process_single_paper(paper)
                if analysis:
                    results.append(analysis)
                
                progress.advance(task)

        # Sonuçları kaydet
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_file = self.output_dir / f"deep_analysis_{timestamp}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        console.print(f"\n[bold green]✅ Analiz tamamlandı! {len(results)} sonuç şuraya kaydedildi:[/bold green]")
        console.print(f"[blue]{output_file}[/blue]")

    def process_single_paper(self, paper: Dict) -> Optional[Dict]:
        """Tek bir makaleyi indir, oku ve analiz et."""
        title = paper.get("title")
        pdf_url = paper.get("pdf_url")
        
        logger.info(f"İşleniyor: {title}")
        
        # 1. PDF İndir
        pdf_path = None
        if pdf_url:
            filename = title.lower().replace(" ", "_")[:50] + ".pdf"
            pdf_path = self.downloader.download(pdf_url, filename)
        
        # 2. Metin Çıkar
        content = ""
        if pdf_path:
            content = self.parser.extract_text(pdf_path)
        
        # Eğer PDF içeriği yoksa abstract kullan
        if not content:
            content = paper.get("abstract", "")
            if not content:
                logger.warning(f"İçerik bulunamadı (PDF yok, abstract yok): {title}")
                return None
            source_type = "abstract_only"
        else:
            source_type = "full_pdf"

        # 3. LLM ile Analiz
        analysis_prompt = (
            f"Aşağıdaki makaleyi Enes'in tezi ('Multi-Agent Grid Load Negotiation for EV Charging') için analiz et.\n\n"
            f"MAKALE BİLGİLERİ:\n"
            f"Başlık: {title}\n"
            f"Yazarlar: {paper.get('authors')}\n"
            f"Yıl: {paper.get('year')}\n\n"
            f"MAKALE İÇERİĞİ ({source_type}):\n"
            f"{content[:15000]}  # Token limitine takılmamak için ilk 15k karakter\n\n"
            f"LÜTFEN ŞU FORMATTA ANALİZ YAP (JSON):\n"
            f"{{\n"
            f"  \"summary\": \"Makalenin kısa özeti\",\n"
            f"  \"key_methodologies\": [\"Yöntem 1\", \"Yöntem 2\"],\n"
            f"  \"relevance_to_thesis\": \"Bu makalenin teze katkısı nedir?\",\n"
            f"  \"limitations_and_gaps\": \"Makalenin eksik bıraktığı veya Enes'in geliştirebileceği alanlar\",\n"
            f"  \"suggested_references\": [\"Takip edilmesi gereken atıflar\"]\n"
            f"}}"
        )

        try:
            llm_result = self.llm.generate_json(analysis_prompt, self.system_prompt)
            
            return {
                "paper_info": paper,
                "source": source_type,
                "pdf_local_path": str(pdf_path) if pdf_path else None,
                "analysis": llm_result
            }
        except Exception as e:
            logger.error(f"Analiz hatası ({title}): {e}")
            return None
