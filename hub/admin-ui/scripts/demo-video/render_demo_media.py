#!/usr/bin/env python3
"""Render local SAPI narration, captions, and the ComfyUI music bed into a tour MP4."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def media_duration(ffprobe: str, path: Path) -> float:
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def probe(ffprobe: str, path: Path) -> dict:
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "stream=index,codec_name,codec_type,width,height,channels,sample_rate:format=duration,size,bit_rate",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def vtt_timestamp(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    whole_seconds, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02}:{minutes:02}:{whole_seconds:02}.{milliseconds:03}"


def atempo_filters(factor: float) -> list[str]:
    filters: list[str] = []
    while factor > 2.0:
        filters.append("atempo=2.0")
        factor /= 2.0
    while factor < 0.5:
        filters.append("atempo=0.5")
        factor /= 0.5
    if abs(factor - 1.0) > 0.001:
        filters.append(f"atempo={factor:.6f}")
    return filters


def windows_path(path: Path) -> str:
    result = subprocess.run(
        ["wslpath", "-w", str(path.resolve())],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parents[3]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--locale", choices=("ja", "en"), required=True)
    parser.add_argument("--tour", type=Path, default=script_dir / "tour.json")
    parser.add_argument("--video", type=Path)
    parser.add_argument("--timeline", type=Path)
    parser.add_argument("--bgm", type=Path, default=Path("/tmp/inas-demo-video/inas-demo-bgm.flac"))
    parser.add_argument("--work-dir", type=Path, default=Path("/tmp/inas-demo-video"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--poster", type=Path)
    parser.add_argument("--vtt", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument(
        "--powershell",
        default="/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
    )
    parser.add_argument("--update-compatibility", action="store_true")
    args = parser.parse_args()

    locale = args.locale
    args.video = args.video or args.work_dir / f"demo-{locale}-silent.mp4"
    args.timeline = args.timeline or args.work_dir / f"demo-{locale}-timeline.json"
    args.output = args.output or repo_root / "lp" / "assets" / f"demo-{locale}.mp4"
    args.poster = args.poster or repo_root / "lp" / "assets" / f"demo-{locale}-poster.jpg"
    args.vtt = args.vtt or repo_root / "lp" / "assets" / f"demo-{locale}.vtt"
    args.report = args.report or args.work_dir / f"demo-{locale}-render.json"

    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise SystemExit("ffmpeg and ffprobe must be available on PATH")
    for required in (args.video, args.timeline, args.bgm, args.tour):
        if not required.is_file():
            raise SystemExit(f"required input does not exist: {required}")

    tour = json.loads(args.tour.read_text(encoding="utf-8"))
    localized = tour["locales"][locale]
    timeline = json.loads(args.timeline.read_text(encoding="utf-8"))
    if timeline["locale"] != locale:
        raise SystemExit(f"timeline locale is {timeline['locale']}, expected {locale}")
    total_duration = float(timeline["duration_seconds"])
    scene_copy = localized["scenes"]
    scene_timing = {item["id"]: item for item in timeline["scenes"]}
    if set(scene_copy) != set(scene_timing):
        raise SystemExit("tour scenes and captured timeline scenes do not match")

    locale_work = args.work_dir / f"tts-{locale}"
    raw_dir = locale_work / "raw"
    processed_dir = locale_work / "processed"
    raw_dir.mkdir(parents=True, exist_ok=True)
    processed_dir.mkdir(parents=True, exist_ok=True)
    tts_spec_path = locale_work / "tts-spec.json"
    tts_spec = {
        "voice": localized["voice"],
        "ssml_language": localized["ssml_language"],
        "rate_percent": localized["rate_percent"],
        "volume_percent": localized["volume_percent"],
        "lines": [{"id": scene_id, "spoken_text": scene["narration"]} for scene_id, scene in scene_copy.items()],
    }
    tts_spec_path.write_text(json.dumps(tts_spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    tts_script = script_dir / "render_demo_tts.ps1"
    run(
        [
            args.powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            windows_path(tts_script),
            "-SpecPath",
            windows_path(tts_spec_path),
            "-OutputDirectory",
            windows_path(raw_dir),
        ]
    )

    rendered_lines: list[dict] = []
    for scene_id, scene in scene_copy.items():
        timing = scene_timing[scene_id]
        raw_path = raw_dir / f"{scene_id}.wav"
        trimmed_path = processed_dir / f"{scene_id}-trimmed.wav"
        output_path = processed_dir / f"{scene_id}.wav"
        trim_filter = (
            "silenceremove=start_periods=1:start_duration=0.02:start_threshold=-45dB,"
            "areverse,"
            "silenceremove=start_periods=1:start_duration=0.02:start_threshold=-45dB,"
            "areverse,apad=pad_dur=0.10,aresample=48000"
        )
        run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(raw_path),
                "-af",
                trim_filter,
                "-ar",
                "48000",
                "-ac",
                "2",
                str(trimmed_path),
            ]
        )
        trimmed_duration = media_duration(ffprobe, trimmed_path)
        lead_seconds = 0.25
        tail_seconds = 0.30
        available_duration = float(timing["duration_seconds"]) - lead_seconds - tail_seconds
        tempo = max(1.0, trimmed_duration / available_duration)
        speed_filters = atempo_filters(tempo)
        if speed_filters:
            run(
                [
                    ffmpeg,
                    "-y",
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-i",
                    str(trimmed_path),
                    "-af",
                    ",".join(speed_filters),
                    "-ar",
                    "48000",
                    "-ac",
                    "2",
                    str(output_path),
                ]
            )
        else:
            shutil.copy2(trimmed_path, output_path)
        rendered_duration = media_duration(ffprobe, output_path)
        if rendered_duration > available_duration + 0.05:
            raise SystemExit(f"{scene_id} narration is {rendered_duration:.3f}s; available duration is {available_duration:.3f}s")
        start = float(timing["start_seconds"]) + lead_seconds
        end = min(float(timing["end_seconds"]) - 0.15, start + rendered_duration + 0.15)
        rendered_lines.append(
            {
                "id": scene_id,
                "path": output_path,
                "start_seconds": start,
                "end_seconds": end,
                "duration_seconds": rendered_duration,
                "tempo": tempo,
                "caption_text": scene["narration"],
            }
        )

    vtt_lines = ["WEBVTT", ""]
    for line in rendered_lines:
        vtt_lines.extend(
            [
                f"{vtt_timestamp(line['start_seconds'])} --> {vtt_timestamp(line['end_seconds'])}",
                line["caption_text"],
                "",
            ]
        )
    args.vtt.parent.mkdir(parents=True, exist_ok=True)
    args.vtt.write_text("\n".join(vtt_lines), encoding="utf-8")

    voice_mix_path = locale_work / "voices.wav"
    voice_command = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "warning",
    ]
    for line in rendered_lines:
        voice_command.extend(["-i", str(line["path"])])

    voice_filters: list[str] = []
    voice_labels: list[str] = []
    for input_index, line in enumerate(rendered_lines):
        delay = round(float(line["start_seconds"]) * 1000)
        label = f"voice{input_index}"
        voice_filters.append(
            f"[{input_index}:a]aresample=48000,"
            "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
            "loudnorm=I=-17:LRA=7:TP=-1.5,"
            "aresample=48000,"
            f"adelay={delay}|{delay}[{label}]"
        )
        voice_labels.append(f"[{label}]")
    voice_filters.append(
        "".join(voice_labels) + f"amix=inputs={len(voice_labels)}:duration=longest:normalize=0,"
        "aresample=48000,aformat=sample_fmts=s16:sample_rates=48000:channel_layouts=stereo,"
        f"apad=pad_dur={total_duration:.3f},atrim=duration={total_duration:.3f},"
        "asetpts=N/SR/TB[voices]"
    )
    voice_command.extend(
        [
            "-filter_complex",
            ";".join(voice_filters),
            "-map",
            "[voices]",
            "-c:a",
            "pcm_s16le",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-t",
            f"{total_duration:.3f}",
            str(voice_mix_path),
        ]
    )
    run(voice_command)
    voice_duration = media_duration(ffprobe, voice_mix_path)
    if abs(voice_duration - total_duration) > 0.15:
        raise SystemExit(f"voice mix is {voice_duration:.3f}s; expected {total_duration:.3f}s")

    mixed_audio_path = locale_work / "mixed.wav"
    mix_command = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-stream_loop",
        "-1",
        "-i",
        str(args.bgm),
        "-i",
        str(voice_mix_path),
    ]

    fade_out_start = max(0.0, total_duration - 1.6)
    filters = [
        "[0:a]"
        f"atrim=duration={total_duration:.3f},asetpts=N/SR/TB,"
        "loudnorm=I=-27:LRA=9:TP=-4,"
        "aresample=48000,aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
        "afade=t=in:st=0:d=1.2,"
        f"afade=t=out:st={fade_out_start:.3f}:d=1.5[bed]"
    ]
    filters.append(
        "[1:a]aresample=48000,"
        "aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo,"
        f"atrim=duration={total_duration:.3f},asplit=2[sidechain][voice_mix]"
    )
    filters.append("[bed][sidechain]sidechaincompress=threshold=0.015:ratio=10:attack=12:release=280:knee=3[ducked]")
    filters.append(
        "[ducked][voice_mix]amix=inputs=2:duration=first:normalize=0,"
        "alimiter=limit=0.95,aresample=48000,"
        "aformat=sample_fmts=s16:sample_rates=48000:channel_layouts=stereo,"
        f"apad=pad_dur=1,atrim=duration={total_duration:.3f},asetpts=N/SR/TB[outa]"
    )

    audio_language = "jpn" if locale == "ja" else "eng"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    mix_command.extend(
        [
            "-filter_complex",
            ";".join(filters),
            "-map",
            "[outa]",
            "-c:a",
            "pcm_s16le",
            "-ar",
            "48000",
            "-ac",
            "2",
            "-t",
            f"{total_duration:.3f}",
            str(mixed_audio_path),
        ]
    )
    run(mix_command)
    mixed_duration = media_duration(ffprobe, mixed_audio_path)
    if abs(mixed_duration - total_duration) > 0.05:
        raise SystemExit(f"mixed audio is {mixed_duration:.3f}s; expected {total_duration:.3f}s")

    run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-i",
            str(args.video),
            "-i",
            str(mixed_audio_path),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-metadata:s:a:0",
            f"language={audio_language}",
            "-metadata",
            f"title={localized['dialog_title']}",
            "-movflags",
            "+faststart",
            "-t",
            f"{total_duration:.3f}",
            str(args.output),
        ]
    )

    args.poster.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "warning",
            "-ss",
            "1.5",
            "-i",
            str(args.output),
            "-frames:v",
            "1",
            "-update",
            "1",
            "-q:v",
            "2",
            str(args.poster),
        ]
    )

    if args.update_compatibility:
        if locale != "ja":
            raise SystemExit("--update-compatibility may only be used with --locale ja")
        shutil.copy2(args.output, repo_root / "lp" / "assets" / "demo.mp4")
        shutil.copy2(args.poster, repo_root / "lp" / "assets" / "demo-poster.jpg")

    report = {
        "locale": locale,
        "voice": localized["voice"],
        "video": str(args.output),
        "poster": str(args.poster),
        "captions": str(args.vtt),
        "bgm": str(args.bgm),
        "duration_seconds": total_duration,
        "lines": [{key: value for key, value in line.items() if key != "path"} for line in rendered_lines],
        "probe": probe(ffprobe, args.output),
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
