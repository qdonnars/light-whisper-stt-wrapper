"""Given silence, whisper continues the only text it has: the prompt.

Seen in the log as the prompt itself on the clipboard, 25 times in 616 takes,
and pasted into the focused window when auto-paste was on. Dropping it is
right; dropping a real sentence that happens to use a word from the prompt is
not.
"""

import pytest

from whisper_stt import is_prompt_echo, pick_language

PROMPT = "LLM IA HuggingFace MCP throughput JEV Gemma"

ECHOES = [
    "LLM IA HuggingFace MCP throughput JEV Gemma",
    "IA HuggingFace MCP throughput JEV Gemma",
    "IA HuggingFace MCP throughput",
    "IA HuggingFace MCP throughput JEV Gemma IA HuggingFace MCP throughput JEV Gemma",
    "  llm ia huggingface mcp throughput jev gemma.  ",
]

SPEECH = [
    "Gemma",
    "MCP throughput",
    "Le throughput du MCP est meilleur avec Gemma.",
    "On a testé HuggingFace puis MCP.",
    "",
]


@pytest.mark.parametrize("text", ECHOES)
def test_the_prompt_read_back_is_an_echo(text):
    assert is_prompt_echo(text, PROMPT) is True


@pytest.mark.parametrize("text", SPEECH)
def test_speech_using_prompt_words_is_kept(text):
    assert is_prompt_echo(text, PROMPT) is False


def test_no_prompt_means_no_echo():
    assert is_prompt_echo("LLM IA HuggingFace MCP", "") is False


def test_a_short_prompt_cannot_swallow_short_answers():
    """Two words dictated on purpose must survive a two-word prompt."""
    assert is_prompt_echo("Claude Code", "Claude Code") is False


# ─── pick_language ───────────────────────────────────────────────────────────


def test_the_best_allowed_language_wins_over_a_better_forbidden_one():
    # index 0 = en, 1 = es, 2 = fr; Spanish scores highest but is not allowed
    probs = [0.20, 0.50, 0.30]
    assert pick_language(probs, {"fr": 2, "en": 0}) == "fr"


def test_no_allowed_language_gives_none():
    assert pick_language([0.5, 0.5], {}) is None


def test_an_id_outside_the_table_is_ignored():
    assert pick_language([0.9, 0.1], {"en": 0, "xx": 7}) == "en"
