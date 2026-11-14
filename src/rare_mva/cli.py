"""Command-line interface for privacy checks, validation, and scoring."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Sequence

from rare_mva.privacy import scan_paths
from rare_mva.track1.builder import BuilderError, build_track1
from rare_mva.track1.schema import ValidationError, load_ground_truth, load_submission
from rare_mva.track1.scoring import score_submission


class _CliUsageError(ValueError):
    """Raised instead of printing argparse's environment-dependent usage error."""


class _JsonArgumentParser(argparse.ArgumentParser):
    """Argument parser that delegates usage errors to deterministic JSON output."""

    def error(self, message: str) -> None:
        raise _CliUsageError(message)


def _stable_usage_error(message: str) -> str:
    """Normalize argparse wording that changed in Python 3.14."""

    match = re.fullmatch(
        r"(argument command: invalid choice: .+ \(choose from )(.+)(\))",
        message,
    )
    if match is None:
        return message
    choices = [choice.strip().strip("'\"") for choice in match.group(2).split(",")]
    if not choices or any(not choice for choice in choices):
        return message
    rendered = ", ".join(repr(choice) for choice in choices)
    return f"{match.group(1)}{rendered}{match.group(3)}"


def _emit(payload: dict[str, Any], *, error: bool = False) -> None:
    stream = sys.stderr if error else sys.stdout
    print(json.dumps(payload, ensure_ascii=True, separators=(",", ":")), file=stream)


def _privacy_scan(args: argparse.Namespace) -> int:
    try:
        findings = scan_paths(args.root)
    except ValueError:
        _emit(
            {"error": "privacy_scan_failed", "messages": ["root.invalid"]},
            error=True,
        )
        return 2
    payload = {
        "ok": not findings,
        "findings": [finding.to_dict() for finding in findings],
    }
    _emit(payload, error=bool(findings))
    return 0 if not findings else 1


def _validate_track1(args: argparse.Namespace) -> int:
    try:
        submission = load_submission(args.submission)
    except ValidationError:
        _emit(
            {"error": "validation_failed", "messages": ["submission.invalid"]},
            error=True,
        )
        return 1
    if (
        args.expected_proband_id is not None
        and submission.proband_id != args.expected_proband_id
    ):
        _emit(
            {"error": "validation_failed", "messages": ["proband_id.unexpected"]},
            error=True,
        )
        return 1
    if not args.quiet:
        _emit(
            {
                "ok": True,
                "proband_id": submission.proband_id,
                "candidate_count": len(submission.candidates),
            }
        )
    return 0


def _build_track1(args: argparse.Namespace) -> int:
    try:
        submission = build_track1(
            args.candidates,
            args.output,
            public_root=args.public_root,
        )
    except BuilderError as exc:
        _emit(
            {"error": "build_failed", "messages": list(exc.messages)},
            error=True,
        )
        return 1
    if not args.quiet:
        _emit({"ok": True, "candidate_count": len(submission.candidates)})
    return 0


def _score_track1(args: argparse.Namespace) -> int:
    try:
        submission = load_submission(args.submission)
        ground_truth = load_ground_truth(args.ground_truth)
        truth = ground_truth.get(submission.proband_id)
        if truth is None:
            raise ValidationError(
                f"ground truth has no entry for proband_id '{submission.proband_id}'"
            )
    except ValidationError:
        _emit(
            {"error": "validation_failed", "messages": ["score_inputs.invalid"]},
            error=True,
        )
        return 1

    result = score_submission(submission, truth)
    _emit(result.to_dict())
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level command parser."""

    parser = _JsonArgumentParser(
        prog="rare-mva",
        description="Privacy-safe Track 1 validation and public-compatible scoring.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    privacy = subparsers.add_parser(
        "privacy-scan",
        help="scan repository paths and sizes for privacy hazards",
    )
    privacy.add_argument("root", nargs="?", type=Path, default=Path("."))
    privacy.set_defaults(handler=_privacy_scan)

    validate = subparsers.add_parser(
        "validate-track1", help="validate a Track 1 submission CSV"
    )
    validate.add_argument("submission", type=Path, metavar="SUBMISSION.csv")
    validate.add_argument(
        "--expected-proband-id",
        metavar="ID",
        help="require the organizer-provided proband identifier",
    )
    validate.add_argument(
        "--quiet",
        action="store_true",
        help="emit no output when validation succeeds",
    )
    validate.set_defaults(handler=_validate_track1)

    build = subparsers.add_parser(
        "build-track1",
        help="build a validated Track 1 CSV from a strict local candidate JSON",
    )
    build.add_argument("candidates", type=Path, metavar="CANDIDATES.json")
    build.add_argument("output", type=Path, metavar="OUTPUT.csv")
    build.add_argument(
        "--public-root",
        type=Path,
        default=Path("."),
        metavar="ROOT",
        help="public repository boundary (default: current working directory)",
    )
    build.add_argument(
        "--quiet",
        action="store_true",
        help="emit no output when the build succeeds",
    )
    build.set_defaults(handler=_build_track1)

    score = subparsers.add_parser(
        "score-track1", help="score a Track 1 submission against local ground truth"
    )
    score.add_argument("submission", type=Path, metavar="SUBMISSION.csv")
    score.add_argument("ground_truth", type=Path, metavar="GROUND_TRUTH.json")
    score.set_defaults(handler=_score_track1)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command-line interface and return a process exit code."""

    parser = build_parser()
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        args = parser.parse_args(arguments)
    except _CliUsageError as exc:
        messages = (
            ["build_track1.invalid_arguments"]
            if arguments and arguments[0] == "build-track1"
            else [_stable_usage_error(str(exc))]
        )
        _emit({"error": "usage_error", "messages": messages}, error=True)
        return 2
    return int(args.handler(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
