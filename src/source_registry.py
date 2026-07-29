"""Registry for website novel source adapters."""

from __future__ import annotations

from .sources.esjzone import EsjzoneClient, EsjzoneSource
from .sources.masiro import MasiroClient, MasiroSource
from .utils import LogCallback, _default_log


def create_novel_source(
    source_id: str,
    *,
    cookie: str = "",
    user_agent: str = "",
    auto_purchase: bool = False,
    max_purchase_cost: int | None = None,
    log: LogCallback = _default_log,
):
    normalized = source_id.strip().lower()
    if normalized == EsjzoneSource.source_id:
        return EsjzoneSource(EsjzoneClient(cookie=cookie), log)
    if normalized == MasiroSource.source_id:
        return MasiroSource(
            MasiroClient(
                cookie=cookie,
                user_agent=user_agent,
                rate_limit_callback=lambda seconds: log(
                    f"[Rate Limit] Masiro cooling down for {seconds:g} second(s)"
                ),
            ),
            log,
            auto_purchase=auto_purchase,
            max_purchase_cost=max_purchase_cost,
        )
    raise ValueError(f"Unsupported novel source: {source_id}")


def available_novel_sources() -> tuple[str, ...]:
    return (EsjzoneSource.source_id, MasiroSource.source_id)
