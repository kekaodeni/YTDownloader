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
@pytest.mark.parametrize("suffix", [".mp4", ".m4v", ".mkv"])
@pytest.mark.parametrize("image_kind", ["JPEG", "PNG"])
def test_real_ffmpeg_embeds_one_cover_without_reencoding_unicode_media(tmp_path: Path, suffix: str, image_kind: str) -> None:
    ffmpeg = find_tool("ffmpeg")
    ffprobe = find_tool("ffprobe")
    if not ffmpeg or not ffprobe:
        pytest.skip("FFmpeg integration tools are unavailable")
    directory = tmp_path / "封面 媒体😀"
    directory.mkdir()
    media = directory / ("原视频" + suffix)
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
    if image_kind == "PNG":
        from PIL import Image
        png = cover.with_suffix(".png")
        with Image.open(cover) as image:
            image.save(png, "PNG")
        cover = png
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
    if suffix == ".mkv":
        cover_tags = covers[0].get("tags", {})
        expected_extension, expected_mime = (
            ("png", "image/png") if image_kind == "PNG" else ("jpg", "image/jpeg")
        )
        assert cover_tags.get("filename") == f"cover.{expected_extension}"
        assert cover_tags.get("mimetype") == expected_mime
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


@pytest.mark.integration
@pytest.mark.parametrize("suffix", [".webm", ".mov", ".avi", ".flv", ".ts", ".m2ts", ".mpg", ".ogv", ".wmv", ".3gp"])
def test_cover_copy_is_lossless_keeps_original_and_never_overwrites(tmp_path, suffix):
    import threading
    from yt_downloader.core.errors import OperationCancelled
    service = FfmpegService(shell_thumbnail_checker=lambda *_: None)
    if not service.available:
        pytest.skip("FFmpeg unavailable")
    media = tmp_path / ("副本来源😀" + suffix)
    video, audio = {
        ".webm": ("libvpx-vp9", "libopus"), ".mov": ("libx264", "aac"),
        ".avi": ("mpeg4", "libmp3lame"), ".flv": ("flv1", "libmp3lame"),
        ".ts": ("mpeg2video", "mp2"), ".m2ts": ("mpeg2video", "mp2"),
        ".mpg": ("mpeg2video", "mp2"), ".ogv": ("libtheora", "libvorbis"),
        ".wmv": ("msmpeg4", "wmav2"), ".3gp": ("libx264", "aac"),
    }[suffix]
    codecs = ["-c:v", video, "-c:a", audio]
    service._run([str(service.ffmpeg_path), "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=160x90:d=1:r=25",
                  "-f", "lavfi", "-i", "sine=duration=1", "-shortest", *codecs,
                  "-metadata", "title=原始标题", "-y", str(media)])
    original = media.read_bytes()
    cover = service.extract_frame(media, .2, tmp_path / "cover.jpg")
    destination = tmp_path / "副本.mkv"
    def stream_hash(path):
        output = service._run([str(service.ffmpeg_path), "-v", "error", "-i", str(path),
                               "-map", "0:0", "-map", "0:1", "-c", "copy", "-f", "streamhash", "-hash", "sha256", "-"]).stdout
        return [line for line in output.splitlines() if line and not line.startswith("#")]
    before_hash = stream_hash(media)
    result = service.embed_cover(media, cover, output_path=destination)
    assert result.file_path == destination
    assert result.media_validated
    assert media.read_bytes() == original
    assert stream_hash(destination) == before_hash
    assert len([s for s in service.probe(destination)["streams"] if service._is_cover_stream(s)]) == 1
    saved = destination.read_bytes()
    with pytest.raises(AppError, match="目标文件已存在"):
        service.embed_cover(media, cover, output_path=destination)
    assert destination.read_bytes() == saved
    assert media.read_bytes() == original
    cancel = threading.Event()
    service.shell_thumbnail_checker = lambda *_: cancel.set()
    cancelled = tmp_path / "取消.mkv"
    with pytest.raises(OperationCancelled):
        service.embed_cover(media, cover, output_path=cancelled, cancel_event=cancel)
    assert not cancelled.exists()
    assert media.read_bytes() == original
    assert not list(tmp_path.glob(".*.cover-candidate.*"))


@pytest.mark.integration
def test_mkv_keeps_chapters_subtitles_and_unrelated_attachments(tmp_path):
    from PIL import Image
    service = FfmpegService(shell_thumbnail_checker=lambda *_: None)
    if not service.available:
        pytest.skip("FFmpeg unavailable")
    text = tmp_path / "note.txt"; text.write_text("keep this attachment", encoding="utf-8")
    back = tmp_path / "back.png"; Image.new("RGB", (30, 40), "blue").save(back)
    subtitle = tmp_path / "sub.srt"; subtitle.write_text("1\n00:00:00,000 --> 00:00:00,800\n保留字幕\n", encoding="utf-8")
    metadata = tmp_path / "chapters.txt"; metadata.write_text(";FFMETADATA1\ntitle=保留标题\n[CHAPTER]\nTIMEBASE=1/1000\nSTART=0\nEND=800\ntitle=第一章\n", encoding="utf-8")
    media = tmp_path / "with-attachments.mkv"
    service._run([str(service.ffmpeg_path), "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=160x90:d=1:r=15",
                  "-f", "lavfi", "-i", "sine=duration=1", "-i", str(subtitle), "-i", str(metadata),
                  "-map", "0", "-map", "1", "-map", "2", "-map_metadata", "3", "-map_chapters", "3",
                  "-c:v", "libx264", "-c:a", "aac", "-c:s", "srt", "-attach", str(text),
                  "-metadata:s:t:0", "mimetype=text/plain", "-metadata:s:t:0", "filename=note.txt", "-attach", str(back),
                  "-metadata:s:t:1", "mimetype=image/png", "-metadata:s:t:1", "filename=back.png", "-y", str(media)])
    before = service.probe(media)
    cover = service.extract_frame(media, .2, tmp_path / "cover.jpg")
    for _ in range(2):
        service.embed_cover(media, cover)
        after = service.probe(media)
        assert service._stream_signature(before) == service._stream_signature(after)
        assert service._chapter_signature(before) == service._chapter_signature(after)
        assert len(after["chapters"]) == 1
        assert len([s for s in after["streams"] if service._is_cover_stream(s)]) == 1
        assert {s.get("tags", {}).get("filename") for s in after["streams"]} >= {"note.txt", "back.png", "cover.jpg"}
        image_stream = next(s for s in after["streams"] if s.get("tags", {}).get("filename") == "back.png")
        preserved_image = tmp_path / "preserved.png"
        service._run([str(service.ffmpeg_path), "-v", "error", "-i", str(media), "-map", f"0:{image_stream['index']}",
                      "-c", "copy", "-frames:v", "1", "-f", "image2", "-y", str(preserved_image)])
        assert preserved_image.read_bytes() == back.read_bytes()

    stable_bytes = media.read_bytes()
    stable_probe = service.probe(media)
    corrupt_cover = tmp_path / "损坏封面.jpg"
    corrupt_cover.write_bytes(b"not a JPEG or PNG")
    with pytest.raises(AppError):
        service.embed_cover(media, corrupt_cover)
    assert media.read_bytes() == stable_bytes
    rolled_back = service.probe(media)
    assert service._stream_signature(stable_probe) == service._stream_signature(rolled_back)
    assert service._chapter_signature(stable_probe) == service._chapter_signature(rolled_back)
    assert len([s for s in rolled_back["streams"] if service._is_cover_stream(s)]) == 1
    assert {s.get("tags", {}).get("filename") for s in rolled_back["streams"]} >= {"note.txt", "back.png", "cover.jpg"}
    assert not list(tmp_path.glob(".*.cover-candidate.*"))


@pytest.mark.integration
@pytest.mark.parametrize("suffix", [".mp4", ".mkv"])
def test_wrong_embedded_image_never_replaces_original(tmp_path, monkeypatch, suffix):
    from PIL import Image
    service = FfmpegService(shell_thumbnail_checker=lambda *_: None)
    assert service.available
    media = tmp_path / ("original" + suffix)
    service._run([str(service.ffmpeg_path), "-v", "error", "-f", "lavfi", "-i", "color=c=blue:s=160x90:d=1",
                  "-c:v", "libx264", "-y", str(media)])
    selected = tmp_path / "selected.jpg"; Image.new("RGB", (160, 90), "red").save(selected)
    wrong = tmp_path / "wrong.jpg"; Image.new("RGB", (160, 90), "green").save(wrong)
    original = media.read_bytes()
    run = service._run
    def wrong_mux(arguments, **kwargs):
        if kwargs.get("stage") == "Embedding cover":
            arguments = [str(wrong) if a == str(selected) else a for a in arguments]
        return run(arguments, **kwargs)
    monkeypatch.setattr(service, "_run", wrong_mux)
    with pytest.raises(AppError) as error:
        service.embed_cover(media, selected)
    assert error.value.code == "cover_content_mismatch"
    assert media.read_bytes() == original
    assert not list(tmp_path.glob(".*.cover-candidate*"))


@pytest.mark.integration
def test_mpeg_missing_timestamps_can_be_copied_without_reencoding(tmp_path):
    service = FfmpegService(shell_thumbnail_checker=lambda *_: None)
    assert service.available
    media = tmp_path / "missing-pts.mpg"
    service._run([str(service.ffmpeg_path), "-v", "error", "-f", "lavfi", "-i", "color=blue:s=180x320:d=1:r=25",
                  "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-c:v", "mpeg2video", "-c:a", "mp2",
                  "-shortest", str(media)])
    before = media.read_bytes()
    cover = service.extract_frame(media, .2, tmp_path / "cover.jpg")
    destination = tmp_path / "with-cover.mkv"
    service.embed_cover(media, cover, output_path=destination)
    assert media.read_bytes() == before
    def encoded_hashes(path):
        output = service._run([str(service.ffmpeg_path), "-v", "error", "-i", str(path), "-map", "0:V:0", "-map", "0:a:0",
                               "-c", "copy", "-f", "streamhash", "-hash", "sha256", "-"]).stdout
        return [line for line in output.splitlines() if line and not line.startswith("#")]
    assert encoded_hashes(media) == encoded_hashes(destination)
