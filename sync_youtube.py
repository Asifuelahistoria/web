#!/usr/bin/env python3
"""Descarga la lista de videos del canal con la YouTube Data API v3.

Requiere la variable de entorno YOUTUBE_API_KEY. Escribe data/videos.json.
Si la clave no existe o falla la API, deja el archivo como estaba.
"""
import json
import re
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
API = "https://www.googleapis.com/youtube/v3/"


def get(endpoint, **params):
    params["key"] = os.environ["YOUTUBE_API_KEY"]
    with urllib.request.urlopen(API + endpoint + "?" + urllib.parse.urlencode(params), timeout=30) as r:
        return json.load(r)


def main():
    if not os.environ.get("YOUTUBE_API_KEY"):
        print("Sin YOUTUBE_API_KEY: se mantiene data/videos.json")
        return
    cfg = yaml.safe_load((ROOT / "site.yaml").read_text(encoding="utf-8"))
    canal = get("channels", part="contentDetails", id=cfg["youtube_canal_id"])
    uploads = canal["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, token = [], None
    while True:
        params = dict(part="contentDetails", playlistId=uploads, maxResults=50)
        if token:
            params["pageToken"] = token
        page = get("playlistItems", **params)
        ids += [i["contentDetails"]["videoId"] for i in page["items"]]
        token = page.get("nextPageToken")
        if not token:
            break
    videos = []
    for i in range(0, len(ids), 50):
        data = get("videos", part="snippet,contentDetails,status", id=",".join(ids[i:i + 50]))
        for v in data["items"]:
            if v["status"].get("privacyStatus") != "public":
                continue
            s = v["snippet"]
            m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", v["contentDetails"]["duration"])
            seg = sum(int(x or 0) * k for x, k in zip(m.groups(), (3600, 60, 1))) if m else 0
            if seg < 180 or "#short" in s["title"].lower():
                continue  # se excluyen los Shorts
            videos.append({
                "id": v["id"],
                "titulo": s["title"],
                "publicado": s["publishedAt"],
                "descripcion": s.get("description", "")[:600],
                "segundos": seg,
            })
    videos.sort(key=lambda v: v["publicado"], reverse=True)
    out = ROOT / "data" / "videos.json"
    out.write_text(json.dumps(videos, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(videos)} videos guardados en {out}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # no romper el despliegue por un fallo de la API
        print("Aviso: no se pudo sincronizar YouTube:", exc, file=sys.stderr)
