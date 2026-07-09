(function () {
  const toggle = document.getElementById("search-toggle");
  const drawer = document.getElementById("search-drawer");
  if (toggle && drawer) {
    function closeDrawer() {
      drawer.classList.remove("open");
      toggle.setAttribute("aria-expanded", "false");
    }
    function openDrawer() {
      drawer.classList.add("open");
      toggle.setAttribute("aria-expanded", "true");
      const input = document.getElementById("search-drawer-input");
      if (input) input.focus();
    }
    toggle.addEventListener("click", function (e) {
      e.stopPropagation();
      if (drawer.classList.contains("open")) closeDrawer();
      else openDrawer();
    });
    document.addEventListener("click", function (e) {
      if (drawer.classList.contains("open") && !drawer.contains(e.target) && e.target !== toggle) {
        closeDrawer();
      }
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeDrawer();
    });
  }
})();

(function () {
  const params = new URLSearchParams(window.location.search);
  const q = (params.get("q") || "").trim();

  const resultsEl = document.getElementById("search-results");
  const input = document.querySelector(".search-form input");
  if (input && q) input.value = q;

  if (!resultsEl) return;

  if (!q) {
    resultsEl.innerHTML = "<p>הקלד מונח חיפוש בשדה למעלה.</p>";
    return;
  }

  fetch("/assets/search-index.json")
    .then((r) => r.json())
    .then((data) => {
      const needle = q.toLowerCase();
      const matches = data.filter((a) =>
        a.title.toLowerCase().includes(needle) ||
        a.category.toLowerCase().includes(needle) ||
        a.source.toLowerCase().includes(needle)
      );

      if (!matches.length) {
        resultsEl.innerHTML = "<p>לא נמצאו תוצאות עבור \"" + escapeHtml(q) + "\".</p>";
        return;
      }

      resultsEl.innerHTML = matches
        .slice(0, 60)
        .map((a) => {
          const img = a.image || "/assets/placeholder.svg";
          const videoBadge = a.video ? '<span class="badge badge-video">וידאו</span>' : "";
          return `
          <a class="card" href="/article/${a.slug}.html">
            <div class="card-img-wrap">
              <img class="card-img" src="${escapeHtml(img)}" alt="" loading="lazy" onerror="this.src='/assets/placeholder.svg'">
              ${videoBadge}
            </div>
            <div class="card-body">
              <span class="card-cat">${escapeHtml(a.category)}</span>
              <h3>${escapeHtml(a.title)}</h3>
              <span class="card-meta">${escapeHtml(a.source)} · ${escapeHtml(a.date.slice(0, 10))}</span>
            </div>
          </a>`;
        })
        .join("");
    })
    .catch(() => {
      resultsEl.innerHTML = "<p>שגיאה בטעינת תוצאות החיפוש.</p>";
    });

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
})();

(function () {
  var section = document.getElementById("recently-viewed-section");
  var grid = document.getElementById("recently-viewed-grid");
  if (!section || !grid) return;

  var list;
  try {
    list = JSON.parse(localStorage.getItem("kk_recent") || "[]");
  } catch (e) {
    list = [];
  }
  if (!list.length) return;

  grid.innerHTML = list
    .map(function (a) {
      return (
        '<a class="card" href="/article/' + a.slug + '.html">' +
        '<div class="card-img-wrap"><img class="card-img" src="' + escapeHtml(a.img) + '" alt="" loading="lazy"></div>' +
        '<div class="card-body">' +
        '<span class="card-cat">' + escapeHtml(a.cat) + "</span>" +
        "<h3>" + escapeHtml(a.title) + "</h3>" +
        "</div></a>"
      );
    })
    .join("");
  section.hidden = false;

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }
})();

(function () {
  var select = document.getElementById("sort-select");
  var grid = document.getElementById("category-grid");
  if (!select || !grid) return;

  var originalOrder = Array.from(grid.children);

  select.addEventListener("change", function () {
    var order = select.value === "oldest" ? originalOrder.slice().reverse() : originalOrder;
    order.forEach(function (el) { grid.appendChild(el); });
  });
})();
