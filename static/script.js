//Globals & Utilities 
const DEFAULT_COVER =
  "https://images.rawpixel.com/image_png_social_landscape/" +
  "czNmcy1wcml2YXRlL3Jhd3BpeGVsX2ltYWdlcy93ZWJzaXRlX2NvbnRlbnQv" +
  "bHIvam9iNjgzLTAwMzEucG5n.png";

async function fetchJSON(url, opts) {
  const res = await fetch(
    url,
    Object.assign({ headers: { "Content-Type": "application/json" } }, opts || {})
  );
  if (!res.ok) {
    let text = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status}: ${text || res.statusText}`);
  }
  return await res.json();
}

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

//  Cards
function cardHTML(book) {
  const img = (book.image_url && book.image_url.trim()) || DEFAULT_COVER;
  const authors = book.authors || "Unknown";
  const year = book.publication_year ?? "";

  return `
  <article class="card" data-book='${JSON.stringify(book).replaceAll("'", "&apos;")}'>
    <img class="cover" src="${img}" alt="Cover of ${escapeHtml(book.title)}" loading="lazy">
    <div class="meta">
      <div class="title">${escapeHtml(book.title)}</div>
      <p class="author">${escapeHtml(authors)}</p>
      ${year !== "" ? `<div class="year">${escapeHtml(String(year))}</div>` : ""}
    </div>
  </article>`;
}

function renderShelfPayload(payload) {
  const shelf = document.getElementById("shelf");
  const rc = document.getElementById("resultCount");
  const items = (payload && payload.items) || [];

  if (!shelf) return;

  if (items.length === 0) {
    if (rc) rc.textContent = "0 results";
    shelf.innerHTML = `<div class="empty">No books found.</div>`;
    return;
  }

  if (rc) rc.textContent = `${items.length} result${items.length === 1 ? "" : "s"}`;
  shelf.innerHTML = items.map(cardHTML).join("");

  // open modal on click (robust JSON parse)
  shelf.querySelectorAll(".card").forEach((el) => {
    const raw = (el.getAttribute("data-book") || "").replaceAll("&apos;", "'");
    const book = JSON.parse(raw);
    el.addEventListener("click", () => openBookModal(book));
  });
}

async function loadBooks(q = "", limit = "all") {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (limit != null) params.set("limit", String(limit));
  const url = `/api/books${params.toString() ? "?" + params.toString() : ""}`;
  const payload = await fetchJSON(url);
  renderShelfPayload(payload);
}

// Adding Book Flow 
function validateForm({ title, author, publication_year }) {
  const errs = [];
  if (!title) errs.push("Title");
  if (!author) errs.push("Author");
  if (publication_year === "" || publication_year === null || publication_year === undefined) {
    errs.push("Publication Year");
  } else if (!/^\d+$/.test(String(publication_year))) {
    errs.push("Publication Year (must be an integer)");
  }
  return errs;
}

async function addBook() {
  const title = document.getElementById("bookTitle")?.value.trim() || "";
  const author = document.getElementById("authorName")?.value.trim() || "";
  const publication_year = document.getElementById("publicationYear")?.value.trim() || "";
  const image_url = document.getElementById("imageUrl")?.value.trim() || "";

  const errors = validateForm({ title, author, publication_year });
  if (errors.length) {
    alert("Please correct the following:\n• " + errors.join("\n• "));
    return;
  }

  const payload = {
    title,
    author,
    publication_year: parseInt(publication_year, 10),
    image_url: image_url || null
  };

  try {
    await fetchJSON("/api/books", {
      method: "POST",
      body: JSON.stringify(payload)
    });

    const clear = (id) => { const el = document.getElementById(id); if (el) el.value = ""; };
    ["bookTitle", "authorName", "publicationYear", "imageUrl"].forEach(clear);

    // CHANGED: after adding, reloading full list
    await loadBooks("", "all");
  } catch (err) {
    console.error(err);
    alert("Failed to add book. " + err.message);
  }
}

//Modal: book details + reviews
const modal = {
  root: null,
  cover: null,
  title: null,
  authors: null,
  year: null,
  reviewsBox: null,
  form: null,
  toggleBtn: null,
  currentBookId: null,
  showAll: false,
  cachedReviews: null
};

function initModalRefs() {
  if (modal.root) return;
  modal.root = document.getElementById("bookModal");
  modal.cover = document.getElementById("modalCover");
  modal.title = document.getElementById("modalTitle");
  modal.authors = document.getElementById("modalAuthors");
  modal.year = document.getElementById("modalYear");
  modal.reviewsBox = document.getElementById("modalReviews");
  modal.form = document.getElementById("modalReviewForm");
  modal.toggleBtn = document.getElementById("modalToggleAll");

  if (!modal.root) return;

  // close handlers
  modal.root.querySelectorAll("[data-close]").forEach(btn =>
    btn.addEventListener("click", closeBookModal)
  );
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal.root.getAttribute("aria-hidden") === "false") {
      closeBookModal();
    }
  });

  // submitting review (then refreshing list, keeping current showAll mode)
  if (modal.form) {
    modal.form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const reviewer = modal.form.querySelector('input[name=reviewer]')?.value.trim() || "";
      const rating = modal.form.querySelector('input[name=rating]')?.value.trim() || "";
      const text = modal.form.querySelector('textarea[name=text]')?.value.trim() || "";
      if (!reviewer || !rating || !text) {
        alert("Please fill all review fields.");
        return;
      }
      await fetchJSON("/api/reviews", {
        method: "POST",
        body: JSON.stringify({
          book_id: modal.currentBookId,
          reviewer,
          rating: Number(rating),
          text
        })
      });
      modal.form.reset();
      await loadReviews(modal.currentBookId); // respects modal.showAll
      modal.reviewsBox?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  }

  // toggle Show all / Show less
  if (modal.toggleBtn) {
    modal.toggleBtn.addEventListener("click", () => {
      modal.showAll = !modal.showAll;
      renderReviews(modal.cachedReviews);
    });
  }
}

function openBookModal(book) {
  initModalRefs();
  modal.currentBookId = book.book_id;
  modal.showAll = false; // starts with "recent 3"

  if (modal.cover) {
    modal.cover.src = (book.image_url && book.image_url.trim()) || DEFAULT_COVER;
    modal.cover.alt = `Cover of ${book.title}`;
  }
  if (modal.title) modal.title.textContent = book.title;
  if (modal.authors) modal.authors.textContent = book.authors || "Unknown";
  if (modal.year) modal.year.textContent = book.publication_year ? String(book.publication_year) : "";

  if (modal.root) {
    modal.root.setAttribute("aria-hidden", "false");
  }
  document.body.classList.add("modal-open");
  loadReviews(book.book_id);
}

function closeBookModal() {
  if (!modal.root) return;
  modal.root.setAttribute("aria-hidden", "true");
  document.body.classList.remove("modal-open");
}

//Reviews (MongoDB)
async function loadReviews(bookId) {
  if (modal.reviewsBox) {
    modal.reviewsBox.innerHTML = `<div class="muted">Loading reviews...</div>`;
  }
  try {
    const data = await fetchJSON(`/api/reviews?book_id=${bookId}`);
    renderReviews(data);
  } catch (e) {
    console.error("Failed to load reviews", e);
    if (modal.reviewsBox) {
      modal.reviewsBox.innerHTML = `<div class="error">Failed to load reviews.</div>`;
    }
    if (modal.toggleBtn) modal.toggleBtn.style.display = "none";
  }
}

function renderReviews(data) {
  modal.cachedReviews = data;
  const items = (data && data.items) || [];
  const total = data && typeof data.count === "number" ? data.count : items.length;

  // API returns newest first; for "recent", show the first 3
  const toShow = modal.showAll ? items : items.slice(0, 3);

  if (modal.reviewsBox) {
    if (total === 0) {
      modal.reviewsBox.innerHTML = `<div class="muted">No reviews yet.</div>`;
    } else {
      modal.reviewsBox.innerHTML = toShow.map(r => `
        <div class="review">
          <div class="review-head">
            <strong>${escapeHtml(r.reviewer)}</strong>
            <span class="muted">(${r.rating}/5)</span>
            <span class="muted review-time">${r.created_at ? new Date(r.created_at).toLocaleString() : ""}</span>
          </div>
          <div class="review-text">${escapeHtml(r.text)}</div>
        </div>
      `).join("");  // closing backtick now in the right place
    }
  }

  if (modal.toggleBtn) {
    if (total > 3) {
      modal.toggleBtn.style.display = "inline-flex";
      modal.toggleBtn.textContent = modal.showAll ? "Show less" : `Show all (${total})`;
    } else {
      modal.toggleBtn.style.display = "none";
    }
  }
}


// Wire-up
document.addEventListener("DOMContentLoaded", async () => {
  const addBtn = document.getElementById("addBtn");
  if (addBtn) addBtn.addEventListener("click", addBook);

  const form = document.getElementById("searchForm");
  if (form) {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const q = document.getElementById("searchInput")?.value.trim() || "";
      await loadBooks(q, "all");
    });
  }

  const showAllBtn = document.getElementById("showAllBtn");
  if (showAllBtn) {
    showAllBtn.addEventListener("click", async () => {
      const si = document.getElementById("searchInput");
      if (si) si.value = "";
      await loadBooks("", "all");
    });
  }

  const si = document.getElementById("searchInput");
  if (si) {
    si.addEventListener("keydown", async (e) => {
      if (e.key === "Escape") {
        e.target.value = "";
        await loadBooks("", "all");
      }
    });
  }

  // CHANGED: Initial auto-load = all books
  await loadBooks("", "all");
});
