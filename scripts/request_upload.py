import json
import os
import urllib.request


payload = {
    "creator_id": "creator_42",
    "asset_id": "launch-trailer",
    "filename": "launch.mp4",
    "content_type": "video/mp4",
    "size_bytes": 24_000_000,
}
request = urllib.request.Request(
    os.environ.get("MEDIA_SERVICE_URL", "http://127.0.0.1:8000") + "/asset-intakes",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(request) as response:
    print(json.dumps(json.load(response), indent=2))
