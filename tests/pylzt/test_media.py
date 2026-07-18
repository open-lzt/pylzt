"""Media / Request.files / multipart wiring / BaseMethod routing / media_storage."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pylzt.client import Client
from pylzt.lib.clock import FakeClock
from pylzt.lib.media_storage import BaseMediaStorage, FileMediaStorage, NullMediaStorage
from pylzt.media import Media
from pylzt.methods.base import BaseMethod, passthrough
from pylzt.token_pool.base import Token
from pylzt.token_pool.round_robin import RoundRobinTokenPool
from pylzt.transport.base import BaseTransport, Request, Response
from pylzt.transport.session import HttpxSession
from pylzt.types import ApiTarget, HttpMethod, RateClass, TokenId


def _pool() -> RoundRobinTokenPool:
    return RoundRobinTokenPool([Token(token_id=TokenId("t0"), credential="tok")], clock=FakeClock())


def test_media_sha256_is_a_64_char_hex_digest() -> None:
    media = Media(data=b"hello world", filename="a.png")
    assert len(media.sha256) == 64
    assert all(c in "0123456789abcdef" for c in media.sha256)


def test_media_from_path_reads_bytes_and_infers_filename(tmp_path: Path) -> None:
    p = tmp_path / "avatar.png"
    p.write_bytes(b"\x89PNG...")
    media = Media.from_path(p)
    assert media.data == b"\x89PNG..."
    assert media.filename == "avatar.png"
    assert media.content_type is None


def test_request_constructs_with_files() -> None:
    req = Request(
        method="POST",
        path="/x",
        rate_class=RateClass.FORUM,
        files={"avatar": Media(data=b"x", filename="a.png")},
    )
    assert req.files is not None
    assert req.files["avatar"].filename == "a.png"


def test_request_files_defaults_to_none() -> None:
    req = Request(method="GET", path="/x", rate_class=RateClass.GENERAL)
    assert req.files is None


class _FakeHttpxResponse:
    def __init__(self) -> None:
        self.status_code = 200
        self.headers: dict[str, str] = {}

    def json(self) -> dict[str, Any]:
        return {"ok": True}


class _FakeHttpxClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def request(self, method: str, path: str, **kwargs: Any) -> _FakeHttpxResponse:
        self.calls.append({"method": method, "path": path, **kwargs})
        return _FakeHttpxResponse()

    async def aclose(self) -> None:
        return None


async def test_raw_send_passes_files_and_data_when_files_present() -> None:
    fake_client = _FakeHttpxClient()
    session = HttpxSession(client=fake_client, token_pool=_pool())  # type: ignore[arg-type]
    media = Media(data=b"bytes", filename="a.png", content_type="image/png")
    req = Request(
        method="POST",
        path="/users/1/avatar",
        rate_class=RateClass.FORUM,
        json_body={"x": 1},
        files={"avatar": media},
    )
    await session._do_wire_send(req)

    call = fake_client.calls[0]
    assert call["files"] == {"avatar": ("a.png", b"bytes", "image/png")}
    assert call["data"] == {"x": 1}
    assert "json" not in call


async def test_raw_send_uses_json_path_when_files_is_none() -> None:
    fake_client = _FakeHttpxClient()
    session = HttpxSession(client=fake_client, token_pool=_pool())  # type: ignore[arg-type]
    req = Request(method="POST", path="/x", rate_class=RateClass.GENERAL, json_body={"a": 1})
    await session._do_wire_send(req)

    call = fake_client.calls[0]
    assert call["json"] == {"a": 1}
    assert "files" not in call


class _UploadAvatar(BaseMethod[str]):
    __api__ = ApiTarget.FORUM
    __rate_class__ = RateClass.FORUM
    __http_method__ = HttpMethod.POST
    __url__ = "/users/{user_id}/avatar"
    __returning__ = passthrough

    user_id: str
    avatar: Media
    x: int | None = None


class _CropAvatar(BaseMethod[str]):
    __api__ = ApiTarget.FORUM
    __rate_class__ = RateClass.FORUM
    __http_method__ = HttpMethod.POST
    __url__ = "/users/{user_id}/avatar/crop"
    __returning__ = passthrough

    user_id: str
    x: int | None = None


def test_build_request_routes_media_field_to_files() -> None:
    media = Media(data=b"x", filename="a.png")
    req = _UploadAvatar(user_id="1", avatar=media, x=5).build_request()
    assert req.files == {"avatar": media}
    assert req.json_body == {"x": 5}
    assert req.path == "/users/1/avatar"


def test_build_request_without_media_field_is_unaffected() -> None:
    req = _CropAvatar(user_id="1", x=5).build_request()
    assert req.files is None
    assert req.json_body == {"x": 5}


def test_null_media_storage_is_a_noop() -> None:
    storage = NullMediaStorage()

    async def run() -> None:
        assert await storage.get("k") is None
        await storage.save("k", Media(data=b"x", filename="a.png"))  # must not raise

    import asyncio

    asyncio.run(run())


def test_base_media_storage_requires_both_methods() -> None:
    with pytest.raises(TypeError):

        class _Incomplete(BaseMediaStorage):  # type: ignore[abstract]
            async def get(self, key: str) -> Media | None:
                return None

        _Incomplete()  # type: ignore[abstract]


async def test_file_media_storage_round_trips(tmp_path: Path) -> None:
    storage = FileMediaStorage(tmp_path)
    media = Media(data=b"\x89PNG...", filename="avatar.png", content_type="image/png")

    assert await storage.get(media.sha256) is None  # nothing saved yet
    await storage.save(media.sha256, media)
    loaded = await storage.get(media.sha256)

    assert loaded == media


async def test_file_media_storage_creates_root_directory(tmp_path: Path) -> None:
    root = tmp_path / "nested" / "media"
    assert not root.exists()
    FileMediaStorage(root)
    assert root.is_dir()


async def test_file_media_storage_get_missing_key_returns_none(tmp_path: Path) -> None:
    storage = FileMediaStorage(tmp_path)
    assert await storage.get("does-not-exist") is None


async def test_file_media_storage_overwrite_same_key(tmp_path: Path) -> None:
    storage = FileMediaStorage(tmp_path)
    first = Media(data=b"aaa", filename="a.png")
    second = Media(data=b"aaa", filename="renamed.png")  # same bytes -> same sha256

    await storage.save(first.sha256, first)
    await storage.save(second.sha256, second)
    loaded = await storage.get(first.sha256)

    assert loaded == second  # last write wins, no stale filename left behind


class _RecordingTransport(BaseTransport):
    def __init__(self) -> None:
        super().__init__(token_pool=_pool())
        self.sent: list[Request] = []

    async def _send_raw(self, req: Request) -> Response:
        self.sent.append(req)
        return Response(status=200, body={"ok": True})

    async def aclose(self) -> None:
        return None


class _RecordingMediaStorage(BaseMediaStorage):
    def __init__(self, *, raise_on_save: bool = False) -> None:
        self.saved: list[tuple[str, Media]] = []
        self._raise_on_save = raise_on_save

    async def get(self, key: str) -> Media | None:
        return None

    async def save(self, key: str, media: Media) -> None:
        if self._raise_on_save:
            raise RuntimeError("storage is down")
        self.saved.append((key, media))


async def test_execute_saves_media_to_storage_after_success() -> None:
    media = Media(data=b"bytes", filename="a.png")
    storage = _RecordingMediaStorage()
    transport = _RecordingTransport()
    # _UploadAvatar is __api__ = ApiTarget.FORUM -> routes through forum_transport.
    async with Client(tokens=["tok"], forum_transport=transport, media_storage=storage) as client:
        result = await client.execute(_UploadAvatar(user_id="1", avatar=media))

    assert result is not None
    assert storage.saved == [(media.sha256, media)]


async def test_execute_save_failure_does_not_propagate() -> None:
    media = Media(data=b"bytes", filename="a.png")
    storage = _RecordingMediaStorage(raise_on_save=True)
    transport = _RecordingTransport()
    async with Client(tokens=["tok"], forum_transport=transport, media_storage=storage) as client:
        # Must not raise even though storage.save() blows up internally.
        await client.execute(_UploadAvatar(user_id="1", avatar=media))


async def test_client_defaults_to_null_media_storage() -> None:
    transport = _RecordingTransport()
    async with Client(tokens=["tok"], transport=transport) as client:
        assert isinstance(client._media_storage, NullMediaStorage)
