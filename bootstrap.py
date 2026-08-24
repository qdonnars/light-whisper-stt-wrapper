"""
Whisper STT: first-time asset download.

Fetches the whisper.cpp binaries and the speech-to-text model so the
application is ready to run.  Re-run at any time to update or repair.

This is not a packaging script.  It used to be called setup.py, which is the
name Python tooling reserves for building distributions, and some of that
tooling will happily run it on its own.

Author:  Quentin Donnars <https://github.com/qdonnars>
License: MIT
"""

import hashlib
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
#
# x64, not Win32.  Win32 is the 32-bit artifact: a 64-bit Python loading those
# DLLs dies with "OSError: [WinError 193] is not a valid Win32 application",
# and whisper_stt.py mirrors the parameter struct with 8-byte pointers, so
# 32-bit could never have worked anyway.  This went unnoticed for a while
# because the development machine uses hand-built Vulkan DLLs that shadow
# these.
#
# For Vulkan GPU acceleration you compile whisper.cpp yourself; see the README.
# Keep this tag in step with EXPECTED_WHISPER_CPP_TAG in whisper_stt.py, which
# mirrors this release's whisper_full_params layout.
WHISPER_CPP_TAG = "v1.8.3"
WHISPER_CPP_ZIP = (
    f"https://github.com/ggml-org/whisper.cpp/releases/download/"
    f"{WHISPER_CPP_TAG}/whisper-blas-bin-x64.zip"
)
# Recorded 2026-08-24 from the release asset above.  Bumping WHISPER_CPP_TAG
# means recomputing this: certutil -hashfile <file> SHA256
WHISPER_CPP_SHA256 = "2c9e6b95d9b679120553631d07b97d4bb1a56668a592052838dc9e7e24769c04"

# GGML model hosted on Hugging Face.  The repository moved from ggerganov to
# ggml-org; the old name still redirects, but pointing at the real one means
# one less thing that can break quietly.
MODEL_REPO = "ggml-org/whisper.cpp"
MODEL_FILE = "ggml-large-v3-turbo.bin"
MODEL_URL = (
    f"https://huggingface.co/{MODEL_REPO}/resolve/main/{MODEL_FILE}"
)
MODEL_SHA256 = "1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69"


class IntegrityError(RuntimeError):
    """A download did not match its expected SHA256."""


def _require_64bit_python() -> None:
    """Refuse to fetch 64-bit DLLs for an interpreter that cannot load them."""
    if sys.maxsize <= 2**32:
        sys.exit(
            "[ERROR] This is a 32-bit Python. Whisper STT needs 64-bit Python:\n"
            "        the whisper.cpp binaries and the ctypes struct layout it\n"
            "        uses are both x86_64. Install 64-bit Python and re-run."
        )


def _download(url: str, dest: Path, label: str) -> str:
    """Download *url* to *dest*, returning the SHA256 of what arrived.

    Hashing as the bytes go by avoids reading a 1.5 GB file back off disk
    just to check it.
    """
    print(f"  Downloading {label} ...")
    digest = hashlib.sha256()
    req = urllib.request.Request(url, headers={"User-Agent": "whisper-stt-bootstrap"})
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
                digest.update(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded * 100 // total
                    print(f"\r  {pct:3d}% ({downloaded >> 20} / {total >> 20} MB)",
                          end="", flush=True)
        print()
    return digest.hexdigest()


def _verify(actual: str, expected: str, dest: Path, label: str) -> None:
    """Delete *dest* and raise unless the digests match.

    These are DLLs loaded straight into the process and a model the app
    trusts.  "Nothing leaves your machine" is only half the promise; the other
    half is knowing what came onto it.
    """
    if actual == expected:
        print(f"  SHA256 verified: {actual}")
        return
    dest.unlink(missing_ok=True)
    raise IntegrityError(
        f"{label} does not match its expected checksum, so it was deleted.\n"
        f"        expected {expected}\n"
        f"        actual   {actual}\n"
        "        Either the download was corrupted, or the upstream file was\n"
        "        replaced. If you trust the new file, update the constant in\n"
        "        bootstrap.py."
    )


def download_binaries() -> None:
    """Download and extract whisper.cpp Windows binaries."""
    # Bail out if anything is already there. This is what protects a hand-built
    # Vulkan whisper.cpp: those DLLs are the whole point of the GPU path and
    # must never be replaced by the CPU build from a plain re-run.
    if WHISPER_DIR.exists() and (WHISPER_DIR / "whisper.dll").exists():
        print("[OK] whisper-cpp binaries already present, skipping.")
        print("     Delete whisper-cpp/whisper.dll first if you want the CPU")
        print("     build back; a hand-built Vulkan one is kept as is.")
        return

    WHISPER_DIR.mkdir(exist_ok=True)
    zip_path = BASE_DIR / "_whisper_bin.zip"

    try:
        actual = _download(WHISPER_CPP_ZIP, zip_path, "whisper.cpp binaries")
        _verify(actual, WHISPER_CPP_SHA256, zip_path, "The whisper.cpp binaries archive")
        print("  Extracting ...")
        with zipfile.ZipFile(zip_path) as zf:
            for member in zf.infolist():
                # Flatten to the basename: this also defuses zip-slip, since a
                # member named ../../evil.dll cannot escape whisper-cpp/.
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
        print(f"[OK] Model {MODEL_FILE} already present, skipping.")
        return

    WHISPER_DIR.mkdir(exist_ok=True)
    print(f"  Model: {MODEL_FILE} (~1.5 GB)")
    # Download to a .part file and only rename once the hash checks out.  An
    # interrupted download used to leave a truncated model in place, which
    # every later run then skipped as "already present".
    part_path = model_path.with_suffix(model_path.suffix + ".part")
    try:
        actual = _download(MODEL_URL, part_path, MODEL_FILE)
        _verify(actual, MODEL_SHA256, part_path, f"The model {MODEL_FILE}")
        part_path.replace(model_path)
    finally:
        part_path.unlink(missing_ok=True)
    print(f"[OK] Model saved to whisper-cpp/{MODEL_FILE}")


def create_config() -> None:
    """Copy config.example.yaml → config.yaml if it doesn't exist yet."""
    if CONFIG_PATH.exists():
        print("[OK] config.yaml already exists, skipping.")
        return
    if CONFIG_EXAMPLE.exists():
        shutil.copy2(CONFIG_EXAMPLE, CONFIG_PATH)
        print("[OK] Created config.yaml from config.example.yaml")
    else:
        print("[WARN] config.example.yaml not found, skipping config creation.")


def main() -> None:
    print("=" * 60)
    print("  Whisper STT Setup")
    print("=" * 60)
    print()

    _require_64bit_python()

    try:
        download_binaries()
        print()
        download_model()
    except IntegrityError as e:
        sys.exit(f"[ERROR] {e}")
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
