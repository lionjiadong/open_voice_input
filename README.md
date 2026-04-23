# Open Voice Input

macOS / Linux 全局语音输入工具。长按 `Ctrl` 说话，松手自动识别并输入文字到当前焦点应用。

## 功能

- 🎙️ 长按 `Ctrl` 300ms 开始录音，松手发送识别
- 🚀 基于 vLLM + Qwen3-ASR-1.7B 实时语音识别
- ⌨️ 识别结果通过模拟键盘输入插入到任意应用
- 📊 菜单栏图标显示状态：🎤 就绪 / 🔴 录音中 / 🟡 处理中

## 环境

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) 包管理器
- macOS（当前）/ Fedora（计划中）

## 安装

```bash
# 克隆项目
git clone https://github.com/lionjiadong/open_voice_input.git
cd open_voice_input

# 安装依赖
uv sync
```

## 使用

### 全局语音输入（守护进程）

```bash
uv run python main.py
```

长按 `Ctrl` 开始录音，松手后识别结果自动输入到当前光标位置。

### 文件转写

```bash
# 转写单个文件
uv run python main.py ./asr_en.wav

# 转写多个文件
uv run python main.py ./asr_en.wav ./asr_zh.wav
```

### Gradio 网页版

```bash
uv run python test.py
```

## 配置

默认连接远程 vLLM 服务：

- Base URL: `http://120.55.162.96:18000/v1`
- Model: `./Qwen3-ASR-1.7B`

可通过环境变量或命令行参数修改：

```bash
uv run python main.py --base-url http://your-server:8000/v1 --model your-model
```

## 项目结构

```
open_voice_input/
├── main.py                 # 入口文件
├── voice_input_daemon.py   # 主守护进程（菜单栏 + 快捷键）
├── websocket_asr.py        # WebSocket ASR 客户端
├── audio_capture.py        # 麦克风音频采集
├── keyboard_injector.py    # 键盘模拟输入（macOS）
├── global_hotkey.py        # 全局快捷键监听
├── realtime_file.py        # 文件版实时转写（带进度条）
└── test.py                 # Gradio 网页版
```

## 平台适配状态

| 平台 | 状态 | 说明 |
|------|------|------|
| macOS | ✅ 可用 | 使用 `pynput` + `rumps` + `sounddevice` |
| Fedora | 🚧 计划中 | 需替换 `rumps`（macOS only），适配 `pynput` 在 Wayland 下的限制 |

## Fedora 适配计划

1. **菜单栏/系统托盘**：`rumps` 仅支持 macOS，需替换为 `pystray`（跨平台）
2. **全局快捷键**：`pynput` 在 Wayland 下受限，需调研 `evdev` 或 DBus 方案
3. **音频采集**：`sounddevice` 跨平台可用，无需改动
4. **键盘输入**：`pynput` 在 X11 下可用，Wayland 需调研 `ydotool` 或 `wtype`

## License

MIT
