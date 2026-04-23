# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: Copyright contributors to the vLLM project
"""
Minimal Gradio demo for real-time speech transcription using the vLLM Realtime API.

Start the vLLM server first:

    vllm serve mistralai/Voxtral-Mini-4B-Realtime-2602 --enforce-eager

Then run this script:

    python openai_realtime_microphone_client.py --host localhost --port 8000

Use --share to create a public Gradio link.

Requirements: websockets, numpy, gradio
"""

import argparse
import asyncio
import json
import queue
import threading
from typing import Any

import gradio as gr
import numpy as np
import pybase64 as base64
import websockets

SAMPLE_RATE = 16_000

# Global state
audio_queue: queue.Queue = queue.Queue()
transcription_text = ""
is_running = False
ws_url = ""
model = ""
last_error = ""


def format_message(message: str | bytes) -> str:
    if isinstance(message, bytes):
        return message.decode("utf-8", errors="replace")
    return message


async def websocket_handler():
    """Connect to WebSocket and handle audio streaming + transcription."""
    global last_error, transcription_text, is_running

    headers = {"Authorization": "Bearer Ljd@1234", "OpenAI-Beta": "realtime=v1"}

    async with websockets.connect(ws_url, additional_headers=headers, proxy=None) as ws:
        session_message = format_message(await ws.recv())
        print(f"session event: {session_message}")

        await ws.send(json.dumps({"type": "session.update", "model": model}))
        await ws.send(json.dumps({"type": "input_audio_buffer.commit"}))

        async def send_audio():
            while is_running:
                try:
                    chunk = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: audio_queue.get(timeout=0.1)
                    )
                    await ws.send(json.dumps({"type": "input_audio_buffer.append", "audio": chunk}))
                except queue.Empty:
                    continue

            await ws.send(json.dumps({"type": "input_audio_buffer.commit", "final": True}))

        async def receive_transcription():
            global transcription_text
            async for message in ws:
                data = json.loads(format_message(message))
                event_type = data.get("type")
                print(f"realtime event: {event_type}")
                if data.get("type") == "transcription.delta":
                    transcription_text += data["delta"]
                elif event_type == "transcription.done":
                    transcription_text = data.get("text", transcription_text)
                    return
                elif event_type == "error":
                    last_error = json.dumps(data, ensure_ascii=False)
                    raise RuntimeError(last_error)

        await asyncio.gather(send_audio(), receive_transcription())


def start_websocket():
    """Start WebSocket connection in background thread."""
    global is_running, last_error
    is_running = True
    last_error = ""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(websocket_handler())
    except Exception as e:
        last_error = str(e)
        print(f"WebSocket error: {e}")


def start_recording():
    """Start the transcription service."""
    global transcription_text
    transcription_text = ""
    thread = threading.Thread(target=start_websocket, daemon=True)
    thread.start()
    return gr.update(interactive=False), gr.update(interactive=True), ""


def stop_recording():
    """Stop the transcription service."""
    global is_running, last_error
    is_running = False
    final_text = transcription_text
    if last_error:
        final_text = f"[websocket error] {last_error}\n{final_text}".strip()
    return gr.update(interactive=True), gr.update(interactive=False), final_text


def process_audio(audio: Any):
    """Process incoming audio and queue for streaming."""
    global transcription_text

    if audio is None or not is_running:
        return transcription_text

    sample_rate, audio_data = audio

    # Convert to mono if stereo
    if len(audio_data.shape) > 1:
        audio_data = audio_data.mean(axis=1)

    # Normalize to float
    if audio_data.dtype == np.int16:
        audio_float = audio_data.astype(np.float32) / 32767.0
    else:
        audio_float = audio_data.astype(np.float32)

    # Resample to 16kHz if needed
    if sample_rate != SAMPLE_RATE:
        num_samples = int(len(audio_float) * SAMPLE_RATE / sample_rate)
        audio_float = np.interp(
            np.linspace(0, len(audio_float) - 1, num_samples),
            np.arange(len(audio_float)),
            audio_float,
        )

    # Convert to PCM16 and base64 encode
    audio_float = np.nan_to_num(audio_float, nan=0.0, posinf=1.0, neginf=-1.0)
    audio_float = np.clip(audio_float, -1.0, 1.0)
    pcm16 = (audio_float * 32767).astype(np.int16)
    b64_chunk = base64.b64encode(pcm16.tobytes()).decode("utf-8")
    audio_queue.put(b64_chunk)

    return transcription_text


# Gradio interface
with gr.Blocks(title="Real-time Speech Transcription") as demo:
    gr.Markdown("# Real-time Speech Transcription")
    gr.Markdown(
        "Click **Start** and speak into your microphone. "
        "The audio timeline stays above and the live transcript updates below it."
    )

    with gr.Row():
        start_btn = gr.Button("Start", variant="primary")
        stop_btn = gr.Button("Stop", variant="stop", interactive=False)

    audio_input = gr.Audio(
        label="Audio Timeline",
        sources=["microphone"],
        streaming=True,
        type="numpy",
        waveform_options=gr.WaveformOptions(
            show_recording_waveform=True,
            waveform_progress_color="#2563eb",
            waveform_color="#93c5fd",
            trim_region_color="#bfdbfe",
            sample_rate=SAMPLE_RATE,
        ),
    )
    transcription_output = gr.Textbox(
        label="Live Transcript",
        lines=8,
        max_lines=12,
        autoscroll=True,
        placeholder="Recognition text will appear under the audio progress bar.",
    )

    start_btn.click(start_recording, outputs=[start_btn, stop_btn, transcription_output])
    stop_btn.click(stop_recording, outputs=[start_btn, stop_btn, transcription_output])
    audio_input.stream(process_audio, inputs=[audio_input], outputs=[transcription_output])

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Realtime WebSocket Transcription with Gradio")
    parser.add_argument(
        "--model",
        type=str,
        default="./Qwen3-ASR-1.7B",
        help="Model that is served and should be pinged.",
    )
    parser.add_argument("--host", type=str, default="localhost", help="vLLM server host")
    parser.add_argument("--port", type=int, default=8000, help="vLLM server port")
    parser.add_argument("--share", action="store_true", help="Create public Gradio link")
    args = parser.parse_args()

    ws_url = f"ws://{args.host}:{args.port}/v1/realtime"
    model = args.model
    demo.launch(share=args.share)
