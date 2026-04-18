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
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
        }
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

@app.route("/api/stream")
def stream():
    vid = request.args.get("id", "")
    quality = request.args.get("q", "720")
    if not vid:
        return jsonify({"error": "ID kosong"}), 400
    try:
        url = "https://www.youtube.com/watch?v=" + vid

        # Format berbeda untuk setiap kualitas
        fmt_map = {
            "360": "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]/worst[ext=mp4]",
            "480": "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best[height<=480]",
            "720": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]",
        }
        fmt = fmt_map.get(quality, fmt_map["720"])

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "format": fmt,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        # Cari URL stream yang punya video+audio
        stream_url = None
        actual_height = None

        # Kalau format sudah merged (ada url langsung)
        if info.get("url"):
            stream_url = info["url"]
            actual_height = info.get("height")
        else:
            # Cari format dengan video+audio sekaligus
            for f in reversed(info.get("formats", [])):
                h = f.get("height", 0) or 0
                has_video = f.get("vcodec", "none") != "none"
                has_audio = f.get("acodec", "none") != "none"
                if has_video and has_audio and h <= int(quality) and h > 0:
                    stream_url = f.get("url")
                    actual_height = h
                    break

            # Fallback: ambil format apapun yang ada
            if not stream_url:
                for f in reversed(info.get("formats", [])):
                    if f.get("url"):
                        stream_url = f.get("url")
                        actual_height = f.get("height")
                        break

        if not stream_url:
            return jsonify({"error": "Stream URL tidak ditemukan"}), 404

        return jsonify({
            "url": stream_url,
            "title": info.get("title"),
            "actual_quality": str(actual_height) + "p" if actual_height else quality + "p"
        })
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

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "format": fmt,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        # Ambil URL download
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
                    has_video = f.get("vcodec", "none") != "none"
                    has_audio = f.get("acodec", "none") != "none"
                    if has_video and has_audio and h <= int(quality) and h > 0:
                        dl_url = f.get("url")
                        dl_ext = f.get("ext", "mp4")
                        break

            if not dl_url and formats:
                dl_url = formats[-1].get("url")
                dl_ext = formats[-1].get("ext", ext)

        if not dl_url:
            return jsonify({"error": "URL download tidak ditemukan"}), 404

        # Proxy download agar browser bisa download langsung
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
