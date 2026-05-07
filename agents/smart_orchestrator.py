"""
Smart Orchestrator - Akıllı görev planlama ve tam pipeline yönetimi.
Tüm ajanları koordine eder ve sonuçları sentezler.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
from loguru import logger
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from agents.orchestrator import Orchestrator
from agents.literature_scout import LiteratureScout
from agents.patent_scanner import PatentScanner
from agents.dataset_hunter import DatasetHunter
from agents.synthesis_agent import SynthesisAgent
from agents.report_generator import ReportGenerator

console = Console()


class SmartOrchestrator(Orchestrator):
    """Akıllı orkestratör - tam araştırma pipeline'ını yönetir."""

    def __init__(self, config: dict, project_root: Path):
        super().__init__(config, project_root)
        self.literature_scout = LiteratureScout(config, project_root)
        self.patent_scanner = PatentScanner(config, project_root)
        self.dataset_hunter = DatasetHunter(config, project_root)
        self.synthesis_agent = SynthesisAgent(config, project_root)
        self.report_generator = ReportGenerator(config, project_root)

    def run_full_pipeline(self):
        """Tam araştırma pipeline'ını çalıştır."""
        self.start_time = datetime.now()
        console.print("\n[bold green]═══ TAM ARAŞTIRMA PIPELİNE BAŞLIYOR ═══[/bold green]\n")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:

            # Adım 1: Literatür Taraması
            task = progress.add_task("📚 Literatür taraması...", total=None)
            try:
                lit_results = self.literature_scout.run()
                self.log_step("LiteratureScout", "search", "success",
                              f"{len(lit_results)} sonuç bulundu")
            except Exception as e:
                self.log_step("LiteratureScout", "search", "error", str(e))
                lit_results = []
                logger.error(f"Literatür taraması hatası: {e}")
            progress.remove_task(task)
            console.print(f"  ✅ Literatür: {len(lit_results)} sonuç\n")

            # Adım 2: Patent Taraması
            task = progress.add_task("📋 Patent taraması...", total=None)
            try:
                patent_results = self.patent_scanner.run()
                self.log_step("PatentScanner", "search", "success",
                              f"{len(patent_results)} patent bulundu")
            except Exception as e:
                self.log_step("PatentScanner", "search", "error", str(e))
                patent_results = []
                logger.error(f"Patent taraması hatası: {e}")
            progress.remove_task(task)
            console.print(f"  ✅ Patent: {len(patent_results)} sonuç\n")

            # Adım 3: Veri Seti Taraması
            task = progress.add_task("📊 Veri seti taraması...", total=None)
            try:
                dataset_results = self.dataset_hunter.run()
                self.log_step("DatasetHunter", "search", "success",
                              f"{len(dataset_results)} veri seti bulundu")
            except Exception as e:
                self.log_step("DatasetHunter", "search", "error", str(e))
                dataset_results = []
                logger.error(f"Veri seti taraması hatası: {e}")
            progress.remove_task(task)
            console.print(f"  ✅ Veri Seti: {len(dataset_results)} sonuç\n")

            # Adım 4: Sentez & Gap Analizi
            task = progress.add_task("🧪 Sentez analizi...", total=None)
            try:
                synthesis = self.synthesis_agent.run(
                    literature=lit_results,
                    patents=patent_results,
                    datasets=dataset_results
                )
                self.log_step("SynthesisAgent", "analyze", "success", "Sentez tamamlandı")
            except Exception as e:
                self.log_step("SynthesisAgent", "analyze", "error", str(e))
                synthesis = {}
                logger.error(f"Sentez hatası: {e}")
            progress.remove_task(task)
            console.print("  ✅ Sentez tamamlandı\n")

            # Adım 5: Rapor Üretimi
            task = progress.add_task("📝 Rapor üretiliyor...", total=None)
            try:
                report_path = self.report_generator.generate_weekly_report(
                    literature=lit_results,
                    patents=patent_results,
                    datasets=dataset_results,
                    synthesis=synthesis
                )
                self.log_step("ReportGenerator", "generate", "success",
                              f"Rapor: {report_path}")
            except Exception as e:
                self.log_step("ReportGenerator", "generate", "error", str(e))
                logger.error(f"Rapor üretimi hatası: {e}")
            progress.remove_task(task)
            console.print("  ✅ Rapor üretildi\n")

        # Logu kaydet
        self.save_run_log()

        elapsed = datetime.now() - self.start_time
        console.print(f"\n[bold green]═══ PIPELİNE TAMAMLANDI ({elapsed.total_seconds():.1f}s) ═══[/bold green]")

    def run_incremental(self, focus: str = "all"):
        """Artımlı güncelleme — sadece yeni sonuçları topla."""
        console.print(f"[cyan]Artımlı güncelleme: focus={focus}[/cyan]")
        
        if focus in ("all", "literature"):
            self.literature_scout.run_incremental()
        if focus in ("all", "patents"):
            self.patent_scanner.run_incremental()
        if focus in ("all", "datasets"):
            self.dataset_hunter.run_incremental()
