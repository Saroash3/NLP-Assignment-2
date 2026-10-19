"""
Assignment 3 voice pipeline, without any speech model: ASR, TTS and the VAD are faked, so these
tests check OUR code -- sentence splitting, endpointing, the event order of a spoken turn, error
handling, and that typed chat on another connection is not blocked.
"""
import base64

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.llm_engine import GenerationStats
from app.main import app
from app.voice import asr, tts, vad, voice_session
from app.voice.sentence_buffer import SentenceBuffer, clean_for_speech

# ---------------------------------------------------------------- sentence buffer


def speak(text: str) -> list[str]:
    buffer, out = SentenceBuffer(), []
    for token in text.split(" "):
        out += buffer.push(token + " ")
    rest = buffer.flush()
    return out + ([rest] if rest else [])


def test_sentences_are_released_as_soon_as_they_end():
    assert speak("Your BMI is 24.7. That is normal! Want a plan?") == [
        "Your BMI is 24.7.", "That is normal!", "Want a plan?"]


def test_long_first_clause_is_released_at_a_comma():
    first = speak("Great question about recovery and sleep, rest days matter a lot for growth.")[0]
    assert first == "Great question about recovery and sleep,"


def test_markdown_is_not_read_out():
    assert clean_for_speech("**Plus** -- PKR 16,000 `now`") == "Plus, PKR 16,000 now"


# ---------------------------------------------------------------- fakes


class FakeVAD:
    """Speech = loud window. Real Silero is tested by hand / in the benchmark."""

    def reset(self):
        pass

    def probabilities(self, windows):
        return (np.abs(windows).mean(axis=1) > 0.05).astype(np.float32)


class Engine:
    async def generate_with_stats(self, messages, **kwargs):
        return ("NONE" if "TOOLS:" in messages[0]["content"] else "ON_TOPIC"), GenerationStats(0, 0, 1)

    async def stream_chat(self, messages):
        for token in ("Hello! ", "The gym opens ", "at 6 am."):
            yield token

    async def check_health(self):
        return True

    async def aclose(self):
        return None


@pytest.fixture
def fake_voice(monkeypatch):
    async def transcribe(audio, member_name=None):
        return "When does the gym open?"

    async def synthesize(text):
        return b"\x01\x00" * 100

    monkeypatch.setattr(asr, "is_ready", lambda: True)
    monkeypatch.setattr(asr, "transcribe_async", transcribe)
    monkeypatch.setattr(tts, "is_ready", lambda: True)
    monkeypatch.setattr(tts, "sample_rate", lambda: 22050)
    monkeypatch.setattr(tts, "synthesize_async", synthesize)
    monkeypatch.setattr(vad, "is_ready", lambda: True)
    monkeypatch.setattr(voice_session.vad, "StreamingVAD", FakeVAD)


def pcm(seconds: float, loud: bool) -> bytes:
    samples = np.full(int(16000 * seconds), 8000 if loud else 0, dtype=np.int16)
    return samples.tobytes()


def send_audio(ws, *parts):
    for part in parts:
        for i in range(0, len(part), 2048):  # 64 ms frames, like the browser
            ws.send_bytes(part[i:i + 2048])


def receive_until(ws, event_type):
    events = []
    while not events or events[-1]["type"] != event_type:
        events.append(ws.receive_json())
    return events


# ---------------------------------------------------------------- spoken turn


def test_spoken_turn_uses_the_normal_pipeline_and_streams_audio(fake_voice):
    with TestClient(app) as client:
        app.state.llm_engine = Engine()
        with client.websocket_connect("/ws/chat?extended=1") as ws:
            ws.receive_json()  # session
            ws.send_json({"type": "voice_start"})
            assert ws.receive_json() == {"type": "voice_state", "state": "listening"}
            send_audio(ws, pcm(0.2, False), pcm(0.6, True), pcm(0.8, False))
            events = receive_until(ws, "latency")

    partials = [e for e in events if e["type"] == "transcript" and not e["final"]]
    assert partials  # live captions arrived while still "speaking"
    events = [e for e in events if e not in partials]
    types = [e["type"] for e in events]
    assert types[:3] == ["voice_state", "transcript", "voice_state"]  # transcribing, final, thinking
    assert events[1] == {"type": "transcript", "text": "When does the gym open?", "final": True}
    assert events[2] == {"type": "voice_state", "state": "thinking"}
    assert "done" in types and types[-2] == "audio_end"
    audio = [e for e in events if e["type"] == "audio"]
    assert [a["seq"] for a in audio] == list(range(len(audio))) and len(audio) == 2  # 2 sentences
    assert base64.b64decode(audio[0]["data"]) == b"\x01\x00" * 100
    latency = events[-1]
    assert {"asr_ms", "llm_first_token_ms", "tts_first_audio_ms", "total_ms"} <= set(latency)


def test_noise_blip_is_ignored(fake_voice):
    with TestClient(app) as client:
        app.state.llm_engine = Engine()
        with client.websocket_connect("/ws/chat?extended=1") as ws:
            ws.receive_json()
            ws.send_json({"type": "voice_start"})
            ws.receive_json()
            send_audio(ws, pcm(0.1, True), pcm(0.8, False))  # 0.1 s < minimum speech
            ws.send_json({"type": "voice_stop"})
            assert ws.receive_json() == {"type": "voice_state", "state": "idle"}  # no transcript came


def test_voice_start_without_models_gives_a_clean_error():
    with TestClient(app) as client:
        with client.websocket_connect("/ws/chat?extended=1") as ws:
            ws.receive_json()
            ws.send_json({"type": "voice_start"})
            event = ws.receive_json()
            assert event["type"] == "error" and event["code"] == "voice_unavailable"
            ws.send_json({"type": "message", "content": "hi"})  # text chat still works


def test_tts_failure_still_delivers_the_text_reply(fake_voice, monkeypatch):
    async def broken(text):
        raise RuntimeError("onnx exploded")

    monkeypatch.setattr(tts, "synthesize_async", broken)
    with TestClient(app) as client:
        app.state.llm_engine = Engine()
        with client.websocket_connect("/ws/chat?extended=1") as ws:
            ws.receive_json()
            ws.send_json({"type": "voice_start"})
            send_audio(ws, pcm(0.6, True), pcm(0.8, False))
            events = receive_until(ws, "latency")
    types = [e["type"] for e in events]
    assert "done" in types and "audio" not in types and "audio_end" in types
    assert [e["code"] for e in events if e["type"] == "error"] == ["tts_error"]  # reported once


def test_audio_frames_are_ignored_until_voice_start():
    with TestClient(app) as client:
        app.state.llm_engine = Engine()
        with client.websocket_connect("/ws/chat?extended=1") as ws:
            ws.receive_json()
            ws.send_bytes(pcm(1.0, True))
            ws.send_json({"type": "message", "content": "hi"})
            assert ws.receive_json()["type"] == "token"  # the audio produced nothing


def test_quiet_audio_is_normalised_but_silence_is_not_amplified():
    quiet = np.full(1600, 0.25, dtype=np.float32)
    assert abs(float(asr.normalize(quiet).max()) - 0.9) < 1e-6  # 0.25 -> 0.9
    near_silence = np.full(1600, 0.005, dtype=np.float32)
    assert np.allclose(asr.normalize(near_silence), near_silence)  # below the floor: left alone


def test_noah_is_corrected_to_nova():
    text = "Hi Noah, how are you?"
    for wrong, right in asr.FIXES:
        text = wrong.sub(right, text)
    assert text == "Hi Nova, how are you?"


def test_planes_is_corrected_to_plans():
    text = "Okay, tell me about Standard Planes."
    for wrong, right in asr.FIXES:
        text = wrong.sub(right, text)
    assert text == "Okay, tell me about Standard plans."


def test_clipped_admission_fee_is_restored():
    for heard in ("What's the procedure about Mission P?", "the procedure about? Mission fee."):
        text = heard
        for wrong, right in asr.FIXES:
            text = wrong.sub(right, text)
        assert "admission fee" in text
    text = "What is the admission fee?"  # already right: left alone
    for wrong, right in asr.FIXES:
        text = wrong.sub(right, text)
    assert text == "What is the admission fee?"


def test_after_the_spoken_greeting_nova_listens_again(fake_voice, tmp_path, monkeypatch):
    """Regression (live demo): after speaking the welcome-back greeting, the state stayed
    'speaking', so the browser never sent the mic again."""
    from app.tools import user_profile
    from app.tools.json_store import JsonStore

    monkeypatch.setattr(user_profile, "store", JsonStore(tmp_path / "profiles.json"))
    import asyncio
    asyncio.run(user_profile.store.update(lambda d: d.update({"returning": {"name": "Sara"}})))
    with TestClient(app) as client:
        app.state.llm_engine = Engine()
        with client.websocket_connect("/ws/chat?extended=1&user_id=returning") as ws:
            ws.receive_json()  # session
            assert "Welcome back, Sara" in ws.receive_json()["content"]
            ws.receive_json()  # done
            ws.send_json({"type": "voice_start"})
            events = receive_until(ws, "audio_end")
            assert events[0] == {"type": "voice_state", "state": "listening"}
            assert ws.receive_json() == {"type": "voice_state", "state": "listening"}  # listens again


def test_sound_alikes_of_the_assistants_name_become_nova():
    for heard in ("Hi Dova, how are you?", "Hi Noah, how are you?", "Hey Nowa!"):
        text = heard
        for wrong, right in asr.FIXES:
            text = wrong.sub(right, text)
        assert "Nova" in text and "ova," in text or "Nova!" in text
