"""Download pinned voice assets explicitly; never download models on a customer turn."""

import argparse
import hashlib
import shutil
import urllib.request
from pathlib import Path

ASSETS = {
    "silero_vad.onnx": (
        "https://raw.githubusercontent.com/snakers4/silero-vad/master/src/silero_vad/data/silero_vad.onnx",
        "1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3",
    ),
    "en_US-lessac-medium.onnx": (
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx",
        "5efe09e69902187827af646e1a6e9d269dee769f9877d17b16b1b46eeaaf019f",
    ),
    "en_US-lessac-medium.onnx.json": (
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx.json",
        "efe19c417bed055f2d69908248c6ba650fa135bc868b0e6abb3da181dab690a0",
    ),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=Path("var/models"))
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    for name, (url, expected) in ASSETS.items():
        target = args.directory / name
        if (
            not target.is_file()
            or hashlib.sha256(target.read_bytes()).hexdigest() != expected
        ):
            temporary = target.with_suffix(target.suffix + ".download")
            try:
                with (
                    urllib.request.urlopen(url, timeout=60) as response,
                    temporary.open("wb") as output,
                ):
                    shutil.copyfileobj(response, output)
                actual = hashlib.sha256(temporary.read_bytes()).hexdigest()
                if actual != expected:
                    raise RuntimeError(
                        "Upstream asset changed; review and update the pinned checksum: "
                        + name
                    )
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)
        print("Ready:", target)
    print(
        "Assets verified. Piper is GPL-3.0; the voice model card and source are documented in docs/voice-design.md."
    )


if __name__ == "__main__":
    main()
