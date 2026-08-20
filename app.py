#!/usr/bin/env python3
"""
app.py — local web server for youtube_transcript.py

Run:
    pip install -r requirements.txt
    python app.py

Then open http://127.0.0.1:5000 in your browser.
"""

from flask import Flask, request, jsonify, send_from_directory
from youtube_transcript_api import TranscriptsDisabled, NoTranscriptFound, VideoUnavailable

from transcript_core import (
    extract_video_id,
    build_api,
    fetch_transcript,
    render,
    list_channel_videos,
)

app = Flask(__name__, static_folder="static", static_url_path="")


@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/api/video", methods=["POST"])
def api_video():
    data = request.get_json(force=True, silent=True) or {}
    raw_url = (data.get("url") or "").strip()
    if not raw_url:
        return jsonify(error="Укажи ссылку на видео или ID."), 400

    try:
        video_id = extract_video_id(raw_url)
    except ValueError as e:
        return jsonify(error=str(e)), 400

    languages = [l.strip() for l in (data.get("lang") or "en").split(",") if l.strip()]
    proxy = (data.get("proxy") or "").strip() or None
    fmt = data.get("format") or "txt"

    api = build_api(proxy)

    try:
        entries = fetch_transcript(video_id, languages, api)
    except TranscriptsDisabled:
        return jsonify(error=f"Субтитры отключены для видео {video_id}."), 404
    except VideoUnavailable:
        return jsonify(error=f"Видео {video_id} недоступно."), 404
    except NoTranscriptFound:
        return jsonify(error=f"Транскрипт не найден для {video_id} в языках {languages}."), 404
    except Exception as e:
        return jsonify(error=f"Ошибка: {e}"), 500

    return jsonify(video_id=video_id, format=fmt, output=render(entries, fmt))


@app.route("/api/channel", methods=["POST"])
def api_channel():
    data = request.get_json(force=True, silent=True) or {}
    channel_url = (data.get("url") or "").strip()
    if not channel_url:
        return jsonify(error="Укажи ссылку на канал."), 400

    languages = [l.strip() for l in (data.get("lang") or "en").split(",") if l.strip()]
    proxy = (data.get("proxy") or "").strip() or None
    fmt = data.get("format") or "plain"
    limit_raw = data.get("limit")
    limit = int(limit_raw) if limit_raw else None

    try:
        videos = list_channel_videos(channel_url, limit, proxy)
    except Exception as e:
        return jsonify(error=f"Не удалось получить список видео канала: {e}"), 500

    api = build_api(proxy)
    results = []
    for v in videos:
        try:
            entries = fetch_transcript(v["id"], languages, api)
            results.append({
                "id": v["id"],
                "title": v["title"],
                "ok": True,
                "output": render(entries, fmt),
            })
        except (TranscriptsDisabled, VideoUnavailable, NoTranscriptFound) as e:
            results.append({
                "id": v["id"],
                "title": v["title"],
                "ok": False,
                "error": str(e),
            })

    return jsonify(results=results, total=len(videos))


if __name__ == "__main__":
    app.run(debug=True, port=5000)
