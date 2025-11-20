# test_app.py
import os
import shutil
import tempfile
import time
import uuid
import json
import sqlite3
import pytest

from app import create_app

# ---------- Helpers ----------
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

SAMPLE_BOOK = (
    "PyTest Sample Book",
    2024,
    "https://covers.openlibrary.org/b/isbn/9780132350884-L.jpg",
    "Unit Tester"
)

def ensure_db_has_book(db_path: str):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA_SQL)
        cur = conn.cursor()
        # If there are books already, leave them
        n = cur.execute("SELECT COUNT(*) FROM books").fetchone()[0]
        if n == 0:
            # Insert one sample book + author link
            title, year, img, author = SAMPLE_BOOK
            cur.execute("INSERT OR IGNORE INTO authors(name) VALUES (?)", (author,))
            cur.execute("SELECT author_id FROM authors WHERE name=?", (author,))
            aid = cur.fetchone()[0]
            cur.execute("INSERT INTO books(title, publication_year, image_url) VALUES (?,?,?)",
                        (title, year, img))
            bid = cur.lastrowid
            cur.execute("INSERT OR IGNORE INTO book_author(book_id, author_id) VALUES (?,?)",
                        (bid, aid))
        conn.commit()
    finally:
        conn.close()

# ---------- Pytest fixtures ----------

@pytest.fixture(scope="session")
def tmp_sqlite_db():
    """Make a writable copy of your real db if it exists; otherwise create minimal DB with 1 book."""
    project_db = os.path.join(os.getcwd(), "db", "books.db")
    tmpdir = tempfile.mkdtemp(prefix="books_sqlite_")
    tmpdb = os.path.join(tmpdir, "books.db")
    if os.path.exists(project_db):
        shutil.copy2(project_db, tmpdb)
    ensure_db_has_book(tmpdb)
    yield tmpdb
    # cleanup
    shutil.rmtree(tmpdir, ignore_errors=True)

@pytest.fixture(scope="session")
def mongo_test_cfg():
    """Use a throwaway Mongo DB so we don't touch your dev data."""
    uri = os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017")
    dbname = f"books_app_test_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    coll = "reviews"
    return {"MONGODB_URI": uri, "MONGO_DB_NAME": dbname, "REVIEWS_COLL": coll}

@pytest.fixture(scope="session")
def app(tmp_sqlite_db, mongo_test_cfg):
    cfg = {
        "DATABASE": tmp_sqlite_db,
        "MONGODB_URI": mongo_test_cfg["MONGODB_URI"],
        "MONGO_DB_NAME": mongo_test_cfg["MONGO_DB_NAME"],
        "REVIEWS_COLL": mongo_test_cfg["REVIEWS_COLL"],
    }
    app = create_app(cfg)
    # testing mode for Flask
    app.config.update(TESTING=True)
    yield app

    # teardown: drop the temporary Mongo database
    try:
        from pymongo import MongoClient
        client = MongoClient(mongo_test_cfg["MONGODB_URI"], uuidRepresentation="standard")
        client.drop_database(mongo_test_cfg["MONGO_DB_NAME"])
        client.close()
    except Exception:
        pass  # if Mongo isn't running, tests would have failed earlier anyway

@pytest.fixture()
def client(app):
    return app.test_client()

# ---------- Tests ----------

def test_books_list_has_items(client):
    r = client.get("/api/books?limit=all")
    assert r.status_code == 200
    data = r.get_json()
    assert isinstance(data, dict)
    assert "items" in data and "count" in data
    assert data["count"] >= 1
    # keep first book_id for next test via response body
    # (pytest will call tests independently; the next test fetches it again)
    assert isinstance(data["items"][0]["book_id"], int)

def test_reviews_crud_round_trip(client):
    # 1) get one real book_id
    r = client.get("/api/books?limit=1")
    assert r.status_code == 200
    book = r.get_json()["items"][0]
    book_id = int(book["book_id"])

    # 2) add a review
    payload = {
        "book_id": book_id,
        "reviewer": "PyTest",
        "rating": 5,
        "text": "Great integration!"
    }
    r = client.post("/api/reviews", data=json.dumps(payload),
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 201
    created = r.get_json()["review"]
    assert created["book_id"] == book_id
    assert created["reviewer"] == "PyTest"
    assert created["rating"] == 5
    rid = created["_id"]

    # 3) fetch reviews for that book
    r = client.get(f"/api/reviews?book_id={book_id}")
    assert r.status_code == 200
    reviews = r.get_json()
    assert reviews["count"] >= 1
    assert any(rv["_id"] == rid for rv in reviews["items"])

    # 4) delete that review
    r = client.delete(f"/api/reviews/{rid}")
    assert r.status_code == 200
    assert r.get_json()["deleted"] in (1, 0)  # 1 normally; 0 if already deleted

    # 5) confirm it's gone
    r = client.get(f"/api/reviews?book_id={book_id}")
    assert r.status_code == 200
    ids = [rv["_id"] for rv in r.get_json()["items"]]
    assert rid not in ids
