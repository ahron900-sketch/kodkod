// Honest, client-side-only "style learning": a running tally of which
// categories/sources/content-types this visitor engages with, kept entirely
// in localStorage (never transmitted anywhere). Views count once each;
// likes count extra, since liking is a much stronger preference signal than
// just viewing. Used later in this file to re-rank homepage/category
// sections and cards - never to change what's actually published.
window.kkAffinity = (function () {
  var KEY = "kk_affinity";
  function consented() {
    try { return localStorage.getItem("kk_cookie_consent") !== "declined"; } catch (e) { return false; }
  }
  function load() {
    try { return JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { return {}; }
  }
  function save(data) {
    try { localStorage.setItem(KEY, JSON.stringify(data)); } catch (e) {}
  }
  function bump(data, bucket, key, delta) {
    if (!key) return;
    if (!data[bucket]) data[bucket] = {};
    data[bucket][key] = (data[bucket][key] || 0) + delta;
  }
  return {
    get: load,
    recordEntry: function (entry, delta) {
      if (!entry || !consented()) return;
      var data = load();
      bump(data, "cats", entry.cat, delta);
      bump(data, "sources", entry.source, delta);
      bump(data, "types", entry.type, delta);
      save(data);
    }
  };
})();

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
  // Infinite scroll on category pages: the static HTML already has the
  // first ~100 articles; further batches are read from the site's existing
  // search-index.json (already generated for the search feature - reused
  // here instead of building separate per-category pagination files) and
  // fetched only once the visitor actually scrolls near the bottom.
  var grid = document.getElementById("category-grid");
  var sentinel = document.getElementById("load-more-sentinel");
  if (!grid || !sentinel) return;

  var category = grid.getAttribute("data-category");
  var shown = parseInt(grid.getAttribute("data-shown-count"), 10) || 0;
  var PAGE_SIZE = 24;
  var PLACEHOLDER = "/assets/placeholder.svg";
  var categoryArticles = null;
  var loading = false;
  var exhausted = false;

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function cardHtml(a) {
    var img = a.image || PLACEHOLDER;
    var videoBadge = a.video ? '<span class="badge badge-video">וידאו</span>' : "";
    return (
      '<a class="card" href="/article/' + a.slug + '.html" data-slug="' + escapeHtml(a.slug) +
      '" data-cat="' + escapeHtml(a.category) + '" data-source="' + escapeHtml(a.source) + '">' +
      '<div class="card-img-wrap">' +
      '<img class="card-img" src="' + escapeHtml(img) + '" alt="" loading="lazy" onerror="this.src=\'' + PLACEHOLDER + '\'">' +
      videoBadge +
      '</div>' +
      '<div class="card-body">' +
      '<span class="card-cat">' + escapeHtml(a.category) + '</span>' +
      '<h3>' + escapeHtml(a.title) + '</h3>' +
      '<span class="card-meta">' + escapeHtml(a.source) + ' · ' + escapeHtml(a.date.slice(0, 10)) + '</span>' +
      '</div></a>'
    );
  }

  function finishLoad() {
    loading = false;
    sentinel.hidden = true;
  }

  function loadNextPage() {
    if (loading || exhausted) return;
    loading = true;
    sentinel.hidden = false;

    var ready = categoryArticles
      ? Promise.resolve(categoryArticles)
      : fetch("/assets/search-index.json")
          .then(function (r) { return r.json(); })
          .then(function (data) {
            categoryArticles = data
              .filter(function (a) { return a.category === category; })
              .sort(function (a, b) { return a.date < b.date ? 1 : -1; });
            return categoryArticles;
          });

    ready.then(function (list) {
      var next = list.slice(shown, shown + PAGE_SIZE);
      if (!next.length) {
        exhausted = true;
        observer.disconnect();
        finishLoad();
        return;
      }
      grid.insertAdjacentHTML("beforeend", next.map(cardHtml).join(""));
      shown += next.length;
      if (shown >= list.length) {
        exhausted = true;
        observer.disconnect();
      }
      finishLoad();
    }).catch(function () {
      finishLoad();
    });
  }

  var observer = new IntersectionObserver(function (entries) {
    if (entries[0].isIntersecting) loadNextPage();
  }, { rootMargin: "600px 0px" });
  observer.observe(sentinel);
})();

(function () {
  var bar = document.querySelector(".engagement-bar");
  var likeBtn = document.getElementById("like-btn");
  var shareBtn = document.getElementById("share-btn");
  if (!bar) return;

  var slug = bar.getAttribute("data-slug");
  var likeEntry = {
    cat: bar.getAttribute("data-cat"),
    source: bar.getAttribute("data-source"),
    type: bar.getAttribute("data-type")
  };
  var LIKE_AFFINITY_WEIGHT = 2;

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
        if (window.kkAffinity) window.kkAffinity.recordEntry(likeEntry, LIKE_AFFINITY_WEIGHT);
      } else {
        liked.splice(idx, 1);
        likeBtn.classList.remove("liked");
        likeBtn.setAttribute("aria-pressed", "false");
        likeBtn.querySelector("#like-count").textContent = "אהבתי";
        if (window.kkAffinity) window.kkAffinity.recordEntry(likeEntry, -LIKE_AFFINITY_WEIGHT);
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
  var carousel = document.getElementById("hero-carousel");
  if (!carousel) return;
  var slides = carousel.querySelectorAll(".hero-slide");
  var dots = carousel.querySelectorAll(".hero-dot");
  if (slides.length < 2) return;

  var current = 0;
  var ROTATE_MS = 2000;
  var timer = null;

  function showSlide(index) {
    slides.forEach(function (s, i) { s.classList.toggle("active", i === index); });
    dots.forEach(function (d, i) { d.classList.toggle("active", i === index); });
    current = index;
  }
  function start() {
    timer = setInterval(function () {
      showSlide((current + 1) % slides.length);
    }, ROTATE_MS);
  }
  function stop() {
    if (timer) clearInterval(timer);
    timer = null;
  }

  dots.forEach(function (dot, i) {
    dot.addEventListener("click", function () {
      stop();
      showSlide(i);
      start();
    });
  });
  carousel.addEventListener("mouseenter", stop);
  carousel.addEventListener("mouseleave", start);

  start();
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
        localStorage.removeItem("kk_affinity");
        localStorage.removeItem("kk_affinity_last_slug");
      } catch (e) {}
      banner.hidden = true;
    });
  }
})();

(function () {
  var toggleBtn = document.getElementById("a11y-toggle");
  var drawer = document.getElementById("a11y-drawer");
  var closeBtn = document.getElementById("a11y-close");
  if (!toggleBtn || !drawer) return;

  var STORAGE_KEY = "kk_a11y";
  var root = document.documentElement;
  var FONT_STEP = 1;
  var MIN_SIZE = 14;
  var MAX_SIZE = 24;

  var CLASS_MAP = {
    lineHeight: "a11y-line-height",
    letterSpacing: "a11y-letter-spacing",
    readableFont: "a11y-readable-font",
    contrast: "a11y-contrast",
    invert: "a11y-invert",
    grayscale: "a11y-grayscale",
    underlineLinks: "a11y-underline-links",
    bigCursor: "a11y-big-cursor",
    stopMotion: "a11y-stop-motion",
    readingGuide: "a11y-reading-guide"
  };
  var ACTION_MAP = {
    "line-height": "lineHeight",
    "letter-spacing": "letterSpacing",
    "readable-font": "readableFont",
    "contrast": "contrast",
    "invert": "invert",
    "grayscale": "grayscale",
    "underline-links": "underlineLinks",
    "big-cursor": "bigCursor",
    "stop-motion": "stopMotion",
    "reading-guide": "readingGuide"
  };

  function loadState() {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || "{}"); }
    catch (e) { return {}; }
  }
  function saveState(state) {
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch (e) {}
  }
  function applyState(state) {
    Object.keys(CLASS_MAP).forEach(function (key) {
      root.classList.toggle(CLASS_MAP[key], !!state[key]);
    });
    root.style.fontSize = state.fontSize ? state.fontSize + "px" : "";
    drawer.querySelectorAll("button[data-a11y]").forEach(function (btn) {
      var key = ACTION_MAP[btn.getAttribute("data-a11y")];
      if (key) btn.classList.toggle("active", !!state[key]);
    });
  }

  var state = loadState();
  applyState(state);

  function openDrawer() {
    drawer.hidden = false;
    requestAnimationFrame(function () { drawer.classList.add("open"); });
    toggleBtn.setAttribute("aria-expanded", "true");
  }
  function closeDrawer() {
    drawer.classList.remove("open");
    toggleBtn.setAttribute("aria-expanded", "false");
    setTimeout(function () { drawer.hidden = true; }, 300);
  }
  toggleBtn.addEventListener("click", function () {
    if (drawer.classList.contains("open")) closeDrawer();
    else openDrawer();
  });
  if (closeBtn) closeBtn.addEventListener("click", closeDrawer);
  document.addEventListener("click", function (e) {
    if (drawer.classList.contains("open") && !drawer.contains(e.target) && !toggleBtn.contains(e.target)) {
      closeDrawer();
    }
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && drawer.classList.contains("open")) closeDrawer();
  });

  drawer.querySelectorAll("button[data-a11y]").forEach(function (btn) {
    var action = btn.getAttribute("data-a11y");
    if (action === "read-aloud") return; // has its own handler below
    btn.addEventListener("click", function () {
      if (action === "font-inc" || action === "font-dec") {
        var currentSize = parseFloat(getComputedStyle(root).fontSize) || 17;
        state.fontSize = action === "font-inc"
          ? Math.min(MAX_SIZE, currentSize + FONT_STEP)
          : Math.max(MIN_SIZE, currentSize - FONT_STEP);
      } else if (action === "reset") {
        state = {};
      } else if (ACTION_MAP[action]) {
        var key = ACTION_MAP[action];
        state[key] = !state[key];
      }
      applyState(state);
      saveState(state);
    });
  });

  // Reading guide: translucent bar that follows the cursor vertically,
  // only active while the toggle is on (checked on every mousemove so
  // turning it off/on doesn't need attaching/detaching the listener)
  var guideBar = document.createElement("div");
  guideBar.className = "a11y-reading-guide-bar";
  document.body.appendChild(guideBar);
  document.addEventListener("mousemove", function (e) {
    if (root.classList.contains("a11y-reading-guide")) {
      guideBar.style.top = (e.clientY - 20) + "px";
    }
  });

  // Read-aloud: native browser speech synthesis (window.speechSynthesis) -
  // no external service, no API key, works entirely offline once the page
  // has loaded. Reads the current article's title + body, if present.
  var readAloudBtn = document.getElementById("a11y-read-aloud");
  if (readAloudBtn) {
    if (!("speechSynthesis" in window)) {
      readAloudBtn.disabled = true;
      readAloudBtn.textContent = "הקראה לא נתמכת בדפדפן זה";
    } else {
      var speaking = false;
      readAloudBtn.addEventListener("click", function () {
        if (speaking) {
          window.speechSynthesis.cancel();
          speaking = false;
          readAloudBtn.textContent = "הקראת הכתבה";
          readAloudBtn.classList.remove("active");
          return;
        }
        var titleEl = document.querySelector("main.article h1");
        var bodyEls = document.querySelectorAll("main.article .article-body");
        if (!titleEl && !bodyEls.length) {
          var original = readAloudBtn.textContent;
          readAloudBtn.textContent = "אין כתבה להקראה בעמוד זה";
          setTimeout(function () { readAloudBtn.textContent = original; }, 2500);
          return;
        }
        var text = (titleEl ? titleEl.textContent + ". " : "") +
          Array.prototype.map.call(bodyEls, function (el) { return el.textContent; }).join(" ");
        var utterance = new SpeechSynthesisUtterance(text);
        utterance.lang = "he-IL";
        utterance.onend = function () {
          speaking = false;
          readAloudBtn.textContent = "הקראת הכתבה";
          readAloudBtn.classList.remove("active");
        };
        window.speechSynthesis.cancel();
        window.speechSynthesis.speak(utterance);
        speaking = true;
        readAloudBtn.textContent = "עצור הקראה";
        readAloudBtn.classList.add("active");
      });
    }
  }
})();

(function () {
  // The article view_tracker script (runs earlier, inline, on article pages)
  // already pushed this page's article to the front of kk_recent - pick it
  // up here and count it once towards the running kk_affinity tally. Guarded
  // by a "last recorded slug" marker so re-rendering/reloading the same
  // article page doesn't count the same view twice.
  if (!window.kkAffinity) return;
  try {
    if (localStorage.getItem("kk_cookie_consent") === "declined") return;
    var recent = JSON.parse(localStorage.getItem("kk_recent") || "[]");
    if (!recent.length) return;
    var latest = recent[0];
    var MARKER_KEY = "kk_affinity_last_slug";
    if (latest.slug && latest.slug !== localStorage.getItem(MARKER_KEY)) {
      window.kkAffinity.recordEntry(latest, 1);
      localStorage.setItem(MARKER_KEY, latest.slug);
    }
  } catch (e) {}
})();

(function () {
  // Honest, real personalization: reorders this visitor's own homepage
  // category sections based on their own local affinity tally (kk_affinity,
  // built from views + likes, saved to their browser only). Never leaves
  // the browser, never touches the scraper/server side.
  var wrap = document.getElementById("personalized-sections");
  if (!wrap || !window.kkAffinity) return;
  try {
    if (localStorage.getItem("kk_cookie_consent") === "declined") return;
    var catCounts = (window.kkAffinity.get().cats) || {};
    if (!Object.keys(catCounts).length) return;
    var sections = Array.from(wrap.querySelectorAll(".cat-section-wrap"));
    if (sections.length < 2) return;
    sections.sort(function (a, b) {
      var ac = catCounts[a.getAttribute("data-category")] || 0;
      var bc = catCounts[b.getAttribute("data-category")] || 0;
      return bc - ac;
    });
    var hasPreference = sections.some(function (s) {
      return (catCounts[s.getAttribute("data-category")] || 0) > 0;
    });
    if (hasPreference) {
      sections.forEach(function (s) { wrap.appendChild(s); });
    }
  } catch (e) {}
})();

(function () {
  // Same idea, one level finer: within any card grid on the site (a
  // category section, a full category-listing page, etc), nudge cards from
  // sources/content-types this visitor tends to engage with towards the
  // front - without touching grids where there's no real preference signal,
  // so browsing stays in normal chronological order by default.
  if (!window.kkAffinity) return;
  try {
    if (localStorage.getItem("kk_cookie_consent") === "declined") return;
    var affinity = window.kkAffinity.get();
    var sourceScores = affinity.sources || {};
    var typeScores = affinity.types || {};
    if (!Object.keys(sourceScores).length && !Object.keys(typeScores).length) return;

    function scoreOf(card) {
      var src = card.getAttribute("data-source") || "";
      var type = card.getAttribute("data-type") || "";
      return (sourceScores[src] || 0) + (typeScores[type] || 0);
    }

    document.querySelectorAll(".grid-inner").forEach(function (grid) {
      var cards = Array.prototype.filter.call(grid.children, function (el) {
        return el.classList.contains("card");
      });
      if (cards.length < 2) return;
      var withScores = cards.map(function (c, i) { return { el: c, score: scoreOf(c), i: i }; });
      var hasPreference = withScores.some(function (w) { return w.score > 0; });
      if (!hasPreference) return;
      withScores.sort(function (a, b) {
        if (b.score !== a.score) return b.score - a.score;
        return a.i - b.i; // stable: keep original (chronological) order among ties
      });
      withScores.forEach(function (w) { grid.appendChild(w.el); });
    });
  } catch (e) {}
})();
