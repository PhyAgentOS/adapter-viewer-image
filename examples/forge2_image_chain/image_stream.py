"""Hardware-free Forge Image producer and strict Dora image-stream checker."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
from dora import Node
from forge_msgs import CompressedImage, Image


def validate_image(value, metadata):
    try:
        image = Image.from_arrow(value)
    except (KeyError, TypeError, ValueError):
        image = CompressedImage.from_arrow(value)
    pixels = image.to_numpy()
    if pixels.size == 0:
        raise ValueError("empty image")
    sequence = metadata.get("fixture_sequence")
    if sequence is not None:
        expected = (sequence % 251 if pixels.dtype == np.uint8 else (sequence % 100 + 1) / 100)
        if not np.allclose(pixels, expected, rtol=0, atol=1e-6):
            raise ValueError(f"image content differs from fixture sequence {sequence}")
    return pixels.shape


def send(args):
    node = Node()
    sequence = 0
    for event in node:
        if event["type"] == "STOP":
            break
        if event["type"] == "ERROR":
            raise RuntimeError(event.get("error", "Dora error"))
        if event["type"] != "INPUT" or event["id"] != "tick":
            continue
        metadata = {"fixture_sequence": sequence, "fixture_sent_ns": time.time_ns()}
        color = np.full((args.height, args.width, 3), sequence % 251, dtype=np.uint8)
        depth = np.full((args.height, args.width), (sequence % 100 + 1) / 100, dtype=np.float32)
        node.send_output("rgb", Image.from_numpy(color, encoding="rgb8").to_arrow(), metadata=metadata)
        node.send_output("depth", Image.from_numpy(depth, encoding="32FC1").to_arrow(), metadata=metadata)
        sequence += 1


def check(args):
    counts = {name: 0 for name in args.inputs.split(",")}
    started = time.monotonic()
    maximum_latency_ms = 0.0
    failure = None
    try:
        for event in Node():
            if event["type"] == "STOP":
                break
            if event["type"] == "ERROR":
                raise RuntimeError(event.get("error", "Dora error"))
            if event["type"] != "INPUT" or event["id"] not in counts:
                continue
            metadata = event.get("metadata", {})
            shape = validate_image(event["value"], metadata)
            if args.width and shape[1] != args.width:
                raise ValueError(f"unexpected width: {shape}")
            if args.height and shape[0] != args.height:
                raise ValueError(f"unexpected height: {shape}")
            counts[event["id"]] += 1
            sent_ns = metadata.get("fixture_sent_ns")
            if sent_ns is not None:
                maximum_latency_ms = max(maximum_latency_ms, (time.time_ns() - sent_ns) / 1e6)
            if args.delay_ms:
                time.sleep(args.delay_ms / 1000)
        missing = {key: count for key, count in counts.items() if count < args.min_frames}
        if missing:
            raise ValueError(f"insufficient valid images: {missing}; minimum={args.min_frames}")
    except Exception as error:
        failure = str(error)
        raise
    finally:
        report = {
            "passed": failure is None,
            "counts": counts,
            "elapsed_seconds": time.monotonic() - started,
            "max_fixture_latency_ms": maximum_latency_ms,
            "error": failure,
        }
        if args.report:
            Path(args.report).write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["send", "check"])
    parser.add_argument("--width", type=int, default=0)
    parser.add_argument("--height", type=int, default=0)
    parser.add_argument("--inputs", default="rgb,depth")
    parser.add_argument("--min-frames", type=int, default=1)
    parser.add_argument("--delay-ms", type=int, default=0)
    parser.add_argument("--report")
    args = parser.parse_args()
    if min(args.width, args.height, args.delay_ms) < 0 or args.min_frames < 1:
        parser.error("dimensions/delay must be nonnegative and min-frames must be positive")
    if args.mode == "send" and (not args.width or not args.height):
        parser.error("send requires positive --width and --height")
    (send if args.mode == "send" else check)(args)


if __name__ == "__main__":
    main()
