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

import numpy as np
import pyaudio
import pyperclip
import pystray
import yaml
from PIL import Image, ImageDraw

# ─── Logging (file + console) ────────────────────────────────────────────────

LOG_PATH = Path(__file__).resolve().parent / "whisper_stt.log"
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

# ─── Paths ───────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.yaml"
DLL_DIR = str(BASE_DIR / "whisper-cpp")

# ─── Config ──────────────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "language": "auto",
    "prompt": "",
    "hotkey": "win+y",
    "model": "whisper-cpp/ggml-large-v3-turbo.bin",
    "microphone": None,
    "auto_paste": True,
}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        return {**DEFAULT_CONFIG, **cfg}
    return dict(DEFAULT_CONFIG)


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


def send_ctrl_v():
    """Simulate Ctrl+V using Windows SendInput API."""
    VK_CONTROL = 0x11
    VK_V = 0x56
    KEYEVENTF_KEYUP = 0x0002

    INPUT_KEYBOARD = 1

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", w.WORD),
            ("wScan", w.WORD),
            ("dwFlags", w.DWORD),
            ("time", w.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INPUT(ctypes.Structure):
        class _INPUT(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]
        _fields_ = [
            ("type", w.DWORD),
            ("_input", _INPUT),
        ]

    def make_key(vk, flags=0):
        inp = INPUT()
        inp.type = INPUT_KEYBOARD
        inp._input.ki.wVk = vk
        inp._input.ki.dwFlags = flags
        return inp

    inputs = (INPUT * 4)(
        make_key(VK_CONTROL),
        make_key(VK_V),
        make_key(VK_V, KEYEVENTF_KEYUP),
        make_key(VK_CONTROL, KEYEVENTF_KEYUP),
    )
    user32.SendInput(4, ctypes.byref(inputs), ctypes.sizeof(INPUT))


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

    def transcribe(self, audio: np.ndarray, language: str = "auto",
                   prompt: str = "") -> str:
        self._pinned.clear()
        params = self._lib.whisper_full_default_params_by_ref(0)

        if language and language != "auto":
            self._set_ptr_field(params, _OFFSET_LANGUAGE, language.encode("utf-8"))
        else:
            self._set_ptr_field(params, _OFFSET_LANGUAGE, None)

        if prompt:
            self._set_ptr_field(params, _OFFSET_INITIAL_PROMPT, prompt.encode("utf-8"))

        audio_f32 = audio.astype(np.float32)
        ret = self._lib.whisper_full(
            self._ctx, params,
            audio_f32.ctypes.data_as(ctypes.POINTER(ctypes.c_float)),
            len(audio_f32),
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


def resample(audio: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Simple linear interpolation resample."""
    if src_rate == dst_rate:
        return audio
    ratio = dst_rate / src_rate
    n_out = int(len(audio) * ratio)
    indices = np.arange(n_out) / ratio
    indices_floor = np.clip(indices.astype(np.int64), 0, len(audio) - 2)
    frac = indices - indices_floor
    return (audio[indices_floor] * (1 - frac) + audio[indices_floor + 1] * frac).astype(np.float32)


def _is_device_available(pa: pyaudio.PyAudio, device_index: int) -> bool:
    """Check if a device is actually usable by trying to open a stream."""
    try:
        stream = pa.open(
            format=FORMAT, channels=CHANNELS, rate=RECORD_RATE,
            input=True, frames_per_buffer=CHUNK,
            input_device_index=device_index,
        )
        stream.close()
        return True
    except (ValueError, OSError):
        return False


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
                if name not in seen_names and _is_device_available(pa, i):
                    seen_names.add(name)
                    mics.append((i, name))

    # Second pass: any remaining unique devices (e.g. Bluetooth via WDM-KS only)
    skip_prefixes = ("Mappeur", "Pilote de capture", "Primary")
    for i in range(pa.get_device_count()):
        info = pa.get_device_info_by_index(i)
        if info["maxInputChannels"] > 0:
            name = info["name"].strip()
            if name.startswith(skip_prefixes):
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
    def __init__(self, device_index: int | None = None):
        self.device_index = device_index
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
        self._frames = []
        self._recording = True
        threading.Thread(target=self._read_loop, daemon=True).start()

    def _find_supported_rate(self) -> int:
        """Find a sample rate the device supports, trying common rates."""
        rates = [RECORD_RATE, 48000, 16000, 22050, 32000, 8000]
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
            except Exception:
                break

    def stop(self) -> np.ndarray | None:
        self._recording = False
        if self._stream:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        if self._pa:
            self._pa.terminate()
            self._pa = None
        if not self._frames:
            return None
        raw = b"".join(self._frames)
        audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        # Resample from mic native rate to whisper's 16kHz
        return resample(audio, self.rate, WHISPER_RATE)


# ─── Paste ───────────────────────────────────────────────────────────────────

def paste_text(text: str):
    if not text:
        return
    pyperclip.copy(text)
    time.sleep(0.05)
    send_ctrl_v()


# ─── System tray ─────────────────────────────────────────────────────────────

COLORS = {
    "idle": "#4a9eff",
    "recording": "#ff4444",
    "processing": "#ffaa00",
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
        self._hotkey_mods, self._hotkey_vk = parse_hotkey(self.cfg["hotkey"])

    def _load_engine(self):
        log.info("Loading model (this takes a few seconds)...")
        self.engine = WhisperEngine(self.cfg["model"])

    # ── Tray menu ──

    def _build_menu(self) -> pystray.Menu:
        lang = self.cfg["language"]
        mic_idx = self.cfg.get("microphone")
        prompt = self.cfg.get("prompt", "") or "(vide)"
        if len(prompt) > 40:
            prompt = prompt[:37] + "..."

        mics = list_microphones()
        mic_items = [
            pystray.MenuItem(
                f"{'> ' if mic_idx is None else '  '}System default",
                self._make_mic_setter(None),
            ),
        ]
        for idx, name in mics:
            short = name[:50]
            mic_items.append(
                pystray.MenuItem(
                    f"{'> ' if idx == mic_idx else '  '}{short}",
                    self._make_mic_setter(idx),
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

    def _make_mic_setter(self, idx: int):
        def setter(icon, item):
            self.cfg["microphone"] = idx
            save_config(self.cfg)
            self.recorder = Recorder(idx)
            self._refresh_menu()
            log.info(f"Micro -> {idx}")
        return setter

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
            if state == "idle":
                self.tray.title = f"Whisper STT [{lang}] - {mic}"
            elif state == "recording":
                self.tray.title = "Whisper STT - RECORDING..."
            elif state == "processing":
                self.tray.title = "Whisper STT - Transcribing..."

    # ── Recording flow ──

    def _start_recording(self):
        self.recording = True
        self._set_state("recording")
        log.info("Recording...")
        self.recorder = Recorder(device_index=self.cfg.get("microphone"))
        self.recorder.start()

    def _stop_and_transcribe(self):
        self.recording = False
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

    def _transcribe_worker(self, audio: np.ndarray):
        try:
            text = self.engine.transcribe(
                audio,
                language=self.cfg["language"],
                prompt=self.cfg.get("prompt", ""),
            )
            log.info(f"Result: {text}")
            if text and self.cfg.get("auto_paste", True):
                paste_text(text)
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

    # ── Run ──

    def _get_mic_name(self) -> str:
        mic_idx = self.cfg.get("microphone")
        if mic_idx is None:
            try:
                pa = pyaudio.PyAudio()
                name = pa.get_default_input_device_info()["name"]
                pa.terminate()
                return name
            except Exception:
                return "default"
        for idx, name in list_microphones():
            if idx == mic_idx:
                return name
        return f"device {mic_idx}"

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
        self.tray.run()


if __name__ == "__main__":
    app = WhisperSTT()
    app.run()
