"""
Embedding model ağırlıklarını HF Hub'dan indirip models/ klasörüne kaydeder.

Kullanım:
    python download_model.py

Proje ilk kurulumunda bir kez çalıştır. Sonraki çalışmalarda
sentence-transformers otomatik olarak bu klasörü kullanır (HF Hub'a bağlanmaz).
"""

from pathlib import Path
import shutil

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
DEST = Path(__file__).parent / "models" / "all-MiniLM-L6-v2"


def main():
    if DEST.exists() and any(DEST.iterdir()):
        print(f"Model zaten mevcut: {DEST}")
        return

    print(f"Model indiriliyor: {MODEL_NAME} → {DEST}")
    from sentence_transformers import SentenceTransformer

    # HF Hub'dan indir (cache'e kaydeder)
    model = SentenceTransformer(MODEL_NAME)

    # Cache içindeki snapshot'ı bul ve kopyala
    cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
    cache_model_dir = cache_dir / "models--sentence-transformers--all-MiniLM-L6-v2" / "snapshots"

    if cache_model_dir.exists():
        snap = sorted(cache_model_dir.iterdir())[0]
        DEST.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(snap, DEST, symlinks=False)
        size_mb = sum(f.stat().st_size for f in DEST.rglob("*") if f.is_file()) / 1024 / 1024
        print(f"Kopyalandı: {DEST}  ({size_mb:.1f} MB)")
    else:
        # ST varsayılan cache kullanılmış, model path'i direkt al
        import os
        model_path = model._model_card_data.get("base_model") if hasattr(model, "_model_card_data") else None
        print(f"Model hazır (sentence-transformers cache: {model_path or 'bilinmiyor'})")
        print("Not: models/ klasörüne kopyalanamadı, HF cache kullanılıyor.")


if __name__ == "__main__":
    main()
