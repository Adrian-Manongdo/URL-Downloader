# VideoFetch

A small personal web app for downloading public videos that `yt-dlp` supports. The Docker image includes FFmpeg plus Deno for current YouTube JavaScript-challenge support.

Use it only for media you own or have permission to download. It does not include DRM bypass, cookie importing, account-login bypasses, or paywall circumvention.

## Deploy free on Render

1. Create a new GitHub repository.
2. Upload all files in this folder to the repository root.
3. In Render, choose **New > Blueprint** and connect the repository.
4. Render reads `render.yaml` and builds the Docker image automatically.
5. When prompted for `APP_PASSWORD`, enter a private password. This is strongly recommended so strangers cannot burn your bandwidth.
6. Deploy, then open the generated `*.onrender.com` URL.

The first visit after the service has been idle can be slow because Render free services sleep after inactivity.

## Run locally

Install FFmpeg, then:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

Open http://localhost:8000

Optional environment variables:

- `APP_PASSWORD` — protects the downloader with a simple shared password.
- `MAX_FILE_MB` — maximum file size. Default: `750`.

## Notes

- Public video-site support depends on `yt-dlp` and can change when sites change.
- Some websites require authentication or use DRM. This app intentionally does not bypass those restrictions.
- Render's filesystem is temporary, which is fine here because files are deleted after they are sent to the browser.
- Video downloads consume outbound bandwidth quickly, so this is best kept as a personal tool.
