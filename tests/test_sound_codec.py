from __future__ import annotations

import math
from pathlib import Path
import wave

import pytest

from zve10_installer import sound_codec


def write_wav(path: Path, samples: list[float], rate: int = 24_000) -> None:
    pcm = b"".join(
        int(max(-32768, min(32767, round(value)))).to_bytes(2, "little", signed=True)
        for value in samples
    )
    with wave.open(str(path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(pcm)


def test_first_test_clip_is_1216_bytes(tmp_path):
    samples = [
        math.sin(2 * math.pi * 1000 * index / 24_000) * 8000
        for index in range(1_178)
    ]
    source = tmp_path / "click.wav"
    write_wav(source, samples)

    converted = sound_codec.prepare_wav(source)
    assert len(converted.data) == 1_216
    assert converted.blocks == 38
    assert converted.samples == 1_178
    assert converted.duration_seconds == pytest.approx(1_178 / 24_000)

    bin_path = tmp_path / "click.bin"
    bin_path.write_bytes(converted.data)
    decoded = sound_codec.decode_bin(bin_path)
    assert decoded.samples == 1_178
    assert decoded.blocks == 38
    assert decoded.preview_wav[:4] == b"RIFF"


def test_longer_audio_rejected(tmp_path):
    source = tmp_path / "long.wav"
    write_wav(source, [0.0] * 24_001)
    with pytest.raises(sound_codec.SoundError):
        sound_codec.prepare_wav(source)


def test_non_pcm_wav_rejected(tmp_path):
    source = tmp_path / "bad.wav"
    source.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt ")
    with pytest.raises(sound_codec.SoundError):
        sound_codec.prepare_wav(source)
