import json
from pathlib import Path

import pytest
import yt_dlp

from yt_downloader.core.formats import apply_codec_preference, normalize_formats
from yt_downloader.core.models import CodecPreference, FormatOption
from yt_downloader.services.media_metadata import resolve_metadata


def test_bilibili_1080p60_quality_groups_encoder_measurements_without_loss():
    # Redacted exact-video metadata: quality 116 is the site's 1080P60 tier.
    # The three measured FPS values are encoder-specific, not three UI tiers.
    formats = [
        {"format_id": "30280", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2", "quality": 0},
        {"format_id": "30116", "ext": "mp4", "width": 1920, "height": 1080,
         "fps": 62.5, "quality": 116, "vcodec": "avc1.640032", "acodec": "none"},
        {"format_id": "30117", "ext": "mp4", "width": 1920, "height": 1080,
         "fps": 59.94, "quality": 116, "vcodec": "avc1.640032", "acodec": "none"},
        {"format_id": "100028", "ext": "mp4", "width": 1920, "height": 1080,
         "fps": 60.15, "quality": 116, "vcodec": "av01.0.12M.08", "acodec": "none"},
        {"format_id": "30106", "ext": "mp4", "width": 1920, "height": 1080,
         "fps": 58.82, "quality": 116, "vcodec": "hev1.1.6.L120", "acodec": "none"},
        {"format_id": "30080", "ext": "mp4", "width": 1920, "height": 1080,
         "fps": 29.41, "quality": 80, "vcodec": "avc1.640028", "acodec": "none"},
    ]
    media = resolve_metadata({"extractor_key": "BiliBili", "formats": formats}, "https://www.bilibili.com/video/BV1SL411q7xR/")
    assert [option.label for option in media.formats] == ["1080p 60 FPS", "1080p"]
    assert set(media.formats[0].candidate_video_format_ids) == {"30116", "30117", "100028", "30106"}
    assert media.formats[0].video_format_id in media.formats[0].candidate_video_format_ids
    assert media.formats[0].audio_format_id == "30280"
    assert len([option.label for option in media.formats]) == len({option.label for option in media.formats})


def test_bilibili_1080p_quality_and_high_bitrate_are_distinct_visible_buckets():
    formats = [
        {"format_id": format_id, "ext": "mp4", "width": 1920, "height": 1080,
         "fps": 30, "quality": quality, "vcodec": codec, "acodec": "none"}
        for format_id, quality, codec in (
            ("30080", 80, "avc1.640033"), ("30077", 80, "hvc1.1.6.L150"),
            ("30112", 112, "avc1.640033"), ("30102", 112, "hvc1.1.6.L150"),
        )
    ]

    media = resolve_metadata({"extractor_key": "BiliBili", "formats": formats},
                             "https://www.bilibili.com/video/BV1G4hD61EqA/")

    by_label = {option.label: set(option.candidate_video_format_ids) for option in media.formats}
    assert by_label == {
        "1080p": {"30080", "30077"},
        "1080p 高码率": {"30112", "30102"},
    }
    assert len({option.label for option in media.formats}) == len(media.formats)


def test_bilibili_quality_80_112_116_labels_and_tiers_are_distinct():
    formats = [
        {"format_id": format_id, "ext": "mp4", "width": 1920, "height": 1080,
         "fps": fps, "quality": quality, "vcodec": codec, "acodec": "none"}
        for format_id, quality, fps, codec in (
            ("q80-avc", 80, 30, "avc1.640033"),
            ("q112-avc", 112, 30, "avc1.640033"),
            ("q116-avc", 116, 59.94, "avc1.640033"),
        )
    ]
    media = resolve_metadata({"extractor_key": "BiliBili", "formats": formats},
                             "https://www.bilibili.com/video/BV1SL411q7xR/")
    labels = {option.label for option in media.formats}
    assert labels == {"1080p", "1080p 高码率", "1080p 60 FPS"}
    assert len(labels) == len(media.formats)


def test_bilibili_semantic_quality_ignores_nonstandard_encoded_dimensions():
    # Redacted dimensions from BV1KBaa6JEZV. Bilibili's qn, rather than the
    # encoder's coded height, defines each user-visible tier.
    formats = [
        {"format_id": format_id, "ext": "mp4", "width": width, "height": height,
         "fps": fps, "quality": quality, "vcodec": codec, "acodec": "none"}
        for format_id, quality, width, height, fps, codec in (
            ("q120-av1", 120, 3360, 1890, 59.94, "av01.0.12M.08"),
            ("q120-avc", 120, 3360, 1890, 60.0, "avc1.640032"),
            ("q116-av1-58", 116, 1576, 886, 58.82, "av01.0.09M.08"),
            ("q116-hevc-59", 116, 1594, 896, 59.94, "hev1.1.6.L150"),
            ("q116-avc-60", 116, 1920, 1080, 60.15, "avc1.640032"),
            ("q116-avc-62", 116, 1576, 886, 62.5, "avc1.640032"),
            ("q112-avc", 112, 1576, 886, 30.0, "avc1.640032"),
            ("q80-avc", 80, 1576, 886, 30.0, "avc1.640032"),
            ("q74-avc", 74, 1280, 590, 59.94, "avc1.640028"),
            ("q64-avc", 64, 1280, 590, 30.0, "avc1.640028"),
            ("q32-avc", 32, 702, 394, 30.0, "avc1.64001F"),
            ("q16-avc", 16, 524, 294, 30.0, "avc1.64001E"),
            ("q6-avc", 6, 426, 240, 30.0, "avc1.640015"),
        )
    ]

    media = resolve_metadata({"extractor_key": "BiliBili", "formats": formats},
                             "https://www.bilibili.com/video/BV1KBaa6JEZV/")

    assert [option.label for option in media.formats] == [
        "2160p 4K 60 FPS", "1080p 60 FPS", "1080p 高码率", "1080p",
        "720p 60 FPS", "720p", "480p", "360p", "240p",
    ]
    q116 = next(option for option in media.formats if option.label == "1080p 60 FPS")
    assert set(q116.candidate_video_format_ids) == {
        "q116-av1-58", "q116-hevc-59", "q116-avc-60", "q116-avc-62",
    }
    assert q116.site_quality == 116
    assert q116.semantic_height == q116.display_height == 1080
    assert q116.semantic_fps == q116.display_fps == 60
    raw_by_id = {item["format_id"]: item for item in formats}
    selected_q116_raw = raw_by_id[q116.video_format_id]
    assert (q116.width, q116.height, q116.fps) == (
        selected_q116_raw["width"], selected_q116_raw["height"], selected_q116_raw["fps"],
    )
    h264_option = apply_codec_preference(q116, CodecPreference.H264)
    h264_raw = raw_by_id[h264_option.video_format_id]
    assert (h264_option.width, h264_option.height, h264_option.fps) == (
        h264_raw["width"], h264_raw["height"], h264_raw["fps"],
    )
    assert (h264_option.site_quality, h264_option.semantic_height, h264_option.semantic_fps) == (116, 1080, 60)
    q120 = media.formats[0]
    assert q120.site_quality == 120
    selected_q120_raw = raw_by_id[q120.video_format_id]
    assert (q120.width, q120.height, q120.fps) == (
        selected_q120_raw["width"], selected_q120_raw["height"], selected_q120_raw["fps"],
    )
    assert (q120.width, q120.height) == (3360, 1890)
    assert q120.semantic_height == q120.display_height == 2160
    assert q120.semantic_fps == q120.display_fps == 60
    assert {format_id for option in media.formats for format_id in option.candidate_video_format_ids} == {
        item["format_id"] for item in formats
    }
    assert len({option.label for option in media.formats}) == len(media.formats)


def test_bilibili_dynamic_range_125_126_preserves_semantics_and_codec_candidates():
    formats = [
        {"format_id": format_id, "ext": "mp4", "width": 3840, "height": 2160,
         "fps": 30, "quality": quality, "dynamic_range": dynamic_range,
         "vcodec": codec, "acodec": "none"}
        for format_id, quality, dynamic_range, codec in (
            ("dv-av1", 126, "DV", "av01.0.12M.08"),
            ("dv-hevc", 126, "DV", "hev1.1.6.L150"),
            ("hdr-avc", 125, "HDR10", "avc1.640033"),
            ("sdr-avc", 120, "SDR", "avc1.640033"),
        )
    ]

    media = resolve_metadata({"extractor_key": "BiliBili", "formats": formats},
                             "https://www.bilibili.com/video/BV1KBaa6JEZV/")

    by_range = {option.dynamic_range: option for option in media.formats}
    assert by_range["DV"].label == "杜比视界"
    assert by_range["HDR10"].label == "HDR"
    assert by_range["SDR"].label == "2160p 4K"
    assert set(by_range["DV"].candidate_video_format_ids) == {"dv-av1", "dv-hevc"}
    assert apply_codec_preference(by_range["DV"], CodecPreference.AV1).dynamic_range == "DV"
    assert {option.site_quality for option in media.formats} == {120, 125, 126}
    assert all("QN" not in option.label for option in media.formats)
    assert len({option.label for option in media.formats}) == len(media.formats)
    assert {option.dynamic_range for option in media.formats} == {"DV", "HDR10", "SDR"}


def test_bilibili_dynamic_range_uses_semantic_fps_without_guessing():
    formats = [
        {"format_id": format_id, "ext": "mp4", "width": 3840, "height": 2160,
         "fps": fps, "quality": 126, "dynamic_range": "DV",
         "vcodec": "avc1.640033", "acodec": "none"}
        for format_id, fps in (("dv-30", 30), ("dv-unknown", None), ("dv-60", 59.94))
    ]

    media = resolve_metadata({"extractor_key": "BiliBili", "formats": formats},
                             "https://www.bilibili.com/video/BV1KBaa6JEZV/")

    assert {option.label for option in media.formats} == {
        "杜比视界", "杜比视界 60 FPS",
    }
    assert {option.dynamic_range for option in media.formats} == {"DV"}
    no_fps = next(option for option in media.formats if option.label == "杜比视界")
    assert set(no_fps.candidate_video_format_ids) == {"dv-30", "dv-unknown"}


def test_bilibili_unknown_quality_and_other_extractors_keep_generic_resolution_labels():
    bilibili = resolve_metadata({"extractor_key": "BiliBili", "formats": [
        {"format_id": "unknown-bili-q", "ext": "mp4", "width": 1576, "height": 886,
         "fps": 30, "quality": 66, "vcodec": "avc1.640032", "acodec": "none"},
    ]}, "https://www.bilibili.com/video/BV1KBaa6JEZV/")
    generic = resolve_metadata({"extractor_key": "Generic", "formats": [
        {"format_id": "generic-q120", "ext": "mp4", "width": 3360, "height": 1890,
         "fps": 59.94, "quality": 120, "vcodec": "avc1.640032", "acodec": "none"},
    ]}, "https://example.org/video")

    assert bilibili.formats[0].label == "886p"
    assert bilibili.formats[0].site_quality == 66
    assert bilibili.formats[0].semantic_height is None
    assert generic.formats[0].label == "1890p 2K 60 FPS"
    assert generic.formats[0].site_quality is None


def test_bilibili_quality_bucket_keeps_landscape_and_portrait_semantics_separate():
    formats = [
        {"format_id": "q80-landscape", "ext": "mp4", "width": 1576, "height": 886,
         "fps": 30, "quality": 80, "vcodec": "avc1.640032", "acodec": "none"},
        {"format_id": "q80-portrait", "ext": "mp4", "width": 886, "height": 1576,
         "fps": 30, "quality": 80, "vcodec": "avc1.640032", "acodec": "none"},
    ]
    media = resolve_metadata({"extractor_key": "BiliBili", "formats": formats},
                             "https://www.bilibili.com/video/BV1KBaa6JEZV/")

    assert {option.label: option.candidate_video_format_ids for option in media.formats} == {
        "1080p": ("q80-landscape",),
        "1080p 竖屏": ("q80-portrait",),
    }


def test_unknown_bilibili_quality_collision_keeps_labels_unique_without_guessing():
    formats = [
        {"format_id": "q80", "ext": "mp4", "width": 1920, "height": 1080,
         "fps": 30, "quality": 80, "vcodec": "avc1.640032", "acodec": "none"},
        {"format_id": "q66", "ext": "mp4", "width": 1920, "height": 1080,
         "fps": 30, "quality": 66, "vcodec": "hev1.1.6.L150", "acodec": "none"},
    ]
    media = resolve_metadata({"extractor_key": "BiliBili", "formats": formats},
                             "https://www.bilibili.com/video/BV1KBaa6JEZV/")

    assert {option.label for option in media.formats} == {"1080p", "1080p (QN 66)"}
    assert len({option.label for option in media.formats}) == len(media.formats)


def test_unknown_resolution_variants_do_not_create_duplicate_visible_labels():
    formats = [
        {"format_id": "unknown-a", "ext": "mp4", "vcodec": "avc1", "acodec": "none", "fps": 30},
        {"format_id": "unknown-b", "ext": "mp4", "vcodec": "av01", "acodec": "none", "fps": 60},
    ]

    options = normalize_formats(formats)

    assert [option.label for option in options] == ["未知清晰度"]
    assert set(options[0].candidate_video_format_ids) == {"unknown-a", "unknown-b"}


def test_other_sites_do_not_merge_genuine_59_and_62_fps_tiers():
    formats = [{"format_id": str(fps), "ext": "mp4", "width": 1920, "height": 1080,
                "fps": fps, "vcodec": "avc1", "acodec": "mp4a"} for fps in (59, 62)]
    media = resolve_metadata({"extractor_key": "Generic", "formats": formats}, "https://example.org/video")
    assert {item.label for item in media.formats} == {"1080p 59 FPS", "1080p 62 FPS"}


def test_x_hls_audio_with_unspecified_codec_is_retained_for_native_selection() -> None:
    # Redacted fields from the exact public X sample. yt-dlp itself selects
    # the audio rendition even though the extractor leaves acodec unset.
    formats = [
        {"format_id": "hls-audio-128000-Audio", "ext": "mp4", "vcodec": "none",
         "acodec": None, "format_note": "Audio", "protocol": "m3u8_native", "tbr": 128},
        {"format_id": "hls-1662", "ext": "mp4", "width": 720, "height": 1280,
         "vcodec": "avc1.640020", "acodec": "none", "protocol": "m3u8_native", "tbr": 1662},
    ]
    option = normalize_formats(formats)[0]
    assert option.format_selector == "hls-1662+hls-audio-128000-Audio"
    assert option.audio_format_id == "hls-audio-128000-Audio"
    assert option.acodec != "none"


def test_huya_hls_video_formats_with_unspecified_codecs_are_retained() -> None:
    # Redacted shape from native HuyaVideo metadata. yt-dlp -F exposes all
    # three resolutions as downloadable m3u8 formats with unknown codecs.
    formats = [
        {"format_id": "360P", "ext": "mp4", "protocol": "m3u8_native", "width": 640,
         "height": 360, "fps": None, "tbr": None, "vcodec": None, "acodec": None,
         "url": "https://media.example/360.m3u8"},
        {"format_id": "720P", "ext": "mp4", "protocol": "m3u8_native", "width": 1280,
         "height": 720, "fps": None, "tbr": None, "vcodec": None, "acodec": None,
         "url": "https://media.example/720.m3u8"},
        {"format_id": "1080P", "ext": "mp4", "protocol": "m3u8_native", "width": 1920,
         "height": 1080, "fps": None, "tbr": None, "vcodec": None, "acodec": None,
         "url": "https://media.example/1080.m3u8"},
    ]

    media = resolve_metadata(
        {"extractor": "huya:video", "extractor_key": "HuyaVideo", "formats": formats},
        "https://www.huya.com/video/play/1126525468.html",
    )

    assert [option.video_format_id for option in media.formats] == ["1080P", "720P", "360P"]
    assert [option.format_selector for option in media.formats] == ["1080P", "720P", "360P"]
    assert all(option.vcodec == "unknown" and option.acodec == "unknown" for option in media.formats)


@pytest.mark.parametrize("preference", [CodecPreference.AUTO, CodecPreference.VP9])
def test_vp9_webm_selection_and_size_match_native_ytdlp(preference) -> None:
    # Public metadata captured without media/signed URLs or request headers.
    fixture = json.loads((Path(__file__).parent / "fixtures" / "vp9-native-selection.json").read_text(encoding="utf-8"))
    formats = fixture["formats"]
    with yt_dlp.YoutubeDL({"quiet": True}) as ydl:
        native_formats = [dict(item) for item in formats]
        ydl.sort_formats({"formats": native_formats})
        native = ydl._select_formats(native_formats, ydl.build_format_selector("bv*+ba/b"))[0]

    option = apply_codec_preference(normalize_formats(formats)[0], preference)

    assert option.format_selector == native["format_id"] == "315+251"
    assert option.video_protocol == "https"
    assert option.video_size == 1_002_746_821
    assert option.audio_size == 8_970_523
    assert option.estimated_size == 1_011_717_344
    assert not option.size_is_estimate


def test_normalizes_and_sorts_user_facing_quality_options() -> None:
    formats = [
        {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2", "abr": 129, "filesize": 10},
        {"format_id": "251", "ext": "webm", "vcodec": "none", "acodec": "opus", "abr": 150, "filesize": 12},
        {"format_id": "22", "ext": "mp4", "height": 720, "fps": 30, "vcodec": "avc1.64001F", "acodec": "mp4a.40.2", "filesize": 100},
        {"format_id": "137", "ext": "mp4", "height": 1080, "fps": 30, "vcodec": "avc1.640028", "acodec": "none", "filesize_approx": 200},
        {"format_id": "248", "ext": "webm", "height": 1080, "fps": 30, "vcodec": "vp9", "acodec": "none", "filesize": 180},
        {"format_id": "299", "ext": "mp4", "height": 1080, "fps": 60, "vcodec": "avc1.64002a", "acodec": "none", "filesize": 240},
        {"format_id": "313", "ext": "webm", "height": 2160, "fps": 30, "vcodec": "vp9", "acodec": "none", "filesize": 400},
    ]

    options = normalize_formats(formats)

    assert all(isinstance(option, FormatOption) for option in options)
    assert [option.label for option in options] == ["2160p 4K", "1080p 60 FPS", "1080p", "720p"]
    assert all("137" not in option.label and "313" not in option.label for option in options)

    option_1080 = next(option for option in options if option.label == "1080p")
    assert option_1080.format_selector == "248+251"
    assert option_1080.container == "WebM"
    assert option_1080.requires_merge
    assert option_1080.estimated_size == 192
    assert option_1080.size_is_estimate is False
    assert option_1080.video_size == 180
    assert option_1080.video_size_is_estimate is False
    assert option_1080.audio_size == 12
    assert option_1080.audio_size_is_estimate is False

    option_720 = next(option for option in options if option.label == "720p")
    assert option_720.estimated_size == 100
    assert option_720.size_is_estimate is False

    option_4k = options[0]
    assert option_4k.format_selector == "313+251"
    assert option_4k.container == "WebM"
    assert next(option for option in options if option.is_recommended).label == "1080p"


def test_split_format_has_unknown_size_when_one_required_stream_size_is_missing() -> None:
    options = normalize_formats([
        {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2"},
        {"format_id": "137", "ext": "mp4", "height": 1080, "fps": 30, "vcodec": "avc1", "acodec": "none", "filesize": 200},
    ])

    assert options[0].requires_merge is True
    assert options[0].estimated_size is None


def test_fragmented_format_does_not_invent_size_from_duration_and_peak_bitrate() -> None:
    options = normalize_formats([
        {
            "format_id": "140",
            "ext": "m4a",
            "vcodec": "none",
            "acodec": "mp4a.40.2",
            "filesize": 2_410_324,
        },
        {
            "format_id": "628",
            "ext": "mp4",
            "width": 3840,
            "height": 2160,
            "fps": 60,
            "vcodec": "vp09.00.51.08",
            "acodec": "none",
            "tbr": 27_982.889,
            "protocol": "m3u8_native",
        },
    ], duration=149)

    option = options[0]
    assert option.video_size is None
    assert option.video_size_is_estimate is False
    assert option.audio_size == 2_410_324
    assert option.estimated_size is None
    assert option.size_is_estimate is False


def test_portrait_quality_uses_the_short_edge_and_preserves_dimensions() -> None:
    options = normalize_formats([
        {
            "format_id": "portrait",
            "ext": "mp4",
            "width": 1080,
            "height": 1920,
            "fps": 30,
            "vcodec": "avc1",
            "acodec": "mp4a.40.2",
            "filesize": 200,
        },
    ])

    assert options[0].label == "1080p 竖屏"
    assert options[0].width == 1080
    assert options[0].height == 1920


def test_unknown_height_is_kept_without_guessing_from_width() -> None:
    options = normalize_formats([
        {
            "format_id": "unknown-height",
            "ext": "mp4",
            "width": 3840,
            "height": None,
            "fps": None,
            "vcodec": "avc1",
            "acodec": "mp4a.40.2",
        },
    ])

    assert len(options) == 1
    assert options[0].label == "未知清晰度"
    assert options[0].width == 3840
    assert options[0].height is None
    assert options[0].fps is None


def test_auto_codec_policy_uses_ytdlp_native_format_order() -> None:
    options = normalize_formats([
        {
            "format_id": "140",
            "ext": "m4a",
            "vcodec": "none",
            "acodec": "mp4a.40.2",
            "abr": 129,
            "protocol": "https",
            "filesize": 1_141_383,
            "url": "https://example.invalid/audio",
        },
        {
            "format_id": "628",
            "ext": "mp4",
            "width": 3840,
            "height": 2160,
            "fps": 60,
            "vcodec": "vp09.00.51.08",
            "acodec": "none",
            "tbr": 61_229.923,
            "protocol": "m3u8_native",
            "url": "https://example.invalid/hls",
        },
        {
            "format_id": "401",
            "ext": "mp4",
            "width": 3840,
            "height": 2160,
            "fps": 60,
            "vcodec": "av01.0.12M.08",
            "acodec": "none",
            "tbr": 19_417.005,
            "protocol": "https",
            "filesize": 170_918_192,
            "url": "https://example.invalid/video",
        },
    ])

    assert options[0].format_selector == "401+140"
    assert options[0].video_format_id == "401"
    assert options[0].estimated_size == 172_059_575
    assert options[0].size_is_estimate is False


@pytest.mark.parametrize(
    ("preference", "expected_id"),
    [
        (CodecPreference.AV1, "401"),
        (CodecPreference.VP9, "628"),
        (CodecPreference.H264, "701"),
    ],
)
def test_codec_preference_selects_candidate_after_normalization_without_filtering_tiers(
    preference: CodecPreference,
    expected_id: str,
) -> None:
    shared = {
        "ext": "mp4",
        "width": 3840,
        "height": 2160,
        "fps": 60,
        "acodec": "none",
        "protocol": "https",
    }
    options = normalize_formats([
        {"format_id": "140", "ext": "m4a", "vcodec": "none", "acodec": "mp4a.40.2", "protocol": "https"},
        {**shared, "format_id": "401", "vcodec": "av01.0.12M.08"},
        {**shared, "format_id": "628", "vcodec": "vp09.00.51.08"},
        {**shared, "format_id": "701", "vcodec": "avc1.640033"},
    ])

    selected = apply_codec_preference(options[0], preference)
    assert selected.video_format_id == expected_id
    assert options[0].candidate_video_format_ids == ("401", "628", "701")


@pytest.mark.parametrize(
    ("width", "height", "expected"),
    [
        (3840, 2160, "2160p 4K"),
        (2560, 1440, "1440p 2K"),
        (1920, 1080, "1080p"),
        (1280, 720, "720p"),
        (854, 480, "480p"),
        (640, 360, "360p"),
        (426, 240, "240p"),
        (256, 144, "144p"),
        (2560, 1080, "1080p"),
    ],
)
def test_landscape_quality_labels_follow_vertical_resolution(
    width: int,
    height: int,
    expected: str,
) -> None:
    option = normalize_formats([
        {
            "format_id": str(height),
            "ext": "mp4",
            "width": width,
            "height": height,
            "fps": None,
            "vcodec": "avc1",
            "acodec": "mp4a.40.2",
        },
    ])[0]

    assert option.label == expected
    assert (option.width, option.height, option.fps) == (width, height, None)
