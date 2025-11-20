#!/usr/bin/env python3
from __future__ import annotations
import argparse, csv, os, sqlite3, sys
from typing import List, Tuple

# --- project-root safe paths ---
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH  = os.path.join(APP_ROOT, "db", "books.db")
SCHEMA   = os.path.join(APP_ROOT, "db", "script.sql")
CSV_PATH = os.path.join(APP_ROOT, "data", "books.csv")  # optional

# --- sample data fallback (same as before) ---
def cover(isbn: str) -> str:
    return f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"

FALLBACK_BOOKS: List[Tuple[str, int, str, str]] = [
    ("Clean Code", 2008, "Robert C. Martin", cover("9780132350884")),
    ("The Pragmatic Programmer", 1999, "Andrew Hunt", cover("9780201616224")),
    ("Design Patterns: Elements of Reusable Object-Oriented Software", 1994, "Erich Gamma", cover("9780201633610")),
    ("Refactoring: Improving the Design of Existing Code (2nd Edition)", 2018, "Martin Fowler", cover("9780134757599")),
    ("Introduction to Algorithms (3rd Edition)", 2009, "Thomas H. Cormen", cover("9780262033848")),
    ("Structure and Interpretation of Computer Programs", 1996, "Harold Abelson", cover("9780262510875")),
    ("Code Complete (2nd Edition)", 2004, "Steve McConnell", cover("9780735619678")),
    ("Patterns of Enterprise Application Architecture", 2002, "Martin Fowler", cover("9780321127426")),
    ("Working Effectively with Legacy Code", 2004, "Michael Feathers", cover("9780131177055")),
    ("Clean Architecture", 2017, "Robert C. Martin", cover("9780134494166")),
]

def ensure_schema(con: sqlite3.Connection) -> None:
    with open(SCHEMA, "r", encoding="utf-8") as f:
        con.executescript(f.read())
    # Case-insensitive uniqueness on title
    con.execute("DROP INDEX IF EXISTS idx_books_unique_title")
    con.execute("""
      CREATE UNIQUE INDEX IF NOT EXISTS idx_books_unique_title_nocase
      ON books(title COLLATE NOCASE)
    """)
    con.commit()

def read_books_from_csv() -> List[Tuple[str, int, str, str]]:
    if not os.path.exists(CSV_PATH):
        return []
    rows: List[Tuple[str, int, str, str]] = []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        rdr = csv.DictReader(f)
        for r in rdr:
            title = (r.get("title") or "").strip()
            author = (r.get("author") or "").strip()
            year = int(r.get("year") or 0)
            image = (r.get("image_url") or "").strip()
            if title and author and year:
                rows.append((title, year, author, image))
    return rows

def upsert_books(con: sqlite3.Connection, books: List[Tuple[str, int, str, str]]) -> int:
    """
    Upsert by title (NOCASE). Ensures author row + link in book_author.
    Returns number of titles processed.
    """
    cur = con.cursor()
    for title, year, author, image_url in books:
        # ensuring author
        cur.execute("INSERT OR IGNORE INTO authors(name) VALUES (?)", (author,))
        author_id = cur.execute("SELECT author_id FROM authors WHERE name = ?", (author,)).fetchone()[0]

        # book by title (NOCASE)
        cur.execute("SELECT book_id FROM books WHERE title = ? COLLATE NOCASE", (title,))
        row = cur.fetchone()
        if row:
            book_id = row[0]
            cur.execute(
                "UPDATE books SET publication_year = ?, image_url = COALESCE(?, image_url) WHERE book_id = ?",
                (year, image_url or None, book_id),
            )
        else:
            cur.execute(
                "INSERT INTO books(title, publication_year, image_url) VALUES (?,?,?)",
                (title, year, image_url or None),
            )
            book_id = cur.lastrowid

        # linking
        cur.execute(
            "INSERT OR IGNORE INTO book_author(book_id, author_id) VALUES (?, ?)",
            (book_id, author_id),
        )
    con.commit()
    return len(books)

def reset_sqlite() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    ensure_schema(con)
    con.close()

def seed_sqlite() -> int:
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    ensure_schema(con)
    data = read_books_from_csv() or FALLBACK_BOOKS
    n = upsert_books(con, data)
    cnt = con.execute("SELECT COUNT(*) FROM books").fetchone()[0]
    con.close()
    print(f"Seeded/updated {n} titles. Total in DB: {cnt}.")
    return n

def clear_mongo_reviews(uri: str, db_name: str, coll: str) -> int:
    from pymongo import MongoClient
    c = MongoClient(uri, uuidRepresentation="standard")
    db = c[db_name]
    res = db[coll].delete_many({})
    c.close()
    return res.deleted_count

def main():
    parser = argparse.ArgumentParser(description="Manage DB for Fancy Book Shelf")
    parser.add_argument("--reset", action="store_true", help="Delete SQLite DB and recreate schema")
    parser.add_argument("--seed", action="store_true", help="Upsert seed data (CSV or fallback)")
    parser.add_argument("--wipe-reviews", action="store_true", help="Delete ALL MongoDB reviews")
    parser.add_argument("--mongo-uri", default=os.environ.get("MONGODB_URI","mongodb://127.0.0.1:27017"))
    parser.add_argument("--mongo-db", default=os.environ.get("MONGO_DB_NAME","books_app"))
    parser.add_argument("--mongo-coll", default=os.environ.get("REVIEWS_COLL","reviews"))
    args = parser.parse_args()

    if args.reset:
        reset_sqlite()
        print(f"SQLite reset at: {DB_PATH}")

    if args.seed:
        seed_sqlite()

    if args.wipe_reviews:
        deleted = clear_mongo_reviews(args.mongo_uri, args.mongo_db, args.mongo_coll)
        print(f"Deleted {deleted} MongoDB reviews from {args.mongo_db}.{args.mongo_coll}")

    if not (args.reset or args.seed or args.wipe_reviews):
        parser.print_help()

if __name__ == "__main__":
    sys.exit(main())
