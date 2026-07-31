(function () {
  // Owner directive: the site closes 10 minutes before Shabbat (real
  // sunset-based candle-lighting time from Hebcal, computed at build time
  // in build_site.py - never approximated here) and reopens at Shabbat's
  // end. Runs first, before anything else, so a visitor who loads the
  // page already inside the closed window sees the lockout immediately
  // rather than a flash of the real site first.
  var overlay = document.getElementById("shabbat-lockout");
  var warning = document.getElementById("shabbat-warning");
  if (!overlay) return;

  var closeTime = new Date(overlay.getAttribute("data-close")).getTime();
  var reopenTime = new Date(overlay.getAttribute("data-reopen")).getTime();
  if (isNaN(closeTime) || isNaN(reopenTime)) return;

  var WARNING_LEAD_MS = 15 * 60 * 1000;
  var warningInterval = null;

  function pad(n) { return n < 10 ? "0" + n : "" + n; }

  function showLockout() {
    if (warningInterval) { clearInterval(warningInterval); warningInterval = null; }
    if (warning) warning.hidden = true;
    var reopenDate = new Date(reopenTime);
    var reopenTextEl = document.getElementById("shabbat-reopen-text");
    if (reopenTextEl) {
      reopenTextEl.textContent = "האתר ייפתח שוב במוצאי שבת בשעה " +
        pad(reopenDate.getHours()) + ":" + pad(reopenDate.getMinutes());
    }
    overlay.hidden = false;
    document.documentElement.style.overflow = "hidden";
  }

  function showWarning() {
    if (!warning) return;
    function updateText() {
      var minutesLeft = Math.max(0, Math.ceil((closeTime - Date.now()) / 60000));
      var textEl = document.getElementById("shabbat-warning-text");
      if (textEl) textEl.textContent = "לתשומת ליבכם: האתר ייסגר בעוד " + minutesLeft + " דקות לקראת כניסת שבת";
    }
    updateText();
    warning.hidden = false;
    warningInterval = setInterval(updateText, 30000);
  }

  function tick() {
    var now = Date.now();
    if (now >= closeTime && now < reopenTime) {
      showLockout();
      return;
    }
    if (now >= reopenTime) return; // Shabbat already over this week
    var msUntilClose = closeTime - now;
    if (msUntilClose <= WARNING_LEAD_MS) {
      showWarning();
    } else {
      setTimeout(showWarning, msUntilClose - WARNING_LEAD_MS);
    }
    setTimeout(showLockout, msUntilClose);
  }

  tick();
})();

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
  // Two header drawers (search, categories) - sharing one open/close
  // helper so opening either one closes the other, instead of both being
  // open and stacked at once. The bottom tab bar's own buttons drive these
  // same toggles rather than duplicating the logic.
  const panels = [
    { toggle: document.getElementById("search-toggle"), drawer: document.getElementById("search-drawer"), focusId: "search-drawer-input" },
    { toggle: document.getElementById("categories-toggle"), drawer: document.getElementById("categories-drawer"), focusId: null },
  ].filter(function (p) { return p.toggle && p.drawer; });

  function closeAll(except) {
    panels.forEach(function (p) {
      if (p === except) return;
      p.drawer.classList.remove("open");
      p.toggle.setAttribute("aria-expanded", "false");
    });
  }

  panels.forEach(function (p) {
    function isOpen() { return p.drawer.classList.contains("open"); }
    function open() {
      closeAll(p);
      p.drawer.classList.add("open");
      p.toggle.setAttribute("aria-expanded", "true");
      if (p.focusId) {
        const input = document.getElementById(p.focusId);
        if (input) input.focus();
      }
    }
    function close() {
      p.drawer.classList.remove("open");
      p.toggle.setAttribute("aria-expanded", "false");
    }
    p.toggle.addEventListener("click", function (e) {
      e.stopPropagation();
      if (isOpen()) close(); else open();
    });
    p.open = open; // exposed so the tab bar buttons below can reuse it
  });

  document.addEventListener("click", function (e) {
    panels.forEach(function (p) {
      if (p.drawer.classList.contains("open") && !p.drawer.contains(e.target) && e.target !== p.toggle && !p.toggle.contains(e.target)) {
        p.drawer.classList.remove("open");
        p.toggle.setAttribute("aria-expanded", "false");
      }
    });
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeAll(null);
  });

  const tabSearch = document.getElementById("tab-search-toggle");
  const tabCategories = document.getElementById("tab-categories-toggle");
  const searchPanel = panels.filter(function (p) { return p.toggle.id === "search-toggle"; })[0];
  const categoriesPanel = panels.filter(function (p) { return p.toggle.id === "categories-toggle"; })[0];
  if (tabSearch && searchPanel) tabSearch.addEventListener("click", function (e) { e.stopPropagation(); searchPanel.open(); });
  if (tabCategories && categoriesPanel) tabCategories.addEventListener("click", function (e) { e.stopPropagation(); categoriesPanel.open(); });
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
  var select = document.getElementById("sort-select");
  var grid = document.getElementById("category-grid");
  if (!select || !grid) return;

  var originalOrder = Array.from(grid.children);

  select.addEventListener("change", function () {
    var order = select.value === "oldest" ? originalOrder.slice().reverse() : originalOrder;
    order.forEach(function (el) { grid.appendChild(el); });
  });
})();

// Infinite scroll, shared by category-listing pages AND an article page's
// "related articles" section (owner directive: a related-articles section
// that visibly ends is exactly the moment a reader leaves - so it never
// visibly runs out within a normal session, same underlying mechanism
// either way). The static HTML already has the first batch; further ones
// come from the site's existing search-index.json (already generated for
// search - reused here instead of building separate pagination files),
// fetched only once the visitor actually scrolls near the bottom.
function setupInfiniteGrid(grid, sentinel, excludeSlug) {
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
              .filter(function (a) { return a.category === category && a.slug !== excludeSlug; })
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
}

setupInfiniteGrid(document.getElementById("category-grid"), document.getElementById("load-more-sentinel"));
(function () {
  var grid = document.getElementById("related-grid");
  if (!grid) return;
  setupInfiniteGrid(grid, document.getElementById("related-load-more-sentinel"), grid.getAttribute("data-exclude-slug"));
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
    // Older saved data was a plain array of slugs (no metadata) - normalize
    // so the "הכתבות שאהבתי" page always has real objects to work with,
    // without silently dropping anything a returning visitor already liked
    liked = liked.map(function (item) {
      return typeof item === "string" ? { slug: item } : item;
    });
    function findLikedIndex() {
      for (var i = 0; i < liked.length; i++) {
        if (liked[i].slug === slug) return i;
      }
      return -1;
    }

    var isLiked = findLikedIndex() !== -1;
    if (isLiked) {
      likeBtn.classList.add("liked");
      likeBtn.setAttribute("aria-pressed", "true");
      likeBtn.querySelector("#like-count").textContent = "אהבתי!";
    }
    likeBtn.addEventListener("click", function () {
      var idx = findLikedIndex();
      if (idx === -1) {
        liked.push({
          slug: slug,
          title: bar.getAttribute("data-title"),
          img: bar.getAttribute("data-img"),
          cat: likeEntry.cat,
          source: likeEntry.source,
          date: bar.getAttribute("data-date")
        });
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
    // mobile with a native share sheet: use it directly, no menu needed.
    // everywhere else (most desktop browsers don't implement
    // navigator.share): a small menu with WhatsApp/email/Facebook instead
    // of silently falling back to clipboard-copy only.
    var shareMenu = null;
    function buildShareMenu() {
      var title = shareBtn.getAttribute("data-title");
      var url = shareBtn.getAttribute("data-url");
      var menu = document.createElement("div");
      menu.className = "share-menu";
      menu.hidden = true;

      var items = [
        {
          label: "וואטסאפ",
          href: "https://wa.me/?text=" + encodeURIComponent(title + " " + url),
        },
        {
          label: "אימייל",
          href: "mailto:?subject=" + encodeURIComponent(title) + "&body=" + encodeURIComponent(url),
        },
        {
          label: "פייסבוק",
          href: "https://www.facebook.com/sharer/sharer.php?u=" + encodeURIComponent(url),
        },
      ];
      items.forEach(function (item) {
        var a = document.createElement("a");
        a.className = "share-menu-item";
        a.href = item.href;
        a.target = "_blank";
        a.rel = "noopener";
        a.textContent = item.label;
        menu.appendChild(a);
      });

      var copyBtn = document.createElement("button");
      copyBtn.type = "button";
      copyBtn.className = "share-menu-item";
      copyBtn.textContent = "העתקת קישור";
      copyBtn.addEventListener("click", function () {
        if (navigator.clipboard) {
          navigator.clipboard.writeText(url).then(function () {
            copyBtn.textContent = "הועתק!";
            setTimeout(function () { copyBtn.textContent = "העתקת קישור"; }, 1800);
          });
        }
      });
      menu.appendChild(copyBtn);

      // wrap the button so the menu (a sibling, not a child - a <button>
      // can't validly contain nested <a>/<button> elements) has a
      // position:relative ancestor to anchor to, instead of drifting to
      // whatever the nearest positioned ancestor further up happens to be
      var wrap = document.createElement("div");
      wrap.className = "share-wrap";
      shareBtn.parentNode.insertBefore(wrap, shareBtn);
      wrap.appendChild(shareBtn);
      wrap.appendChild(menu);
      return menu;
    }

    document.addEventListener("click", function (e) {
      if (shareMenu && !shareMenu.hidden && e.target !== shareBtn && !shareBtn.contains(e.target) && !shareMenu.contains(e.target)) {
        shareMenu.hidden = true;
      }
    });

    shareBtn.addEventListener("click", function () {
      var title = shareBtn.getAttribute("data-title");
      var url = shareBtn.getAttribute("data-url");
      if (navigator.share) {
        navigator.share({ title: title, url: url }).catch(function () {});
        return;
      }
      if (!shareMenu) shareMenu = buildShareMenu();
      shareMenu.hidden = !shareMenu.hidden;
    });
  }
})();

(function () {
  // Real YouTube IFrame Player API (not a raw unmanaged iframe) - needed to
  // track playback position so we can cover YouTube's own end-of-video
  // suggestions grid with our own branded replay screen a moment before it
  // would appear, instead of it interrupting into other channels' videos.
  // rel=0/modestbranding=1/iv_load_policy=3 are YouTube's own documented,
  // legitimate embed parameters (not a hack) - this doesn't hide or modify
  // required YouTube attribution during actual playback, it only keeps
  // chrome minimal and takes over at the very end, which is standard
  // practice for embedded video on publisher sites.
  var player = document.querySelector(".kk-player");
  if (!player) return;
  var playBtn = player.querySelector(".kk-player-play");
  var poster = player.querySelector(".kk-player-poster");
  var endCard = player.querySelector(".kk-player-endcard");
  var replayBtn = player.querySelector(".kk-player-replay");
  var videoId = player.getAttribute("data-video-id");
  var ytPlayer = null;
  var watchTimer = null;

  function stopWatching() {
    if (watchTimer) {
      clearInterval(watchTimer);
      watchTimer = null;
    }
  }

  function showEndCard() {
    stopWatching();
    if (endCard) endCard.hidden = false;
  }

  function startWatching() {
    stopWatching();
    watchTimer = setInterval(function () {
      if (!ytPlayer || typeof ytPlayer.getDuration !== "function") return;
      var duration = ytPlayer.getDuration();
      var current = ytPlayer.getCurrentTime();
      if (duration > 0 && duration - current <= 1) showEndCard();
    }, 250);
  }

  function createPlayer() {
    var frameHost = document.createElement("div");
    frameHost.className = "kk-player-frame";
    var frameId = "kk-yt-" + videoId + "-" + Math.floor(Math.random() * 1e6);
    frameHost.id = frameId;
    player.insertBefore(frameHost, endCard);

    ytPlayer = new YT.Player(frameId, {
      videoId: videoId,
      host: "https://www.youtube-nocookie.com",
      playerVars: { autoplay: 1, rel: 0, modestbranding: 1, iv_load_policy: 3 },
      events: {
        onStateChange: function (e) {
          if (e.data === YT.PlayerState.PLAYING) {
            if (endCard) endCard.hidden = true;
            startWatching();
          } else if (e.data === YT.PlayerState.ENDED) {
            showEndCard();
          } else if (e.data === YT.PlayerState.PAUSED) {
            stopWatching();
          }
        }
      }
    });
  }

  function loadApiAndCreatePlayer() {
    if (window.YT && window.YT.Player) {
      createPlayer();
      return;
    }
    var previous = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = function () {
      if (typeof previous === "function") previous();
      createPlayer();
    };
    if (!document.getElementById("youtube-iframe-api")) {
      var tag = document.createElement("script");
      tag.id = "youtube-iframe-api";
      tag.src = "https://www.youtube.com/iframe_api";
      document.head.appendChild(tag);
    }
  }

  // guards against a second overlapping player even if the poster's
  // hidden state is ever wrong for some other unforeseen reason - the
  // CSS fix above should already prevent a re-click, this is a second,
  // independent line of defense against ever creating two YT.Player
  // instances in the same container (the actual symptom reported: video
  // "running twice")
  var started = false;
  playBtn.addEventListener("click", function () {
    if (started) return;
    started = true;
    if (poster) poster.hidden = true;
    loadApiAndCreatePlayer();
  });

  if (replayBtn) {
    replayBtn.addEventListener("click", function () {
      endCard.hidden = true;
      if (ytPlayer && typeof ytPlayer.seekTo === "function") {
        ytPlayer.seekTo(0);
        ytPlayer.playVideo();
      }
    });
  }
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
  // side-rail ad backgrounds are only ever shown at >=1500px viewport width
  // (see .side-rail's media query in style.css) - loading them via a plain
  // CSS background-image would still cost every visitor the download even
  // when the element is display:none, so the URL is deferred here and only
  // ever applied once the same width condition actually matches
  var wideViewport = window.matchMedia("(min-width: 1500px)");
  function applyLazyAdBackgrounds() {
    if (!wideViewport.matches) return;
    document.querySelectorAll(".ad-slot-bg[data-bg-lazy]").forEach(function (el) {
      el.style.backgroundImage = "url('" + el.getAttribute("data-bg-lazy") + "')";
      el.removeAttribute("data-bg-lazy");
    });
  }
  applyLazyAdBackgrounds();
  wideViewport.addEventListener("change", applyLazyAdBackgrounds);
})();

(function () {
  // ad-slot rotation - same crossfade technique as the hero carousel just
  // above, just slower (ads carry more text to actually read than a
  // headline) and independently instantiated per slot, since a page can
  // have several (between category sections, inside articles, side rails)
  var ROTATE_MS = 6000;
  document.querySelectorAll(".ad-slot").forEach(function (slot) {
    var slides = slot.querySelectorAll(".ad-slide");
    if (slides.length < 2) return;
    var current = 0;
    Array.prototype.forEach.call(slides, function (s, i) {
      if (s.classList.contains("active")) current = i;
    });
    var timer = null;
    function showSlide(index) {
      Array.prototype.forEach.call(slides, function (s, i) { s.classList.toggle("active", i === index); });
      current = index;
    }
    function start() {
      timer = setInterval(function () { showSlide((current + 1) % slides.length); }, ROTATE_MS);
    }
    function stop() {
      if (timer) clearInterval(timer);
      timer = null;
    }
    slot.addEventListener("mouseenter", stop);
    slot.addEventListener("mouseleave", start);
    start();
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

(function () {
  // Advertise-page wizard: one step visible at a time, "הבא"/"הקודם" swap
  // which .ad-wizard-step carries the .active class rather than the form
  // growing into one long scroll. All steps' fields stay in the same real
  // <form> the whole time (just hidden), so the final submit still sends
  // every field together - the generic Formspree-AJAX handler below picks
  // up the actual submit event with no changes needed.
  document.querySelectorAll(".ad-wizard-form").forEach(function (form) {
    var steps = Array.prototype.slice.call(form.querySelectorAll(".ad-wizard-step"));
    var card = form.closest(".ad-wizard-card");
    var dots = card ? Array.prototype.slice.call(card.querySelectorAll(".ad-wizard-dot")) : [];
    var current = 0;

    function showStep(index) {
      steps.forEach(function (s, i) { s.classList.toggle("active", i === index); });
      dots.forEach(function (d, i) {
        d.classList.toggle("active", i === index);
        d.classList.toggle("done", i < index);
      });
      var firstField = steps[index].querySelector("input, textarea");
      if (firstField) firstField.focus();
      current = index;
    }

    function currentStepValid() {
      var fields = steps[current].querySelectorAll("input, textarea");
      for (var i = 0; i < fields.length; i++) {
        if (!fields[i].checkValidity()) {
          fields[i].reportValidity();
          return false;
        }
      }
      return true;
    }

    form.querySelectorAll(".ad-wizard-next").forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (currentStepValid() && current < steps.length - 1) showStep(current + 1);
      });
    });
    form.querySelectorAll(".ad-wizard-back").forEach(function (btn) {
      btn.addEventListener("click", function () {
        if (current > 0) showStep(current - 1);
      });
    });
    // Enter key inside a step field should advance to the next step instead
    // of silently submitting the whole (partially-hidden) form early
    form.addEventListener("keydown", function (e) {
      if (e.key !== "Enter" || e.target.tagName === "TEXTAREA") return;
      if (current < steps.length - 1) {
        e.preventDefault();
        if (currentStepValid()) showStep(current + 1);
      }
    });
  });
})();

(function () {
  // Formspree forms (report/tip-line/advertise contact) default to a full
  // page navigation to Formspree's own thank-you page on submit. Accept:
  // application/json tells Formspree to respond with JSON instead of
  // redirecting, so the submission can stay on the same page - the form
  // is replaced in place with a short thank-you message instead of
  // navigating away (per Formspree's own documented AJAX pattern:
  // https://help.formspree.io/hc/en-us/articles/360013470814).
  var forms = document.querySelectorAll(".contact-form, .report-form");
  forms.forEach(function (form) {
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var submitBtn = form.querySelector("button[type=submit]");
      var originalLabel = submitBtn ? submitBtn.textContent : "";
      if (submitBtn) {
        submitBtn.disabled = true;
        submitBtn.textContent = "שולח...";
      }
      var existingError = form.querySelector(".form-error-msg");
      if (existingError) existingError.remove();

      fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        headers: { Accept: "application/json" },
      }).then(function (response) {
        if (response.ok) {
          var thanks = document.createElement("div");
          thanks.className = "form-thanks";
          thanks.innerHTML = "<strong>תודה!</strong><span>הפנייה נשלחה בהצלחה, נחזור אליכם בהקדם.</span>";
          form.replaceWith(thanks);
        } else {
          throw new Error("submit failed");
        }
      }).catch(function () {
        if (submitBtn) {
          submitBtn.disabled = false;
          submitBtn.textContent = originalLabel;
        }
        var errorMsg = document.createElement("p");
        errorMsg.className = "form-error-msg";
        errorMsg.textContent = "משהו השתבש - אפשר לנסות שוב?";
        form.appendChild(errorMsg);
      });
    });
  });
})();
