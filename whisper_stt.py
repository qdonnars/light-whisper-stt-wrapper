"""
Whisper STT — Push-to-talk transcription via whisper.cpp DLL (Vulkan GPU).
System tray app with configurable hotkey, language, prompt, and microphone.
Uses Windows RegisterHotKey API for reliable global hotkeys.
"""

import ctypes
import ctypes.wintypes as w
import logging
import os
import re
import sys
import threading
import time
from pathlib import Path

import array
import struct

import pyaudio
import pyperclip
import pystray
import yaml
from PIL import Image, ImageDraw

# ─── Paths ───────────────────────────────────────────────────────────────────
# When frozen (PyInstaller exe), use the exe's directory as base.
# When running as script, use the script's directory.

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

CONFIG_PATH = BASE_DIR / "config.yaml"
DLL_DIR = str(BASE_DIR / "whisper-cpp")

# ─── Logging (file + console) ────────────────────────────────────────────────

LOG_PATH = BASE_DIR / "whisper_stt.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("whisper_stt")

# ─── Config ──────────────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "language": "auto",
    "prompt": "",
    "hotkey": "win+y",
    "model": None,  # auto-detected
    "microphone": None,
    # Off by default: the transcription always lands on the clipboard, and you
    # choose where to paste it (and it stays in the Win+V history).
    "auto_paste": False,
}

# Models in preference order (best first)
_MODEL_CANDIDATES = [
    "whisper-cpp/ggml-large-v3-turbo.bin",
    "whisper-cpp/ggml-medium.bin",
    "whisper-cpp/ggml-small.bin",
    "whisper-cpp/ggml-tiny.bin",
]


def _detect_model() -> str:
    """Find the first available model file."""
    for candidate in _MODEL_CANDIDATES:
        if (BASE_DIR / candidate).exists():
            return candidate
    return _MODEL_CANDIDATES[0]  # fallback, will error later with a clear message


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    else:
        cfg = {}
    merged = {**DEFAULT_CONFIG, **cfg}
    if not merged.get("model"):
        merged["model"] = _detect_model()
    return merged


def save_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)


# ─── Windows Hotkey (RegisterHotKey API) ─────────────────────────────────────

user32 = ctypes.windll.user32

MOD_MAP = {
    "ctrl": 0x0002,
    "alt": 0x0001,
    "shift": 0x0004,
    "win": 0x0008,
}

VK_MAP = {
    **{chr(c): c for c in range(0x41, 0x5B)},  # A-Z
    **{str(i): 0x30 + i for i in range(10)},    # 0-9
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "space": 0x20, ";": 0xBA, ",": 0xBC, ".": 0xBE,
}

WM_HOTKEY = 0x0312
HOTKEY_ID = 1


def parse_hotkey(hotkey_str: str) -> tuple[int, int]:
    """Parse 'win+h' into (modifier_flags, virtual_key_code)."""
    mods = 0
    vk = 0
    for part in hotkey_str.lower().split("+"):
        part = part.strip()
        if part in MOD_MAP:
            mods |= MOD_MAP[part]
        elif part.upper() in VK_MAP:
            vk = VK_MAP[part.upper()]
        elif part in VK_MAP:
            vk = VK_MAP[part]
        else:
            log.warning(f"Unknown key: {part}")
    return mods, vk


KEYEVENTF_KEYUP = 0x0002
INPUT_KEYBOARD = 1

# Modifiers that must not be held when we inject Ctrl+V. A screenshot is
# Win+Shift+S: if Win/Shift are still down, Windows reads the injection as
# Win+Ctrl+Shift+V and nothing is pasted. Same for our own win+y hotkey.
_MODIFIER_VKS = (
    0xA0, 0xA1,  # LShift, RShift
    0xA2, 0xA3,  # LCtrl, RCtrl
    0xA4, 0xA5,  # LAlt, RAlt
    0x5B, 0x5C,  # LWin, RWin
)


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", w.WORD),
        ("wScan", w.WORD),
        ("dwFlags", w.DWORD),
        ("time", w.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", w.LONG),
        ("dy", w.LONG),
        ("mouseData", w.DWORD),
        ("dwFlags", w.DWORD),
        ("time", w.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", w.DWORD), ("wParamL", w.WORD), ("wParamH", w.WORD)]


class INPUT(ctypes.Structure):
    """Must mirror the full Win32 INPUT union (40 bytes on x64).

    Declaring only KEYBDINPUT makes the struct 32 bytes; SendInput validates
    cbSize against its own sizeof(INPUT) and silently returns 0 — no key is
    ever injected. That is not a cosmetic detail, it breaks auto-paste.
    """
    class _INPUT(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]
    _fields_ = [
        ("type", w.DWORD),
        ("_input", _INPUT),
    ]


_EXPECTED_INPUT_SIZE = 40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28
if ctypes.sizeof(INPUT) != _EXPECTED_INPUT_SIZE:
    # Not an assert: it must survive python -O, since the failure is silent.
    raise RuntimeError(
        f"sizeof(INPUT)={ctypes.sizeof(INPUT)}, expected {_EXPECTED_INPUT_SIZE}; "
        "SendInput would reject it and auto-paste would do nothing"
    )


def _make_key(vk: int, flags: int = 0) -> INPUT:
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp._input.ki.wVk = vk
    inp._input.ki.dwFlags = flags
    return inp


def _send(inputs: list) -> bool:
    if not inputs:
        return True
    arr = (INPUT * len(inputs))(*inputs)
    ctypes.set_last_error(0)
    sent = user32.SendInput(len(inputs), ctypes.byref(arr), ctypes.sizeof(INPUT))
    if sent != len(inputs):
        log.error(
            f"SendInput injected {sent}/{len(inputs)} events "
            f"(GetLastError={ctypes.get_last_error()}) — keystrokes may be blocked"
        )
        return False
    return True


def _held_modifiers() -> list[int]:
    return [vk for vk in _MODIFIER_VKS if user32.GetAsyncKeyState(vk) & 0x8000]


def wait_modifiers_released(timeout: float = 1.5) -> list[int]:
    """Give the user a moment to let go. Returns the modifiers still held."""
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if not _held_modifiers():
            return []
        time.sleep(0.02)
    return _held_modifiers()


def send_ctrl_v():
    """Simulate Ctrl+V, first releasing any modifier the user still holds."""
    stuck = wait_modifiers_released()
    if stuck:
        log.info(f"Forcing release of stuck modifiers: {[hex(v) for v in stuck]}")
        _send([_make_key(vk, KEYEVENTF_KEYUP) for vk in stuck])
        time.sleep(0.02)

    VK_CONTROL = 0x11
    VK_V = 0x56
    return _send([
        _make_key(VK_CONTROL),
        _make_key(VK_V),
        _make_key(VK_V, KEYEVENTF_KEYUP),
        _make_key(VK_CONTROL, KEYEVENTF_KEYUP),
    ])


# ─── Whisper DLL bindings ────────────────────────────────────────────────────

_OFFSET_INITIAL_PROMPT = 80
_OFFSET_LANGUAGE = 104


class WhisperEngine:
    """Thin ctypes wrapper around whisper.dll (Vulkan-compiled)."""

    def __init__(self, model_path: str):
        os.add_dll_directory(DLL_DIR)
        self._lib = ctypes.CDLL(os.path.join(DLL_DIR, "whisper.dll"))
        self._setup_functions()
        self._pinned: list = []

        cparams = self._lib.whisper_context_default_params_by_ref()
        model_bytes = str(BASE_DIR / model_path).encode("utf-8")
        self._ctx = self._lib.whisper_init_from_file_with_params(model_bytes, cparams)
        self._lib.whisper_free_context_params(cparams)
        if not self._ctx:
            raise RuntimeError(f"Failed to load whisper model: {model_path}")
        log.info("Model loaded on GPU")

    def _setup_functions(self):
        lib = self._lib
        lib.whisper_context_default_params_by_ref.restype = ctypes.c_void_p
        lib.whisper_context_default_params_by_ref.argtypes = []
        lib.whisper_init_from_file_with_params.restype = ctypes.c_void_p
        lib.whisper_init_from_file_with_params.argtypes = [ctypes.c_char_p, ctypes.c_void_p]
        lib.whisper_full_default_params_by_ref.restype = ctypes.c_void_p
        lib.whisper_full_default_params_by_ref.argtypes = [ctypes.c_int]
        lib.whisper_full.restype = ctypes.c_int
        lib.whisper_full.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                     ctypes.POINTER(ctypes.c_float), ctypes.c_int]
        lib.whisper_full_n_segments.restype = ctypes.c_int
        lib.whisper_full_n_segments.argtypes = [ctypes.c_void_p]
        lib.whisper_full_get_segment_text.restype = ctypes.c_char_p
        lib.whisper_full_get_segment_text.argtypes = [ctypes.c_void_p, ctypes.c_int]
        lib.whisper_free.restype = None
        lib.whisper_free.argtypes = [ctypes.c_void_p]
        lib.whisper_free_params.restype = None
        lib.whisper_free_params.argtypes = [ctypes.c_void_p]
        lib.whisper_free_context_params.restype = None
        lib.whisper_free_context_params.argtypes = [ctypes.c_void_p]

    def _set_ptr_field(self, params_ptr: int, offset: int, value: bytes | None):
        if value is not None:
            c_str = ctypes.c_char_p(value)
            self._pinned.append(c_str)
            ctypes.memmove(params_ptr + offset, ctypes.byref(c_str), 8)
        else:
            null = ctypes.c_void_p(0)
            ctypes.memmove(params_ptr + offset, ctypes.byref(null), 8)

    def transcribe(self, audio: array.array, language: str = "auto",
                   prompt: str = "") -> str:
        self._pinned.clear()
        params = self._lib.whisper_full_default_params_by_ref(0)

        if language and language != "auto":
            self._set_ptr_field(params, _OFFSET_LANGUAGE, language.encode("utf-8"))
        else:
            self._set_ptr_field(params, _OFFSET_LANGUAGE, None)

        if prompt:
            self._set_ptr_field(params, _OFFSET_INITIAL_PROMPT, prompt.encode("utf-8"))

        # Convert array.array('f') to ctypes float pointer
        c_audio = (ctypes.c_float * len(audio)).from_buffer(audio)
        ret = self._lib.whisper_full(
            self._ctx, params,
            ctypes.cast(c_audio, ctypes.POINTER(ctypes.c_float)),
            len(audio),
        )
        if ret != 0:
            self._lib.whisper_free_params(params)
            log.error(f"whisper_full error: {ret}")
            return ""

        segments = []
        n = self._lib.whisper_full_n_segments(self._ctx)
        for i in range(n):
            text_bytes = self._lib.whisper_full_get_segment_text(self._ctx, i)
            if text_bytes:
                segments.append(text_bytes.decode("utf-8", errors="replace"))

        self._lib.whisper_free_params(params)
        self._pinned.clear()

        text = " ".join(s.strip() for s in segments).strip()
        for noise in ["[BLANK_AUDIO]", "(BLANK_AUDIO)", "Thank you.",
                       "Thanks for watching!", "Sous-titres par"]:
            text = text.replace(noise, "").strip()
        return text

    def close(self):
        if self._ctx:
            self._lib.whisper_free(self._ctx)
            self._ctx = None


# ─── Audio ───────────────────────────────────────────────────────────────────

RECORD_RATE = 44100   # native mic rate (most mics don't support 16kHz directly)
WHISPER_RATE = 16000   # whisper expects 16kHz
CHANNELS = 1
FORMAT = pyaudio.paInt16
CHUNK = 1024
SILENCE_PEAK = 0.01   # below this the recording is treated as silence
PEAK_STRIDE = 16      # subsampling used for the level check


def resample(audio: array.array, src_rate: int, dst_rate: int) -> array.array:
    """Simple linear interpolation resample."""
    if src_rate == dst_rate:
        return audio
    ratio = dst_rate / src_rate
    n_out = int(len(audio) * ratio)
    last = len(audio) - 2
    out = array.array("f", bytes(n_out * 4))
    for i in range(n_out):
        idx = i / ratio
        j = min(int(idx), last)
        frac = idx - j
        out[i] = audio[j] * (1.0 - frac) + audio[j + 1] * frac
    return out


def _is_device_available(pa: pyaudio.PyAudio, device_index: int) -> bool:
    """Check a device is usable, probing at the rate the device itself reports.

    Probing at a hardcoded 44100 silently disqualified every 48 kHz WASAPI
    endpoint -- which is exactly the endpoint we want. list_microphones() then
    fell through to the MME entry for the same mic, so routing the default
    "through WASAPI" kept landing on MME.
    """
    try:
        native = int(pa.get_device_info_by_index(device_index)["defaultSampleRate"])
    except Exception:
        native = RECORD_RATE
    for rate in dict.fromkeys((native, RECORD_RATE, 48000)):
        try:
            stream = pa.open(
                format=FORMAT, channels=CHANNELS, rate=rate,
                input=True, frames_per_buffer=CHUNK,
                input_device_index=device_index,
            )
            stream.close()
            return True
        except (ValueError, OSError):
            continue
    return False


_VIRTUAL_MIC_KEYWORDS = (
    "steam streaming", "nvidia broadcast", "vb-audio", "vb-cable",
    "voicemeeter", "cable input", "cable output", "virtual audio",
    "obs virtual", "discord", "wave link",
)


def _is_virtual_mic(name: str) -> bool:
    lower = name.lower()
    return any(kw in lower for kw in _VIRTUAL_MIC_KEYWORDS)


_last_host_api_msg: dict[str, str] = {}


def _host_api_of(device_index: int) -> str:
    """Name of the host API backing a device index, for logging."""
    try:
        pa = pyaudio.PyAudio()
        try:
            info = pa.get_device_info_by_index(device_index)
            return pa.get_host_api_info_by_index(info["hostApi"])["name"]
        finally:
            pa.terminate()
    except Exception:
        return "?"


def _find_by_name(wanted: str, mics: list[tuple[int, str]]) -> tuple[int, str] | None:
    """Locate a device by name, tolerating the truncation some host APIs apply."""
    for idx, name in mics:
        if name == wanted:
            return idx, name
    for idx, name in mics:
        if name.startswith(wanted[:20]) or wanted.startswith(name[:20]):
            return idx, name
    return None


def _default_or_best_physical() -> tuple[int | None, str | None]:
    """Resolve 'System default' to a WASAPI endpoint, avoiding virtual mics.

    Returning None here means PortAudio picks its own default, and on Windows
    that is the *MME* device -- the legacy emulation layer. MME reports this
    mic at 44100 Hz while the endpoint actually runs at 48000 Hz in WASAPI, and
    once another app reconfigures the endpoint, MME hands out silence instead
    of failing. Windows' own dictation goes straight to WASAPI, which is why it
    kept working while this app recorded 43 seconds of digital zeroes.

    list_microphones() is already WASAPI-first and drops virtual devices, so
    routing the default through it fixes both problems at once.
    """
    try:
        pa = pyaudio.PyAudio()
        try:
            info = pa.get_default_input_device_info()
            api = pa.get_host_api_info_by_index(info["hostApi"])["name"]
        finally:
            pa.terminate()
    except Exception as e:
        log.warning(f"No Windows default input device: {e}")
        return None, None

    name = info["name"].strip()
    mics = list_microphones()

    if _is_virtual_mic(name):
        best = next(iter(mics), None)
        if best is None:
            log.error(f"Windows default is a virtual mic {name!r} and no physical mic was found")
            return None, None
        log.warning(f"Windows default is a virtual mic {name!r} — using {best[1]!r} instead")
        return best

    found = _find_by_name(name, mics)
    if found is None:
        log.warning(f"Windows default {name!r} has no usable endpoint; letting PortAudio choose")
        return None, None
    # Report the host API we actually landed on, not the one we hoped for:
    # claiming "using its WASAPI endpoint" while opening MME hid a real bug.
    got = _host_api_of(found[0])
    if got != api:
        msg = f"Windows default {name!r} is exposed via {api}; using its {got} endpoint instead"
        # Resolution runs several times per take (tray state, menu, recording);
        # only report a change, so the log stays readable.
        if msg != _last_host_api_msg.get("v"):
            _last_host_api_msg["v"] = msg
            (log.info if got == "Windows WASAPI" else log.warning)(msg)
    return found


def resolve_microphone(wanted) -> tuple[int | None, str | None]:
    """Turn the configured microphone into an index valid *right now*.

    PortAudio freezes its device list at Pa_Initialize() and its own docs warn
    that after a refresh "all device indexes may refer to different devices".
    A saved index is therefore meaningless across a headset sleeping, a
    Bluetooth device connecting, or a driver reload: index 18 is the PRO X 2
    today and the Steam Streaming Mic tomorrow. So we save the *name* and look
    the index up again for every take.
    """
    if wanted is None:
        return _default_or_best_physical()
    mics = list_microphones()
    if isinstance(wanted, int):
        # Config written by an older version: migrate index -> name.
        for idx, name in mics:
            if idx == wanted:
                return idx, name
        log.warning(f"Saved microphone index {wanted} no longer exists")
        return None, None
    found = _find_by_name(wanted, mics)
    if found is not None:
        return found
    log.warning(
        f"Microphone {wanted!r} is not available (asleep? disconnected?) — "
        f"falling back to the Windows default. Seen: {[n for _, n in mics]}"
    )
    return None, None


def list_microphones() -> list[tuple[int, str]]:
    """List active input devices, preferring WASAPI (best quality), deduped by name."""
    pa = pyaudio.PyAudio()

    # Find WASAPI host API index
    wasapi_idx = None
    for i in range(pa.get_host_api_count()):
        if "WASAPI" in pa.get_host_api_info_by_index(i)["name"]:
            wasapi_idx = i
            break

    seen_names = set()
    mics = []
    # First pass: WASAPI devices
    if wasapi_idx is not None:
        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            if info["maxInputChannels"] > 0 and info["hostApi"] == wasapi_idx:
                name = info["name"].strip()
                if _is_virtual_mic(name):
                    continue
                if name not in seen_names and _is_device_available(pa, i):
                    seen_names.add(name)
                    mics.append((i, name))

    # Second pass: any remaining unique devices (e.g. Bluetooth via WDM-KS only)
    skip_prefixes = ("Mappeur", "Pilote de capture", "Primary")
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        if info["maxInputChannels"] > 0:
            name = info["name"].strip()
            if name.startswith(skip_prefixes) or _is_virtual_mic(name):
                continue
            # Skip if already covered (substring match for truncated MME names)
            if any(name in s or s in name for s in seen_names):
                continue
            # Clean up ugly Bluetooth driver paths
            if "@System32" in name or "bthhfenum" in name:
                m = re.search(r'\(([A-Za-z][\w\s-]+)', name, re.DOTALL)
                name = m.group(1).strip() if m else "Bluetooth"
            if _is_device_available(pa, i):
                seen_names.add(name)
                mics.append((i, name))

    pa.terminate()
    return mics


class Recorder:
    def __init__(self, device_index: int | None = None, expected_name: str | None = None):
        self.device_index = device_index
        self.expected_name = expected_name
        self._pa: pyaudio.PyAudio | None = None
        self._stream = None
        self._frames: list[bytes] = []
        self._recording = False
        self._cached_rate: int | None = None

    def start(self):
        self._pa = pyaudio.PyAudio()
        if self._cached_rate is None:
            self._cached_rate = self._find_supported_rate()
        self.rate = self._cached_rate
        kwargs = dict(
            format=FORMAT, channels=CHANNELS, rate=self.rate,
            input=True, frames_per_buffer=CHUNK,
        )
        if self.device_index is not None:
            kwargs["input_device_index"] = self.device_index
        self._stream = self._pa.open(**kwargs)
        # Log the device actually opened: with microphone=null this follows the
        # Windows default, which can silently change mid-session (headset going
        # to sleep, another app grabbing the input) and yield silent audio.
        try:
            idx = self.device_index
            if idx is None:
                idx = self._pa.get_default_input_device_info()["index"]
            info = self._pa.get_device_info_by_index(idx)
            opened = info["name"].strip()
            log.info(f"Capturing from [{idx}] {opened} @ {self.rate} Hz")
            if self.expected_name and opened != self.expected_name:
                log.warning(
                    f"Expected {self.expected_name!r} but the index now points to "
                    f"{opened!r} — the device list shifted under us"
                )
        except Exception as e:
            log.warning(f"Could not identify the capture device: {e}")
        self._frames = []
        self._recording = True
        threading.Thread(target=self._read_loop, daemon=True).start()

    def _find_supported_rate(self) -> int:
        """Find a sample rate the device supports, its own native rate first.

        Hardcoding 44100 first meant opening a 48 kHz WASAPI endpoint at the
        wrong rate and relying on the host API to resample -- which is exactly
        where MME starts returning silence.
        """
        native = None
        try:
            idx = self.device_index
            if idx is None:
                idx = self._pa.get_default_input_device_info()["index"]
            native = int(self._pa.get_device_info_by_index(idx)["defaultSampleRate"])
        except Exception:
            pass
        rates = [r for r in (native, RECORD_RATE, 48000, 16000, 22050, 32000, 8000) if r]
        rates = list(dict.fromkeys(rates))  # keep order, drop duplicates
        for rate in rates:
            try:
                self._pa.open(
                    format=FORMAT, channels=CHANNELS, rate=rate,
                    input=True, frames_per_buffer=CHUNK,
                    input_device_index=self.device_index,
                ).close()
                return rate
            except (ValueError, OSError):
                continue
        return RECORD_RATE

    def _read_loop(self):
        while self._recording and self._stream:
            try:
                data = self._stream.read(CHUNK, exception_on_overflow=False)
                self._frames.append(data)
            except Exception as e:
                # Losing the device mid-recording (headset sleeping, another app
                # taking the input) used to end up as a silent empty result.
                log.error(f"Capture stopped after {len(self._frames)} chunks: {e}")
                break

    def stop(self) -> array.array | None:
        self._recording = False
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        if self._pa:
            self._pa.terminate()
            self._pa = None
        if not self._frames:
            log.warning("No audio captured at all")
            return None
        raw = b"".join(self._frames)
        samples = struct.unpack(f"<{len(raw) // 2}h", raw)
        audio = array.array("f", (s / 32768.0 for s in samples))

        # Report the input level: an empty transcription is almost always a
        # silent mic, and without this the log cannot tell the two apart.
        duration = len(audio) / self.rate
        # Subsampled: scanning every sample costs ~215 ms on a 2 min take, and
        # this only has to answer "is the mic dead?", not measure the signal.
        peak = max((abs(s) for s in audio[::PEAK_STRIDE]), default=0.0)
        if peak < SILENCE_PEAK:
            log.warning(
                f"Recorded {duration:.1f}s but the signal is silent "
                f"(peak {peak:.4f}) — muted mic, or a noise gate closing on you "
                f"(G HUB Blue VO!CE, NVIDIA Broadcast, Discord noise suppression)?"
            )
        else:
            log.info(f"Recorded {duration:.1f}s, peak {peak:.3f}")
        return resample(audio, self.rate, WHISPER_RATE)


# ─── Paste ───────────────────────────────────────────────────────────────────

def _copy_to_clipboard(text: str, attempts: int = 5) -> bool:
    """Copy with retries: the clipboard is often locked briefly by the snipping
    tool, clipboard history or a password manager, and pyperclip then raises."""
    for i in range(attempts):
        try:
            pyperclip.copy(text)
            if pyperclip.paste() == text:
                return True
        except Exception as e:
            log.warning(f"Clipboard busy (try {i + 1}/{attempts}): {e}")
        time.sleep(0.1)
    return False


def deliver_text(text: str, auto_paste: bool):
    """Always put the transcription on the clipboard; only inject Ctrl+V if asked.

    The clipboard write must never be conditional: with auto_paste off the text
    would otherwise go nowhere at all.
    """
    if not text:
        return
    if not _copy_to_clipboard(text):
        log.error("Could not write to the clipboard — transcription LOST (see above)")
        return
    log.info("Copied to clipboard")
    if auto_paste:
        time.sleep(0.05)
        send_ctrl_v()


# ─── System tray ─────────────────────────────────────────────────────────────

COLORS = {
    "idle": "#4a9eff",
    "recording": "#ff4444",
    "processing": "#ffaa00",
    "empty": "#888888",   # transcription came back empty (silent mic?)
}


def make_icon(color: str) -> Image.Image:
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, size - 4, size - 4], fill=color)
    return img


# ─── App ─────────────────────────────────────────────────────────────────────

class WhisperSTT:
    def __init__(self):
        self.cfg = load_config()
        self.recorder: Recorder | None = None
        self.recording = False
        self.processing = False
        self.tray: pystray.Icon | None = None
        self.engine: WhisperEngine | None = None
        self._running = True
        self._empty_result = False
        self._hotkey_mods, self._hotkey_vk = parse_hotkey(self.cfg["hotkey"])
        self._migrate_microphone_setting()

    def _migrate_microphone_setting(self):
        """Rewrite a config still holding a device index into a device name."""
        wanted = self.cfg.get("microphone")
        if not isinstance(wanted, int):
            return
        _, name = resolve_microphone(wanted)
        self.cfg["microphone"] = name
        save_config(self.cfg)
        log.info(f"Migrated microphone index {wanted} to {name or 'System default'}")

    def _load_engine(self):
        log.info("Loading model (this takes a few seconds)...")
        self.engine = WhisperEngine(self.cfg["model"])

    # ── Tray menu ──

    def _build_menu(self) -> pystray.Menu:
        lang = self.cfg["language"]
        _, mic_name = resolve_microphone(self.cfg.get("microphone"))
        prompt = self.cfg.get("prompt", "") or "(vide)"
        if len(prompt) > 40:
            prompt = prompt[:37] + "..."

        mics = list_microphones()
        mic_items = [
            pystray.MenuItem(
                f"{'> ' if mic_name is None else '  '}System default",
                self._make_mic_setter(None),
            ),
        ]
        for _idx, name in mics:
            short = name[:50]
            mic_items.append(
                pystray.MenuItem(
                    f"{'> ' if name == mic_name else '  '}{short}",
                    self._make_mic_setter(name),
                )
            )
        if not mic_items:
            mic_items.append(pystray.MenuItem("(aucun micro)", None, enabled=False))

        return pystray.Menu(
            pystray.MenuItem(f"Langue: {lang}", pystray.Menu(
                pystray.MenuItem("auto", self._make_lang_setter("auto")),
                pystray.MenuItem("fr", self._make_lang_setter("fr")),
                pystray.MenuItem("en", self._make_lang_setter("en")),
            )),
            pystray.MenuItem(f"Prompt: {prompt}", self._on_edit_prompt),
            pystray.MenuItem("Micro", pystray.Menu(*mic_items)),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Coller automatiquement (Ctrl+V)",
                self._on_toggle_auto_paste,
                checked=lambda item: self.cfg.get("auto_paste", False),
            ),
            pystray.MenuItem(f"Hotkey: {self.cfg['hotkey']}", None, enabled=False),
            pystray.MenuItem("Quitter", self._on_quit),
        )

    def _make_lang_setter(self, lang: str):
        def setter(icon, item):
            self.cfg["language"] = lang
            save_config(self.cfg)
            self._refresh_menu()
            log.info(f"Langue -> {lang}")
        return setter

    def _make_mic_setter(self, name: str | None):
        def setter(icon, item):
            # Store the name, not the index: indices are only valid until the
            # device list changes (see resolve_microphone).
            self.cfg["microphone"] = name
            save_config(self.cfg)
            self._refresh_menu()
            log.info(f"Micro -> {name or 'System default'}")
        return setter

    def _on_toggle_auto_paste(self, icon, item):
        self.cfg["auto_paste"] = not self.cfg.get("auto_paste", False)
        save_config(self.cfg)
        self._refresh_menu()
        log.info(f"Auto-paste -> {self.cfg['auto_paste']}")

    def _on_edit_prompt(self, icon, item):
        threading.Thread(target=self._prompt_dialog, daemon=True).start()

    def _prompt_dialog(self):
        try:
            import tkinter as tk
            from tkinter import simpledialog
            root = tk.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            result = simpledialog.askstring(
                "Whisper STT — Prompt",
                "Mots-cles / jargon pour guider la transcription :",
                initialvalue=self.cfg.get("prompt", ""),
                parent=root,
            )
            root.destroy()
            if result is not None:
                self.cfg["prompt"] = result
                save_config(self.cfg)
                self._refresh_menu()
                log.info(f"Prompt -> {result}")
        except Exception as e:
            log.error(f"Prompt dialog: {e}")

    def _on_quit(self, icon, item):
        log.info("Quit")
        self._running = False
        if self.engine:
            self.engine.close()
        icon.stop()

    def _refresh_menu(self):
        if self.tray:
            self.tray.menu = self._build_menu()
            self.tray.update_menu()

    def _set_state(self, state: str):
        if self.tray:
            self.tray.icon = make_icon(COLORS[state])
            lang = self.cfg["language"]
            mic = self._get_mic_name()[:30]
            if state == "idle" and self._empty_result:
                self.tray.icon = make_icon(COLORS["empty"])
                self.tray.title = "Whisper STT - rien transcrit (micro muet ?)"
            elif state == "idle":
                self.tray.title = f"Whisper STT [{lang}] - {mic}"
            elif state == "recording":
                self.tray.title = "Whisper STT - RECORDING..."
            elif state == "processing":
                self.tray.title = "Whisper STT - Transcribing..."

    # ── Recording flow ──

    def _start_recording(self):
        self.recording = True
        self._empty_result = False
        self._set_state("recording")
        log.info("Recording...")
        # Resolved per take, never cached: the index is only valid right now.
        idx, name = resolve_microphone(self.cfg.get("microphone"))
        self.recorder = Recorder(device_index=idx, expected_name=name)
        self.recorder.start()

    def _stop_and_transcribe(self):
        self.recording = False
        self.processing = True
        self._set_state("processing")
        log.info("Transcribing...")

        audio = self.recorder.stop() if self.recorder else None
        self.recorder = None

        if audio is not None and len(audio) > 0:
            threading.Thread(
                target=self._transcribe_worker, args=(audio,), daemon=True,
            ).start()
        else:
            self._set_state("idle")

    def _transcribe_worker(self, audio: array.array):
        try:
            t0 = time.perf_counter()
            text = self.engine.transcribe(
                audio,
                language=self.cfg["language"],
                prompt=self.cfg.get("prompt", ""),
            )
            elapsed = time.perf_counter() - t0
            log.info(f"Transcribed in {elapsed:.2f}s: {text}")
            if text.strip():
                deliver_text(text, auto_paste=self.cfg.get("auto_paste", False))
            else:
                # Silently doing nothing here leaves the previous transcription
                # on the clipboard, which reads as "the app stopped working".
                log.warning("Empty transcription — clipboard left untouched")
                self._empty_result = True
        except Exception as e:
            log.error(f"Transcription: {e}")
        finally:
            self.processing = False
            self._set_state("idle")

    # ── Hotkey message loop (Windows RegisterHotKey) ──

    def _hotkey_loop(self):
        """Runs on a dedicated thread. Registers hotkey and pumps Windows messages."""
        mods = self._hotkey_mods | 0x4000  # MOD_NOREPEAT
        vk = self._hotkey_vk

        if not user32.RegisterHotKey(None, HOTKEY_ID, mods, vk):
            log.error(f"FAILED to register {self.cfg['hotkey']}! Taken by another app?")
            return

        log.info(f"Hotkey registered: {self.cfg['hotkey']}")
        msg = w.MSG()

        while self._running:
            # Check for WM_HOTKEY messages (non-blocking)
            if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    if not self.recording and not self.processing:
                        self._start_recording()
                        # Wait for the last key to be released
                        self._wait_for_release()
                        if self.recording:
                            self._stop_and_transcribe()
            else:
                time.sleep(0.01)

        user32.UnregisterHotKey(None, HOTKEY_ID)

    def _wait_for_release(self):
        """Poll GetAsyncKeyState until the trigger key is released."""
        vk = self._hotkey_vk
        while self._running:
            # GetAsyncKeyState: high bit set = key is down
            if not (user32.GetAsyncKeyState(vk) & 0x8000):
                return
            time.sleep(0.02)

    # ── Startup dialog ──

    def _show_startup_dialog(self):
        """Setup dialog on launch: hotkey, language, and a reminder about the tray."""
        import tkinter as tk
        from tkinter import ttk

        root = tk.Tk()
        root.title("Whisper STT")
        root.resizable(False, False)
        root.attributes("-topmost", True)

        # Center on screen
        root.update_idletasks()
        w, h = 420, 360
        x = (root.winfo_screenwidth() - w) // 2
        y = (root.winfo_screenheight() - h) // 2
        root.geometry(f"{w}x{h}+{x}+{y}")

        frame = ttk.Frame(root, padding=20)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Whisper STT", font=("Segoe UI", 14, "bold")).pack(pady=(0, 10))

        # Hotkey
        hk_frame = ttk.Frame(frame)
        hk_frame.pack(fill="x", pady=4)
        ttk.Label(hk_frame, text="Raccourci :").pack(side="left")
        hotkey_var = tk.StringVar(value=self.cfg["hotkey"])
        hotkey_entry = ttk.Entry(hk_frame, textvariable=hotkey_var, width=20)
        hotkey_entry.pack(side="right")

        # No microphone picker here on purpose: Windows already owns that
        # choice, and asking at launch made people pick a device before they
        # had any reason to. The tray menu keeps it as an override for when
        # the Windows default is the wrong one.

        # Language
        lang_frame = ttk.Frame(frame)
        lang_frame.pack(fill="x", pady=4)
        ttk.Label(lang_frame, text="Langue :").pack(side="left")
        lang_var = tk.StringVar(value=self.cfg["language"])
        lang_combo = ttk.Combobox(lang_frame, textvariable=lang_var,
                                  values=["auto", "fr", "en", "de", "es", "it"],
                                  state="readonly", width=20)
        lang_combo.set(self.cfg["language"])
        lang_combo.pack(side="right")

        # Usage reminder
        ttk.Separator(frame).pack(fill="x", pady=8)
        ttk.Label(
            frame,
            text="Comment ca marche :\n"
                 "1. Maintenez le raccourci et parlez\n"
                 "2. Relachez pour transcrire\n"
                 "3. Le texte est automatiquement colle (Ctrl+V)",
            justify="left", foreground="gray",
        ).pack(anchor="w")
        ttk.Label(
            frame,
            text="L'application reste dans la barre des taches (en bas a droite).",
            justify="center", foreground="gray",
        ).pack(pady=(6, 0))

        def on_ok():
            # Save settings
            self.cfg["hotkey"] = hotkey_var.get().strip()
            self.cfg["language"] = lang_var.get()
            save_config(self.cfg)
            self._hotkey_mods, self._hotkey_vk = parse_hotkey(self.cfg["hotkey"])
            log.info(f"Config updated: hotkey={self.cfg['hotkey']}, "
                     f"lang={self.cfg['language']}")
            root.destroy()

        ttk.Button(frame, text="Demarrer", command=on_ok).pack(pady=(10, 0))

        root.protocol("WM_DELETE_WINDOW", on_ok)
        root.mainloop()

    # ── Run ──

    def _get_mic_name(self) -> str:
        wanted = self.cfg.get("microphone")
        if wanted is None:
            try:
                pa = pyaudio.PyAudio()
                name = pa.get_default_input_device_info()["name"]
                pa.terminate()
                return name
            except Exception:
                return "default"
        _, name = resolve_microphone(wanted)
        return name or f"{wanted} (indisponible)"

    def run(self):
        log.info("=" * 45)
        log.info("Whisper STT — Push-to-talk (Vulkan GPU)")
        log.info(f"Hotkey : {self.cfg['hotkey']} (maintenir)")
        log.info(f"Langue : {self.cfg['language']}")
        log.info(f"Micro  : {self._get_mic_name()}")
        log.info(f"Prompt : {self.cfg.get('prompt') or '(vide)'}")
        log.info("=" * 45)

        self._load_engine()

        hotkey_thread = threading.Thread(target=self._hotkey_loop, daemon=True)
        hotkey_thread.start()

        self.tray = pystray.Icon(
            "whisper_stt",
            make_icon(COLORS["idle"]),
            "Whisper STT",
            menu=self._build_menu(),
        )
        log.info(f"Ready! Hold {self.cfg['hotkey']} to record, release to transcribe.")
        self._show_startup_dialog()
        self.tray.run()


def ensure_single_instance():
    """Prevent multiple instances using a Windows named mutex."""
    kernel32 = ctypes.windll.kernel32
    mutex = kernel32.CreateMutexW(None, True, "WhisperSTT_SingleInstance")
    ERROR_ALREADY_EXISTS = 183
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        log.warning("Whisper STT is already running.")
        user32.MessageBoxW(
            None,
            "Whisper STT est déjà en cours d'exécution.\n"
            "Vérifiez l'icône dans la barre des tâches (en bas à droite).",
            "Whisper STT",
            0x40,  # MB_ICONINFORMATION
        )
        sys.exit(0)
    return mutex


if __name__ == "__main__":
    _mutex = ensure_single_instance()
    app = WhisperSTT()
    app.run()
