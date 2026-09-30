"""Unit coverage independent of the optional IndexD server test fixture."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from gen3.auth import Gen3Auth
from gen3.index import Gen3Index


@pytest.mark.parametrize(
    "auth,expected",
    [
        (None, {}),
        (("service", "password"), {"auth": aiohttp.BasicAuth("service", "password")}),
    ],
)
def test_anonymous_and_basic_auth(auth, expected):
    index = Gen3Index("https://commons.example", auth_provider=auth)
    assert index._async_read_credentials() == expected


@pytest.mark.parametrize(
    "method,args",
    [
        ("async_get_record", ("private",)),
        ("async_get_records_on_page", (10, 0)),
        ("async_get_records_from_checksum", ("a" * 32,)),
        ("async_get_with_params", ({"size": 1},)),
        ("async_query_urls", ("secret",)),
    ],
)
def test_all_async_discovery_methods_send_gen3_credentials(method, args):
    auth = Gen3Auth(endpoint="https://commons.example", access_token="test-token")
    index = Gen3Index(auth)
    response = MagicMock()
    response.json = AsyncMock(return_value={"records": []})
    response_context = MagicMock()
    response_context.__aenter__ = AsyncMock(return_value=response)
    session = MagicMock()
    session.get.return_value = response_context
    session_context = MagicMock()
    session_context.__aenter__ = AsyncMock(return_value=session)
    with patch.object(auth, "_get_auth_value", return_value="Bearer caller"), patch(
        "gen3.index.aiohttp.ClientSession", return_value=session_context
    ):
        asyncio.run(getattr(index, method)(*args))
        assert session.get.call_args.kwargs["headers"] == {
            "Authorization": "Bearer caller"
        }
        response.raise_for_status.assert_called_once()


def test_sync_reads_send_auth_to_indexclient():
    auth = Gen3Auth(endpoint="https://commons.example", access_token="test-token")
    index = Gen3Index(auth)
    response = MagicMock(status_code=200)
    response.json.return_value = {
        "did": "private",
        "rev": "1",
        "visibility": "restricted",
    }
    with patch("indexclient.client.requests.get", return_value=response) as get:
        assert index.get_record("private")["visibility"] == "restricted"
        assert get.call_args.kwargs["auth"] is auth


def test_create_new_version_serializes_opt_in_field():
    index = Gen3Index("https://commons.example")
    response = MagicMock(status_code=200)
    response.json.return_value = {"did": "new-version"}
    with patch.object(
        index.client, "_post", return_value=response
    ) as post, patch.object(index, "get_record", return_value={}):
        index.create_new_version(
            "private", {"md5": "a" * 32}, 1, visibility="restricted"
        )
        assert json.loads(post.call_args.kwargs["data"])["visibility"] == "restricted"


def test_blank_record_can_be_restricted_before_upload():
    index = Gen3Index("https://commons.example")
    response = MagicMock(status_code=201)
    response.json.return_value = {"did": "blank"}
    with patch.object(
        index.client, "_post", return_value=response
    ) as post, patch.object(index, "get_record", return_value={}):
        index.create_blank(
            "owner", "private.txt", authz=["/private"], visibility="restricted"
        )
        body = json.loads(post.call_args.kwargs["data"])
        assert body["visibility"] == "restricted"
        assert body["authz"] == ["/private"]
