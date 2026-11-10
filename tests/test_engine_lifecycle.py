"""The app around the engine: a GPU reset must not leave it broken for good.

After a driver timeout the whisper context is dead and every call into it
raises a native error. The app used to log it and keep the dead context, so
each later take failed the same way until someone restarted it. No real model
is loaded here: the engine is a stand-in.
"""

import array

import pytest

import whisper_stt


class FakeEngine:
    created = 0
    fail_first = 0

    def __init__(self, model, gpu_device=None):
        type(self).created += 1
        self.closed = False

    def transcribe(self, audio, language="auto", prompt="", auto_languages=()):
        if type(self).fail_first > 0:
            type(self).fail_first -= 1
            raise OSError("[WinError -529697949] Windows Error 0xe06d7363")
        return "bonjour"

    def close(self):
        self.closed = True


@pytest.fixture
def app(monkeypatch, tmp_path):
    FakeEngine.created = 0
    FakeEngine.fail_first = 0
    monkeypatch.setattr(whisper_stt, "CONFIG_PATH", tmp_path / "config.yaml")
    monkeypatch.setattr(whisper_stt, "WhisperEngine", FakeEngine)
    delivered = []
    monkeypatch.setattr(whisper_stt, "deliver_text",
                        lambda text, auto_paste: delivered.append(text))
    app = whisper_stt.WhisperSTT()
    app.delivered = delivered
    return app


AUDIO = array.array("f", [0.1] * 16000)


def test_a_take_after_a_gpu_reset_reloads_the_model_and_goes_through(app):
    app._load_engine()
    dead = app.engine
    FakeEngine.fail_first = 1
    app.processing = True
    app._transcribe_worker(AUDIO)
    assert app.delivered == ["bonjour"]
    assert dead.closed and app.engine is not dead
    assert FakeEngine.created == 2
    assert app.processing is False


def test_it_retries_once_not_forever(app):
    FakeEngine.fail_first = 5
    app.processing = True
    app._transcribe_worker(AUDIO)
    assert app.delivered == []
    assert FakeEngine.created == 2, "one load, one reload, then give up"
    assert app.processing is False, "the hotkey must stay usable"


def test_the_model_is_loaded_once_and_reused(app):
    for _ in range(3):
        app.processing = True
        app._transcribe_worker(AUDIO)
    assert FakeEngine.created == 1
    assert app.delivered == ["bonjour"] * 3


def test_idle_unload_then_the_next_take_loads_it_again(app):
    app._load_engine()
    first = app.engine
    app._last_used -= 6 * 60
    app._unload_if_idle()
    assert app.engine is None and first.closed
    app.processing = True
    app._transcribe_worker(AUDIO)
    assert app.delivered == ["bonjour"] and FakeEngine.created == 2


class Icon:
    stopped = False

    def stop(self):
        self.stopped = True


def test_quit_does_not_wait_for_a_transcription_in_progress(app):
    """It runs on the tray's thread: waiting froze the menu for the whole take."""
    app._load_engine()
    engine = app.engine
    app.processing = True
    icon = Icon()
    app._on_quit(icon, None)
    assert icon.stopped and not engine.closed


def test_quit_still_quits_when_freeing_the_model_fails(app):
    """An error here used to skip icon.stop(): Quit did nothing, every time."""
    app._load_engine()

    def broken_close():
        raise OSError("device lost")

    app.engine.close = broken_close
    icon = Icon()
    app._on_quit(icon, None)
    assert icon.stopped


def test_quit_frees_the_model_when_nothing_is_running(app):
    app._load_engine()
    engine = app.engine
    icon = Icon()
    app._on_quit(icon, None)
    assert icon.stopped and engine.closed and app.engine is None
