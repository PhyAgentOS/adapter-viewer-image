[English](README.md) | 中文

# Forge 2 / Dora 1 图像链测试夹具

发送确定性 RGB（rgb8）和米制深度（32FC1），Python 接收端逐帧检查完整像素内容。
坏帧、缺少必需流、帧数不足及 Dora 错误都会返回失败。这只证明传输，不代替设备或 Linux 发布包验收。

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m pytest test_image_stream.py test_run_chain.py -q
uv sync --project /path/to/adapter-forge-gateway --frozen --no-dev
python run_chain.py --gateway-root /path/to/adapter-forge-gateway
cat build/gateway-chain/chain-report.json
```

测试依赖使用已审查的 Forge 2 Gateway 源码（提交 `c02ac097a636de9a2bc2b4656962aa11c610dbb9`，
CI 同样固定此版本）。`run_chain.py` 在模板中加入必需的 Gateway，校验后执行 Dora，
并检查 Gateway WebSocket 的两路图像。输出包含实际数据流、`dora.log`、逐帧计数和最终报告。
模板本身不是验收数据流。`--viewer-binary` 加入原生 GUI（需要桌面），
`--usb-sink-binary` 加入 Rust RGB／深度接收端。CI 为无头检查，不代替 GUI 或相机真机验收。
退出码为零并不足以判定通过：daemon 错误、超大消息和传输回复失败同样使报告失败。
本机 640×480 多消费者检查中，部分运行触发 Dora 的 64 MiB 回复上限，后续运行正常；
这一间歇问题仍未解决。

`image_stream.py check` 支持 `--inputs rgb,depth`、`--min-frames`、可选的
`--width`／`--height`、`--delay-ms` 和 `--report`。存在 `fixture_sequence`
metadata 时校验完整测试图案；真实相机帧不要求测试专用 metadata。
报告只保存有界计数和最大测试延迟，不存图片或无限增长的逐帧历史。跨主机延迟要求时钟对齐。

慢消费者测试可设置 `--delay-ms 100`，同时保留一个正常消费者。
输入队列显式设置 `queue_size: 1`、`drop_oldest`。Rust 接收端可使用 USB 相机仓库
构建的 `usb_camera_test_sink`：每路图像映射到配置的 `input_id`，YAML 中设置
`min_frames`、可选 `delay_ms`。日志抽样不会减少实际校验的帧数。

GUI 检查将同样输出接到本仓构建的 `image_viewer`；无头接收通过不能代替 GUI 验收。

长跑前固定吞吐、丢帧、延迟和内存预算；最终生产者产物预热后至少连续运行 4 小时，
监控共享内存实际字节数与进程 RSS。异常退出／重启和反复启停单独记录，不能用无有效流量的时间凑满长跑。
