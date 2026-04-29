"""Asset upload/serve routes.

Assets are space-scoped images/SVGs the composer can reference in image layers.
Files live under `data/assets/{space_id}/{asset_id}{ext}` and are served via
`/assets/file/{asset_id}` so the vite dev proxy (which forwards `/api` only)
does not need extra config — we serve through `/api/assets/...` in prod too.
"""

import mimetypes
import shutil
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.database.assets import (
    create_asset,
    delete_asset,
    get_asset,
    get_asset_path,
    list_space_assets,
)
from app.database.spaces import get_space

router = APIRouter(tags=["assets"])

ASSETS_ROOT = Path("data/assets")
ALLOWED_MIMES = {"image/png", "image/jpeg", "image/svg+xml", "image/webp", "image/gif"}
ALLOWED_EXTS = {".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif"}


@router.post("/spaces/{space_id}/assets")
async def upload_asset(space_id: str, file: UploadFile, tags: str | None = None):
    """Upload an image asset scoped to a space."""
    if get_space(space_id) is None:
        raise HTTPException(status_code=404, detail="Space not found")

    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"Extension '{ext}' not allowed. Use: {sorted(ALLOWED_EXTS)}",
        )

    mime = file.content_type or mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"
    if mime not in ALLOWED_MIMES:
        # Be lenient — infer from extension
        mime = mimetypes.guess_type(file.filename or "")[0] or "image/png"

    space_dir = ASSETS_ROOT / space_id
    space_dir.mkdir(parents=True, exist_ok=True)

    # Create the record first so we get an id, then write the file at {id}{ext}
    # (two-step because we want the file name to match the id for traceability)
    # Instead: generate id via create_asset with tentative path, then rename.
    # Simpler: write to temp, create record with real path.
    from uuid import uuid4
    tentative_id = str(uuid4())
    save_path = space_dir / f"{tentative_id}{ext}"

    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
    url = f"/api/assets/file/{tentative_id}"

    # Insert DB row using the same id we used for the filename
    # (create_asset generates its own uuid, so we call the underlying insert path)
    from app.database.connection import get_connection
    import json as _json
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO assets (id, space_id, filename, mime, path, url, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                tentative_id, space_id, file.filename or "asset", mime,
                str(save_path), url, _json.dumps(tag_list),
            ],
        )
    finally:
        conn.close()

    asset = get_asset(tentative_id)
    return asset.model_dump() if asset else {"id": tentative_id, "url": url}


class AssetFromUrlRequest(BaseModel):
    url: str
    tags: str | None = None


MAX_DOWNLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/spaces/{space_id}/assets/from-url")
async def upload_asset_from_url(space_id: str, request: AssetFromUrlRequest):
    """Fetch an image from a public URL and store it as a space asset."""
    if get_space(space_id) is None:
        raise HTTPException(status_code=404, detail="Space not found")

    parsed = urlparse(request.url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="URL must be http(s)")

    # Fetch with size + content-type guards
    headers = {
        # Many CDNs (incl. Wikimedia) return 403 without a real-looking UA.
        "User-Agent": "Mozilla/5.0 (compatible; SpaceDashboard/0.2) httpx",
        "Accept": "image/*,*/*;q=0.8",
    }
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0, headers=headers) as client:
            resp = await client.get(request.url)
            resp.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=400, detail=f"Download failed: {e}")

    content = resp.content
    if len(content) > MAX_DOWNLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (>10 MB)")

    mime = (resp.headers.get("content-type") or "").split(";")[0].strip() or "application/octet-stream"
    if mime not in ALLOWED_MIMES and not mime.startswith("image/"):
        raise HTTPException(status_code=400, detail=f"URL is not an image (content-type={mime})")

    # Determine extension from URL path, then content-type
    url_path = parsed.path or ""
    ext = Path(url_path).suffix.lower()
    if ext not in ALLOWED_EXTS:
        guessed = mimetypes.guess_extension(mime) or ""
        ext = guessed if guessed in ALLOWED_EXTS else ".png"

    space_dir = ASSETS_ROOT / space_id
    space_dir.mkdir(parents=True, exist_ok=True)

    asset_id = str(uuid4())
    save_path = space_dir / f"{asset_id}{ext}"
    save_path.write_bytes(content)

    filename = Path(url_path).name or f"from-url{ext}"
    tag_list = [t.strip() for t in (request.tags or "").split(",") if t.strip()]
    url_public = f"/api/assets/file/{asset_id}"

    from app.database.connection import get_connection
    import json as _json
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO assets (id, space_id, filename, mime, path, url, tags) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [asset_id, space_id, filename, mime, str(save_path), url_public, _json.dumps(tag_list)],
        )
    finally:
        conn.close()

    asset = get_asset(asset_id)
    return asset.model_dump() if asset else {"id": asset_id, "url": url_public}


@router.get("/spaces/{space_id}/assets")
async def list_assets(space_id: str):
    if get_space(space_id) is None:
        raise HTTPException(status_code=404, detail="Space not found")
    assets = list_space_assets(space_id)
    return {"assets": [a.model_dump() for a in assets]}


@router.get("/assets/file/{asset_id}")
async def serve_asset(asset_id: str):
    path = get_asset_path(asset_id)
    if path is None or not Path(path).exists():
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(path)


@router.delete("/assets/{asset_id}")
async def remove_asset(asset_id: str):
    path = delete_asset(asset_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    p = Path(path)
    if p.exists():
        p.unlink()
    return {"status": "deleted", "asset_id": asset_id}
