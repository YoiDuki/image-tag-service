import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "tags.db")

_COLS = "id, filename, filepath, tags, artists, characters, media_type, style, nsfw, status, error, palette, author_username, posted_at, created_at, updated_at, tags_edited, clip_scores, clip_tags"


def _expand_synonym_tag_clauses(term):
    """Return (tag_clauses, params) — extra tag LIKE clauses expanding Chinese canonical to English synonyms."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT canonical FROM tag_synonyms WHERE canonical LIKE ?",
        (f"%{term}%",)
    ).fetchall()
    conn.close()
    if not rows:
        return [], []
    tag_clauses = []
    params = []
    for r in rows:
        c = r["canonical"]
        conn2 = get_conn()
        syns = conn2.execute(
            "SELECT synonym FROM tag_synonyms WHERE canonical = ?", (c,)
        ).fetchall()
        conn2.close()
        for s in syns:
            tag_clauses.append("tags LIKE ?")
            params.append(f'%"' + s["synonym"] + '"%')
    return tag_clauses, params


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
        "clip_scores",
        "clip_tags",
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
    clip_scores=None,
    clip_tags=None,
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
               status=?, error=?, updated_at=?, clip_scores=?, clip_tags=? WHERE filename=?""",
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
                json.dumps(clip_scores or []),
                json.dumps(clip_tags or {}),
                filename,
            ),
        )
    else:
        conn.execute(
            """INSERT INTO images
               (filename, filepath, tags, media_type, style, nsfw, palette, artists, characters, author_username, posted_at, status, error, created_at, updated_at, clip_scores, clip_tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                json.dumps(clip_scores or []),
                json.dumps(clip_tags or {}),
            ),
        )
    conn.commit()
    conn.close()


def _build_tag_clause(tag_value, conn):
    """Build tag filter for a single tag value. Returns (clause_string, params_list)."""
    if tag_value == "__no_tag__":
        return ("(tags IS NULL OR tags = '[]')", [])
    tag_clauses = ["tags LIKE ?"]
    tag_params = [f'%"{tag_value}"%']
    rows = conn.execute(
        "SELECT synonym FROM tag_synonyms WHERE canonical = ? OR synonym = ?",
        (tag_value, tag_value),
    ).fetchall()
    if rows:
        alt_names = {r["synonym"] for r in rows}
        for alt_tag in alt_names:
            tag_clauses.append("tags LIKE ?")
            tag_params.append(f'%"{alt_tag}"%')
    return (f"({' OR '.join(tag_clauses)})", tag_params)


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
        for tv in tag.split(","):
            tv = tv.strip()
            if tv:
                clause, tag_params = _build_tag_clause(tv, conn)
                if clause:
                    clauses.append(clause)
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
            base_clause = "(filename LIKE ? OR artists LIKE ? OR characters LIKE ? OR author_username LIKE ? OR style LIKE ? OR media_type LIKE ? OR tags LIKE ?)"
            base_params = [like, like, like, like, like, like, like]
            syn_clauses, syn_params = _expand_synonym_tag_clauses(term)
            if syn_clauses:
                full_clause = base_clause[:-1] + " OR " + " OR ".join(syn_clauses) + ")"
                search_clauses.append(full_clause)
                params.extend(base_params + syn_params)
            else:
                search_clauses.append(base_clause)
                params.extend(base_params)
        clauses.append(f"({' AND '.join(search_clauses)})")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    order_map = {"posted_at": "posted_at DESC", "updated_at": "updated_at DESC"}
    order_by = order_map.get(sort, "updated_at DESC")
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
    synonym_map = get_synonym_map()
    for r in rows:
        d = dict(r)
        d["tags"] = json.loads(d["tags"]) if isinstance(d["tags"], str) else d["tags"]
        d["displayed_tags"] = [synonym_map.get(t, t) for t in (d["tags"] or [])]
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
        d["clip_scores"] = (
            json.loads(d["clip_scores"])
            if isinstance(d.get("clip_scores"), str)
            else d.get("clip_scores", [])
        )
        d["clip_tags"] = (
            json.loads(d["clip_tags"])
            if isinstance(d.get("clip_tags"), str)
            else d.get("clip_tags", {})
        )
        result.append(d)
    return {
        "images": result,
        "page": page,
        "per_page": per_page,
        "total": total,
        "total_pages": total_pages,
    }


def set_images_pending(
    status=None,
    author=None,
    media_type=None,
    style=None,
    tag=None,
    nsfw=None,
    search=None,
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
    if tag == "__no_tag__":
        clauses.append("(tags IS NULL OR tags = '[]')")
        tag = None
    if tag:
        for tv in tag.split(","):
            tv = tv.strip()
            if tv:
                clause, tag_params = _build_tag_clause(tv, conn)
                if clause:
                    clauses.append(clause)
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
            base_clause = "(filename LIKE ? OR artists LIKE ? OR characters LIKE ? OR author_username LIKE ? OR style LIKE ? OR media_type LIKE ? OR tags LIKE ?)"
            base_params = [like, like, like, like, like, like, like]
            syn_clauses, syn_params = _expand_synonym_tag_clauses(term)
            if syn_clauses:
                full_clause = base_clause[:-1] + " OR " + " OR ".join(syn_clauses) + ")"
                search_clauses.append(full_clause)
                params.extend(base_params + syn_params)
            else:
                search_clauses.append(base_clause)
                params.extend(base_params)
        clauses.append(f"({' AND '.join(search_clauses)})")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    cur = conn.execute(f"UPDATE images SET status = 'pending', updated_at = datetime('now','localtime') {where}", params)
    affected = cur.rowcount
    conn.commit()
    conn.close()
    return {"affected": affected}


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


def _build_filter_where(exclude=None, **kwargs):
    """Build WHERE clause and params from filter kwargs, optionally excluding one key."""
    conn = get_conn()
    clauses = []
    params = []
    for key, val in kwargs.items():
        if not val or key == exclude:
            continue
        if key == "author":
            clauses.append("author_username = ?")
            params.append(val)
        elif key == "media_type":
            clauses.append("media_type = ?")
            params.append(val)
        elif key == "style":
            clauses.append("style = ?")
            params.append(val)
        elif key == "tag":
            if val == "__no_tag__":
                clauses.append("(tags IS NULL OR tags = '[]')")
            else:
                for tv in val.split(","):
                    tv = tv.strip()
                    if tv:
                        clause, tag_params = _build_tag_clause(tv, conn)
                        if clause:
                            clauses.append(clause)
                            params.extend(tag_params)
        elif key == "nsfw":
            if val == "yes":
                clauses.append("nsfw = 'yes'")
            elif val == "no":
                clauses.append("(nsfw IS NULL OR nsfw = '' OR nsfw = 'no')")
        elif key == "search":
            terms = [t for t in val.split() if t]
            if terms:
                search_clauses = []
                for term in terms:
                    like = f"%{term}%"
                    base_clause = "(filename LIKE ? OR artists LIKE ? OR characters LIKE ? OR author_username LIKE ? OR style LIKE ? OR media_type LIKE ? OR tags LIKE ?)"
                    base_params = [like, like, like, like, like, like, like]
                    syn_clauses, syn_params = _expand_synonym_tag_clauses(term)
                    if syn_clauses:
                        full_clause = base_clause[:-1] + " OR " + " OR ".join(syn_clauses) + ")"
                        search_clauses.append(full_clause)
                        params.extend(base_params + syn_params)
                    else:
                        search_clauses.append(base_clause)
                        params.extend(base_params)
                clauses.append(f"({' AND '.join(search_clauses)})")
    conn.close()
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def get_filters(author=None, media_type=None, style=None, tag=None, nsfw=None, search=None):
    conn = get_conn()
    syn_rows = conn.execute("SELECT synonym, canonical FROM tag_synonyms").fetchall()
    conn.close()
    synonym_map = {r["synonym"]: r["canonical"] for r in syn_rows}

    def _get_counts(group_col, exclude_key):
        where, params = _build_filter_where(
            exclude=exclude_key,
            author=author, media_type=media_type, style=style,
            tag=tag, nsfw=nsfw, search=search,
        )
        conn2 = get_conn()
        if group_col == "tags":
            rows2 = conn2.execute(
                f"SELECT tags FROM images {where}", params
            ).fetchall()
            counts = {}
            for r in rows2:
                if r["tags"]:
                    try:
                        lst = json.loads(r["tags"])
                        if isinstance(lst, list):
                            for t in lst:
                                if isinstance(t, str):
                                    c = synonym_map.get(t, t)
                                    counts[c] = counts.get(c, 0) + 1
                    except (json.JSONDecodeError, TypeError):
                        pass
        else:
            rows2 = conn2.execute(
                f"SELECT {group_col}, COUNT(*) as c FROM images {where} GROUP BY {group_col}", params
            ).fetchall()
            counts = {r[group_col]: r["c"] for r in rows2 if r[group_col] and r[group_col] != "unknown"}
        conn2.close()
        return sorted(
            [{"name": n, "count": c} for n, c in counts.items()],
            key=lambda x: (-x["count"], x["name"]),
        )

    authors = _get_counts("author_username", "author")
    media_types = _get_counts("media_type", "media_type")
    styles = _get_counts("style", "style")
    tags = _get_counts("tags", "tag")
    return {
        "authors": authors,
        "media_types": media_types,
        "styles": styles,
        "tags": tags,
        "synonym_map": synonym_map,
    }


def _load_wd_tags():
    import csv
    path = None
    for root, dirs, files in os.walk(os.path.join(os.path.dirname(__file__), "..", "models")):
        for f in files:
            if f == "selected_tags.csv":
                path = os.path.join(root, f)
                break
        if path:
            break
    if not path:
        return set()
    with open(path, "r", encoding="utf-8") as f:
        return {row["name"] for row in csv.DictReader(f)}


def generate_tag_descriptions(top_n=10):
    wd_tags = _load_wd_tags()
    print(f"[tag_desc] Loaded {len(wd_tags)} WD labels")

    conn = get_conn()
    rows = conn.execute(
        "SELECT filepath, tags FROM images WHERE tags_edited = 1"
    ).fetchall()
    conn.close()

    custom_tags = {}
    total = 0
    for r in rows:
        try:
            lst = json.loads(r["tags"])
            if not isinstance(lst, list):
                continue
        except (json.JSONDecodeError, TypeError):
            continue
        custom = [t for t in lst if isinstance(t, str) and t.strip() and t not in wd_tags]
        if not custom:
            continue
        wd = [t for t in lst if isinstance(t, str) and t in wd_tags]
        total += 1
        for t in custom:
            if t not in custom_tags:
                custom_tags[t] = {"paths": set(), "wd_cooccur": {}}
            custom_tags[t]["paths"].add(r["filepath"])
            for w in wd:
                custom_tags[t]["wd_cooccur"][w] = custom_tags[t]["wd_cooccur"].get(w, 0) + 1

    print(f"[tag_desc] Found {total} edited images with custom tags, {len(custom_tags)} custom tags")

    _CHAR_KEYWORDS = {
        "skin", "hair", "eyes", "tits", "breast", "ear", "tail", "face", "hand",
        "head", "nose", "mouth", "foot", "feet", "leg", "arm", "body", "chest",
        "belly", "neck", "shoulder", "hip", "thigh", "knee", "elbow", "wing",
        "horn", "fang", "claw", "blush", "smile", "tongue", "tear", "sweat",
        "scar", "tattoo", "piercing", "wound", "cut", "bruise", "blood",
        "outfit", "dress", "skirt", "shirt", "jacket", "coat", "hat", "crown",
        "ribbon", "sock", "shoe", "boot", "glove", "scarf", "necklace",
        "collar", "belt", "mask", "cape", "hood", "veil", "armor", "robe",
        "kimono", "uniform", "suit", "apron", "stocking", "thighhigh", "heel",
    }
    _SCENE_KEYWORDS = {
        "sky", "water", "wave", "beach", "mountain", "forest", "field",
        "river", "lake", "sea", "ocean", "cloud", "sunset", "sunrise",
        "dawn", "dusk", "night", "moon", "star", "snow", "rain",
        "rainbow", "storm", "flower", "grass", "tree", "leaf", "petal",
        "cherry", "blossom", "garden", "park", "building", "house",
        "room", "window", "door", "floor", "wall", "bed", "table",
        "chair", "desk", "street", "road", "city", "town", "village",
        "castle", "bridge", "tower", "gate", "fence", "path",
        "lamp", "shadow", "stair", "step", "rail", "train", "car",
    }
    _STYLE_KEYWORDS = {
        "sketch", "drawing", "painting", "watercolor", "render",
        "fanart", "doujin", "concept", "portrait", "landscape",
        "chibi", "realistic", "semi", "anime", "cartoon", "ink",
        "lineart", "digital", "traditional", "oil", "acrylic",
    }

    def _make_description(tag_name, top_wd):
        tag_nat = tag_name.replace("_", " ")
        words = set(tag_nat.lower().split())
        # pick top co-occurring WD tags
        wd_nat = [w.replace("_", " ").replace("-", " ") for w, _ in top_wd[:4]]
        wd_part = ", ".join(wd_nat)

        if words & _CHAR_KEYWORDS:
            base = f"a character with {tag_nat}"
        elif words & _SCENE_KEYWORDS:
            base = f"a scene with {tag_nat}"
        elif words & _STYLE_KEYWORDS:
            base = f"a {tag_nat} artwork"
        else:
            base = f"an image featuring {tag_nat}"

        if wd_part:
            return f"{base}, {wd_part}"
        return base

    updated = 0
    conn = get_conn()
    for tag_name, data in custom_tags.items():
        paths = list(data["paths"])
        wd_scores = {w: c for w, c in data["wd_cooccur"].items()}
        top_wd = sorted(wd_scores.items(), key=lambda x: -x[1])[:top_n]

        desc = _make_description(tag_name, top_wd)
        if not desc:
            continue
        conn.execute(
            "INSERT INTO tag_meta (name, description) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET description = ?",
            (tag_name, desc, desc),
        )
        updated += 1
        print(f"[tag_desc]  {tag_name} → {desc}")
    conn.commit()
    conn.close()

    print(f"[tag_desc] Updated {updated} tag_meta descriptions")
    return updated


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
    d["clip_scores"] = (
        json.loads(d["clip_scores"])
        if isinstance(d.get("clip_scores"), str)
        else d.get("clip_scores", [])
    )
    d["clip_tags"] = (
        json.loads(d["clip_tags"])
        if isinstance(d.get("clip_tags"), str)
        else d.get("clip_tags", {})
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
