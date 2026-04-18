from flask import Flask, request, jsonify, Response, send_from_directory
import yt_dlp
import os

app = Flask(__name__, static_folder="static")

def get_ydl_opts():
    return {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
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
            "default_search": "ytsearch10",
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
                "thumbnail": entry.get("thumbnail") or "https://img.youtube.com/vi/" + str(entry.get("id")) + "/mqdefault.jpg",
                "view_count": entry.get("view_count"),
            })
        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/info")
def video_info():
    vid = request.args.get("id", "")
    if not vid:
        return jsonify({"error": "ID kosong"}), 400
    try:
        url = "https://www.youtube.com/watch?v=" + vid
        ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        
        formats = []
        seen = set()
        for f in info.get("formats", []):
            height = f.get("height")
            ext = f.get("ext")
            if height and ext == "mp4" and height not in seen and height <= 720:
                seen.add(height)
                formats.append({"format_id": f["format_id"], "height": height, "ext": ext})
        formats.sort(key=lambda x: x["height"], reverse=True)

        return jsonify({
            "id": info.get("id"),
            "title": info.get("title"),
            "uploader": info.get("uploader"),
            "duration": info.get("duration"),
            "thumbnail": info.get("thumbnail"),
            "description": (info.get("description") or "")[:300],
            "formats": formats,
        })
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
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "format": "bestvideo[ext=mp4][height<=" + quality + "]+bestaudio[ext=m4a]/best[ext=mp4][height<=" + quality + "]",
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        
        # Ambil URL stream langsung
        if "url" in info:
            stream_url = info["url"]
        else:
            # Cari format terbaik
            formats = info.get("formats", [])
            stream_url = None
            for f in reversed(formats):
                if f.get("vcodec") != "none" and f.get("acodec") != "none":
                    stream_url = f.get("url")
                    break
            if not stream_url and formats:
                stream_url = formats[-1].get("url")

        return jsonify({"url": stream_url, "title": info.get("title")})
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
        ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        if mode == "audio":
            # Cari format audio terbaik
            for f in reversed(info.get("formats", [])):
                if f.get("acodec") != "none" and f.get("vcodec") == "none":
                    return jsonify({"url": f["url"], "title": info.get("title"), "ext": f.get("ext", "m4a")})
            return jsonify({"error": "Format audio tidak ditemukan"}), 404
        else:
            for f in reversed(info.get("formats", [])):
                h = f.get("height", 0)
                if h and h <= int(quality) and f.get("ext") == "mp4" and f.get("vcodec") != "none":
                    return jsonify({"url": f["url"], "title": info.get("title"), "ext": "mp4"})
            return jsonify({"error": "Format tidak ditemukan"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
