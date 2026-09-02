#!/usr/bin/env python3
"""Send a small concurrent chat workload through the Layerwise proxy."""

from __future__ import annotations

import argparse
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from launch import load_config


def _request_json(
    url: str, payload: dict[str, Any] | None = None
) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="GET" if data is None else "POST",
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        return json.loads(response.read())


def _chat(config: dict[str, Any], index: int, max_tokens: int) -> str:
    base_url = f"http://{config['proxy_ip']}:{config['ports']['proxy']}"
    response = _request_json(
        f"{base_url}/v1/chat/completions",
        {
            "model": config["served_model_name"],
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Reply with exactly this identifier and no other text: "
                        f"edge-cloud-{index}"
                    ),
                }
            ],
            "temperature": 0,
            "max_tokens": max_tokens,
            "stream": False,
        },
    )
    if "error" in response:
        raise RuntimeError(f"Request {index} failed: {response['error']}")
    choices = response.get("choices") or []
    if not choices:
        raise RuntimeError(f"Request {index} returned no choices: {response}")
    message = choices[0].get("message") or {}
    return str(message.get("content", choices[0].get("text", "")))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--requests", type=int, default=4)
    parser.add_argument("--max-tokens", type=int, default=32)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.requests <= 0 or args.max_tokens <= 0:
        raise ValueError("--requests and --max-tokens must be positive")
    config = load_config(args.config)
    base_url = f"http://{config['proxy_ip']}:{config['ports']['proxy']}"
    health = _request_json(f"{base_url}/healthcheck")
    if health != {
        "status": "ok",
        "prefill_instances": 1,
        "decode_instances": 1,
    }:
        raise RuntimeError(f"Unexpected proxy health response: {health}")

    with ThreadPoolExecutor(max_workers=args.requests) as executor:
        outputs = list(
            executor.map(
                lambda index: _chat(config, index, args.max_tokens),
                range(args.requests),
            )
        )
    for index, output in enumerate(outputs):
        print(f"request={index} output={output!r}")
    print(f"PASS: {len(outputs)} edge-cloud PD requests completed")


if __name__ == "__main__":
    main()
