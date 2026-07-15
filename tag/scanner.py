import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from .database import image_exists, upsert_image, get_unprocessed, get_conn
from .classifier import classify_image
from .likes_loader import lookup as _likes_lookup

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".avif"}

_print_lock = threading.Lock()

_cpu_count = (
    len(os.sched_getaffinity(0))
    if hasattr(os, "sched_getaffinity")
    else os.cpu_count() or 4
)
_cpu_counter = 0
_cpu_counter_lock = threading.Lock()


def _worker_init():
    global _cpu_counter
    if not hasattr(os, "sched_setaffinity"):
        return
    with _cpu_counter_lock:
        cpu = _cpu_counter % _cpu_count
        _cpu_counter += 1
    os.sched_setaffinity(0, [cpu])


def _print(*args, **kwargs):
    with _print_lock:
        print(*args, **kwargs)


def scan_directory(directory):
    directory = os.path.abspath(directory)
    if not os.path.isdir(directory):
        _print(f"[scanner] Directory not found: {directory}")
        return []
    files = []
    for fname in os.listdir(directory):
        ext = os.path.splitext(fname)[1].lower()
        if ext in IMAGE_EXTENSIONS:
            fpath = os.path.join(directory, fname)
            if os.path.isfile(fpath):
                files.append((fname, fpath))
    return files


def process_new_files(directory, limit=0):
    files = scan_directory(directory)
    if limit > 0:
        files = files[:limit]
    new_count = 0
    for fname, fpath in files:
        if not image_exists(fname):
            info = _likes_lookup(fname)
            upsert_image(
                fname,
                fpath,
                status="pending",
                author_username=info.get("author_username", ""),
                posted_at=info.get("posted_at", ""),
            )
            new_count += 1
    _print(f"[scanner] Found {len(files)} images, {new_count} new")
    return new_count


def _process_one(item):
    fpath = item["filepath"]
    fname = item["filename"]
    info = _likes_lookup(fname)
    author_username = info.get("author_username", "")
    posted_at = info.get("posted_at", "")
    if not os.path.isfile(fpath):
        upsert_image(
            fname,
            fpath,
            status="error",
            error="file not found",
            author_username=author_username,
            posted_at=posted_at,
        )
        return
    try:
        _print(f"[scanner]  {fname}")
        conn = get_conn()
        row = conn.execute("SELECT palette FROM images WHERE filename = ?", (fname,)).fetchone()
        conn.close()
        existing_palette = None
        if row and row["palette"]:
            import json
            try:
                p = json.loads(row["palette"])
                if isinstance(p, list) and len(p) > 0:
                    existing_palette = p
            except (json.JSONDecodeError, TypeError):
                pass
        result = classify_image(fpath, existing_palette=existing_palette)
        upsert_image(
            fname,
            fpath,
            tags=result["tags"],
            media_type=result["media_type"],
            style=result["style"],
            nsfw=result["nsfw"],
            palette=result["palette"],
            artists=result["artists"],
            characters=result["characters"],
            author_username=author_username,
            posted_at=posted_at,
            status="done",
            clip_scores=result.get("clip_scores"),
            clip_tags=result.get("clip_tags"),
        )
    except Exception as e:
        _print(f"[scanner]  ERROR: {fname} - {e}")
        upsert_image(
            fname,
            fpath,
            status="error",
            error=str(e),
            author_username=author_username,
            posted_at=posted_at,
        )


def process_pending(max_workers=None, force=False):
    if max_workers is None:
        try:
            import torch
            if torch.cuda.is_available():
                max_workers = min(3, _cpu_count)
            else:
                max_workers = _cpu_count
        except ImportError:
            max_workers = _cpu_count
    pending = get_unprocessed(force=force)
    if not pending:
        return
    label = "all" if force else "pending"
    _print(f"[scanner] Processing {len(pending)} {label} images with {max_workers} workers...")
    with ThreadPoolExecutor(
        max_workers=max_workers, initializer=_worker_init
    ) as executor:
        futures = [executor.submit(_process_one, item) for item in pending]
        for f in as_completed(futures):
            f.result()
    _print("[scanner] All pending images processed")
