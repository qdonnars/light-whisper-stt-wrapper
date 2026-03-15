"""
Whisper STT — First-time setup script.

Downloads the whisper.cpp binaries and the speech-to-text model so the
application is ready to run.  Re-run at any time to update or repair.
"""

import io
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
WHISPER_DIR = BASE_DIR / "whisper-cpp"
CONFIG_PATH = BASE_DIR / "config.yaml"
CONFIG_EXAMPLE = BASE_DIR / "config.example.yaml"

# ─── Configurable URLs ───────────────────────────────────────────────────────

# whisper.cpp pre-built Windows binaries (CPU + OpenBLAS).
# For Vulkan GPU acceleration you need to compile whisper.cpp yourself — see
# the README for instructions.
WHISPER_CPP_TAG = "v1.8.3"
WHISPER_CPP_ZIP = (
    f"https://github.com/ggml-org/whisper.cpp/releases/download/"
    f"{WHISPER_CPP_TAG}/whisper-blas-bin-Win32.zip"
)

# GGML model hosted on Hugging Face.
MODEL_REPO = "ggerganov/whisper.cpp"
MODEL_FILE = "ggml-large-v3-turbo.bin"
MODEL_URL = (
    f"https://huggingface.co/{MODEL_REPO}/resolve/main/{MODEL_FILE}"
)


def _download(url: str, dest: Path, label: str) -> None:
    """Download *url* to *dest* with a simple progress indicator."""
    print(f"  Downloading {label} …")
    req = urllib.request.Request(url, headers={"User-Agent": "whisper-stt-setup"})
    with urllib.request.urlopen(req) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        chunk_size = 1 << 20  # 1 MB
        with open(dest, "wb") as f:
            while True:
                chunk = resp.read(chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded * 100 // total
                    print(f"\r  {pct:3d}% ({downloaded >> 20} / {total >> 20} MB)", end="", flush=True)
        print()


def download_binaries() -> None:
    """Download and extract whisper.cpp Windows binaries."""
    if WHISPER_DIR.exists() and (WHISPER_DIR / "whisper.dll").exists():
        print("[OK] whisper-cpp binaries already present — skipping.")
        return

    WHISPER_DIR.mkdir(exist_ok=True)
    zip_path = BASE_DIR / "_whisper_bin.zip"

    try:
        _download(WHISPER_CPP_ZIP, zip_path, "whisper.cpp binaries")
        print("  Extracting …")
        with zipfile.ZipFile(zip_path) as zf:
            for member in zf.infolist():
                # Flatten: extract files directly into whisper-cpp/
                filename = Path(member.filename).name
                if not filename or member.is_dir():
                    continue
                dest = WHISPER_DIR / filename
                with zf.open(member) as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)
        print("[OK] Binaries extracted to whisper-cpp/")
    finally:
        zip_path.unlink(missing_ok=True)


def download_model() -> None:
    """Download the GGML model file."""
    model_path = WHISPER_DIR / MODEL_FILE
    if model_path.exists():
        print(f"[OK] Model {MODEL_FILE} already present — skipping.")
        return

    WHISPER_DIR.mkdir(exist_ok=True)
    print(f"  Model: {MODEL_FILE} (~1.5 GB)")
    _download(MODEL_URL, model_path, MODEL_FILE)
    print(f"[OK] Model saved to whisper-cpp/{MODEL_FILE}")


def create_config() -> None:
    """Copy config.example.yaml → config.yaml if it doesn't exist yet."""
    if CONFIG_PATH.exists():
        print("[OK] config.yaml already exists — skipping.")
        return
    if CONFIG_EXAMPLE.exists():
        shutil.copy2(CONFIG_EXAMPLE, CONFIG_PATH)
        print("[OK] Created config.yaml from config.example.yaml")
    else:
        print("[WARN] config.example.yaml not found — skipping config creation.")


def main() -> None:
    print("=" * 60)
    print("  Whisper STT — Setup")
    print("=" * 60)
    print()

    download_binaries()
    print()
    download_model()
    print()
    create_config()

    print()
    print("=" * 60)
    print("  Setup complete!")
    print()
    print("  Next steps:")
    print("    1. Create a virtual environment:  python -m venv .venv")
    print("    2. Activate it:                   .venv\\Scripts\\activate")
    print("    3. Install dependencies:          pip install -r requirements.txt")
    print("    4. Edit config.yaml if needed")
    print("    5. Run:                           python whisper_stt.py")
    print("       Or double-click launch.vbs for silent background mode.")
    print("=" * 60)


if __name__ == "__main__":
    main()
