"""CLI behavior tests using only committed synthetic fixtures."""

from __future__ import annotations

import json
from pathlib import Path

from rare_mva.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


def test_validate_cli_success(capsys: object) -> None:
    assert main(["validate-track1", str(FIXTURES / "valid_single.csv")]) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert json.loads(captured.out) == {
        "ok": True,
        "proband_id": "SYNTHETIC_PROBAND_SINGLE",
        "candidate_count": 1,
    }
    assert captured.err == ""


def test_validate_cli_quiet_success(capsys: object) -> None:
    assert main(
        ["validate-track1", str(FIXTURES / "valid_single.csv"), "--quiet"]
    ) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert captured.out == ""
    assert captured.err == ""


def test_validate_cli_expected_proband_id(capsys: object) -> None:
    submission = str(FIXTURES / "valid_single.csv")
    assert main(
        ["validate-track1", submission, "--expected-proband-id", "WRONG"]
    ) == 1
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert json.loads(captured.err) == {
        "error": "validation_failed",
        "messages": ["proband_id.unexpected"],
    }
    assert captured.out == ""


def test_score_cli_success(capsys: object) -> None:
    exit_code = main(
        [
            "score-track1",
            str(FIXTURES / "valid_compound.csv"),
            str(FIXTURES / "ground_truth.json"),
        ]
    )
    assert exit_code == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert json.loads(captured.out) == {
        "proband_id": "SYNTHETIC_PROBAND_COMPOUND",
        "rank_points": 50.0,
        "fmax": 0.8,
        "f_max_threshold": 0.9,
        "n_predictions_at_f_max": 2,
        "full_match_rank": 2,
        "partial_match_rank": None,
        "candidate_count": 3,
    }


def test_score_cli_failure_does_not_echo_proband_or_paths(
    tmp_path: Path, capsys: object
) -> None:
    empty_truth = tmp_path / "synthetic_empty_truth.json"
    empty_truth.write_text("{}", encoding="utf-8")
    submission = FIXTURES / "valid_single.csv"
    assert main(["score-track1", str(submission), str(empty_truth)]) == 1
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert json.loads(captured.err) == {
        "error": "validation_failed",
        "messages": ["score_inputs.invalid"],
    }
    assert "SYNTHETIC_PROBAND_SINGLE" not in captured.err
    assert str(empty_truth.resolve()) not in captured.err
    assert captured.out == ""


def test_validate_cli_failure_is_json(tmp_path: Path, capsys: object) -> None:
    invalid = tmp_path / "invalid.csv"
    invalid.write_text("wrong,header\nSYNTHETIC,ONLY\n", encoding="utf-8")
    assert main(["validate-track1", str(invalid)]) == 1
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    payload = json.loads(captured.err)
    assert payload["error"] == "validation_failed"
    assert payload["messages"] == ["submission.invalid"]
    assert "wrong" not in captured.err
    assert captured.out == ""


def test_privacy_cli_success_is_deterministic_json(
    tmp_path: Path, capsys: object
) -> None:
    (tmp_path / "synthetic.txt").write_text("SYNTHETIC", encoding="utf-8")
    assert main(["privacy-scan", str(tmp_path)]) == 0
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert captured.out == '{"ok":true,"findings":[]}\n'
    assert captured.err == ""


def test_privacy_cli_invalid_root_does_not_echo_path(
    tmp_path: Path, capsys: object
) -> None:
    missing = tmp_path / "SYNTHETIC_SECRET_PATH"
    assert main(["privacy-scan", str(missing)]) == 2
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    assert json.loads(captured.err) == {
        "error": "privacy_scan_failed",
        "messages": ["root.invalid"],
    }
    assert "SYNTHETIC_SECRET_PATH" not in captured.err
    assert str(missing.resolve()) not in captured.err
    assert captured.out == ""


def test_usage_error_is_deterministic_json(capsys: object) -> None:
    assert main(["not-a-command"]) == 2
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    payload = json.loads(captured.err)
    assert payload["error"] == "usage_error"
    assert payload["messages"] == [
        "argument command: invalid choice: 'not-a-command' "
        "(choose from 'privacy-scan', 'validate-track1', 'build-track1', "
        "'score-track1')"
    ]
    assert captured.out == ""
