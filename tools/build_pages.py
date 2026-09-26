#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_pages.py - deterministic static site page builder for vanchinh.

Generates all public HTML pages from shared components + per-page content.
GitHub Pages serves the committed static output; no build step is required at deploy time.
Run: python3 tools/build_pages.py   (from repo root)

Rules encoded here (see README.md / docs/):
- canonical base: https://thuexemayhanoi.github.io/vanchinh/
- opening hours: 09:00-17:00 daily (source of truth: config/business-facts.json)
- no unverified business claims (24/7, coc 0d, 15-min delivery, "so 1", ...)
- one H1 per page, unique title/description, self canonical, lang=vi
"""
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = "https://thuexemayhanoi.github.io/vanchinh/"
FACTS = json.loads((ROOT / "config" / "business-facts.json").read_text(encoding="utf-8"))
PHONE_TEL = FACTS["phone_tel"]
HOURS_DISPLAY = "9h - 17h"
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

def localbusiness_schema():
    return {
        "@context": "https://schema.org",
        "@type": "LocalBusiness",
        "name": FACTS["business_name"],
        "image": BASE + "IMG_0995.png",
        "@id": BASE,
        "url": BASE,
        "telephone": FACTS["phone_e164"],
        "address": {
            "@type": "PostalAddress",
            "streetAddress": "24 Ngõ 5 Nguyễn Văn Cừ, Ngọc Lâm",
            "addressLocality": "Long Biên",
            "addressRegion": "Hà Nội",
            "postalCode": "100000",
            "addressCountry": "VN",
        },
        "geo": {"@type": "GeoCoordinates",
                "latitude": FACTS["coordinates"]["latitude"],
                "longitude": FACTS["coordinates"]["longitude"]},
        "openingHoursSpecification": [{
            "@type": "OpeningHoursSpecification",
            "dayOfWeek": DAYS,
            "opens": FACTS["opening_hours"]["opens"],
            "closes": FACTS["opening_hours"]["closes"],
        }],
        "priceRange": "150000VND - 250000VND",
    }

# ---------------------------------------------------------------- claim fixes
def fix(text: str) -> str:
    """Apply repo-wide factual corrections to legacy markup."""
    reps = [
        # wrong owner domain -> correct owner
        ("https://chothuexemayohanoi.github.io/vanchinh/", BASE),
        ("https://raw.githubusercontent.com/chothuexemayohanoi/vanchinh/refs/heads/main/IMG_0995.png",
         "https://raw.githubusercontent.com/thuexemayhanoi/vanchinh/main/IMG_0995.png"),
        # opening hours: ONLY business hours, not itinerary times
        ("9h - 21h", HOURS_DISPLAY), ("9h-21h", HOURS_DISPLAY),
        ('"closes": "21:00"', '"closes": "17:00"'),
        ("Giờ mở cửa phục vụ: 9h - 21h hàng ngày", "Giờ mở cửa phục vụ: 9h - 17h hàng ngày"),
        ("Hỗ trợ 9h - 17h", "Mở cửa 9h - 17h"),
        # unsupported business claims -> verified/neutral wording
        ("Giao Xe 24/7", "Giao Xe Tận Nơi"),
        ("Cọc Nhẹ, Giao Xe Tận Nơi", "Cọc Nhẹ, Giao Xe Tận Nơi"),
        ("Cọc 0đ", "Cọc Nhẹ"),
        ("cọc nhẹ 0đ", "cọc nhẹ theo loại xe"),
        ("Cứu Hộ Lốp & Động Cơ 24/7", "Hỗ Trợ Sự Cố Xe"),
        ("Cứu Hộ 24/7", "Hỗ Trợ Sự Cố Xe"),
        ("chúng tôi có đội cơ động trực tuyến 24/24 sẵn sàng mang xe mới đến đổi trả cho bạn ngay lập tức, không làm lỡ lịch trình.",
         "hãy dắt xe vào lề an toàn và gọi ngay hotline 0989.595.533 để được hướng dẫn xử lý."),
        ("Chúng tôi có đội cơ động trực tuyến 24/7 sẵn sàng mang xe khác đến đổi tận nơi miễn phí cho bạn.",
         "Hãy dắt xe vào lề an toàn và gọi hotline 0989.595.533 (giờ mở cửa 9h - 17h) để được hướng dẫn."),
        ("Đối tác du lịch tin cậy số 1 Thủ Đô", "Dịch vụ cho thuê xe máy tại Hà Nội"),
        ("trung tâm giao dịch xe gắn máy hàng đầu", "điểm cho thuê xe máy tại Long Biên, Hà Nội"),
        ("Hàng ngàn du khách", "Nhiều du khách"),
        ("Hàng ngàn chuyến đi", "Nhiều chuyến đi"),
        ("Hàng Ngàn Khách Hàng", "Nhiều Khách Hàng"),
        ("Nhận xe ngay sau 15 phút gọi điện.", "Nhận xe sau khi đã xác nhận lịch giao qua điện thoại."),
        ("giao xe đến tận nơi cho bạn trong 15 phút.", "giao xe đến tận nơi cho bạn sau khi đặt lịch."),
        ("15 phút sau nhân viên mang", "ngay sau đó nhân viên mang"),
        ("mang xe đến tận nơi miễn phí trong bán kính 3-5km (Nguyễn Văn Cừ, Ngọc Lâm, Gia Lâm, Hoàn Kiếm).",
         "mang xe đến tận nơi trong khu vực nội thành Hà Nội; thời gian và chi phí được xác nhận khi bạn đặt xe."),
        ("Giao Xe Tận Nơi & Cứu Hộ 24/7", "Giao Xe Tận Nơi & Hỗ Trợ Sự Cố"),
        ("hệ thống cho thuê xe máy uy tín, chuyên nghiệp hàng đầu tại Long Biên", "dịch vụ cho thuê xe máy tại Long Biên"),
        ("hỗ trợ sinh viên và khách du lịch không cần phải cọc một khoản tiền lớn",
         "hỗ trợ sinh viên và khách du lịch với mức cọc nhẹ theo loại xe"),
    ]
    for a, b in reps:
        text = text.replace(a, b)
    return text

def slug_ok(t):
    return t

# ---------------------------------------------------------------- shared chrome
def nav_links():
    return {
        "home": ("Trang Chủ", "index.html", "fas fa-home", "bg-blue-500"),
        "about": ("Giới Thiệu", "gioithieu.html", "fas fa-info", "bg-purple-500"),
        "price": ("Bảng Giá", "banggia.html", "fas fa-tags", "bg-pink-500"),
    }

AREAS = [
    ("Long Biên", "longbien.html", "fas fa-map-marker-alt"),
    ("Gia Lâm", "gialam.html", "fas fa-map-marker-alt"),
    ("Hoàn Kiếm", "hoankiem.html", "fas fa-map-marker-alt"),
    ("Phố Cổ", "phoco.html", "fas fa-map-marker-alt"),
    ("Ba Đình", "badinh.html", "fas fa-landmark"),
    ("Tây Hồ", "tayho.html", "fas fa-water"),
    ("Hai Bà Trưng", "haibatrung.html", "fas fa-building"),
    ("Xe Điện", "xedien.html", "fas fa-bolt"),
]
DURATIONS = [
    ("Thuê Theo Ngày", "thuengay.html", "fas fa-calendar-day"),
    ("Thuê Theo Tuần", "thuetuan.html", "fas fa-calendar-week"),
    ("Thuê Theo Tháng", "thuethang.html", "fas fa-calendar-alt"),
]
HUBS = [
    ("Kinh Nghiệm", "kinhnghiem.html", "fas fa-lightbulb"),
    ("An Toàn", "antoan.html", "fas fa-shield-halved"),
    ("Xe Máy", "xemay.html", "fas fa-motorcycle"),
    ("Du Lịch", "dulich.html", "fas fa-camera-retro"),
    ("Cung Đường", "cungduong.html", "fas fa-route"),
    ("Hỏi Đáp", "hoidap.html", "fas fa-question"),
]
SUPPORT = [
    ("Hỏi Đáp", "faq.html", "fas fa-question", "bg-gray-500"),
    ("Thủ Tục Thuê Xe", "thutuc.html", "fas fa-file-alt", "bg-teal-500"),
    ("Bảo Mật", "baomat.html", "fas fa-shield-alt", "bg-rose-500"),
    ("Chính Sách", "chinhsach.html", "fas fa-file-contract", "bg-cyan-500"),
    ("Điều Khoản", "dieukhoan.html", "fas fa-gavel", "bg-amber-500"),
    ("Liên Hệ", "lienhe.html", "fas fa-envelope", "bg-indigo-500"),
]

def _nav_item(label, href, icon, bg, arrow=True):
    arrow_html = f'<i aria-hidden="true" class="fas fa-chevron-right text-gray-400 text-xs"></i>' if arrow else ""
    return f'''<a href="{href}" class="ios-item flex items-center px-4 py-3.5 text-gray-800 dark:text-white">
    <div class="w-8 h-8 rounded-lg {bg} flex items-center justify-center text-white mr-3 shadow-sm">
        <i aria-hidden="true" class="{icon} text-sm"></i>
    </div>
    <span class="font-medium text-[15px] flex-1">{label}</span>
    {arrow_html}
</a>'''

def _nav_group(title, items, icon, bg, summary_label):
    lis = "\n".join(
        f'<li><a href="{href}" class="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300"><i aria-hidden="true" class="{ic} text-gray-400"></i> {label}</a></li>'
        for label, href, ic in items
    )
    return f'''<details class="group">
    <summary class="ios-item flex items-center px-4 py-3.5 text-gray-800 dark:text-white cursor-pointer">
        <div class="w-8 h-8 rounded-lg {bg} flex items-center justify-center text-white mr-3 shadow-sm">
            <i aria-hidden="true" class="{icon} text-sm"></i>
        </div>
        <span class="font-medium text-[15px] flex-1">{summary_label}</span>
        <i aria-hidden="true" class="fas fa-chevron-down transition-transform duration-200 group-open:rotate-180 text-gray-400 text-xs"></i>
    </summary>
    <ul class="pl-14 pr-4 py-2 space-y-3 bg-gray-50/50 dark:bg-gray-800/50">
        {lis}
    </ul>
</details>'''

def sidebar():
    area_group = _nav_group("Khu Vực", AREAS, "fas fa-motorcycle", "bg-orange-500", "Chọn Khu Vực")
    duration_group = _nav_group("Hình Thức", DURATIONS, "fas fa-clock", "bg-teal-500", "Hình Thức Thuê")
    hub_group = _nav_group("Cẩm Nang", HUBS, "fas fa-book-open", "bg-green-500", "Cẩm Nang")
    support_items = "\n".join(_nav_item(l, h, i, b, arrow=False) for l, h, i, b in SUPPORT)
    main_items = "\n".join(
        _nav_item(l, h, i, b) for l, h, i, b in
        [("Trang Chủ", "index.html", "fas fa-home", "bg-blue-500"),
         ("Giới Thiệu", "gioithieu.html", "fas fa-info", "bg-purple-500"),
         ("Bảng Giá", "banggia.html", "fas fa-tags", "bg-pink-500")]
    )
    return f'''<div id="sidebar-overlay" class="fixed inset-0 bg-black/20 z-40 hidden opacity-0 backdrop-blur-sm transition-opacity" aria-hidden="true"></div>
<aside id="sidebar-menu" class="ios-sidebar fixed top-0 right-0 h-full w-[320px] max-w-[85vw] z-50 transform translate-x-full sidebar-transition flex flex-col shadow-2xl" role="dialog" aria-modal="true" aria-hidden="true" aria-label="Menu chính">
    <div class="px-6 pt-12 pb-4 flex justify-between items-end">
        <h2 class="font-bold text-3xl text-gray-900 dark:text-white tracking-tight">Menu</h2>
        <button id="close-menu-btn" class="w-8 h-8 rounded-full bg-gray-200/50 dark:bg-gray-700/50 flex items-center justify-center text-gray-500 hover:bg-gray-300/50 transition-colors" aria-label="Đóng menu">
            <i aria-hidden="true" class="fas fa-times text-sm"></i>
        </button>
    </div>
    <nav class="flex-1 overflow-y-auto px-4 pb-10 space-y-6">
        <div class="mb-4 mx-1 p-6 rounded-[1.5rem] bg-white/40 dark:bg-gray-800/40 backdrop-blur-md border border-white/20 shadow-xl flex flex-col items-center text-center relative overflow-hidden group">
            <div class="absolute -top-10 -left-10 w-32 h-32 bg-brand-500/20 rounded-full blur-2xl group-hover:bg-brand-500/30 transition-colors"></div>
            <div class="absolute -bottom-10 -right-10 w-32 h-32 bg-purple-500/20 rounded-full blur-2xl group-hover:bg-purple-500/30 transition-colors"></div>
            <div class="relative z-10">
                <div class="inline-flex items-center justify-center w-14 h-14 rounded-full bg-gradient-to-br from-orange-400 to-pink-500 text-white shadow-lg mb-3 transform group-hover:scale-110 transition-transform">
                    <i aria-hidden="true" class="fas fa-clock text-2xl"></i>
                </div>
                <div class="text-sm font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1">Giờ Mở Cửa</div>
                <div class="text-3xl font-black text-gray-800 dark:text-white tracking-tighter">9h - 17h</div>
                <div class="mt-2 text-xs font-bold text-gray-500 dark:text-gray-400">Hàng ngày (kể cả cuối tuần)</div>
            </div>
        </div>
        <div class="ios-group">{main_items}</div>
        <div class="space-y-2">
            <h3 class="px-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Dịch Vụ</h3>
            <div class="ios-group">{area_group}{duration_group}</div>
        </div>
        <div class="space-y-2">
            <h3 class="px-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Cẩm Nang</h3>
            <div class="ios-group">{hub_group}</div>
        </div>
        <div class="space-y-2">
            <h3 class="px-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Hỗ Trợ</h3>
            <div class="ios-group">{support_items}</div>
        </div>
    </nav>
</aside>'''

def header():
    return f'''<header class="fixed top-0 left-0 right-0 z-50 glass-header shadow-sm">
    <div class="container mx-auto px-4 py-3 flex justify-between items-center">
        <div class="flex items-center gap-3">
            <a href="index.html" class="flex items-center gap-2 group">
                <img src="IMG_0995.png" alt="Logo Văn Chính Cho Thuê Xe Máy" loading="eager" decoding="async"
                     class="h-10 w-auto rounded-lg shadow-md group-hover:scale-105 transition-transform border border-white/50">
                <span class="font-bold text-xl tracking-tight text-gray-900 dark:text-white group-hover:text-brand-600 transition-colors">
                    Văn Chính
                </span>
            </a>
        </div>
        <div class="flex items-center gap-4">
            <a href="tel:{PHONE_TEL}" class="hidden sm:flex items-center gap-2 px-3 py-2 rounded-lg bg-brand-50/50 text-brand-600 dark:bg-gray-800/50 dark:text-brand-400 transition-colors font-bold text-sm">
                <i aria-hidden="true" class="fas fa-phone text-xs"></i> {FACTS["phone"]}
            </a>
            <button id="theme-toggle" aria-label="Chuyển đổi giao diện" class="p-2 rounded-full hover:bg-white/50 dark:hover:bg-gray-800/50 transition-colors text-yellow-500 dark:text-gray-400 backdrop-blur-sm">
                <i aria-hidden="true" class="fas fa-sun text-xl" id="theme-icon"></i>
            </button>
            <button id="menu-btn" aria-label="Mở menu" aria-controls="sidebar-menu" aria-expanded="false" class="p-2 rounded-lg bg-brand-50/50 text-brand-600 hover:bg-brand-100/50 dark:bg-gray-800/50 dark:text-brand-400 transition-colors backdrop-blur-sm">
                <i aria-hidden="true" class="fas fa-bars text-2xl"></i>
            </button>
        </div>
    </div>
</header>'''

def contact_widget():
    return f'''<div id="quick-contact-widget" class="fixed left-5 bottom-8 z-[100] flex flex-col items-center gap-4 widget-container group">
    <div class="widget-items-wrapper flex flex-col gap-4 mb-3 pb-2 items-center">
        <a href="{FACTS['zalo']}" target="_blank" rel="noopener noreferrer"
           class="w-14 h-14 rounded-full bg-blue-500 text-white flex items-center justify-center shadow-blue-500/50 shadow-lg hover:scale-110 border-2 border-white/40 backdrop-blur-md relative group/tooltip transition-transform duration-300">
            <img src="https://upload.wikimedia.org/wikipedia/commons/9/91/Icon_of_Zalo.svg" alt="Zalo" loading="lazy" decoding="async" class="w-8 h-8 filter brightness-0 invert">
            <span class="absolute left-16 px-3 py-1.5 bg-gray-900/90 text-white text-xs font-bold rounded-lg shadow-xl opacity-0 group-hover/tooltip:opacity-100 transition-opacity whitespace-nowrap backdrop-blur-md border border-white/10">Chat Zalo</span>
        </a>
        <a href="https://www.google.com/maps/search/?api=1&query={FACTS['coordinates']['latitude']},{FACTS['coordinates']['longitude']}" target="_blank" rel="noopener noreferrer" aria-label="Chỉ đường Maps"
           class="w-14 h-14 rounded-full bg-red-500 text-white flex items-center justify-center shadow-red-500/50 shadow-lg hover:scale-110 border-2 border-white/40 backdrop-blur-md relative group/tooltip transition-transform duration-300">
            <i aria-hidden="true" class="fas fa-map-marked-alt text-xl"></i>
            <span class="absolute left-16 px-3 py-1.5 bg-gray-900/90 text-white text-xs font-bold rounded-lg shadow-xl opacity-0 group-hover/tooltip:opacity-100 transition-opacity whitespace-nowrap backdrop-blur-md border border-white/10">Chỉ Đường</span>
        </a>
        <a href="tel:{PHONE_TEL}" aria-label="Gọi điện thoại"
           class="w-14 h-14 rounded-full bg-green-500 text-white flex items-center justify-center shadow-green-500/50 shadow-lg hover:scale-110 border-2 border-white/40 backdrop-blur-md relative group/tooltip transition-transform duration-300">
            <i aria-hidden="true" class="fas fa-phone text-xl"></i>
            <span class="absolute left-16 px-3 py-1.5 bg-gray-900/90 text-white text-xs font-bold rounded-lg shadow-xl opacity-0 group-hover/tooltip:opacity-100 transition-opacity whitespace-nowrap backdrop-blur-md border border-white/10">Gọi Luôn</span>
        </a>
    </div>
    <button id="main-contact-btn" aria-label="Mở tiện ích liên hệ nhanh" aria-expanded="false" class="relative w-16 h-16 rounded-full bg-gradient-to-br from-brand-500 to-indigo-600 text-white shadow-brand-500/60 shadow-2xl flex items-center justify-center text-2xl transition-all duration-300 hover:scale-105 border-[3px] border-white/30 backdrop-blur-sm z-20 overflow-visible">
        <i aria-hidden="true" class="fas fa-phone-volume text-3xl drop-shadow-md transition-transform duration-300" id="contact-icon"></i>
    </button>
    <span class="text-[10px] font-bold text-brand-600 dark:text-brand-400 bg-white/80 dark:bg-gray-800/80 px-2 py-0.5 rounded-full shadow-sm backdrop-blur-sm mt-1">Mở cửa 9h - 17h</span>
</div>'''

def footer():
    def col(title, links):
        lis = "\n".join(
            f'<li><a href="{h}" class="hover:text-brand-400 transition-colors">{l}</a></li>' for l, h in links
        )
        return f'''<div class="footer-group border-b border-gray-700 pb-2 md:border-none md:pb-0">
    <h4 class="footer-heading cursor-pointer md:cursor-default flex justify-between items-center text-white font-bold mb-2 md:mb-4">
        {title}
        <i aria-hidden="true" class="fas fa-chevron-down footer-chevron md:hidden text-xs"></i>
    </h4>
    <ul class="footer-content space-y-2 text-sm">{lis}</ul>
</div>'''
    hub_links = "".join(
        f'<li><a href="{h}" class="hover:text-brand-400 transition-colors">Cẩm nang {t}</a></li>' for t, h, _ in HUBS
    )
    return f'''<footer class="bg-gray-900/95 text-gray-300 pt-16 pb-8 border-t border-gray-800 backdrop-blur-lg relative z-10">
    <div class="container mx-auto px-4">
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-8 mb-12">
            <div class="col-span-1 space-y-4 border-b border-gray-700 pb-6 md:border-none md:pb-0">
                <h3 class="text-2xl font-bold text-white mb-2">Văn Chính<span class="text-brand-500">.</span></h3>
                <p class="text-sm leading-relaxed text-gray-400">
                    <i aria-hidden="true" class="fas fa-motorcycle mr-1 text-brand-500"></i> Dịch vụ cho thuê xe máy tại Long Biên và nội thành Hà Nội. Đồng hành cùng mọi chặng đường.
                </p>
                <div class="flex space-x-3 pt-2">
                    <a href="{FACTS['facebook']}" target="_blank" rel="noopener noreferrer" class="w-8 h-8 rounded-full bg-gray-800 flex items-center justify-center hover:bg-blue-600 transition-colors text-white" aria-label="Facebook">
                        <i aria-hidden="true" class="fab fa-facebook-f text-sm"></i>
                    </a>
                    <a href="https://share.google/HKoX2vDQkEkdAOSZE" target="_blank" rel="noopener noreferrer" class="w-8 h-8 rounded-full bg-gray-800 flex items-center justify-center hover:bg-red-500 transition-colors text-white" aria-label="Google Map">
                        <i aria-hidden="true" class="fas fa-map-marked-alt text-sm"></i>
                    </a>
                    <a href="https://www.tripadvisor.com.vn/Attraction_Review-g293924-d34112208-Reviews-Cho_Thue_Xe_May_Van_Chinh-Hanoi.html" target="_blank" rel="noopener noreferrer" class="w-8 h-8 rounded-full bg-gray-800 flex items-center justify-center hover:bg-yellow-500 transition-colors text-white" aria-label="TripAdvisor Reviews">
                        <i aria-hidden="true" class="fas fa-star text-sm"></i>
                    </a>
                    <a href="https://thuexemaynguyentu.com" target="_blank" rel="noopener noreferrer" class="w-8 h-8 rounded-full bg-gray-800 flex items-center justify-center hover:bg-green-500 transition-colors text-white" aria-label="Thuê xe máy Nguyễn Tú">
                        <i aria-hidden="true" class="fas fa-globe text-sm"></i>
                    </a>
                </div>
            </div>
            {col("Về Chúng Tôi", [("Trang Chủ", "index.html"), ("Giới Thiệu", "gioithieu.html"), ("Bảng Giá", "banggia.html"), ("Liên Hệ", "lienhe.html")])}
            {col("Khu Vực Phục Vụ", [(t, h) for t, h, _ in AREAS])}
            {col("Hình Thức Thuê", [(t, h) for t, h, _ in DURATIONS] + [("Thủ Tục Cần Biết", "thutuc.html"), ("Hỏi Đáp", "faq.html")])}
            <div class="footer-group col-span-1 border-b border-gray-700 pb-2 md:border-none md:pb-0">
                <h4 class="footer-heading cursor-pointer md:cursor-default flex justify-between items-center text-white font-bold mb-2 md:mb-4">
                    Thông Tin Liên Hệ
                    <i aria-hidden="true" class="fas fa-chevron-down footer-chevron md:hidden text-xs"></i>
                </h4>
                <ul class="footer-content space-y-3 text-sm mb-4">
                    <li class="flex items-start">
                        <i aria-hidden="true" class="fas fa-map-marker-alt mt-1 mr-2 text-brand-500 text-xs"></i>
                        <div class="flex flex-col space-y-1">
                            <span>Cơ sở 1: Số 24 Ngõ 5 Nguyễn Văn Cừ, Ngọc Lâm, Long Biên, Hà Nội.</span>
                            <span>Cơ sở 2: Số 24 Tạ Hiện, Hàng Buồm, Hoàn Kiếm, Hà Nội.</span>
                        </div>
                    </li>
                    <li class="flex items-center">
                        <i aria-hidden="true" class="fas fa-phone-alt mr-2 text-brand-500 text-xs"></i>
                        <a href="tel:{PHONE_TEL}" class="hover:text-white transition-colors font-bold">{FACTS["phone"]}</a>
                    </li>
                    <li class="flex items-center">
                        <i aria-hidden="true" class="fas fa-envelope mr-2 text-brand-500 text-xs"></i>
                        <a href="mailto:{FACTS['email']}" class="hover:text-white transition-colors">{FACTS["email"]}</a>
                    </li>
                    <li class="flex items-center">
                        <i aria-hidden="true" class="fas fa-clock mr-2 text-brand-500 text-xs"></i>
                        <span class="text-gray-300">Giờ mở cửa: 9h - 17h hàng ngày</span>
                    </li>
                </ul>
                <ul class="footer-content space-y-2 text-sm"><li class="text-xs font-semibold text-gray-500 uppercase tracking-wider">Cẩm Nang</li>{hub_links}</ul>
            </div>
        </div>
        <div class="border-t border-gray-800 pt-8 flex flex-col md:flex-row justify-between items-center text-sm text-gray-500">
            <p class="mb-2 md:mb-0">© 2026 <a href="index.html" class="hover:text-brand-500 transition-colors font-medium">Bản quyền thuộc về Dịch vụ Cho thuê xe máy Hà Nội</a>. Thiết kế Văn Chính</p>
            <div class="flex space-x-4">
                <a href="faq.html" class="hover:text-gray-300"><i aria-hidden="true" class="fas fa-question-circle mr-1"></i>Hỏi Đáp Thường Gặp</a>
                <a href="lienhe.html" class="hover:text-gray-300"><i aria-hidden="true" class="fas fa-envelope mr-1"></i>Gửi Email Liên Hệ</a>
            </div>
        </div>
    </div>
</footer>'''

def render_page(filename, title, description, content, extra_jsonld=None, include_assistant=False,
                og_image=None, noindex=False):
    canonical = BASE + ("" if filename == "index.html" else filename)
    og_image = og_image or (BASE + "IMG_0995.png")
    jsonld_blocks = []
    if extra_jsonld:
        for obj in extra_jsonld:
            jsonld_blocks.append('<script type="application/ld+json">\n' + json.dumps(obj, ensure_ascii=False, indent=2) + "\n</script>")
    jsonld = "\n".join(jsonld_blocks)
    robots = "noindex, nofollow" if noindex else "index, follow"
    assistant_libs = f'''<script src="https://cdnjs.cloudflare.com/ajax/libs/dompurify/3.0.6/purify.min.js" crossorigin="anonymous"></script>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js" crossorigin="anonymous"></script>''' if include_assistant else ""
    assistant_script = '<script src="assets/js/assistant.js" defer></script>' if include_assistant else ""
    html = f'''<!DOCTYPE html>
<html lang="vi" class="scroll-smooth">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <meta name="description" content="{description}">
    <meta name="robots" content="{robots}">
    <link rel="canonical" href="{canonical}">
    <meta property="og:type" content="website">
    <meta property="og:site_name" content="Văn Chính - Cho Thuê Xe Máy Hà Nội">
    <meta property="og:title" content="{title}">
    <meta property="og:description" content="{description}">
    <meta property="og:url" content="{canonical}">
    <meta property="og:image" content="{og_image}">
    <meta property="og:locale" content="vi_VN">
    <meta name="theme-color" content="#2563eb">
    <link rel="icon" type="image/png" href="IMG_0995.png">
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" crossorigin="anonymous">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Be+Vietnam+Pro:wght@300;400;500;600;700;900&display=swap" rel="stylesheet">
    {assistant_libs}
    <link rel="stylesheet" href="assets/css/main.css">
    <script src="assets/js/tailwind-config.js"></script>
    <script src="assets/js/main.js" defer></script>
    {assistant_script}
{jsonld}
</head>
<body class="bg-gray-50 text-gray-800 dark:bg-gray-900 dark:text-gray-100 transition-colors duration-300 relative">
    <a href="#main" class="sr-only focus:not-sr-only p-2 absolute z-[9999] bg-white text-brand-600">Bỏ qua tới nội dung chính</a>
    <div class="ambient-bg"></div>
    {header()}
    {contact_widget()}
    {sidebar()}
    <main id="main" class="pt-20">
{content}
    </main>
    {footer()}
</body>
</html>
'''
    return html

def breadcrumb(name, path):
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Trang Chủ", "item": BASE},
            {"@type": "ListItem", "position": 2, "name": name, "item": BASE + path},
        ],
    }

# ---------------------------------------------------------------- page content
def sec(name):
    """Load an extracted legacy section with claim fixes applied."""
    raw = (ROOT / "sections" / (name + ".txt")).read_text(encoding="utf-8")
    return fix(raw)

def wrap_article(*blocks):
    return ('<article class="container mx-auto px-4 py-16 space-y-20 max-w-5xl relative z-10">\n'
            + "\n".join(blocks) + "\n</article>")

def page_h1(title, subtitle, icon="fas fa-motorcycle"):
    return f'''<section class="bg-gradient-to-r from-brand-600/90 to-indigo-700/90 text-white">
    <div class="container mx-auto px-4 py-14 text-center">
        <div class="inline-flex items-center justify-center w-16 h-16 rounded-full bg-white/20 backdrop-blur-sm mb-4">
            <i aria-hidden="true" class="{icon} text-3xl"></i>
        </div>
        <h1 class="text-3xl md:text-5xl font-extrabold tracking-tight">{title}</h1>
        <p class="mt-4 text-white/90 max-w-2xl mx-auto font-medium">{subtitle}</p>
    </div>
</section>'''

def content_block(inner):
    return f'<article class="container mx-auto px-4 py-12 max-w-3xl relative z-10"><div class="content-block text-gray-700 dark:text-gray-300">{inner}</div></article>'

def cta_block(text="Gọi ngay hotline 0989.595.533 hoặc chat Zalo để được tư vấn và giữ xe."):
    return f'''<article class="container mx-auto px-4 pb-16 max-w-3xl relative z-10">
    <div class="glass-panel bg-gradient-to-r from-brand-600/90 to-indigo-700/90 rounded-2xl p-8 text-center text-white shadow-xl relative overflow-hidden border-none">
        <h2 class="text-2xl md:text-3xl font-bold mb-3">Sẵn Sàng Chọn Xe Cho Chuyến Đi Của Bạn?</h2>
        <p class="mb-6 text-white/90">{text}</p>
        <div class="flex flex-col sm:flex-row justify-center gap-4">
            <a href="tel:{PHONE_TEL}" class="px-6 py-3 bg-white text-brand-700 font-bold rounded-lg shadow-lg hover:scale-105 transition-transform"><i aria-hidden="true" class="fas fa-phone mr-2"></i>{FACTS["phone"]}</a>
            <a href="banggia.html" class="px-6 py-3 bg-white/20 border border-white/40 font-bold rounded-lg hover:bg-white/30 transition-colors"><i aria-hidden="true" class="fas fa-tags mr-2"></i>Xem Bảng Giá</a>
        </div>
        <p class="mt-4 text-sm text-white/80"><i aria-hidden="true" class="fas fa-clock mr-1"></i>Giờ mở cửa: 9h - 17h hàng ngày</p>
    </div>
</article>'''

def facts_table():
    t = FACTS["prices"]["tiers"]
    rows = "".join(
        f'<tr class="border-b border-gray-200 dark:border-gray-700"><td class="py-3 pr-4 font-semibold">{x["name"]}</td><td class="py-3 pr-4">{x["day"]}/ngày</td><td class="py-3 pr-4">{x["week"]}/tuần</td><td class="py-3 pr-4">{x["month"]}/tháng</td><td class="py-3">từ {x["deposit_from"]}</td></tr>'
        for x in t)
    return f'''<div class="overflow-x-auto my-6"><table class="w-full text-sm border border-gray-200 dark:border-gray-700 rounded-lg">
<thead class="bg-gray-100 dark:bg-gray-800"><tr><th class="p-3 text-left">Dòng xe</th><th class="p-3 text-left">Theo ngày</th><th class="p-3 text-left">Theo tuần</th><th class="p-3 text-left">Theo tháng</th><th class="p-3 text-left">Cọc từ</th></tr></thead>
<tbody>{rows}</tbody></table></div>
<p class="text-sm text-gray-500 dark:text-gray-400">* Giá tham khảo niêm yết, có thể thay đổi theo thời điểm - luôn xác nhận qua hotline. Xe giao kèm: {", ".join(FACTS["included_with_bike"])}.</p>'''

def area_page(name, intro, landmarks, note):
    h1 = page_h1(f"Cho Thuê Xe Máy Tại {name} - Văn Chính",
                 f"Dịch vụ cho thuê xe máy tại {name}, Hà Nội của Văn Chính. Xe tay ga, xe số được bảo dưỡng định kỳ, thủ tục đơn giản, giao xe tận nơi theo thỏa thuận.", "fas fa-map-marker-alt")
    lm = "".join(f"<li>{x}</li>" for x in landmarks)
    body = f'''<p>Văn Chính cung cấp dịch vụ <strong>cho thuê xe máy tại {name}</strong> cho cả khách du lịch, sinh viên và người đi làm. Đội xe gồm xe số (Wave Alpha, Sirius) và xe tay ga (Vision, Air Blade) được bảo dưỡng trước mỗi lượt thuê, kèm mũ bảo hiểm và áo mưa khi giao xe.</p>
<p>{intro}</p>
<h2>Điểm đến gần {name} phù hợp đi xe máy</h2>
<ul>{lm}</ul>
<h2>Thủ tục và thời gian làm việc</h2>
<p>Khách cần có CCCD gắn chip hoặc Hộ chiếu (khách nước ngoài) và giấy phép lái xe hợp lệ. Tiền cọc theo loại xe, được hoàn trả khi trả xe đúng hiện trạng. Văn Chính mở cửa <strong>9h - 17h hàng ngày</strong>; bạn nên liên hệ hotline trước để được giữ xe và thỏa thuận giao xe tận nơi.</p>
<p>{note}</p>
<h2>Bảng giá tham khảo</h2>
{facts_table()}'''
    return h1 + content_block(body) + cta_block()

def duration_page(name, unit, intro, extra):
    h1 = page_h1(f"{name} Xe Máy Hà Nội - Văn Chính",
                 f"Gói {unit} cho thuê xe máy của Văn Chính tại Hà Nội. Giá công khai, cọc theo loại xe, hỗ trợ giao xe theo thỏa thuận.", "fas fa-calendar-check")
    body = f'''<p>{intro}</p>
<p>Khách cần CCCD gắn chip/Hộ chiếu và giấy phép lái xe hợp lệ. Tiền cọc theo loại xe (xem bảng giá), hoàn trả khi trả xe đúng hiện trạng. Giờ nhận/trả xe: <strong>9h - 17h hàng ngày</strong>.</p>
{extra}
<h2>Giá {unit} tham khảo</h2>
{facts_table()}'''
    return h1 + content_block(body) + cta_block()

def hub_page(hub_id, name, desc, cat_prefix, cat_name):
    h1 = page_h1(f"Cẩm Nang {name} - Văn Chính",
                 f"Chuyên mục {name}: bài viết hướng dẫn, kinh nghiệm và hỏi đáp về thuê xe máy tại Hà Nội.", "fas fa-book-open")
    body = f'''<p>{desc}</p>
<p>Các bài viết thuộc chuyên mục <strong>{name}</strong> ({cat_prefix}) được đăng tại thư mục <code>cam-nang/{cat_prefix.lower() if cat_prefix.lower()!="hoi-dap" else "hoi-dap"}/</code> và sẽ được liệt kê dưới đây khi xuất bản.</p>
<div id="hub-list-{hub_id}" class="my-8 p-6 rounded-xl bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-300">
    <p><i aria-hidden="true" class="fas fa-info-circle mr-2 text-brand-500"></i>Chưa có bài viết nào trong chuyên mục này. Danh sách sẽ được cập nhật tự động khi các bài đạt chuẩn xuất bản.</p>
</div>
<p>Bạn cần thuê xe ngay? Xem <a href="banggia.html" class="text-brand-600 dark:text-brand-400 font-semibold hover:underline">bảng giá</a> hoặc gọi hotline <a href="tel:{PHONE_TEL}" class="text-brand-600 dark:text-brand-400 font-semibold hover:underline">{FACTS["phone"]}</a> (giờ mở cửa 9h - 17h hàng ngày).</p>'''
    return h1 + content_block(body)

PAGES = {}

# ---------------- index (homepage: brand intent) ----------------
PAGES["index.html"] = dict(
    title="Cho Thuê Xe Máy Hà Nội - Văn Chính | Cọc Nhẹ, Giao Xe Tận Nơi",
    description="Dịch vụ cho thuê xe máy Hà Nội - Văn Chính tại Long Biên. Xe tay ga, xe số được bảo dưỡng, cọc theo loại xe, giao xe tận nơi theo thỏa thuận. Mở cửa 9h-17h hàng ngày. Gọi 0989595533.",
    content=sec("hero") + wrap_article(sec("aifeatures"), sec("about"), sec("pricing"), sec("reviews"), sec("location"), sec("faq"), sec("cta")),
    jsonld=[localbusiness_schema()],
    include_assistant=True,
)

# ---------------- about ----------------
PAGES["gioithieu.html"] = dict(
    title="Giới Thiệu Văn Chính - Cho Thuê Xe Máy Long Biên, Hà Nội",
    description="Tìm hiểu về Văn Chính - dịch vụ cho thuê xe máy tại Long Biên, Hà Nội: đội xe, quy trình bảo dưỡng, thủ tục thuê và cam kết phục vụ trong giờ mở cửa 9h-17h hàng ngày.",
    content=page_h1("Giới Thiệu Văn Chính - Cho Thuê Xe Máy Long Biên, Hà Nội",
                    "Cửa hàng cho thuê xe máy tại Ngọc Lâm, Long Biên: đội xe, quy trình bảo dưỡng và cách phục vụ trong giờ mở cửa 9h - 17h hàng ngày.",
                    "fas fa-info")
    + wrap_article(sec("about"), sec("reviews")) + cta_block("Gọi hotline để được tư vấn về dòng xe phù hợp với chuyến đi của bạn."),
    jsonld=[localbusiness_schema(), breadcrumb("Giới Thiệu", "gioithieu.html")],
)

# ---------------- pricing ----------------
PAGES["banggia.html"] = dict(
    title="Bảng Giá Cho Thuê Xe Máy Hà Nội 2026 - Văn Chính",
    description="Bảng giá thuê xe máy Văn Chính: xe số, xe tay ga, thuê ngày/tuần/tháng, mức cọc theo loại xe. Giá công khai, không chi phí ẩn. Xác nhận qua hotline 0989595533.",
    content=page_h1("Bảng Giá Cho Thuê Xe Máy - Văn Chính",
                    "Giá công khai theo từng dòng xe, thuê theo ngày, tuần hoặc tháng. Xác nhận giá và tình trạng xe qua hotline trước khi nhận.",
                    "fas fa-tags")
    + content_block(f'''<p>Giá thuê tại Văn Chính được niêm yết công khai theo dòng xe và thời gian thuê. Mỗi xe giao đi kèm: {", ".join(FACTS["included_with_bike"])}.</p>
{facts_table()}
<h2>Lưu ý về giá và cọc</h2>
<ul>
<li>Giá có thể thay đổi theo mùa và dòng xe cụ thể - xác nhận qua hotline 0989.595.533 trước khi đến nhận xe.</li>
<li>Tiền cọc hoàn trả đầy đủ khi trả xe đúng hiện trạng.</li>
<li>Giao xe tận nơi tại Hà Nội: thời gian và chi phí xác nhận khi đặt xe.</li>
</ul>
<h2>Giờ nhận xe</h2>
<p>Văn Chính mở cửa <strong>9h - 17h hàng ngày</strong>, kể cả cuối tuần. Vui lòng sắp xếp nhận/trả xe trong khung giờ này.</p>''')
    + cta_block(),
    jsonld=[localbusiness_schema(), breadcrumb("Bảng Giá", "banggia.html")],
)

# ---------------- faq ----------------
PAGES["faq.html"] = dict(
    title="Hỏi Đáp Cho Thuê Xe Máy Hà Nội - Văn Chính",
    description="Câu hỏi thường gặp khi thuê xe máy tại Văn Chính Hà Nội: giấy tờ cần thiết, mức cọc, giao xe tận nơi, sự cố xe, giờ mở cửa 9h-17h hàng ngày.",
    content=page_h1("Hỏi Đáp Thường Gặp", "Giấy tờ, cọc, giao xe, sự cố xe - những thắc mắc phổ biến nhất khi thuê xe máy tại Văn Chính.", "fas fa-question-circle")
    + wrap_article(sec("faq")),
    jsonld=[breadcrumb("Hỏi Đáp", "faq.html")],
)

# ---------------- contact ----------------
PAGES["lienhe.html"] = dict(
    title="Liên Hệ Văn Chính - Cho Thuê Xe Máy Hà Nội",
    description="Liên hệ Văn Chính: hotline 0989.595.533, Zalo, email, địa chỉ Số 24 Ngõ 5 Nguyễn Văn Cừ, Ngọc Lâm, Long Biên, Hà Nội. Mở cửa 9h-17h hàng ngày.",
    content=page_h1("Liên Hệ Văn Chính", "Hotline, Zalo, email và địa chỉ cửa hàng. Giờ mở cửa 9h - 17h hàng ngày.", "fas fa-envelope")
    + wrap_article(sec("location")) + cta_block("Gọi hoặc chat Zalo để được tư vấn nhanh nhất trong giờ mở cửa."),
    jsonld=[localbusiness_schema(), breadcrumb("Liên Hệ", "lienhe.html")],
)

# ---------------- areas ----------------
PAGES["longbien.html"] = dict(
    title="Cho Thuê Xe Máy Long Biên - Văn Chính",
    description="Cho thuê xe máy tại Long Biên, Hà Nội. Cửa hàng Văn Chính tại 24 Ngõ 5 Nguyễn Văn Cừ, Ngọc Lâm. Xe số, xe ga, cọc theo loại xe, mở cửa 9h-17h hàng ngày.",
    content=area_page("Long Biên",
        "Cửa hàng chính của Văn Chính nằm tại <strong>Số 24 Ngõ 5 Nguyễn Văn Cừ, Ngọc Lâm, Long Biên</strong> - gần cầu Chương Dương, thuận tiện di chuyển sang Phố Cổ hoặc lên các tỉnh phía Bắc.",
        ["Cầu Long Biên và ga Long Biên", "Chợ Long Biên, phố ẩm thực Ngọc Lâm", "Sóc Sơn, Núi Hàm Lợn (cuối tuần)", "Đền Gióng (Sóc Sơn)"],
        "Bạn đang ở Long Biên? Đến trực tiếp cửa hàng trong giờ 9h - 17h để xem và chọn xe."),
    jsonld=[localbusiness_schema(), breadcrumb("Long Biên", "longbien.html")],
)
PAGES["gialam.html"] = dict(
    title="Cho Thuê Xe Máy Gia Lâm - Văn Chính",
    description="Cho thuê xe máy tại Gia Lâm, Hà Nội của Văn Chính. Giao xe tận nơi theo thỏa thuận, thủ tục đơn giản, mở cửa 9h-17h hàng ngày. Hotline 0989595533.",
    content=area_page("Gia Lâm",
        "Gia Lâm nằm sát Long Biên, cách cửa hàng Văn Chính chưa đầy 10 phút đi xe. Khách ở Gia Lâm có thể đến nhận xe trực tiếp hoặc thỏa thuận giao xe tận nơi.",
        ["Bát Tràng (làng gốm)", "Van Duc, Lệ Chi (du lịch sinh thái)", "Cầu Thanh Trì, Vĩnh Tuy", "Đường cổ Thổ Hà"],
        "Hãy gọi trước để chúng tôi chuẩn bị xe phù hợp với lịch trình của bạn."),
    jsonld=[breadcrumb("Gia Lâm", "gialam.html")],
)
PAGES["hoankiem.html"] = dict(
    title="Cho Thuê Xe Máy Hoàn Kiếm - Văn Chính",
    description="Cho thuê xe máy tại quận Hoàn Kiếm, Hà Nội. Văn Chính giao xe tận nơi theo thỏa thuận, cọc theo loại xe, mở cửa 9h-17h hàng ngày. Hotline 0989595533.",
    content=area_page("Hoàn Kiếm",
        "Trung tâm phố cổ với nhiều đường một chiều - đi xe máy là cách linh hoạt nhất để khám phá Hồ Gươm và 36 phố phường. Văn Chính hỗ trợ giao xe tận nơi tại Hoàn Kiếm theo thỏa thuận.",
        ["Hồ Hoàn Kiếm, Tháp Rùa", "Nhà Thờ Lớn, Hàng Mã", "Chợ Đồng Xuân", "Cầu Long Biên (đi xe 10 phút)"],
        "Cuối tuần khu vực Hồ Gươm cấm xe cơ giới để đi bộ - kiểm tra lịch trước khi lượn phố."),
    jsonld=[breadcrumb("Hoàn Kiếm", "hoankiem.html")],
)
PAGES["phoco.html"] = dict(
    title="Cho Thuê Xe Máy Phố Cổ Hà Nội - Văn Chính",
    description="Cho thuê xe máy tại Phố Cổ Hà Nội. Xe ga nhẹ, dễ lái cho đường nhỏ, giao xe theo thỏa thuận, mở cửa 9h-17h hàng ngày. Hotline 0989595533.",
    content=area_page("Phố Cổ",
        "Phố Cổ gồm các phố Hàng rộng hẹp và nhiều đường một chiều; xe tay ga nhỏ gọn như Vision là lựa chọn hợp lý. Văn Chính có cơ sở tại 24 Tạ Hiện, Hàng Buồm (xác nhận trước khi đến) và giao xe theo thỏa thuận.",
        ["Tạ Hiện, Hàng Buồm (phố bia)", "Đồng Xuân, Hàng Đào", "Hàng Mã, Hàng Quạt", "Nhà Thờ Lớn, Hàng Trống"],
        "Đỗ xe: gửi bãi trông xe có vé (5.000đ - 10.000đ/lượt), không để xe trên vỉa hè để tránh bị cẩu."),
    jsonld=[breadcrumb("Phố Cổ", "phoco.html")],
)
PAGES["badinh.html"] = dict(
    title="Cho Thuê Xe Máy Ba Đình - Văn Chính",
    description="Cho thuê xe máy tại quận Ba Đình, Hà Nội. Giao xe tận nơi theo thỏa thuận, cọc theo loại xe, mở cửa 9h-17h hàng ngày. Hotline 0989595533.",
    content=area_page("Ba Đình",
        "Ba Đình là khu vực di tích lịch sử với các trục đường rộng như Hồ Chí Minh, Kim Mã - phù hợp di chuyển bằng xe máy từ cửa hàng Long Biên qua cầu Nhật Tân hoặc Chương Dương.",
        ["Lăng Bác, Quảng trường Ba Đình", "Hồ Tây, đường Thanh Niên", "Chùa Một Cột, Bảo tàng Dân tộc học (Cầu Giấy)"],
        "Khu vực Lăng Bác có quy định dừng đỗ riêng - chú ý biển báo khi tham quan."),
    jsonld=[breadcrumb("Ba Đình", "badinh.html")],
)
PAGES["tayho.html"] = dict(
    title="Cho Thuê Xe Máy Tây Hồ - Văn Chính",
    description="Cho thuê xe máy tại quận Tây Hồ, Hà Nội. Đường ven hồ đẹp để đi phượt nhẹ, giao xe theo thỏa thuận, mở cửa 9h-17h hàng ngày. Hotline 0989595533.",
    content=area_page("Tây Hồ",
        "Đường Thanh Niên vành đai Hồ Tây là một trong những cung đường đẹp nhất Hà Nội để đi xe máy buổi chiều. Văn Chính hỗ trợ giao xe tại Tây Hồ theo thỏa thuận.",
        ["Đường Thanh Niên, Hồ Tây", "Chùa Trấn Quốc", "Phố Nhật Tân (phố đào)", "Khu Lotte Mall Tây Hồ"],
        "Tuyệt đẹp vào hoàng hôn; nhớ trả xe trước 17h hoặc thỏa thuận thuê qua đêm."),
    jsonld=[breadcrumb("Tây Hồ", "tayho.html")],
)
PAGES["haibatrung.html"] = dict(
    title="Cho Thuê Xe Máy Hai Bà Trưng - Văn Chính",
    description="Cho thuê xe máy tại quận Hai Bà Trưng, Hà Nội. Giao xe tận nơi theo thỏa thuận, cọc theo loại xe, mở cửa 9h-17h hàng ngày. Hotline 0989595533.",
    content=area_page("Hai Bà Trưng",
        "Hai Bà Trưng nối trung tâm với phía Nam qua cầu Mai Động, Vĩnh Tuy - thuận tiện cho khách công tác cần di chuyển nhiều điểm trong ngày.",
        ["Hồ Ba Mẫu, công viên Thống Nhất", "Chợ Hôm, phố Bạch Mai", "Cầu Vĩnh Tuy ngắm夜景 thành phố"],
        "Giờ cao điểm sáng 7h-8h30, chiều 17h-18h45 - chủ động lộ trình để tránh tắc đường."),
    jsonld=[breadcrumb("Hai Bà Trưng", "haibatrung.html")],
)
PAGES["haibatrung.html"]["content"] = PAGES["haibatrung.html"]["content"].replace("夜景", "nền trời đêm")
PAGES["xedien.html"] = dict(
    title="Thuê Xe Máy Điện Hà Nội - Văn Chính",
    description="Thuê xe máy điện tại Hà Nội của Văn Chính. Phù hợp đi phố, học viên, di chuyển ngắn trong nội thành. Giao xe theo thỏa thuận, mở cửa 9h-17h hàng ngày.",
    content=area_page("Xe Điện",
        "Xe máy điện phù hợp hành trình ngắn trong nội thành: đi phố, đi làm, đi học; vận hành êm và không tốn xăng. Tùy thời điểm, Văn Chính có một số dòng xe điện - gọi hotline trước để kiểm tra tình trạng xe.",
        ["Di chuyển nội thành, phố cổ", "Lộ trình dưới 40km/ngày", "Sạc xe qua đêm tại chỗ nghỉ"],
        "Xe điện có giới hạn quãng đường pin - thảo luận rõ lộ trình của bạn để được tư vấn xe phù hợp."),
    jsonld=[breadcrumb("Xe Điện", "xedien.html")],
)

# ---------------- durations ----------------
PAGES["thuengay.html"] = dict(
    title="Thuê Xe Máy Theo Ngày Hà Nội - Văn Chính",
    description="Thuê xe máy theo ngày tại Hà Nội của Văn Chính. Xe số từ 150.000đ/ngày, xe ga 180.000-250.000đ/ngày (tham khảo), cọc theo loại xe, mở cửa 9h-17h hàng ngày.",
    content=duration_page("Thuê Theo Ngày", "theo ngày",
        "Thuê theo ngày là gói phổ biến nhất cho du khách khám phá Hà Nội trong 1-2 ngày hoặc đi周边 sát như Sóc Sơn, Ba Vì, Tam Đảo.",
        "<p>Tính ngày thuê: theo ngày tự nhiên, nhận trong giờ mở cửa 9h - 17h. Thuê 7 ngày trở lên được tính giá tuần ưu đãi hơn (xem bảng giá).</p>"),
    jsonld=[breadcrumb("Thuê Theo Ngày", "thuengay.html")],
)
PAGES["thuengay.html"]["content"] = PAGES["thuengay.html"]["content"].replace("周边", "các vùng ven")
PAGES["thuetuan.html"] = dict(
    title="Thuê Xe Máy Theo Tuần Hà Nội - Văn Chính",
    description="Thuê xe máy theo tuần tại Hà Nội: giá ưu đãi so với thuê ngày, xe số 600.000-900.000đ/tuần (tham khảo). Mở cửa 9h-17h hàng ngày. Hotline 0989595533.",
    content=duration_page("Thuê Theo Tuần", "theo tuần",
        "Gói tuần dành cho khách du lịch dài ngày hoặc công tác cả tuần. Giá tuần đã ưu đãi so với tổng giá ngày; đồng thời còn có ưu đãi tự động khi đặt từ 7 ngày trở lên.",
        "<p>Thuê tuần giúp chủ động lịch trình mà không cần gia hạn hằng ngày. Xe được kiểm tra giữa kỳ nếu thuê dài ngày.</p>"),
    jsonld=[breadcrumb("Thuê Theo Tuần", "thuetuan.html")],
)
PAGES["thuethang.html"] = dict(
    title="Thuê Xe Máy Theo Tháng Hà Nội - Văn Chính",
    description="Thuê xe máy theo tháng tại Hà Nội cho sinh viên và người đi làm. Xe số từ 800.000đ/tháng (tham khảo), thủ tục đơn giản, mở cửa 9h-17h hàng ngày.",
    content=duration_page("Thuê Theo Tháng", "theo tháng",
        "Gói tháng dành cho sinh viên, người đi làm cần phương tiện cố định. Ưu điểm: giá rẻ hơn thuê ngày, xe ổn định trong suốt tháng, hỗ trợ kiểm tra giữa kỳ.",
        "<p>Khi thuê tháng, khách cần CCCD gắn chip chính chủ và giấy phép lái xe; tiền cọc theo loại xe hoàn trả cuối kỳ.</p>"),
    jsonld=[breadcrumb("Thuê Theo Tháng", "thuethang.html")],
)

# ---------------- support pages ----------------
PAGES["thutuc.html"] = dict(
    title="Thủ Tục Thuê Xe Máy Tại Văn Chính Hà Nội",
    description="Thủ tục thuê xe máy tại Văn Chính: giấy tờ cần thiết cho người Việt và khách nước ngoài, mức cọc theo loại xe, giờ nhận xe 9h-17h hàng ngày.",
    content=page_h1("Thủ Tục Thuê Xe Máy", "Giấy tờ, cọc và quy trình nhận - trả xe tại Văn Chính.", "fas fa-file-alt")
    + content_block(f'''<h2>Giấy tờ cần thiết</h2>
<ul>
<li>Khách Việt Nam: CCCD gắn chip bản gốc + giấy phép lái xe hợp lệ.</li>
<li>Khách nước ngoài: Hộ chiếu (Passport) + giấy phép lái xe được chấp nhận tại Việt Nam (GPLX Việt Nam, bằng quốc tế IDP còn hiệu lực theo đúng quy định hiện hành - xác nhận lại với cơ quan cấp khi dùng).</li>
</ul>
<h2>Tiền cọc</h2>
<p>Tiền cọc theo loại xe: từ 2.000.000đ (xe số), 3.000.000đ (xe tay ga), 5.000.000đ (xe cao cấp). Hoàn trả đầy đủ khi trả xe đúng hiện trạng. Việc giữ giấy tờ gốc thay tiền cọc chỉ áp dụng khi hai bên thỏa thuận.</p>
<h2>Quy trình nhận - trả xe</h2>
<ul>
<li>Bước 1: Gọi hotline hoặc chat Zalo để chọn xe và thời gian (giờ mở cửa <strong>9h - 17h hàng ngày</strong>).</li>
<li>Bước 2: Đến cửa hàng hoặc nhận xe giao tận nơi theo thỏa thuận.</li>
<li>Bước 3: Kiểm tra hiện trạng xe, mũ bảo hiểm, áo mưa; ký nhận xe.</li>
<li>Bước 4: Trả xe đúng giờ thỏa thuận trong giờ mở cửa; nhận lại cọc sau khi kiểm tra xe.</li>
</ul>''')
    + cta_block(),
    jsonld=[breadcrumb("Thủ Tục", "thutuc.html")],
)
PAGES["chinhsach.html"] = dict(
    title="Chính Sách Thuê Xe Máy - Văn Chính Hà Nội",
    description="Chính sách thuê xe máy tại Văn Chính: cọc và hoàn cọc, giao xe, bảo dưỡng, xử lý sự cố, giờ mở cửa 9h-17h hàng ngày.",
    content=page_h1("Chính Sách Thuê Xe", "Các quy định về cọc, giao xe, bảo dưỡng và hỗ trợ sự cố.", "fas fa-file-contract")
    + content_block(f'''<h2>Giờ mở cửa</h2>
<p>Văn Chính mở cửa <strong>9h - 17h hàng ngày</strong>, kể cả cuối tuần và ngày lễ.</p>
<h2>Cọc và hoàn cọc</h2>
<p>Tiền cọc theo loại xe (xem <a href="banggia.html" class="text-brand-600 dark:text-brand-400 font-semibold hover:underline">bảng giá</a>), hoàn trả đầy đủ khi xe được trả đúng hiện trạng, đúng giờ thỏa thuận.</p>
<h2>Giao xe tận nơi</h2>
<p>Văn Chính hỗ trợ giao xe tận nơi tại Hà Nội. Thời gian và chi phí giao xe thay đổi theo vị trí - luôn xác nhận qua hotline khi đặt.</p>
<h2>Bảo dưỡng và sự cố</h2>
<ul>
<li>Xe được bảo dưỡng định kỳ trước khi giao; mỗi xe kèm {", ".join(FACTS["included_with_bike"])}.</li>
<li>Sự cố nhỏ (thủng lốp): tìm tiệm sửa gần nhất, giữ hóa đơn để thỏa thuận.</li>
<li>Sự cố nặng không di chuyển được: dắt xe vào lề an toàn và gọi hotline {FACTS["phone"]} (trong giờ mở cửa) để được hướng dẫn.</li>
<li>Hư hỏng do lỗi sử dụng của khách: khách chịu chi phí sửa chữa theo thỏa thuận.</li>
</ul>''')
    + cta_block("Đọc kỹ chính sách trước khi thuê - gọi hotline nếu bạn cần làm rõ thêm."),
    jsonld=[breadcrumb("Chính Sách", "chinhsach.html")],
)
PAGES["baomat.html"] = dict(
    title="Chính Sách Bảo Mật - Văn Chính",
    description="Chính sách bảo mật thông tin khách hàng của dịch vụ cho thuê xe máy Văn Chính, Hà Nội.",
    content=page_h1("Chính Sách Bảo Mật", "Văn Chính thu thập và bảo vệ thông tin khách hàng như thế nào.", "fas fa-user-shield")
    + content_block('''<h2>Thông tin chúng tôi thu thập</h2>
<p>Khi bạn thuê xe, chúng tôi lưu thông tin tối thiểu cần thiết để thực hiện hợp đồng thuê: họ tên, số giấy tờ tùy thân, giấy phép lái xe, số điện thoại. Thông tin giấy tờ được hoàn trả/đối chiếu khi kết thúc hợp đồng thuê.</p>
<h2>Mục đích sử dụng</h2>
<ul>
<li>Xác minh danh tính người thuê xe theo quy định về cho thuê phương tiện.</li>
<li>Liên hệ về lịch nhận/trả xe và các thông tin dịch vụ bạn yêu cầu.</li>
</ul>
<p>Chúng tôi không bán, cho thuê hay chia sẻ thông tin cá nhân của bạn cho bên thứ ba ngoài mục đích nêu trên, trừ khi có yêu cầu của cơ quan có thẩm quyền theo quy định pháp luật.</p>
<h2>Website</h2>
<p>Site là trang tĩnh trên GitHub Pages, không có tài khoản người dùng, không dùng cookie theo dõi. Mọi liên hệ diễn ra qua hotline, Zalo hoặc email.</p>
<h2>Liên hệ</h2>
<p>Email: vanchinhnguyen1702@gmail.com - Hotline: 0989.595.533 (giờ mở cửa 9h - 17h hàng ngày).</p>'''),
    jsonld=[breadcrumb("Bảo Mật", "baomat.html")],
)
PAGES["dieukhoan.html"] = dict(
    title="Điều Khoản Thuê Xe Máy - Văn Chính Hà Nội",
    description="Điều khoản hợp đồng thuê xe máy tại Văn Chính: trách nhiệm khách hàng, hoàn cọc, hủy đặt xe, xử lý tranh chấp.",
    content=page_h1("Điều Khoản Thuê Xe", "Quy định chung khi thuê xe máy tại Văn Chính.", "fas fa-gavel")
    + content_block('''<h2>Trách nhiệm của khách hàng</h2>
<ul>
<li>Có giấy phép lái xe hợp lệ và giấy tờ tùy thân khi nhận xe.</li>
<li>Sử dụng xe đúng mục đích, không cho mượn lại, không dùng xe vi phạm pháp luật.</li>
<li>Chịu trách nhiệm vi phạm giao thông và hư hỏng xe do lỗi sử dụng trong thời gian thuê.</li>
<li>Trả xe đúng giờ thỏa thuận, trong giờ mở cửa 9h - 17h hàng ngày.</li>
</ul>
<h2>Trả xe muộn / hủy đặt</h2>
<p>Nếu cần trả xe muộn hoặc hủy đặt xe, vui lòng thông báo sớm nhất qua hotline để hai bên thỏa thuận. Điều kiện cụ thể được xác nhận khi nhận xe.</p>
<h2>Hoàn cọc</h2>
<p>Tiền cọc hoàn trả đầy đủ khi xe được trả đúng hiện trạng và đúng thời gian thỏa thuận. Trừ chi phí sửa chữa nếu xe hư hỏng do lỗi khách.</p>
<h2>Tranh chấp</h2>
<p>Mọi tranh chấp phát sinh được ưu tiên giải quyết bằng thỏa thuận giữa khách hàng và Văn Chính.</p>'''),
    jsonld=[breadcrumb("Điều Khoản", "dieukhoan.html")],
)

# ---------------- hubs ----------------
HUB_DEFS = [
    ("kinhnghiem", "Kinh Nghiệm", "KN", "kinh-nghiem",
     "Kinh nghiệm thuê xe máy tại Hà Nội: chọn xe theo mùa, theo lộ trình, theo nhóm khách; mẹo lấy xe nhanh và tiết kiệm."),
    ("antoan", "An Toàn", "AT", "an-toan",
     "An toàn khi đi xe máy tại Hà Nội và các cung đường ven: luật giao thông hiện hành, mũ bảo hiểm, lái xe đường trơn trượt, phối hợp giao thông đường trường."),
    ("xemay", "Xe Máy", "XM", "xe-may",
     "Tìm hiểu về xe máy: cấu tạo, bảo dưỡng cơ bản, so sánh dòng xe số và xe ga, chọn xe phù hợp nhu cầu thuê."),
    ("dulich", "Du Lịch", "DL", "du-lich",
     "Du lịch Hà Nội và vùng ven bằng xe máy: lịch trình, điểm đến mùa, chi phí tham khảo và cách tối ưu chuyến đi."),
    ("cungduong", "Cung Đường", "CD", "cung-duong",
     "Các cung đường phượt từ Hà Nội: Sóc Sơn, Ba Vì, Tam Đảo, Ninh Bình, Hòa Bình - mô tả cung, độ khó, thời điểm lý tưởng."),
    ("hoidap", "Hỏi Đáp", "HD", "hoi-dap",
     "Hỏi đáp nhanh về thuê xe máy, giấy tờ, luật giao thông đường bộ áp dụng cho xe máy tại Việt Nam."),
]
for hub_id, hub_name, cat, folder, desc in HUB_DEFS:
    PAGES[hub_id + ".html"] = dict(
        title=f"Cẩm Nang {hub_name} - Thuê Xe Máy Hà Nội - Văn Chính",
        description=desc + " Chuyên mục của Văn Chính - cho thuê xe máy Hà Nội.",
        content=hub_page(hub_id, hub_name, desc, cat, hub_name),
        jsonld=[breadcrumb("Cẩm Nang " + hub_name, hub_id + ".html")],
    )

def main():
    out = ROOT
    for filename, spec in PAGES.items():
        html = render_page(
            filename,
            spec["title"], spec["description"], spec["content"],
            extra_jsonld=spec.get("jsonld"),
            include_assistant=spec.get("include_assistant", False),
        )
        (out / filename).write_text(html, encoding="utf-8")
        print(f"wrote {filename} ({len(html)} bytes)")
    print(f"TOTAL pages: {len(PAGES)}")

if __name__ == "__main__":
    sys.exit(main())
