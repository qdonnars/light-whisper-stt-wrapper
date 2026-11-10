# Whisper STT

[![CI](https://github.com/qdonnars/light-whisper-stt-wrapper/actions/workflows/ci.yml/badge.svg)](https://github.com/qdonnars/light-whisper-stt-wrapper/actions/workflows/ci.yml)

Lightweight push-to-talk speech-to-text for Windows. No cloud, no bloat: hold a hotkey, talk, release. Everything runs on your machine via [whisper.cpp](https://github.com/ggerganov/whisper.cpp) with optional Vulkan GPU acceleration.

Most speech-to-text tools are heavy, cloud-dependent, or bundled with features you don't need. Whisper STT is a single Python script that sits in your system tray and does one thing well: transcribe your voice when you press a key.

## Why this exists

Most local speech-to-text solutions carry significant overhead, even when they run the same model:

| Stack | What you install, besides the model | GPU acceleration |
|-------|-------------------------------------|------------------|
| OpenAI Whisper (PyTorch) | Python, PyTorch, ffmpeg. Several GB with the CUDA build | NVIDIA only (CUDA) |
| faster-whisper (CTranslate2) | Python, CTranslate2, plus the cuDNN and cuBLAS libraries for GPU | NVIDIA only (CUDA) |
| **Whisper STT (this project)** | **About 100 MB: the app and the whisper.cpp DLLs** | **Any Vulkan GPU: NVIDIA, AMD, Intel, integrated** |

All three run the same Whisper models with comparable accuracy. The difference is the stack. Whisper STT calls whisper.cpp directly via ctypes: no PyTorch, no CUDA runtime, no heavy ML framework. Just a Python script, a DLL, and a model file.

The model itself is the heavy part, whatever the stack: `large-v3-turbo` is 1.6 GB on disk and about 1.8 GB of VRAM once loaded (of RAM, without a GPU). So the app does not hold on to it. After five minutes without a dictation the model is unloaded and that memory goes back to whatever needs it, a game for instance; it loads again while you speak your next take, in a little over a second on a GPU. Measured on an RTX 5090: about 180 MB of RAM with the model loaded, about 100 MB once it is unloaded.

## Features

- **Push-to-talk:** hold a global hotkey (default `Win+Y`), speak, release to transcribe
- **Clipboard-first:** the transcription always lands on the clipboard and in the `Win+V` history. Auto-paste (Ctrl+V injection) is opt-in
- **System tray:** minimal UI with prompt editing, an auto-paste toggle, and the settings. While you hold the hotkey the icon is a red ring with a green core that grows with your voice, so a muted microphone shows before the take is over, not after
- **Out of the way:** a setup dialog at the first launch, then nothing. It can start with Windows, and the settings stay one click away in the tray menu
- **Fully local:** no internet required, nothing leaves your machine
- **Fast:** whisper.cpp with Vulkan GPU acceleration when available, CPU otherwise
- **Light when idle:** the model is unloaded after a few minutes without dictation and its VRAM is given back; it reloads on the next hotkey press
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

> **Checking what you downloaded:** every release note lists the SHA256 of its zip. Since the executable is not signed, this is the way to confirm you got the file that was published. Compare it before extracting:
> ```
> certutil -hashfile whisper-stt-v1.3.0-win-x64.zip SHA256
> ```

## Installation (from source)

Requires Python 3.10+ and Git.

1. **Clone the repository:**
   ```
   git clone https://github.com/qdonnars/light-whisper-stt-wrapper.git
   cd light-whisper-stt-wrapper
   ```

2. **Run the bootstrap script.** It downloads the whisper.cpp pre-built binaries and the `ggml-large-v3-turbo` model (~1.5 GB), and checks both against a known SHA256 before using them:
   ```
   python bootstrap.py
   ```

3. **Create a virtual environment and install dependencies:**
   ```
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

4. **Edit `config.yaml`** to change the hotkey or the language. The microphone needs no setup.

### Vulkan GPU acceleration (optional)

The bootstrap script downloads CPU-based binaries. For Vulkan GPU acceleration:

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

1. Activate the virtual environment and install the development extras, which is where PyInstaller lives:
   ```
   .venv\Scripts\activate
   pip install -r requirements-dev.txt
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

- Edit the transcription prompt, useful for jargon and proper nouns
- Toggle auto-paste (off by default)
- Open the settings shown at the first launch: hotkey (click it, then press the keys), the languages you dictate in, whether dictations are kept in the log, and whether the app starts with Windows
- Quit

The icon tells you what the app is doing: blue when idle, a red ring while recording (with a green core that follows your voice), orange while transcribing, and grey when the last take produced nothing.

### Configuration

All settings live in `config.yaml`:

| Key | Default | Description |
|-----|---------|-------------|
| `language` | `auto` | `auto`, or one Whisper code to force that language. Ticking a single language in the settings does the same |
| `auto_languages` | `[]` | Languages `auto` may choose from, e.g. `[fr, en]`. Ticked in the settings dialog; any other Whisper code can be added here. Empty means any language, which misfires on short takes |
| `prompt` | `""` | Prompt to guide transcription (jargon, proper nouns). Write it the way you speak, with the misheard words used in a sentence |
| `hotkey` | `win+y` | Push-to-talk hotkey |
| `model` | `whisper-cpp/ggml-large-v3-turbo.bin` | Path to the GGML model |
| `microphone` | `null` | Leave as `null` to follow the Windows default. To pin a device, give its **name**, never an index: PortAudio indices shift when devices sleep or reconnect |
| `auto_paste` | `false` | Inject Ctrl+V after copying. Off by default, so the text simply waits on the clipboard |
| `unload_after_minutes` | `5` | Minutes without a dictation before the model is unloaded and its memory released. It reloads on the next hotkey press. `0` keeps it loaded; anything under a minute counts as one |
| `gpu_device` | `null` | Which GPU runs the model. `null` picks a dedicated card over an integrated one. A number forces one of the GPUs listed in the log at startup |
| `log_transcriptions` | `true` | Write what you dictate to `whisper_stt.log`. Set to `false`, or untick the box at startup, to keep only timings and diagnostics there |

## Troubleshooting

The app writes everything it does to `whisper_stt.log`, next to the executable or the script. Start there.

- **Silent recordings:** check that the Windows default input is a real microphone and not a virtual device (Steam Streaming, OBS, VB-Cable). The app already skips known virtual mics, but an aggressive noise gate on the headset can also produce silence.
- **The hotkey does nothing:** another application may already own `Win+Y`. Pick another one from **Settings** in the tray menu. Note that `Win+H` is reserved by Windows dictation.
- **The ring stays empty while you speak:** no sound is reaching the app. The take will not be transcribed; check the microphone mute and any noise gate.
- **Transcription takes tens of seconds:** check the `Model loaded on ...` line in the log. On a machine with an integrated chip and a graphics card, the model must be on the card; the app chooses it, and `gpu_device` in `config.yaml` forces it.
- **No GPU acceleration:** the binaries downloaded by `bootstrap.py` are CPU-only. Follow the Vulkan section above to get GPU support.

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
