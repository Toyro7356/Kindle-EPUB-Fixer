"""Registry for website novel source adapters."""

from __future__ import annotations

from .sources.esjzone import EsjzoneClient, EsjzoneSource
from .utils import LogCallback, _default_log


def create_novel_source(source_id: str, *, cookie: str = "", log: LogCallback = _default_log):
    normalized = source_id.strip().lower()
    if normalized == EsjzoneSource.source_id:
        return EsjzoneSource(EsjzoneClient(cookie=cookie), log)
    raise ValueError(f"Unsupported novel source: {source_id}")


def available_novel_sources() -> tuple[str, ...]:
    return (EsjzoneSource.source_id,)
