from __future__ import annotations

from typing import TYPE_CHECKING, Type

if TYPE_CHECKING:
    from flask import Flask

__all__ = ["create_app"]


def create_app(config_class: Type | None = None) -> Flask:
    """Application factory (lazy import so `pyadminer.validators` works without full deps)."""
    from pyadminer.app_factory import create_app as _create_app
    from pyadminer.config import Config

    return _create_app(config_class or Config)
