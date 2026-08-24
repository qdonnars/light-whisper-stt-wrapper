"""The parts of whisper_stt.py that need neither Windows, a microphone, nor a DLL."""

import array

import pytest

import whisper_stt
from whisper_stt import _find_by_name, _is_virtual_mic, load_config, parse_hotkey, resample

# ─── parse_hotkey ────────────────────────────────────────────────────────────

MOD_ALT, MOD_CTRL, MOD_SHIFT, MOD_WIN = 0x0001, 0x0002, 0x0004, 0x0008


def test_default_hotkey():
    assert parse_hotkey("win+y") == (MOD_WIN, 0x59)


def test_modifiers_combine():
    mods, vk = parse_hotkey("ctrl+shift+alt+a")
    assert mods == MOD_CTRL | MOD_SHIFT | MOD_ALT
    assert vk == 0x41


def test_case_and_spacing_are_tolerated():
    assert parse_hotkey("  WIN + Y  ") == parse_hotkey("win+y")


def test_function_keys_and_digits():
    assert parse_hotkey("ctrl+f5") == (MOD_CTRL, 0x74)
    assert parse_hotkey("alt+1") == (MOD_ALT, 0x31)
    assert parse_hotkey("ctrl+space") == (MOD_CTRL, 0x20)


def test_unknown_key_yields_no_virtual_key():
    """RegisterHotKey then fails and the app says so, rather than binding junk."""
    mods, vk = parse_hotkey("ctrl+quux")
    assert mods == MOD_CTRL
    assert vk == 0


# ─── resample ────────────────────────────────────────────────────────────────


def test_same_rate_is_a_passthrough():
    audio = array.array("f", [0.1, 0.2, 0.3])
    assert resample(audio, 16000, 16000) is audio


def test_downsampling_gives_the_expected_length():
    audio = array.array("f", [0.0] * 44100)
    assert len(resample(audio, 44100, 16000)) == 16000


def test_a_ramp_stays_a_ramp():
    """Linear interpolation must not shift or scale the signal."""
    n = 4410
    audio = array.array("f", [i / n for i in range(n)])
    out = resample(audio, 44100, 16000)
    assert out[0] == pytest.approx(0.0, abs=1e-6)
    # every output sample sits on the same line, within one input step
    for i in (1, len(out) // 2, len(out) - 1):
        expected = (i / len(out))
        assert out[i] == pytest.approx(expected, abs=2 / n)


def test_upsampling_works_too():
    audio = array.array("f", [0.0] * 16000)
    assert len(resample(audio, 16000, 48000)) == 48000


# ─── microphone helpers ──────────────────────────────────────────────────────


@pytest.mark.parametrize("name", [
    "Steam Streaming Microphone",
    "NVIDIA Broadcast",
    "CABLE Output (VB-Audio Virtual Cable)",
    "VoiceMeeter Output",
    "OBS Virtual Camera Audio",
    "Wave Link Stream",
])
def test_virtual_mics_are_recognised(name):
    assert _is_virtual_mic(name) is True


@pytest.mark.parametrize("name", [
    "Microphone (PRO X 2 Wireless)",
    "Headset Microphone (Realtek(R) Audio)",
    "Microphone Array (Intel Smart Sound)",
])
def test_real_mics_are_not_filtered(name):
    assert _is_virtual_mic(name) is False


def test_find_by_name_prefers_an_exact_match():
    wanted = "Microphone (PRO X 2 Wireless)"
    mics = [(1, "Microphone (PRO X 2)"), (2, wanted)]
    assert _find_by_name(wanted, mics) == (2, wanted)


def test_find_by_name_tolerates_host_api_truncation():
    """MME truncates device names, so the stored name and the listed one differ."""
    mics = [(3, "Microphone (PRO X 2 Wirele")]
    assert _find_by_name("Microphone (PRO X 2 Wireless)", mics) == (3, "Microphone (PRO X 2 Wirele")


def test_find_by_name_returns_none_when_absent():
    mics = [(1, "Headset Microphone (Realtek(R) Audio)")]
    assert _find_by_name("Microphone (PRO X 2 Wireless)", mics) is None


# ─── load_config ─────────────────────────────────────────────────────────────


@pytest.fixture
def config_file(tmp_path, monkeypatch):
    path = tmp_path / "config.yaml"
    monkeypatch.setattr(whisper_stt, "CONFIG_PATH", path)
    monkeypatch.setattr(whisper_stt, "_detect_model", lambda: "whisper-cpp/detected.bin")
    return path


def test_missing_file_gives_the_defaults(config_file):
    cfg = load_config()
    assert cfg["hotkey"] == "win+y"
    assert cfg["language"] == "auto"
    assert cfg["auto_paste"] is False


def test_user_values_override_defaults(config_file):
    config_file.write_text("hotkey: ctrl+f9\nlanguage: fr\n", encoding="utf-8")
    cfg = load_config()
    assert cfg["hotkey"] == "ctrl+f9"
    assert cfg["language"] == "fr"


def test_unset_keys_still_come_from_defaults(config_file):
    config_file.write_text("language: fr\n", encoding="utf-8")
    cfg = load_config()
    assert cfg["hotkey"] == "win+y"
    assert cfg["microphone"] is None


def test_empty_file_is_not_an_error(config_file):
    config_file.write_text("", encoding="utf-8")
    assert load_config()["hotkey"] == "win+y"


def test_model_is_auto_detected_when_unset(config_file):
    config_file.write_text("language: fr\n", encoding="utf-8")
    assert load_config()["model"] == "whisper-cpp/detected.bin"


def test_an_explicit_model_is_kept(config_file):
    config_file.write_text("model: whisper-cpp/ggml-small.bin\n", encoding="utf-8")
    assert load_config()["model"] == "whisper-cpp/ggml-small.bin"


def test_auto_paste_stays_off_unless_asked(config_file):
    """Clipboard first is the documented default; a typo must not enable pasting."""
    config_file.write_text("language: fr\n", encoding="utf-8")
    assert load_config()["auto_paste"] is False
