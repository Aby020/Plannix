/* ============================================================
   Plannix — main.js (vanilla JS)
   Scroll reveal · navbar · back-to-top · toasts · counters ·
   dashboard sidebar · confirm helper
   ============================================================ */
(function () {
  "use strict";

  var prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- Scroll reveal ---------- */
  function initReveal() {
    var revealEls = document.querySelectorAll(".reveal, .reveal-stagger");
    if (!revealEls.length) return;

    if (prefersReduced || !("IntersectionObserver" in window)) {
      revealEls.forEach(function (el) { el.classList.add("reveal-visible"); });
      return;
    }

    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            entry.target.classList.add("reveal-visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12, rootMargin: "0px 0px -40px 0px" }
    );

    revealEls.forEach(function (el) { observer.observe(el); });
  }

  /* ---------- Navbar scroll state ---------- */
  function initNavbar() {
    var navbar = document.querySelector(".px-navbar");
    if (!navbar) return;

    function onScroll() {
      navbar.classList.toggle("is-scrolled", window.scrollY > 24);
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  /* ---------- Back to top ---------- */
  function initBackToTop() {
    var btn = document.querySelector(".back-to-top");
    if (!btn) return;

    function onScroll() {
      btn.classList.toggle("show", window.scrollY > 400);
    }
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();

    btn.addEventListener("click", function () {
      window.scrollTo({ top: 0, behavior: prefersReduced ? "auto" : "smooth" });
    });
  }

  /* ---------- Toast system ---------- */
  var toastContainer = null;

  function ensureToastContainer() {
    if (!toastContainer) {
      toastContainer = document.createElement("div");
      toastContainer.className = "px-toasts";
      toastContainer.setAttribute("aria-live", "polite");
      document.body.appendChild(toastContainer);
    }
    return toastContainer;
  }

  function showToast(message, type) {
    type = type || "info";
    var container = ensureToastContainer();

    var toast = document.createElement("div");
    toast.className = "px-toast toast-" + type;
    toast.setAttribute("role", "status");

    var icons = { success: "check-circle", error: "x-circle", warning: "alert-triangle", info: "info-circle" };
    var icon = icons[type] || icons.info;

    toast.innerHTML =
      '<span class="toast-icon"><i class="bi bi-' + icon + '"></i></span>' +
      "<span>" + escapeHtml(message) + "</span>";

    container.appendChild(toast);

    setTimeout(function () {
      toast.classList.add("hide");
      toast.addEventListener("animationend", function () { toast.remove(); }, { once: true });
    }, 4200);
  }

  function escapeHtml(str) {
    var div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  /* Auto-render Django messages via window.PLANNIX_MESSAGES (set by base templates) */
  function initDjangoMessages() {
    if (!window.PLANNIX_MESSAGES || !window.PLANNIX_MESSAGES.length) return;
    window.PLANNIX_MESSAGES.forEach(function (m) { showToast(m.text, m.type); });
  }

  /* ---------- Animated counters ---------- */
  function initCounters() {
    var counters = document.querySelectorAll("[data-counter]");
    if (!counters.length) return;

    function animate(el) {
      var target = parseFloat(el.getAttribute("data-counter"));
      var suffix = el.getAttribute("data-suffix") || "";
      var duration = 1400;
      var start = null;

      function step(ts) {
        if (!start) start = ts;
        var progress = Math.min((ts - start) / duration, 1);
        // easeOutCubic
        progress = 1 - Math.pow(1 - progress, 3);
        var value = Math.round(target * progress);
        el.textContent = value.toLocaleString() + suffix;
        if (progress < 1) requestAnimationFrame(step);
        else el.textContent = target.toLocaleString() + suffix;
      }
      requestAnimationFrame(step);
    }

    if (prefersReduced || !("IntersectionObserver" in window)) {
      counters.forEach(function (el) {
        el.textContent = parseFloat(el.getAttribute("data-counter")).toLocaleString() + (el.getAttribute("data-suffix") || "");
      });
      return;
    }

    var observer = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (entry.isIntersecting) {
            animate(entry.target);
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.5 }
    );
    counters.forEach(function (el) { observer.observe(el); });
  }

  /* ---------- Dashboard sidebar ---------- */
  function initSidebar() {
    var toggle = document.querySelector(".sidebar-toggle");
    var sidebar = document.querySelector(".px-sidebar");
    var overlay = document.querySelector(".px-sidebar-overlay");
    if (!toggle || !sidebar) return;

    function open() {
      sidebar.classList.add("open");
      if (overlay) overlay.classList.add("show");
      document.body.style.overflow = "hidden";
    }
    function close() {
      sidebar.classList.remove("open");
      if (overlay) overlay.classList.remove("show");
      document.body.style.overflow = "";
    }

    toggle.addEventListener("click", function () {
      sidebar.classList.contains("open") ? close() : open();
    });
    if (overlay) overlay.addEventListener("click", close);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") close();
    });
  }

  /* ---------- Confirm helper (for destructive actions) ---------- */
  function initConfirmLinks() {
    document.querySelectorAll("[data-confirm]").forEach(function (link) {
      link.addEventListener("click", function (e) {
        var msg = link.getAttribute("data-confirm") || "Are you sure you want to do this?";
        if (!window.confirm(msg)) {
          e.preventDefault();
          e.stopPropagation();
        }
      });
    });
  }

  /* ---------- Autofocus first invalid field on form submit ---------- */
  function initFormFocus() {
    document.querySelectorAll("form").forEach(function (form) {
      form.addEventListener("submit", function () {
        var invalid = form.querySelector(".is-invalid");
        if (invalid) invalid.focus();
      });
    });
  }

  /* ---------- Highlight active nav link by URL ---------- */
  function initActiveNav() {
    var path = window.location.pathname;
    document.querySelectorAll(".px-navbar .nav-link, .px-sidebar .nav-link").forEach(function (link) {
      var href = link.getAttribute("href");
      if (!href || href === "#") return;
      if (path === href || (href !== "/" && path.startsWith(href))) {
        link.classList.add("active");
      }
    });
  }

  /* ---------- Init ---------- */
  document.addEventListener("DOMContentLoaded", function () {
    initReveal();
    initNavbar();
    initBackToTop();
    initDjangoMessages();
    initCounters();
    initSidebar();
    initConfirmLinks();
    initFormFocus();
    initActiveNav();

    // Expose a small API for inline scripts (e.g. form handlers)
    window.Plannix = {
      toast: showToast,
      confirm: function (msg, onOk) {
        if (window.confirm(msg)) onOk();
      },
    };
  });
})();
