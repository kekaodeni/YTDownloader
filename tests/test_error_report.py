from yt_downloader.core.errors import AppError, ErrorContext
from yt_downloader.services.error_report_service import build_error_report, redact_sensitive


def test_redacts_credentials_in_headers_json_and_query_strings() -> None:
    text = (
        "Authorization: Bearer super-secret\n"
        "Cookie: SID=private; PREF=x\n"
        'payload={"api_key":"abc123","password":"pw"}\n'
        "https://example.com/?token=url-secret&v=visible"
    )
    redacted = redact_sensitive(text)
    for secret in ("super-secret", "private", "abc123", '"pw"', "url-secret"):
        assert secret not in redacted
    assert "[REDACTED]" in redacted
    assert "v=visible" in redacted


def test_builds_complete_copyable_error_report() -> None:
    error = AppError(
        code="metadata_failed",
        user_message="无法获取该视频的信息。",
        technical_message="HTTP 403 Authorization: Bearer hidden",
        context=ErrorContext(
            url="https://youtu.be/dQw4w9WgXcQ?si=track",
            selected_format="1080p",
            output_directory="D:/视频",
            stage="Fetching metadata",
            traceback_text="Traceback: token=secret",
            log_excerpt="Cookie: SID=private",
        ),
    )
    report = build_error_report(
        error,
        app_version="0.1.0",
        python_version="3.12.8",
        os_version="Windows 11",
        yt_dlp_version="2026.08.19",
        ffmpeg_version="9.0",
        timestamp="2026-09-01 19:20:31 +08:00",
    )
    for label in ("Application Version", "Python Version", "Windows Version", "yt-dlp Version", "FFmpeg Version", "Selected Format", "Traceback"):
        assert label in report
    assert "dQw4w9WgXcQ" in report
    assert "hidden" not in report and "private" not in report and "secret" not in report
