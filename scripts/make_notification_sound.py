"""Generate the distinctive Talabat Home notification chime (WAV).

The file is written to both the Capacitor Android raw resources (so the
local-notifications plugin can play it) and the web folder (so the browser
preview can play the same sound).
"""
from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

SAMPLE_RATE = 44_100
NOTES = (
    (1046.50, 0.00, 0.22, 0.55),  # C6 - ding
    (783.99, 0.19, 0.34, 0.50),  # G5 - dong
    (1318.51, 0.46, 0.42, 0.32),  # E6 - sparkle
)


def render() -> bytes:
    duration = max(start + length for _, start, length, _ in NOTES) + 0.05
    samples = bytearray()
    total = int(duration * SAMPLE_RATE)
    for i in range(total):
        t = i / SAMPLE_RATE
        value = 0.0
        for freq, start, length, amp in NOTES:
            local = t - start
            if local < 0 or local > length:
                continue
            attack = min(1.0, local / 0.008)
            decay = math.exp(-4.5 * local / length)
            tone = math.sin(2 * math.pi * freq * local)
            tone += 0.28 * math.sin(4 * math.pi * freq * local)
            value += amp * attack * decay * tone / 1.28
        peak = max(0.85, abs(value))
        value = value / peak * 0.82
        samples.extend(struct.pack("<h", int(max(-1.0, min(1.0, value)) * 32767)))
    return bytes(samples)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    targets = [
        root / "capacitor" / "android" / "app" / "src" / "main" / "res" / "raw" / "talabat_chime.wav",
        root / "web" / "talabat_chime.wav",
    ]
    pcm = render()
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(target), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(SAMPLE_RATE)
            wav.writeframes(pcm)
        print(f"wrote {target} ({target.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
