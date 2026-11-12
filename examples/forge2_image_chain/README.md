[English](README.md) | [中文](README_zh.md)

# Forge 2 / Dora 1 image-chain fixture

Generate deterministic raw RGB (rgb8) and metric depth (32FC1), validate the full
pixel content in a Python receiver, and fail on malformed or insufficient data.
This validates transport without claiming hardware or Linux artifact acceptance.

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest test_image_stream.py test_run_chain.py -q
uv sync --project /path/to/adapter-forge-gateway --frozen --no-dev
python run_chain.py --gateway-root /path/to/adapter-forge-gateway
cat build/gateway-chain/chain-report.json
```

Use the reviewed Forge 2 Gateway source (commit `c02ac097a636de9a2bc2b4656962aa11c610dbb9`,
also pinned in CI) as a test dependency. `run_chain.py` renders `dataflow.yaml` with
the mandatory Gateway node, validates it, runs Dora and checks both Gateway WebSocket
image streams. It saves the rendered graph, `dora.log`, frame counters and the final
report. The template alone is not the acceptance graph. `--viewer-binary` adds the
native GUI (requires a desktop); `--usb-sink-binary` adds Rust RGB/depth receivers.
CI runs headlessly and does not qualify the GUI or camera hardware paths.
An exit code of zero is insufficient: daemon errors and oversized/failed transport
replies also fail the report. During local multi-consumer 640×480 checks, some runs
hit Dora's 64 MiB reply limit while later runs were clean; this remains unresolved.

`image_stream.py check` accepts `--inputs rgb,depth`, `--min-frames`, optional
`--width`/`--height`, `--delay-ms` and `--report`. Missing required streams and Dora
errors fail the process. `fixture_sequence` metadata enables whole-frame pattern
checks; real camera frames are validated without requiring synthetic metadata.
Reports retain only bounded counters and maximum fixture latency, not images or an
unbounded per-frame history. Wall-clock latency is meaningful only with aligned clocks.

For a slow receiver, set `--delay-ms 100`; keep a separate fast receiver in the same
graph. Inputs use bounded `queue_size: 1` and `drop_oldest`. For a Rust receiver,
build the sibling USB camera repository's `usb_camera_test_sink`, connect each image
stream as its configured `input_id`, and set `min_frames` and optional `delay_ms` in
its YAML. It validates every frame, including frames omitted from periodic logging.

For GUI checking, connect these same outputs to the `image_viewer` executable built
from this repository. A headless receiver passing does not qualify the GUI path.

For sustained acceptance, predeclare throughput, drop, latency and memory budgets;
run the final production artifacts for at least four hours after warmup, monitor
actual shared-memory bytes and process RSS, and separately exercise crash/restart
and repeated shutdown. Do not count intervals with no effective traffic as soak time.
