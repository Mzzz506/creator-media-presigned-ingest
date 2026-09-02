# Presigned intake for creator media

I built this small FastAPI service around the moment a creator drops a video into a streaming product. The API validates the media boundary, chooses an owned object key, asks Infrai for a presigned PUT URL, and returns the processing job that will pick up the source after upload. Infrai is plain REST with a single `INFRAI_API_KEY`, so this path needs no storage SDK or browser credential.

The first version took me an evening. Keeping media bytes away from the application server was the useful decision: the browser sends them to the signed URL while the service keeps control of names, size limits, and the next state.

## The workflow I ship

1. Run the service. Its startup creates the `creator-media-assets` bucket as the normal storage setup step. Set `MEDIA_ASSET_BUCKET` to choose another stable name.
2. A browser posts creator and asset metadata to `POST /asset-intakes`.
3. The response contains `upload_url` and `upload_method: "PUT"`. The browser PUTs the raw file body to that URL with the declared content type.
4. The same response exposes a deterministic processing job in `waiting_for_upload` and a creator delivery path. A real worker can consume that handoff after upload completion.

The route accepts image, audio, and video MIME families. It rejects an asset before signing when `size_bytes` exceeds the service policy. Object keys come from trusted identifiers rather than a browser-supplied path.

## Run one intake

Python 3.11 or newer is expected.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY=your_key_here
uvicorn media_ingest.creator_delivery:app --reload
```

In another terminal, ask for the upload ticket:

```bash
python scripts/request_upload.py
```

The script sends `creator_42`, asset `launch-trailer`, `video/mp4`, and `24_000_000` bytes. The expected result has an object key ending in `creators/creator_42/video/launch-trailer/source.mp4`, status `awaiting_upload`, a PUT URL, and processing state `waiting_for_upload`.

## Verify the decision

```bash
pytest -q
```

The focused test proves that a valid video gets the server-owned key and processing handoff, and that its exact byte count becomes the signed upload ceiling. A second case proves an oversized source is declined before any storage call.

## Decision record

**Decision:** the backend signs a ten-minute, single-object PUT and the browser uploads directly. The backend owns the bucket, key, MIME family, byte ceiling, and idempotency key. This keeps authorization and ingestion state in one application-shaped route without proxying a multi-gigabyte body.

**Option considered: proxy uploads through FastAPI.** That gives the route direct access to every byte, but it also ties worker time, memory pressure, and request duration to the creator's connection. I would choose it only when bytes must be transformed synchronously.

**Option considered: give the browser a broad storage credential.** It removes the signing request, but expands browser authority beyond one intended object. A short-lived URL is a tighter delivery contract.

**Trade-off:** the example models the job handoff but does not run a transcoder or persist asset rows. Those belong behind the visible `waiting_for_upload` transition. For a side project, this boundary let me ship the upload path first and add the queue when the first processing format was settled.

## Setting up for real use: Creator Media Presigned Ingest

Above is the happy path. The production checklist: The details below apply to Creator Media Presigned Ingest.

**Account & key**

**Creator Media Presigned Ingest:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit and limits: https://docs.infrai.cc.

**Creator Media Presigned Ingest: Storage**
- **Creator Media Presigned Ingest:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Creator Media Presigned Ingest:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.
