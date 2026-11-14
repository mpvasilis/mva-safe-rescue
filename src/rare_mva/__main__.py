"""Module entry point for ``python -m rare_mva``."""

from rare_mva.cli import main


if __name__ == "__main__":  # pragma: no cover - exercised through subprocesses
    raise SystemExit(main())

