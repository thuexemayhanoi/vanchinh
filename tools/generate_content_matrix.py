#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""generate_content_matrix.py - deterministic planner for the 2,000-article matrix.

Generates data/content-matrix.csv with EXACTLY:
- 2000 production rows
- 40 batches x 50 rows
- category allocation: KN350 AT300 XM350 DL400 CD300 HD300

Rows are PLANNED only; no article bodies are written by this tool.
Deterministic: same input -> byte-identical CSV (sorted, stable ids).
"""
import csv
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "content-matrix.csv"

CATEGORIES = {
    "KN": ("Kinh nghiệm", "kinhnghiem.html", 350),
    "AT": ("An toàn", "antoan.html", 300),
    "XM": ("Xe máy", "xemay.html", 350),
    "DL": ("Du lịch", "dulich.html", 400),
    "CD": ("Cung đường", "cungduong.html", 300),
    "HD": ("Hỏi đáp", "hoidap.html", 300),
}
CAT_FOLDER = {"KN": "kinh-nghiem", "AT": "an-toan", "XM": "xe-may",
              "DL": "du-lich", "CD": "cung-duong", "HD": "hoi-dap"}
# Source of truth for per-category commercial targets: config/seo-ownership.json
# (docs/SEO-OWNERSHIP.md rule 3); keep code and matrix in lockstep with the docs.
OWNERSHIP = json.loads((ROOT / "config" / "seo-ownership.json").read_text(encoding="utf-8"))
COMMERCIAL = OWNERSHIP["article_commercial_targets"]
assert set(COMMERCIAL) == set(CATEGORIES), "article_commercial_targets must cover all categories"
INTENTS = {"KN": "informational", "AT": "informational", "XM": "informational",
           "DL": "informational", "CD": "informational", "HD": "informational"}
REQUIRES_SOURCES = {"AT": True, "HD": True}  # legal/safety categories need primary sources

BIKES = ["Wave Alpha", "Sirius", "Vision", "Air Blade", "Exciter", "Winner X", "SH", "Liberty", "Xe máy điện"]
AUDIENCES = ["sinh viên", "du khách", "người đi làm", "khách nước ngoài", "gia đình", "người mới lái", "dân phượt"]
MONTHS = ["tháng 1", "tháng 2", "tháng 3", "tháng 4", "tháng 5", "tháng 6",
          "tháng 7", "tháng 8", "tháng 9", "tháng 10", "tháng 11", "tháng 12",
          "mùa hè", "mùa đông", "mùa mưa", "dịp Tết", "dịp 30/4", "dịp 2/9"]
DISTRICTS = ["Long Biên", "Gia Lâm", "Hoàn Kiếm", "Phố Cổ", "Ba Đình", "Tây Hồ",
             "Hai Bà Trưng", "Cầu Giấy", "Đống Đa", "Thanh Xuân", "Nam Từ Liêm", "Hoàng Mai"]
DESTINATIONS = ["Sóc Sơn", "Tam Đảo", "Ba Vì", "Ninh Bình", "Tràng An", "Hòa Bình",
                "Thung Nai", "Mộc Châu", "Cúc Phương", "Perfume Pagoda", "Chùa Hương",
                "Đền Gióng", "Hàm Lợn", "Bát Tràng", "Đường Lâm", "Vũng Chưa", "Cửa Lò",
                "Thành nhà Hồ", "Kim Sơn", "Yên Tử", "Côn Sơn", "Đại Lải", "Đồng Mô", "Quán Sơn"]
ROUTES = ["Hà Nội - Tam Đảo", "Hà Nội - Ba Vì", "Hà Nội - Hàm Lợn", "Hà Nội - Chùa Hương",
          "Hà Nội - Ninh Bình", "Hà Nội - Tràng An", "Hà Nội - Thung Nai", "Hà Nội - Mộc Châu",
          "Hà Nội - Cúc Phương", "Hà Nội - Đại Lải", "Hà Nội - Đường Lâm", "Hà Nội - Bát Tràng",
          "Hà Nội - Kim Sơn", "Hà Nội - Yên Tử", "Hà Nội - Đại Lải vòng hồ", "Sóc Sơn - Hàm Lợn",
          "Hà Nội - Perfume Pagoda"]
ROAD_TOPICS = ["quy định nón bảo hiểm", "giấy phép lái xe A1", "nồng độ cồn",
               "giới hạn tốc độ xe máy", "đèn tín hiệu giao thông", "đi xe trong mưa",
               "phanh số và phanh đĩa", "lốp xe máy an toàn", "đi đường đèo",
               "đi đường cao tốc", "chở người ngồi sau", "chở trẻ em trên xe",
               "gương chiếu hậu", "còi và đèn xe", "sát hạch giấy phép lái xe",
               "bảo hiểm trách nhiệm dân sự", "mũ bảo hiểm đạt chuẩn", "đi xe đêm",
               "giữ khoảng cách an toàn", "bạn đồng hành trên xe"]

def slugify(text):
    import unicodedata
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.lower()
    for ch in "đĐ":
        text = text.replace(ch, "d")
    keep = []
    for ch in text:
        if ch.isalnum():
            keep.append(ch)
        elif ch in " -_/":
            keep.append("-")
    slug = "".join(keep).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug

def uniq(seq):
    seen = set()
    out = []
    for item in seq:
        key = item[1]
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out

def build_kn():
    rows = []
    for bike in BIKES:
        rows.append((f"kinh nghiệm thuê {bike} ở Hà Nội", f"Kinh nghiệm thuê xe {bike} tại Hà Nội: chọn xe, kiểm tra và nhận xe đúng cách"))
    for aud in AUDIENCES:
        rows.append((f"kinh nghiệm thuê xe máy Hà Nội cho {aud}", f"Kinh nghiệm thuê xe máy tại Hà Nội dành cho {aud}"))
    for d in DISTRICTS:
        rows.append((f"kinh nghiệm thuê xe máy tại {d}", f"Kinh nghiệm thuê xe máy tại {d}: điều cần biết trước khi nhận xe"))
    for m in MONTHS:
        rows.append((f"thuê xe máy Hà Nội {m}", f"Thuê xe máy Hà Nội {m}: kinh nghiệm chọn xe theo thời điểm"))
    for bike in BIKES:
        for m in ["mùa hè", "mùa đông", "mùa mưa", "Tết", "cao điểm du lịch"]:
            rows.append((f"thuê {bike} Hà Nội {m}", f"Thuê {bike} tại Hà Nội {m}: kinh nghiệm đặt xe sớm"))
    for bike in BIKES:
        for p in ["giá tốt", "xe mới", "cọc nhẹ", "xe bền", "tiết kiệm xăng"]:
            rows.append((f"mẹo thuê {bike} {p} ở Hà Nội", f"Mẹo thuê {bike} {p} khi đến Hà Nội"))
    for d in DISTRICTS:
        for p in ["giá tốt", "gần cầu", "đi Phố Cổ", "đi sân bay", "đi huyện Soc Sơn".replace("Soc Sơn", "Sóc Sơn")]:
            rows.append((f"thuê xe máy {d} {p}", f"Thuê xe máy tại {d} khi cần {p}"))
    for bike in BIKES:
        for aud in AUDIENCES:
            rows.append((f"thuê {bike} cho {aud} ở Hà Nội", f"Thuê {bike} tại Hà Nội dành cho {aud}: những điều nên biết"))
    for bike in BIKES:
        for d in DISTRICTS:
            rows.append((f"thuê {bike} tại {d}", f"Thuê {bike} tại {d}: kinh nghiệm nhận xe nhanh"))
    for i in range(1, 30):
        rows.append((f"kinh nghiệm thuê xe máy Hà Nội phần {i}", f"Kinh nghiệm thuê xe máy Hà Nội - phần {i}: lưu ý thực tế"))
    for bike in BIKES:
        for topic in ["đổi nhớt", "tra dầu xích", "thay bugi", "kiểm tra lốp", "phanh", "ắc quy", "đèn xe", "lọc gió"]:
            rows.append((f"{bike}: bảo dưỡng {topic}", f"Bảo dưỡng {bike}: {topic} đúng kỹ thuật"))
    for bike in BIKES:
        for d in DISTRICTS:
            rows.append((f"thuê {bike} ở {d} có tốt không", f"Thuê {bike} tại {d}: trải nghiệm thực tế"))
    for bike in BIKES:
        for r in ["đường phố", "đường đèo", "đường trường", "đi cắm trại", "đi làm hàng ngày", "chở người ngồi sau"]:
            rows.append((f"{bike} khi {r}", f"{bike} khi {r}: ưu nhược điểm"))
    return uniq(rows)[:350]

def build_at():
    rows = []
    for t in ROAD_TOPICS:
        rows.append((f"{t} khi đi xe máy", f"{t.capitalize()} khi đi xe máy: quy định và lưu ý an toàn"))
    for t in ROAD_TOPICS:
        for d in ["Hà Nội", "đường trường", "nội thành", "đường đèo", "mùa mưa",
                  "mùa khô", "đêm khuya", "giờ cao điểm", "cuối tuần", "khu phố cổ"]:
            rows.append((f"{t} khi đi xe máy {d}", f"{t.capitalize()} khi đi xe máy tại {d}"))
    for b in ["nón bảo hiểm fullface", "găng tay đi xe", "áo mưa đi xe", "kính đi xe máy", "bình chữa cháy nhỏ", "bộ dụng cụ sửa xe mini"]:
        rows.append((f"chọn {b} đúng chuẩn", f"Cách chọn {b} đúng chuẩn khi đi xe máy"))
    for cond in ["đi trong mưa", "đi đường trơn", "đi ngập nước", "đi sương mù", "đi nắng gắt", "đi gió lớn", "đi đường tối", "đi đường đông"]:
        for who in ["người mới lái", "người đi phượt", "khách nước ngoài"]:
            rows.append((f"an toàn {cond} cho {who}", f"An toàn khi {cond} - hướng dẫn cho {who}"))
    for cond in ["đi trong mưa", "đi đường trơn", "đi ngập nước"]:
        for who in ["người đi làm", "bạn đồng hành"]:
            rows.append((f"an toàn {cond} với {who}", f"An toàn khi {cond} cùng {who}"))
    for b in ["nón bảo hiểm trẻ em", "khóa cổ xe máy", "hãm phanh khẩn cấp", "đèn báo hiệu rẽ", "bình xăng dự phòng"]:
        rows.append((f"sử dụng {b} an toàn", f"Sử dụng {b} đúng cách để an toàn"))
    for i in range(1, 40):
        rows.append((f"an toàn khi đi xe máy tại Hà Nội phần {i}", f"An toàn khi đi xe máy tại Hà Nội - phần {i}"))
    return uniq(rows)[:300]

def build_xm():
    rows = []
    for bike in BIKES:
        rows.append((f"đánh giá {bike}", f"Đánh giá {bike}: có đáng thuê khi đến Hà Nội?"))
        rows.append((f"{bike} tiêu tốn xăng thế nào", f"{bike} và mức tiêu hao xăng trong nội thành Hà Nội"))
        rows.append((f"kinh nghiệm lái {bike} trong phố", f"Kinh nghiệm lái {bike} trong phố cổ Hà Nội"))
    for topic in ["đổi nhớt", "tra dầu xích", "thay bugi", "kiểm tra lốp", "phanh đĩa", "ắc quy",
                  "rửa xe định kỳ", "chỉnh chế độ hòa khí", "thay lốp", "đèn xe", "lọc gió", "giảm xóc"]:
        rows.append((f"bảo dưỡng xe máy {topic}", f"Bảo dưỡng xe máy: {topic} đúng kỹ thuật"))
    for cmp in [("xe số", "xe ga"), ("Wave Alpha", "Sirius"), ("Vision", "Air Blade"), ("xe máy xăng", "xe máy điện"), ("xe ga", "xe côn tay")]:
        rows.append((f"so sánh {cmp[0]} và {cmp[1]}", f"So sánh {cmp[0]} và {cmp[1]}: nên thuê dòng nào?"))
    for i in range(1, 30):
        rows.append((f"kiến thức xe máy cơ bản phần {i}", f"Kiến thức xe máy cơ bản cho người thuê xe - phần {i}"))
    for bike in BIKES:
        for aud in ["người đi làm", "sinh viên", "khách nước ngoài"]:
            rows.append((f"{bike} có phù hợp cho {aud}", f"{bike} có phù hợp cho {aud} khi thuê ở Hà Nội?"))
    for bike in BIKES[:6]:
        for p in ["cốp xe", "mức tiêu thụ nhiên liệu", "độ bền máy", "giá thuê tham khảo", "phụ tùng phổ biến"]:
            rows.append((f"{bike} {p}", f"{bike}: {p} cần biết trước khi thuê"))
    for bike in BIKES:
        for topic in ["đổi nhớt", "tra dầu xích", "thay bugi", "kiểm tra lốp", "phanh", "ắc quy", "đèn xe", "lọc gió"]:
            rows.append((f"{bike}: bảo dưỡng {topic}", f"Bảo dưỡng {bike}: {topic} đúng kỹ thuật"))
    for bike in BIKES:
        for d in DISTRICTS:
            rows.append((f"thuê {bike} ở {d} có tốt không", f"Thuê {bike} tại {d}: trải nghiệm thực tế"))
    for bike in BIKES:
        for r in ["đường phố", "đường đèo", "đường trường", "đi cắm trại", "đi làm hàng ngày", "chở người ngồi sau"]:
            rows.append((f"{bike} khi {r}", f"{bike} khi {r}: ưu nhược điểm"))
    return uniq(rows)[:350]

def build_dl():
    rows = []
    for d in DESTINATIONS:
        rows.append((f"du lịch {d} bằng xe máy", f"Du lịch {d} bằng xe máy từ Hà Nội: lộ trình và chuẩn bị"))
    for d in DESTINATIONS[:20]:
        for p in ["2 ngày 1 đêm", "1 ngày", "cuối tuần"]:
            rows.append((f"du lịch {d} {p}", f"Lịch trình du lịch {d} {p} bằng xe máy"))
    for d in DESTINATIONS:
        rows.append((f"kinh nghiệm du lịch {d}", f"Kinh nghiệm du lịch {d}: ăn ở, đi lại, chi phí"))
    for m in MONTHS:
        rows.append((f"đi đâu Hà Nội {m} bằng xe máy", f"Gợi ý điểm đến quanh Hà Nội {m} bằng xe máy"))
    for p in ["chụp ảnh sống ảo", "cắm trại", "check-in cafe", "đi phượt nhóm", "săn mây", "suối thác"]:
        rows.append((f"du lịch quanh Hà Nội {p}", f"Du lịch quanh Hà Nội: {p} bằng xe máy"))
    for i in range(1, 30):
        rows.append((f"gợi ý du lịch Hà Nội bằng xe máy phần {i}", f"Gợi ý du lịch quanh Hà Nội bằng xe máy - phần {i}"))
    for d in DESTINATIONS:
        for m in ["mùa hoa", "mùa lá đỏ", "mùa nước nổi", "cuối tuần"]:
            rows.append((f"{d} {m}", f"Đi {d} {m} bằng xe máy: thời điểm và chuẩn bị"))
    for d in DESTINATIONS:
        for b in ["xe số", "xe ga", "xe máy điện"]:
            rows.append((f"đi {d} bằng {b}", f"Đi {d} bằng {b}: nên hay không?"))
    for d in DESTINATIONS:
        for a in ["cặp đôi", "nhóm bạn", "gia đình có trẻ em", "người đi một mình"]:
            rows.append((f"{d} dành cho {a}", f"Trải nghiệm {d} dành cho {a}"))
    for d in DESTINATIONS:
        rows.append((f"điểm ăn uống gần {d}", f"Điểm ăn uống gần {d} khi đi phượt"))
    for d in DESTINATIONS:
        rows.append((f"chỗ nghỉ gần {d}", f"Chỗ nghỉ gần {d}: gợi ý cho chuyến đi 2 ngày"))
    return uniq(rows)[:400]

def build_cd():
    rows = []
    for r in ROUTES:
        rows.append((f"cung đường {r}", f"Cung đường {r}: mô tả, độ khó và điểm dừng"))
    for r in ROUTES:
        for p in ["cho người mới", "cuối tuần", "đi nhóm"]:
            rows.append((f"cung đường {r} {p}", f"Cung đường {r} {p}: kinh nghiệm đi thực tế"))
    for r in ROUTES:
        for t in ["mùa khô", "mùa mưa"]:
            # t already contains "mùa"; avoid duplicated "mùa mùa" in keyword/title
            rows.append((f"cung đường {r} {t}", f"Cung đường {r} vào {t}: kinh nghiệm thực tế"))
    for i in range(1, 40):
        rows.append((f"cung đường phượt Hà Nội phần {i}", f"Cung đường phượt từ Hà Nội - phần {i}"))
    for r in ROUTES[:12]:
        rows.append((f"bản đồ cung đường {r}", f"Bản đồ và lộ trình chi tiết cung đường {r}"))
    for r in ROUTES:
        for b in ["xe số", "xe ga", "xe máy điện"]:
            rows.append((f"{r} bằng {b}", f"Chinh phục cung đường {r} bằng {b}"))
    for r in ROUTES:
        for a in ["người mới đi phượt", "nhóm 3-5 xe", "cặp đôi"]:
            rows.append((f"{r} dành cho {a}", f"Cung đường {r} dành cho {a}"))
    for r in ROUTES:
        for s2 in ["điểm dừng nghỉ", "trạm xăng", "quán ăn dọc đường", "điểm chụp ảnh"]:
            rows.append((f"{r}: {s2}", f"Cung đường {r}: {s2} nên biết"))
    for r in ROUTES:
        rows.append((f"chi phí đi {r}", f"Chi phí tham khảo khi đi {r}"))
    return uniq(rows)[:300]

def build_hd():
    rows = []
    qs = [
        "thuê xe máy ở Hà Nội cần giấy tờ gì",
        "thuê xe máy Hà Nội cần bằng lái gì",
        "khách nước ngoài thuê xe máy ở Việt Nam cần gì",
        "bằng lái quốc tế có dùng được ở Việt Nam không",
        "thuê xe máy bị phạt nguợt thế nào".replace("nguợt", "nợt"),
        "đi xe máy không có bằng lái bị phạt bao nhiêu",
        "nồng độ cồn khi đi xe máy quy định thế nào",
        "chở người ngồi sau mấy tuổi được phép",
        "xe máy được chở bao nhiêu người",
        "giới hạn tốc độ xe máy trong nội thành là bao nhiêu",
        "nón bảo hiểm loại nào đạt chuẩn",
        "bảo hiểm xe máy bắt buộc không",
        "thuê xe máy giao tận nơi có không",
        "thuê xe máy Hà Nội giá bao nhiêu",
        "thuê xe máy bị thủng lốp thì làm sao",
        "thuê xe máy đi tỉnh được không",
        "để hộ chiếu thuê xe có an toàn không",
        "trả xe thuê muộn bị tính sao",
        "xe máy điện có cần bằng lái không",
        "chở trẻ em trên xe máy quy định thế nào",
        "đi xe máy trên cao tốc có được không",
        "uống bia bao nhiêu là vượt ngưỡng phạt",
        "thuê xe máy có được thử xe trước không",
        "thuê xe máy cần đặt cọc bao nhiêu",
        "mất chìa khóa xe thuê phải làm sao",
        "xe thuê bị hư máy giữa đường xử lý thế nào",
        "thuê xe máy dịp Tết có tăng giá không",
        "thuê xe máy tự lái có cần hộ khẩu không",
        "giao xe tận nơi có mất phí không",
        "có nên đặt xe máy online trước không",
    ]
    for q in qs:
        rows.append((q, q.capitalize() + "?"))
        rows.append((q + " 2026", q.capitalize() + " theo quy định hiện hành?"))
    for i in range(1, 60):
        rows.append((f"hỏi đáp thuê xe máy Hà Nội phần {i}", f"Hỏi đáp về thuê xe máy tại Hà Nội - phần {i}"))
    for q in qs:
        for p in ["khi thuê xe", "cho người mới"]:
            rows.append((q + " " + p, q.capitalize() + f" {p}?"))
    for q in qs:
        for p in ["ở Long Biên", "khi đi du lịch", "cho sinh viên", "cho khách nước ngoài", "khi thuê dài ngày"]:
            rows.append((q + " " + p, q.capitalize() + f" {p}?"))
    return uniq(rows)[:300]

BUILDERS = {"KN": build_kn, "AT": build_at, "XM": build_xm, "DL": build_dl, "CD": build_cd, "HD": build_hd}

def main():
    all_rows = []
    for cat in ["KN", "AT", "XM", "DL", "CD", "HD"]:
        name, hub, count = CATEGORIES[cat]
        topics = BUILDERS[cat]()
        if len(topics) < count:
            print(f"ERROR: category {cat} generated only {len(topics)} unique topics (need {count})", file=sys.stderr)
            return 1
        for i in range(count):
            kw, title = topics[i]
            slug = f"{cat.lower()}-{i+1:04d}-{slugify(title)}"
            all_rows.append({
                "article_id": f"{cat}-{i+1:04d}",
                "batch_id": "",  # assigned after sort
                "category": cat,
                "status": "PLANNED",
                "primary_keyword": kw,
                "secondary_keywords": f"{name.lower()}; {kw.split()[0]}",
                "search_intent": INTENTS[cat],
                "working_title": title,
                "slug": slug,
                "output_path": f"cam-nang/{CAT_FOLDER[cat]}/{slug}.html",
                "parent_hub": hub,
                "requires_sources": "true" if cat in REQUIRES_SOURCES else "false",
                "source_policy": "OFFICIAL_VN_PRIMARY" if cat in REQUIRES_SOURCES else "EDITORIAL_ONLY",
                "internal_link_targets": f"{hub};kinhnghiem.html",
                "commercial_link_target": COMMERCIAL[cat],
                "author": "Văn Chính Editorial",
                "score": "",
                "quality_status": "",
                "repair_attempts": "0",
                "published_date": "",
                "last_checked": "",
                "notes": "",
            })
    # deterministic order: category then index; assign 40x50 batches
    all_rows.sort(key=lambda r: r["article_id"])
    assert len(all_rows) == 2000, len(all_rows)
    for idx, row in enumerate(all_rows):
        row["batch_id"] = f"B{idx // 50 + 1:02d}"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        w.writeheader()
        w.writerows(all_rows)
    print(f"wrote {OUT} rows={len(all_rows)}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
