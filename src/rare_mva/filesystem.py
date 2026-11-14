"""Small cross-platform filesystem metadata helpers."""

from __future__ import annotations

import stat
from pathlib import Path
from typing import Final

WINDOWS_REPARSE_POINT_ATTRIBUTE: Final[int] = 0x400


def is_link_or_reparse(path: str | Path) -> bool:
    """Return whether a path itself is a symlink or Windows reparse point.

    ``lstat`` deliberately inspects the directory entry rather than its target.
    Metadata errors are left to the caller so security-sensitive callers can
    fail closed in the manner appropriate to their API.
    """

    metadata = Path(path).lstat()
    attributes = getattr(metadata, "st_file_attributes", 0)
    return stat.S_ISLNK(metadata.st_mode) or bool(
        attributes & WINDOWS_REPARSE_POINT_ATTRIBUTE
    )
