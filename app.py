from flask import Flask, request, jsonify, Response, send_from_directory
import yt_dlp
import os
import requests
import random

app = Flask(__name__, static_folder="static")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# Kategori untuk FYP beranda
FYP_KEYWORDS = [
    "trending music 2025", "viral video 2025", "top hits 2025",
    "music mix 2025", "popular songs 2025", "best songs 2025",
    "trending indonesia 2025", "lagu viral 2025", "top indonesia 2025",
    "donghua terbaik 2025", "anime ost 2025", "lofi music",
    "chill music 2025", "workout music 2025", "gaming music 2025",
]

@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/api/search")
def search():
    q = request.args.get("q", "")
    limit = int(request.args.get("limit", "20"))
    if not q:
        return jsonify({"error": "Query kosong"}), 400
    try:
        ydl_opts = {"quiet": True, "no_warnings": True, "extract_flat": True}
        search_query = f"ytsearch{limit}:{q}"
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_query, download=False)
        results = []
        for entry in info.get("entries", []):
            if not entry: continue
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

@app.route("/api/fyp")
def fyp():
    """Ambil banyak video untuk beranda FYP dari berbagai kategori."""
    try:
        # Ambil dari beberapa keyword sekaligus
        keywords = random.sample(FYP_KEYWORDS, min(5, len(FYP_KEYWORDS)))
        all_results = []
        seen_ids = set()

        ydl_opts = {"quiet": True, "no_warnings": True, "extract_flat": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            for kw in keywords:
                try:
                    info = ydl.extract_info(f"ytsearch8:{kw}", download=False)
                    for entry in info.get("entries", []):
                        if not entry: continue
                        vid_id = entry.get("id")
                        if vid_id and vid_id not in seen_ids:
                            seen_ids.add(vid_id)
                            all_results.append({
                                "id": vid_id,
                                "title": entry.get("title"),
                                "uploader": entry.get("uploader") or entry.get("channel"),
                                "duration": entry.get("duration"),
                                "thumbnail": "https://img.youtube.com/vi/" + str(vid_id) + "/mqdefault.jpg",
                                "view_count": entry.get("view_count"),
                            })
                except: continue

        random.shuffle(all_results)
        return jsonify({"results": all_results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/audio_url")
def audio_url():
    vid = request.args.get("id", "")
    if not vid:
        return jsonify({"error": "ID kosong"}), 400
    try:
        url = "https://www.youtube.com/watch?v=" + vid
        ydl_opts = {
            "quiet": True, "no_warnings": True,
            "format": "bestaudio[ext=m4a]/bestaudio/best",
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        audio_src = info.get("url")
        if not audio_src:
            for f in reversed(info.get("formats", [])):
                if f.get("acodec") != "none" and f.get("url"):
                    audio_src = f["url"]; break

        if not audio_src:
            return jsonify({"error": "URL audio tidak ditemukan"}), 404

        return jsonify({
            "url": audio_src,
            "title": info.get("title"),
            "uploader": info.get("uploader"),
            "thumbnail": "https://img.youtube.com/vi/" + vid + "/maxresdefault.jpg",
            "duration": info.get("duration"),
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Stopword untuk filter keyword
_STOPWORDS = {
    "official","video","audio","lyrics","lyric","hd","4k","full","song","music",
    "mv","feat","ft","the","a","an","and","or","of","in","on","at","to","is",
    "cover","version","ver","reprise","remix","female","male","lofi","slowed",
    "reverb","acoustic","live","instrumental","extended","edit","vevo","with",
    "new","hindi","english","punjabi","tamil","telugu","kannada","malayalam",
}

def make_keywords(title, uploader, vid_id):
    """Buat beberapa variasi keyword dari judul + channel untuk search paralel."""
    words = [w for w in title.lower().split() if len(w) > 2 and w not in _STOPWORDS]
    keywords = []
    # Keyword 1: 3-4 kata bermakna dari judul
    if words:
        keywords.append(" ".join(words[:4]))
    # Keyword 2: judul asli (tanpa filter) tapi pendek
    raw_words = title.split()
    if len(raw_words) >= 2:
        keywords.append(" ".join(raw_words[:3]))
    # Keyword 3: channel/uploader saja — cari video dari artis yang sama
    if uploader and uploader.lower() not in _STOPWORDS:
        keywords.append(uploader)
    # Keyword 4: kombinasi channel + kata pertama judul
    if uploader and words:
        keywords.append(f"{uploader} {words[0]}")
    # Dedupe, buang yang kosong
    seen = set()
    result = []
    for k in keywords:
        k = k.strip()
        if k and k not in seen:
            seen.add(k)
            result.append(k)
    return result

@app.route("/api/next")
def next_videos():
    """Ambil video rekomendasi Up Next — multi-keyword paralel seperti YouTube."""
    vid   = request.args.get("id", "")
    title = request.args.get("title", "")
    uploader = request.args.get("uploader", "")
    limit = int(request.args.get("limit", "20"))
    if not vid:
        return jsonify({"error": "ID kosong"}), 400
    try:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        keywords = make_keywords(title, uploader, vid)
        if not keywords:
            keywords = [title[:50]] if title else ["trending music"]

        seen_ids = {vid}
        all_results = []

        ydl_opts = {"quiet": True, "no_warnings": True, "extract_flat": True}

        def search_one(kw):
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(f"ytsearch{limit}:{kw}", download=False)
                return info.get("entries") or []
            except:
                return []

        # Jalankan semua keyword secara paralel
        with ThreadPoolExecutor(max_workers=4) as ex:
            futures = {ex.submit(search_one, kw): kw for kw in keywords}
            batches = [f.result() for f in as_completed(futures)]

        # Gabung semua hasil, dedupe by ID
        for batch in batches:
            for entry in batch:
                if not entry:
                    continue
                eid = entry.get("id")
                if not eid or eid in seen_ids:
                    continue
                seen_ids.add(eid)
                all_results.append({
                    "id": eid,
                    "title": entry.get("title") or "",
                    "uploader": entry.get("uploader") or entry.get("channel") or "",
                    "duration": entry.get("duration"),
                    "thumbnail": "https://img.youtube.com/vi/" + eid + "/mqdefault.jpg",
                    "view_count": entry.get("view_count"),
                })

        # Acak sedikit biar tidak selalu urutan yang sama
        random.shuffle(all_results)
        return jsonify({"results": all_results[:limit * 2]})
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
            fmt = "bestaudio[ext=m4a]/bestaudio/best"; ext = "m4a"
        else:
            fmt_map = {
                "360": "best[height<=360][ext=mp4]/bestvideo[height<=360]+bestaudio/best[height<=360]",
                "480": "best[height<=480][ext=mp4]/bestvideo[height<=480]+bestaudio/best[height<=480]",
                "720": "best[height<=720][ext=mp4]/bestvideo[height<=720]+bestaudio/best[height<=720]",
            }
            fmt = fmt_map.get(quality, fmt_map["720"]); ext = "mp4"

        ydl_opts = {"quiet": True, "no_warnings": True, "format": fmt}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        dl_url = info.get("url")
        dl_ext = info.get("ext", ext)
        title = info.get("title", "video")

        if not dl_url:
            for f in reversed(info.get("formats", [])):
                if mode == "audio":
                    if f.get("acodec") != "none" and f.get("vcodec") == "none":
                        dl_url = f.get("url"); dl_ext = f.get("ext","m4a"); break
                else:
                    h = f.get("height",0) or 0
                    if f.get("vcodec","none")!="none" and f.get("acodec","none")!="none" and h<=int(quality):
                        dl_url = f.get("url"); dl_ext = f.get("ext","mp4"); break

        if not dl_url:
            return jsonify({"error": "URL tidak ditemukan"}), 404

        safe = "".join(c for c in title if c.isalnum() or c in " -_")[:60]
        filename = safe + "." + dl_ext

        def gen():
            with requests.get(dl_url, headers=HEADERS, stream=True, timeout=60) as r:
                r.raise_for_status()
                for chunk in r.iter_content(chunk_size=1024*512): yield chunk

        return Response(gen(), headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "video/mp4" if mode=="video" else "audio/m4a",
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
