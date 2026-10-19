"""Unit tests never load the speech models (slow, and not what these tests check):
voice tests fake ASR/TTS instead. Set before app.config is imported (get_settings is cached)."""
import os

os.environ["VOICE_ENABLED"] = "false"
