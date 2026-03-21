"""
Build whisper_stt.exe using PyInstaller.

Usage:
    python build.py

Output:
    dist/whisper_stt/              — ready-to-distribute folder
      whisper_stt.exe
      whisper-cpp/                 — DLLs + model (user adds model)
      config.example.yaml
      _internal/                   — Python runtime (auto-generated)
"""

import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
DIST = BASE / "dist" / "whisper_stt"
WHISPER_CPP_SRC = BASE / "whisper-cpp"


def main():
    # 1. Run PyInstaller
    print("Building with PyInstaller...")
    subprocess.check_call([
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        str(BASE / "whisper_stt.spec"),
    ])

    # 2. Copy whisper-cpp DLLs (not model — too large) next to exe
    dst_wc = DIST / "whisper-cpp"
    dst_wc.mkdir(exist_ok=True)
    for dll in WHISPER_CPP_SRC.glob("*.dll"):
        shutil.copy2(dll, dst_wc / dll.name)
        print(f"  Copied {dll.name}")

    # 3. Copy config example
    shutil.copy2(BASE / "config.example.yaml", DIST / "config.example.yaml")

    # 4. Copy model if present (optional — large file)
    for model in WHISPER_CPP_SRC.glob("*.bin"):
        dest = dst_wc / model.name
        if not dest.exists():
            print(f"  Copying model {model.name} (this may take a moment)...")
            shutil.copy2(model, dest)
        else:
            print(f"  Model {model.name} already present")

    print()
    print(f"Done! Output: dist/whisper_stt/")
    print()
    print("To distribute (without model):")
    print("  1. Zip dist/whisper_stt/ (excluding .bin files if too large)")
    print("  2. Users download the model separately via setup.py or Hugging Face")
    print("  3. Drop the .bin into whisper-cpp/ and run whisper_stt.exe")


if __name__ == "__main__":
    main()
