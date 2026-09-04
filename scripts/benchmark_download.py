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
import os
from pathlib import Path
import re
import shutil
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
from yt_downloader.services.download_tuning import (
    BenchmarkTrafficBudget,
    choose_auto_fragment_count,
    needs_third_sample,
)
from yt_downloader.services.error_report_service import redact_sensitive
from yt_downloader.services.network_policy import NetworkPolicy


DEFAULT_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
DEFAULT_FORMAT = "bv*+ba/b"


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    runner: str
    fragments: int | None
    ignore_config: bool = True
    use_exact_format: bool = True


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
    format_selector: str = ""
    protocol: str = ""
    concurrent_fragments: int | None = None
    peak_speed_bytes_per_second: float = 0.0
    effective_proxy: str = ""


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
    protocol: str,
) -> RunMetric:
    first_progress: float | None = None
    peak_speed = 0.0
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
            nonlocal first_progress, peak_speed
            if first_progress is None and (value.downloaded_bytes or 0) > 0:
                first_progress = time.monotonic()
            if value.speed:
                peak_speed = max(peak_speed, float(value.speed))

        request = DownloadRequest(uuid.uuid4().hex, video, option, directory, f"app-{scenario.name}-{repetition}")
        result = service.download(request, progress, threading.Event())
        elapsed = time.monotonic() - started
        retries, fragment_errors = _count_diagnostics(capture.lines)
        transferred = max(result.file_size, option.estimated_size or 0)
        return RunMetric(
            scenario.name, repetition, True, elapsed, transferred,
            transferred / elapsed, (first_progress - started) if first_progress else None,
            retries, fragment_errors,
            format_selector=option.format_selector,
            protocol=protocol,
            concurrent_fragments=scenario.fragments,
            peak_speed_bytes_per_second=peak_speed,
            effective_proxy=policy.snapshot().safe_description,
        )
    except Exception as exc:
        elapsed = time.monotonic() - started
        retries, fragment_errors = _count_diagnostics(capture.lines)
        transferred = _directory_bytes(directory)
        return RunMetric(
            scenario.name, repetition, False, elapsed, transferred, 0.0,
            (first_progress - started) if first_progress else None,
            retries, fragment_errors, redact_sensitive(repr(exc)),
            format_selector=option.format_selector,
            protocol=protocol,
            concurrent_fragments=scenario.fragments,
            peak_speed_bytes_per_second=peak_speed,
            effective_proxy=policy.snapshot().safe_description,
        )
    finally:
        download_logger.removeHandler(capture)


def _run_cli(
    scenario: Scenario,
    repetition: int,
    directory: Path,
    url: str,
    exact_selector: str | None,
    policy: NetworkPolicy,
    deno: Path,
    ffmpeg: Path,
) -> RunMetric:
    output = (directory / f"cli-{repetition}.%(ext)s").resolve()
    command = [sys.executable, "-m", "yt_dlp"]
    if scenario.ignore_config:
        command.append("--ignore-config")
    command.extend([
        "--no-playlist", "--newline", "--progress", "--no-warnings",
        "--progress-template", "download:__PROGRESS__:%(progress.downloaded_bytes)s:%(progress.speed)s",
        "--print", "before_dl:__FORMAT__:%(format_id)s:%(protocol)s",
        "--print", "after_move:__RESULT__:%(filepath)s",
        "-o", str(output), *_tool_args(deno, ffmpeg), *_network_args(policy),
    ])
    if exact_selector:
        command.extend(["-f", exact_selector])
    if scenario.fragments:
        command.extend(["-N", str(scenario.fragments)])
    command.append(url)
    started = time.monotonic()
    first_progress: float | None = None
    lines: list[str] = []
    result_path: Path | None = None
    selected_format = exact_selector or "yt-dlp default"
    selected_protocol = "unknown"
    peak_speed = 0.0
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        shell=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        env={**os.environ, "PYTHONUTF8": "1"},
    )
    assert process.stdout is not None
    for line in process.stdout:
        cleaned = line.rstrip()
        lines.append(redact_sensitive(cleaned))
        if "__PROGRESS__:" in cleaned and first_progress is None:
            try:
                if float(cleaned.split(":")[-2]) > 0:
                    first_progress = time.monotonic()
            except ValueError:
                pass
        if "__PROGRESS__:" in cleaned:
            try:
                speed_text = cleaned.rsplit(":", 1)[-1]
                if speed_text not in {"NA", "None"}:
                    peak_speed = max(peak_speed, float(speed_text))
            except ValueError:
                pass
        if cleaned.startswith("__FORMAT__:"):
            _, selected_format, selected_protocol = cleaned.split(":", 2)
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
            format_selector=selected_format,
            protocol=selected_protocol,
            concurrent_fragments=scenario.fragments,
            peak_speed_bytes_per_second=peak_speed,
            effective_proxy=policy.snapshot().safe_description,
        )
    excerpt = " | ".join(lines[-5:])[-1200:]
    transferred = _directory_bytes(directory)
    return RunMetric(
        scenario.name, repetition, False, elapsed, transferred, 0.0,
        (first_progress - started) if first_progress else None,
        retries, fragment_errors, excerpt or f"yt-dlp exit code {return_code}",
        format_selector=selected_format,
        protocol=selected_protocol,
        concurrent_fragments=scenario.fragments,
        peak_speed_bytes_per_second=peak_speed,
        effective_proxy=policy.snapshot().safe_description,
    )


def _directory_bytes(directory: Path) -> int:
    return sum(
        path.stat().st_size
        for path in directory.rglob("*")
        if path.is_file()
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
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--format", default=DEFAULT_FORMAT)
    parser.add_argument("--runs", type=int, default=2)
    parser.add_argument("--traffic-limit-bytes", type=int, default=1_500_000_000)
    parser.add_argument("--initial-traffic-bytes", type=int, default=0)
    parser.add_argument("--network-mode", choices=("system", "direct", "custom"), default="system")
    parser.add_argument("--proxy", default="")
    parser.add_argument("--work-dir", type=Path, default=Path(".tool-stage") / "benchmark-download")
    parser.add_argument("--report", type=Path, default=Path(".tool-stage") / "benchmark-download.json")
    parser.add_argument(
        "--scenario",
        action="append",
        choices=(
            "cli_original", "cli_ignore_config", "app_current_default",
            "cli_parity", "app_parity", "app_n1", "app_n4", "app_n8",
        ),
        help="run only selected scenarios; repeat this option to select more than one",
    )
    args = parser.parse_args()
    if args.runs not in {2, 3}:
        parser.error("--runs must be 2 or 3")
    if args.traffic_limit_bytes <= 0:
        parser.error("--traffic-limit-bytes must be positive")
    if not 0 <= args.initial_traffic_bytes < args.traffic_limit_bytes:
        parser.error("--initial-traffic-bytes must be within the traffic limit")
    deno = find_tool("deno")
    ffmpeg = find_tool("ffmpeg")
    if not deno or not ffmpeg:
        raise SystemExit("Locked Deno and FFmpeg tools are required; run scripts/prepare_tools.ps1 first.")
    policy = NetworkPolicy(args.network_mode, args.proxy)
    video, option, protocol = _resolve_video(args.url, args.format, policy, deno)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    scenarios = [
        Scenario("cli_original", "cli", None, ignore_config=False, use_exact_format=False),
        Scenario("cli_ignore_config", "cli", None, use_exact_format=False),
        Scenario("app_current_default", "app", 0),
        Scenario("cli_parity", "cli", None),
        Scenario("app_parity", "app", 0),
        Scenario("app_n1", "app", 1),
        Scenario("app_n4", "app", 4),
        Scenario("app_n8", "app", 8),
    ]
    if args.scenario:
        selected_names = set(args.scenario)
        scenarios = [item for item in scenarios if item.name in selected_names]
    baseline_names = {"cli_original", "cli_ignore_config", "app_current_default"}
    budget = BenchmarkTrafficBudget(
        args.traffic_limit_bytes,
        args.initial_traffic_bytes,
    )
    estimated_run_bytes = option.estimated_size
    metrics: list[RunMetric] = []

    def run_scenario(scenario: Scenario, repetition: int) -> bool:
            if not budget.can_start(estimated_run_bytes):
                print(
                    f"traffic budget prevents {scenario.name}; "
                    f"consumed={budget.consumed_bytes} limit={budget.limit_bytes}",
                    flush=True,
                )
                return False
            run_dir = args.work_dir / f"r{repetition}-{scenario.name}"
            run_dir.mkdir(parents=True, exist_ok=True)
            print(f"[{repetition}/{args.runs}] {scenario.name}", flush=True)
            if scenario.runner == "cli":
                metric = _run_cli(
                    scenario, repetition, run_dir, video.url,
                    option.format_selector if scenario.use_exact_format else None,
                    policy, deno, ffmpeg,
                )
            else:
                metric = _run_app(
                    scenario, repetition, run_dir, video, option, policy, deno, ffmpeg, protocol,
                )
            metrics.append(metric)
            budget.record(metric.bytes_downloaded)
            print(json.dumps(asdict(metric), ensure_ascii=False), flush=True)
            shutil.rmtree(run_dir, ignore_errors=True)
            return True

    for scenario in scenarios:
        if scenario.name in baseline_names and not run_scenario(scenario, 1):
            break

    repeated = [item for item in scenarios if item.name not in baseline_names]
    for repetition in range(1, min(args.runs, 2) + 1):
        for scenario in _ordered(repeated, repetition):
            if not run_scenario(scenario, repetition):
                repeated = []
                break
        if not repeated:
            break

    if args.runs == 3:
        for scenario in repeated:
            samples = [
                item.throughput_bytes_per_second
                for item in metrics
                if item.scenario == scenario.name and item.succeeded
            ]
            if needs_third_sample(samples) and not run_scenario(scenario, 3):
                break
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
        "traffic_limit_bytes": budget.limit_bytes,
        "traffic_initial_bytes": args.initial_traffic_bytes,
        "traffic_consumed_bytes": budget.consumed_bytes,
        "metrics": [asdict(item) for item in metrics],
        "summary": summary,
        "recommended_auto_fragment_count": recommendation,
        "decision_rule": "lowest error-free concurrency within 5% of fastest median throughput",
        "parity_rule": "CLI and GUI medians within 10% indicate no material wrapper bottleneck",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2), flush=True)
    print(f"recommended_auto_fragment_count={recommendation}", flush=True)
    print(f"report={args.report.resolve()}", flush=True)
    return 0 if all(item.succeeded for item in metrics) else 2


if __name__ == "__main__":
    raise SystemExit(main())
