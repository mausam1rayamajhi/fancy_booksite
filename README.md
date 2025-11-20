# Fancy Book Shelf

Polished Flask + SQLite bookshelf with modern UI, real covers, search, and integration tests.

## Quickstart
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# initialize DB schema and seed 10 real books
python - <<'PY'
from seed import seed
seed('db/books.db')
PY

python app.py
# open http://127.0.0.1:5000
```

## Tests
```bash
pytest -q
# or with coverage
pytest --cov=.
```
