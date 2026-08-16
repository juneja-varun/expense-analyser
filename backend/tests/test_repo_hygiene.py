"""Repository-level checks that are easy to get wrong and silent when wrong."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
APPS_DIR = REPO_ROOT / "backend" / "apps"


def is_ignored(path: Path) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", str(path)],
        cwd=REPO_ROOT,
        check=False,
    )
    return result.returncode == 0


class TestGitignore:
    @pytest.mark.parametrize(
        "app_dir",
        sorted(p.name for p in APPS_DIR.iterdir() if p.is_dir() and not p.name.startswith("_")),
    )
    def test_application_packages_are_not_ignored(self, app_dir: str) -> None:
        """Regression: the rule keeping users' real statements out of the repo
        was written unanchored as `statements/`, which also matched
        `backend/apps/statements/` and silently excluded the whole app from
        commits. CI caught it only as `ModuleNotFoundError` on a fresh clone.
        """
        package = APPS_DIR / app_dir / "__init__.py"
        assert not is_ignored(package), (
            f"backend/apps/{app_dir}/ is excluded by .gitignore. "
            "Anchor the offending rule with a leading slash so it only matches "
            "the repository root."
        )

    @pytest.mark.parametrize("scratch", ["statements", "files"])
    def test_root_scratch_directories_are_still_ignored(self, scratch: str) -> None:
        """The anchoring fix must not stop protecting the thing it was for."""
        assert is_ignored(REPO_ROOT / scratch / "statement.pdf"), (
            f"/{scratch}/ is no longer ignored — real statements dropped there "
            "would be committable."
        )

    def test_env_file_is_ignored(self) -> None:
        assert is_ignored(REPO_ROOT / ".env")
