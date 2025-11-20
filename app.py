from __future__ import annotations
import os
import sqlite3
from datetime import datetime, timezone
from flask import Flask, jsonify, request, render_template, g, has_request_context
from flask import Response, make_response
import time
import json
from functools import wraps
from bson import ObjectId
import mysql.connector 


# Logging helpers (MySQL)
def get_logs_db_conn():
    cfg = {
        "host": os.environ.get("LOGS_DB_HOST", "127.0.0.1"),
        "user": os.environ.get("LOGS_DB_USER", "root"),
        "password": os.environ.get("LOGS_DB_PASSWORD", ""),
        "database": os.environ.get("LOGS_DB_NAME", "books"),
    }
    conn = mysql.connector.connect(**cfg)
    try:
        conn.autocommit = True
    except Exception:
        pass
    return conn


def _write_log_row(function_name, status, message=None, execution_time=None, extra=None):
    if os.environ.get("DISABLE_DB_LOGGING") == "1":
        return
    try:
        http_method = path = user_agent = None
        if has_request_context():
            http_method = request.method
            path = request.path
            user_agent = (request.headers.get("User-Agent", "") or "")[:255]
        extra_json = json.dumps(extra) if extra else None
        conn = get_logs_db_conn()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO logs (function_name, status, message, execution_time, http_method, path, user_agent, extra_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s, CAST(%s AS JSON))
                """,
                (function_name, status, message, execution_time, http_method, path, user_agent, extra_json)
            )
            conn.commit()
        finally:
            try:
                cur.close()
            except Exception:
                pass
            conn.close()
    except Exception as log_err:
        print(f"[LOGGING ERROR] {log_err}")


def log_call(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        t1 = time.perf_counter()
        try:
            result = func(*args, **kwargs)

            # Normalizing to a Response to inspect status code
            resp = result
            if not isinstance(result, Response):
                resp = make_response(result)

            dt = time.perf_counter() - t1
            status_label = "success" if 200 <= resp.status_code < 400 else "error"
            _write_log_row(func.__name__, status_label, execution_time=dt)
            return result
        except Exception as e:
            _write_log_row(func.__name__, "error", message=str(e), execution_time=None)
            raise
    return wrapper


# Ending Logging helpers

# default cover if a book has no image_url
DEFAULT_COVER = (
    "https://images.rawpixel.com/image_png_social_landscape/"
    "czNmcy1wcml2YXRlL3Jhd3BpeGVsX2ltYWdlcy93ZWJzaXRlX2NvbnRlbnQv"
    "bHIvam9iNjgzLTAwMzEucG5n.png"
)


def create_app(config: dict | None = None):

    """
    Flask app factory. You can override settings by passing a dict:
      - DATABASE: SQLite path (default env BOOKS_DB_PATH or db/books.db)
      - MONGODB_URI: Mongo connection string (default env MONGODB_URI or localhost)
      - MONGO_DB_NAME: Mongo DB name (default env MONGO_DB_NAME or books_app)
      - REVIEWS_COLL: Mongo collection name (default env REVIEWS_COLL or reviews)
    """
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
        static_url_path="/static",
    )
    cfg = config or {}

    DB_PATH = cfg.get("DATABASE", os.environ.get("BOOKS_DB_PATH", "db/books.db"))
    # normalizing to absolute path relative to the project so cwd doesn't matter
    if not os.path.isabs(DB_PATH):
        DB_PATH = os.path.join(app.root_path, DB_PATH)

    MONGODB_URI = (
        os.environ.get("MONGO_URL")
        or os.environ.get("MONGODB_URI")
        or "mongodb://127.0.0.1:27017/"
    )
    MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "books_app")
    REVIEWS_COLL = os.environ.get("REVIEWS_COLL", "reviews")




    # SQLite helpers (books/authors) 
    def get_db():
        if "db" not in g:
            g.db = sqlite3.connect(DB_PATH)
            g.db.row_factory = sqlite3.Row
        return g.db

    @app.teardown_appcontext
    def close_dbs(_exc):
        db = g.pop("db", None)
        if db is not None:
            db.close()
        mclient = g.pop("mclient", None)
        if mclient is not None:
            mclient.close()

    # Mongo helpers (reviews)
    def get_reviews_coll():
        from pymongo import MongoClient  
        if "mclient" not in g:
            g.mclient = MongoClient(MONGODB_URI, uuidRepresentation="standard")
            g.mdb = g.mclient[MONGO_DB_NAME]
        return g.mdb[REVIEWS_COLL]

    #Routes 

    @app.get("/")
    @log_call
    def home():
        return render_template("index.html")

    @app.get("/api/books")
    @log_call
    def list_books():
        q = (request.args.get("q") or "").strip()
        pattern = f"%{q}%"

        # Support ?limit=all or an integer (default 100)
        limit_raw = (request.args.get("limit") or "100").strip().lower()
        if limit_raw == "all":
            limit = None
        else:
            try:
                limit = int(limit_raw)
            except Exception:
                limit = 100

        base_sql = """
        SELECT b.book_id, b.title, b.publication_year,
               COALESCE(b.image_url, ?) AS image_url,
               GROUP_CONCAT(a.name, ', ') AS authors
        FROM books b
        LEFT JOIN book_author ba ON ba.book_id = b.book_id
        LEFT JOIN authors a ON a.author_id = ba.author_id
        WHERE (? = '' OR b.title LIKE ? OR a.name LIKE ?)
        GROUP BY b.book_id, b.title, b.publication_year, b.image_url
        ORDER BY b.title COLLATE NOCASE ASC
        """
        params = [DEFAULT_COVER, q, pattern, pattern]
        sql = base_sql + (" LIMIT ?" if limit is not None else "")
        if limit is not None:
            params.append(limit)

        rows = get_db().execute(sql, params).fetchall()
        return jsonify({"items": [dict(r) for r in rows], "count": len(rows)})

    @app.post("/api/books")
    @log_call
    def add_book():
        data = request.get_json(force=True, silent=True) or {}
        title = (data.get("title") or "").strip()
        author = (data.get("author") or "").strip()
        year = data.get("publication_year")
        image_url = (data.get("image_url") or "").strip() or None

        if not title or not author:
            return jsonify({"error": "title and author required"}), 400
        try:
            year = int(year)
        except Exception:
            return jsonify({"error": "publication_year must be an integer"}), 400

        db = get_db()
        cur = db.cursor()

        # Ensuring author row exists
        cur.execute("INSERT OR IGNORE INTO authors(name) VALUES(?)", (author,))
        cur.execute("SELECT author_id FROM authors WHERE name = ?", (author,))
        author_id = cur.fetchone()["author_id"]

        # Checking for an existing book by title (case-insensitive)
        cur.execute(
            "SELECT book_id FROM books WHERE title = ? COLLATE NOCASE",
            (title,),
        )
        row = cur.fetchone()

        if row:
            # Updating existing book's year/image if provided
            book_id = row["book_id"]
            cur.execute(
                "UPDATE books SET publication_year = COALESCE(?, publication_year), "
                "image_url = COALESCE(?, image_url) WHERE book_id = ?",
                (year, image_url, book_id),
            )
            # Ensuring link exists
            cur.execute(
                "INSERT OR IGNORE INTO book_author(book_id, author_id) VALUES(?,?)",
                (book_id, author_id),
            )
            db.commit()

            sql = """
            SELECT b.book_id, b.title, b.publication_year,
                   COALESCE(b.image_url, ?) AS image_url,
                   GROUP_CONCAT(a.name, ', ') AS authors
            FROM books b
            LEFT JOIN book_author ba ON ba.book_id = b.book_id
            LEFT JOIN authors a ON a.author_id = ba.author_id
            WHERE b.book_id = ?
            GROUP BY b.book_id, b.title, b.publication_year, b.image_url
            """
            existing = db.execute(sql, (DEFAULT_COVER, book_id)).fetchone()
            return jsonify(
                {"message": "Book already existed; updated/linked author.", "book": dict(existing)}
            ), 200

        # Inserting new book
        cur.execute(
            "INSERT INTO books(title, publication_year, image_url) VALUES(?,?,?)",
            (title, year, image_url),
        )
        book_id = cur.lastrowid
        cur.execute(
            "INSERT OR IGNORE INTO book_author(book_id, author_id) VALUES(?,?)",
            (book_id, author_id),
        )
        db.commit()

        sql = """
        SELECT b.book_id, b.title, b.publication_year,
               COALESCE(b.image_url, ?) AS image_url,
               GROUP_CONCAT(a.name, ', ') AS authors
        FROM books b
        LEFT JOIN book_author ba ON ba.book_id = b.book_id
        LEFT JOIN authors a ON a.author_id = ba.author_id
        WHERE b.book_id = ?
        GROUP BY b.book_id, b.title, b.publication_year, b.image_url
        """
        new_book = db.execute(sql, (DEFAULT_COVER, book_id)).fetchone()
        return jsonify({"message": "Book added successfully", "book": dict(new_book)}), 201

    # Reviews (MongoDB)
    def _serialize_review(doc):
        created = doc.get("created_at")
        if isinstance(created, datetime):
            created = created.isoformat()
        return {
            "_id": str(doc.get("_id")),
            "book_id": int(doc.get("book_id")) if doc.get("book_id") is not None else None,
            "reviewer": doc.get("reviewer"),
            "rating": int(doc.get("rating")) if doc.get("rating") is not None else None,
            "text": doc.get("text"),
            "created_at": created,
        }

    @app.get("/api/reviews")
    @log_call
    def get_reviews():
        book_id = request.args.get("book_id")
        if not book_id:
            return jsonify({"error": "book_id is required"}), 400
        try:
            book_id = int(book_id)
        except Exception:
            return jsonify({"error": "book_id must be an integer"}), 400

        # fetching from Mongo
        coll = get_reviews_coll()
        items = list(coll.find({"book_id": book_id}).sort("created_at", -1))
        return jsonify({"items": [_serialize_review(d) for d in items], "count": len(items)})

    @app.post("/api/reviews")
    @log_call
    def add_review():
        data = request.get_json(force=True, silent=True) or {}
        # Validating fields
        for field in ("book_id", "reviewer", "rating", "text"):
            if field not in data or (isinstance(data[field], str) and not data[field].strip()):
                return jsonify({"error": f"{field} is required"}), 400
        try:
            book_id = int(data["book_id"])
            rating = int(data["rating"])
            if rating < 1 or rating > 5:
                raise ValueError()
        except Exception:
            return jsonify({"error": "rating must be integer 1-5 and book_id integer"}), 400

        # ensuring book exists in SQLite
        if not get_db().execute("SELECT 1 FROM books WHERE book_id = ?", (book_id,)).fetchone():
            return jsonify({"error": "book_id does not exist"}), 404

        # inserting into Mongo
        coll = get_reviews_coll()
        doc = {
            "book_id": book_id,
            "reviewer": str(data["reviewer"]).strip(),
            "rating": rating,
            "text": str(data["text"]).strip(),
            "created_at": datetime.now(timezone.utc),
        }
        inserted = coll.insert_one(doc)
        saved = coll.find_one({"_id": inserted.inserted_id})
        return jsonify({"message": "Review added", "review": _serialize_review(saved)}), 201

    @app.delete("/api/reviews/<rid>")
    def delete_review(rid):
        coll = get_reviews_coll()
        try:
            oid = ObjectId(rid)
        except Exception:
            return jsonify({"error": "invalid review id"}), 400
        res = coll.delete_one({"_id": oid})
        return jsonify({"deleted": res.deleted_count})

    return app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
