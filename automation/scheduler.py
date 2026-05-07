"""
Scheduler - Otomatik görev zamanlayıcı.
Haftalık rapor üretimi ve periyodik tarama planlar.
"""

import schedule
import time
from datetime import datetime
from pathlib import Path
from loguru import logger
from rich.console import Console

console = Console()


class ResearchScheduler:
    """Araştırma görevleri zamanlayıcısı."""

    def __init__(self, config: dict, project_root: Path):
        self.config = config
        self.project_root = project_root
        self.reporting = config.get("reporting", {})

    def setup_schedule(self):
        """Zamanlama kurallarını ayarla."""
        # Her Pazartesi 02:00 → tam tarama
        schedule.every().monday.at("02:00").do(self._full_scan_job)
        logger.info("Tam tarama zamanlandı: Her Pazartesi 02:00")

        # Her gün 08:00 → artımlı tarama
        schedule.every().day.at("08:00").do(self._daily_scan_job)
        logger.info("Günlük tarama zamanlandı: 08:00")

        # Her Cuma 20:00 → haftalık rapor (hem .md hem .docx)
        schedule.every().friday.at("20:00").do(self._weekly_report_job)
        logger.info("Haftalık rapor zamanlandı: Her Cuma 20:00")

        # Her 30 dk → GitHub sync
        schedule.every(30).minutes.do(self._github_sync_job)
        logger.info("GitHub sync zamanlandı: Her 30 dk")

    def run(self):
        """Zamanlayıcıyı başlat (daemon modu)."""
        self.setup_schedule()
        console.print("[green]🤖 Daemon başlatıldı. Çıkış için Ctrl+C.[/green]")
        
        while True:
            schedule.run_pending()
            time.sleep(60)

    def _full_scan_job(self):
        """Tam tarama görevi."""
        logger.info("Tam tarama görevi başlıyor...")
        try:
            from agents.smart_orchestrator import SmartOrchestrator
            import yaml
            
            config_path = self.project_root / "config.yaml"
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            
            orchestrator = SmartOrchestrator(config, self.project_root)
            orchestrator.run_full_pipeline()
            logger.info("Tam tarama görevi tamamlandı")
        except Exception as e:
            logger.error(f"Tam tarama görevi hatası: {e}")

    def _weekly_report_job(self):
        """Haftalık rapor üretim görevi."""
        logger.info("Haftalık rapor görevi başlıyor...")
        try:
            from agents.report_generator import ReportGenerator
            import yaml
            
            config_path = self.project_root / "config.yaml"
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            
            generator = ReportGenerator(config, self.project_root)
            generator.generate_weekly_report()
            logger.info("Haftalık rapor görevi tamamlandı")
        except Exception as e:
            logger.error(f"Haftalık rapor görevi hatası: {e}")

    def _daily_scan_job(self):
        """Günlük artımlı tarama görevi."""
        logger.info("Günlük tarama görevi başlıyor...")
        try:
            from agents.literature_scout import LiteratureScout
            import yaml
            
            config_path = self.project_root / "config.yaml"
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            
            scout = LiteratureScout(config, self.project_root)
            new_results = scout.run_incremental()
            logger.info(f"Günlük tarama: {len(new_results)} yeni sonuç")
        except Exception as e:
            logger.error(f"Günlük tarama hatası: {e}")

    def _github_sync_job(self):
        """GitHub'a push görevi."""
        logger.info("GitHub sync görevi başlıyor...")
        try:
            from automation.github_sync import GitHubSync
            sync = GitHubSync(self.config, self.project_root)
            sync.commit_and_push("Haftalık otomatik güncelleme")
            logger.info("GitHub sync tamamlandı")
        except Exception as e:
            logger.error(f"GitHub sync hatası: {e}")


if __name__ == "__main__":
    import yaml
    
    project_root = Path(__file__).parent.parent
    config_path = project_root / "config.yaml"
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    scheduler = ResearchScheduler(config, project_root)
    scheduler.run()
