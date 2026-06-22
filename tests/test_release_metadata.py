"""Regression checks for supported Python versions in package metadata."""

from pathlib import Path

import pytest

tomllib = pytest.importorskip("tomllib")

ROOT = Path(__file__).resolve().parents[1]
PROJECT_FILES = (
    ROOT / "pyproject.toml",
    ROOT / "packaging" / "consent" / "pyproject.toml",
    ROOT / "packaging" / "cookies" / "pyproject.toml",
)
SUPPORTED_PYTHON_CLASSIFIERS = {
    f"Programming Language :: Python :: 3.{minor}" for minor in range(10, 15)
}


@pytest.mark.parametrize(
    "project_file",
    PROJECT_FILES,
    ids=lambda path: str(path.relative_to(ROOT)),
)
def test_supported_python_versions_are_declared(project_file: Path) -> None:
    with project_file.open("rb") as stream:
        project = tomllib.load(stream)["project"]

    assert project["requires-python"] == ">=3.10"
    assert SUPPORTED_PYTHON_CLASSIFIERS <= set(project["classifiers"])
