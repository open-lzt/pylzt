"""Proxy source implementations: static list, file, and environment variable."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from pydantic import SecretStr

from pylzt.proxy_pool.base import BaseProxySource, Proxy, ProxyAuth
from pylzt.types import ProxyId, ProxyScheme

if TYPE_CHECKING:
    from collections.abc import Sequence


def _parse_proxy_url(url: str) -> Proxy | None:
    """Parse a single proxy URL string into a Proxy dataclass.

    Returns None if the URL is malformed or uses an unsupported scheme.
    """
    parsed = urlparse(url.strip())
    scheme_str = (parsed.scheme or "").lower()
    host = parsed.hostname or ""
    port = parsed.port

    if not scheme_str or not host or port is None:
        return None

    try:
        scheme = ProxyScheme(scheme_str)
    except ValueError:
        return None

    proxy_id = ProxyId(f"{scheme}://{host}:{port}")

    auth: ProxyAuth | None = None
    if parsed.username and parsed.password:
        auth = ProxyAuth(
            username=parsed.username,
            password=SecretStr(parsed.password),
        )

    return Proxy(proxy_id=proxy_id, scheme=scheme, host=host, port=port, auth=auth)


def _parse_proxy_lines(lines: list[str]) -> list[Proxy]:
    """Parse a list of raw text lines into Proxy objects, skipping blanks and comments."""
    result: list[Proxy] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        proxy = _parse_proxy_url(stripped)
        if proxy is not None:
            result.append(proxy)
    return result


class StaticProxySource(BaseProxySource):
    """In-memory proxy source backed by a pre-built list."""

    def __init__(self, proxies: list[Proxy]) -> None:
        self._proxies = proxies

    def load(self) -> Sequence[Proxy]:
        return list(self._proxies)


class FileProxySource(BaseProxySource):
    """Proxy source that reads URLs from a text file (one per line)."""

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)

    def load(self) -> Sequence[Proxy]:
        lines = self._path.read_text(encoding="utf-8").splitlines()
        return _parse_proxy_lines(lines)


class EnvProxySource(BaseProxySource):
    """Proxy source that reads a comma-separated list from an environment variable."""

    def __init__(self, var: str) -> None:
        self._var = var

    def load(self) -> Sequence[Proxy]:
        raw = os.environ.get(self._var, "")
        if not raw:
            return []
        return _parse_proxy_lines(raw.split(","))
