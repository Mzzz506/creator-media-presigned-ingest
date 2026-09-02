from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from .asset_intake import (
    AssetUploadRequest,
    AssetUploadTicket,
    IntakePolicy,
    open_asset_intake,
)
from .infrai_storage import InfraiError, InfraiStorage


BUCKET = os.environ.get("MEDIA_ASSET_BUCKET", "creator-media-assets")
MAX_ASSET_BYTES = 2_000_000_000


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    api_key = os.environ.get("INFRAI_API_KEY")
    if not api_key:
        raise RuntimeError("Set INFRAI_API_KEY before starting the service")

    storage = InfraiStorage(api_key)
    await storage.ensure_bucket(BUCKET)
    app.state.storage = storage
    try:
        yield
    finally:
        await storage.close()


app = FastAPI(title="Creator media intake", lifespan=lifespan)
policy = IntakePolicy(bucket=BUCKET, max_asset_bytes=MAX_ASSET_BYTES)


@app.exception_handler(InfraiError)
async def infrai_error_response(_request: Request, exc: InfraiError) -> JSONResponse:
    status = exc.status_code if 400 <= exc.status_code < 500 else 502
    return JSONResponse(
        status_code=status,
        content={"detail": {"code": exc.code, **exc.detail}},
    )


@app.post("/asset-intakes", response_model=AssetUploadTicket, status_code=201)
async def create_asset_intake(
    request: AssetUploadRequest, http_request: Request
) -> AssetUploadTicket:
    try:
        return await open_asset_intake(
            request,
            policy=policy,
            storage=http_request.app.state.storage,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
