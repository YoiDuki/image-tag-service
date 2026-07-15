import sys
import os
from tag.database import init_db, generate_tag_descriptions, get_conn
from tag.scanner import process_new_files, process_pending


def main():
    init_db()

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python run_tag.py scan <directory> [limit]")
        print("  python run_tag.py process [max_workers] [--force]")
        print("  python run_tag.py gen-desc [top_n]")
        print("  python run_tag.py gen-translations [top_n] [--overwrite]")
        return

    command = sys.argv[1]

    if command == "scan":
        directory = sys.argv[2] if len(sys.argv) > 2 else "."
        limit = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        process_new_files(directory, limit)
    elif command == "process":
        force = "--force" in sys.argv
        args = [a for a in sys.argv[2:] if a != "--force"]
        max_workers = int(args[0]) if args else None
        process_pending(max_workers, force=force)
    elif command == "gen-desc":
        top_n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        generate_tag_descriptions(top_n=top_n)
    elif command == "gen-translations":
        overwrite = "--overwrite" in sys.argv
        args = [a for a in sys.argv[2:] if a != "--overwrite"]
        top_n = int(args[0]) if args else 500
        _gen_translations(overwrite=overwrite, top_n=top_n)
    else:
        print(f"Unknown command: {command}")


def _gen_translations(overwrite=False, top_n=500):
    try:
        from deep_translator import GoogleTranslator
    except ImportError:
        print("Install deep-translator: python -m pip install deep-translator")
        return

    import json
    from collections import Counter

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

    # Prioritize by frequency, take top_n
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
