import os
import json
from fastapi import FastAPI, Query, HTTPException
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from starlette.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from tag.database import init_db, get_all_images, get_filters, search_by_color, upsert_image, image_exists, get_conn, get_tag_meta, upsert_tag_meta, delete_tag_meta, get_tag_synonyms, add_tag_synonym, delete_tag_synonym

init_db()

app = FastAPI(title="Image Tag Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DIST = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/images")
def list_images(
    status: str = Query(None),
    author: str = Query(None),
    media_type: str = Query(None),
    style: str = Query(None),
    tag: str = Query(None),
    nsfw: str = Query(None),
    search: str = Query(None),
    sort: str = Query("updated_at"),
    page: int = Query(1, ge=1),
    per_page: int = Query(24, ge=1, le=200),
):
    return get_all_images(
        status=status, author=author, media_type=media_type,
        style=style, tag=tag, nsfw=nsfw,
        search=search, sort=sort,
        page=page, per_page=per_page,
    )


@app.get("/api/filters")
def filters():
    return get_filters()


@app.get("/api/images/color")
def search_color_endpoint(
    r: int = Query(...),
    g: int = Query(...),
    b: int = Query(...),
    threshold: int = Query(100),
    page: int = Query(1, ge=1),
    per_page: int = Query(24, ge=1, le=200),
):
    return search_by_color(r, g, b, threshold, page, per_page)


@app.get("/api/images/{filename}/file")
def serve_image(filename: str):
    conn = get_conn()
    row = conn.execute(
        "SELECT filepath FROM images WHERE filename = ?", (filename,)
    ).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(404, "not found")
    fpath = row["filepath"]
    if not os.path.isfile(fpath):
        raise HTTPException(404, "file not found on disk")
    return FileResponse(fpath)


@app.get("/api/images/{filename}")
def get_image(filename: str):
    conn = get_conn()
    _COLS = "id, filename, filepath, tags, artists, characters, media_type, style, nsfw, status, error, palette, author_username, posted_at, created_at, updated_at, tags_edited"
    row = conn.execute(
        f"SELECT {_COLS} FROM images WHERE filename = ?", (filename,)
    ).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(404, "not found")
    d = dict(row)
    for field in ("tags", "palette", "artists", "characters"):
        if isinstance(d.get(field), str):
            d[field] = json.loads(d[field])
    return d


class ImageUpdate(BaseModel):
    tags: list | None = None
    artists: list | None = None
    characters: list | None = None
    media_type: str | None = None
    style: str | None = None
    nsfw: bool | None = None
    palette: list | None = None
    author_username: str | None = None
    posted_at: str | None = None
    status: str | None = None
    error: str | None = None
    filepath: str | None = None


@app.put("/api/images/{filename}")
def update_image_endpoint(filename: str, data: ImageUpdate):
    if not image_exists(filename):
        raise HTTPException(404, "not found")

    update_data = {k: v for k, v in data.model_dump(exclude_none=True).items() if v is not None}
    if not update_data:
        raise HTTPException(400, "no valid fields")

    set_clauses = []
    params = []
    for key, value in update_data.items():
        if key in ("tags", "artists", "characters", "palette"):
            value = json.dumps(value)
        elif key == "nsfw":
            value = "yes" if value else "no"
        set_clauses.append(f"{key} = ?")
        params.append(value)

    if "tags" in update_data:
        set_clauses.append("tags_edited = 1")
    set_clauses.append("updated_at = datetime('now','localtime')")
    params.append(filename)

    conn = get_conn()
    conn.execute(
        f"UPDATE images SET {', '.join(set_clauses)} WHERE filename = ?",
        params,
    )
    conn.commit()
    conn.close()
    return {"status": "updated"}


@app.delete("/api/images/{filename}")
def delete_image_endpoint(filename: str):
    conn = get_conn()
    conn.execute("DELETE FROM images WHERE filename = ?", (filename,))
    conn.commit()
    conn.close()
    return {"status": "deleted"}


@app.get("/api/stats")
def stats():
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) as c FROM images").fetchone()["c"]
    pending = conn.execute(
        "SELECT COUNT(*) as c FROM images WHERE status = 'pending'"
    ).fetchone()["c"]
    done = conn.execute(
        "SELECT COUNT(*) as c FROM images WHERE status = 'done'"
    ).fetchone()["c"]
    error = conn.execute(
        "SELECT COUNT(*) as c FROM images WHERE status = 'error'"
    ).fetchone()["c"]
    conn.close()
    return {"total": total, "pending": pending, "done": done, "error": error}


@app.get("/api/tags-meta")
def list_tags_meta(search: str = Query(None)):
    return get_tag_meta(search=search)


class TagMetaCreate(BaseModel):
    name: str
    description: str = ""


@app.post("/api/tags-meta")
def add_tag_meta_endpoint(data: TagMetaCreate):
    upsert_tag_meta(data.name, data.description)
    return {"status": "ok"}


class TagMetaUpdate(BaseModel):
    description: str


@app.put("/api/tags-meta/{name}")
def update_tag_meta_endpoint(name: str, data: TagMetaUpdate):
    upsert_tag_meta(name, data.description)
    return {"status": "ok"}


@app.delete("/api/tags-meta/{name}")
def delete_tag_meta_endpoint(name: str):
    delete_tag_meta(name)
    return {"status": "deleted"}


@app.get("/api/tag-synonyms")
def list_tag_synonyms(search: str = Query(None)):
    return get_tag_synonyms(search=search)


class TagSynonymCreate(BaseModel):
    synonym: str
    canonical: str


@app.post("/api/tag-synonyms")
def add_tag_synonym_endpoint(data: TagSynonymCreate):
    add_tag_synonym(data.synonym, data.canonical)
    return {"status": "ok"}


@app.delete("/api/tag-synonyms/{synonym}")
def delete_tag_synonym_endpoint(synonym: str):
    delete_tag_synonym(synonym)
    return {"status": "deleted"}


if os.path.isdir(DIST):
    @app.get("/{full_path:path}")
    def serve_frontend(full_path: str):
        file_path = os.path.join(DIST, full_path)
        if full_path and os.path.isfile(file_path):
            return FileResponse(file_path)
        index = os.path.join(DIST, "index.html")
        if os.path.isfile(index):
            return HTMLResponse(open(index).read())
        return JSONResponse({"error": "frontend not built"}, status_code=503)
