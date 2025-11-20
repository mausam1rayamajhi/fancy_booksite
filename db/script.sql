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
