"""Run RGB/depth transport through the checker and adapter-forge-gateway."""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import sys
import time
import urllib.request

import numpy as np
from PIL import Image as PILImage
import yaml
from websockets.sync.client import connect


def runtime_failures(log_text):
    return [line for line in log_text.splitlines()
            if " ERROR " in line or "outgoing message size" in line or "failed to send NextEvent reply" in line]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway-root", required=True, type=Path)
    parser.add_argument("--gateway-python", type=Path)
    parser.add_argument("--output", type=Path, default=Path("build/gateway-chain"))
    parser.add_argument("--viewer-binary", type=Path)
    parser.add_argument("--usb-sink-binary", type=Path)
    parser.add_argument("--seconds", type=int, default=10)
    args = parser.parse_args()
    if args.seconds < 6:
        parser.error("--seconds must be at least 6")
    dora = os.environ.get("DORA_BIN") or shutil.which("dora")
    if dora is None:
        parser.error("Dora CLI 1.0.1 is required")
    fixture = Path(__file__).resolve().parent
    gateway_root = args.gateway_root.resolve()
    gateway_python = (args.gateway_python or gateway_root / ".venv/bin/python").absolute()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    config = {"host": "127.0.0.1", "port": port, "joint_order": ["fixture_joint"],
              "image_input_ids": ["image/rgb", "image/depth"],
              "readiness": {"require_proprio_state": False, "require_images": True,
                            "require_state_client": False, "require_image_client": False}}
    (out / "gateway.yaml").write_text(yaml.safe_dump(config))
    flow = yaml.safe_load((fixture / "dataflow.yaml").read_text())
    for node in flow["nodes"]:
        node["path"] = sys.executable
        node["args"] = shlex.quote(str(fixture / "image_stream.py")) + " " + node["args"].split(" ", 1)[1]
    def image_input(stream):
        return {"source": f"sender/{stream}", "queue_size": 1, "queue_policy": "drop_oldest"}

    flow["nodes"].append({"id": "adapter-forge-gateway", "path": str(gateway_python),
                         "args": f"-m forge_gateway --config {shlex.quote(str(out / 'gateway.yaml'))}",
                         "env": {"PYTHONPATH": str(gateway_root / "src")},
                         "inputs": {"tick": "dora/timer/millis/20", "image/rgb": image_input("rgb"), "image/depth": image_input("depth")},
                         "outputs": ["policy_command"]})
    if args.viewer_binary:
        (out / "viewer.yaml").write_text(yaml.safe_dump({"images": ["rgb", "depth"], "renderer": "glow"}))
        flow["nodes"].append({"id": "image-viewer", "path": str(args.viewer_binary.resolve()),
                             "args": f"--config {shlex.quote(str(out / 'viewer.yaml'))}",
                             "inputs": {"rgb": image_input("rgb"), "depth": image_input("depth")}})
    if args.usb_sink_binary:
        for stream in ("rgb", "depth"):
            path = out / f"sink-{stream}.yaml"
            path.write_text(yaml.safe_dump({"input_id": "image", "min_frames": 30}))
            flow["nodes"].append({"id": f"rust-{stream}", "path": str(args.usb_sink_binary.resolve()),
                                 "args": f"--config {shlex.quote(str(path))}", "inputs": {"image": image_input(stream)}})
    flow_path = out / "dataflow.yaml"
    flow_path.write_text(yaml.safe_dump(flow, sort_keys=False))
    command = [dora, "run", str(flow_path), "--stop-after", f"{args.seconds}s"]
    report = {"command": command, "includes_gateway": True, "passed": False,
              "viewer_included": bool(args.viewer_binary), "rust_sinks_included": bool(args.usb_sink_binary)}
    process = None
    # Remove a previous run's result so an early failure cannot reuse stale success.
    (out / "report.json").unlink(missing_ok=True)
    try:
        subprocess.run([dora, "validate", str(flow_path)], check=True, cwd=out)
        with (out / "dora.log").open("w") as log:
            process = subprocess.Popen(command, cwd=out, stdout=log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + args.seconds
            while True:
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=0.5) as response:
                        if json.load(response).get("ok"):
                            break
                except OSError:
                    pass
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("Gateway did not become healthy; inspect dora.log")
                time.sleep(0.1)
            received = {}
            with connect(f"ws://127.0.0.1:{port}/ws/images", open_timeout=2) as ws:
                while set(received) != {"image/rgb", "image/depth"}:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Gateway did not deliver both image streams")
                    payload = json.loads(ws.recv(timeout=2))
                    pixels = np.array(PILImage.open(io.BytesIO(base64.b64decode(payload["data"]))))
                    if pixels.shape[:2] != (480, 640):
                        raise ValueError(f"unexpected Gateway image shape: {pixels.shape}")
                    received[payload["id"]] = {"shape": list(pixels.shape), "format": payload["format"]}
            report["gateway_images"] = received
            process.wait(timeout=args.seconds + 10)
        report["exit_code"] = process.returncode
        checker = json.loads((out / "report.json").read_text())
        report["checker"] = checker
        daemon_errors = runtime_failures((out / "dora.log").read_text())
        if daemon_errors:
            report["daemon_errors"] = daemon_errors[:5]
            raise RuntimeError("Dora logged runtime errors despite its exit status; inspect dora.log")
        if process.returncode != 0 or not checker["passed"]:
            raise RuntimeError("Dora or frame checker failed; inspect dora.log")
        report["passed"] = True
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        (out / "chain-report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report))


if __name__ == "__main__":
    main()
