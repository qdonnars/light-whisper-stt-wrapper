"""The parts of whisper_stt.py that need neither Windows, a microphone, nor a DLL."""

import array

import pytest

import whisper_stt
from whisper_stt import (
    _find_by_name,
    _is_virtual_mic,
    format_hotkey,
    load_config,
    mods_from_vks,
    parse_hotkey,
    resample,
)

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


# ─── hotkey capture ──────────────────────────────────────────────────────────


def test_captured_hotkey_round_trips_through_the_parser():
    combo = format_hotkey(MOD_CTRL | MOD_ALT, 0x52)
    assert combo == "ctrl+alt+r"
    assert parse_hotkey(combo) == (MOD_CTRL | MOD_ALT, 0x52)


def test_default_hotkey_is_formatted_like_the_config():
    assert format_hotkey(MOD_WIN, 0x59) == "win+y"


def test_left_and_right_modifiers_fold_together():
    # LShift, RCtrl, LWin
    assert mods_from_vks([0xA0, 0xA3, 0x5B]) == MOD_SHIFT | MOD_CTRL | MOD_WIN


def test_bare_letter_is_refused():
    """Binding plain Y would eat every Y typed on the machine."""
    assert format_hotkey(0, 0x59) is None


def test_bare_function_key_is_allowed():
    assert format_hotkey(0, 0x78) == "f9"


def test_key_outside_the_map_is_refused():
    assert format_hotkey(MOD_CTRL, 0x2D) is None  # Insert


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


# ─── should_unload ───────────────────────────────────────────────────────────


def test_the_model_is_unloaded_once_the_delay_has_passed():
    assert whisper_stt.should_unload(299, 5, busy=False) is False
    assert whisper_stt.should_unload(300, 5, busy=False) is True


def test_a_take_in_progress_is_never_interrupted():
    assert whisper_stt.should_unload(10_000, 5, busy=True) is False


@pytest.mark.parametrize("minutes", [0, None, "", "never", -1])
def test_zero_or_nonsense_keeps_the_model_loaded(minutes):
    assert whisper_stt.should_unload(10_000, minutes, busy=False) is False


def test_the_delay_cannot_be_set_under_a_minute():
    """Loading and freeing a GPU model every few seconds is hard on the driver."""
    assert whisper_stt.should_unload(30, 0.05, busy=False) is False
    assert whisper_stt.should_unload(60, 0.05, busy=False) is True


# ─── pick_gpu ────────────────────────────────────────────────────────────────

GB = 1 << 30
CPU, GPU, IGPU = 0, whisper_stt.DEV_GPU, whisper_stt.DEV_IGPU


def test_a_graphics_card_wins_over_the_integrated_chip_listed_first():
    """The exact machine this broke on: Vulkan0 integrated, Vulkan1 the card.
    whisper.cpp's default of 0 ran the model on the integrated chip."""
    assert whisper_stt.pick_gpu([(IGPU, 16 * GB), (GPU, 32 * GB), (CPU, 32 * GB)]) == 1


def test_the_card_is_still_chosen_when_it_comes_first():
    assert whisper_stt.pick_gpu([(GPU, 32 * GB), (IGPU, 16 * GB), (CPU, 32 * GB)]) == 0


def test_an_integrated_chip_with_more_memory_does_not_beat_a_card():
    assert whisper_stt.pick_gpu([(IGPU, 48 * GB), (GPU, 8 * GB)]) == 1


def test_between_two_cards_the_larger_one_wins():
    assert whisper_stt.pick_gpu([(GPU, 8 * GB), (GPU, 24 * GB)]) == 1


def test_a_laptop_with_only_an_integrated_chip_uses_it():
    assert whisper_stt.pick_gpu([(IGPU, 8 * GB), (CPU, 16 * GB)]) == 0


def test_the_index_counts_gpus_only_like_whisper_cpp_does():
    """A CPU entry ahead of the card must not shift the index."""
    assert whisper_stt.pick_gpu([(CPU, 32 * GB), (IGPU, 16 * GB), (GPU, 32 * GB)]) == 1


def test_no_gpu_at_all_gives_none():
    assert whisper_stt.pick_gpu([(CPU, 16 * GB)]) is None
    assert whisper_stt.pick_gpu([]) is None


# ─── unload delay, as typed in the settings dialog ───────────────────────────


@pytest.mark.parametrize("typed, expected", [
    ("5", 5), ("0", 0), (" 10 ", 10), ("2.5", 2.5), ("2,5", 2.5), ("0.2", 1), ("240", 240),
])
def test_a_typed_delay_is_understood(typed, expected):
    assert whisper_stt.parse_minutes(typed, previous=5) == expected


@pytest.mark.parametrize("typed", ["", "soon", "-3", "nan"])
def test_nonsense_keeps_the_previous_delay(typed):
    assert whisper_stt.parse_minutes(typed, previous=7) == 7


@pytest.mark.parametrize(
    "value, shown", [(5, "5"), (2.5, "2.5"), (0, "0"), (None, "5"), ("x", "5")]
)
def test_the_delay_is_shown_without_a_trailing_zero(value, shown):
    assert whisper_stt.format_minutes(value) == shown
