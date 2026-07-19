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

(function () {
  var bar = document.querySelector(".engagement-bar");
  var likeBtn = document.getElementById("like-btn");
  var shareBtn = document.getElementById("share-btn");
  if (!bar) return;

  var slug = bar.getAttribute("data-slug");

  if (likeBtn) {
    var likeKey = "kk_liked";
    var liked;
    try {
      liked = JSON.parse(localStorage.getItem(likeKey) || "[]");
    } catch (e) {
      liked = [];
    }
    var isLiked = liked.indexOf(slug) !== -1;
    if (isLiked) {
      likeBtn.classList.add("liked");
      likeBtn.setAttribute("aria-pressed", "true");
      likeBtn.querySelector("#like-count").textContent = "אהבתי!";
    }
    likeBtn.addEventListener("click", function () {
      var idx = liked.indexOf(slug);
      if (idx === -1) {
        liked.push(slug);
        likeBtn.classList.add("liked");
        likeBtn.setAttribute("aria-pressed", "true");
        likeBtn.querySelector("#like-count").textContent = "אהבתי!";
      } else {
        liked.splice(idx, 1);
        likeBtn.classList.remove("liked");
        likeBtn.setAttribute("aria-pressed", "false");
        likeBtn.querySelector("#like-count").textContent = "אהבתי";
      }
      try {
        if (localStorage.getItem("kk_cookie_consent") !== "declined") {
          localStorage.setItem(likeKey, JSON.stringify(liked));
        }
      } catch (e) {}
    });
  }

  if (shareBtn) {
    shareBtn.addEventListener("click", function () {
      var title = shareBtn.getAttribute("data-title");
      var url = shareBtn.getAttribute("data-url");
      if (navigator.share) {
        navigator.share({ title: title, url: url }).catch(function () {});
      } else if (navigator.clipboard) {
        navigator.clipboard.writeText(url).then(function () {
          var span = shareBtn.querySelector("span");
          var original = span.textContent;
          span.textContent = "הועתק!";
          setTimeout(function () { span.textContent = original; }, 1800);
        });
      }
    });
  }
})();

(function () {
  var player = document.querySelector(".kk-player");
  if (!player) return;
  var playBtn = player.querySelector(".kk-player-play");
  var videoId = player.getAttribute("data-video-id");

  playBtn.addEventListener("click", function () {
    var iframe = document.createElement("iframe");
    iframe.src = "https://www.youtube-nocookie.com/embed/" + videoId + "?autoplay=1";
    iframe.setAttribute("allow", "accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture");
    iframe.setAttribute("allowfullscreen", "");
    iframe.setAttribute("frameborder", "0");
    player.innerHTML = "";
    player.appendChild(iframe);
  });
})();

(function () {
  var els = document.querySelectorAll(".reveal");
  if (!els.length) return;
  if (!("IntersectionObserver" in window)) {
    els.forEach(function (el) { el.classList.add("is-visible"); });
    return;
  }
  var observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (entry.isIntersecting) {
        entry.target.classList.add("is-visible");
        observer.unobserve(entry.target);
      }
    });
  }, { threshold: 0.1, rootMargin: "0px 0px -40px 0px" });
  els.forEach(function (el) { observer.observe(el); });
})();

(function () {
  var banner = document.getElementById("cookie-banner");
  if (!banner) return;
  var KEY = "kk_cookie_consent";
  var existing;
  try {
    existing = localStorage.getItem(KEY);
  } catch (e) {
    existing = null;
  }
  if (!existing) {
    banner.hidden = false;
  }

  var acceptBtn = document.getElementById("cookie-accept");
  var declineBtn = document.getElementById("cookie-decline");

  if (acceptBtn) {
    acceptBtn.addEventListener("click", function () {
      try { localStorage.setItem(KEY, "accepted"); } catch (e) {}
      banner.hidden = true;
    });
  }
  if (declineBtn) {
    declineBtn.addEventListener("click", function () {
      try {
        localStorage.setItem(KEY, "declined");
        // honor the choice immediately - clear anything already stored
        localStorage.removeItem("kk_recent");
        localStorage.removeItem("kk_liked");
      } catch (e) {}
      banner.hidden = true;
    });
  }
})();

(function () {
  var toggle = document.getElementById("a11y-toggle");
  var panel = document.getElementById("a11y-panel");
  if (!toggle || !panel) return;

  var STORAGE_KEY = "kk_a11y";
  var root = document.documentElement;
  var FONT_STEP = 1;
  var MIN_SIZE = 14;
  var MAX_SIZE = 24;

  function loadState() {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}");
    } catch (e) {
      return {};
    }
  }
  function saveState(state) {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch (e) {}
  }
  function applyState(state) {
    root.classList.toggle("a11y-contrast", !!state.contrast);
    root.classList.toggle("a11y-stop-motion", !!state.stopMotion);
    if (state.fontSize) {
      root.style.fontSize = state.fontSize + "px";
    } else {
      root.style.fontSize = "";
    }
  }

  var state = loadState();
  applyState(state);

  toggle.addEventListener("click", function () {
    var isHidden = panel.hidden;
    panel.hidden = !isHidden;
    toggle.setAttribute("aria-expanded", String(isHidden));
  });

  document.addEventListener("click", function (e) {
    if (!panel.hidden && !panel.contains(e.target) && e.target !== toggle) {
      panel.hidden = true;
      toggle.setAttribute("aria-expanded", "false");
    }
  });

  panel.querySelectorAll("button[data-a11y]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var action = btn.getAttribute("data-a11y");
      var current = getComputedStyle(root).fontSize;
      var currentSize = parseFloat(current) || 17;
      if (action === "font-inc") {
        state.fontSize = Math.min(MAX_SIZE, currentSize + FONT_STEP);
      } else if (action === "font-dec") {
        state.fontSize = Math.max(MIN_SIZE, currentSize - FONT_STEP);
      } else if (action === "contrast") {
        state.contrast = !state.contrast;
      } else if (action === "stop-motion") {
        state.stopMotion = !state.stopMotion;
      } else if (action === "reset") {
        state = {};
      }
      applyState(state);
      saveState(state);
    });
  });
})();

(function () {
  // Honest, real personalization: reorders this visitor's own homepage
  // category sections based on their own local reading history
  // (kk_recent, saved to their browser only). Never leaves the browser,
  // never touches the scraper/server side, and only runs if the visitor
  // hasn't declined local storage.
  var wrap = document.getElementById("personalized-sections");
  if (!wrap) return;
  try {
    if (localStorage.getItem("kk_cookie_consent") === "declined") return;
    var recent = JSON.parse(localStorage.getItem("kk_recent") || "[]");
    if (!recent.length) return;
    var counts = {};
    recent.forEach(function (item) {
      if (item.cat) counts[item.cat] = (counts[item.cat] || 0) + 1;
    });
    var sections = Array.from(wrap.querySelectorAll(".cat-section-wrap"));
    if (sections.length < 2) return;
    sections.sort(function (a, b) {
      var ac = counts[a.getAttribute("data-category")] || 0;
      var bc = counts[b.getAttribute("data-category")] || 0;
      return bc - ac;
    });
    var hasPreference = sections.some(function (s) {
      return (counts[s.getAttribute("data-category")] || 0) > 0;
    });
    if (hasPreference) {
      sections.forEach(function (s) { wrap.appendChild(s); });
    }
  } catch (e) {}
})();
