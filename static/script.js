const DEFAULT_COVER =
  "https://images.rawpixel.com/image_png_social_landscape/czNmcy1wcml2YXRlL3Jhd3BpeGVsX2ltYWdlcy93ZWJzaXRlX2NvbnRlbnQvbHIvam9iNjgzLTAwMzEucG5n.png";

const PALETTES = [
  ["#4f46e5", "#0ea5e9"],
  ["#22c55e", "#86efac"],
  ["#f97316", "#fb923c"],
  ["#ec4899", "#f472b6"],
  ["#6366f1", "#8b5cf6"],
  ["#14b8a6", "#2dd4bf"],
  ["#a855f7", "#d946ef"]
];

const ANGLES = ["45deg", "120deg", "180deg", "200deg"];

function hashInt(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) {
    h = (h * 31 + str.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

function coverBackground(title) {
  const h = hashInt(title);
  const palette = PALETTES[h % PALETTES.length];
  const angle = ANGLES[h % ANGLES.length];
  return `linear-gradient(${angle}, ${palette[0]}, ${palette[1]})`;
}

async function fetchJSON(url, opts = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...opts
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  return await res.json();
}

function escapeHtml(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function cardHTML(book) {
  const title = book.title || "Untitled";
  const authors = book.authors || "Unknown";
  const year = book.publication_year ?? "";
  const bg = coverBackground(title);
  const safeBook = JSON.stringify(book).replaceAll("'", "&apos;");

  return `
    <article class="card" data-book='${safeBook}'>
      <div class="cover-auto" style="background:${bg}">
        <div class="cover-auto__title">${escapeHtml(title)}</div>
      </div>
      <div class="meta">
        <div class="title">${escapeHtml(title)}</div>
        <p class="author">${escapeHtml(authors)}</p>
        ${year ? `<div class="year">${escapeHtml(String(year))}</div>` : ""}
      </div>
    </article>`;
}

function renderShelfPayload(payload) {
  const shelf = document.getElementById("shelf");
  const rc = document.getElementById("resultCount");
  const items = payload.items || [];

  if (!items.length) {
    if (rc) rc.textContent = "0 results";
    if (shelf) {
      shelf.innerHTML = `<div class="empty">No books found.</div>`;
    }
    return;
  }

  if (rc) rc.textContent = `${items.length} result${items.length === 1 ? "" : "s"}`;
  if (shelf) {
    shelf.innerHTML = items.map(cardHTML).join("");

    shelf.querySelectorAll(".card").forEach((el) => {
      const raw = el.getAttribute("data-book").replaceAll("&apos;", "'");
      const book = JSON.parse(raw);
      el.addEventListener("click", () => openBookModal(book));
    });
  }
}

async function loadBooks(q = "", limit = "all") {
  const params = new URLSearchParams();
  if (q.trim()) params.set("q", q);
  params.set("limit", limit);
  const data = await fetchJSON(`/api/books?${params}`);
  renderShelfPayload(data);
}

async function addBook() {
  const title = document.getElementById("bookTitle").value.trim();
  const author = document.getElementById("authorName").value.trim();
  const publication_year = document.getElementById("publicationYear").value.trim();
  const image_url = document.getElementById("imageUrl").value.trim();

  if (!title || !author || !publication_year) {
    alert("Title, Author, and Publication Year are required.");
    return;
  }

  await fetchJSON("/api/books", {
    method: "POST",
    body: JSON.stringify({
      title,
      author,
      publication_year: Number(publication_year),
      image_url: image_url || null
    })
  });

  ["bookTitle", "authorName", "publicationYear", "imageUrl"].forEach((id) => {
    document.getElementById(id).value = "";
  });

  await loadBooks("", "all");
}

const modal = {
  root: null,
  coverImg: null,
  coverAuto: null,
  coverAutoTitle: null,
  title: null,
  authors: null,
  year: null,
  reviewsBox: null,
  form: null,
  toggleBtn: null,
  currentBookId: null,
  cachedReviews: null,
  showAll: false
};

function initModalRefs() {
  modal.root = document.getElementById("bookModal");
  modal.coverImg = document.getElementById("modalCover");
  modal.coverAuto = document.getElementById("modalCoverAuto");
  modal.coverAutoTitle = document.querySelector("#modalCoverAuto .modal__cover-title");
  modal.title = document.getElementById("modalTitle");
  modal.authors = document.getElementById("modalAuthors");
  modal.year = document.getElementById("modalYear");
  modal.reviewsBox = document.getElementById("modalReviews");
  modal.form = document.getElementById("modalReviewForm");
  modal.toggleBtn = document.getElementById("modalToggleAll");

  modal.root.querySelectorAll("[data-close]").forEach((btn) =>
    btn.addEventListener("click", closeBookModal)
  );

  modal.form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const fd = new FormData(modal.form);
    const reviewer = (fd.get("reviewer") || "").toString().trim();
    const rating = Number(fd.get("rating"));
    const text = (fd.get("text") || "").toString().trim();

    if (!reviewer || !rating || !text) {
      alert("Please fill all review fields.");
      return;
    }

    await fetchJSON("/api/reviews", {
      method: "POST",
      body: JSON.stringify({
        book_id: modal.currentBookId,
        reviewer,
        rating,
        text
      })
    });

    modal.form.reset();
    loadReviews(modal.currentBookId);
  });

  modal.toggleBtn.addEventListener("click", () => {
    modal.showAll = !modal.showAll;
    renderReviews(modal.cachedReviews);
  });
}

function openBookModal(book) {
  if (!modal.root) initModalRefs();

  modal.currentBookId = book.book_id;
  modal.title.textContent = book.title;
  modal.authors.textContent = book.authors || "Unknown";
  modal.year.textContent = book.publication_year || "";

  if (book.image_url && book.image_url.trim()) {
    modal.coverImg.style.display = "block";
    modal.coverImg.src = book.image_url.trim();
    modal.coverImg.onerror = () => {
      modal.coverImg.style.display = "none";
      modal.coverAuto.style.display = "flex";
      modal.coverAuto.style.background = coverBackground(book.title);
      modal.coverAutoTitle.textContent = book.title;
    };
    modal.coverAuto.style.display = "none";
  } else {
    modal.coverImg.style.display = "none";
    modal.coverAuto.style.display = "flex";
    modal.coverAuto.style.background = coverBackground(book.title);
    modal.coverAutoTitle.textContent = book.title;
  }

  modal.root.setAttribute("aria-hidden", "false");
  document.body.classList.add("modal-open");
  loadReviews(book.book_id);
}

function closeBookModal() {
  modal.root.setAttribute("aria-hidden", "true");
  document.body.classList.remove("modal-open");
}

async function loadReviews(bookId) {
  modal.reviewsBox.innerHTML = "<div class='muted'>Loading...</div>";
  const data = await fetchJSON(`/api/reviews?book_id=${bookId}`);
  modal.cachedReviews = data;
  renderReviews(data);
}

function renderReviews(data) {
  const items = data.items || [];
  const visible = modal.showAll ? items : items.slice(0, 3);

  if (!items.length) {
    modal.reviewsBox.innerHTML = "<div class='muted'>No reviews yet.</div>";
  } else {
    modal.reviewsBox.innerHTML = visible
      .map(
        (r) => `
        <div class="review">
          <div class="review-head">
            <strong>${escapeHtml(r.reviewer)}</strong>
            <span class="muted">(${r.rating}/5)</span>
            <span class="muted review-time">${
              r.created_at ? new Date(r.created_at).toLocaleString() : ""
            }</span>
          </div>
          <div class="review-text">${escapeHtml(r.text)}</div>
        </div>
      `
      )
      .join("");
  }

  if (items.length > 3) {
    modal.toggleBtn.style.display = "inline";
    modal.toggleBtn.textContent = modal.showAll
      ? "Show less"
      : `Show all (${items.length})`;
  } else {
    modal.toggleBtn.style.display = "none";
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  const addBtn = document.getElementById("addBtn");
  const searchForm = document.getElementById("searchForm");
  const showAllBtn = document.getElementById("showAllBtn");
  const searchInput = document.getElementById("searchInput");

  if (addBtn) addBtn.addEventListener("click", addBook);

  if (searchForm) {
    searchForm.addEventListener("submit", (e) => {
      e.preventDefault();
      loadBooks(searchInput.value.trim());
    });
  }

  if (showAllBtn) {
    showAllBtn.addEventListener("click", () => {
      searchInput.value = "";
      loadBooks("");
    });
  }

  await loadBooks("", "all");
});
