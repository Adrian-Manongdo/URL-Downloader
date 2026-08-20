import asyncio
import ipaddress
import os
import shutil
import socket
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from fastapi import FastAPI, Header, HTTPException
from fastapi.background import BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

app = FastAPI(title="VideoFetch", version="1.0.0")

APP_PASSWORD = os.getenv("APP_PASSWORD", "").strip()
MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "750"))
MAX_FILE_BYTES = MAX_FILE_MB * 1024 * 1024
DOWNLOAD_LOCK = asyncio.Lock()

INDEX_HTML = Path(__file__).parent / "templates" / "index.html"


class UrlRequest(BaseModel):
    url: str


def require_password(x_app_password: str | None) -> None:
    if APP_PASSWORD and x_app_password != APP_PASSWORD:
        raise HTTPException(status_code=401, detail="Wrong app password")


def validate_public_url(raw_url: str) -> str:
    raw_url = raw_url.strip()
    parsed = urlparse(raw_url)

    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(status_code=400, detail="Enter a valid http(s) video URL")

    hostname = parsed.hostname.lower()
    if hostname in {"localhost", "localhost.localdomain"}:
        raise HTTPException(status_code=400, detail="Local/private URLs are not allowed")

    try:
        addresses = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        raise HTTPException(status_code=400, detail="Could not resolve that hostname")

    for result in addresses:
        ip = ipaddress.ip_address(result[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise HTTPException(status_code=400, detail="Local/private URLs are not allowed")

    return raw_url


def extract_info_sync(url: str) -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "skip_download": True,
        "socket_timeout": 20,
        "retries": 2,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if info is None:
        raise RuntimeError("No video information was returned")

    return {
        "title": info.get("title") or "Untitled video",
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "site": info.get("extractor_key") or info.get("extractor") or "Unknown",
        "live_status": info.get("live_status"),
    }


def download_sync(url: str) -> tuple[str, str]:
    temp_dir = tempfile.mkdtemp(prefix="videofetch-")
    output_template = str(Path(temp_dir) / "%(title).150s [%(id)s].%(ext)s")

    opts = {
        "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "socket_timeout": 30,
        "retries": 3,
        "fragment_retries": 3,
        "max_filesize": MAX_FILE_BYTES,
        "overwrites": True,
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = (info or {}).get("title") or "video"

        candidates = [
            p for p in Path(temp_dir).iterdir()
            if p.is_file() and p.suffix.lower() not in {".part", ".ytdl", ".json"}
        ]
        if not candidates:
            raise RuntimeError("Download finished but no output file was found")

        output_file = max(candidates, key=lambda p: p.stat().st_size)
        if output_file.stat().st_size > MAX_FILE_BYTES:
            raise RuntimeError(f"Video is larger than the {MAX_FILE_MB} MB app limit")

        return str(output_file), title
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return INDEX_HTML.read_text(encoding="utf-8")


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.post("/api/info")
async def info_endpoint(
    payload: UrlRequest,
    x_app_password: str | None = Header(default=None),
) -> dict:
    require_password(x_app_password)
    url = validate_public_url(payload.url)

    try:
        return await asyncio.to_thread(extract_info_sync, url)
    except yt_dlp.utils.DownloadError as exc:
        raise HTTPException(status_code=400, detail=f"Could not read this video: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/download")
async def download_endpoint(
    payload: UrlRequest,
    background_tasks: BackgroundTasks,
    x_app_password: str | None = Header(default=None),
):
    require_password(x_app_password)
    url = validate_public_url(payload.url)

    async with DOWNLOAD_LOCK:
        try:
            file_path, _title = await asyncio.to_thread(download_sync, url)
        except yt_dlp.utils.DownloadError as exc:
            raise HTTPException(status_code=400, detail=f"Download failed: {exc}")
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    parent_dir = str(Path(file_path).parent)
    background_tasks.add_task(shutil.rmtree, parent_dir, True)

    safe_name = Path(file_path).name
    return FileResponse(
        file_path,
        filename=safe_name,
        media_type="application/octet-stream",
        background=background_tasks,
    )
