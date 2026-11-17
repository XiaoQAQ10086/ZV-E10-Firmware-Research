"""Offline WAV <-> ZV-E10 avsystemsound BIN codec.

Format facts are taken from the public zve10-qemu research notes (block model,
24 kHz target, one-second limit). This is an independent implementation: no
PolyForm-licensed source was copied.

Native block:
    32 bytes = 1 control byte + 31 signed residual bytes
    control high nibble = predictor (0 or 1)
    control low nibble  = shift (0..8)
    decode: previous = residual * (1 << shift) + (15/16 if predictor else 0) * previous

New audio is encoded with predictor 0, choosing the least-squared-error shift
per block. Only standard library is used; no camera or USB access.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import math
from pathlib import Path
import struct
import wave

TARGET_RATE = 24_000
MAX_SECONDS = 1.0
MAX_SOURCE_BYTES = 5 * 1024 * 1024
BLOCK_BYTES = 32
BLOCK_SAMPLES = 31
MAX_ENCODED_BYTES = 24_832


class SoundError(ValueError):
    """User-facing audio conversion error."""


@dataclass(frozen=True)
class Converted:
    data: bytes
    preview_wav: bytes
    duration_seconds: float
    samples: int
    blocks: int
    sha256: str

    def summary(self) -> dict:
        return {
            "bytes": len(self.data),
            "blocks": self.blocks,
            "samples": self.samples,
            "duration_seconds": round(self.duration_seconds, 6),
            "sha256": self.sha256,
        }


def decode_native(data: bytes) -> list[float]:
    if not data or len(data) % BLOCK_BYTES:
        raise SoundError("BIN 长度必须是 32 字节的整数倍")
    values: list[float] = []
    previous = 0.0
    for at in range(0, len(data), BLOCK_BYTES):
        control = data[at]
        predictor, shift = control >> 4, control & 0x0F
        if predictor not in (0, 1) or shift > 8:
            raise SoundError(f"字节 {at} 的音频块参数不受支持")
        coefficient = 15.0 / 16.0 if predictor else 0.0
        for byte in data[at + 1:at + BLOCK_BYTES]:
            residual = byte if byte < 128 else byte - 256
            previous = residual * (1 << shift) + coefficient * previous
            values.append(previous)
    return values


def encode_predictor_zero(samples: list[float]) -> bytes:
    if not samples or len(samples) > TARGET_RATE:
        raise SoundError("音频为空或超过 1 秒")
    if any(not math.isfinite(value) or abs(value) > 32767 for value in samples):
        raise SoundError("音频样本超出可编码范围")
    padded = list(samples) + [0.0] * (-len(samples) % (2 * BLOCK_SAMPLES))
    output = bytearray()
    for at in range(0, len(padded), BLOCK_SAMPLES):
        target = padded[at:at + BLOCK_SAMPLES]
        best_error = math.inf
        best_block = b""
        for shift in range(9):
            scale = 1 << shift
            quantized = [max(-128, min(127, round(value / scale))) for value in target]
            error = sum(
                (value - integer * scale) ** 2
                for value, integer in zip(target, quantized)
            )
            if error < best_error:
                best_error = error
                best_block = bytes([shift] + [value & 255 for value in quantized])
        output.extend(best_block)
    if len(output) > MAX_ENCODED_BYTES:
        raise SoundError(f"编码后超过 {MAX_ENCODED_BYTES} 字节，请缩短音频")
    return bytes(output)


def _read_pcm_wav(path: Path) -> tuple[list[float], int]:
    if path.stat().st_size > MAX_SOURCE_BYTES:
        raise SoundError("源音频不能超过 5 MB")
    try:
        with wave.open(str(path), "rb") as source:
            if source.getcomptype() != "NONE":
                raise SoundError("只支持未压缩的 PCM WAV")
            channels = source.getnchannels()
            width = source.getsampwidth()
            rate = source.getframerate()
            frames = source.getnframes()
            raw = source.readframes(frames)
    except wave.Error as exc:
        raise SoundError(f"无法读取 WAV：{exc}") from exc

    if channels not in (1, 2):
        raise SoundError("只支持单声道或双声道")
    if width not in (1, 2, 3, 4):
        raise SoundError("只支持 8/16/24/32 位 PCM")
    if not 8_000 <= rate <= 96_000:
        raise SoundError("采样率需要在 8,000–96,000 Hz 之间")
    if frames <= 0 or frames > rate:
        raise SoundError("音频最长为 1 秒")
    expected = frames * channels * width
    if len(raw) != expected:
        raise SoundError("WAV 数据长度不完整")

    values: list[float] = []
    at = 0
    for _ in range(frames):
        total = 0.0
        for _ in range(channels):
            if width == 1:
                sample = raw[at] - 128
            elif width == 2:
                sample = int.from_bytes(raw[at:at + 2], "little", signed=True)
            elif width == 3:
                sample = int.from_bytes(raw[at:at + 3], "little", signed=True)
            else:
                sample = int.from_bytes(raw[at:at + 4], "little", signed=True)
            total += sample
            at += width
        values.append(max(-32767.0, min(32767.0, total / channels)))
    return values, rate


def resample_to_24k(samples: list[float], source_rate: int) -> list[float]:
    if source_rate == TARGET_RATE:
        return list(samples)
    count = max(1, round(len(samples) * TARGET_RATE / source_rate))
    if count > TARGET_RATE:
        raise SoundError("重采样后超过 1 秒")
    cutoff = 0.94 * min(1.0, TARGET_RATE / source_rate)
    radius = math.ceil(18 / cutoff)
    output: list[float] = []
    for index in range(count):
        center = index * source_rate / TARGET_RATE
        left = math.floor(center) - radius + 1
        right = math.floor(center) + radius
        value = weight_sum = 0.0
        for point in range(left, right + 1):
            if 0 <= point < len(samples):
                distance = point - center
                x = math.pi * cutoff * distance
                sinc = 1.0 if abs(x) < 1e-12 else math.sin(x) / x
                weight = cutoff * sinc * (0.5 + 0.5 * math.cos(math.pi * distance / radius))
                value += samples[point] * weight
                weight_sum += weight
        output.append(max(-32767.0, min(32767.0, value / weight_sum if weight_sum else 0.0)))
    return output


def preview_wav(samples: list[float]) -> bytes:
    pcm = b"".join(
        struct.pack("<h", max(-32768, min(32767, round(value)))) for value in samples
    )
    target = io.BytesIO()
    with wave.open(target, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(TARGET_RATE)
        output.writeframes(pcm)
    return target.getvalue()


def prepare_wav(path: str | Path) -> Converted:
    path = Path(path).expanduser().resolve(strict=True)
    if not path.is_file():
        raise SoundError("请选择一个 WAV 文件")
    samples, rate = _read_pcm_wav(path)
    converted = resample_to_24k(samples, rate)
    data = encode_predictor_zero(converted)
    return Converted(
        data=data,
        preview_wav=preview_wav(decode_native(data)[:len(converted)]),
        duration_seconds=len(converted) / TARGET_RATE,
        samples=len(converted),
        blocks=len(data) // BLOCK_BYTES,
        sha256=hashlib.sha256(data).hexdigest(),
    )


def decode_bin(path: str | Path) -> Converted:
    path = Path(path).expanduser().resolve(strict=True)
    raw = path.read_bytes()
    if not raw or len(raw) % BLOCK_BYTES:
        raise SoundError("BIN 长度必须是 32 字节的整数倍")
    if len(raw) > MAX_ENCODED_BYTES:
        raise SoundError("BIN 超过 24,832 字节")
    values = decode_native(raw)
    return Converted(
        data=raw,
        preview_wav=preview_wav(values),
        duration_seconds=len(values) / TARGET_RATE,
        samples=len(values),
        blocks=len(raw) // BLOCK_BYTES,
        sha256=hashlib.sha256(raw).hexdigest(),
    )
