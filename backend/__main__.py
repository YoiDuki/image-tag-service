import sys
import os
import uvicorn


def main():
    args = sys.argv[1:]

    if not args or args[0] in ("run", "server"):
        from backend.app import app
        uvicorn.run("backend.app:app", host="0.0.0.0", port=5000, reload=True)
        return

    command = args[0]

    if command == "scan":
        from tag.database import init_db
        from tag.scanner import process_new_files
        init_db()
        directory = args[1] if len(args) > 1 else "."
        limit = int(args[2]) if len(args) > 2 else 0
        process_new_files(directory, limit)
    elif command == "process":
        from tag.database import init_db
        from tag.scanner import process_pending
        init_db()
        force = "--force" in args
        worker_args = [a for a in args[1:] if a != "--force"]
        max_workers = int(worker_args[0]) if worker_args else None
        process_pending(max_workers, force=force)
    elif command == "gen-desc":
        from tag.database import init_db, generate_tag_descriptions
        init_db()
        top_n = int(args[1]) if len(args) > 1 else 10
        generate_tag_descriptions(top_n=top_n)
    elif command == "gen-translations":
        from tag.database import init_db, get_conn
        init_db()
        _gen_translations(args)
    else:
        print(f"Unknown command: {command}")
        print("Available commands:")
        print("  (no args)         Start the web server")
        print("  scan <dir> [lim]  Scan directory for new images")
        print("  process [n] [--force]  Process pending images")
        print("  gen-desc [n]      Generate tag descriptions")
        print("  gen-translations [n] [--overwrite]  Generate translations")


def _gen_translations(args):
    try:
        from deep_translator import GoogleTranslator
    except ImportError:
        print("Install deep-translator: python -m pip install deep-translator")
        return

    import json
    from collections import Counter
    from tag.database import get_conn

    overwrite = "--overwrite" in args
    cmd_args = [a for a in args if a != "--overwrite"]
    top_n = int(cmd_args[1]) if len(cmd_args) > 1 else 500

    conn = get_conn()
    rows = conn.execute("SELECT tags FROM images WHERE tags IS NOT NULL AND tags != '[]'").fetchall()
    tag_freq = Counter()
    for r in rows:
        try:
            for t in json.loads(r["tags"]):
                if isinstance(t, str) and t.strip():
                    tag_freq[t.strip()] += 1
        except (json.JSONDecodeError, TypeError):
            pass

    existing = set()
    for r in conn.execute("SELECT DISTINCT canonical FROM tag_synonyms").fetchall():
        existing.add(r["canonical"])

    if overwrite:
        conn.execute("DELETE FROM tag_synonyms WHERE synonym GLOB '*[^a-zA-Z0-9_ -]*'")
        conn.commit()
        existing.clear()

    candidates = [(tag, freq) for tag, freq in tag_freq.most_common() if tag not in existing]
    if top_n and top_n < len(candidates):
        candidates = candidates[:top_n]

    if not candidates:
        print("Nothing to translate")
        conn.close()
        return

    to_translate = [tag for tag, _ in candidates]
    print(f"Translating top {len(to_translate)} tags by frequency...")

    translator = GoogleTranslator(source="en", target="zh-CN")
    batch_size = 200
    added = 0
    for i in range(0, len(to_translate), batch_size):
        batch = to_translate[i : i + batch_size]
        batch_clean = [t.replace("_", " ") for t in batch]
        try:
            results = translator.translate_batch(batch_clean)
        except Exception as e:
            print(f"  Batch error at {i}: {e}")
            results = []
            for t in batch_clean:
                try:
                    results.append(translator.translate(t))
                except Exception as e2:
                    print(f"    SKIP {t}: {e2}")
                    results.append(None)
        for tag, cn in zip(batch, results):
            if cn and cn.strip() and cn.strip().lower() != tag.replace("_", " ") and len(cn.strip()) < 50:
                conn.execute(
                    "INSERT OR IGNORE INTO tag_synonyms (synonym, canonical) VALUES (?, ?)",
                    (cn.strip().lower(), tag),
                )
                added += 1
        conn.commit()
        print(f"  ... {min(i + batch_size, len(to_translate))}/{len(to_translate)} added:{added}")
    conn.close()
    total_coverage = sum(freq for _, freq in candidates) / sum(tag_freq.values()) * 100
    print(f"Done. Added {added} translations (covers {total_coverage:.1f}% of tag occurrences)")


if __name__ == "__main__":
    main()
