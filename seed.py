# seed.py
import sqlite3
from typing import List, Tuple
import os

def cover(isbn: str) -> str:
  return f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg"

# 10 real books: (title, year, author, image_url)
BOOKS: List[Tuple[str, int, str, str]] = [
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

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS books (
  book_id INTEGER PRIMARY KEY,
  title TEXT NOT NULL,
  publication_year INTEGER,
  image_url TEXT
);

CREATE TABLE IF NOT EXISTS authors (
  author_id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS book_author (
  book_id INTEGER NOT NULL,
  author_id INTEGER NOT NULL,
  PRIMARY KEY (book_id, author_id),
  FOREIGN KEY (book_id) REFERENCES books (book_id) ON DELETE CASCADE,
  FOREIGN KEY (author_id) REFERENCES authors (author_id) ON DELETE CASCADE
);
"""

def seed(db_path: str = "db/books.db") -> None:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()

        # 1) Ensuring tables exist
        cur.executescript(SCHEMA_SQL)

        # 2) Unique title to prevent duplicates
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_books_unique_title ON books(title)")

        # 3) Upsert each book; ensure author; link
        for title, year, author, image_url in BOOKS:
            cur.execute("SELECT book_id FROM books WHERE title = ?", (title,))
            row = cur.fetchone()
            if row:
                book_id = row[0]
                cur.execute(
                    "UPDATE books SET publication_year = ?, image_url = ? WHERE book_id = ?",
                    (year, image_url, book_id),
                )
            else:
                cur.execute(
                    "INSERT INTO books(title, publication_year, image_url) VALUES (?, ?, ?)",
                    (title, year, image_url),
                )
                book_id = cur.lastrowid

            cur.execute("INSERT OR IGNORE INTO authors(name) VALUES (?)", (author,))
            author_id = cur.execute(
                "SELECT author_id FROM authors WHERE name = ?", (author,)
            ).fetchone()[0]

            cur.execute(
                "INSERT OR IGNORE INTO book_author(book_id, author_id) VALUES (?, ?)",
                (book_id, author_id),
            )

        con.commit()
        print("Seeding complete: 10 books.")
    finally:
        con.close()

if __name__ == "__main__":
    seed("db/books.db")
