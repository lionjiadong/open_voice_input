## Open Voice Input Demo

This demo uses `uv` with Python `3.14.4` and sends local `.wav` files to a vLLM OpenAI-compatible realtime ASR endpoint over WebSocket.

### Endpoint

- Base URL: `http://120.55.162.96:18000/v1`
- Model: `./Qwen3-ASR-1.7B`

### Run

To transcribe all `.wav` files in the current directory:

```bash
uv run python main.py
```

If you want to pass one or more files explicitly:

```bash
uv run python main.py ./asr_en.wav
uv run python main.py ./asr_en.wav ./asr_zh.wav
```

The default client:

- converts the input audio to `PCM16 @ 16kHz mono`
- opens a WebSocket connection to `/v1/realtime`
- sends `session.update`
- streams audio via `input_audio_buffer.append`
- prints `transcription.delta` as it arrives

### Behavior

- Reads one or more `.wav` files from disk
- Connects to `/v1/realtime`
- Prints transcript text incrementally to stdout
- Separates multiple files with a divider line

If the deployed service has a server-side realtime issue, the client will print the WebSocket error returned by the server.
