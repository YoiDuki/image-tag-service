import sys
import os
from tag.database import init_db
from tag.scanner import process_new_files, process_pending


def main():
    init_db()

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python run_tag.py scan <directory> [limit]")
        print("  python run_tag.py process [max_workers] [--force]")
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
    else:
        print(f"Unknown command: {command}")


if __name__ == "__main__":
    main()
