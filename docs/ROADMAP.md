# Roadmap

Ideas and known rough edges, kept here so they are not lost. Nothing on this
list is a commitment, and the ordering is rough. Items move to `main` when they
ship, and to [CHANGELOG.md](../CHANGELOG.md) when they are released.

## Known rough edges

- **The desktop shortcut icon is pixelated on 4K displays.** `whisper_stt.ico`
  is generated at a single small size. It needs to carry the full set of
  resolutions up to 256x256 so Windows stops upscaling the 32px frame.
- **SmartScreen warns on first launch.** The executable is not code-signed, so
  every new user sees "Windows protected your PC". Proper signing needs a
  certificate; documenting the workaround in the README is the interim answer.
- **Errors are only visible in the log.** When capture fails or the clipboard
  write is refused, the tray icon gives no sign. A tray notification, or an icon
  state change, would make failures noticeable without opening
  `whisper_stt.log`.

## Ideas

- **Model download from the tray.** Switching models means editing
  `config.yaml` and fetching a `.bin` by hand. The tray menu already knows the
  model path and could offer the standard set.
- **Per-language prompts.** The transcription prompt is global, but the jargon
  worth priming differs by language. Storing one prompt per language would make
  the feature usable when switching between English and French.
- **Configurable hotkey from the tray.** The hotkey is only changeable in
  `config.yaml`, which requires restarting the app. `RegisterHotKey` can be
  re-registered at runtime.
- **A rolling log file.** `whisper_stt.log` grows without bound. Switching to
  `RotatingFileHandler` is a small change and stops the file reaching hundreds
  of megabytes on a machine that is never restarted.

## Explicitly not planned

- **Cloud or API-backed transcription.** Everything staying on the machine is
  the reason this project exists.
- **Real-time streaming transcription.** It would mean holding the model warm
  and decoding continuously, which trades away the low idle footprint that the
  README advertises.
- **Cross-platform support.** The hotkey layer is `RegisterHotKey`, the audio
  layer is WASAPI, and the paste path is `SendInput`. Porting would mean
  rewriting all three, and good tools already exist elsewhere.
