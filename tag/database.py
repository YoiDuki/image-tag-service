import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "tags.db")

_COLS = "id, filename, filepath, tags, artists, characters, media_type, style, nsfw, status, error, palette, author_username, posted_at, created_at, updated_at, tags_edited"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT UNIQUE NOT NULL,
            filepath TEXT NOT NULL,
            tags TEXT DEFAULT '[]',
            artists TEXT DEFAULT '[]',
            characters TEXT DEFAULT '[]',
            media_type TEXT DEFAULT 'unknown',
            style TEXT,
            nsfw TEXT DEFAULT 'no',
            status TEXT DEFAULT 'pending',
            error TEXT,
            palette TEXT DEFAULT '[]',
            author_username TEXT DEFAULT '',
            posted_at TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
    """)
    for col in [
        "media_type",
        "style",
        "nsfw",
        "palette",
        "artists",
        "characters",
        "author_username",
        "posted_at",
        "tags_edited",
    ]:
        try:
            conn.execute(f"ALTER TABLE images ADD COLUMN {col} TEXT")
        except sqlite3.OperationalError:
            pass
    conn.commit()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tag_meta (
            name TEXT PRIMARY KEY,
            description TEXT DEFAULT ''
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tag_synonyms (
            synonym TEXT PRIMARY KEY,
            canonical TEXT NOT NULL
        )
    """)
    if conn.execute("SELECT COUNT(*) as c FROM tag_meta").fetchone()["c"] == 0:
        defaults = [
            ("cosplay", "cosplay, someone dressed in costume, costume play, cosplayer"),
            ("big_tits", "a person with big breasts, large chest, huge bust, big tits"),
            ("seifuku", "seifuku, school uniform, japanese sailor uniform, sailor fuku"),
            ("JK", "a japanese high school girl, female student wearing school uniform, JK"),
        ]
        conn.executemany(
            "INSERT INTO tag_meta (name, description) VALUES (?, ?)", defaults
        )
    conn.commit()
    conn.close()


def get_tag_meta(search=None):
    conn = get_conn()
    if search:
        rows = conn.execute(
            "SELECT name, description FROM tag_meta WHERE name LIKE ? ORDER BY name",
            (f"%{search}%",),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT name, description FROM tag_meta ORDER BY name"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_tag_meta_prompts():
    conn = get_conn()
    rows = conn.execute(
        "SELECT name, description FROM tag_meta WHERE description != '' ORDER BY name"
    ).fetchall()
    conn.close()
    return {r["name"]: r["description"] for r in rows}


def upsert_tag_meta(name, description):
    conn = get_conn()
    conn.execute(
        "INSERT INTO tag_meta (name, description) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET description = ?",
        (name, description, description),
    )
    conn.commit()
    conn.close()


def delete_tag_meta(name):
    conn = get_conn()
    conn.execute("DELETE FROM tag_meta WHERE name = ?", (name,))
    conn.commit()
    conn.close()


def get_tag_synonyms(search=None):
    conn = get_conn()
    if search:
        rows = conn.execute(
            "SELECT synonym, canonical FROM tag_synonyms WHERE synonym LIKE ? OR canonical LIKE ? ORDER BY canonical, synonym",
            (f"%{search}%", f"%{search}%"),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT synonym, canonical FROM tag_synonyms ORDER BY canonical, synonym"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_tag_synonym(synonym, canonical):
    conn = get_conn()
    conn.execute(
        "INSERT OR IGNORE INTO tag_synonyms (synonym, canonical) VALUES (?, ?)",
        (synonym, canonical),
    )
    conn.commit()
    conn.close()


def delete_tag_synonym(synonym):
    conn = get_conn()
    conn.execute("DELETE FROM tag_synonyms WHERE synonym = ?", (synonym,))
    conn.commit()
    conn.close()


def get_synonym_map():
    conn = get_conn()
    rows = conn.execute("SELECT synonym, canonical FROM tag_synonyms").fetchall()
    conn.close()
    result = {}
    for r in rows:
        result[r["synonym"]] = r["canonical"]
    return result


def upsert_image(
    filename,
    filepath,
    tags=None,
    media_type="unknown",
    style=None,
    nsfw=False,
    palette=None,
    artists=None,
    characters=None,
    author_username="",
    posted_at="",
    status="pending",
    error=None,
):
    conn = get_conn()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    existing = conn.execute(
        "SELECT id FROM images WHERE filename = ?", (filename,)
    ).fetchone()

    if existing:
        conn.execute(
            """UPDATE images SET filepath=?, tags=?, media_type=?, style=?,
               nsfw=?, palette=?,
               artists=?, characters=?, author_username=?, posted_at=?,
               status=?, error=?, updated_at=? WHERE filename=?""",
            (
                filepath,
                json.dumps(tags or []),
                media_type,
                style,
                "yes" if nsfw else "no",
                json.dumps(palette or []),
                json.dumps(artists or []),
                json.dumps(characters or []),
                author_username,
                posted_at,
                status,
                error,
                now,
                filename,
            ),
        )
    else:
        conn.execute(
            """INSERT INTO images
               (filename, filepath, tags, media_type, style, nsfw, palette, artists, characters, author_username, posted_at, status, error, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                filename,
                filepath,
                json.dumps(tags or []),
                media_type,
                style,
                "yes" if nsfw else "no",
                json.dumps(palette or []),
                json.dumps(artists or []),
                json.dumps(characters or []),
                author_username,
                posted_at,
                status,
                error,
                now,
                now,
            ),
        )
    conn.commit()
    conn.close()


def get_all_images(
    status=None,
    author=None,
    media_type=None,
    style=None,
    tag=None,
    nsfw=None,
    search=None,
    sort="updated_at",
    page=1,
    per_page=24,
):
    conn = get_conn()
    clauses = []
    params = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if author:
        clauses.append("author_username = ?")
        params.append(author)
    if media_type:
        clauses.append("media_type = ?")
        params.append(media_type)
    if style:
        clauses.append("style = ?")
        params.append(style)
    if tag == '__no_tag__':
        clauses.append("(tags IS NULL OR tags = '[]')")
        tag = None
    if tag:
        tag_clauses = ["tags LIKE ?"]
        tag_params = [f'%"{tag}"%']
        rows = conn.execute(
            "SELECT synonym FROM tag_synonyms WHERE canonical = ? OR synonym = ?",
            (tag, tag),
        ).fetchall()
        if rows:
            alt_names = {r["synonym"] for r in rows}
            alt_names.add(tag)
            alt_names.discard(tag)
            for alt_tag in alt_names:
                if conn.execute("SELECT 1 FROM tag_synonyms WHERE synonym = ?", (alt_tag,)).fetchone():
                    pass
                tag_clauses.append("tags LIKE ?")
                tag_params.append(f'%"{alt_tag}"%')
        clauses.append(f"({' OR '.join(tag_clauses)})")
        params.extend(tag_params)
    if nsfw:
        if nsfw == "yes":
            clauses.append("nsfw = 'yes'")
        elif nsfw == "no":
            clauses.append("(nsfw IS NULL OR nsfw = '' OR nsfw = 'no')")
    if search:
        terms = [t for t in search.split() if t]
        search_clauses = []
        for term in terms:
            like = f"%{term}%"
            search_clauses.append(
                "(filename LIKE ? OR artists LIKE ? OR characters LIKE ? OR author_username LIKE ? OR style LIKE ? OR media_type LIKE ? OR tags LIKE ?)"
            )
            params.extend([like, like, like, like, like, like, like])
        clauses.append(f"({' AND '.join(search_clauses)})")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    order_map = {"posted_at": "posted_at DESC", "updated_at": "updated_at DESC"}
    order_by = order_map.get(sort, "updated_at DESC")

    # Total count for pagination
    count_row = conn.execute(
        f"SELECT COUNT(*) as c FROM images {where}", params
    ).fetchone()
    total = count_row["c"] if count_row else 0
    total_pages = max(1, (total + per_page - 1) // per_page) if per_page > 0 else 1

    if per_page > 0:
        offset = (page - 1) * per_page
        rows = conn.execute(
            f"SELECT {_COLS} FROM images {where} ORDER BY {order_by} LIMIT ? OFFSET ?",
            params + [per_page, offset],
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT {_COLS} FROM images {where} ORDER BY {order_by}", params
        ).fetchall()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        d["tags"] = json.loads(d["tags"]) if isinstance(d["tags"], str) else d["tags"]
        d["palette"] = (
            json.loads(d["palette"])
            if isinstance(d["palette"], str)
            else d.get("palette", [])
        )
        d["artists"] = (
            json.loads(d["artists"])
            if isinstance(d.get("artists"), str)
            else d.get("artists", [])
        )
        d["characters"] = (
            json.loads(d["characters"])
            if isinstance(d.get("characters"), str)
            else d.get("characters", [])
        )
        result.append(d)
    return {
        "images": result,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
    }


def get_unprocessed(force=False):
    conn = get_conn()
    if force:
        rows = conn.execute(
            f"SELECT {_COLS} FROM images ORDER BY created_at ASC"
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT {_COLS} FROM images WHERE status = 'pending' ORDER BY created_at ASC"
        ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["tags"] = json.loads(d["tags"]) if isinstance(d["tags"], str) else d["tags"]
        d["palette"] = (
            json.loads(d["palette"])
            if isinstance(d["palette"], str)
            else d.get("palette", [])
        )
        d["artists"] = (
            json.loads(d["artists"])
            if isinstance(d.get("artists"), str)
            else d.get("artists", [])
        )
        d["characters"] = (
            json.loads(d["characters"])
            if isinstance(d.get("characters"), str)
            else d.get("characters", [])
        )
        result.append(d)
    return result


def image_exists(filename):
    conn = get_conn()
    row = conn.execute(
        "SELECT 1 FROM images WHERE filename = ?", (filename,)
    ).fetchone()
    conn.close()
    return row is not None


def get_filters():
    conn = get_conn()
    rows = conn.execute(
        "SELECT author_username, media_type, style, tags FROM images"
    ).fetchall()
    syn_rows = conn.execute("SELECT synonym, canonical FROM tag_synonyms").fetchall()
    conn.close()
    synonym_map = {r["synonym"]: r["canonical"] for r in syn_rows}
    author_counts = {}
    media_type_counts = {}
    style_counts = {}
    tag_counts = {}
    for r in rows:
        if r["author_username"]:
            name = r["author_username"]
            author_counts[name] = author_counts.get(name, 0) + 1
        if r["media_type"] and r["media_type"] != "unknown":
            media_type_counts[r["media_type"]] = media_type_counts.get(r["media_type"], 0) + 1
        if r["style"]:
            style_counts[r["style"]] = style_counts.get(r["style"], 0) + 1
        if r["tags"]:
            try:
                lst = json.loads(r["tags"])
                if isinstance(lst, list):
                    for t in lst:
                        if isinstance(t, str):
                            canonical = synonym_map.get(t, t)
                            tag_counts[canonical] = tag_counts.get(canonical, 0) + 1
            except (json.JSONDecodeError, TypeError):
                pass
    authors = sorted(
        [{"name": n, "count": c} for n, c in author_counts.items()],
        key=lambda a: (-a["count"], a["name"]),
    )
    media_types = sorted(
        [{"name": n, "count": c} for n, c in media_type_counts.items()],
        key=lambda m: (-m["count"], m["name"]),
    )
    styles = sorted(
        [{"name": n, "count": c} for n, c in style_counts.items()],
        key=lambda s: (-s["count"], s["name"]),
    )
    tags = sorted(
        [{"name": n, "count": c} for n, c in tag_counts.items()],
        key=lambda t: (-t["count"], t["name"]),
    )
    return {
        "authors": authors,
        "media_types": sorted(media_types),
        "styles": sorted(styles),
        "tags": tags,
        "synonym_map": synonym_map,
    }


def _parse_image_row(d):
    d["tags"] = json.loads(d["tags"]) if isinstance(d.get("tags"), str) else d.get("tags", [])
    d["palette"] = (
        json.loads(d["palette"])
        if isinstance(d.get("palette"), str)
        else d.get("palette", [])
    )
    d["artists"] = (
        json.loads(d["artists"])
        if isinstance(d.get("artists"), str)
        else d.get("artists", [])
    )
    d["characters"] = (
        json.loads(d["characters"])
        if isinstance(d.get("characters"), str)
        else d.get("characters", [])
    )
    return d


def search_by_color(r, g, b, threshold=100, page=1, per_page=24):
    conn = get_conn()
    rows = conn.execute(f"SELECT {_COLS} FROM images").fetchall()
    conn.close()
    target = (r, g, b)
    matches = []
    for row in rows:
        d = dict(row)
        raw_palette = d.get("palette", "[]")
        try:
            palette = (
                json.loads(raw_palette)
                if isinstance(raw_palette, str)
                else (raw_palette or [])
            )
        except (json.JSONDecodeError, TypeError):
            palette = []
        if not palette:
            continue
        best_dist = None
        best_hex = None
        best_pct = 0
        for c in palette:
            crgb = c.get("rgb")
            if not crgb or len(crgb) < 3:
                continue
            dr = target[0] - crgb[0]
            dg = target[1] - crgb[1]
            db = target[2] - crgb[2]
            dist = (dr * dr + dg * dg + db * db) ** 0.5
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_hex = c.get("hex")
                best_pct = c.get("percentage", 0) or 0
        if best_dist is not None and best_dist <= threshold:
            d = _parse_image_row(d)
            d["_color_distance"] = round(best_dist, 2)
            d["_matched_hex"] = best_hex
            d["_color_pct"] = round(best_pct, 4)
            matches.append((best_pct, best_dist, d))
    # sort by color proportion (desc), then distance (asc) as tiebreaker
    matches.sort(key=lambda x: (-x[0], x[1]))
    total = len(matches)
    total_pages = (total + per_page - 1) // per_page if per_page > 0 else 1
    if page < 1:
        page = 1
    start = (page - 1) * per_page
    page_items = [m[2] for m in matches[start : start + per_page]]
    return {
        "images": page_items,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
    }
