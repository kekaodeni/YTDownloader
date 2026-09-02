from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from yt_downloader.core.errors import AppError
from yt_downloader.infrastructure.runtime import find_tool
from yt_downloader.infrastructure.windows_thumbnail import shell_thumbnail_matches
from yt_downloader.services.ffmpeg_service import ExplorerCoverStatus, FfmpegService


@pytest.mark.integration
def test_real_ffmpeg_probe_unicode_path_and_frame_extraction(tmp_path: Path) -> None:
    ffmpeg = find_tool("ffmpeg")
    ffprobe = find_tool("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg integration tools are unavailable")
    chinese = tmp_path / "中文 视频"
    chinese.mkdir()
    media = chinese / "含音频.mp4"
    subprocess.run([
        str(ffmpeg), "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=0x0067c0:s=320x180:d=2",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
        "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        "-y", str(media),
    ], shell=False, check=True, capture_output=True)
    service = FfmpegService(ffmpeg, ffprobe)

    assert 1.8 <= service.probe_duration(media) <= 2.2
    assert service.has_audio_and_video(media)
    thumbnail = service.extract_frame(media, 1.0, chinese / "缩略图.jpg", duration=2.0)
    assert thumbnail.is_file()
    assert thumbnail.stat().st_size > 0


@pytest.mark.integration
def test_real_ffmpeg_embeds_one_cover_without_reencoding_unicode_media(tmp_path: Path) -> None:
    ffmpeg = find_tool("ffmpeg")
    ffprobe = find_tool("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg integration tools are unavailable")
    directory = tmp_path / "封面 媒体😀"
    directory.mkdir()
    media = directory / "原视频.mp4"
    subprocess.run([
        str(ffmpeg), "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc2=s=320x180:d=2:r=24",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
        "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
        "-metadata", "title=保留的标题", "-y", str(media),
    ], shell=False, check=True, capture_output=True)
    service = FfmpegService(
        ffmpeg,
        ffprobe,
        shell_thumbnail_checker=lambda _candidate, _cover: True,
    )
    cover = service.extract_frame(media, 1.0, directory / "临时预览.jpg", duration=2.0)
    before = service.probe(media)

    result = service.embed_cover(media, cover)

    after = service.probe(media)
    before_streams = [
        (stream.get("codec_type"), stream.get("codec_name"))
        for stream in before["streams"]
        if not stream.get("disposition", {}).get("attached_pic")
    ]
    after_streams = [
        (stream.get("codec_type"), stream.get("codec_name"))
        for stream in after["streams"]
        if not stream.get("disposition", {}).get("attached_pic")
    ]
    covers = [stream for stream in after["streams"] if stream.get("disposition", {}).get("attached_pic")]
    assert before_streams == after_streams
    assert len(covers) == 1
    assert after["format"]["tags"]["title"] == "保留的标题"
    assert result.media_validated
    assert result.explorer_status is ExplorerCoverStatus.MATCHED
    assert not list(directory.glob(".*.cover-candidate.*"))
    replacement_cover = service.extract_frame(media, 0.25, directory / "第二张临时预览.jpg", duration=2.0)
    service.embed_cover(media, replacement_cover)
    replaced_probe = service.probe(media)
    assert len([
        stream for stream in replaced_probe["streams"]
        if stream.get("disposition", {}).get("attached_pic")
    ]) == 1

    actual_shell_result = shell_thumbnail_matches(media, replacement_cover)
    assert actual_shell_result is None or isinstance(actual_shell_result, bool)

    original_bytes = media.read_bytes()
    validation_failure = FfmpegService(
        ffmpeg,
        ffprobe,
        shell_thumbnail_checker=lambda _candidate, _cover: True,
    )

    def reject_candidate(*_args) -> None:
        raise AppError("forced_validation_failure", "验证失败", "forced by regression test")

    validation_failure._validate_cover_candidate = reject_candidate  # type: ignore[method-assign]
    try:
        validation_failure.embed_cover(media, cover)
    except AppError as error:
        assert error.code == "forced_validation_failure"
    else:
        pytest.fail("candidate validation failure was not propagated")
    assert media.read_bytes() == original_bytes
    assert not list(directory.glob(".*.cover-candidate.*"))


@pytest.mark.integration
def test_unsupported_cover_container_is_unchanged(tmp_path: Path) -> None:
    ffmpeg = find_tool("ffmpeg")
    ffprobe = find_tool("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg integration tools are unavailable")
    media = tmp_path / "视频.webm"
    cover = tmp_path / "封面.jpg"
    media.write_bytes(b"original-webm-bytes")
    Image = pytest.importorskip("PIL.Image")
    Image.new("RGB", (32, 18), "blue").save(cover, "JPEG")

    try:
        FfmpegService(ffmpeg, ffprobe).embed_cover(media, cover)
    except AppError as error:
        assert error.code == "cover_container_unsupported"
    else:
        pytest.fail("unsupported container was accepted")

    assert media.read_bytes() == b"original-webm-bytes"
