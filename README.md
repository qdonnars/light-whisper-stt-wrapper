# Whisper STT

Lightweight push-to-talk speech-to-text for Windows. No cloud, no bloat — just hold a hotkey and talk. Runs entirely on your machine via [whisper.cpp](https://github.com/ggerganov/whisper.cpp) with Vulkan GPU acceleration.

Most speech-to-text tools are heavy, cloud-dependent, or come bundled with features you don't need. Whisper STT is a single Python script that sits in your system tray and does one thing well: transcribe your voice when you press a key.

## Why this exists

Most local speech-to-text solutions come with significant overhead — even when using the same model:

| Stack | Runtime overhead | Requires | Notes |
|-------|-----------------|----------|-------|
| OpenAI Whisper (PyTorch) | ~300 MB (Python + PyTorch) | CUDA, ffmpeg | Full ML framework loaded at all times |
| faster-whisper (CTranslate2) | ~200 MB (Python + CT2) | CUDA | Faster, but still needs a GPU runtime |
| **Whisper STT (this project)** | **~30 MB (Python only)** | **Nothing extra** | **Direct DLL call via whisper.cpp** |

All three run the same Whisper models with comparable accuracy. The difference is the stack: Whisper STT calls whisper.cpp directly via ctypes — no PyTorch, no CUDA runtime, no heavy ML framework. Just a single Python script, a DLL, and a model file.

## Features

- **Push-to-talk** — hold a global hotkey (default `Win+Y`), speak, release to transcribe
- **Auto-paste** — transcription is copied to clipboard and pasted into the active window
- **System tray** — minimal UI with language selection, microphone picker, and prompt editing
- **Fully local** — no internet required, everything runs on your machine
- **Fast** — uses whisper.cpp with Vulkan GPU acceleration
- **Configurable** — language, hotkey, model, microphone, and transcription prompt via `config.yaml`

## Requirements

- Windows 10 or later
- Python 3.10+ and Git (must be pre-installed)
- **No admin rights needed** to install or run
- Works on any modern CPU — a dedicated GPU is not required

### Recommended specs

| Hardware | Minimum | Recommended |
|----------|---------|-------------|
| RAM | 8 GB | 16 GB |
| CPU | Any x86_64 | Intel Core Ultra / AMD Ryzen 7000+ |
| GPU | Not required | Any Vulkan-compatible (iGPU or dedicated) |
| Disk | 2 GB free | 2 GB free |

> **Laptop-friendly:** Runs well on corporate laptops (Dell Latitude, Lenovo ThinkPad, etc.) without a dedicated GPU. Transcription takes ~3-5s per sentence on CPU vs ~1s with Vulkan GPU acceleration.

### Alternative models

The default model (`large-v3-turbo`) offers the best accuracy-to-speed ratio. For lower-end machines, you can use a smaller model by changing the `model` path in `config.yaml`:

| Model | Size | RAM usage | Best for |
|-------|------|-----------|----------|
| `ggml-tiny.bin` | 75 MB | ~300 MB | Very low-end hardware, fast but less accurate |
| `ggml-small.bin` | 466 MB | ~600 MB | Lightweight machines, good accuracy |
| `ggml-medium.bin` | 1.5 GB | ~800 MB | Balanced accuracy and speed |
| `ggml-large-v3-turbo.bin` | 1.5 GB | ~1.5 GB | Best accuracy, fast (default) |

Download alternative models from [Hugging Face](https://huggingface.co/ggerganov/whisper.cpp/tree/main) and place them in the `whisper-cpp/` folder.

## Installation

1. **Clone the repository:**
   ```
   git clone https://github.com/qdonnars/light-whisper-stt-wrapper.git
   cd light-whisper-stt-wrapper
   ```

2. **Run the setup script** (downloads the model and whisper.cpp binaries):
   ```
   python setup.py
   ```
   This downloads:
   - whisper.cpp pre-built binaries (~50 MB)
   - The `ggml-large-v3-turbo` model (~1.5 GB)

3. **Create a virtual environment and install dependencies:**
   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

4. **Edit `config.yaml`** if you want to change the hotkey, language, or microphone.

### Vulkan GPU acceleration (optional)

The setup script downloads CPU-based binaries. For Vulkan GPU acceleration:

1. Install the [Vulkan SDK](https://vulkan.lunarg.com/)
2. Build whisper.cpp with Vulkan support:
   ```
   git clone https://github.com/ggerganov/whisper.cpp
   cd whisper.cpp
   cmake -B build -DGGML_VULKAN=ON
   cmake --build build --config Release
   ```
3. Copy the resulting DLLs (`whisper.dll`, `ggml.dll`, `ggml-vulkan.dll`, etc.) into the `whisper-cpp/` folder, replacing the existing ones.

## Usage

**Run from terminal:**
```
python whisper_stt.py
```

**Run silently in the background:**
Double-click `launch.vbs` — the app starts hidden with no console window.

**Default hotkey:** Hold `Win+Y` to record, release to transcribe. The transcription is automatically copied to your clipboard and pasted.

### System tray menu

Right-click the tray icon to:
- Switch language (auto, English, French, etc.)
- Select a microphone
- Edit the transcription prompt (useful for jargon or proper nouns)
- Quit

### Configuration

All settings are in `config.yaml`:

| Key | Default | Description |
|-----|---------|-------------|
| `language` | `auto` | Transcription language (`auto`, `fr`, `en`, etc.) |
| `prompt` | `""` | Prompt to guide transcription (jargon, proper nouns) |
| `hotkey` | `win+y` | Push-to-talk hotkey |
| `model` | `whisper-cpp/ggml-large-v3-turbo.bin` | Path to the GGML model |
| `microphone` | `null` | Microphone device index (`null` = system default) |
| `auto_paste` | `true` | Automatically paste transcription into active window |

## License

[MIT](LICENSE)
