# Whisper STT

Lightweight push-to-talk speech-to-text for Windows. No cloud, no bloat: hold a hotkey, talk, release. Everything runs on your machine via [whisper.cpp](https://github.com/ggerganov/whisper.cpp) with optional Vulkan GPU acceleration.

Most speech-to-text tools are heavy, cloud-dependent, or bundled with features you don't need. Whisper STT is a single Python script that sits in your system tray and does one thing well: transcribe your voice when you press a key.

## Why this exists

Most local speech-to-text solutions carry significant overhead, even when they run the same model:

| Stack | Runtime overhead | Requires | Notes |
|-------|-----------------|----------|-------|
| OpenAI Whisper (PyTorch) | ~300 MB (Python + PyTorch) | CUDA, ffmpeg | Full ML framework loaded at all times |
| faster-whisper (CTranslate2) | ~200 MB (Python + CT2) | CUDA | Faster, but still needs a GPU runtime |
| **Whisper STT (this project)** | **~30 MB (Python only)** | **Nothing extra** | **Direct DLL call via whisper.cpp** |

All three run the same Whisper models with comparable accuracy. The difference is the stack. Whisper STT calls whisper.cpp directly via ctypes: no PyTorch, no CUDA runtime, no heavy ML framework. Just a Python script, a DLL, and a model file.

## Features

- **Push-to-talk:** hold a global hotkey (default `Win+Y`), speak, release to transcribe
- **Clipboard-first:** the transcription always lands on the clipboard and in the `Win+V` history. Auto-paste (Ctrl+V injection) is opt-in
- **System tray:** minimal UI with language selection, prompt editing, and an auto-paste toggle
- **Fully local:** no internet required, nothing leaves your machine
- **Fast:** whisper.cpp with Vulkan GPU acceleration when available, CPU otherwise
- **Zero microphone setup:** the app follows the Windows default input, resolves it to its WASAPI endpoint, opens it at the device's native sample rate, and skips virtual microphones
- **Configurable:** language, hotkey, model, and transcription prompt via `config.yaml`

## Requirements

- Windows 10 or later
- **No admin rights** needed to install or run the standalone build
- Python 3.10+ and Git only if you run from source
- Works on any modern CPU. A dedicated GPU is optional

### Recommended specs

| Hardware | Minimum | Recommended |
|----------|---------|-------------|
| RAM | 8 GB | 16 GB |
| CPU | Any x86_64 | Intel Core Ultra / AMD Ryzen 7000+ |
| GPU | Not required | Any Vulkan-compatible (iGPU or dedicated) |
| Disk | 2 GB free | 2 GB free |

> **Laptop-friendly:** runs well on corporate laptops (Dell Latitude, Lenovo ThinkPad, and similar) without a dedicated GPU. Expect roughly 3 to 5 seconds per sentence on CPU, against about 1 second with Vulkan GPU acceleration.

### Alternative models

The default model (`large-v3-turbo`) offers the best accuracy-to-speed ratio. On lower-end machines, point the `model` key in `config.yaml` at a smaller file:

| Model | Size | RAM usage | Best for |
|-------|------|-----------|----------|
| `ggml-tiny.bin` | 75 MB | ~300 MB | Very low-end hardware, fast but less accurate |
| `ggml-small.bin` | 466 MB | ~600 MB | Lightweight machines, good accuracy |
| `ggml-medium.bin` | 1.5 GB | ~800 MB | Balanced accuracy and speed |
| `ggml-large-v3-turbo.bin` | 1.5 GB | ~1.5 GB | Best accuracy, fast (default) |

Download alternative models from [Hugging Face](https://huggingface.co/ggerganov/whisper.cpp/tree/main) and drop them in the `whisper-cpp/` folder.

## Installation (standalone .exe)

No Python needed. Download, extract, run.

1. **Download** the latest release `.zip` from the [Releases](https://github.com/qdonnars/light-whisper-stt-wrapper/releases) page.

2. **Extract** the zip into a folder of your choice (for example `C:\Tools\whisper-stt`). You should have:
   ```
   whisper-stt/
     whisper_stt.exe
     config.example.yaml
     _internal/            <- runtime files (do not modify)
     whisper-cpp/
       whisper.dll
       ggml.dll
       ggml-vulkan.dll
       ggml-large-v3-turbo.bin   <- model (~1.5 GB)
   ```

3. **Create your config:** copy `config.example.yaml` to `config.yaml` in the same folder.
   ```
   copy config.example.yaml config.yaml
   ```

4. **Run** `whisper_stt.exe`. An icon appears in the system tray and you are ready to go.

> **Windows SmartScreen:** on first launch, Windows may show a "Windows protected your PC" warning. Click **More info**, then **Run anyway**. The executable is not code-signed, which is what triggers the prompt.

## Installation (from source)

Requires Python 3.10+ and Git.

1. **Clone the repository:**
   ```
   git clone https://github.com/qdonnars/light-whisper-stt-wrapper.git
   cd light-whisper-stt-wrapper
   ```

2. **Run the setup script.** It downloads the whisper.cpp pre-built binaries (~50 MB) and the `ggml-large-v3-turbo` model (~1.5 GB):
   ```
   python setup.py
   ```

3. **Create a virtual environment and install dependencies:**
   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

4. **Edit `config.yaml`** to change the hotkey or the language. The microphone needs no setup.

### Vulkan GPU acceleration (optional)

The setup script downloads CPU-based binaries. For Vulkan GPU acceleration:

1. Install the [Vulkan SDK](https://vulkan.lunarg.com/).
2. Build whisper.cpp with Vulkan support:
   ```
   git clone https://github.com/ggerganov/whisper.cpp
   cd whisper.cpp
   cmake -B build -DGGML_VULKAN=ON
   cmake --build build --config Release
   ```
3. Copy the resulting DLLs (`whisper.dll`, `ggml.dll`, `ggml-vulkan.dll`, and the rest) into the `whisper-cpp/` folder, replacing the existing ones.

### Building the .exe yourself

1. Activate the virtual environment. PyInstaller is already listed in `requirements.txt`:
   ```
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Run the build script, which invokes PyInstaller and lays out the distribution folder:
   ```
   python build.py
   ```

   To drive PyInstaller directly instead, use the provided spec file and copy the extra files yourself:
   ```
   pyinstaller whisper_stt.spec
   copy config.example.yaml dist\whisper_stt\
   xcopy whisper-cpp dist\whisper_stt\whisper-cpp\ /E
   ```

3. Zip `dist/whisper_stt/` for distribution.

## Usage

**Standalone (.exe):** double-click `whisper_stt.exe`. The app starts in the system tray.

**From source:**
```
python whisper_stt.py
```

**Silently in the background (source only):** double-click `launch.vbs`. The app starts hidden, with no console window.

**Default hotkey:** hold `Win+Y` to record, release to transcribe. The text is copied to the clipboard, so paste it wherever you need it. Enable auto-paste in the tray menu if you want it injected into the active window instead.

### System tray menu

Right-click the tray icon to:

- Switch language (auto, English, French, and the rest of the Whisper set)
- Edit the transcription prompt, useful for jargon and proper nouns
- Toggle auto-paste (off by default)
- Quit

### Configuration

All settings live in `config.yaml`:

| Key | Default | Description |
|-----|---------|-------------|
| `language` | `auto` | Transcription language (`auto`, `fr`, `en`, and so on) |
| `prompt` | `""` | Prompt to guide transcription (jargon, proper nouns) |
| `hotkey` | `win+y` | Push-to-talk hotkey |
| `model` | `whisper-cpp/ggml-large-v3-turbo.bin` | Path to the GGML model |
| `microphone` | `null` | Leave as `null` to follow the Windows default. To pin a device, give its **name**, never an index: PortAudio indices shift when devices sleep or reconnect |
| `auto_paste` | `false` | Inject Ctrl+V after copying. Off by default, so the text simply waits on the clipboard |

## Troubleshooting

The app writes everything it does to `whisper_stt.log`, next to the executable or the script. Start there.

- **Silent recordings:** check that the Windows default input is a real microphone and not a virtual device (Steam Streaming, OBS, VB-Cable). The app already skips known virtual mics, but an aggressive noise gate on the headset can also produce silence.
- **The hotkey does nothing:** another application may already own `Win+Y`. Change `hotkey` in `config.yaml`. Note that `Win+H` is reserved by Windows dictation.
- **No GPU acceleration:** the binaries downloaded by `setup.py` are CPU-only. Follow the Vulkan section above to get GPU support.

## Author

Built by **Quentin Donnars** ([@qdonnars](https://github.com/qdonnars)).

Standing on the shoulders of [whisper.cpp](https://github.com/ggerganov/whisper.cpp) by Georgi Gerganov and the OpenAI Whisper models.

## Contributing

`main` holds released, stable code. Day-to-day work lands on `dev` first, so please open pull requests against `dev`.

Read [CONTRIBUTING.md](CONTRIBUTING.md) first. It covers the branch model, how to
set up a source checkout, what to test by hand before opening a pull request, and
the handful of Windows audio traps that have already caused bugs here.

Released versions and what changed in each are listed in [CHANGELOG.md](CHANGELOG.md).
Ideas and known rough edges live in [docs/ROADMAP.md](docs/ROADMAP.md).

## License

[MIT](LICENSE), (c) 2026 Quentin Donnars
