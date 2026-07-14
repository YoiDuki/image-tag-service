import os
import json
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
from tag.database import init_db, get_all_images, get_filters, search_by_color, upsert_image, image_exists, get_conn, get_tag_meta, upsert_tag_meta, delete_tag_meta, get_tag_synonyms, add_tag_synonym, delete_tag_synonym

app = Flask(__name__, static_folder="../frontend/dist", static_url_path="")
CORS(app)
init_db()

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def serve_frontend(path):
    dist = app.static_folder
    if not dist or not os.path.isdir(dist):
        return jsonify({"error": "frontend not built"}), 503
    if path and os.path.isfile(os.path.join(dist, path)):
        return send_from_directory(dist, path)
    return send_from_directory(dist, "index.html")


@app.route("/api/images/<filename>/file", methods=["GET"])
def serve_image(filename):
    conn = get_conn()
    row = conn.execute(
        "SELECT filepath FROM images WHERE filename = ?", (filename,)
    ).fetchone()
    conn.close()
    if row is None:
        return jsonify({"error": "not found"}), 404
    if not os.path.isfile(row["filepath"]):
        return jsonify({"error": "file not found on disk"}), 404
    return send_file(row["filepath"])


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/api/images", methods=["GET"])
def list_images():
    result = get_all_images(
        status=request.args.get("status"),
        author=request.args.get("author"),
        media_type=request.args.get("media_type"),
        style=request.args.get("style"),
        tag=request.args.get("tag"),
        nsfw=request.args.get("nsfw"),
        search=request.args.get("search"),
        sort=request.args.get("sort", "updated_at"),
        page=request.args.get("page", 1, type=int),
        per_page=request.args.get("per_page", 24, type=int),
    )
    return jsonify(result)


@app.route("/api/filters", methods=["GET"])
def filters():
    return jsonify(get_filters())


@app.route("/api/images/color", methods=["GET"])
def search_color():
    r = request.args.get("r", type=int)
    g = request.args.get("g", type=int)
    b = request.args.get("b", type=int)
    if r is None or g is None or b is None:
        return jsonify({"error": "r, g, b are required"}), 400
    threshold = request.args.get("threshold", 100, type=int)
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 24, type=int)
    return jsonify(search_by_color(r, g, b, threshold, page, per_page))


@app.route("/api/images/<filename>", methods=["GET"])
def get_image(filename):
    conn = get_conn()
    _COLS = "id, filename, filepath, tags, artists, characters, media_type, style, nsfw, status, error, palette, author_username, posted_at, created_at, updated_at, tags_edited"
    row = conn.execute(
        f"SELECT {_COLS} FROM images WHERE filename = ?", (filename,)
    ).fetchone()
    conn.close()
    if row is None:
        return jsonify({"error": "not found"}), 404
    d = dict(row)
    for field in ("tags", "palette", "artists", "characters"):
        if isinstance(d.get(field), str):
            d[field] = json.loads(d[field])
    return jsonify(d)


@app.route("/api/images/<filename>", methods=["PUT"])
def update_image(filename):
    data = request.get_json()
    if not data:
        return jsonify({"error": "no data"}), 400
    if not image_exists(filename):
        return jsonify({"error": "not found"}), 404

    allowed_fields = {
        "tags", "artists", "characters", "media_type", "style",
        "nsfw", "palette",
        "author_username", "posted_at", "status", "error", "filepath",
    }
    update_data = {k: v for k, v in data.items() if k in allowed_fields}

    if not update_data:
        return jsonify({"error": "no valid fields"}), 400

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
    return jsonify({"status": "updated"})


@app.route("/api/images/<filename>", methods=["DELETE"])
def delete_image(filename):
    conn = get_conn()
    conn.execute("DELETE FROM images WHERE filename = ?", (filename,))
    conn.commit()
    conn.close()
    return jsonify({"status": "deleted"})


@app.route("/api/stats", methods=["GET"])
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
    return jsonify({"total": total, "pending": pending, "done": done, "error": error})


@app.route("/api/tags-meta", methods=["GET"])
def list_tags_meta():
    search = request.args.get("search")
    return jsonify(get_tag_meta(search=search))


@app.route("/api/tags-meta", methods=["POST"])
def add_tag_meta():
    data = request.get_json()
    if not data or "name" not in data:
        return jsonify({"error": "name is required"}), 400
    upsert_tag_meta(data["name"], data.get("description", ""))
    return jsonify({"status": "ok"})


@app.route("/api/tags-meta/<name>", methods=["PUT"])
def update_tag_meta(name):
    data = request.get_json()
    if not data or "description" not in data:
        return jsonify({"error": "description is required"}), 400
    upsert_tag_meta(name, data["description"])
    return jsonify({"status": "ok"})


@app.route("/api/tags-meta/<name>", methods=["DELETE"])
def delete_tag_meta_route(name):
    delete_tag_meta(name)
    return jsonify({"status": "deleted"})


@app.route("/api/tag-synonyms", methods=["GET"])
def list_tag_synonyms():
    search = request.args.get("search")
    return jsonify(get_tag_synonyms(search=search))


@app.route("/api/tag-synonyms", methods=["POST"])
def add_tag_synonym_route():
    data = request.get_json()
    if not data or "synonym" not in data or "canonical" not in data:
        return jsonify({"error": "synonym and canonical are required"}), 400
    add_tag_synonym(data["synonym"], data["canonical"])
    return jsonify({"status": "ok"})


@app.route("/api/tag-synonyms/<synonym>", methods=["DELETE"])
def delete_tag_synonym_route(synonym):
    delete_tag_synonym(synonym)
    return jsonify({"status": "deleted"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=not os.environ.get("PROD"))
