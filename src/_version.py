"""Single source of truth for the project version.

The version is declared exactly once, in ``pyproject.toml``. Everything that
needs it -- the FastAPI OpenAPI document, the logging subsystem, the analysis
scripts -- reads it from here. Never hardcode a version anywhere else: a second
place to maintain is a second place to forget (see ``.claude/commands/release.md``,
step 2).

Resolution order, and why it is this way round:

1. ``pyproject.toml`` next to the repository root. This is how the project is
   actually operated -- ``pip install -r requirements.txt`` plus
   ``uvicorn src.api.main:app`` from the source tree, and the Docker images,
   which copy the tree rather than installing the distribution. The working
   tree's own declaration must win, so a stale ``pip install .`` in the same
   environment cannot report a version the code is not.
2. ``importlib.metadata`` -- correct when the distribution really is installed
   and no source tree is around (a built wheel).

If neither works, the constant falls back to ``0.0.0``. That is deliberately an
impossible release number: it reads as "version unknown", not as "some version".
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

DISTRIBUTION_NAME = "datenschutz-rechtsprechung-api"
UNKNOWN_VERSION = "0.0.0"

_PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def _from_pyproject() -> Optional[str]:
    """Read ``[project] version`` from pyproject.toml, or return None."""
    try:
        text = _PYPROJECT.read_text(encoding="utf-8")
    except OSError:
        return None

    try:
        import tomllib  # Python 3.11+
    except ImportError:
        # Python 3.10 is still supported (pyproject `requires-python`) and has
        # no tomllib. The version line is machine-written by the release
        # command, so a narrow anchored regex over it is sufficient here.
        match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        return match.group(1) if match else None

    try:
        return tomllib.loads(text)["project"]["version"]
    except (KeyError, TypeError, ValueError):
        return None


def _from_installed_metadata() -> Optional[str]:
    """Read the version from installed distribution metadata, or return None."""
    try:
        from importlib.metadata import PackageNotFoundError, version
    except ImportError:  # pragma: no cover - importlib.metadata is stdlib on 3.8+
        return None

    try:
        return version(DISTRIBUTION_NAME)
    except PackageNotFoundError:
        return None


def get_version() -> str:
    """Return the project version, or ``0.0.0`` if it cannot be determined."""
    return _from_pyproject() or _from_installed_metadata() or UNKNOWN_VERSION


PROJECT_VERSION = get_version()
__version__ = PROJECT_VERSION
