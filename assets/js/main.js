/* main.js - shared site behavior: theme, sidebar, contact widget, footer accordion, price calculator.
   Loaded on every page. Assistant logic lives in assets/js/assistant.js and is only loaded
   on pages that use it. All business facts must come from config/business-facts.json. */

(function () {
  'use strict';

  /* ---------- Theme toggle ---------- */
  var themeToggleBtn = document.getElementById('theme-toggle');
  var themeIcon = document.getElementById('theme-icon');
  var html = document.documentElement;

  function applyThemeIcon() {
    if (!themeIcon) return;
    var dark = html.classList.contains('dark');
    themeIcon.classList.toggle('fa-sun', !dark);
    themeIcon.classList.toggle('fa-moon', dark);
  }

  if (localStorage.theme === 'dark' ||
      (!('theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
    html.classList.add('dark');
  } else {
    html.classList.remove('dark');
  }
  applyThemeIcon();

  if (themeToggleBtn) {
    themeToggleBtn.addEventListener('click', function () {
      html.classList.toggle('dark');
      localStorage.theme = html.classList.contains('dark') ? 'dark' : 'light';
      applyThemeIcon();
    });
  }

  /* ---------- Sidebar ---------- */
  var menuBtn = document.getElementById('menu-btn');
  var closeMenuBtn = document.getElementById('close-menu-btn');
  var sidebar = document.getElementById('sidebar-menu');
  var overlay = document.getElementById('sidebar-overlay');

  function openSidebar() {
    sidebar.classList.remove('translate-x-full');
    sidebar.setAttribute('aria-hidden', 'false');
    overlay.classList.remove('hidden');
    requestAnimationFrame(function () { overlay.classList.add('opacity-100'); });
    menuBtn.setAttribute('aria-expanded', 'true');
    document.body.style.overflow = 'hidden';
    if (closeMenuBtn) closeMenuBtn.focus();
  }

  function closeSidebar() {
    sidebar.classList.add('translate-x-full');
    sidebar.setAttribute('aria-hidden', 'true');
    overlay.classList.remove('opacity-100');
    setTimeout(function () { overlay.classList.add('hidden'); }, 300);
    menuBtn.setAttribute('aria-expanded', 'false');
    document.body.style.overflow = '';
    if (menuBtn) menuBtn.focus();
  }

  if (menuBtn && sidebar && overlay) {
    menuBtn.addEventListener('click', openSidebar);
    if (closeMenuBtn) closeMenuBtn.addEventListener('click', closeSidebar);
    overlay.addEventListener('click', closeSidebar);
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !sidebar.classList.contains('translate-x-full')) closeSidebar();
    });
  }

  /* ---------- Price calculator (index, banggia, duration pages) ---------- */
  var bikeBtns = document.querySelectorAll('.bike-select-btn');
  var priceInput = document.getElementById('bike-price');
  var daysInput = document.getElementById('days');
  var totalPriceEl = document.getElementById('total-price');

  function calculateTotal() {
    if (!priceInput || !daysInput || !totalPriceEl) return;
    var price = parseInt(priceInput.value, 10) || 0;
    var days = parseInt(daysInput.value, 10) || 1;
    var total = price * days;
    if (days >= 7) total = total * 0.9; // weekly+ discount as published on site
    totalPriceEl.textContent = new Intl.NumberFormat('vi-VN', {
      style: 'currency', currency: 'VND', maximumFractionDigits: 0
    }).format(Math.round(total));
  }

  if (priceInput && daysInput && totalPriceEl) {
    bikeBtns.forEach(function (btn) {
      btn.addEventListener('click', function () {
        bikeBtns.forEach(function (b) {
          b.classList.remove('active', 'ring-2', 'ring-brand-500', 'bg-brand-50/70', 'dark:bg-gray-700/70');
          b.classList.add('bg-white/50', 'dark:bg-gray-800/50', 'border-white/20');
        });
        btn.classList.add('active', 'ring-2', 'ring-brand-500', 'bg-brand-50/70', 'dark:bg-gray-700/70');
        btn.classList.remove('bg-white/50', 'dark:bg-gray-800/50', 'border-white/20');
        priceInput.value = btn.getAttribute('data-value');
        calculateTotal();
      });
    });

    window.adjustDays = function (amount) {
      var d = parseInt(daysInput.value, 10) || 1;
      d += amount;
      if (d < 1) d = 1;
      if (d > 90) d = 90;
      daysInput.value = d;
      calculateTotal();
    };

    daysInput.addEventListener('change', function () {
      var d = parseInt(daysInput.value, 10) || 1;
      if (d < 1) d = 1;
      if (d > 90) d = 90;
      daysInput.value = d;
      calculateTotal();
    });

    calculateTotal();
  }

  /* ---------- Quick contact widget ---------- */
  var widgetContainer = document.getElementById('quick-contact-widget');
  var mainContactBtn = document.getElementById('main-contact-btn');
  var contactIcon = document.getElementById('contact-icon');

  if (widgetContainer && mainContactBtn && contactIcon) {
    var shakeTimer = null;

    function triggerShake() {
      mainContactBtn.classList.add('animate-ring-shake');
      if (navigator.vibrate) navigator.vibrate([10, 30, 10]);
      setTimeout(function () { mainContactBtn.classList.remove('animate-ring-shake'); }, 1200);
    }
    function startShakeInterval() {
      stopShakeInterval();
      shakeTimer = setInterval(triggerShake, 5000);
    }
    function stopShakeInterval() {
      if (shakeTimer) { clearInterval(shakeTimer); shakeTimer = null; }
      mainContactBtn.classList.remove('animate-ring-shake');
    }

    function setWidget(open) {
      widgetContainer.classList.toggle('active', open);
      contactIcon.classList.toggle('fa-times', open);
      contactIcon.classList.toggle('rotate-90', open);
      contactIcon.classList.toggle('fa-phone-volume', !open);
      mainContactBtn.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (open) { stopShakeInterval(); } else { startShakeInterval(); }
    }

    mainContactBtn.addEventListener('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      if (navigator.vibrate) navigator.vibrate(50);
      setWidget(!widgetContainer.classList.contains('active'));
    });

    setTimeout(function () { startShakeInterval(); triggerShake(); }, 2000);

    document.addEventListener('click', function (e) {
      if (!widgetContainer.contains(e.target) && widgetContainer.classList.contains('active')) {
        setWidget(false);
      }
    });
  }

  /* ---------- Footer accordion (mobile) ---------- */
  var footerHeadings = document.querySelectorAll('.footer-heading');
  footerHeadings.forEach(function (heading) {
    heading.addEventListener('click', function () {
      if (window.innerWidth >= 768) return;
      var content = heading.nextElementSibling;
      var chevron = heading.querySelector('.footer-chevron');
      footerHeadings.forEach(function (other) {
        if (other !== heading) {
          var c = other.nextElementSibling;
          var ch = other.querySelector('.footer-chevron');
          if (c) c.style.maxHeight = null;
          if (ch) ch.style.transform = 'rotate(0deg)';
        }
      });
      if (content.style.maxHeight) {
        content.style.maxHeight = null;
        if (chevron) chevron.style.transform = 'rotate(0deg)';
      } else {
        content.style.maxHeight = content.scrollHeight + 'px';
        if (chevron) chevron.style.transform = 'rotate(180deg)';
      }
    });
  });
})();
