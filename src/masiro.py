"""Compatibility facade for the Masiro web novel source."""

from .sources.masiro import (
    MASIRO_BASE_URL,
    MasiroBookInfo,
    MasiroBuildOptions,
    MasiroChapterRef,
    MasiroClient,
    MasiroPurchasePlan,
    MasiroReader,
    MasiroSource,
    build_masiro_epub,
    preview_masiro_purchase,
)

__all__ = [
    "MASIRO_BASE_URL",
    "MasiroBookInfo",
    "MasiroBuildOptions",
    "MasiroChapterRef",
    "MasiroClient",
    "MasiroPurchasePlan",
    "MasiroReader",
    "MasiroSource",
    "build_masiro_epub",
    "preview_masiro_purchase",
]
