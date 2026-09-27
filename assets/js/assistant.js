/* assistant.js - simulated assistant (static demo, no backend, no paid LLM API).
   BUSINESS RULE: every business answer (hours, phone, deposit, delivery, support) is read from
   config/business-facts.json (fetched same-origin). This file must NOT hard-code business facts.
   Itinerary / food / mechanic content is generic editorial guidance only, not business claims. */

(function () {
  'use strict';

  var FALLBACK_FACTS = {
    phone: '0989.595.533',
    opening_hours: { display: '09:00–17:00 hàng ngày', opens: '09:00', closes: '17:00' }
  };
  var FACTS = FALLBACK_FACTS;

  fetch('config/business-facts.json')
    .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error('http ' + r.status)); })
    .then(function (j) {
      FACTS = {
        phone: j.phone || FALLBACK_FACTS.phone,
        opening_hours: j.opening_hours || FALLBACK_FACTS.opening_hours
      };
    })
    .catch(function () { /* fallback facts remain; static hosting always serves the file */ });

  function safeHTML(str) { return DOMPurify.sanitize(str); }

  /* ---------- Generic editorial content (NOT business facts) ---------- */
  var PLAN_1 = [
    '### 🏍️ Lịch Trình 1 Ngày Vi Vu Hà Nội',
    '*Lộ trình gợi ý: Long Biên - Phố Cổ - Hồ Tây*',
    '',
    '* **09:00:** Nhận xe tại Văn Chính (Ngõ 5 Nguyễn Văn Cừ). Ăn sáng Bún chả Hàng Than.',
    '* **09:30:** Check-in Cầu Long Biên lịch sử.',
    '* **10:30:** Lượn lờ Phố Cổ (Nhà Thờ Lớn, Hồ Gươm).',
    '* **12:00:** Ăn trưa Phở Bát Đàn hoặc Bún đậu mắm tôm Ngõ Phất Lộc.',
    '* **14:30:** Di chuyển lên Hồ Tây, uống cafe view hồ.',
    '* **16:30:** Ngắm hoàng hôn Hồ Tây và trả xe trước 17:00.',
    '',
    '**💡 Tip:** Đường Phố Cổ nhiều đường 1 chiều, chú ý biển báo!'
  ].join('\n');

  var PLAN_2 = [
    '### 🌲 Lịch Trình 2 Ngày 1 Đêm: Sóc Sơn - Hàm Lợn',
    '*Gợi ý trốn khói bụi thành phố - cắm trại chill*',
    '',
    '**Ngày 1:**',
    '* **08:30:** Thuê xe số (leo dốc khỏe).',
    '* **09:30:** Di chuyển hướng Cầu Nhật Tân -> Sóc Sơn.',
    '* **10:30:** Đến Núi Hàm Lợn. Dựng trại ven hồ.',
    '* **12:00:** BBQ ngoài trời; chiều trekking rừng thông, chụp ảnh.',
    '',
    '**Ngày 2:**',
    '* **06:00:** Đón bình minh, pha cafe.',
    '* **09:00:** Tham quan Đền Gióng.',
    '* **15:00:** Khởi hành về Hà Nội, trả xe.'
  ].join('\n');

  var PLAN_NIGHT = [
    '### 🌃 Gợi Ý Lượn Phố Buổi Tối',
    '* Lấy xe và trả xe trong giờ mở cửa ' + '09:00–17:00' + '.',
    '* Hóng gió cầu Chương Dương (đúng làn xe máy), lượn Hồ Tây.',
    '* Cuối tuần khu vực Hồ Gươm cấm xe cơ giới - kiểm tra trước khi đi.'
  ].join('\n');

  function planResponse(days) {
    if (days.indexOf('1 ngày') !== -1) return PLAN_1;
    if (days.indexOf('2 ngày') !== -1) return PLAN_2;
    return PLAN_NIGHT;
  }

  function foodResponse(input) {
    var q = input.toLowerCase();
    if (q.indexOf('phở') !== -1) {
      return '### 🍜 Quán Phở Gợi Ý\n* **Phở Lâm - Hàng Vải** - lõi rùa giòn, nước trong.\n* **Phở Lý Quốc Sư** - nước đậm đà.\n* **Phở Gà Nguyệt - Phủ Doãn** - phở trộn. *Giá tham khảo 50k-90k, kiểm tra khi đến.*';
    }
    if (q.indexOf('bún') !== -1) {
      return '### 🥗 Bún Chả & Bún Đậu Gợi Ý\n* **Bún Chả Hương Liên (Obama)** - Lê Văn Hưu.\n* **Bún Đậu Mắm Tôm Hàng Khay**.\n* **Bún Riêu Cua Hàng Bạc** - riêu cua thật.';
    }
    if (q.indexOf('cafe') !== -1 || q.indexOf('cà phê') !== -1) {
      return '### ☕ Cafe View Đẹp Gợi Ý\n* **Serein Cafe** - Ga Long Biên, view cầu Long Biên.\n* **Hanoi House Cafe** - Lý Quốc Sư, view Nhà Thờ Lớn.\n* **Cafe Giảng** - Nguyễn Hữu Huân, cafe trứng.';
    }
    return '### 😋 Gợi Ý Ăn Gì\nGần Văn Chính có nhiều quán ăn vặt khu Ngọc Lâm; hoặc ghé Phố Cổ thử **Xôi Yến** Nguyễn Hữu Huân.';
  }

  function mechanicResponse(symptom) {
    var q = symptom.toLowerCase();
    if (q.indexOf('không đề') !== -1 || q.indexOf('tắt máy') !== -1) {
      return '### ⚠️ Chẩn đoán: Hết ắc quy hoặc bugi ẩm\n1. Thử đạp cần khởi động (xe số).\n2. Kiểm tra gạt chân chống (xe ga).\n3. Không được thì gọi hotline ' + FACTS.phone + ' (trong giờ ' + FACTS.opening_hours.display + ') để được hướng dẫn.';
    }
    if (q.indexOf('lốp') !== -1 || q.indexOf('xăm') !== -1 || q.indexOf('thủng') !== -1) {
      return '### ⚠️ Chẩn đoán: Thủng săm/lốp\n1. Dừng xe vào lề an toàn.\n2. Tìm tiệm sửa xe gần nhất (tìm "Sửa xe máy" trên Google Maps).\n3. Không đi tiếp để tránh hỏng vành xe.';
    }
    if (q.indexOf('kêu') !== -1) {
      return '### ⚠️ Chẩn đoán: Nhông xích khô hoặc bộ nồi\n1. "Lạch cạch" ở hộp xích: tra dầu hoặc tăng xích.\n2. "Gào" khi lên ga: có thể do bộ nồi (côn) mòn.\n3. Đem xe đi kiểm tra tại tiệm tin cậy.';
    }
    return '### ℹ️ Tư vấn kỹ thuật\nHiện tượng bạn mô tả cần thợ kiểm tra trực tiếp. Bạn có thể nhắn qua mục Hỗ Trợ trên trang hoặc gọi hotline ' + FACTS.phone + ' để được hướng dẫn thêm.';
  }

  function procedureResponse(userType) {
    var hours = FACTS.opening_hours.display;
    if (userType === 'student') {
      return '### 🎓 Thủ Tục Cho Sinh Viên\n* **Giấy tờ:** CCCD gốc, thẻ sinh viên, GPLX hợp lệ.\n* **Cọc:** theo loại xe (xem bảng giá). Tiền cọc hoàn trả khi trả xe đúng hiện trạng.\n* **Thanh toán:** chuyển khoản hoặc tiền mặt.\n* **Lưu ý:** luôn xác nhận mức cọc và giá sinh viên qua hotline trước khi đến nhận xe (giờ làm việc ' + hours + ').';
    }
    if (userType === 'tourist') {
      return '### ✈️ Thủ Tục Cho Khách Du Lịch\n* **Giấy tờ:** Hộ chiếu (Passport) hoặc CCCD, GPLX hợp lệ (khách nước ngoài cần GPLX/Bằng quốc tế được chấp nhận tại VN).\n* **Cọc:** theo loại xe (xem bảng giá); thỏa thuận giữ giấy tờ thay cọc nếuhai bên đồng ý - xác nhận trước qua hotline.\n* **Lưu ý:** nhận/trả xe trong giờ ' + hours + '.';
    }
    if (userType === 'luxury') {
      return '### 💎 Thủ Tục Thuê Xe Cao Cấp\n* **Giấy tờ:** CCCD gắn chip chính chủ, GPLX hợp lệ.\n* **Cọc:** theo bảng giá dòng cao cấp (xem banggia.html).\n* **Lưu ý:** kiểm tra kỹ hiện trạng xe trước khi nhận; nhận xe trong giờ ' + hours + '.';
    }
    return '### 💼 Thủ Tục Chung\n* **Giấy tờ:** CCCD gắn chip chính chủ + GPLX hợp lệ.\n* **Cọc:** theo loại xe (xem bảng giá), hoàn trả khi trả xe đúng hiện trạng.\n* **Giao xe tận nơi:** có thể sắp đặt, thời gian/chi phí xác nhận qua hotline.\n* **Giờ làm việc:** ' + hours + '.';
  }

  function simulateAIResponse(promptType, inputData) {
    return new Promise(function (resolve) {
      setTimeout(function () {
        var response = '';
        if (promptType === 'plan') response = planResponse(inputData);
        else if (promptType === 'food') response = foodResponse(inputData);
        else if (promptType === 'mechanic') response = mechanicResponse(inputData);
        else if (promptType === 'procedure') response = procedureResponse(inputData);
        resolve(response);
      }, 1200);
    });
  }

  /* ---------- Feature handlers ---------- */
  function runHandler(config) {
    var btn = document.getElementById(config.btn);
    var result = document.getElementById(config.result);
    var content = document.getElementById(config.content);
    var loading = document.getElementById(config.loading);
    var input = document.getElementById(config.input);
    var defaultBtnText = config.btnText;

    if (!btn || !result) return;

    var form = btn.closest('form');
    if (form) form.addEventListener('submit', function (e) { e.preventDefault(); btn.click(); });

    btn.addEventListener('click', function (e) {
      e.preventDefault();
      var value = input ? (input.value || '') : '';
      var input2 = document.getElementById(config.input2);
      if (input2) value = value + ' ' + (input2.value || '');
      if (config.requireInput && !value) return;

      btn.disabled = true; btn.innerText = '⏳ Đang xử lý...';
      result.classList.add('hidden');
      if (loading) loading.classList.remove('hidden');

      simulateAIResponse(config.type, value).then(function (data) {
        content.innerHTML = safeHTML(marked.parse(data));
        result.classList.remove('hidden');
      }).catch(function () {
        alert('Có lỗi xảy ra. Vui lòng thử lại sau!');
      }).finally(function () {
        if (loading) loading.classList.add('hidden');
        btn.disabled = false; btn.innerText = defaultBtnText;
      });
    });
  }

  runHandler({ type: 'plan', btn: 'btn-generate-plan', result: 'ai-result-plan', content: 'ai-content-plan', loading: 'ai-loading-plan', input: 'ai-days', btnText: 'Tạo Lịch Trình' });
  runHandler({ type: 'food', btn: 'btn-generate-food', result: 'ai-result-food', content: 'ai-content-food', loading: 'ai-loading-food', input: 'food-location', input2: 'food-craving', btnText: 'Tìm Quán Ngon' });
  runHandler({ type: 'mechanic', btn: 'btn-generate-mech', result: 'ai-result-mech', content: 'ai-content-mech', loading: 'ai-loading-mech', input: 'mech-input', requireInput: true, btnText: 'Chẩn Đoán Ngay' });
  runHandler({ type: 'procedure', btn: 'btn-generate-proc', result: 'ai-result-proc', content: 'ai-content-proc', loading: 'ai-loading-proc', input: 'proc-input', requireInput: true, btnText: 'Tra Cứu Thủ Tục' });
})();
