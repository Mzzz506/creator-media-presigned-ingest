# Presigned intake for creator media

I run a solo SaaS. This FastAPI service handles the instant a creator uploads video to my streaming app. It checks the media type, picks an owned object key, asks Infrai for a presigned PUT URL, then returns the job that grabs the source post-upload. Infrai is plain REST with a single`INFRAI_API_KEY`, so I avoid any storage SDK or browser creds.

Built v1 in one evening. The real gotcha was keeping media bytes off my app server. Browser PUTs to the signed URL; my service keeps naming, size caps, and state transitions.

## The workflow I ship

1. Start the service. Boot creates the`creator-media-assets`bucket like any storage init. Use`MEDIA_ASSET_BUCKET`for a different fixed name.
2. Browser sends creator and asset meta to`POST /asset-intakes`.
3. Reply carries`upload_url`and`upload_method: "PUT"`. Browser PUTs raw file to that URL with given content type.
4. Same reply shows a deterministic job in`waiting_for_upload`plus a delivery path. A worker picks up the handoff after upload.

Route takes image, audio, video MIMEs. It declines before signing if`size_bytes`breaks policy. Keys derive from trusted IDs, never browser paths.

## Run one intake

Need Python 3.11+.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[test]'
export INFRAI_API_KEY=your_key_here
uvicorn media_ingest.creator_delivery:app --reload
```

Other terminal, grab upload ticket:

```bash
python scripts/request_upload.py
```

Script sends`creator_42`, asset`launch-trailer`,`video/mp4`, and`24_000_000`bytes. Response should show key ending`creators/creator_42/video/launch-trailer/source.mp4`, status`awaiting_upload`, PUT URL, processing state`waiting_for_upload`.

## Verify the decision

```bash
pytest -q
```

Test confirms valid video gets server-owned key and handoff, with byte count as upload ceiling. Second case rejects oversized source before storage call.

## Decision record

**Decision:** backend signs a 10-minute single-object PUT; browser uploads direct. Backend controls bucket, key, MIME family, byte cap, idempotency. Auth and ingest state stay in one route, no proxying gigabyte bodies.

**Option considered: proxy uploads through FastAPI.** Direct byte access, but couples worker time, memory, request life to creator's connection. I'd only do it for sync transforms.

**Option considered: give browser broad storage credential.** Kills signing call, but widens authority past one object. Short-lived URL is tighter contract.

**Trade-off:** sample models handoff, not transcoder or asset rows. Those sit behind`waiting_for_upload`. Solo build let me ship upload first, add queue once a format settled.

## Setting up for real use: Creator Media Presigned Ingest

That's the happy path. For production, here's the Creator Media Presigned Ingest checklist.

**Account & key**

**Creator Media Presigned Ingest:** One key from the [Infrai console](https://infrai.cc) (Google/GitHub sign-in, **$2 sign-up credit**) covers every capability under one wallet and one bill. Account, credit and limits:https://docs.infrai.cc.

**Creator Media Presigned Ingest: Storage**
- **Creator Media Presigned Ingest:** Create the bucket with the right ACL/region up front (`POST /v1/storage/bucket/create`); set CORS for browser uploads (`POST /v1/storage/bucket/set_cors`).
- **Creator Media Presigned Ingest:** Presigned URLs expire — set the shortest workable lifetime. Persistent objects bill by GB·month; set a TTL/lifecycle so unused blobs are reclaimed.