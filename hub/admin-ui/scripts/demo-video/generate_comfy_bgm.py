#!/usr/bin/env python3
"""Generate the product-tour music bed with ComfyUI ACE-Step 1.5."""

from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


def request_json(url: str, *, payload: dict | None = None) -> dict:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"ComfyUI returned HTTP {error.code}: {detail}") from error


def workflow(music: dict) -> dict:
    seed = int(music["seed"])
    duration = float(music["duration_seconds"])
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": music["model"]},
        },
        "2": {
            "class_type": "ModelSamplingAuraFlow",
            "inputs": {"model": ["1", 0], "shift": 3.0},
        },
        "3": {
            "class_type": "TextEncodeAceStepAudio1.5",
            "inputs": {
                "clip": ["1", 1],
                "tags": music["tags"],
                "lyrics": music["lyrics"],
                "seed": seed,
                "bpm": int(music["bpm"]),
                "duration": duration,
                "timesignature": music["time_signature"],
                "language": music["language"],
                "keyscale": music["key_scale"],
                "generate_audio_codes": True,
                "cfg_scale": 2.0,
                "temperature": 0.85,
                "top_p": 0.9,
                "top_k": 0,
                "min_p": 0.0,
            },
        },
        "4": {
            "class_type": "ConditioningZeroOut",
            "inputs": {"conditioning": ["3", 0]},
        },
        "5": {
            "class_type": "EmptyAceStep1.5LatentAudio",
            "inputs": {"seconds": duration, "batch_size": 1},
        },
        "6": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["2", 0],
                "positive": ["3", 0],
                "negative": ["4", 0],
                "latent_image": ["5", 0],
                "seed": seed,
                "steps": 8,
                "cfg": 1.0,
                "sampler_name": "euler",
                "scheduler": "simple",
                "denoise": 1.0,
            },
        },
        "7": {
            "class_type": "VAEDecodeAudio",
            "inputs": {"samples": ["6", 0], "vae": ["1", 2]},
        },
        "8": {
            "class_type": "SaveAudio",
            "inputs": {
                "audio": ["7", 0],
                "filename_prefix": "inas_demo_bgm/inas-demo-bgm",
            },
        },
    }


def find_audio(history: dict) -> dict:
    for output in history.get("outputs", {}).values():
        for key in ("audio", "audios"):
            items = output.get(key, [])
            if items:
                return items[0]
    raise RuntimeError(f"ComfyUI completed without an audio output: {json.dumps(history)[:2000]}")


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", default="http://127.0.0.1:8188")
    parser.add_argument("--tour", type=Path, default=script_dir / "tour.json")
    parser.add_argument("--output", type=Path, default=Path("/tmp/inas-demo-video/inas-demo-bgm.flac"))
    parser.add_argument("--report", type=Path, default=Path("/tmp/inas-demo-video/inas-demo-bgm.json"))
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.output.exists() and not args.force:
        print(json.dumps({"output": str(args.output), "status": "reused"}, indent=2))
        return

    tour = json.loads(args.tour.read_text(encoding="utf-8"))
    music = tour["music"]
    base_url = args.server.rstrip("/")
    request_json(f"{base_url}/system_stats")

    client_id = str(uuid.uuid4())
    prompt = workflow(music)
    queued = request_json(
        f"{base_url}/prompt",
        payload={"prompt": prompt, "client_id": client_id},
    )
    prompt_id = queued["prompt_id"]
    deadline = time.monotonic() + args.timeout
    history_entry = None
    while time.monotonic() < deadline:
        history = request_json(f"{base_url}/history/{prompt_id}")
        history_entry = history.get(prompt_id)
        if history_entry:
            status = history_entry.get("status", {})
            if status.get("status_str") == "error" or not status.get("completed", True):
                raise RuntimeError(f"ComfyUI generation failed: {json.dumps(status)}")
            if history_entry.get("outputs"):
                break
        time.sleep(2)
    else:
        raise TimeoutError(f"ComfyUI did not finish prompt {prompt_id} within {args.timeout}s")

    audio = find_audio(history_entry)
    query = urllib.parse.urlencode(
        {
            "filename": audio["filename"],
            "subfolder": audio.get("subfolder", ""),
            "type": audio.get("type", "output"),
        }
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(f"{base_url}/view?{query}", timeout=120) as response:
        args.output.write_bytes(response.read())

    report = {
        "generator": "ComfyUI ACE-Step 1.5",
        "prompt_id": prompt_id,
        "output": str(args.output),
        "source": audio,
        "music": music,
        "workflow": prompt,
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "report": str(args.report), "prompt_id": prompt_id}, indent=2))


if __name__ == "__main__":
    main()
