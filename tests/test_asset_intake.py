import pytest

from media_ingest.asset_intake import AssetUploadRequest, IntakePolicy, open_asset_intake


class RecordingStorage:
    def __init__(self) -> None:
        self.call: dict[str, object] = {}

    async def presign_put(self, **kwargs: object) -> dict[str, object]:
        self.call = kwargs
        return {"url": "https://uploads.example/signed-source"}


@pytest.mark.asyncio
async def test_video_intake_scopes_upload_and_schedules_processing() -> None:
    storage = RecordingStorage()
    request = AssetUploadRequest(
        creator_id="creator_42",
        asset_id="launch-trailer",
        filename="launch.mp4",
        content_type="video/mp4",
        size_bytes=24_000_000,
    )

    ticket = await open_asset_intake(
        request,
        policy=IntakePolicy(bucket="creator-media-assets", max_asset_bytes=50_000_000),
        storage=storage,
    )

    assert ticket.object_key == (
        "creators/creator_42/video/launch-trailer/source.mp4"
    )
    assert ticket.status == "awaiting_upload"
    assert ticket.processing.state == "waiting_for_upload"
    assert ticket.processing.source_key == ticket.object_key
    assert storage.call == {
        "bucket": "creator-media-assets",
        "key": ticket.object_key,
        "content_type": "video/mp4",
        "max_bytes": 24_000_000,
        "idempotency_key": "asset-upload-creator_42-launch-trailer",
    }


@pytest.mark.asyncio
async def test_oversize_asset_is_rejected_before_signing() -> None:
    storage = RecordingStorage()
    request = AssetUploadRequest(
        creator_id="creator_42",
        asset_id="raw-cut",
        filename="raw.mov",
        content_type="video/quicktime",
        size_bytes=51_000_000,
    )

    with pytest.raises(ValueError, match="intake limit"):
        await open_asset_intake(
            request,
            policy=IntakePolicy(
                bucket="creator-media-assets", max_asset_bytes=50_000_000
            ),
            storage=storage,
        )

    assert storage.call == {}
