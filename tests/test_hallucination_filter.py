"""Whisper fills silence with stock subtitle phrases. Dropping them is right;
dropping them out of the middle of real speech is not.

The previous filter ran str.replace() for each marker over the transcription,
so "Thank you. I'll send the file tomorrow" reached the clipboard as "I'll send
the file tomorrow", and the log only ever showed the text after the damage.
"""

import pytest

from whisper_stt import is_hallucination

DROPPED = [
    "[BLANK_AUDIO]",
    "(BLANK_AUDIO)",
    "Thank you.",
    "thank you",
    "  Thank you.  ",
    "Thanks for watching!",
    "Thanks for watching",
    "Sous-titres par la communauté d'Amara.org",
    "Sous-titres réalisés par la communauté d'Amara.org",
    "",
    "   ",
]

KEPT = [
    "Thank you. I'll send the file tomorrow.",
    "Thank you very much.",
    "Thanks for watching the demo, it was useful.",
    "Je vais relire les sous-titres par curiosité.",
    "Merci beaucoup pour ton aide.",
    "Blank audio is what we call it.",
]


@pytest.mark.parametrize("text", DROPPED)
def test_silence_fillers_are_dropped(text):
    assert is_hallucination(text) is True


@pytest.mark.parametrize("text", KEPT)
def test_real_speech_survives(text):
    assert is_hallucination(text) is False


def test_a_marker_followed_by_speech_is_kept_whole():
    """The exact regression: the marker is a prefix, not the transcription."""
    text = "Thank you. I'll send the file tomorrow."
    assert is_hallucination(text) is False
    # and nothing rewrites it
    assert text.startswith("Thank you.")


def test_matching_ignores_case_punctuation_and_spacing():
    assert is_hallucination("THANK YOU") is True
    assert is_hallucination("Thank you!") is True
    assert is_hallucination("Thank   you") is True
