"""Hand-patched — same gap as `market_batch_requests.Batch`: the generated `BatchExecute`
had no request-body fields (POST /batch's raw job-array body isn't a flat field set
codegen's method generator can capture) and the spec's guessed `Jobs`/`JobsJobId`
response model doesn't match the real dynamic-key-map wire shape either (confirmed live
in `lib/batch.py`) — both are hand-written here instead.
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
from pylzt.types import ApiTarget, HttpMethod, RateClass

if TYPE_CHECKING:
    from pylzt.transport.base import Response


class BatchExecute(BaseMethod[dict[str, BatchJobResult]]):
    """One POST /batch for up to `lib.batch.MAX_BATCH_JOBS` arbitrary forum API calls
    (any method/uri/params), keyed back by the caller-supplied job id.

    Required scopes: same as every called API request.

    Docs: https://lolzteam.readme.io/reference/batchexecute
    """

    __api__ = ApiTarget.FORUM
    __rate_class__ = RateClass.FORUM
    __http_method__ = HttpMethod.POST
    __url__ = "/batch"

    # Defaults to empty so the still-generated, unwired `GeneratedForumFacade.batch_execute()`
    # stub (zero args, per the OpenAPI spec codegen reads) stays callable/type-valid —
    # a real call always passes `jobs` explicitly, via `Client.execute_batch` or directly.
    jobs: Sequence[BatchJob] = ()

    def build_request(self) -> Request:
        return build_generic_batch_request(self.jobs, rate_class=RateClass.FORUM)

    def parse_response(self, response: Response) -> dict[str, BatchJobResult]:
        return parse_generic_batch_body(response.body)
