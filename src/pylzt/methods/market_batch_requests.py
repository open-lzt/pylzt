"""Hand-patched — the generated `Batch` had no request-body fields at all: the official
OpenAPI spec's POST /batch body is a raw array of job objects, a shape codegen's flat
per-field method generator can't capture, so it silently emitted a zero-arg stub that
could never actually batch anything. Also `Jobs`/`JobsJobId` (the spec's guessed response
model) modeled `jobs` as one fixed `job_id` field; the real wire shape (confirmed live in
`lib/batch.py`) is a dynamic map keyed by job id, so response parsing is hand-written here
too instead of routing through `Jobs.from_raw`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from pylzt.lib.batch import (
    BatchJob,
    BatchJobResult,
    build_generic_batch_request,
    parse_generic_batch_body,
)
from pylzt.methods.base import BaseMethod
from pylzt.transport.base import Request
from pylzt.types import HttpMethod

if TYPE_CHECKING:
    from pylzt.transport.base import Response


class Batch(BaseMethod[dict[str, BatchJobResult]]):
    """One POST /batch for up to `lib.batch.MAX_BATCH_JOBS` arbitrary market API calls
    (any method/uri/params), keyed back by the caller-supplied job id. Two endpoints are
    server-excluded from batching (`GET /{item_id}/image`, `/item/fast-sell`) — batching
    either raises a 400 from the server, not caught client-side.

    Docs: https://lzt-market.readme.io/reference/batch
    """

    __http_method__ = HttpMethod.POST
    __url__ = "/batch"

    # Defaults to empty so the still-generated, unwired `GeneratedMarketFacade.batch()`
    # stub (zero args, per the OpenAPI spec codegen reads) stays callable/type-valid —
    # a real call always passes `jobs` explicitly, via `Client.execute_batch` or directly.
    jobs: Sequence[BatchJob] = ()

    def build_request(self) -> Request:
        return build_generic_batch_request(self.jobs)

    def parse_response(self, response: Response) -> dict[str, BatchJobResult]:
        return parse_generic_batch_body(response.body)
