from pathlib import Path

from agentbench.util.jsonl import append_jsonl, read_jsonl


def test_append_jsonl_and_read_jsonl_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"

    assert append_jsonl(path, {"event": "start", "ok": True}) is True
    assert append_jsonl(path, '{"event":"end","ok":false}') is True

    records = list(read_jsonl(path))

    assert records == [
        {"event": "start", "ok": True},
        {"event": "end", "ok": False},
    ]


def test_read_jsonl_skips_empty_and_invalid_lines(tmp_path: Path) -> None:
    path = tmp_path / "mixed.jsonl"
    path.write_text('{"a": 1}\n\nnot-json\n{"b": 2}\n', encoding="utf-8")

    records = list(read_jsonl(path))

    assert records == [{"a": 1}, {"b": 2}]
