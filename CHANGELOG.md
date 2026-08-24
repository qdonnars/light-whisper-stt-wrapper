# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

## [1.3.0] - 2026-08-24

### Fixed

- The transcription prompt now reaches whisper.cpp. Parameters were written into
  `whisper_full_params` at two hardcoded byte offsets, and one of them was
  wrong: the prompt pointer went to offset 80, which is `carry_initial_prompt`,
  not `initial_prompt` at 72. Every prompt set from the tray menu was written
  into a bool and its padding and had no effect on transcription. The struct is
  now mirrored field by field and fields are set by name.
- `bootstrap.py` downloads the x64 whisper.cpp binaries instead of the 32-bit
  `Win32` ones. A 64-bit Python could not load those DLLs at all, so installing
  from source and running on the CPU build never worked. It went unnoticed
  because the development machine uses hand-built Vulkan DLLs that shadow them.
- The hallucination filter no longer eats real speech. It ran `str.replace()`
  for each marker over the whole transcription, so dictating "Thank you. I'll
  send the file tomorrow" put "I'll send the file tomorrow" on the clipboard,
  with nothing in the log to explain it. A transcription is now discarded only
  when the whole of it is a known silence filler, and the discard is logged.
- `transcribe()` frees the parameter struct on every path, including when the
  decode raises, and serialises calls so that a second one cannot free the
  buffers the DLL is reading.
- The tray tooltip and the already-running dialog are in English, like the rest
  of the interface.

### Added

- `whisper.dll` is checked at startup against the parameter layout the app
  mirrors, by reading known defaults back from it. A DLL from another
  whisper.cpp release now fails with an explicit error instead of silently
  writing to the wrong field.
- Downloads are verified against a known SHA256, and the model is written to a
  `.part` file until it passes. An interrupted download used to leave a
  truncated model that every later run accepted as complete.
- Test suite (`pytest`) and linting (`ruff`), run by GitHub Actions on
  `windows-latest` for every push and pull request. Tests that need a
  microphone, a tray, or `whisper.dll` are marked `hardware` and excluded by
  default.
- `pyproject.toml` holding the project metadata and the tool configuration.

### Changed

- `setup.py` is now `bootstrap.py`. It downloads binaries and a model; it is not
  a packaging script, and `setup.py` is the name Python tooling reserves for
  one and may run on its own.
- `requirements.txt` holds only what the app needs to run. PyInstaller, pytest,
  and ruff moved to `requirements-dev.txt`, so following the README no longer
  installs a build tool on every user's machine.
- The model is fetched from `ggml-org/whisper.cpp`, its real home, rather than
  relying on the redirect from `ggerganov/whisper.cpp`.

## [1.2.0] - 2026-08-24

### Fixed

- Probing a device no longer opens a capture stream. On some headsets the probe
  stream left the endpoint in a state where the next real capture recorded
  silence. Device availability and sample rate are now read from the PortAudio
  device info instead of by opening the device.

### Changed

- Silent-recording warnings report the input level in raw units and give the
  ratio of non-zero samples, which distinguishes a muted microphone from one
  that is alive but crushed by a noise gate.
- The startup banner logs the application version.

### Documentation

- README rewritten: corrected the Releases link, added troubleshooting, author,
  and contributing sections, and aligned the usage section with the
  clipboard-first behaviour introduced in 1.1.0.

## [1.1.0] - 2026-08-21

### Fixed

- Auto-paste was silently injecting nothing. `SendInput` validates `cbSize`
  against its own `sizeof(INPUT)`, so declaring only `KEYBDINPUT` made the
  struct 32 bytes and every call returned 0 without pressing a key.
- The capture thread is now joined before the stream is closed, which removes a
  race on shutdown.
- The desktop shortcut launches through the signed system Python rather than the
  virtual environment, so WDAC-protected machines can start the app.

### Changed

- **Clipboard-first behaviour.** The transcription always lands on the clipboard
  and in the `Win+V` history. Auto-paste is now opt-in and off by default.
- **No microphone picker.** The app follows the Windows default input, resolves
  it to its WASAPI endpoint, opens it at the device's native sample rate, and
  skips virtual microphones (Steam Streaming, OBS, VB-Cable and friends).
  Routing through MME was the root cause of silent recordings: it accepts
  44100 Hz on a 48 kHz endpoint and resamples silently, where WASAPI correctly
  refuses with `Invalid sample rate`.
- A pinned microphone is stored by **name** and resolved at every recording.
  PortAudio indices are only valid until the next hardware change.
- Capture device and input level are logged, and empty transcriptions are
  surfaced instead of silently leaving the previous text on the clipboard.

### Added

- PyInstaller is declared as a build dependency in `requirements.txt`.

## [1.0.0] - 2026-03-22

First public release.

### Added

- Push-to-talk transcription on a global hotkey (`Win+Y` by default) via the
  Windows `RegisterHotKey` API, which is immune to the localised key names that
  break keyboard-hook libraries.
- whisper.cpp loaded directly as a DLL through `ctypes`, with Vulkan GPU
  acceleration. No PyTorch, no CUDA runtime, no subprocess.
- System tray UI with language selection and prompt editing.
- Startup dialog and single-instance guard.
- Standalone `.exe` packaging through PyInstaller, plus a `setup.py` that
  downloads the whisper.cpp binaries and the model.

[1.3.0]: https://github.com/qdonnars/light-whisper-stt-wrapper/releases/tag/v1.3.0
[1.2.0]: https://github.com/qdonnars/light-whisper-stt-wrapper/releases/tag/v1.2.0
[1.1.0]: https://github.com/qdonnars/light-whisper-stt-wrapper/releases/tag/v1.1.0
[1.0.0]: https://github.com/qdonnars/light-whisper-stt-wrapper/releases/tag/v1.0.0
