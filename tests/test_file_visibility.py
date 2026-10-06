"""Download-only permission must work without a discoverable IndexD filename."""

from unittest.mock import MagicMock, patch

import pytest
from gen3.auth import Gen3Auth
from gen3.file import Gen3File


@pytest.mark.parametrize(
    "record,name",
    [(None, "private-guid"), ({"file_name": "visible.txt"}, "visible.txt")],
)
@pytest.mark.parametrize("retry", [False, True])
def test_download_single_preserves_independent_storage_access(
    tmp_path, record, name, retry
):
    content = b"approved download"
    file = Gen3File(Gen3Auth(endpoint="https://commons.example", access_token="caller"))
    response = MagicMock(status_code=200, headers={"content-length": str(len(content))})
    response.iter_content.return_value = iter([content])
    index = MagicMock()
    index.get_record.return_value = record
    responses = [MagicMock(status_code=503), response] if retry else [response]
    with patch.object(
        file,
        "get_presigned_url",
        return_value={"url": "https://objects.example/approved"},
    ), patch("gen3.file.requests.get", side_effect=responses) as get, patch(
        "gen3.file.Gen3Index", return_value=index
    ), patch(
        "gen3.file.time.sleep"
    ):
        assert file.download_single("dg.MMRF/private-guid", tmp_path) is True
        assert (tmp_path / name).read_bytes() == content
        assert get.call_count == (2 if retry else 1)
        assert all(
            call.args[0] == "https://objects.example/approved"
            for call in get.call_args_list
        )
        index.get_record.assert_called_once_with("dg.MMRF/private-guid")


def test_discovery_does_not_bypass_a_denied_signed_download(tmp_path):
    file = Gen3File(Gen3Auth(endpoint="https://commons.example", access_token="caller"))
    with patch.object(
        file, "get_presigned_url", side_effect=RuntimeError("Fence denied")
    ), patch("gen3.file.requests.get") as get, patch("gen3.file.Gen3Index") as index:
        assert file.download_single("private-guid", tmp_path) is False
        get.assert_not_called()
        index.assert_not_called()
        assert list(tmp_path.iterdir()) == []
