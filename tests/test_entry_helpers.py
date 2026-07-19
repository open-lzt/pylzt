"""Entry helpers: Client.from_token/from_env, ClientConfig.for_testnet, list_lots kwargs."""

from __future__ import annotations

import pytest

from pylzt import Client
from pylzt.config import ClientConfig
from pylzt.models.lot import LotFilter
from pylzt.types import Category


def test_from_token_and_bare_string() -> None:
    assert isinstance(Client.from_token("tok"), Client)
    assert isinstance(Client("tok"), Client)  # ctor accepts a bare token, not only a list
    assert isinstance(Client(["tok"]), Client)


def test_empty_tokens_still_raise() -> None:
    with pytest.raises(ValueError):
        Client()
    with pytest.raises(ValueError):
        Client([])


def test_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LZT_TOKEN", "envtok")
    assert isinstance(Client.from_env(), Client)


def test_from_env_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LZT_TOKEN", raising=False)
    with pytest.raises(ValueError):
        Client.from_env()


def test_for_testnet_default() -> None:
    cfg = ClientConfig.for_testnet()
    assert cfg.base_url == "http://127.0.0.1:8765"
    assert cfg.forum_base_url == cfg.base_url


def test_for_testnet_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LZT_TESTNET_HOST", "10.0.0.1")
    monkeypatch.setenv("LZT_TESTNET_PORT", "9999")
    cfg = ClientConfig.for_testnet()
    assert cfg.base_url == "http://10.0.0.1:9999"


def test_list_lots_accepts_kwargs_or_bare() -> None:
    client = Client.from_token("tok")
    assert client.market.list_lots(category=Category.STEAM) is not None  # builds LotFilter
    assert client.market.list_lots() is not None  # unfiltered
    with pytest.raises(TypeError):
        client.market.list_lots(LotFilter(category=Category.STEAM), category=Category.STEAM)
