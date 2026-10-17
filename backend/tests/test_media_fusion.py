from app.media.pipeline import _fuse_segments


def test_fuse_segments_keeps_timestamps_and_modalities() -> None:
    segments = _fuse_segments(
        duration_ms=65_000,
        transcript=[
            {"start_ms": 1_000, "end_ms": 5_000, "text": "第一段语音"},
            {"start_ms": 31_000, "end_ms": 35_000, "text": "第二段语音"},
        ],
        frames=[
            (2_000, "frames/first.jpg", "首页画面"),
            (62_000, "frames/last.jpg", "结束画面"),
        ],
    )

    assert [(item["start_ms"], item["end_ms"]) for item in segments] == [
        (0, 30_000),
        (30_000, 60_000),
        (60_000, 65_000),
    ]
    assert segments[0]["transcript"] == "第一段语音"
    assert segments[0]["visual_text"] == "首页画面"
    assert segments[2]["frame_keys"] == ["frames/last.jpg"]


def test_fuse_segments_drops_empty_windows() -> None:
    segments = _fuse_segments(
        duration_ms=120_000,
        transcript=[{"start_ms": 61_000, "end_ms": 62_000, "text": "唯一内容"}],
        frames=[],
    )
    assert len(segments) == 1
    assert segments[0]["start_ms"] == 60_000

