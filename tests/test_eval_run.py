import json
from pathlib import Path

import pytest

from evals.run import write_summary
from evals.scoring import Summary


def fake_result(directory: Path, name: str, model: str, passed: int) -> None:
    summary = Summary(
        model=model,
        answer_accuracy=1.0,
        refusal_accuracy=0.5,
        safe_refusal_rate=0.5,
        invented_rate=0.0,
        latency_p50_s=1.0,
        latency_p95_s=2.0,
        passed=passed,
        total=10,
    )
    payload = {"model": model, "summary": summary.__dict__, "results": []}
    (directory / name).write_text(json.dumps(payload), encoding="utf-8")


def test_summary_keeps_rows_from_earlier_runs(tmp_path: Path) -> None:
    fake_result(tmp_path, "llama3.2-3b.json", "llama3.2:3b", 7)
    fake_result(tmp_path, "claude-haiku-5-5.json", "claude-haiku-5-5", 9)
    (tmp_path / "summary.md").write_text("stale", encoding="utf-8")

    table = write_summary(tmp_path)

    assert "| `llama3.2:3b` | 7/10 |" in table
    assert "| `claude-haiku-5-5` | 9/10 |" in table
    assert (tmp_path / "summary.md").read_text(encoding="utf-8") == table + "\n"


def test_summary_skips_results_files_it_cannot_parse(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fake_result(tmp_path, "llama3.2-3b.json", "llama3.2:3b", 7)
    old = {"model": "old", "summary": {"model": "old", "accuracy": 0.5}, "results": []}
    (tmp_path / "old-schema.json").write_text(json.dumps(old), encoding="utf-8")
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")

    table = write_summary(tmp_path)

    assert "| `llama3.2:3b` | 7/10 |" in table
    assert "old" not in table
    out = capsys.readouterr().out
    assert "old-schema.json" in out
    assert "broken.json" in out
