from __future__ import annotations

import argparse
import sys
from urllib.parse import urlparse

from voice_input_daemon import VoiceInputApp

BASE_URL = "http://120.55.162.96:18000/v1"
API_KEY = "Ljd@1234"
MODEL = "./Qwen3-ASR-1.7B"


def build_ws_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    netloc = parsed.netloc
    path = parsed.path.rstrip("/")
    if path.endswith("/v1"):
        path = path[:-3]
    return f"{scheme}://{netloc}{path}/v1/realtime"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Global voice input daemon for macOS")
    parser.add_argument(
        "--base-url",
        default=BASE_URL,
        help="OpenAI-compatible base URL",
    )
    parser.add_argument(
        "--api-key",
        default=API_KEY,
        help="API key for authentication",
    )
    parser.add_argument(
        "--model",
        default=MODEL,
        help="Realtime ASR model name",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ws_url = build_ws_url(args.base_url)

    app = VoiceInputApp(
        ws_url=ws_url,
        api_key=args.api_key,
        model=args.model,
    )
    app.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
