"""Cookie package public entrypoint."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("django-cookies-152fz")
except PackageNotFoundError:
    __version__ = "0.0.0"
