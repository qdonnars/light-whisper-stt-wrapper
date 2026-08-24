# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[semantic versioning](https://semver.org/spec/v2.0.0.html).

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

[1.2.0]: https://github.com/qdonnars/light-whisper-stt-wrapper/releases/tag/v1.2.0
[1.1.0]: https://github.com/qdonnars/light-whisper-stt-wrapper/releases/tag/v1.1.0
[1.0.0]: https://github.com/qdonnars/light-whisper-stt-wrapper/releases/tag/v1.0.0
