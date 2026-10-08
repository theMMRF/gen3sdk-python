"""Optional real HTTP acceptance against IndexD's disposable local_server.py."""

import asyncio
import os
from unittest.mock import patch
from urllib.parse import urlsplit

import aiohttp
import pytest
import requests
from gen3.auth import Gen3Auth
from gen3.index import Gen3Index

URL = os.getenv("VISIBILITY_TEST_INDEXD_URL")
pytestmark = pytest.mark.skipif(
    not URL, reason="Start the disposable IndexD local_server.py fixture"
)
RESOURCE = "/programs/MMRF/projects/private-sdk-test"


@pytest.fixture(autouse=True)
def loopback_only():
    assert urlsplit(URL).hostname in (
        "localhost",
        "127.0.0.1",
    ), "This fixture only writes to loopback test servers"


@pytest.fixture
def records():
    admin = Gen3Index(URL, auth_provider=("test", "test"), service_location="")
    private = admin.create_record(
        {"md5": "a" * 32},
        10,
        urls=["s3://test/private"],
        authz=[RESOURCE],
    )
    public = admin.create_record({"md5": "b" * 32}, 1, urls=["s3://test/public"], authz=["/open"])
    try:
        yield private, public
    finally:
        admin.delete_record(private["did"])
        admin.delete_record(public["did"])


def test_standard_sdk_sync_discovery_and_bulk(records):
    private, public = records
    anonymous = Gen3Index(URL, service_location="")
    assert anonymous.get_record(private["did"]) is None
    assert [
        record["did"]
        for record in anonymous.get_records([private["did"], public["did"]])
    ] == []
    auth = Gen3Auth(endpoint=URL, access_token="allowed")
    authenticated = Gen3Index(auth, service_location="")
    with patch.object(auth, "_get_auth_value", return_value="Bearer allowed"):
        assert authenticated.get_record(private["did"])["authz"] == [RESOURCE]
        assert len(authenticated.get_records_on_page()) == 2
        assert len(authenticated.get_records([private["did"], public["did"]])) == 2


def test_standard_sdk_async_discovery(records):
    private, _ = records
    auth = Gen3Auth(endpoint=URL, access_token="allowed")
    index = Gen3Index(auth, service_location="")
    with patch.object(auth, "_get_auth_value", return_value="Bearer allowed"):
        assert (
            asyncio.run(index.async_get_record(private["did"]))["authz"]
            == [RESOURCE]
        )
        assert len(asyncio.run(index.async_get_records_on_page())) == 2
        assert len(asyncio.run(index.async_get_records_from_checksum("a" * 32))) == 1
    anonymous = Gen3Index(URL, service_location="")
    with pytest.raises(aiohttp.ClientResponseError) as error:
        # Bypass the SDK's generic retry decorator for a deterministic denial assertion.
        asyncio.run(anonymous.async_get_record.__wrapped__(anonymous, private["did"]))
    assert error.value.status == 404


def test_browser_cookie_and_metadata_only_identity(records):
    private, _ = records
    target = URL + "/index/" + private["did"]
    assert requests.get(target, cookies={"access_token": "allowed"}).status_code == 200
    assert (
        requests.get(
            target,
            cookies={"access_token": "allowed"},
            headers={"Authorization": "Bearer metadata-only"},
        ).status_code
        == 404
    )


def test_blank_record_is_private_from_creation():
    admin = Gen3Index(URL, auth_provider=("test", "test"), service_location="")
    blank = admin.create_blank(
        "owner", "private.txt", authz=[RESOURCE]
    )
    try:
        assert Gen3Index(URL, service_location="").get_record(blank["did"]) is None
        assert (
            requests.get(
                URL + "/index/" + blank["did"], cookies={"access_token": "allowed"}
            ).status_code
            == 200
        )
    finally:
        admin.delete_record(blank["did"])
