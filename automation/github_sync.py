"""
GitHub Sync - Git otomasyonu.
Araştırma sonuçlarını otomatik olarak GitHub'a commit ve push eder.
"""

import subprocess
from datetime import datetime
from pathlib import Path
from loguru import logger


class GitHubSync:
    """Git commit ve push otomasyonu."""

    def __init__(self, config: dict, project_root: Path):
        self.config = config
        self.project_root = project_root
        self.github_config = config.get("github", {})
        self.repo_name = self.github_config.get("repo_name", "oto-research-multi-agent-ev-charging")
        self.commit_prefix = self.github_config.get("commit_prefix", "[research-agent]")

    def init_repo(self):
        """Git repo'yu başlat ve remote ekle."""
        try:
            self._run_git("init")
            self._run_git("remote", "add", "origin",
                         f"https://github.com/moltyraspi/{self.repo_name}.git")
            logger.info(f"Git repo başlatıldı: {self.repo_name}")
        except Exception as e:
            if "already exists" in str(e):
                logger.info("Git repo zaten mevcut")
            else:
                logger.error(f"Git init hatası: {e}")

    def commit_and_push(self, message: str = ""):
        """Değişiklikleri commit et ve push yap."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        
        if not message:
            message = f"Araştırma güncelleme — {timestamp}"
        
        full_message = f"{self.commit_prefix} {message}"
        
        try:
            # Stage all changes
            self._run_git("add", "-A")
            
            # Değişiklik var mı kontrol et
            result = self._run_git("status", "--porcelain")
            if not result.strip():
                logger.info("Commit edilecek değişiklik yok")
                return False
            
            # Commit
            self._run_git("commit", "-m", full_message)
            logger.info(f"Commit yapıldı: {full_message}")
            
            # Push
            self._run_git("push", "-u", "origin", "main")
            logger.info("Push başarılı")
            return True
            
        except Exception as e:
            logger.error(f"Git commit/push hatası: {e}")
            return False

    def create_branch(self, branch_name: str):
        """Yeni branch oluştur."""
        try:
            self._run_git("checkout", "-b", branch_name)
            logger.info(f"Branch oluşturuldu: {branch_name}")
        except Exception as e:
            logger.error(f"Branch oluşturma hatası: {e}")

    def _run_git(self, *args) -> str:
        """Git komutunu çalıştır."""
        cmd = ["git", *args]
        result = subprocess.run(
            cmd,
            cwd=str(self.project_root),
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Git hatası: {result.stderr.strip()}")
        return result.stdout
