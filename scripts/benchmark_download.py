"""Repeatable, opt-in yt-dlp throughput benchmark for YTDownloader.

This script deliberately uses a short public sample and never runs as part of pytest.
It compares the real CLI with the app's real DownloadService while holding URL,
format IDs, network policy, yt-dlp version, and toolchain constant.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
import re
import statistics
import subprocess
import sys
import threading
import time
from typing import Any
import uuid

import yt_dlp
import yt_dlp.version

from yt_downloader.core.models import DownloadRequest, FormatOption, VideoInfo
from yt_downloader.infrastructure.runtime import find_tool
from yt_downloader.services.download_service import DownloadService
from yt_downloader.services.download_tuning import choose_auto_fragment_count
from yt_downloader.services.error_report_service import redact_sensitive
from yt_downloader.services.network_policy import NetworkPolicy


DEFAULT_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
DEFAULT_FORMAT = "bestvideo[height<=360]+bestaudio/best[height<=360]"


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    runner: str
    fragments: int | None


@dataclass(frozen=True, slots=True)
class RunMetric:
    scenario: str
    repetition: int
    succeeded: bool
    wall_seconds: float
    bytes_downloaded: int
    throughput_bytes_per_second: float
    ttfb_seconds: float | None
    retries: int
    fragment_errors: int
    error: str | None = None


class _CaptureHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(redact_sensitive(record.getMessage()))


def _network_args(policy: NetworkPolicy) -> list[str]:
    snapshot = policy.snapshot()
    if snapshot.mode == "direct":
        return ["--proxy", ""]
    if snapshot.mode == "custom":
        return ["--proxy", snapshot.custom_proxy_url]
    return []


def _tool_args(deno: Path, ffmpeg: Path) -> list[str]:
    return ["--js-runtimes", f"deno:{deno}", "--ffmpeg-location", str(ffmpeg.parent)]


def _resolve_video(url: str, selector: str, policy: NetworkPolicy, deno: Path) -> tuple[VideoInfo, FormatOption, str]:
    options: dict[str, Any] = {
        "ignoreconfig": True,
        "noplaylist": True,
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "format": selector,
        "js_runtimes": {"deno": {"path": str(deno)}},
        "remote_components": [],
    }
    options.update(policy.ytdlp_options())
    with yt_dlp.YoutubeDL(options) as ydl:
        raw = ydl.extract_info(url, download=False)
        info = ydl.sanitize_info(raw)
    requested = list(info.get("requested_formats") or [info])
    ids = [str(item["format_id"]) for item in requested]
    exact_selector = "+".join(ids)
    video_stream = next((item for item in requested if item.get("vcodec") not in {None, "none"}), requested[0])
    audio_stream = next((item for item in requested if item.get("acodec") not in {None, "none"}), requested[-1])
    size_values: list[int] = []
    estimated = False
    complete_size = True
    for item in requested:
        exact = item.get("filesize")
        approximate = item.get("filesize_approx")
        value = exact if isinstance(exact, int) and exact > 0 else approximate
        if not isinstance(value, int) or value <= 0:
            complete_size = False
            continue
        size_values.append(value)
        estimated = estimated or exact is None
    option = FormatOption(
        label="Benchmark exact format",
        height=int(video_stream.get("height") or 0),
        fps=float(video_stream.get("fps") or 0),
        vcodec=str(video_stream.get("vcodec") or "none"),
        acodec=str(audio_stream.get("acodec") or "none"),
        container=str(info.get("ext") or video_stream.get("ext") or "mp4").upper(),
        final_ext=str(info.get("ext") or video_stream.get("ext") or "mp4"),
        format_selector=exact_selector,
        estimated_size=sum(size_values) if complete_size else None,
        requires_merge=len(requested) > 1,
        video_format_id=str(video_stream["format_id"]),
        audio_format_id=str(audio_stream["format_id"]) if len(requested) > 1 else None,
        is_recommended=True,
        size_is_estimate=estimated,
    )
    video = VideoInfo(
        video_id=str(info["id"]),
        url=str(info.get("webpage_url") or url),
        title=str(info.get("title") or "Benchmark video"),
        channel=str(info.get("channel") or info.get("uploader") or "Unknown"),
        duration=float(info["duration"]) if isinstance(info.get("duration"), (int, float)) else None,
        thumbnail_url=None,
        thumbnail_bytes=None,
        formats=(option,),
    )
    protocol = "+".join(str(item.get("protocol") or "unknown") for item in requested)
    return video, option, protocol


def _count_diagnostics(lines: list[str]) -> tuple[int, int]:
    retry_pattern = re.compile(r"retry|retrying", re.IGNORECASE)
    fragment_error_pattern = re.compile(r"fragment.*(?:error|fail)|(?:error|fail).*fragment", re.IGNORECASE)
    return (
        sum(bool(retry_pattern.search(line)) for line in lines),
        sum(bool(fragment_error_pattern.search(line)) for line in lines),
    )


def _run_app(
    scenario: Scenario,
    repetition: int,
    directory: Path,
    video: VideoInfo,
    option: FormatOption,
    policy: NetworkPolicy,
    deno: Path,
    ffmpeg: Path,
) -> RunMetric:
    first_progress: float | None = None
    started = time.monotonic()
    capture = _CaptureHandler()
    download_logger = logging.getLogger("yt_downloader.services.download_service")
    download_logger.addHandler(capture)
    try:
        service = DownloadService(
            deno_path=deno,
            ffmpeg_path=ffmpeg,
            network_policy=policy,
            concurrent_fragments=int(scenario.fragments or 0),
        )

        def progress(value) -> None:
            nonlocal first_progress
            if first_progress is None and (value.downloaded_bytes or 0) > 0:
                first_progress = time.monotonic()

        request = DownloadRequest(uuid.uuid4().hex, video, option, directory, f"app-{scenario.name}-{repetition}")
        result = service.download(request, progress, threading.Event())
        elapsed = time.monotonic() - started
        retries, fragment_errors = _count_diagnostics(capture.lines)
        return RunMetric(
            scenario.name, repetition, True, elapsed, result.file_size,
            result.file_size / elapsed, (first_progress - started) if first_progress else None,
            retries, fragment_errors,
        )
    except Exception as exc:
        elapsed = time.monotonic() - started
        retries, fragment_errors = _count_diagnostics(capture.lines)
        return RunMetric(
            scenario.name, repetition, False, elapsed, 0, 0.0,
            (first_progress - started) if first_progress else None,
            retries, fragment_errors, redact_sensitive(repr(exc)),
        )
    finally:
        download_logger.removeHandler(capture)


def _run_cli(
    scenario: Scenario,
    repetition: int,
    directory: Path,
    url: str,
    exact_selector: str,
    policy: NetworkPolicy,
    deno: Path,
    ffmpeg: Path,
) -> RunMetric:
    output = directory / f"cli-{repetition}.%(ext)s"
    command = [
        sys.executable, "-m", "yt_dlp", "--ignore-config", "--no-playlist", "--newline", "--progress",
        "--no-warnings", "--progress-template", "download:__PROGRESS__:%(progress.downloaded_bytes)s",
        "--print", "after_move:__RESULT__:%(filepath)s", "-f", exact_selector,
        "-o", str(output), *_tool_args(deno, ffmpeg), *_network_args(policy), url,
    ]
    started = time.monotonic()
    first_progress: float | None = None
    lines: list[str] = []
    result_path: Path | None = None
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert process.stdout is not None
    for line in process.stdout:
        cleaned = line.rstrip()
        lines.append(redact_sensitive(cleaned))
        if "__PROGRESS__:" in cleaned and first_progress is None:
            try:
                if float(cleaned.rsplit(":", 1)[-1]) > 0:
                    first_progress = time.monotonic()
            except ValueError:
                pass
        if cleaned.startswith("__RESULT__:"):
            result_path = Path(cleaned.removeprefix("__RESULT__:"))
    return_code = process.wait()
    elapsed = time.monotonic() - started
    retries, fragment_errors = _count_diagnostics(lines)
    if return_code == 0 and result_path and result_path.is_file():
        size = result_path.stat().st_size
        return RunMetric(
            scenario.name, repetition, True, elapsed, size, size / elapsed,
            (first_progress - started) if first_progress else None, retries, fragment_errors,
        )
    excerpt = " | ".join(lines[-5:])[-1200:]
    return RunMetric(
        scenario.name, repetition, False, elapsed, 0, 0.0,
        (first_progress - started) if first_progress else None,
        retries, fragment_errors, excerpt or f"yt-dlp exit code {return_code}",
    )


def _ordered(scenarios: list[Scenario], repetition: int) -> list[Scenario]:
    offset = (repetition - 1) % len(scenarios)
    result = scenarios[offset:] + scenarios[:offset]
    return list(reversed(result)) if repetition % 2 == 0 else result


def _summary(metrics: list[RunMetric]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in sorted({item.scenario for item in metrics}):
        selected = [item for item in metrics if item.scenario == name]
        succeeded = [item for item in selected if item.succeeded]
        result[name] = {
            "runs": len(selected),
            "successes": len(succeeded),
            "failures": len(selected) - len(succeeded),
            "median_throughput_bytes_per_second": statistics.median(
                item.throughput_bytes_per_second for item in succeeded
            ) if succeeded else 0.0,
            "median_wall_seconds": statistics.median(item.wall_seconds for item in succeeded) if succeeded else None,
            "total_retries": sum(item.retries for item in selected),
            "fragment_errors": sum(item.fragment_errors for item in selected),
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--format", default=DEFAULT_FORMAT)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--network-mode", choices=("system", "direct", "custom"), default="system")
    parser.add_argument("--proxy", default="")
    parser.add_argument("--work-dir", type=Path, default=Path(".tool-stage") / "benchmark-download")
    parser.add_argument("--report", type=Path, default=Path(".tool-stage") / "benchmark-download.json")
    parser.add_argument(
        "--scenario",
        action="append",
        choices=("cli_default", "app_default", "app_n1", "app_n4", "app_n8"),
        help="run only selected scenarios; repeat this option to select more than one",
    )
    args = parser.parse_args()
    if args.runs < 3:
        parser.error("--runs must be at least 3 so medians are meaningful")
    deno = find_tool("deno")
    ffmpeg = find_tool("ffmpeg")
    if not deno or not ffmpeg:
        raise SystemExit("Locked Deno and FFmpeg tools are required; run scripts/prepare_tools.ps1 first.")
    policy = NetworkPolicy(args.network_mode, args.proxy)
    video, option, protocol = _resolve_video(args.url, args.format, policy, deno)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    scenarios = [
        Scenario("cli_default", "cli", None),
        Scenario("app_default", "app", 0),
        Scenario("app_n1", "app", 1),
        Scenario("app_n4", "app", 4),
        Scenario("app_n8", "app", 8),
    ]
    if args.scenario:
        selected_names = set(args.scenario)
        scenarios = [item for item in scenarios if item.name in selected_names]
    metrics: list[RunMetric] = []
    for repetition in range(1, args.runs + 1):
        for scenario in _ordered(scenarios, repetition):
            run_dir = args.work_dir / f"r{repetition}-{scenario.name}"
            run_dir.mkdir(parents=True, exist_ok=True)
            print(f"[{repetition}/{args.runs}] {scenario.name}", flush=True)
            if scenario.runner == "cli":
                metric = _run_cli(
                    scenario, repetition, run_dir, video.url, option.format_selector,
                    policy, deno, ffmpeg,
                )
            else:
                metric = _run_app(
                    scenario, repetition, run_dir, video, option, policy, deno, ffmpeg,
                )
            metrics.append(metric)
            print(json.dumps(asdict(metric), ensure_ascii=False), flush=True)
    summary = _summary(metrics)
    samples = {
        count: [
            item.throughput_bytes_per_second for item in metrics
            if item.scenario == f"app_n{count}" and item.succeeded
        ]
        for count in (1, 4, 8)
    }
    failures = {
        count: sum(not item.succeeded for item in metrics if item.scenario == f"app_n{count}")
        for count in (1, 4, 8)
    }
    recommendation = choose_auto_fragment_count(samples, failures)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "yt_dlp_version": yt_dlp.version.__version__,
        "url": video.url,
        "video_id": video.video_id,
        "duration_seconds": video.duration,
        "format_selector": option.format_selector,
        "protocol": protocol,
        "network": policy.snapshot().safe_description,
        "runs_per_scenario": args.runs,
        "metrics": [asdict(item) for item in metrics],
        "summary": summary,
        "recommended_auto_fragment_count": recommendation,
        "decision_rule": "lowest error-free concurrency within 5% of fastest median throughput",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2), flush=True)
    print(f"recommended_auto_fragment_count={recommendation}", flush=True)
    print(f"report={args.report.resolve()}", flush=True)
    return 0 if all(item.succeeded for item in metrics) else 2


if __name__ == "__main__":
    raise SystemExit(main())
