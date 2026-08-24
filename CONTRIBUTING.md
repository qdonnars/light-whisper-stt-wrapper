# Contributing

Thanks for taking a look. This is a small, focused project: a push-to-talk
transcriber that lives in the system tray. Contributions are welcome as long as
they keep it small and focused.

## Branch model

| Branch | What it holds |
|--------|---------------|
| `main` | Released code. Every commit here corresponds to a tag and a GitHub release. |
| `dev`  | Integration branch. Everything lands here first. |

Open your pull request against `dev`, not `main`. `main` only moves when a
release is cut, at which point `dev` is merged into it and tagged.

Work in a topic branch off `dev`:

```
git checkout dev
git pull
git checkout -b fix/silent-capture
```

## Getting set up

You need Windows 10 or later, Python 3.10+, and Git.

```
git clone https://github.com/qdonnars/light-whisper-stt-wrapper.git
cd light-whisper-stt-wrapper
git checkout dev
python bootstrap.py
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
copy config.example.yaml config.yaml
python whisper_stt.py
```

`bootstrap.py` downloads the whisper.cpp binaries and the model, roughly 1.5 GB,
so give it a moment on the first run. It checks both against a known SHA256 and
refuses anything that does not match. It also leaves an existing
`whisper-cpp/whisper.dll` in place, so a hand-built Vulkan whisper.cpp survives
a re-run.

`requirements-dev.txt` pulls in `requirements.txt` plus pytest, ruff, and
PyInstaller. Running the app needs only `requirements.txt`.

## Testing a change

There are two halves to this, and you need both.

**The automated half.** Everything that is pure logic has tests:

```
ruff check .
pytest
```

CI runs exactly those two commands on `windows-latest` for every push and pull
request against `dev` and `main`. Windows only, and not for show: the module
builds Win32 structures and touches `user32` at import time, so it cannot be
imported anywhere else.

Tests that need a real desktop, a microphone, or `whisper.dll` are marked
`@pytest.mark.hardware` and skipped by default. Run them on your own machine
with:

```
pytest -m hardware
```

That is where the check lives that `whisper.dll` still matches the
`whisper_full_params` layout `whisper_stt.py` mirrors. Run it after swapping in
a whisper.cpp build.

**The manual half.** Audio capture, global hotkeys, and the tray still need a
real Windows desktop with a real microphone, and CI cannot stand in for that.
Before opening a pull request, run the app from source and check:

1. The tray icon appears and the menu opens.
2. Holding the hotkey records, releasing transcribes, and the text reaches the
   clipboard.
3. `whisper_stt.log` shows no warnings you did not expect. In particular, look
   for the capture device line and the input level.
4. Recording twice in a row still works. Several past bugs only showed up on the
   second capture, because the first one left the audio endpoint in a bad state.
5. If you touched the audio path, test with the microphone unplugged, asleep, and
   switched mid-session.

Say in the pull request which of these you actually ran and on what hardware.
"Tested on a Logitech PRO X 2 over WASAPI at 48 kHz" is far more useful than
"works for me".

## Things worth knowing before you touch the audio path

These are all bugs that have already been fixed once. They are easy to
reintroduce.

- **Never route capture through MME.** It is PortAudio's default host API on
  Windows and it will happily accept 44100 Hz on an endpoint running at 48 kHz,
  resampling silently and producing dead audio. WASAPI refuses with
  `Invalid sample rate`, which is the behaviour we want. Always resolve the
  device to its WASAPI endpoint.
- **Never hardcode a sample rate.** Read `defaultSampleRate` from the device and
  resample to 16 kHz yourself.
- **Never open a stream just to probe a device.** The probe stream can leave the
  endpoint unusable for the capture that follows. Read the device info instead.
- **Never store a PortAudio device index.** Indices are only valid until the next
  hardware change. Store the device *name* and resolve it at every recording.
- **`SendInput` validates `cbSize` against its own `sizeof(INPUT)`.** Declaring
  only the `KEYBDINPUT` member makes the struct 32 bytes, and every call returns
  0 without injecting anything. The union has to be declared in full.
- **Key names are localised on Windows.** That is why hotkeys go through
  `RegisterHotKey` with scan codes rather than a keyboard-hook library.

## Things worth knowing before you touch the whisper.cpp binding

- **Never write into `whisper_full_params` by byte offset.** It was done that
  way once, with two constants, and one of them was wrong: the prompt pointer
  went to offset 80, which is `carry_initial_prompt`, so the tray menu's prompt
  landed in a bool and its padding while `initial_prompt` stayed null. The
  feature did nothing and nothing could report it, because writing a pointer
  into padding is perfectly legal. `WhisperFullParams` now mirrors the struct
  field by field; set fields by name.
- **The mirror is version specific.** It matches `EXPECTED_WHISPER_CPP_TAG` and
  is x86_64 only. Swapping in a whisper.dll from another release can move every
  field after the change. `_verify_params_layout()` reads known defaults back
  from the DLL at startup so that fails loudly rather than silently.
- **Check numbers before pointers.** That verification reads the numeric fields
  first on purpose. Reading an int at a wrong offset returns nonsense and moves
  on; reading a `char *` at a wrong offset dereferences whatever integer sits
  there and takes the process down without a traceback.

## Style

Match the code that is already there. Practically:

- Comments explain *why*, not *what*. If a line looks odd, the comment should say
  which bug it prevents.
- Commit messages describe the problem being solved, in the imperative, on a
  subject line under about 72 characters. Look at `git log` for the tone.
- Log every decision the app makes about audio devices. When something goes wrong
  on a user's machine, `whisper_stt.log` is the only evidence anyone has.
- No new runtime dependencies without a good reason. Staying light is the point
  of the project.
- No em dashes in prose, comments, or log messages.

## Reporting a bug

Open an issue with:

- What you did and what happened instead.
- The relevant part of `whisper_stt.log`.
- Your Windows version, microphone model, and how it is connected (USB,
  Bluetooth, wireless dongle, docking station).

Audio bugs are almost always hardware-specific, so those last details are the
ones that make a report actionable.
