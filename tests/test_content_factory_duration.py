from backend.api.admin.content_factory import (
    _coerce_duration,
    _detect_media_type,
    _first_duration_from_ffprobe,
    _format_duration,
)


def test_video_type_detects_by_extension_when_mime_is_generic():
    assert _detect_media_type("application/octet-stream", "movie.mp4") == "video"
    assert _detect_media_type("", "clip.MKV") == "video"


def test_duration_parsing_rejects_zero_and_uses_positive_values():
    assert _coerce_duration(0) is None
    assert _coerce_duration("N/A") is None
    assert _coerce_duration("93.42") == 93.42
    assert _first_duration_from_ffprobe("N/A\n125.5\n") == 125.5


def test_format_duration_uses_minutes_and_hours():
    assert _format_duration(0) == "0min"
    assert _format_duration(30) == "1min"
    assert _format_duration(125.5) == "2min"
    assert _format_duration(4800) == "1hr20min"
    assert _format_duration(7200) == "2hr"
