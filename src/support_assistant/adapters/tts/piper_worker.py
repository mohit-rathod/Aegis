"""Isolated native synthesis: cancellation can kill and reap this process."""

import json
import struct
import sys


def main():
    from piper import PiperVoice

    voice = PiperVoice.load(sys.argv[1])
    request = json.loads(sys.stdin.buffer.readline())
    for chunk in voice.synthesize(request["text"]):
        raw = chunk.audio_int16_bytes
        for offset in range(0, len(raw), 2048):
            part = raw[offset : offset + 2048]
            sys.stdout.buffer.write(
                struct.pack("!II", chunk.sample_rate, len(part)) + part
            )
            sys.stdout.buffer.flush()


if __name__ == "__main__":
    main()
