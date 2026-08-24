"""The ctypes mirror of whisper_full_params.

These offsets are the whole point of the file. Two pointers used to be written
at hardcoded offsets 80 and 104: 104 really was `language`, but 80 is
`carry_initial_prompt`, so every prompt set from the tray menu was written into
a bool and its padding while `initial_prompt` stayed null. Nothing raised,
because writing a pointer into padding is legal, and the prompt feature simply
never did anything.

Pinning the offsets here means the next edit to the struct has to be deliberate.
"""

import ctypes

import pytest

import whisper_stt


def test_pointer_fields_sit_where_whisper_h_puts_them():
    # whisper.cpp v1.8.3, include/whisper.h, x86_64.
    assert whisper_stt.WhisperFullParams.initial_prompt.offset == 72
    assert whisper_stt.WhisperFullParams.carry_initial_prompt.offset == 80
    assert whisper_stt.WhisperFullParams.language.offset == 104


def test_initial_prompt_is_not_where_the_old_code_wrote_it():
    """The regression this whole change exists to prevent."""
    assert whisper_stt.WhisperFullParams.initial_prompt.offset != 80


def test_struct_size_matches_v1_8_3():
    assert ctypes.sizeof(whisper_stt.WhisperFullParams) == 304


def test_head_and_tail_offsets():
    params = whisper_stt.WhisperFullParams
    assert params.strategy.offset == 0
    assert params.n_threads.offset == 4
    assert params.vad_params.offset == 280


def test_fingerprint_checks_numbers_before_pointers():
    """Order is load bearing.

    Reading an int at a wrong offset is harmless; reading a char* at a wrong
    offset dereferences whatever integer sits there and segfaults the process.
    The numeric pass is what turns that crash into an error message, so no
    pointer field may appear in the numeric fingerprint.
    """
    pointer_fields = {"language", "initial_prompt", "suppress_regex", "vad_model_path"}
    numeric_fields = {name for name, _ in whisper_stt._PARAMS_FINGERPRINT_NUMERIC}
    assert not (numeric_fields & pointer_fields)
    assert numeric_fields, "an empty numeric pass would let pointer reads run unguarded"


def test_setting_fields_writes_at_the_right_addresses():
    """Assigning by name lands on the declared offsets, not somewhere else."""
    params = whisper_stt.WhisperFullParams()
    params.language = b"fr"
    params.initial_prompt = b"jargon"

    base = ctypes.addressof(params)
    language_ptr = ctypes.c_char_p.from_address(base + 104)
    prompt_ptr = ctypes.c_char_p.from_address(base + 72)
    assert language_ptr.value == b"fr"
    assert prompt_ptr.value == b"jargon"
    # The bool the old offset pointed at is untouched.
    assert ctypes.c_bool.from_address(base + 80).value is False


@pytest.mark.hardware
def test_layout_matches_the_installed_dll():
    """Run with `pytest -m hardware` where whisper-cpp/whisper.dll exists."""
    import os

    engine = whisper_stt.WhisperEngine.__new__(whisper_stt.WhisperEngine)
    os.add_dll_directory(whisper_stt.DLL_DIR)
    engine._lib = ctypes.CDLL(os.path.join(whisper_stt.DLL_DIR, "whisper.dll"))
    engine._setup_functions()
    engine._verify_params_layout()  # raises LayoutMismatch if the DLL moved on
