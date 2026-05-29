"""
API anahtarı yönetimi — .env dosyasını okur/yazar.

Proje ilk çalıştırıldığında .env olmayabilir. Bu modül UI'daki ayar
popup'ından gelen anahtarları doğru değişken isimleriyle .env dosyasına
yazar ve aynı zamanda mevcut process'in ortam değişkenlerini günceller
(böylece kullanıcı yeniden başlatmadan keyleri kullanabilir).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, List

from loguru import logger

# Proje kökü: src/config/api_keys.py → parents[2]
ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT / ".env"


# Popup'ta ve sidebar'da gösterilecek anahtar tanımları.
# `help` alanı sonra detaylandırılacak ("nasıl bulurum?" rehberi).
API_KEYS: List[Dict[str, str]] = [
    {
        "env": "GEMINI_API_KEY",
        "label": "Gemini API Key",
        "required": True,
        "placeholder": "AIza...",
        "help_url": "https://aistudio.google.com/app/apikey",
        "help": (
            "Google AI Studio'ya gir → **Get API key** → **Create API key**. "
            "Oluşan `AIza...` ile başlayan anahtarı buraya yapıştır. "
            "(Detaylı anlatım sonra eklenecek.)"
        ),
    },
    {
        "env": "ZOTERO_API_KEY",
        "label": "Zotero API Key",
        "required": False,
        "placeholder": "Zotero kütüphanesi kullanacaksan",
        "help_url": "https://www.zotero.org/settings/keys",
        "help": (
            "zotero.org/settings/keys → **Create new private key** → "
            "okuma (read) izni yeterli. Üretilen anahtarı buraya yapıştır. "
            "(Detaylı anlatım sonra eklenecek.)"
        ),
    },
    {
        "env": "ZOTERO_USER_ID",
        "label": "Zotero User ID",
        "required": False,
        "placeholder": "Sadece rakamlardan oluşur",
        "help_url": "https://www.zotero.org/settings/keys",
        "help": (
            "zotero.org/settings/keys sayfasında "
            "**\"Your userID for use in API calls is: <ID>\"** satırındaki sayı. "
            "(Detaylı anlatım sonra eklenecek.)"
        ),
    },
    {
        "env": "SCOPUS_API_KEY",
        "label": "Scopus API Key",
        "required": False,
        "placeholder": "Scopus araması kullanacaksan",
        "help_url": "https://dev.elsevier.com/apikey/manage",
        "help": (
            "dev.elsevier.com → **I want an API Key** → kurumsal ağdan kayıt ol → "
            "API key oluştur. (Detaylı anlatım sonra eklenecek.)"
        ),
    },
]

REQUIRED_KEYS = [k["env"] for k in API_KEYS if k.get("required")]


def get_value(env_name: str) -> str:
    """Mevcut ortam değişkeni değerini döndürür (process içi)."""
    return os.getenv(env_name, "") or ""


def is_configured(env_name: str) -> bool:
    return bool(get_value(env_name).strip())


def mask_value(value: str) -> str:
    """Anahtarı tam göstermeden maskeler: '••••••••1c3d'."""
    value = (value or "").strip()
    if not value:
        return ""
    if len(value) <= 4:
        return "•" * len(value)
    return "•" * 8 + value[-4:]


def needs_setup() -> bool:
    """Zorunlu anahtarlardan en az biri eksikse True (ilk açılış popup'ı için)."""
    return any(not is_configured(env) for env in REQUIRED_KEYS)


def _parse_env_lines(path: Path) -> List[str]:
    if not path.exists():
        return []
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except Exception as exc:  # pragma: no cover
        logger.warning(f".env okunamadı: {exc}")
        return []


def save_keys(updates: Dict[str, str], deletes: List[str] | None = None) -> Path:
    """
    Anahtarları .env dosyasına yazar (varsa mevcut satırları korur),
    ve process ortam değişkenlerini günceller.

    updates: {ENV_NAME: value}  — boş/None değerler atlanır
    deletes: [ENV_NAME, ...]    — .env'den ve ortamdan kaldırılır

    Bilinen API_KEYS dışındaki satırlar (SERPAPI_KEY, yorumlar vb.) korunur.
    """
    deletes = deletes or []

    def _clean_value(key: str, raw: str) -> str:
        """Kullanıcı 'KEY=value' formatında yapıştırmışsa KEY= kısmını soy."""
        v = (raw or "").strip()
        if "=" in v:
            prefix, rest = v.split("=", 1)
            if re.match(r"^[A-Z][A-Z0-9_]*$", prefix.strip()):
                v = rest.strip()
        return v

    updates = {
        k: _clean_value(k, v)
        for k, v in (updates or {}).items()
        if _clean_value(k, v)
    }

    lines = _parse_env_lines(ENV_PATH)
    handled: set[str] = set()
    new_lines: List[str] = []

    for line in lines:
        stripped = line.strip()
        # Yorum veya boş satır → koru
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            new_lines.append(line)
            continue

        key = stripped.split("=", 1)[0].strip()

        if key in deletes:
            handled.add(key)
            continue  # satırı düş
        if key in updates:
            new_lines.append(f"{key}={updates[key]}")
            handled.add(key)
            continue

        new_lines.append(line)

    # Dosyada henüz bulunmayan yeni anahtarları sona ekle
    appended = [k for k in updates if k not in handled]
    if appended:
        if new_lines and new_lines[-1].strip():
            new_lines.append("")
        for k in appended:
            new_lines.append(f"{k}={updates[k]}")

    content = "\n".join(new_lines).rstrip("\n") + "\n"
    ENV_PATH.write_text(content, encoding="utf-8")

    # Process ortamını da güncelle (anında etki)
    for k, v in updates.items():
        os.environ[k] = v
    for k in deletes:
        os.environ.pop(k, None)

    logger.info(
        f".env güncellendi → {ENV_PATH} "
        f"(güncellenen: {list(updates.keys())}, silinen: {deletes})"
    )
    return ENV_PATH
