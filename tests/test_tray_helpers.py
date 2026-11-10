"""The recording icon's level meter, and the Start-with-Windows entry."""

import sys

import pytest

import whisper_stt
from whisper_stt import (
    LEVEL_STEPS,
    SILENCE_PEAK,
    autostart_command,
    is_autostart_enabled,
    level_step,
    make_recording_icon,
    set_autostart,
)

# ─── level_step ──────────────────────────────────────────────────────────────


def test_below_the_silence_floor_nothing_is_shown():
    """Same threshold as the one that decides a take is silent: the icon must
    not claim to hear something the app will then refuse to transcribe."""
    assert level_step(0.0) == 0
    assert level_step(SILENCE_PEAK * 0.99) == 0


def test_anything_audible_lights_at_least_the_first_step():
    assert level_step(SILENCE_PEAK) == 1


def test_loud_speech_fills_the_core_and_clipping_does_not_overflow():
    assert level_step(0.6) == LEVEL_STEPS
    assert level_step(1.0) == LEVEL_STEPS
    assert level_step(3.0) == LEVEL_STEPS


def test_the_meter_never_goes_down_as_the_voice_goes_up():
    steps = [level_step(p / 1000) for p in range(0, 1001)]
    assert steps == sorted(steps)
    assert set(steps) == set(range(LEVEL_STEPS + 1)), "every step must be reachable"


def test_ordinary_speech_sits_mid_scale():
    """Log peaks for normal dictation run around 0.25 to 0.6. On a linear
    scale they would all be in the bottom step."""
    assert 3 <= level_step(0.27) <= LEVEL_STEPS


def test_each_step_has_its_own_icon_and_they_are_cached():
    icons = [make_recording_icon(step) for step in range(LEVEL_STEPS + 1)]
    assert len({icon.tobytes() for icon in icons}) == LEVEL_STEPS + 1
    assert make_recording_icon(2) is icons[2]


# ─── autostart ───────────────────────────────────────────────────────────────


def test_from_source_windows_runs_the_silent_launcher():
    command = autostart_command()
    assert command.startswith("wscript.exe ")
    assert command.endswith('launch.vbs"')
    assert str(whisper_stt.BASE_DIR) in command


def test_frozen_windows_runs_the_exe_itself(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Tools\whisper stt\whisper_stt.exe")
    # Quoted: the path may hold spaces, and the Run key takes a command line.
    assert autostart_command() == r'"C:\Tools\whisper stt\whisper_stt.exe"'


@pytest.mark.hardware
def test_the_run_entry_can_be_added_and_removed():
    """Writes to HKCU under a throwaway name, never the app's own entry."""
    name = "WhisperSTT_pytest"
    try:
        assert is_autostart_enabled(name) is False
        set_autostart(True, name)
        assert is_autostart_enabled(name) is True
    finally:
        set_autostart(False, name)
    assert is_autostart_enabled(name) is False
    set_autostart(False, name)  # removing what is not there is not an error


# ─── languages ───────────────────────────────────────────────────────────────


def test_nothing_is_ticked_for_the_user():
    """The app offers languages; it does not pick any on the user's behalf."""
    assert whisper_stt.DEFAULT_CONFIG["auto_languages"] == []


def test_a_language_from_config_yaml_gets_its_own_checkbox():
    choices = whisper_stt.language_choices(["fr", "ja"])
    assert choices[: len(whisper_stt.COMMON_LANGUAGES)] == list(whisper_stt.COMMON_LANGUAGES)
    assert choices[-1] == "ja"
    assert choices.count("fr") == 1
