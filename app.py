from flask import Flask, request, jsonify, Response, send_from_directory
import yt_dlp
import os
import requests

app = Flask(__name__, static_folder="static")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/api/search")
def search():
    q = request.args.get("q", "")
    if not q:
        return jsonify({"error": "Query kosong"}), 400
    try:
        ydl_opts = {"quiet": True, "no_warnings": True, "extract_flat": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info("ytsearch10:" + q, download=False)
        results = []
        for entry in info.get("entries", []):
            if not entry:
                continue
            results.append({
                "id": entry.get("id"),
                "title": entry.get("title"),
                "uploader": entry.get("uploader") or entry.get("channel"),
                "duration": entry.get("duration"),
                "thumbnail": "https://img.youtube.com/vi/" + str(entry.get("id")) + "/mqdefault.jpg",
                "view_count": entry.get("view_count"),
            })
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/audio_url")
def audio_url():
    """Ambil URL stream audio langsung untuk background play."""
    vid = request.args.get("id", "")
    if not vid:
        return jsonify({"error": "ID kosong"}), 400
    try:
        url = "https://www.youtube.com/watch?v=" + vid
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "format": "bestaudio[ext=m4a]/bestaudio/best",
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        audio_url = None
        if info.get("url"):
            audio_url = info["url"]
        else:
            for f in reversed(info.get("formats", [])):
                if f.get("acodec") != "none" and f.get("url"):
                    audio_url = f["url"]
                    break

        if not audio_url:
            return jsonify({"error": "URL audio tidak ditemukan"}), 404

        return jsonify({
            "url": audio_url,
            "title": info.get("title"),
            "uploader": info.get("uploader"),
            "thumbnail": info.get("thumbnail"),
            "duration": info.get("duration"),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/audio_stream")
def audio_stream():
    """Proxy stream audio — support range request untuk seekbar."""
    vid = request.args.get("id", "")
    if not vid:
        return jsonify({"error": "ID kosong"}), 400
    try:
        url = "https://www.youtube.com/watch?v=" + vid
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "format": "bestaudio[ext=m4a]/bestaudio/best",
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        audio_src = None
        content_type = "audio/mp4"
        if info.get("url"):
            audio_src = info["url"]
            content_type = "audio/" + (info.get("ext") or "mp4")
        else:
            for f in reversed(info.get("formats", [])):
                if f.get("acodec") != "none" and f.get("url"):
                    audio_src = f["url"]
                    content_type = "audio/" + (f.get("ext") or "mp4")
                    break

        if not audio_src:
            return jsonify({"error": "URL tidak ditemukan"}), 404

        # Forward range header kalau ada
        range_header = request.headers.get("Range")
        proxy_headers = dict(HEADERS)
        if range_header:
            proxy_headers["Range"] = range_header

        r = requests.get(audio_src, headers=proxy_headers, stream=True, timeout=30)

        resp_headers = {
            "Content-Type": content_type,
            "Accept-Ranges": "bytes",
        }
        if "Content-Length" in r.headers:
            resp_headers["Content-Length"] = r.headers["Content-Length"]
        if "Content-Range" in r.headers:
            resp_headers["Content-Range"] = r.headers["Content-Range"]

        def generate():
            for chunk in r.iter_content(chunk_size=1024 * 64):
                yield chunk

        status = 206 if range_header else 200
        return Response(generate(), status=status, headers=resp_headers)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/download")
def download():
    vid = request.args.get("id", "")
    mode = request.args.get("mode", "video")
    quality = request.args.get("q", "720")
    if not vid:
        return jsonify({"error": "ID kosong"}), 400
    try:
        url = "https://www.youtube.com/watch?v=" + vid
        if mode == "audio":
            fmt = "bestaudio[ext=m4a]/bestaudio/best"
            ext = "m4a"
        else:
            fmt_map = {
                "360": "best[height<=360][ext=mp4]/bestvideo[height<=360]+bestaudio/best[height<=360]",
                "480": "best[height<=480][ext=mp4]/bestvideo[height<=480]+bestaudio/best[height<=480]",
                "720": "best[height<=720][ext=mp4]/bestvideo[height<=720]+bestaudio/best[height<=720]",
            }
            fmt = fmt_map.get(quality, fmt_map["720"])
            ext = "mp4"

        ydl_opts = {"quiet": True, "no_warnings": True, "format": fmt}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        dl_url = None
        dl_ext = ext
        title = info.get("title", "video")

        if info.get("url"):
            dl_url = info["url"]
            dl_ext = info.get("ext", ext)
        else:
            formats = info.get("formats", [])
            if mode == "audio":
                for f in reversed(formats):
                    if f.get("acodec") != "none" and f.get("vcodec") == "none":
                        dl_url = f.get("url")
                        dl_ext = f.get("ext", "m4a")
                        break
            else:
                for f in reversed(formats):
                    h = f.get("height", 0) or 0
                    if f.get("vcodec","none") != "none" and f.get("acodec","none") != "none" and h <= int(quality):
                        dl_url = f.get("url")
                        dl_ext = f.get("ext", "mp4")
                        break
            if not dl_url and formats:
                dl_url = formats[-1].get("url")
                dl_ext = formats[-1].get("ext", ext)

        if not dl_url:
            return jsonify({"error": "URL download tidak ditemukan"}), 404

        safe_title = "".join(c for c in title if c.isalnum() or c in " -_")[:60]
        filename = safe_title + "." + dl_ext

        def generate():
            with requests.get(dl_url, headers=HEADERS, stream=True, timeout=60) as r:
                r.raise_for_status()
                for chunk in r.iter_content(chunk_size=1024 * 512):
                    yield chunk

        return Response(
            generate(),
            headers={
                "Content-Disposition": 'attachment; filename="' + filename + '"',
                "Content-Type": "video/mp4" if mode == "video" else "audio/m4a",
            }
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
