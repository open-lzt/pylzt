"""Persistence seam for batch-job history — audit/replay/consumption across process
restarts.

Same shape as `lib/cache.py`'s `BaseCache`: an ABC behind `Client`, an in-memory default
(`MemoryStorage`), a consumer swaps in Postgres/Redis/SQLite without the SDK importing
any of them. Every `Client.execute_batch` chunk records what it sent and what came back
via `save_jobs`; `Client.iter_pending_batch_jobs` then drives a consume-commit loop over
`get_jobs`/`commit_jobs` (Stateful Worker pattern — commit is a status flip, not a delete,
so history survives for audit; `delete_jobs` is the separate, explicit cleanup/retention
op). `record_id` (assigned by the client, not the storage) is the stable identity —
`job.id` is only unique WITHIN one batch chunk (1-indexed per call, reused across calls),
so it can't double as a cross-call primary key.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pylzt.lib.batch import BatchJob, BatchJobResult


class BatchJobRecord(BaseModel):
    """One persisted batch job: what was sent (`job`), what came back (`result`, `None`
    if the process crashed/was killed before the response was parsed), and whether a
    consumer has acknowledged it (`committed`)."""

    model_config = ConfigDict(frozen=True)

    record_id: str
    job: BatchJob
    result: BatchJobResult | None = None
    committed: bool = False


class BaseStorage(ABC):
    """Persistence + consume-commit queue for batch-job history. The impl decides
    where it lives."""

    @abstractmethod
    async def save_jobs(self, records: Sequence[BatchJobRecord]) -> None:
        """Persist `records` (append — never overwrites or dedupes existing history)."""

    @abstractmethod
    async def get_jobs(
        self, *, only_pending: bool = True, limit: int | None = None, offset: int = 0
    ) -> list[BatchJobRecord]:
        """Return persisted records oldest-first, paginated by `limit`/`offset`.

        `only_pending=True` (the consumption path) excludes already-`commit_jobs`-ed
        records; `only_pending=False` (the audit path) returns the full history.
        """

    @abstractmethod
    async def commit_jobs(self, record_ids: Sequence[str]) -> None:
        """Mark `record_ids` committed — a status flip, not a delete: they stop showing
        up under `only_pending=True` but stay in storage for `only_pending=False` audit
        reads. Unknown ids are silently skipped (already-committed/deleted is not an error
        — commit is meant to be safely re-runnable after a crash mid-loop)."""

    @abstractmethod
    async def delete_jobs(self, record_ids: Sequence[str]) -> None:
        """Hard-remove `record_ids` — the explicit retention/cleanup op, independent of
        commit state. Unknown ids are silently skipped, same reasoning as `commit_jobs`."""


class MemoryStorage(BaseStorage):
    """In-process job log (default). Lost on restart — inject a real `BaseStorage` for
    history/queue state that needs to survive one."""

    def __init__(self) -> None:
        self._records: dict[str, BatchJobRecord] = {}

    async def save_jobs(self, records: Sequence[BatchJobRecord]) -> None:
        for record in records:
            self._records[record.record_id] = record

    async def get_jobs(
        self, *, only_pending: bool = True, limit: int | None = None, offset: int = 0
    ) -> list[BatchJobRecord]:
        values = list(self._records.values())
        if only_pending:
            values = [r for r in values if not r.committed]
        page = values[offset:]
        return page[:limit] if limit is not None else page

    async def commit_jobs(self, record_ids: Sequence[str]) -> None:
        for record_id in record_ids:
            record = self._records.get(record_id)
            if record is not None:
                self._records[record_id] = record.model_copy(update={"committed": True})

    async def delete_jobs(self, record_ids: Sequence[str]) -> None:
        for record_id in record_ids:
            self._records.pop(record_id, None)
