/* article.js - tiny vanilla enhancements for the generated article shell.
 * Progressive enhancement only; the page is fully usable without JS:
 *  - TOC scroll-spy (aria-current on the visible section link)
 *  - reading progress bar (skipped when prefers-reduced-motion)
 *  - desktop heading anchor links
 * No frameworks, no network calls, no DOM restructuring.
 */
(function () {
  'use strict';
  var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* Reading progress bar */
  var bar = document.getElementById('reading-progress');
  if (bar && !reduceMotion) {
    var ticking = false;
    var update = function () {
      ticking = false;
      var h = document.documentElement;
      var max = h.scrollHeight - h.clientHeight;
      var pct = max > 0 ? Math.min(100, Math.max(0, (h.scrollTop / max) * 100)) : 0;
      bar.style.width = pct.toFixed(2) + '%';
    };
    window.addEventListener('scroll', function () {
      if (!ticking) { ticking = true; window.requestAnimationFrame(update); }
    }, { passive: true });
    update();
  }

  /* Heading anchor links (fine pointers only, keeps mobile clean) */
  var fine = window.matchMedia && window.matchMedia('(hover: hover) and (pointer: fine)').matches;
  var prose = document.querySelector('.article-prose');
  if (fine && prose) {
    var headings = prose.querySelectorAll('h2[id], h3[id]');
    headings.forEach(function (h) {
      if (h.querySelector('.heading-anchor')) return;
      var a = document.createElement('a');
      a.className = 'heading-anchor';
      a.href = '#' + h.id;
      a.setAttribute('aria-label', 'Lien ket toi muc nay');
      a.innerHTML = '&#35;';
      a.addEventListener('click', function (e) {
        e.preventDefault();
        h.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth' });
        history.replaceState(null, '', '#' + h.id);
      });
      h.appendChild(a);
    });
  }

  /* TOC scroll-spy: highlight the section currently in view */
  var tocLinks = Array.prototype.slice.call(document.querySelectorAll('.toc-list a[href^="#"]'));
  if (tocLinks.length && 'IntersectionObserver' in window) {
    var byId = {};
    tocLinks.forEach(function (a) { byId[a.getAttribute('href').slice(1)] = a; });
    var targets = Object.keys(byId)
      .map(function (id) { return document.getElementById(id); })
      .filter(Boolean);
    var setActive = function (id) {
      tocLinks.forEach(function (a) {
        if (a.getAttribute('href') === '#' + id) { a.setAttribute('aria-current', 'true'); }
        else { a.removeAttribute('aria-current'); }
      });
    };
    var visible = null;
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { visible = en.target.id; }
      });
      if (visible) { setActive(visible); }
    }, { rootMargin: '-15% 0px -70% 0px', threshold: 0 });
    targets.forEach(function (t) { io.observe(t); });
  }
})();
