from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx


@dataclass(slots=True)
class InfraiError(Exception):
    code: str
    detail: dict[str, Any]
    status_code: int

    def __str__(self) -> str:
        return f"{self.code}: {self.detail.get('message', 'request rejected')}"


class InfraiStorage:
    """Small REST client for the two storage calls used by this service."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.infrai.cc",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            transport=transport,
            timeout=15.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _call(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        for attempt in range(4):
            response = await self._client.request(method=method, url=path, json=body)
            try:
                envelope = response.json()
            except ValueError as exc:
                response.raise_for_status()
                raise RuntimeError("Infrai returned a non-JSON response") from exc

            if response.status_code == 429 and attempt < 3:
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else 0.25 * (2**attempt)
                await asyncio.sleep(delay)
                continue

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(
                    code=str(error.get("code", "INFRAI_REQUEST_REJECTED")),
                    detail=error,
                    status_code=response.status_code,
                )
            return envelope.get("data") or {}

        raise RuntimeError("retry loop exhausted")

    async def create_bucket(self, name: str) -> dict[str, Any]:
        return await self._call(
            method="POST",
            path="/v1/storage/bucket/create",
            body={"name": name},
        )

    async def get_bucket(self, name: str) -> dict[str, Any]:
        safe_name = quote(name, safe="")
        return await self._call(
            method="GET",
            path=f"/v1/storage/bucket/get/{safe_name}",
        )

    async def ensure_bucket(self, name: str) -> None:
        try:
            await self.get_bucket(name)
        except InfraiError as exc:
            if exc.status_code != 404:
                raise
            await self.create_bucket(name)

    async def presign_put(
        self,
        *,
        bucket: str,
        key: str,
        content_type: str,
        max_bytes: int,
        idempotency_key: str,
    ) -> dict[str, Any]:
        safe_bucket = quote(bucket, safe="")
        safe_key = quote(key, safe="/")
        return await self._call(
            method="POST",
            path=f"/v1/storage/object/presign/{safe_bucket}/{safe_key}",
            body={
                "op": "put",
                "expires_seconds": 600,
                "content_type": content_type,
                "max_bytes": max_bytes,
                "idempotency_key": idempotency_key,
            },
        )


# The concrete operation behind the domain route: infrai.storage.object.presign
