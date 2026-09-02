from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, Field, field_validator


AssetKind = Literal["video", "audio", "image"]


class AssetUploadRequest(BaseModel):
    creator_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    asset_id: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    filename: str = Field(min_length=1, max_length=180)
    content_type: str
    size_bytes: int = Field(gt=0)

    @field_validator("filename")
    @classmethod
    def filename_must_be_plain(cls, value: str) -> str:
        if Path(value).name != value:
            raise ValueError("filename must not contain a path")
        return value


class ProcessingJob(BaseModel):
    job_id: str
    state: Literal["waiting_for_upload"]
    source_key: str


class AssetUploadTicket(BaseModel):
    asset_id: str
    upload_url: str
    upload_method: Literal["PUT"] = "PUT"
    object_key: str
    status: Literal["awaiting_upload"] = "awaiting_upload"
    processing: ProcessingJob
    creator_delivery_path: str


class PresignStore(Protocol):
    async def presign_put(
        self,
        *,
        bucket: str,
        key: str,
        content_type: str,
        max_bytes: int,
        idempotency_key: str,
    ) -> dict[str, object]:
        raise AssertionError("typing protocol only")


@dataclass(frozen=True, slots=True)
class IntakePolicy:
    bucket: str
    max_asset_bytes: int

    def classify(self, content_type: str) -> AssetKind:
        prefix = content_type.split("/", 1)[0]
        if prefix not in {"video", "audio", "image"}:
            raise ValueError("content_type must be video, audio, or image media")
        return prefix  # type: ignore[return-value]

    def object_key(self, request: AssetUploadRequest) -> str:
        kind = self.classify(request.content_type)
        suffix = re.sub(r"[^a-zA-Z0-9._-]", "-", Path(request.filename).suffix.lower())
        return f"creators/{request.creator_id}/{kind}/{request.asset_id}/source{suffix}"


async def open_asset_intake(
    request: AssetUploadRequest,
    *,
    policy: IntakePolicy,
    storage: PresignStore,
) -> AssetUploadTicket:
    if request.size_bytes > policy.max_asset_bytes:
        raise ValueError(f"asset exceeds the {policy.max_asset_bytes}-byte intake limit")

    key = policy.object_key(request)
    signed = await storage.presign_put(
        bucket=policy.bucket,
        key=key,
        content_type=request.content_type,
        max_bytes=request.size_bytes,
        idempotency_key=f"asset-upload-{request.creator_id}-{request.asset_id}",
    )
    upload_url = signed.get("url")
    if not isinstance(upload_url, str):
        raise RuntimeError("presign response did not contain a URL")

    return AssetUploadTicket(
        asset_id=request.asset_id,
        upload_url=upload_url,
        object_key=key,
        processing=ProcessingJob(
            job_id=f"process-{request.asset_id}",
            state="waiting_for_upload",
            source_key=key,
        ),
        creator_delivery_path=f"/creators/{request.creator_id}/assets/{request.asset_id}",
    )
