# AGENTS.md

## 项目背景

全局语音输入工具。长按 `Ctrl` 说话，松手自动识别并输入文字到当前焦点应用。

- 服务端：vLLM 部署的 OpenAI 兼容 realtime ASR，地址 `http://120.55.162.96:18000/v1`
- 模型：`./Qwen3-ASR-1.7B`
- API key：`Ljd@1234`
- vLLM `0.19.1` 有 WebSocket 认证中间件 bug（`scope["method"]` 应为 `scope.get("method")`），服务端已打补丁
- 官方示例要求 `--enforce-eager` 启动 realtime 服务
- vLLM realtime 并发连接容易触发 `EngineCore` 崩溃，建议单连接使用

## 技术栈

- Python 3.14.4
- `uv` 包管理器
- `sounddevice` 音频采集
- `pynput` 全局快捷键 + 键盘模拟
- `rumps` macOS 菜单栏（仅 macOS）
- `websockets` WebSocket 客户端
- `numpy` 音频处理

## 代码规范

每次写完代码必须跑：

```bash
uv run ruff format .
uv run ruff check .
uv run pyright
```

全部通过才能提交。

## 项目结构

```
open_voice_input/
├── main.py                 # 入口文件
├── voice_input_daemon.py   # 主守护进程（菜单栏 + 快捷键 + 协调）
├── websocket_asr.py        # WebSocket ASR 客户端（可复用）
├── audio_capture.py        # 麦克风实时音频采集
├── keyboard_injector.py    # macOS 键盘模拟输入（pynput）
├── global_hotkey.py        # 全局快捷键监听（长按 Ctrl 300ms）
├── realtime_file.py        # 文件版实时转写（带进度条）
├── test.py                 # Gradio 网页版
├── pyproject.toml          # 项目配置
└── README.md               # 使用说明
```

## 关键接口

### AudioCapture

```python
capture = AudioCapture()
capture.start()       # 开始录音
audio_bytes = capture.stop()  # 停止，返回 PCM16 bytes
capture.is_recording()  # 是否正在录音
```

### WebSocketASRClient

```python
client = WebSocketASRClient(ws_url, api_key, model)
await client.connect()
await client.send_audio_chunk(audio_bytes)
await client.commit()
text = await client.receive()
await client.close()
```

### KeyboardInjector

```python
keyboard = KeyboardInjector()
keyboard.type_text("你好世界")  # 模拟键盘输入文字
```

### GlobalHotkey

```python
hotkey = GlobalHotkey(
    on_press=lambda: print("长按触发"),
    on_release=lambda: print("松手"),
    threshold_ms=300.0,
)
hotkey.start()
```

## 已知问题

1. **Mac mini 无内置麦克风**：需要外接耳机/麦克风
2. **vLLM EngineCore 崩溃**：并发连接时 `async_scheduler.py` 的 `num_output_placeholders` 断言失败，必须单连接使用
3. **WebSocket 认证 bug**：vLLM `0.19.1` release 的 `server_utils.py` 第 72 行 `scope["method"]` 在 WebSocket 请求上报 `KeyError`，已修复为 `scope.get("method")`

## Fedora 适配计划

1. **菜单栏/系统托盘**：`rumps` 仅 macOS，替换为 `pystray`（跨平台）
2. **全局快捷键**：`pynput` 在 Wayland 下受限，调研 `evdev` 或 DBus 方案
3. **音频采集**：`sounddevice` 跨平台可用，无需改动
4. **键盘输入**：`pynput` 在 X11 下可用，Wayland 需调研 `ydotool` 或 `wtype`

快速检查当前会话类型：

```bash
echo $XDG_SESSION_TYPE  # wayland 或 x11
```

## GitHub 仓库

https://github.com/lionjiadong/open_voice_input

## 常用命令

```bash
# 运行守护进程
uv run python main.py

# 文件转写
uv run python main.py ./asr_en.wav

# Gradio 网页版
uv run python test.py

# 代码检查
uv run ruff format . && uv run ruff check . && uv run pyright

# 推送代码
git add . && git commit -m "xxx" && git push
```
