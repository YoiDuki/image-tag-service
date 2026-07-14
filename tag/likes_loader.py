import json
import os

_LIKES_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "likes.jsonl")
_cache = None


def _media_id(url):
    stem = url.rstrip("/").split("/")[-1].split("?")[0]
    stem = stem.rsplit(".", 1)[0] if "." in stem else stem
    return stem


def load_likes_map(jsonl_path=None):
    global _cache
    if _cache is not None:
        return _cache
    path = jsonl_path or _LIKES_PATH
    _cache = {}
    if not os.path.isfile(path):
        return _cache
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            author = obj.get("author_username", "")
            created_at = obj.get("created_at", "")
            media_list = obj.get("attachments", {}).get("media", [])
            for m in media_list:
                if m.get("type") != "photo":
                    continue
                url = m.get("url", "")
                if not url:
                    continue
                mid = _media_id(url)
                if mid not in _cache:
                    _cache[mid] = {
                        "author_username": author,
                        "posted_at": created_at,
                    }
    return _cache


def lookup(filename):
    maps = load_likes_map()
    mid = filename.rsplit(".", 1)[0]
    return maps.get(mid, {"author_username": "", "posted_at": ""})
