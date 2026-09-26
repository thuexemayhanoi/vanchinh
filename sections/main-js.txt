
       // Theme Toggle
       const themeToggleBtn = document.getElementById('theme-toggle');
       const themeIcon = document.getElementById('theme-icon');
       const html = document.documentElement;

       if (localStorage.theme === 'dark' || (!('theme' in localStorage) && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
           html.classList.add('dark');
           themeIcon.classList.remove('fa-sun');
           themeIcon.classList.add('fa-moon');
       } else {
           html.classList.remove('dark');
           themeIcon.classList.remove('fa-moon');
           themeIcon.classList.add('fa-sun');
       }

       themeToggleBtn.addEventListener('click', () => {
           html.classList.toggle('dark');
           if (html.classList.contains('dark')) {
               localStorage.theme = 'dark';
               themeIcon.classList.remove('fa-sun');
               themeIcon.classList.add('fa-moon');
           } else {
               localStorage.theme = 'light';
               themeIcon.classList.remove('fa-moon');
               themeIcon.classList.add('fa-sun');
           }
       });

       // Sidebar Logic
       const menuBtn = document.getElementById('menu-btn');
       const closeMenuBtn = document.getElementById('close-menu-btn');
       const sidebar = document.getElementById('sidebar-menu');
       const overlay = document.getElementById('sidebar-overlay');

       function openSidebar() {
           sidebar.classList.remove('translate-x-full');
           sidebar.setAttribute('aria-hidden', 'false');
           overlay.classList.remove('hidden');
           requestAnimationFrame(() => overlay.classList.add('opacity-100'));
           menuBtn.setAttribute('aria-expanded', 'true');
           document.body.style.overflow = 'hidden';
           closeMenuBtn.focus();
       }

       function closeSidebar() {
           sidebar.classList.add('translate-x-full');
           sidebar.setAttribute('aria-hidden', 'true');
           overlay.classList.remove('opacity-100');
           setTimeout(() => overlay.classList.add('hidden'), 300);
           menuBtn.setAttribute('aria-expanded', 'false');
           document.body.style.overflow = '';
           menuBtn.focus();
       }

       menuBtn.addEventListener('click', openSidebar);
       closeMenuBtn.addEventListener('click', closeSidebar);
       overlay.addEventListener('click', closeSidebar);

       // Calculator Logic
       const bikeBtns = document.querySelectorAll('.bike-select-btn');
       const priceInput = document.getElementById('bike-price');
       const daysInput = document.getElementById('days');
       const totalPriceEl = document.getElementById('total-price');

       bikeBtns.forEach(btn => {
           btn.addEventListener('click', () => {
               bikeBtns.forEach(b => {
                   b.classList.remove('active', 'ring-2', 'ring-brand-500', 'bg-brand-50/70', 'dark:bg-gray-700/70');
                   b.classList.add('bg-white/50', 'dark:bg-gray-800/50', 'border-white/20');
               });
               
               btn.classList.add('active', 'ring-2', 'ring-brand-500', 'bg-brand-50/70', 'dark:bg-gray-700/70');
               btn.classList.remove('bg-white/50', 'dark:bg-gray-800/50', 'border-white/20');

               const price = btn.getAttribute('data-value');
               priceInput.value = price;
               calculateTotal();
           });
       });

       function adjustDays(amount) {
           let currentDays = parseInt(daysInput.value, 10) || 1;
           let newDays = currentDays + amount;
           if (newDays < 1) newDays = 1;
           if (newDays > 90) newDays = 90;
           daysInput.value = newDays;
           calculateTotal();
       }

       daysInput.addEventListener('change', () => {
            let d = parseInt(daysInput.value, 10) || 1;
            if (d < 1) d = 1;
            if (d > 90) d = 90;
            daysInput.value = d;
            calculateTotal();
       });

       function calculateTotal() {
           const price = parseInt(priceInput.value, 10);
           const days = parseInt(daysInput.value, 10);
           let total = price * days;
           
           if (days >= 7) {
               total = total * 0.9;
           }
           totalPriceEl.textContent = new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND', maximumFractionDigits: 0 }).format(Math.round(total));
       }
       
       calculateTotal();

       // ULTRA QUICK CALL WIDGET LOGIC
       const widgetContainer = document.getElementById('quick-contact-widget');
       const mainContactBtn = document.getElementById('main-contact-btn');
       const contactIcon = document.getElementById('contact-icon');
       
       mainContactBtn.addEventListener('click', (e) => {
           e.stopPropagation();
           
           if (navigator.vibrate) {
               navigator.vibrate(50); 
           }

           const isActive = widgetContainer.classList.contains('active');
           
           if (isActive) {
               widgetContainer.classList.remove('active');
               contactIcon.classList.remove('fa-times', 'rotate-90');
               contactIcon.classList.add('fa-phone-volume');
               startShakeInterval();
           } else {
               widgetContainer.classList.add('active');
               contactIcon.classList.remove('fa-phone-volume');
               contactIcon.classList.add('fa-times', 'rotate-90');
               stopShakeInterval();
           }
       });

       let shakeInterval;
       function triggerShake() {
           mainContactBtn.classList.add('animate-ring-shake');
           if (navigator.vibrate) navigator.vibrate([10, 30, 10]);
           setTimeout(() => { mainContactBtn.classList.remove('animate-ring-shake'); }, 1200);
       }
       function startShakeInterval() { 
           clearInterval(shakeInterval);
           shakeInterval = setInterval(triggerShake, 5000); 
       }
       function stopShakeInterval() { 
           clearInterval(shakeInterval); 
           mainContactBtn.classList.remove('animate-ring-shake'); 
       }
       setTimeout(() => { startShakeInterval(); triggerShake(); }, 2000);
       document.addEventListener('click', (e) => {
           if (!widgetContainer.contains(e.target) && widgetContainer.classList.contains('active')) {
               widgetContainer.classList.remove('active');
               contactIcon.classList.remove('fa-times', 'rotate-90');
               contactIcon.classList.add('fa-phone-volume');
               startShakeInterval();
           }
       });

       // FOOTER ACCORDION LOGIC
       const footerHeadings = document.querySelectorAll('.footer-heading');
       
       footerHeadings.forEach(heading => {
           heading.addEventListener('click', () => {
               if (window.innerWidth >= 768) return;
               
               const content = heading.nextElementSibling;
               const chevron = heading.querySelector('.footer-chevron');
               
               footerHeadings.forEach(otherHeading => {
                   if (otherHeading !== heading) {
                       const otherContent = otherHeading.nextElementSibling;
                       const otherChevron = otherHeading.querySelector('.footer-chevron');
                       if (otherContent) {
                           otherContent.style.maxHeight = null;
                           if (otherChevron) otherChevron.style.transform = 'rotate(0deg)';
                       }
                   }
               });

               if (content.style.maxHeight) {
                   content.style.maxHeight = null;
                   chevron.style.transform = 'rotate(0deg)';
               } else {
                   content.style.maxHeight = content.scrollHeight + "px";
                   chevron.style.transform = 'rotate(180deg)';
               }
           });
       });

