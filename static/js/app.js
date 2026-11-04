// MediMind Clinical AI - Medical Ocean Blue & Navy Interaction Logic
// Features: Multimodal Gemini Vision, RAG, Double Guardrails, Bilingual i18n, RBAC, Profile & Scan Dataset Management

const chatHistory = [];
let currentLang = 'vi';
let currentRole = 'patient';
let currentUser = JSON.parse(localStorage.getItem('medimind_user') || 'null');
if (!currentUser) {
  currentUser = {
    id: 8429,
    name: 'Nguyễn Thành Khiêm',
    badge: 'BN',
    role: 'Bệnh nhân',
    personal_info: 'Nữ • 24/10/1997 • 0971221306',
    phone: '0971221306',
    dob: '1997-10-24',
    gender: 'Nữ',
    blood_type: 'O+'
  };
}
let pendingTabAfterLogin = null;
let selectedChatImageBase64 = null;
let chatSessions = JSON.parse(localStorage.getItem('medimind_chat_sessions_v2') || '[]');

// ==========================================
// Bilingual i18n Dictionary (VI / EN)
// ==========================================
const translations = {
  vi: {
    brand_subtitle: "HIPAA Compliant • Phác đồ MedlinePlus",
    nav_chat: "Trang chủ",
    nav_ocr: "Đọc đơn thuốc",
    nav_booking: "Bệnh viện",
    nav_doctor: "Bệnh án của tôi",
    nav_admin: "Hạ tầng Cloud",
    nav_login: "Đăng nhập",
    nav_start: "Bắt đầu ngay",
    user_role: "Bác sĩ lâm sàng",
    hero_badge: "Dự án AI vì sức khỏe cộng đồng 2026",
    hero_title_1: "Trợ lý sức khỏe",
    hero_title_2: "thông minh",
    hero_desc: "Hỗ trợ phân tích triệu chứng, đọc đơn thuốc và cung cấp thông tin y tế có nguồn tham khảo từ các tài liệu y khoa đáng tin cậy, được hỗ trợ bởi trí tuệ nhân tạo tiên tiến.",
    hero_btn_check: "Kiểm tra triệu chứng",
    hero_btn_scan: "Đọc đơn thuốc",
    trust_security: "Bảo mật thông tin",
    trust_support: "Hỗ trợ 24/7",
    trust_banner: "Đã hỗ trợ hơn <strong class=\"text-slate-800 font-bold\">15.200+</strong> lượt sàng lọc lâm sàng theo phác đồ MedlinePlus",
    chip_hr: "Nhịp tim",
    chip_info: "Thông tin y khoa",
    chip_source: "Từ nguồn uy tín",
    chat_assistant_title: "Trợ lý MediMind AI",
    chat_status: "Đang hoạt động",
    quick_1: "🩺 Sốt 38.5°C & đau rát họng",
    quick_2: "⚠️ Đau thắt ngực, khó thở",
    quick_3: "💊 Lịch uống đơn thuốc sau ăn?",
    quick_4: "🏥 Gợi ý chuyên khoa khám",
    quick_prompt_text_1: "Tôi bị sốt 38.5 độ và đau rát họng hai hôm nay, nuốt đau",
    quick_prompt_text_2: "Tôi bị đau thắt ngực dữ dội, vã mồ hôi và khó thở lan ra cánh tay trái",
    quick_prompt_text_3: "Sau khi bóc tách đơn thuốc, tôi cần uống thuốc trước hay sau bữa ăn?",
    quick_prompt_text_4: "Tôi bị đau thượng vị cồn cào sau khi ăn thì nên đăng ký khám chuyên khoa nào?",
    chat_input_placeholder: "Mô tả triệu chứng (ví dụ: đau ngực, sốt cao, đau dạ dày) hoặc gửi ảnh đơn thuốc...",
    disclaimer_footer_text: "⚠️ Dự án thử nghiệm công nghệ y tế phục vụ giáo dục • ",
    disclaimer_footer_btn: "Miễn trừ trách nhiệm",
    typing_vision: "Gemini Vision đang phân tích hình thái học...",
    typing_guideline: "Đang đối soát phác đồ y khoa...",
    patient_label: "Vừa xong • Bệnh nhân",
    server_error: "Không thể kết nối đến máy chủ.",
    risk_safe: "An toàn",
    risk_moderate: "Theo dõi",
    risk_emergency: "Cần Cấp cứu",
    default_image_prompt: "Xin bác sĩ quan sát bức ảnh và phân tích giúp tôi dấu hiệu tổn thương trên da."
  },
  en: {
    brand_subtitle: "HIPAA Compliant • MedlinePlus Protocols",
    nav_chat: "Home",
    nav_ocr: "Prescriptions",
    nav_booking: "Hospitals",
    nav_doctor: "My Health Record",
    nav_admin: "Cloud Infrastructure",
    nav_login: "Sign In",
    nav_start: "Get Started",
    user_role: "Clinical Physician",
    hero_badge: "Community Health AI Initiative 2026",
    hero_title_1: "Smart Healthcare",
    hero_title_2: "Assistant",
    hero_desc: "AI-powered clinical triage, prescription analysis, and evidence-grounded health assistance referenced from trusted medical guidelines.",
    hero_btn_check: "Check Symptoms",
    hero_btn_scan: "Scan Prescription",
    trust_security: "Data Security",
    trust_support: "24/7 Support",
    trust_banner: "Assisted over <strong class=\"text-slate-800 font-bold\">15,200+</strong> clinical screenings based on MedlinePlus protocols",
    chip_hr: "Heart Rate",
    chip_info: "Medical Info",
    chip_source: "From trusted sources",
    chat_assistant_title: "MediMind AI Assistant",
    chat_status: "Online",
    quick_1: "📷 Skin Image AI",
    quick_2: "🔍 Unilateral Blisters?",
    quick_3: "🌡️ Safe Antipyretic?",
    quick_4: "💊 Need Antibiotics?",
    quick_prompt_text_2: "I have itchy blisters clustered on one side of my torso",
    quick_prompt_text_3: "What is a safe fever reducer medication?",
    quick_prompt_text_4: "Do I need to take antibiotics for a cold or sore throat?",
    chat_input_placeholder: "Describe symptoms or upload a skin lesion photo...",
    disclaimer_footer_text: "⚠️ Educational Health AI Prototype • ",
    disclaimer_footer_btn: "Medical Disclaimer",
    typing_vision: "Gemini Vision is analyzing morphology...",
    typing_guideline: "Cross-referencing medical guidelines...",
    patient_label: "Just now • Patient",
    server_error: "Unable to connect to server.",
    risk_safe: "Safe",
    risk_moderate: "Monitor",
    risk_emergency: "Emergency",
    default_image_prompt: "Please analyze this clinical image and assess the lesion characteristics on the skin."
  }
};

// ==========================================
// Language Switching Functions
// ==========================================
function toggleLanguageDropdown(e) {
  if (e) e.stopPropagation();
  const menu = document.getElementById('lang-dropdown-menu');
  const arrow = document.getElementById('lang-dropdown-arrow');
  if (menu) menu.classList.toggle('hidden');
  if (arrow) arrow.classList.toggle('rotate-180');
}

function closeLanguageDropdown() {
  const menu = document.getElementById('lang-dropdown-menu');
  const arrow = document.getElementById('lang-dropdown-arrow');
  if (menu) menu.classList.add('hidden');
  if (arrow) arrow.classList.remove('rotate-180');
}

function setLanguage(lang) {
  currentLang = lang;
  closeLanguageDropdown();
  applyLanguage();
}

function applyLanguage() {
  const dict = translations[currentLang] || translations.vi;
  const currentLangCode = document.getElementById('current-lang-code');
  if (currentLangCode) currentLangCode.innerText = currentLang.toUpperCase();

  const checkVi = document.getElementById('check-vi');
  const checkEn = document.getElementById('check-en');
  if (checkVi) checkVi.classList.toggle('hidden', currentLang !== 'vi');
  if (checkEn) checkEn.classList.toggle('hidden', currentLang !== 'en');

  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    if (dict[key]) {
      el.innerHTML = dict[key];
    }
  });

  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    const key = el.getAttribute('data-i18n-placeholder');
    if (dict[key]) {
      el.setAttribute('placeholder', dict[key]);
    }
  });
}

function insertQuickPrompt(num) {
  const dict = translations[currentLang] || translations.vi;
  let promptText = '';
  if (num === 1) promptText = dict.quick_prompt_text_1 || "Tôi bị sốt 38.5 độ và đau rát họng hai hôm nay, nuốt đau";
  else if (num === 2) promptText = dict.quick_prompt_text_2 || "Tôi bị đau thắt ngực dữ dội, vã mồ hôi và khó thở lan ra cánh tay trái";
  else if (num === 3) promptText = dict.quick_prompt_text_3 || "Sau khi bóc tách đơn thuốc, tôi cần uống thuốc trước hay sau bữa ăn?";
  else if (num === 4) promptText = dict.quick_prompt_text_4 || "Tôi bị đau thượng vị cồn cào sau khi ăn thì nên đăng ký khám chuyên khoa nào?";

  if (promptText) {
    insertPrompt(promptText);
  }
}

// ==========================================
// Multimodal Image Upload & Lightbox Modal
// ==========================================
function handleChatImageSelected(e) {
  const inputEl = (e && e.target && e.target.files) ? e.target : ((e && e.files) ? e : document.getElementById('chat-image-input'));
  const file = inputEl?.files?.[0];
  if (!file) {
    console.warn('Không có tệp nào được chọn.');
    return;
  }

  if (!file.type.startsWith('image/')) {
    alert(currentLang === 'vi' ? 'Vui lòng chọn tệp hình ảnh hợp lệ (JPG, PNG, WebP).' : 'Please select a valid image file (JPG, PNG, WebP).');
    return;
  }

  const reader = new FileReader();
  reader.onload = function(evt) {
    selectedChatImageBase64 = evt.target.result;
    const container = document.getElementById('chat-image-preview-container');
    const thumb = document.getElementById('chat-image-preview-thumb');
    const nameEl = document.getElementById('chat-image-preview-name');
    if (container && thumb) {
      thumb.src = selectedChatImageBase64;
      if (nameEl) nameEl.innerText = file.name;
      container.classList.remove('hidden');
    }
    document.getElementById('user-input')?.focus();
  };
  reader.readAsDataURL(file);
}

function clearChatImagePreview() {
  selectedChatImageBase64 = null;
  const container = document.getElementById('chat-image-preview-container');
  const input = document.getElementById('chat-image-input');
  if (container) container.classList.add('hidden');
  if (input) input.value = '';
}

function openImageModal(src, title, caption) {
  const modal = document.getElementById('image-lightbox-modal');
  const img = document.getElementById('lightbox-img');
  const titleEl = document.getElementById('lightbox-title');
  const captionEl = document.getElementById('lightbox-caption');

  if (modal && img) {
    img.src = src;
    if (titleEl) titleEl.innerText = title || (currentLang === 'vi' ? 'Ảnh tham khảo đối chiếu y khoa' : 'Clinical Reference Image');
    if (captionEl) captionEl.innerText = caption || '';
    modal.classList.remove('hidden');
  }
}

function closeImageModal() {
  const modal = document.getElementById('image-lightbox-modal');
  if (modal) modal.classList.add('hidden');
}

// ==========================================
// UI Floating Decorations & Tabs
// ==========================================
function hideFloatingDecorations() {
  const medInfoChip = document.getElementById('floating-medical-info');
  if (medInfoChip) {
    medInfoChip.classList.add('opacity-0', 'pointer-events-none', 'scale-90');
  }
}

function showFloatingDecorations() {
  const medInfoChip = document.getElementById('floating-medical-info');
  if (medInfoChip) {
    medInfoChip.classList.remove('opacity-0', 'pointer-events-none', 'scale-90');
  }
}

function switchTab(tabId) {
  // Yêu cầu đăng nhập khi vào các tab bảo mật
  const protectedTabs = ['profile-tab', 'admin-tab'];
  if (protectedTabs.includes(tabId) && !currentUser) {
    pendingTabAfterLogin = tabId;
    openLoginModal();
    return;
  }

  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  
  // Top Navbar buttons
  document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.classList.remove('glass-pill-cyan-active', 'bg-white/20', 'text-white', 'font-bold', 'border', 'border-white/25', 'shadow-[0_0_15px_rgba(255,255,255,0.2)]');
    btn.classList.add('text-slate-300', 'font-semibold');
  });

  // Floating Capsule Dock buttons
  document.querySelectorAll('.dock-btn').forEach(btn => {
    btn.classList.remove('bg-white', 'text-slate-950', 'shadow-[0_0_20px_rgba(255,255,255,0.45)]');
    btn.classList.add('text-white/60');
  });

  const activeTab = document.getElementById(tabId);
  if (activeTab) activeTab.classList.add('active');

  const activeNav = document.getElementById('nav-' + tabId);
  if (activeNav) {
    activeNav.classList.remove('text-slate-300', 'font-semibold');
    activeNav.classList.add('glass-pill-cyan-active', 'text-white', 'font-bold');
  }

  const activeDock = document.getElementById('dock-' + tabId);
  if (activeDock) {
    activeDock.classList.remove('text-white/60');
    activeDock.classList.add('bg-white', 'text-slate-950', 'shadow-[0_0_20px_rgba(255,255,255,0.45)]');
  }

  // Quản lý Chatbot Nổi góc dưới khi chuyển sang các tab khác (OCR, Bệnh viện, Bệnh án...)
  const floatingRoot = document.getElementById('floating-chatbot-root');
  if (floatingRoot) {
    if (tabId === 'chat-tab') {
      floatingRoot.classList.add('hidden');
      isFloatingChatDismissed = false; // Reset cờ tắt khi quay lại trang chat chính
    } else {
      if (!isFloatingChatDismissed) {
        floatingRoot.classList.remove('hidden');
        syncFloatingChatMessages();
      } else {
        floatingRoot.classList.add('hidden');
      }
    }
  }
}

function insertPrompt(text) {
  const input = document.getElementById('user-input');
  if (input) {
    input.value = text;
    input.focus();
  }
}

function resetChat() {
  showFloatingDecorations();
  clearChatImagePreview();
  chatHistory.length = 0;
  currentConversationId = null;
  currentIntakeSummary = null;

  const container = document.getElementById('chat-messages');
  if (container) container.innerHTML = '';

  const searchInput = document.getElementById('history-search-input');
  if (searchInput) searchInput.value = '';

  const intakeCard = document.getElementById('live-intake-card');
  if (intakeCard) {
    const statusBadge = document.getElementById('intake-status-badge');
    if (statusBadge) {
      statusBadge.innerText = 'Chờ khởi tạo';
      statusBadge.className = 'px-2 py-0.5 rounded-full text-[10px] font-bold bg-sky-500/20 text-sky-300 border border-sky-400/30';
    }
    const cEl = document.getElementById('intake-chief-complaint');
    if (cEl) cEl.innerText = 'Chưa có thông tin';
    const pEl = document.getElementById('intake-present-symptoms');
    if (pEl) pEl.innerText = '--';
    const dnEl = document.getElementById('intake-denied-symptoms');
    if (dnEl) dnEl.innerText = 'Chưa ghi nhận';
    const dEl = document.getElementById('intake-duration');
    if (dEl) dEl.innerText = '--';
    const vEl = document.getElementById('intake-vitals');
    if (vEl) vEl.innerText = '--';
    const btnConfirm = document.getElementById('btn-confirm-intake');
    if (btnConfirm) btnConfirm.classList.remove('hidden');
  }

  // Cập nhật lại thanh lịch sử: giữ nguyên các phiên trước đó, bỏ đánh dấu active
  renderChatHistoryList();
}

// ==========================================
// Chat Logic & Clinical Intake (Multimodal Vision + RAG + Double Guardrails)
// ==========================================
let currentConversationId = null;
let currentIntakeSummary = null;

async function sendChatMessage() {
  const input = document.getElementById('user-input');
  let text = input.value.trim();
  const currentImage = selectedChatImageBase64;

  if (!text && !currentImage) return;
  const dict = translations[currentLang] || translations.vi;
  if (!text && currentImage) {
    text = dict.default_image_prompt;
  }

  hideFloatingDecorations();
  const container = document.getElementById('chat-messages');

  // 1. User Message (Hỗ trợ ảnh đính kèm)
  let userImgHtml = '';
  if (currentImage) {
    userImgHtml = `
      <div class="mb-2 overflow-hidden rounded-xl border border-white/20 shadow-xs cursor-pointer max-w-[220px]" onclick="openImageModal('${currentImage}', 'Ảnh tổn thương bạn đã gửi', 'Ảnh người bệnh cung cấp')">
        <img src="${currentImage}" alt="Ảnh tải lên" class="w-full h-auto max-h-[160px] object-cover hover:scale-105 transition-transform duration-200">
      </div>
    `;
  }

  const userHtml = `
    <div class="flex flex-col items-end my-1">
      <div class="w-fit max-w-[85%] bg-gradient-to-r from-sky-500/90 to-indigo-600/90 text-white px-4 py-2.5 rounded-2xl rounded-tr-sm text-xs sm:text-sm shadow-lg shadow-sky-500/20 backdrop-blur-md leading-relaxed font-medium text-left break-words border border-white/20">
        ${userImgHtml}
        <div>${escapeHtml(text)}</div>
      </div>
      <div class="text-right text-[10px] text-slate-400 mt-1 mr-1">${dict.patient_label}</div>
    </div>
  `;

  container.insertAdjacentHTML('beforeend', userHtml);
  input.value = '';
  clearChatImagePreview();
  container.scrollTop = container.scrollHeight;

  // Khởi tạo phiên ngay lập tức trên thanh Lịch Sử Tư Vấn khi người dùng vừa gửi tin
  if (!currentConversationId) {
    currentConversationId = 'conv_' + Date.now().toString(36) + '_' + Math.random().toString(36).substr(2, 5);
  }
  let activeSession = chatSessions.find(s => s.id === currentConversationId);
  if (!activeSession) {
    const title = text.length > 30 ? text.slice(0, 30) + '...' : text;
    chatSessions.unshift({
      id: currentConversationId,
      title: title,
      lastMessage: text,
      timestamp: Date.now(),
      messageCount: chatHistory.length + 1,
      messages: [...chatHistory, { role: 'user', content: text }],
      facts: {},
      summary: null,
      status: 'collecting',
      riskLevel: 'Đang sàng lọc...',
      riskBadgeClass: 'bg-sky-500/20 text-sky-300 border border-sky-400/30'
    });
    saveSessionsToStorage();
    renderChatHistoryList();
  }

  // 2. Typing Indicator
  const typingId = 'typing-' + Date.now();
  const typingHtml = `
    <div id="${typingId}" class="flex justify-start max-w-md">
      <div class="glass-card border border-white/10 px-4 py-3 rounded-2xl rounded-tl-sm text-xs sm:text-sm text-slate-300 flex items-center space-x-2 shadow-lg backdrop-blur-xl bg-white/[0.05]">
        <span class="w-2 h-2 rounded-full bg-sky-400 animate-ping"></span>
        <span class="pl-1.5 text-xs font-medium text-slate-300">${currentImage ? dict.typing_vision : dict.typing_guideline}</span>
      </div>
    </div>
  `;

  container.insertAdjacentHTML('beforeend', typingHtml);
  container.scrollTop = container.scrollHeight;

  try {
    // Gọi song song Chatbot AI và Dịch vụ Phân tích Dữ kiện Lâm sàng (Intake Service)
    const [chatResponse, intakeResponse] = await Promise.allSettled([
      fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, history: chatHistory, image: currentImage, lang: currentLang })
      }).then(r => r.json()),
      fetch('/api/intake/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ conversation_id: currentConversationId, message: text, image: currentImage })
      }).then(r => r.json())
    ]);

    document.getElementById(typingId)?.remove();

    // 1. Xử lý phản hồi từ Intake Service (Cập nhật bảng dữ kiện và tóm tắt trước khám)
    if (intakeResponse.status === 'fulfilled' && intakeResponse.value) {
      const intakeData = intakeResponse.value;
      if (intakeData.conversation_id) {
        currentConversationId = intakeData.conversation_id;
      }
      if (intakeData.facts) {
        updateLiveIntakeCard(intakeData.facts, intakeData.status, intakeData.summary);
      }
      if (intakeData.summary) {
        currentIntakeSummary = intakeData.summary;
      }
    }

    // 2. Xử lý phản hồi hội thoại
    const data = (chatResponse.status === 'fulfilled') ? chatResponse.value : null;

    if (!data || data.error) {
      appendErrorMessage(data?.error || dict.server_error);
      return;
    }

    updateTriagePanel(data);

    let formattedAnswer = escapeHtml(data.answer)
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/\n/g, '<br>');

    // Đặc điểm thị giác nhận diện từ ảnh (Gemini Vision)
    let visualFindingsHtml = '';
    if (data.visual_findings && data.visual_findings.length > 0) {
      visualFindingsHtml = `
        <div class="p-2.5 rounded-xl bg-sky-500/15 border border-sky-400/30 space-y-1.5">
          <div class="text-[11px] font-bold text-sky-300 flex items-center space-x-1.5">
            <span>👁️</span>
            <span>Đặc điểm thị giác nhận định (Gemini Vision AI):</span>
          </div>
          <div class="flex flex-wrap gap-1.5 pt-0.5">
            ${data.visual_findings.map(f => `
              <span class="text-[10px] font-medium bg-white/[0.06] text-sky-200 px-2 py-0.5 rounded-full border border-sky-400/30 shadow-2xs">
                ${escapeHtml(f)}
              </span>
            `).join('')}
          </div>
        </div>
      `;
    }

    // Cảnh báo cờ đỏ cấp cứu
    let emergencyBadge = '';
    if (data.is_emergency) {
      emergencyBadge = `
        <div class="bg-rose-500/20 border border-rose-400/40 p-2.5 rounded-xl text-xs font-bold text-rose-300 flex items-center space-x-2 shadow-[0_0_15px_rgba(244,63,94,0.25)]">
          <svg class="w-4 h-4 text-rose-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
          </svg>
          <span>NGUY CẤP: GỌI 115 HOẶC ĐẾN CƠ SỞ CẤP CỨU GẦN NHẤT</span>
        </div>
      `;
    }

    const botHtml = `
      <div class="flex justify-start max-w-[95%] sm:max-w-xl">
        <div class="glass-card border border-white/10 p-4 sm:p-5 rounded-2xl rounded-tl-sm text-xs sm:text-sm text-slate-200 space-y-3 leading-relaxed shadow-xl w-full backdrop-blur-xl bg-white/[0.06]">
          ${emergencyBadge}
          ${visualFindingsHtml}
          <div class="text-slate-200 font-normal leading-relaxed">${formattedAnswer}</div>
        </div>
      </div>
    `;

    container.insertAdjacentHTML('beforeend', botHtml);
    container.scrollTop = container.scrollHeight;

    chatHistory.push({ role: 'user', content: text, image: currentImage });
    chatHistory.push({ role: 'assistant', content: data.answer });

    const intakeVal = (intakeResponse.status === 'fulfilled') ? intakeResponse.value : null;
    saveOrUpdateCurrentSession(text, data, intakeVal);

  } catch (err) {
    document.getElementById(typingId)?.remove();
    appendErrorMessage(dict.server_error);
  }
}

// Cập nhật phân tầng lâm sàng định tính (Tuyệt đối KHÔNG hiển thị điểm xác suất 0-100 giả lập)
function updateTriagePanel(data) {
  const floatingRisk = document.getElementById('floating-risk-score');
  const score = data.risk_score || 25;
  if (floatingRisk) {
    if (data.is_emergency || score >= 70) {
      floatingRisk.innerText = `Cảnh báo cấp cứu khẩn cấp`;
      floatingRisk.className = 'text-xs font-bold text-rose-400';
    } else if (score >= 35) {
      floatingRisk.innerText = `Khuyến nghị khám chuyên khoa`;
      floatingRisk.className = 'text-xs font-bold text-amber-300';
    } else {
      floatingRisk.innerText = `Theo dõi & tự chăm sóc tại nhà`;
      floatingRisk.className = 'text-xs font-bold text-emerald-400';
    }
  }
}

// ==========================================
// Clinical Intake & Pre-visit Summary Helpers (Mục 8 & 9)
// ==========================================
function updateLiveIntakeCard(facts, status, summary) {
  const card = document.getElementById('live-intake-card');
  if (!card) return;
  card.classList.remove('hidden');

  const complaintEl = document.getElementById('intake-chief-complaint');
  const presentEl = document.getElementById('intake-present-symptoms');
  const deniedEl = document.getElementById('intake-denied-symptoms');
  const durationEl = document.getElementById('intake-duration');
  const vitalsEl = document.getElementById('intake-vitals');
  const statusBadge = document.getElementById('intake-status-badge');
  const btnConfirm = document.getElementById('btn-confirm-intake');

  if (complaintEl) complaintEl.innerText = facts.chief_complaint || 'Sàng lọc triệu chứng';
  if (presentEl) presentEl.innerText = (facts.present_symptoms && facts.present_symptoms.length > 0) ? facts.present_symptoms.join(', ') : 'Chưa ghi nhận rõ';
  if (deniedEl) deniedEl.innerText = (facts.denied_symptoms && facts.denied_symptoms.length > 0) ? facts.denied_symptoms.join(', ') : 'Chưa phủ nhận triệu chứng nào';
  if (durationEl) durationEl.innerText = facts.duration || 'Chưa rõ số ngày';
  if (vitalsEl) {
    const v = facts.vitals || {};
    vitalsEl.innerText = v.temperature ? `${v.temperature}` : 'Chưa cặp nhiệt độ';
  }

  if (statusBadge) {
    if (status === 'confirmed') {
      statusBadge.innerText = '✓ Đã xác nhận';
      statusBadge.className = 'px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-400/30';
      if (btnConfirm) btnConfirm.classList.add('hidden');
    } else if (status === 'ready_for_review') {
      statusBadge.innerText = 'Chờ xác nhận';
      statusBadge.className = 'px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-400/30';
      if (btnConfirm) btnConfirm.classList.remove('hidden');
    } else {
      statusBadge.innerText = 'Đang thu thập';
      statusBadge.className = 'px-2 py-0.5 rounded-full text-[10px] font-bold bg-sky-500/20 text-sky-300 border border-sky-400/30';
      if (btnConfirm) btnConfirm.classList.remove('hidden');
    }
  }
}

function openPreVisitSummaryModal() {
  const modal = document.getElementById('previsit-summary-modal');
  if (!modal) return;
  modal.classList.remove('hidden');

  if (currentIntakeSummary) {
    renderPreVisitSummaryInModal(currentIntakeSummary);
  } else if (currentConversationId) {
    fetch(`/api/intake/summary/${currentConversationId}`)
      .then(res => res.json())
      .then(data => {
        if (data.summary) {
          currentIntakeSummary = data.summary;
          renderPreVisitSummaryInModal(data.summary);
        }
      });
  }
}

function closePreVisitSummaryModal() {
  const modal = document.getElementById('previsit-summary-modal');
  if (modal) modal.classList.add('hidden');
}

function renderPreVisitSummaryInModal(summary) {
  const partA = summary.part_a_patient_facts || {};
  const partB = summary.part_b_system_assessment || {};

  const statusText = document.getElementById('modal-summary-status-text');
  const createdAt = document.getElementById('modal-summary-created-at');
  if (statusText) statusText.innerText = `Phiên bản: v${partB.version || 1} • ${partB.confirmation_status || 'Chờ xác nhận'}`;
  if (createdAt) createdAt.innerText = partB.created_at || '';

  // Part A
  const cEl = document.getElementById('summary-a-complaint');
  const dEl = document.getElementById('summary-a-duration');
  const pEl = document.getElementById('summary-a-present');
  const dnEl = document.getElementById('summary-a-denied');
  const vEl = document.getElementById('summary-a-vitals');
  const attEl = document.getElementById('summary-a-attachments');
  const mEl = document.getElementById('summary-a-missing');

  if (cEl) cEl.innerText = partA.chief_complaint || '--';
  if (dEl) dEl.innerText = partA.duration || '--';
  if (pEl) pEl.innerText = (partA.symptoms_present && partA.symptoms_present.length) ? partA.symptoms_present.join(', ') : '--';
  if (dnEl) dnEl.innerText = (partA.symptoms_denied && partA.symptoms_denied.length) ? partA.symptoms_denied.join(', ') : 'Chưa có triệu chứng phủ nhận';
  if (vEl) vEl.innerText = partA.vitals || '--';
  if (attEl) attEl.innerText = partA.attachments_and_observations || '--';
  if (mEl) mEl.innerText = (partA.missing_or_unclear_info && partA.missing_or_unclear_info.length) ? partA.missing_or_unclear_info.join('; ') : 'Đã đủ thông tin cơ bản';

  // Part B
  const bStatus = document.getElementById('summary-b-status');
  const bSpec = document.getElementById('summary-b-specialist');
  const bAppr = document.getElementById('summary-b-approach');
  const bSources = document.getElementById('summary-b-sources');

  if (bStatus) bStatus.innerText = partB.triage_status || '--';
  if (bSpec) bSpec.innerText = partB.recommended_specialist || '--';
  if (bAppr) bAppr.innerText = partB.care_approach || '--';
  if (bSources) {
    const sList = partB.sources || [];
    bSources.innerHTML = sList.map(s => `• Nguồn: <a href="${s.url}" target="_blank" class="underline hover:text-white">${escapeHtml(s.title || s.source)}</a>`).join('<br>');
  }

  const modalConfirmBtn = document.getElementById('modal-btn-confirm');
  if (modalConfirmBtn) {
    if (summary.is_confirmed) {
      modalConfirmBtn.innerHTML = '<span>✓ Đã xác nhận lời khai</span>';
      modalConfirmBtn.disabled = true;
      modalConfirmBtn.classList.add('opacity-60', 'cursor-not-allowed');
    } else {
      modalConfirmBtn.innerHTML = '<span>✓ Tôi xác nhận lời khai đúng thực tế</span>';
      modalConfirmBtn.disabled = false;
      modalConfirmBtn.classList.remove('opacity-60', 'cursor-not-allowed');
    }
  }
}

async function confirmCurrentIntake() {
  if (!currentConversationId) return;
  try {
    const res = await fetch('/api/intake/confirm-summary', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conversation_id: currentConversationId })
    });
    const data = await res.json();
    if (data.summary) {
      currentIntakeSummary = data.summary;
      updateLiveIntakeCard(data.summary.part_a_patient_facts, 'confirmed', data.summary);
      showMedicalToast("Đã xác nhận lời khai bệnh sử thành công!", "success");
    }
  } catch (e) {
    showMedicalToast("Lỗi khi xác nhận lời khai", "error");
  }
}

async function confirmCurrentIntakeFromModal() {
  await confirmCurrentIntake();
  if (currentIntakeSummary) {
    renderPreVisitSummaryInModal(currentIntakeSummary);
  }
}

function appendErrorMessage(msg) {
  const container = document.getElementById('chat-messages');
  if (!container) return;
  const errHtml = `
    <div class="glass-card bg-rose-500/20 border border-rose-400/40 p-3 rounded-2xl text-xs text-rose-300 font-medium">
      ${escapeHtml(msg)}
    </div>
  `;
  container.insertAdjacentHTML('beforeend', errHtml);
  container.scrollTop = container.scrollHeight;
}

// ==========================================
// Scan Dataset Files Management (OCR Tab)
// ==========================================
function triggerFileUpload() {
  if (!currentUser) {
    pendingTabAfterLogin = 'ocr-tab';
    openLoginModal();
    return;
  }
  const fileInput = document.getElementById('lab-file-input');
  if (fileInput) {
    fileInput.value = '';
    fileInput.click();
  }
}

async function handleFileSelected(e) {
  const file = e.target.files?.[0];
  if (!file) return;

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch('/api/upload-lab', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();

    if (data.status === 'success') {
      await loadScanFiles();
    } else {
      alert(data.message || 'Lỗi khi tải tệp lên.');
    }
  } catch (err) {
    console.error('Lỗi upload tệp:', err);
    alert('Không thể kết nối đến máy chủ để tải tệp lên.');
  }
}

async function loadScanFiles() {
  try {
    const res = await fetch('/api/scan-files');
    const data = await res.json();
    const files = data.files || [];

    const ocrEmpty = document.getElementById('ocr-table-empty');
    const ocrFilled = document.getElementById('ocr-table-filled');
    const tbody = document.getElementById('scan-files-tbody');
    const countBadge = document.getElementById('scan-files-count');

    if (countBadge) countBadge.innerText = `${files.length} tệp`;

    if (files.length === 0) {
      if (ocrEmpty) ocrEmpty.classList.remove('hidden');
      if (ocrFilled) ocrFilled.classList.add('hidden');
    } else {
      if (ocrEmpty) ocrEmpty.classList.add('hidden');
      if (ocrFilled) ocrFilled.classList.remove('hidden');

      if (tbody) {
        tbody.innerHTML = files.map(f => {
          let badgeClass = 'bg-slate-100 text-slate-700 border-slate-200';
          if (['JPG', 'JPEG', 'PNG'].includes(f.type)) badgeClass = 'bg-blue-50 text-blue-700 border-blue-200';
          else if (f.type === 'PDF') badgeClass = 'bg-rose-50 text-rose-700 border-rose-200';
          else if (['DOCX', 'DOC'].includes(f.type)) badgeClass = 'bg-indigo-50 text-indigo-700 border-indigo-200';

          return `
            <tr class="hover:bg-slate-50/70 transition-colors">
              <td class="py-3 px-3 font-semibold text-slate-800 flex items-center space-x-2">
                <svg class="w-4 h-4 text-slate-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
                </svg>
                <span class="truncate max-w-[200px]" title="${escapeHtml(f.name)}">${escapeHtml(f.name)}</span>
              </td>
              <td class="py-3 px-3">
                <span class="px-2 py-0.5 rounded-full font-bold text-[10px] border ${badgeClass}">${escapeHtml(f.type || 'FILE')}</span>
              </td>
              <td class="py-3 px-3 text-slate-600 font-mono text-[10px]">${escapeHtml(f.size)}</td>
              <td class="py-3 px-3 text-slate-500 text-[10px]">${escapeHtml(f.uploaded_at)}</td>
              <td class="py-3 px-3 text-right">
                <button type="button" onclick="deleteScanFile('${encodeURIComponent(f.name)}')" class="text-rose-500 hover:text-rose-700 hover:bg-rose-50 p-1.5 rounded-lg transition-colors cursor-pointer" title="Xóa tệp khỏi tập huấn luyện">
                  <svg class="w-4 h-4 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path>
                  </svg>
                </button>
              </td>
            </tr>
          `;
        }).join('');
      }
    }
  } catch (err) {
    console.error('Lỗi tải danh sách tệp scan:', err);
  }
}

async function deleteScanFile(encodedName) {
  if (!confirm('Bạn có chắc chắn muốn xóa tệp này khỏi bộ dữ liệu huấn luyện không?')) return;
  try {
    const res = await fetch('/api/scan-files/' + encodedName, { method: 'DELETE' });
    const data = await res.json();
    if (data.status === 'success') {
      await loadScanFiles();
    } else {
      alert(data.message || 'Không thể xóa tệp.');
    }
  } catch (err) {
    console.error('Lỗi khi xóa tệp:', err);
  }
}

function simulateUploadLab() {
  triggerFileUpload();
}

function escapeHtml(string) {
  const div = document.createElement('div');
  div.innerText = string;
  return div.innerHTML;
}

// ==========================================
// Authentication & Profile State Management
// ==========================================
function toggleUserDropdown(e) {
  if (e) e.stopPropagation();
  const menu = document.getElementById('user-dropdown-menu');
  if (menu) menu.classList.toggle('hidden');
}

function closeUserDropdown() {
  const menu = document.getElementById('user-dropdown-menu');
  if (menu) menu.classList.add('hidden');
}

function toggleProfileEdit(isEdit) {
  const viewMode = document.getElementById('profile-view-mode');
  const editMode = document.getElementById('profile-edit-mode');
  if (!viewMode || !editMode) return;

  if (isEdit) {
    if (currentUser) {
      const nameInput = document.getElementById('edit-profile-name');
      const genderSelect = document.getElementById('edit-profile-gender');
      const dobInput = document.getElementById('edit-profile-dob');
      const phoneInput = document.getElementById('edit-profile-phone');

      if (nameInput) nameInput.value = currentUser.name || '';
      if (genderSelect) genderSelect.value = currentUser.gender || 'Nam';
      if (dobInput) dobInput.value = currentUser.dob || '';
      if (phoneInput) phoneInput.value = currentUser.phone_number || '';
    }
    viewMode.classList.add('hidden');
    editMode.classList.remove('hidden');
    document.getElementById('edit-profile-name')?.focus();
  } else {
    editMode.classList.add('hidden');
    viewMode.classList.remove('hidden');
  }
}

async function handleSaveProfile(e) {
  if (e) e.preventDefault();
  const name = document.getElementById('edit-profile-name')?.value.trim();
  const gender = document.getElementById('edit-profile-gender')?.value;
  const dob = document.getElementById('edit-profile-dob')?.value.trim();
  const phone = document.getElementById('edit-profile-phone')?.value.trim();

  if (!name) {
    alert('Vui lòng nhập họ và tên.');
    return;
  }

  try {
    const res = await fetch('/api/auth/profile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: currentUser?.id,
        name: name,
        gender: gender,
        dob: dob,
        phone_number: phone
      })
    });
    const data = await res.json();
    if (data.success && data.user) {
      currentUser = data.user;
      localStorage.setItem('medimind_user', JSON.stringify(currentUser));
      updateAuthUI();
      openProfileModal();
      toggleProfileEdit(false);
      alert('Cập nhật thông tin cá nhân thành công!');
    } else {
      alert(data.error || 'Cập nhật thông tin thất bại.');
    }
  } catch (err) {
    console.error('Lỗi cập nhật thông tin:', err);
    alert('Không thể kết nối đến máy chủ.');
  }
}

function openProfileModal() {
  closeUserDropdown();
  switchTab('profile-tab');
}

async function handleTabSaveProfile(e) {
  if (e) e.preventDefault();
  const name = document.getElementById('tab-profile-name')?.value.trim();
  const dob = document.getElementById('tab-profile-dob')?.value.trim();
  const gender = document.getElementById('tab-profile-gender')?.value;
  const phone = document.getElementById('tab-profile-phone')?.value.trim();
  const email = document.getElementById('tab-profile-email')?.value.trim();
  const bhyt = document.getElementById('tab-profile-bhyt')?.value.trim();
  const city = document.getElementById('tab-profile-city')?.value.trim();
  const address = document.getElementById('tab-profile-address')?.value.trim();

  if (!name) {
    alert('Vui lòng nhập họ và tên.');
    return;
  }

  try {
    const res = await fetch('/api/auth/profile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: currentUser?.id,
        name,
        dob,
        gender,
        phone_number: phone,
        email,
        bhyt,
        city,
        address: [city, address].filter(Boolean).join(' - ')
      })
    });
    const data = await res.json();
    if (data.success && data.user) {
      currentUser = data.user;
      currentUser.city = city;
      localStorage.setItem('medimind_user', JSON.stringify(currentUser));
      updateAuthUI();
      alert('Cập nhật hồ sơ thông tin cá nhân thành công!');
    } else {
      alert(data.error || 'Cập nhật thất bại.');
    }
  } catch (err) {
    console.error('Lỗi lưu hồ sơ:', err);
    alert('Không thể kết nối đến máy chủ.');
  }
}

function closeProfileModal() {
  toggleProfileEdit(false);
  const modal = document.getElementById('profile-modal');
  if (modal) modal.classList.add('hidden');
}

function openLoginModal() {
  const modal = document.getElementById('login-modal');
  if (modal) {
    modal.classList.remove('hidden');
    document.getElementById('login-identifier')?.focus();
  }
}

function closeLoginModal() {
  const modal = document.getElementById('login-modal');
  if (modal) modal.classList.add('hidden');
}

function populateDobDropdowns() {
  const daySelect = document.getElementById('register-dob-day');
  const monthSelect = document.getElementById('register-dob-month');
  const yearSelect = document.getElementById('register-dob-year');
  if (!daySelect || !monthSelect || !yearSelect) return;
  if (daySelect.children.length <= 1) {
    daySelect.innerHTML = '<option value="" disabled selected>Ngày</option>' + 
      Array.from({length: 31}, (_, i) => `<option value="${i+1}">${i+1}</option>`).join('');
    monthSelect.innerHTML = '<option value="" disabled selected>Tháng</option>' + 
      Array.from({length: 12}, (_, i) => `<option value="${i+1}">Tháng ${i+1}</option>`).join('');
    const currentYear = new Date().getFullYear();
    yearSelect.innerHTML = '<option value="" disabled selected>Năm</option>' + 
      Array.from({length: 85}, (_, i) => `<option value="${currentYear - i}">${currentYear - i}</option>`).join('');
  }
}

let currentAuthMode = 'login';
function toggleAuthMode(mode) {
  currentAuthMode = mode;
  const titleEl = document.getElementById('auth-modal-title');
  const tabLogin = document.getElementById('tab-auth-login');
  const tabRegister = document.getElementById('tab-auth-register');
  const loginForm = document.getElementById('login-form');
  const registerForm = document.getElementById('register-form');
  if (mode === 'register') {
    populateDobDropdowns();
    if (titleEl) titleEl.innerText = 'Đăng ký tài khoản MediMind';
    tabLogin?.classList.remove('border-[#0284C7]', 'text-[#0284C7]');
    tabLogin?.classList.add('border-transparent', 'text-slate-500');
    tabRegister?.classList.remove('border-transparent', 'text-slate-500');
    tabRegister?.classList.add('border-[#0284C7]', 'text-[#0284C7]');
    loginForm?.classList.add('hidden');
    registerForm?.classList.remove('hidden');
    document.getElementById('register-last-name')?.focus();
  } else {
    if (titleEl) titleEl.innerText = 'Đăng nhập MediMind AI';
    tabRegister?.classList.remove('border-[#0284C7]', 'text-[#0284C7]');
    tabRegister?.classList.add('border-transparent', 'text-slate-500');
    tabLogin?.classList.remove('border-transparent', 'text-slate-500');
    tabLogin?.classList.add('border-[#0284C7]', 'text-[#0284C7]');
    registerForm?.classList.add('hidden');
    loginForm?.classList.remove('hidden');
    document.getElementById('login-identifier')?.focus();
  }
}

function selectLoginRole(role) {
  currentRole = 'patient';
}

async function handleRegisterSubmit(e) {
  e.preventDefault();
  const lastName = (document.getElementById('register-last-name')?.value || '').trim();
  const firstName = (document.getElementById('register-first-name')?.value || '').trim();
  const fullName = [lastName, firstName].filter(Boolean).join(' ') || (document.getElementById('register-name')?.value || '').trim();
  const day = document.getElementById('register-dob-day')?.value;
  const month = document.getElementById('register-dob-month')?.value;
  const year = document.getElementById('register-dob-year')?.value;
  const gender = document.getElementById('register-gender')?.value || '';
  const identifier = (document.getElementById('register-identifier')?.value || document.getElementById('register-email')?.value || '').trim();
  const password = document.getElementById('register-password')?.value;

  if (!fullName || !identifier || !password) {
    alert('Vui lòng điền đầy đủ Họ và Tên, Email hoặc Số di động và mật khẩu.');
    return;
  }
  if (password.length < 6) {
    alert('Mật khẩu phải có ít nhất 6 ký tự.');
    return;
  }

  const dob = (day && month && year) ? `${String(day).padStart(2, '0')}/${String(month).padStart(2, '0')}/${year}` : '';

  try {
    const res = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        last_name: lastName,
        first_name: firstName,
        name: fullName,
        dob,
        gender,
        identifier,
        email: identifier,
        full_name: fullName,
        password,
        role: 'patient'
      })
    });
    const data = await res.json();
    if (data.success && data.user) {
      currentUser = data.user;
      localStorage.setItem('medimind_user', JSON.stringify(currentUser));
      updateAuthUI();
      closeLoginModal();
      alert('Đăng ký tài khoản thành công! Chào mừng ' + currentUser.name + ' gia nhập MediMind.');
      document.getElementById('register-form')?.reset();
      if (pendingTabAfterLogin) {
        const target = pendingTabAfterLogin;
        pendingTabAfterLogin = null;
        switchTab(target);
      }
    } else {
      alert(data.error || 'Đăng ký tài khoản thất bại.');
    }
  } catch (err) {
    console.error('Lỗi đăng ký:', err);
    alert('Không thể kết nối đến máy chủ.');
  }
}

async function quickLogin(type) {
  const identifier = 'benhnhan.an@gmail.com';
  const password = 'MatKhau123@';
  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ identifier, password, role: 'patient' })
    });
    const data = await res.json();
    if (data.success && data.user) {
      currentUser = data.user;
      localStorage.setItem('medimind_user', JSON.stringify(currentUser));
      updateAuthUI();
      closeLoginModal();
    } else {
      alert(data.error || 'Đăng nhập thất bại.');
    }
  } catch (err) {
    console.error('Lỗi đăng nhập nhanh:', err);
    alert('Không thể kết nối máy chủ xác thực.');
  }
}

async function handleLoginSubmit(e) {
  e.preventDefault();
  const identifier = document.getElementById('login-identifier')?.value.trim();
  const password = document.getElementById('login-password')?.value;
  if (!identifier || !password) {
    alert('Vui lòng nhập đầy đủ tài khoản và mật khẩu.');
    return;
  }
  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ identifier, email: identifier, password, role: currentRole })
    });
    const data = await res.json();
    if (data.success && data.user) {
      currentUser = data.user;
      localStorage.setItem('medimind_user', JSON.stringify(currentUser));
      updateAuthUI();
      closeLoginModal();
      document.getElementById('login-form')?.reset();
      if (pendingTabAfterLogin) {
        const target = pendingTabAfterLogin;
        pendingTabAfterLogin = null;
        switchTab(target);
      }
    } else {
      alert(data.error || 'Thông tin đăng nhập không hợp lệ.');
    }
  } catch (err) {
    console.error('Lỗi gửi form đăng nhập:', err);
    alert('Không thể kết nối tới máy chủ CSDL.');
  }
}

async function handleLogout() {
  try {
    await fetch('/api/auth/logout', { method: 'POST' });
  } catch (err) {
    console.error('Lỗi đăng xuất:', err);
  }
  currentUser = null;
  localStorage.removeItem('medimind_user');
  updateAuthUI();
  switchTab('chat-tab');
}

function updateAuthUI() {
  const unlogged = document.getElementById('auth-unlogged');
  const logged = document.getElementById('auth-logged');
  const nameEl = document.getElementById('user-display-name');
  const roleEl = document.getElementById('user-role-badge');
  const avatarEl = document.getElementById('user-avatar-badge');

  const navDoctorTab = document.getElementById('nav-doctor-tab');
  const ehrTitle = document.getElementById('ehr-title');
  const ehrSubtitle = document.getElementById('ehr-subtitle');
  const ehrPatientName = document.getElementById('ehr-patient-name');
  const ehrPatientId = document.getElementById('ehr-patient-id');
  const ehrAvatarBadge = document.getElementById('ehr-avatar-badge');
  const ocrSyncBtnText = document.getElementById('ocr-sync-btn-text');

  const ehrEmpty = document.getElementById('ehr-content-empty');
  const ehrFilled = document.getElementById('ehr-content-filled');

  if (navDoctorTab) navDoctorTab.innerText = (currentLang === 'vi' ? '📋 Hồ sơ của tôi' : '📋 My Health Record');
  if (ocrSyncBtnText) ocrSyncBtnText.innerText = (currentLang === 'vi' ? 'Xem Hồ sơ của tôi →' : 'View My Record →');

  if (currentUser) {
    if (unlogged) unlogged.classList.add('hidden');
    if (logged) logged.classList.remove('hidden');
    if (nameEl) nameEl.innerText = currentUser.name;

    const subInfo = currentUser.personal_info || currentUser.role || 'Thành viên';
    if (roleEl) roleEl.innerText = subInfo;
    if (avatarEl) avatarEl.innerText = currentUser.badge || 'BN';

    if (ehrTitle) ehrTitle.innerText = (currentLang === 'vi' ? 'Hồ sơ bệnh án' : 'Medical Records');
    if (ehrSubtitle) ehrSubtitle.innerText = (currentLang === 'vi' ? 'Theo dõi lịch sử khám và điều trị' : 'Track examination and treatment history');
    if (ehrPatientName) ehrPatientName.innerText = currentUser.name;
    if (ehrPatientId) ehrPatientId.innerText = 'Mã BN: #BN-2026-' + String(currentUser.id || 8429).padStart(4, '0') + ' • ' + subInfo;
    if (ehrAvatarBadge) ehrAvatarBadge.innerText = currentUser.badge || 'BN';

    const rightPanelName = document.getElementById('right-panel-patient-name');
    const rightPanelId = document.getElementById('right-panel-patient-id');
    const rightPanelAvatar = document.getElementById('right-panel-avatar');
    const rightPanelBhyt = document.getElementById('right-panel-bhyt');
    if (rightPanelName) rightPanelName.innerText = currentUser.name;
    if (rightPanelId) rightPanelId.innerText = 'Mã BN: #BN-2026-' + String(currentUser.id || 4).padStart(4, '0');
    if (rightPanelAvatar) {
      const initials = currentUser.badge || (currentUser.name ? currentUser.name.split(' ').map(w => w[0]).slice(-2).join('').toUpperCase() : 'BN');
      rightPanelAvatar.innerText = initials;
    }
    if (rightPanelBhyt && currentUser.bhyt) {
      rightPanelBhyt.innerText = currentUser.bhyt;
    }

    const dropAvatar = document.getElementById('dropdown-user-avatar');
    const dropName = document.getElementById('dropdown-user-name');
    const dropInfo = document.getElementById('dropdown-user-info');
    if (dropAvatar) dropAvatar.innerText = currentUser.badge || 'BN';
    if (dropName) dropName.innerText = currentUser.name;
    if (dropInfo) dropInfo.innerText = subInfo;

    const tabBannerId = document.getElementById('tab-profile-banner-id');
    const tabBannerName = document.getElementById('tab-profile-banner-name');
    const tabName = document.getElementById('tab-profile-name');
    const tabDob = document.getElementById('tab-profile-dob');
    const tabGender = document.getElementById('tab-profile-gender');
    const tabPhone = document.getElementById('tab-profile-phone');
    const tabEmail = document.getElementById('tab-profile-email');
    const tabBhyt = document.getElementById('tab-profile-bhyt');
    const tabCity = document.getElementById('tab-profile-city');
    const tabAddress = document.getElementById('tab-profile-address');

    if (tabBannerId) tabBannerId.innerText = 'Mã BN: #BN-2026-' + String(currentUser.id || 8429).padStart(4, '0');
    if (tabBannerName) tabBannerName.innerText = 'Họ tên: ' + currentUser.name;
    if (tabName) tabName.value = currentUser.name || '';
    if (tabDob) tabDob.value = currentUser.dob || '';
    if (tabGender) tabGender.value = currentUser.gender || 'Nam';
    if (tabPhone) tabPhone.value = currentUser.phone_number || '';
    if (tabEmail) tabEmail.value = (currentUser.email && !currentUser.email.endsWith('@phone.medimind')) ? currentUser.email : '';
    if (tabBhyt) tabBhyt.value = currentUser.bhyt || '';
    if (tabCity) tabCity.value = currentUser.city || '';
    if (tabAddress) tabAddress.value = currentUser.address || '';

    const isDemoPatient = currentUser.email === 'benhnhan.an@gmail.com' || currentUser.isDemo;
    const hasRecord = isDemoPatient || currentUser.hasMedicalRecord;
    if (ehrEmpty) ehrEmpty.classList.toggle('hidden', !!hasRecord);
    if (ehrFilled) ehrFilled.classList.toggle('hidden', !hasRecord);

    const exportBtn = document.getElementById('ehr-export-pdf-btn');
    if (exportBtn) {
      if (hasRecord) {
        exportBtn.classList.remove('opacity-40', 'cursor-not-allowed');
        exportBtn.removeAttribute('disabled');
        exportBtn.title = 'In hoặc tải bản tóm tắt trước khám (PDF)';
      } else {
        exportBtn.classList.add('opacity-40', 'cursor-not-allowed');
        exportBtn.title = 'Chưa có bản tóm tắt trước khám để kết xuất PDF';
      }
    }
    loadScanFiles();
    syncServerConsultations();
    renderChatHistoryList();
  } else {
    if (unlogged) unlogged.classList.remove('hidden');
    if (logged) logged.classList.add('hidden');
    if (nameEl) nameEl.innerText = 'Khách';
    if (roleEl) roleEl.innerText = 'Chưa đăng nhập';
    if (avatarEl) avatarEl.innerText = '👤';
    if (ehrPatientName) ehrPatientName.innerText = 'Chưa đăng nhập';
    if (ehrPatientId) ehrPatientId.innerText = 'Vui lòng đăng nhập để đồng bộ tóm tắt trước khám';
    if (ehrEmpty) ehrEmpty.classList.remove('hidden');
    if (ehrFilled) ehrFilled.classList.add('hidden');

    renderChatHistoryList();

    const exportBtn = document.getElementById('ehr-export-pdf-btn');
    if (exportBtn) {
      exportBtn.classList.add('opacity-40', 'cursor-not-allowed');
      exportBtn.title = 'Chưa có bản tóm tắt trước khám để kết xuất PDF';
    }
    loadScanFiles();
  }
}

function openDisclaimerModal() {
  const modal = document.getElementById('disclaimer-modal');
  if (modal) modal.classList.remove('hidden');
}

function closeDisclaimerModal() {
  const modal = document.getElementById('disclaimer-modal');
  if (modal) modal.classList.add('hidden');
}

// ==========================================
// Floating Mini Chatbot Widget Logic
// ==========================================
let isFloatingChatDismissed = false;

function toggleFloatingChatWindow() {
  const windowEl = document.getElementById('floating-chat-window');
  const bubbleEl = document.getElementById('floating-chat-bubble');
  if (!windowEl) return;

  const isHidden = windowEl.classList.contains('hidden');
  if (isHidden) {
    syncFloatingChatMessages();
    windowEl.classList.remove('hidden');
    if (bubbleEl) bubbleEl.classList.add('hidden');
    const input = document.getElementById('floating-user-input');
    if (input) setTimeout(() => input.focus(), 150);
  } else {
    windowEl.classList.add('hidden');
    if (bubbleEl) bubbleEl.classList.remove('hidden');
  }
}

function minimizeFloatingChat() {
  const windowEl = document.getElementById('floating-chat-window');
  const bubbleEl = document.getElementById('floating-chat-bubble');
  if (windowEl) windowEl.classList.add('hidden');
  if (bubbleEl) bubbleEl.classList.remove('hidden');
}

function closeFloatingChatCompletely() {
  isFloatingChatDismissed = true;
  const root = document.getElementById('floating-chatbot-root');
  const windowEl = document.getElementById('floating-chat-window');
  const bubbleEl = document.getElementById('floating-chat-bubble');
  if (root) root.classList.add('hidden');
  if (windowEl) windowEl.classList.add('hidden');
  if (bubbleEl) bubbleEl.classList.remove('hidden');
  showMedicalToast('Đã tắt chatbot nổi. Bạn có thể mở lại khi quay lại tab Trang chủ.', 'info', 3000);
}

function expandFloatingChatToFull() {
  minimizeFloatingChat();
  switchTab('chat-tab');
}

function insertFloatingPrompt(text) {
  const input = document.getElementById('floating-user-input');
  if (input) {
    input.value = text;
    input.focus();
  }
}

function syncFloatingChatMessages() {
  const container = document.getElementById('floating-chat-messages');
  if (!container) return;

  if (chatHistory.length === 0) {
    container.innerHTML = `
      <div class="p-3.5 rounded-2xl bg-white/[0.04] border border-sky-400/20 text-slate-300 space-y-2 text-xs">
        <div class="flex items-center gap-2 text-sky-300 font-bold">
          <span>🩺</span>
          <span>Chào bạn, tôi là Trợ lý AI MediMind!</span>
        </div>
        <p class="text-[11px] text-slate-300 leading-relaxed">
          Tôi luôn sẵn sàng hỗ trợ bạn ngay tại góc màn hình này. Hãy hỏi tôi về cách dùng thuốc, giải thích chỉ số xét nghiệm hoặc gợi ý chuyên khoa khám nhé!
        </p>
      </div>
    `;
    return;
  }

  container.innerHTML = chatHistory.map(msg => {
    if (msg.role === 'user') {
      return `
        <div class="flex flex-col items-end my-1">
          <div class="w-fit max-w-[85%] bg-gradient-to-r from-sky-500/90 to-indigo-600/90 text-white px-3 py-2 rounded-xl rounded-tr-xs text-xs leading-relaxed font-medium text-left break-words border border-white/20 shadow-xs">
            ${escapeHtml(msg.content)}
          </div>
          <span class="text-[9px] text-slate-400 mt-0.5 mr-1">Bạn</span>
        </div>
      `;
    } else {
      let formatted = escapeHtml(msg.content)
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/\n/g, '<br>');
      return `
        <div class="flex justify-start max-w-[90%] my-1">
          <div class="glass-card border border-white/10 p-3 rounded-xl rounded-tl-xs text-xs text-slate-200 leading-relaxed shadow-md backdrop-blur-md bg-white/[0.06]">
            ${formatted}
          </div>
        </div>
      `;
    }
  }).join('');

  container.scrollTop = container.scrollHeight;
}

async function sendFloatingChatMessage() {
  const input = document.getElementById('floating-user-input');
  if (!input) return;
  const text = input.value.trim();
  if (!text) return;

  input.value = '';
  const container = document.getElementById('floating-chat-messages');
  if (!container) return;

  // Render tin nhắn của người dùng trong khung mini
  const userHtml = `
    <div class="flex flex-col items-end my-1">
      <div class="w-fit max-w-[85%] bg-gradient-to-r from-sky-500/90 to-indigo-600/90 text-white px-3 py-2 rounded-xl rounded-tr-xs text-xs leading-relaxed font-medium text-left break-words border border-white/20 shadow-xs">
        ${escapeHtml(text)}
      </div>
      <span class="text-[9px] text-slate-400 mt-0.5 mr-1">Bạn</span>
    </div>
  `;
  container.insertAdjacentHTML('beforeend', userHtml);
  container.scrollTop = container.scrollHeight;

  // Đồng thời cập nhật vào khung chat chính
  const mainContainer = document.getElementById('chat-messages');
  if (mainContainer) {
    const mainUserHtml = `
      <div class="flex flex-col items-end my-1">
        <div class="w-fit max-w-[85%] bg-gradient-to-r from-sky-500/90 to-indigo-600/90 text-white px-4 py-2.5 rounded-2xl rounded-tr-sm text-xs sm:text-sm shadow-lg shadow-sky-500/20 backdrop-blur-md leading-relaxed font-medium text-left break-words border border-white/20">
          <div>${escapeHtml(text)}</div>
        </div>
        <div class="text-right text-[10px] text-slate-400 mt-1 mr-1">Bệnh nhân</div>
      </div>
    `;
    mainContainer.insertAdjacentHTML('beforeend', mainUserHtml);
    mainContainer.scrollTop = mainContainer.scrollHeight;
  }

  // Mini Typing Indicator
  const typingId = 'floating-typing-' + Date.now();
  const typingHtml = `
    <div id="${typingId}" class="flex justify-start max-w-[90%] my-1">
      <div class="glass-card border border-white/10 px-3 py-2 rounded-xl rounded-tl-xs text-xs text-slate-300 flex items-center space-x-1.5 shadow-md backdrop-blur-md bg-white/[0.05]">
        <span class="w-2 h-2 rounded-full bg-sky-400 animate-ping"></span>
        <span class="text-[11px] text-slate-300">Đang đối soát phác đồ...</span>
      </div>
    </div>
  `;
  container.insertAdjacentHTML('beforeend', typingHtml);
  container.scrollTop = container.scrollHeight;

  try {
    const [chatResponse, intakeResponse] = await Promise.allSettled([
      fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, history: chatHistory, lang: currentLang })
      }).then(r => r.json()),
      fetch('/api/intake/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ conversation_id: currentConversationId, message: text })
      }).then(r => r.json())
    ]);

    document.getElementById(typingId)?.remove();

    const data = (chatResponse.status === 'fulfilled') ? chatResponse.value : null;
    if (!data || data.error) {
      container.insertAdjacentHTML('beforeend', `<div class="p-2 text-rose-300 text-[11px]">${escapeHtml(data?.error || 'Có lỗi xảy ra, vui lòng thử lại.')}</div>`);
      return;
    }

    if (intakeResponse.status === 'fulfilled' && intakeResponse.value) {
      const intakeData = intakeResponse.value;
      if (intakeData.conversation_id) currentConversationId = intakeData.conversation_id;
      if (intakeData.facts) updateLiveIntakeCard(intakeData.facts, intakeData.status, intakeData.summary);
      if (intakeData.summary) currentIntakeSummary = intakeData.summary;
    }

    updateTriagePanel(data);

    let formattedAnswer = escapeHtml(data.answer)
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/\n/g, '<br>');

    const botHtml = `
      <div class="flex justify-start max-w-[90%] my-1">
        <div class="glass-card border border-white/10 p-3 rounded-xl rounded-tl-xs text-xs text-slate-200 leading-relaxed shadow-md backdrop-blur-md bg-white/[0.06]">
          ${formattedAnswer}
        </div>
      </div>
    `;
    container.insertAdjacentHTML('beforeend', botHtml);
    container.scrollTop = container.scrollHeight;

    // Cập nhật khung chat chính
    if (mainContainer) {
      const mainBotHtml = `
        <div class="flex justify-start max-w-[95%] sm:max-w-xl">
          <div class="glass-card border border-white/10 p-4 sm:p-5 rounded-2xl rounded-tl-sm text-xs sm:text-sm text-slate-200 space-y-3 leading-relaxed shadow-xl w-full backdrop-blur-xl bg-white/[0.06]">
            <div class="text-slate-200 font-normal leading-relaxed">${formattedAnswer}</div>
          </div>
        </div>
      `;
      mainContainer.insertAdjacentHTML('beforeend', mainBotHtml);
      mainContainer.scrollTop = mainContainer.scrollHeight;
    }

    chatHistory.push({ role: 'user', content: text });
    chatHistory.push({ role: 'assistant', content: data.answer });

    const intakeVal = (intakeResponse.status === 'fulfilled') ? intakeResponse.value : null;
    saveOrUpdateCurrentSession(text, data, intakeVal);

  } catch (err) {
    document.getElementById(typingId)?.remove();
    container.insertAdjacentHTML('beforeend', `<div class="p-2 text-rose-300 text-[11px]">Lỗi kết nối máy chủ y tế.</div>`);
  }
}

// ==========================================
// Initialization & Global Event Listeners
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
  populateDobDropdowns();
  updateAuthUI();
  applyLanguage();
  initHistorySearch();
  selectPatientProfile('minh_anh');

  const input = document.getElementById('user-input');
  if (input) {
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendChatMessage();
      }
    });
    input.addEventListener('focus', hideFloatingDecorations);
    input.addEventListener('input', () => {
      if (input.value.trim().length > 0) hideFloatingDecorations();
    });
  }

  const floatingInput = document.getElementById('floating-user-input');
  if (floatingInput) {
    floatingInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendFloatingChatMessage();
      }
    });
  }

  const chatMessagesContainer = document.getElementById('chat-messages');
  if (chatMessagesContainer) {
    chatMessagesContainer.addEventListener('scroll', () => {
      if (chatMessagesContainer.scrollTop > 15) hideFloatingDecorations();
    });
  }

  // Đóng modal & dropdown khi bấm Escape
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeLoginModal();
      closeDisclaimerModal();
      closeProfileModal();
      closeUserDropdown();
      closeLanguageDropdown();
      closeImageModal();
    }
  });

  // Đóng modal khi click ra ngoài nền tối
  const loginModal = document.getElementById('login-modal');
  if (loginModal) {
    loginModal.addEventListener('click', (e) => {
      if (e.target === loginModal) closeLoginModal();
    });
  }

  const disclaimerModal = document.getElementById('disclaimer-modal');
  if (disclaimerModal) {
    disclaimerModal.addEventListener('click', (e) => {
      if (e.target === disclaimerModal) closeDisclaimerModal();
    });
  }

  const profileModal = document.getElementById('profile-modal');
  if (profileModal) {
    profileModal.addEventListener('click', (e) => {
      if (e.target === profileModal) closeProfileModal();
    });
  }

  // Đóng dropdowns khi click ra ngoài
  document.addEventListener('click', (e) => {
    const authLogged = document.getElementById('auth-logged');
    if (authLogged && !authLogged.contains(e.target)) {
      closeUserDropdown();
    }
    const langContainer = document.getElementById('lang-picker-container');
    if (langContainer && !langContainer.contains(e.target)) {
      closeLanguageDropdown();
    }
  });
});


// ==============================================================================

// ==============================================================================
// 🩺 HỆ THỐNG SỐ HÓA & PHÂN TÍCH ĐƠN THUỐC LÂM SÀNG (CLINICAL PRESCRIPTION PARSER)
// ==============================================================================

async function handlePrescriptionFileSelected(e) {
  const file = e.target.files?.[0];
  if (!file) return;

  const preview = document.getElementById('file-chosen-preview');
  const nameEl = document.getElementById('file-chosen-name');
  if (preview && nameEl) {
    nameEl.innerText = `${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
    preview.classList.remove('hidden');
  }

  const formData = new FormData();
  formData.append('file', file);

  showPrescriptionLoading(true, "AI đang nhận dạng văn bản & hình ảnh...", "Trích xuất danh mục thuốc, đối chiếu liều dùng và chuẩn hóa dược học...");

  try {
    const res = await fetch('/api/prescription/scan', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    showPrescriptionLoading(false);

    if (!res.ok) {
      if (res.status === 401) {
        showMedicalToast('Vui lòng đăng nhập tài khoản để quét và lưu trữ đơn thuốc.', 'warning', 4500);
        openLoginModal();
      } else {
        showMedicalToast(data.message || 'Không thể xử lý tệp tài liệu. Vui lòng kiểm tra lại.', 'error');
      }
      return;
    }

    if (data.status === 'failed') {
      renderPrescriptionError(data);
      showMedicalToast(data.message || 'Không thể nhận diện nội dung đơn thuốc. Vui lòng chụp lại ảnh rõ nét.', 'error', 5000);
      return;
    }

    renderPrescriptionResult(data);
    if (data.is_demo) {
      showMedicalToast('Đang hiển thị đơn thuốc mẫu thử nghiệm (Demo).', 'info', 4000);
    } else if (data.needs_review) {
      showMedicalToast('Đã đọc tài liệu: Vui lòng đối chiếu với ảnh gốc để xác nhận các mục chưa chắc chắn.', 'warning', 5000);
    } else {
      showMedicalToast(`Đã nhận dạng thành công đơn thuốc: ${data.diagnosis || 'Đơn thuốc y tế'}`, 'success');
    }
  } catch (err) {
    console.error('Lỗi khi phân tích đơn thuốc:', err);
    showPrescriptionLoading(false);
    showMedicalToast('Hệ thống tạm thời bận hoặc không thể kết nối. Vui lòng tải lại ảnh hoặc chọn hồ sơ mẫu.', 'error');
  }
}

function renderPrescriptionError(data) {
  const resSec = document.getElementById('prescription-result-section');
  if (!resSec) return;
  const msg = data.message || 'Không thể nhận diện nội dung từ hình ảnh đã tải lên.';
  const previewLines = data.raw_ocr_preview && data.raw_ocr_preview.length > 0 
    ? `<div class="mt-3 p-3 rounded-xl bg-white/5 border border-white/10 text-left font-mono text-[11px] text-slate-300 space-y-1">
        <div class="font-bold text-slate-400 mb-1">Đoạn văn bản máy nhận diện được:</div>
        ${data.raw_ocr_preview.map(l => `<div>• ${escapeHtml(l)}</div>`).join('')}
       </div>`
    : '';

  resSec.innerHTML = `
    <div class="glass-panel p-6 border border-rose-500/30 bg-rose-950/20 backdrop-blur-2xl space-y-4 text-center">
      <div class="w-12 h-12 mx-auto rounded-full bg-rose-500/20 border border-rose-400/40 flex items-center justify-center text-rose-300 text-xl font-bold">⚠️</div>
      <h3 class="text-lg font-black text-white">Chưa thể đọc rõ nội dung đơn thuốc</h3>
      <p class="text-xs text-rose-200 max-w-md mx-auto leading-relaxed">${escapeHtml(msg)}</p>
      ${previewLines}
      <div class="pt-2 flex justify-center gap-3">
        <button onclick="resetPrescriptionScan()" class="px-4 py-2 rounded-xl bg-gradient-to-r from-sky-500 to-indigo-600 hover:from-sky-400 hover:to-indigo-500 text-white text-xs font-bold transition-all shadow-md cursor-pointer">Chụp / Tải ảnh khác</button>
        <button onclick="loadPrescriptionPreset('binh_dan')" class="px-4 py-2 rounded-xl glass-pill text-xs font-bold text-slate-300 hover:text-white cursor-pointer">Thử xem đơn mẫu</button>
      </div>
    </div>
  `;
  resSec.classList.remove('hidden');
}

// ==============================================================================
// MODERN TOAST NOTIFICATION SYSTEM & AUDIO FEEDBACK (ZERO ALERT POPUPS)
// ==============================================================================
function showMedicalToast(message, type = 'info', duration = 3500) {
  let container = document.getElementById('medical-toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'medical-toast-container';
    container.className = 'fixed top-5 right-5 sm:right-8 z-50 flex flex-col gap-2.5 max-w-sm pointer-events-none';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  const typeStyles = {
    success: 'bg-emerald-900/95 text-white border-emerald-500/50 shadow-emerald-950/20',
    warning: 'bg-amber-900/95 text-white border-amber-500/50 shadow-amber-950/20',
    error: 'bg-rose-900/95 text-white border-rose-500/50 shadow-rose-950/20',
    info: 'bg-slate-900/95 text-white border-sky-500/50 shadow-slate-950/20'
  };
  const icons = {
    success: `<svg class="w-5 h-5 text-emerald-400 shrink-0" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/></svg>`,
    warning: `<svg class="w-5 h-5 text-amber-400 shrink-0" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>`,
    error: `<svg class="w-5 h-5 text-rose-400 shrink-0" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/></svg>`,
    info: `<svg class="w-5 h-5 text-sky-400 shrink-0" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>`
  };

  toast.className = `pointer-events-auto transform transition-all duration-300 ease-out translate-y-[-10px] opacity-0 flex items-start gap-3 px-4 py-3 rounded-2xl border backdrop-blur-xl shadow-xl text-xs font-semibold leading-relaxed ${typeStyles[type] || typeStyles.info}`;
  toast.innerHTML = `
    ${icons[type] || icons.info}
    <div class="flex-1">${message}</div>
    <button onclick="this.parentElement.remove()" class="text-slate-400 hover:text-white transition-colors ml-1 cursor-pointer">✕</button>
  `;

  container.appendChild(toast);
  requestAnimationFrame(() => {
    toast.classList.remove('translate-y-[-10px]', 'opacity-0');
  });

  setTimeout(() => {
    toast.classList.add('opacity-0', 'translate-y-[-10px]');
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// Gentle pleasant synthesizer chime using Web Audio API
function playMedicalChime() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = 'sine';
    osc.frequency.setValueAtTime(587.33, ctx.currentTime);
    osc.frequency.exponentialRampToValueAtTime(880, ctx.currentTime + 0.12);
    gain.gain.setValueAtTime(0.08, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.35);
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.35);
  } catch (e) {}
}

// Micro celebratory confetti effect
function triggerCelebration(btnEl) {
  playMedicalChime();
  if (!btnEl) return;
  const rect = btnEl.getBoundingClientRect();
  const emojis = ['💊', '✨', '🎉', '🟢', '⭐'];
  for (let i = 0; i < 12; i++) {
    const p = document.createElement('div');
    p.innerText = emojis[Math.floor(Math.random() * emojis.length)];
    p.className = 'fixed pointer-events-none z-50 text-base select-none transition-all duration-700 ease-out';
    p.style.left = `${rect.left + rect.width / 2 + (Math.random() * 80 - 40)}px`;
    p.style.top = `${rect.top + (Math.random() * 20 - 10)}px`;
    p.style.opacity = '1';
    p.style.transform = `translate(0, 0) scale(1)`;
    document.body.appendChild(p);

    const destX = (Math.random() - 0.5) * 160;
    const destY = -60 - Math.random() * 80;

    requestAnimationFrame(() => {
      p.style.transform = `translate(${destX}px, ${destY}px) scale(1.3) rotate(${Math.random() * 90 - 45}deg)`;
      p.style.opacity = '0';
    });

    setTimeout(() => p.remove(), 750);
  }
}

let currentPrescriptionData = null;
let currentSelectedSlotId = null;
let adherenceSlotState = {};

async function loadPrescriptionPreset(presetKey) {
  showPrescriptionLoading(true, "Đang nạp hồ sơ mẫu lâm sàng...", "Thiết lập danh mục hoạt chất, liều lượng và thời gian biểu...");
  try {
    const res = await fetch(`/api/prescription/scan?preset=${presetKey}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ preset: presetKey })
    });
    const data = await res.json();
    showPrescriptionLoading(false);

    // 1. Kiểm tra mã phản hồi & trạng thái lỗi từ máy chủ
    if (!res.ok || data.status === 'error' || data.status === 'failed') {
      renderPrescriptionError(data);
      showMedicalToast(data.message || 'Không thể nạp hồ sơ mẫu. Kịch bản không tồn tại hoặc xảy ra lỗi.', 'error', 5000);
      return;
    }

    // 2. Kiểm tra tính toàn vẹn của đơn thuốc mẫu (không được để trống danh mục thuốc)
    if (data.type === 'prescription' && (!data.medications || data.medications.length === 0)) {
      renderPrescriptionError({
        message: 'Dữ liệu đơn thuốc mẫu không chứa danh mục hoạt chất hợp lệ để lập lịch điều trị.'
      });
      showMedicalToast('Dữ liệu đơn thuốc mẫu không hợp lệ.', 'error', 5000);
      return;
    }

    renderPrescriptionResult(data);
    showMedicalToast(`Đã nạp hồ sơ mẫu: ${data.diagnosis || 'Đơn thuốc chuẩn'}`, 'info');
  } catch (err) {
    console.error('Lỗi khi tải dữ liệu đối soát:', err);
    showPrescriptionLoading(false);
    showMedicalToast('Không thể kết nối đến máy chủ để nạp hồ sơ mẫu.', 'error');
  }
}

function showPrescriptionLoading(show, stepText, substepText) {
  const inputSec = document.getElementById('prescription-input-section');
  const loadSec = document.getElementById('prescription-loading-section');
  const resSec = document.getElementById('prescription-result-section');
  const stepEl = document.getElementById('scan-step-text');
  const substepEl = document.getElementById('scan-substep-text');

  if (show) {
    if (inputSec) inputSec.classList.add('hidden');
    if (resSec) resSec.classList.add('hidden');
    if (loadSec) loadSec.classList.remove('hidden');
    if (stepEl && stepText) stepEl.innerText = stepText;
    if (substepEl && substepText) substepEl.innerText = substepText;
  } else {
    if (loadSec) loadSec.classList.add('hidden');
  }
}

function resetPrescriptionScan() {
  const inputSec = document.getElementById('prescription-input-section');
  const loadSec = document.getElementById('prescription-loading-section');
  const resSec = document.getElementById('prescription-result-section');
  const preview = document.getElementById('file-chosen-preview');
  const fileInput = document.getElementById('prescription-file-input');

  if (fileInput) fileInput.value = '';
  if (preview) preview.classList.add('hidden');
  if (loadSec) loadSec.classList.add('hidden');
  if (resSec) {
    resSec.classList.add('hidden');
    resSec.innerHTML = '';
  }
  if (inputSec) inputSec.classList.remove('hidden');
  adherenceSlotState = {};
  currentPrescriptionData = null;
  inputSec?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// Helper to determine the smart active slot based on real-world time
function detectSmartDoseSlot(slots) {
  if (!slots || slots.length === 0) return null;
  const hour = new Date().getHours();
  let targetId = 'morning';
  if (hour >= 11 && hour < 15) {
    targetId = 'noon';
  } else if (hour >= 15 && hour < 21) {
    targetId = 'evening';
  } else if (hour >= 21 || hour < 5) {
    targetId = 'bedtime';
  }

  const match = slots.find(s => s.id === targetId);
  return match || slots[0];
}

// ==============================================================================
// NEXT-GEN MEDICAL DASHBOARD: USER-CENTRIC, DYNAMIC & FLUID
// ==============================================================================
function renderPrescriptionResult(data) {
  currentPrescriptionData = data;
  const resSec = document.getElementById('prescription-result-section');
  if (!resSec) return;

  const isLab = data.type === 'lab_test';
  const diag = data.diagnosis || 'Chăm sóc & Điều trị';
  const doctor = data.doctor || 'Bác sĩ điều trị';
  const patient = data.patient_name || 'Bệnh nhân';
  const facility = data.facility && data.facility !== 'Không xác định' ? data.facility : '';
  const dateStr = data.date || 'Hôm nay';
  const duration = data.duration || '30 ngày (Theo lượng thuốc cấp)';
  const address = data.address || '';

  if (isLab) {
    let html = `
      <div class="glass-panel p-6 border border-white/10 bg-white/[0.06] backdrop-blur-2xl space-y-4 shadow-2xl">
        <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center pb-4 border-b border-white/10 gap-3">
          <div>
            <div class="flex items-center space-x-2">
              <span class="px-3 py-1 rounded-full text-[10px] font-black tracking-wider bg-sky-500/20 text-sky-300 border border-sky-400/30 uppercase">KẾT QUẢ XÉT NGHIỆM</span>
              ${data.is_demo ? '<span class="px-2.5 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider bg-amber-500/20 text-amber-300 border border-amber-400/40">DỮ LIỆU MẪU (DEMO)</span>' : ''}
              ${data.needs_review ? '<span class="px-2.5 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider bg-rose-500/20 text-rose-300 border border-rose-400/40">CẦN XÁC NHẬN</span>' : ''}
              <span class="text-xs text-slate-400 font-mono">Ngày lập: <strong class="text-white">${dateStr}</strong></span>
            </div>
            <h3 class="text-xl font-black text-white mt-1">${data.doc_title || 'Phiếu Xét Nghiệm Y Khoa'}</h3>
            <p class="text-xs text-slate-300 font-semibold mt-0.5">${patient} • ${doctor}</p>
          </div>
          <div class="flex items-center space-x-2">
            <button onclick="window.print()" class="px-4 py-2 rounded-xl glass-pill text-slate-200 hover:text-white text-xs font-bold transition-all cursor-pointer">In kết quả</button>
            <button onclick="resetPrescriptionScan()" class="px-4 py-2 rounded-xl bg-gradient-to-r from-sky-500 to-indigo-600 hover:from-sky-400 hover:to-indigo-500 text-white text-xs font-bold transition-all cursor-pointer shadow-lg shadow-sky-500/25">Quét tệp khác</button>
          </div>
        </div>

        <div class="overflow-x-auto rounded-2xl border border-white/10 bg-white/[0.03]">
          <table class="w-full text-left text-xs">
            <thead class="bg-white/5 border-b border-white/10 text-slate-300 font-bold uppercase text-[10px]">
              <tr>
                <th class="py-3 px-4">Chỉ số xét nghiệm</th>
                <th class="py-3 px-4">Kết quả</th>
                <th class="py-3 px-4">Khoảng tham chiếu</th>
                <th class="py-3 px-4">Đánh giá lâm sàng</th>
                <th class="py-3 px-4">Lời khuyên</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-white/5">
              ${(data.metrics || []).map(m => `
                <tr class="hover:bg-white/5 transition-colors">
                  <td class="py-3 px-4 font-bold text-white">${m.name}</td>
                  <td class="py-3 px-4 font-mono font-extrabold ${m.status === 'High' ? 'text-rose-400' : m.status === 'Low' ? 'text-sky-400' : 'text-emerald-400'}">${m.value} <span class="text-[10px] text-slate-400 font-normal">${m.unit}</span></td>
                  <td class="py-3 px-4 font-mono text-slate-400 text-[11px]">${m.reference} ${m.unit}</td>
                  <td class="py-3 px-4">
                    <span class="px-2.5 py-1 rounded-full text-[10px] font-black ${m.status === 'High' ? 'bg-rose-500/20 text-rose-300 border border-rose-400/30' : m.status === 'Low' ? 'bg-sky-500/20 text-sky-300 border border-sky-400/30' : 'bg-emerald-500/20 text-emerald-300 border border-emerald-400/30'}">${m.status_label || m.status}</span>
                  </td>
                  <td class="py-3 px-4 text-slate-300 text-[11px]">${m.advice || '---'}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;
    resSec.innerHTML = html;
    resSec.classList.remove('hidden');
    return;
  }

  // PRESCRIPTION MODE
  const tl = data.timeline || {};
  const meds = data.medications || [];
  const warnings = data.warnings || [];

  // Bảo vệ an toàn dữ liệu: không bao giờ tạo lịch uống thuốc từ danh mục thuốc rỗng
  if (meds.length === 0) {
    renderPrescriptionError({
      message: data.message || 'Không tìm thấy danh mục hoạt chất hợp lệ trong tài liệu để thiết lập thời gian biểu.'
    });
    return;
  }

  const allSlotDefs = [
    { id: 'morning', label: 'BUỔI SÁNG', time: '06:30 - 08:00', icon: '🌅', color: 'amber', items: tl.morning || [] },
    { id: 'noon', label: 'BUỔI TRƯA', time: '11:30 - 12:30', icon: '☀️', color: 'sky', items: tl.noon || [] },
    { id: 'evening', label: 'CHIỀU / TỐI', time: '18:00 - 19:30', icon: '🌙', color: 'indigo', items: tl.evening || [] },
    { id: 'bedtime', label: 'TRƯỚC KHI NGỦ', time: '21:00 - 22:00', icon: '🛌', color: 'slate', items: tl.bedtime || [] },
    { id: 'external', label: 'DÙNG NGOÀI DA', time: 'Sáng & Tối', icon: '🧴', color: 'purple', items: tl.external || [] }
  ];

  const activeSlots = allSlotDefs.filter(s => s.items.length > 0);
  const smartSlot = detectSmartDoseSlot(activeSlots.length > 0 ? activeSlots : allSlotDefs);
  currentSelectedSlotId = smartSlot ? smartSlot.id : (activeSlots[0]?.id || 'morning');

  adherenceSlotState = {};
  activeSlots.forEach(s => { adherenceSlotState[s.id] = false; });

  const patientInitials = (patient.split(' ').slice(-2).map(w => w[0]).join('') || 'BN').toUpperCase();

  let html = `
    <div class="space-y-4 font-sans select-none">

      <!-- 1. PATIENT & DIAGNOSIS GLASSMORPHIC HERO BAR -->
      <div class="glass-card p-5 border border-white/15 bg-white/[0.06] backdrop-blur-xl shadow-2xl transition-all">
        <div class="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          
          <div class="flex items-start sm:items-center space-x-3.5">
            <div class="w-13 h-13 rounded-2xl bg-gradient-to-tr from-sky-500 to-indigo-600 text-white flex items-center justify-center font-black text-lg shadow-lg shadow-sky-500/30 border border-white/20 shrink-0">
              ${patientInitials}
            </div>
            <div class="space-y-1 min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <span class="px-2.5 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider bg-sky-500/20 text-sky-300 border border-sky-400/30">
                  ĐƠN NGOẠI TRÚ
                </span>
                ${data.is_demo ? '<span class="px-2.5 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider bg-amber-500/20 text-amber-300 border border-amber-400/40">DỮ LIỆU MẪU (DEMO)</span>' : ''}
                ${data.needs_review ? '<span class="px-2.5 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider bg-rose-500/20 text-rose-300 border border-rose-400/40">CẦN XÁC NHẬN</span>' : ''}
                <span class="text-xs text-slate-400 font-mono">Ngày khám: <strong class="text-white font-bold">${dateStr}</strong></span>
                <span class="px-2.5 py-0.5 rounded-full text-[10px] font-black bg-emerald-500/20 text-emerald-300 border border-emerald-400/30">
                  Đợt dùng: ${duration}
                </span>
              </div>
              <div class="flex items-baseline gap-2 pt-0.5">
                <h2 class="text-lg sm:text-xl font-black text-white tracking-tight flex items-center gap-1.5 truncate">
                  <span class="text-sky-400 font-bold">🩺 Chẩn đoán:</span> ${diag}
                </h2>
              </div>
              <p class="text-xs text-slate-300 font-medium">
                Bệnh nhân: <strong class="text-white font-bold">${patient}</strong>
                ${address ? ` • <span class="text-slate-400 font-normal">${address}</span>` : ''}
                ${doctor ? ` • Kê đơn: <strong class="text-slate-300">${doctor}</strong>` : ''}
              </p>
            </div>
          </div>

          <div class="flex items-center space-x-2 shrink-0 pt-2 lg:pt-0 border-t lg:border-t-0 border-white/10">
            <button onclick="askBotAboutPrescription()" class="px-4 py-2.5 bg-gradient-to-r from-sky-500 to-indigo-600 hover:from-sky-400 hover:to-indigo-500 text-white text-xs font-bold rounded-2xl shadow-lg shadow-sky-500/25 transition-all flex items-center space-x-2 cursor-pointer hover:scale-102">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/></svg>
              <span>Hỏi Bác sĩ AI</span>
            </button>
            <button onclick="window.print()" class="px-3.5 py-2.5 rounded-2xl glass-pill text-slate-200 hover:text-white text-xs font-bold transition-all flex items-center space-x-1.5 cursor-pointer">
              <svg class="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"/></svg>
              <span class="hidden sm:inline">In đơn</span>
            </button>
            <button onclick="resetPrescriptionScan()" class="px-3.5 py-2.5 rounded-2xl glass-card bg-slate-800 hover:bg-slate-700 text-white text-xs font-bold transition-all flex items-center space-x-1.5 cursor-pointer border border-white/10">
              <svg class="w-4 h-4 text-slate-300" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
              <span>Quét đơn khác</span>
            </button>
          </div>
        </div>
      </div>

      <!-- 2. SMART DOCTOR'S SAFETY ALERTS -->
      ${warnings.length > 0 ? `
        <div class="glass-card p-4 border border-amber-400/40 bg-amber-950/25 text-amber-200 backdrop-blur-xl shadow-[0_0_20px_rgba(251,191,36,0.15)] transition-all">
          <div class="flex items-center justify-between cursor-pointer" onclick="toggleWarningDetails()">
            <div class="flex items-center space-x-2.5">
              <span class="w-8 h-8 rounded-xl bg-amber-500 text-white flex items-center justify-center font-black text-sm shrink-0 shadow-sm shadow-amber-500/25 border border-white/20">
                ⚠️
              </span>
              <div>
                <h4 class="text-xs font-black text-amber-300 uppercase tracking-tight">CHỈ DẪN AN TOÀN &amp; LƯU Ý BÁC SĨ:</h4>
                <p class="text-[11px] text-amber-200/90 font-medium line-clamp-1">${warnings[0]}</p>
              </div>
            </div>
            <button id="btn-toggle-warnings" class="text-xs font-bold text-amber-300 hover:text-white transition-colors flex items-center space-x-1 shrink-0 px-2.5 py-1 rounded-lg bg-amber-500/20 border border-amber-400/30">
              <span id="label-toggle-warnings">Xem tất cả (${warnings.length})</span>
              <svg id="icon-toggle-warnings" class="w-3.5 h-3.5 transform transition-transform" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7"/></svg>
            </button>
          </div>
          <div id="expanded-warning-list" class="hidden mt-3 pt-3 border-t border-amber-400/20 space-y-2">
            <ul class="text-xs text-amber-200 font-medium space-y-2 pl-4 list-disc leading-relaxed">
              ${warnings.map(w => `<li>${w}</li>`).join('')}
            </ul>
          </div>
        </div>
      ` : ''}

      <!-- 3. REAL-TIME SMART HERO: CỮ THUỐC ĐANG ĐẾN / HIỆN TẠI -->
      <div id="smart-hero-dose-card" class="glass-panel-elevated p-6 border border-sky-400/35 bg-white/[0.06] backdrop-blur-2xl shadow-[0_0_35px_rgba(56,189,248,0.15)] space-y-5 transition-all relative overflow-hidden">
        
        <div class="absolute -right-16 -top-16 w-60 h-60 bg-sky-500/15 rounded-full blur-3xl pointer-events-none"></div>

        <div class="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-white/10 gap-3 relative z-10">
          <div class="flex items-center space-x-3">
            <span class="text-3xl">${smartSlot ? smartSlot.icon : '🕒'}</span>
            <div>
              <div class="flex items-center space-x-2">
                <span class="relative flex h-2.5 w-2.5">
                  <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
                </span>
                <span class="text-[10px] font-black uppercase tracking-wider text-emerald-300 bg-emerald-500/20 border border-emerald-400/30 px-2 py-0.5 rounded-md">
                  ĐANG TRONG KHUNG GIỜ DÙNG THUỐC
                </span>
              </div>
              <h3 id="current-hero-slot-title" class="text-xl sm:text-2xl font-black text-white mt-0.5">
                ${smartSlot ? smartSlot.label : 'LỊCH UỐNG THUỐC'} <span class="text-xs sm:text-sm font-mono text-slate-400 font-bold">(${smartSlot ? smartSlot.time : ''})</span>
              </h3>
            </div>
          </div>

          <div class="text-left sm:text-right space-y-1">
            <div class="text-[11px] font-bold text-slate-300">
              Tiến độ hôm nay: <span id="adherence-progress-text" class="font-mono font-extrabold text-sky-400">0/${activeSlots.length} cữ (0%)</span>
            </div>
            <div class="w-36 sm:w-44 h-2.5 bg-white/10 rounded-full overflow-hidden border border-white/10">
              <div id="adherence-progress-bar" class="h-full bg-gradient-to-r from-sky-400 to-emerald-400 rounded-full transition-all duration-500 w-0"></div>
            </div>
          </div>
        </div>

        <div id="hero-slot-medications-list" class="space-y-3 relative z-10">
          ${renderSlotPillChecklist(smartSlot || activeSlots[0])}
        </div>

        <div class="pt-2 relative z-10 flex flex-col sm:flex-row items-center justify-between gap-3">
          <button id="btn-hero-complete" onclick="toggleHeroSlotCompletion('${smartSlot ? smartSlot.id : ''}', this)" class="w-full sm:w-auto px-8 py-3.5 bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-white text-sm font-extrabold rounded-2xl shadow-lg shadow-emerald-500/30 transition-all flex items-center justify-center space-x-2.5 cursor-pointer hover:scale-102 border border-white/20">
            <svg class="w-5 h-5 text-white" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/></svg>
            <span id="btn-hero-complete-text">XÁC NHẬN ĐÃ UỐNG XONG CỮ NÀY</span>
          </button>
          
          <span class="text-[11px] text-slate-400 font-medium text-center sm:text-right">
            Nhấn để đánh dấu tiến độ điều trị trong ngày
          </span>
        </div>
      </div>

      <!-- 4. INTERACTIVE TIMELINE SELECTOR & TỦ THUỐC -->
      <div class="glass-panel p-5 border border-white/10 bg-white/[0.06] space-y-4">
        
        <div class="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-white/10 gap-3">
          <div class="flex flex-wrap items-center gap-1.5 p-1 glass-dock rounded-2xl">
            <button id="tab-nav-schedule" onclick="switchPrescriptionMainTab('schedule')" class="px-4 py-2 rounded-xl text-xs font-black transition-all bg-white text-slate-950 shadow-md cursor-pointer">
              🕒 Lộ trình trong ngày
            </button>
            <button id="tab-nav-formulary" onclick="switchPrescriptionMainTab('formulary')" class="px-4 py-2 rounded-xl text-xs font-black transition-all text-slate-300 hover:text-white cursor-pointer">
              💊 Tủ thuốc &amp; Dược thư (${meds.length} loại)
            </button>
          </div>

          <div id="quick-slot-switcher" class="flex flex-wrap items-center gap-1.5">
            ${activeSlots.map(s => `
              <button id="pill-slot-${s.id}" onclick="selectSpecificSlot('${s.id}')" class="px-3 py-1.5 rounded-xl text-xs font-bold transition-all flex items-center space-x-1 cursor-pointer ${s.id === currentSelectedSlotId ? 'bg-sky-500 text-white shadow-lg shadow-sky-500/30 border border-white/20' : 'glass-pill text-slate-300 hover:text-white'}">
                <span>${s.icon}</span>
                <span>${s.label.replace('BUỔI ', '')}</span>
                <span class="font-mono text-[10px] opacity-80">(${s.items.length})</span>
              </button>
            `).join('')}
          </div>
        </div>

        <!-- TAB CONTENT 1: LỘ TRÌNH THEO CỮ -->
        <div id="content-tab-schedule" class="space-y-4">
          <div id="selected-slot-details-view" class="space-y-3">
            ${renderSelectedSlotFullView(smartSlot || activeSlots[0])}
          </div>
        </div>

        <!-- TAB CONTENT 2: TỦ THUỐC & TRA CỨU DƯỢC THƯ (FORMULARY) -->
        <div id="content-tab-formulary" class="hidden space-y-3">
          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            ${meds.map((m, idx) => `
              <div class="glass-card rounded-2xl p-4 border border-white/10 hover:border-sky-400/50 bg-white/[0.05] transition-all space-y-2.5">
                <div class="flex items-start justify-between gap-2">
                  <div class="flex items-center space-x-2.5">
                    <div class="w-8 h-8 rounded-xl bg-sky-500/20 text-sky-300 flex items-center justify-center font-mono font-black text-xs shrink-0 border border-sky-400/30">
                      ${idx + 1}
                    </div>
                    <div>
                      <h4 class="text-sm font-black text-white">${m.name}</h4>
                      <p class="text-[11px] font-mono text-slate-400 font-semibold">${m.ingredient || ''}</p>
                    </div>
                  </div>
                  <span class="px-2.5 py-0.5 rounded-md text-[10px] font-black uppercase tracking-wider bg-sky-500/20 text-sky-300 border border-sky-400/30 shrink-0">
                    ${m.category || 'Thuốc kê đơn'}
                  </span>
                </div>

                <div class="text-xs text-slate-300 leading-relaxed glass-card p-2.5 rounded-xl border border-white/5 bg-white/5">
                  <span class="font-black text-white">Mục đích điều trị:</span> ${m.purpose}
                </div>

                <div class="text-xs text-teal-200 font-bold bg-teal-500/15 border border-teal-400/30 rounded-xl p-2.5 leading-relaxed flex items-center justify-between gap-2">
                  <div>
                    <span class="font-extrabold">Cách dùng:</span> ${m.usage}
                  </div>
                  <button onclick="askBotAboutSpecificMedicine('${m.name}')" class="text-[11px] text-sky-400 hover:text-sky-300 underline font-extrabold whitespace-nowrap cursor-pointer">
                    Hỏi AI →
                  </button>
                </div>
              </div>
            `).join('')}
          </div>
        </div>

      </div>

      <!-- 5. BOTTOM UTILITIES -->
      <div class="flex flex-wrap items-center justify-between gap-3 pt-2">
        <div class="flex items-center space-x-2">
          <button onclick="setMedicationReminder()" class="px-4 py-2.5 rounded-2xl glass-pill hover:bg-white/15 text-slate-200 text-xs font-bold transition-all flex items-center space-x-2 cursor-pointer border border-white/10">
            <svg class="w-4 h-4 text-sky-400" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"/></svg>
            <span>Nhắc nhở uống thuốc định kỳ</span>
          </button>
        </div>

        <button type="button" onclick="resetPrescriptionScan()" class="px-4 py-2.5 rounded-2xl glass-pill hover:bg-white/15 text-slate-300 hover:text-white text-xs font-bold transition-all flex items-center space-x-2 cursor-pointer border border-white/10" title="Quay lại vùng tải đơn thuốc mới">
          <svg class="w-4 h-4 text-slate-300" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18"/></svg>
          <span>← Tải lên đơn thuốc khác</span>
        </button>
      </div>

    </div>
  `;

  resSec.innerHTML = html;
  resSec.classList.remove('hidden');
}

// Render the checklist inside the Smart Hero card
function renderSlotPillChecklist(slot) {
  if (!slot || !slot.items || slot.items.length === 0) {
    return `<div class="p-4 rounded-2xl glass-card text-center text-xs text-slate-400 font-medium">Không có thuốc chỉ định ở cữ này</div>`;
  }

  const beforeMeal = slot.items.filter(it => (it.note || '').toLowerCase().includes('trước'));
  const externalPills = slot.items.filter(it => (it.note || '').toLowerCase().includes('ngoài') || (it.tag || '').toLowerCase().includes('ngoài'));
  const afterMeal = slot.items.filter(it => !beforeMeal.includes(it) && !externalPills.includes(it));

  return `
    <!-- BEFORE MEAL -->
    ${beforeMeal.length > 0 ? `
      <div class="space-y-2">
        <div class="text-[10px] font-black uppercase tracking-wider text-amber-300 bg-amber-500/20 border border-amber-400/30 px-2.5 py-0.5 rounded-lg inline-flex items-center">
          <span class="w-2 h-2 rounded-full bg-amber-400 mr-1.5 animate-pulse"></span>UỐNG TRƯỚC KHI ĂN (30 PHÚT)
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
          ${beforeMeal.map((m, idx) => `
            <div class="flex items-center justify-between p-3 rounded-2xl glass-card border border-amber-400/30 bg-amber-950/20 text-xs hover:border-amber-400/60 transition-colors">
              <div class="flex items-center space-x-2.5 min-w-0">
                <input type="checkbox" onchange="togglePillChecked(this)" class="w-4 h-4 rounded text-amber-500 focus:ring-amber-400 border-amber-400/50 bg-slate-900 cursor-pointer">
                <div class="truncate">
                  <span class="font-black text-white leading-snug block truncate pill-name">${m.name}</span>
                  <span class="text-[10px] text-amber-300 font-bold">${m.tag || 'Trước ăn'}</span>
                </div>
              </div>
              <span class="font-mono font-black text-amber-200 bg-amber-500/30 border border-amber-400/40 px-3 py-1 rounded-xl text-xs shrink-0 ml-2 shadow-2xs">${m.dosage}</span>
            </div>
          `).join('')}
        </div>
      </div>
    ` : ''}

    <!-- AFTER MEAL -->
    ${afterMeal.length > 0 ? `
      <div class="space-y-2 mt-2">
        <div class="text-[10px] font-black uppercase tracking-wider text-sky-300 bg-sky-500/20 border border-sky-400/30 px-2.5 py-0.5 rounded-lg inline-flex items-center">
          <span class="w-2 h-2 rounded-full bg-sky-400 mr-1.5 animate-pulse"></span>UỐNG SAU KHI ĂN NO
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
          ${afterMeal.map((m, idx) => `
            <div class="flex items-center justify-between p-3 rounded-2xl glass-card border border-white/10 bg-white/[0.04] text-xs hover:border-sky-400/50 transition-colors">
              <div class="flex items-center space-x-2.5 min-w-0">
                <input type="checkbox" onchange="togglePillChecked(this)" class="w-4 h-4 rounded text-sky-500 focus:ring-sky-400 border-white/20 bg-slate-900 cursor-pointer">
                <div class="truncate">
                  <span class="font-black text-white leading-snug block truncate pill-name">${m.name}</span>
                  <span class="text-[10px] text-slate-400 font-bold">${m.tag || 'Sau ăn'}</span>
                </div>
              </div>
              <span class="font-mono font-black text-sky-200 bg-sky-500/30 border border-sky-400/40 px-3 py-1 rounded-xl text-xs shrink-0 ml-2 shadow-2xs">${m.dosage}</span>
            </div>
          `).join('')}
        </div>
      </div>
    ` : ''}

    <!-- EXTERNAL APPLICATION (XOA BÓP NGOÀI DA) -->
    ${externalPills.length > 0 ? `
      <div class="space-y-2 mt-2">
        <div class="text-[10px] font-black uppercase tracking-wider text-purple-300 bg-purple-500/20 border border-purple-400/30 px-2.5 py-0.5 rounded-lg inline-flex items-center">
          <span class="w-2 h-2 rounded-full bg-purple-400 mr-1.5 animate-pulse"></span>CHẾ PHẨM DÙNG NGOÀI DA (TUYỆT ĐỐI KHÔNG UỐNG)
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
          ${externalPills.map((m, idx) => `
            <div class="flex items-center justify-between p-3 rounded-2xl glass-card border border-purple-400/30 bg-purple-950/20 text-xs hover:border-purple-400/60 transition-colors">
              <div class="flex items-center space-x-2.5 min-w-0">
                <input type="checkbox" onchange="togglePillChecked(this)" class="w-4 h-4 rounded text-purple-500 focus:ring-purple-400 border-purple-400/50 bg-slate-900 cursor-pointer">
                <div class="truncate">
                  <span class="font-black text-white leading-snug block truncate pill-name">${m.name}</span>
                  <span class="text-[10px] text-purple-300 font-bold">${m.note || 'Xoa lưng đau'}</span>
                </div>
              </div>
              <span class="font-mono font-black text-purple-200 bg-purple-500/30 border border-purple-400/40 px-3 py-1 rounded-xl text-xs shrink-0 ml-2 shadow-2xs">${m.dosage}</span>
            </div>
          `).join('')}
        </div>
      </div>
    ` : ''}
  `;
}

// Render full view when clicking a specific slot tab
function renderSelectedSlotFullView(slot) {
  return `
    <div class="p-4 sm:p-5 rounded-2xl border border-white/10 glass-card bg-white/[0.05] space-y-4">
      <div class="flex items-center justify-between pb-3 border-b border-white/10">
        <div class="flex items-center space-x-2.5">
          <span class="text-2xl">${slot.icon}</span>
          <div>
            <h4 class="text-sm font-black text-white">${slot.label}</h4>
            <p class="text-xs text-slate-400 font-mono">${slot.time}</p>
          </div>
        </div>
        <span class="text-xs font-mono font-black px-3 py-1 rounded-full bg-sky-500/20 text-sky-300 border border-sky-400/30">
          ${slot.items.length} loại thuốc
        </span>
      </div>
      <div>
        ${renderSlotPillChecklist(slot)}
      </div>
    </div>
  `;
}

// Checkbox item micro-interaction
function togglePillChecked(checkbox) {
  const container = checkbox.closest('div');
  const nameEl = container.querySelector('.pill-name');
  if (checkbox.checked) {
    if (nameEl) nameEl.classList.add('line-through', 'opacity-50');
    playMedicalChime();
  } else {
    if (nameEl) nameEl.classList.remove('line-through', 'opacity-50');
  }
}

// Toggle hero slot completion button
function toggleHeroSlotCompletion(slotId, btnEl) {
  if (!slotId) return;
  adherenceSlotState[slotId] = !adherenceSlotState[slotId];
  const isDone = adherenceSlotState[slotId];

  triggerCelebration(btnEl);

  const btnText = document.getElementById('btn-hero-complete-text');
  if (isDone) {
    btnEl.className = 'w-full sm:w-auto px-8 py-3.5 bg-emerald-800 text-white text-sm font-extrabold rounded-2xl shadow-md transition-all flex items-center justify-center space-x-2.5 cursor-pointer border border-emerald-500/30';
    if (btnText) {
      const nowStr = new Date().toLocaleTimeString('vi-VN', { hour: '2-digit', minute: '2-digit' });
      btnText.innerText = `✓ ĐÃ HOÀN THÀNH CỮ NÀY LÚC ${nowStr}`;
    }
    showMedicalToast(`Tuyệt vời! Bạn đã hoàn thành cữ thuốc.`, 'success');
  } else {
    btnEl.className = 'w-full sm:w-auto px-8 py-3.5 bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-white text-sm font-extrabold rounded-2xl shadow-lg shadow-emerald-500/30 transition-all flex items-center justify-center space-x-2.5 cursor-pointer hover:scale-102 border border-white/20';
    if (btnText) btnText.innerText = 'XÁC NHẬN ĐÃ UỐNG XONG CỮ NÀY';
  }

  updateAdherenceProgress();
}

function updateAdherenceProgress() {
  const keys = Object.keys(adherenceSlotState);
  const total = keys.length || 3;
  const completed = keys.filter(k => adherenceSlotState[k]).length;
  const percent = Math.round((completed / total) * 100);

  const textEl = document.getElementById('adherence-progress-text');
  const barEl = document.getElementById('adherence-progress-bar');

  if (textEl) textEl.innerText = `${completed}/${total} cữ (${percent}%)`;
  if (barEl) barEl.style.width = `${percent}%`;
}

// Toggle expanding all doctor's warnings
function toggleWarningDetails() {
  const list = document.getElementById('expanded-warning-list');
  const icon = document.getElementById('icon-toggle-warnings');
  const label = document.getElementById('label-toggle-warnings');
  if (!list) return;

  if (list.classList.contains('hidden')) {
    list.classList.remove('hidden');
    if (icon) icon.classList.add('rotate-180');
    if (label) label.innerText = 'Thu gọn';
  } else {
    list.classList.add('hidden');
    if (icon) icon.classList.remove('rotate-180');
    if (label) label.innerText = `Xem tất cả (${(currentPrescriptionData?.warnings || []).length})`;
  }
}

// Switching between "Lộ trình" and "Tủ thuốc"
function switchPrescriptionMainTab(tab) {
  const schedTab = document.getElementById('content-tab-schedule');
  const formTab = document.getElementById('content-tab-formulary');
  const navSched = document.getElementById('tab-nav-schedule');
  const navForm = document.getElementById('tab-nav-formulary');
  const quickSwitcher = document.getElementById('quick-slot-switcher');

  if (tab === 'schedule') {
    if (schedTab) schedTab.classList.remove('hidden');
    if (formTab) formTab.classList.add('hidden');
    if (quickSwitcher) quickSwitcher.classList.remove('hidden');
    if (navSched) navSched.className = 'px-4 py-2 rounded-xl text-xs font-black transition-all bg-white text-slate-950 shadow-md cursor-pointer';
    if (navForm) navForm.className = 'px-4 py-2 rounded-xl text-xs font-black transition-all text-slate-300 hover:text-white cursor-pointer';
  } else {
    if (schedTab) schedTab.classList.add('hidden');
    if (formTab) formTab.classList.remove('hidden');
    if (quickSwitcher) quickSwitcher.classList.add('hidden');
    if (navSched) navSched.className = 'px-4 py-2 rounded-xl text-xs font-black transition-all text-slate-300 hover:text-white cursor-pointer';
    if (navForm) navForm.className = 'px-4 py-2 rounded-xl text-xs font-black transition-all bg-white text-slate-950 shadow-md cursor-pointer';
  }
}

// Switch slot in the view
function selectSpecificSlot(slotId) {
  currentSelectedSlotId = slotId;
  const tl = currentPrescriptionData?.timeline || {};
  const allSlotDefs = [
    { id: 'morning', label: 'BUỔI SÁNG', time: '06:30 - 08:00', icon: '🌅', items: tl.morning || [] },
    { id: 'noon', label: 'BUỔI TRƯA', time: '11:30 - 12:30', icon: '☀️', items: tl.noon || [] },
    { id: 'evening', label: 'CHIỀU / TỐI', time: '18:00 - 19:30', icon: '🌙', items: tl.evening || [] },
    { id: 'bedtime', label: 'TRƯỚC KHI NGỦ', time: '21:00 - 22:00', icon: '🛌', items: tl.bedtime || [] },
    { id: 'external', label: 'DÙNG NGOÀI DA', time: 'Sáng & Tối', icon: '🧴', items: tl.external || [] }
  ];
  const target = allSlotDefs.find(s => s.id === slotId);

  allSlotDefs.forEach(s => {
    const pill = document.getElementById(`pill-slot-${s.id}`);
    if (pill) {
      if (s.id === slotId) {
        pill.className = 'px-3 py-1.5 rounded-xl text-xs font-bold transition-all flex items-center space-x-1 cursor-pointer bg-sky-500 text-white shadow-lg shadow-sky-500/30 border border-white/20';
      } else {
        pill.className = 'px-3 py-1.5 rounded-xl text-xs font-bold transition-all flex items-center space-x-1 cursor-pointer glass-pill text-slate-300 hover:text-white';
      }
    }
  });

  const viewContainer = document.getElementById('selected-slot-details-view');
  if (viewContainer && target) {
    viewContainer.innerHTML = renderSelectedSlotFullView(target);
  }
}

function setMedicationReminder() {
  playMedicalChime();
  showMedicalToast('Xem thử tính năng nhắc thuốc: Đây là bản minh họa giao diện các cữ uống thuốc trong ngày.', 'info', 4000);
}

function askBotAboutPrescription() {
  if (!currentPrescriptionData) return;
  const diag = currentPrescriptionData.diagnosis || '';
  switchTab('chat-tab');
  const chatInput = document.getElementById('chat-input') || document.getElementById('user-input');
  if (chatInput) {
    chatInput.value = `Xin bác sĩ tư vấn kỹ hơn về hướng điều trị, cách dùng thuốc và lưu ý kiêng khem cho chẩn đoán: "${diag}".`;
    chatInput.focus();
  }
}

function askBotAboutSpecificMedicine(medName) {
  switchTab('chat-tab');
  const chatInput = document.getElementById('chat-input') || document.getElementById('user-input');
  if (chatInput) {
    chatInput.value = `Bác sĩ giải thích giúp tôi công dụng, cách dùng và tác dụng phụ cần chú ý khi uống thuốc: "${medName}".`;
    chatInput.focus();
  }
}

// ==============================================================================
// CLINICAL MINIMAL AMBIENT PRESETS (Ultra-clean, Low-detail & VisionOS Mesh)
// ==============================================================================
const medicalWallpapers = [
  { 
    id: 'minimal_midnight', 
    name: 'Tối giản Midnight Aurora (Chuẩn VisionOS - Mặc định)', 
    dark: 'radial-gradient(circle at 15% 15%, rgba(14, 165, 233, 0.16) 0%, transparent 45%), radial-gradient(circle at 85% 10%, rgba(99, 102, 241, 0.14) 0%, transparent 40%), radial-gradient(circle at 50% 60%, rgba(245, 158, 11, 0.05) 0%, transparent 50%), radial-gradient(circle at 85% 85%, rgba(14, 165, 233, 0.10) 0%, transparent 45%), radial-gradient(circle at 10% 90%, rgba(16, 185, 129, 0.08) 0%, transparent 40%), linear-gradient(180deg, #090D16 0%, #06080F 50%, #030408 100%)',
    light: 'radial-gradient(ellipse at 50% 0%, rgba(14, 165, 233, 0.12) 0%, transparent 60%), radial-gradient(ellipse at 85% 85%, rgba(99, 102, 241, 0.08) 0%, transparent 50%), linear-gradient(180deg, #F8FAFC 0%, #EEF2F6 100%)'
  },
  { 
    id: 'minimal_cyan', 
    name: 'Ánh sáng Lâm sàng Cyan (Clinical Cyan Glow)', 
    dark: 'radial-gradient(circle at 20% 20%, rgba(56, 189, 248, 0.18) 0%, transparent 50%), radial-gradient(circle at 80% 80%, rgba(14, 165, 233, 0.12) 0%, transparent 50%), linear-gradient(180deg, #050B14 0%, #081324 50%, #03070D 100%)',
    light: 'radial-gradient(ellipse at 20% 10%, rgba(56, 189, 248, 0.14) 0%, transparent 50%), linear-gradient(180deg, #F0F9FF 0%, #E0F2FE 100%)'
  },
  { 
    id: 'minimal_sapphire', 
    name: 'Không gian Sapphire Y tế (Sapphire Twilight)', 
    dark: 'radial-gradient(circle at 75% 15%, rgba(99, 102, 241, 0.18) 0%, transparent 50%), radial-gradient(circle at 20% 85%, rgba(14, 165, 233, 0.12) 0%, transparent 45%), linear-gradient(180deg, #080A18 0%, #0D1226 50%, #05060E 100%)',
    light: 'radial-gradient(ellipse at 80% 15%, rgba(99, 102, 241, 0.12) 0%, transparent 50%), linear-gradient(180deg, #EEF2FF 0%, #E0E7FF 100%)'
  },
  { 
    id: 'minimal_slate', 
    name: 'Kính Khói Neutral Studio (Minimal Dark Slate)', 
    dark: 'radial-gradient(circle at 50% 0%, rgba(255, 255, 255, 0.06) 0%, transparent 60%), linear-gradient(180deg, #0F172A 0%, #090E1A 50%, #030712 100%)',
    light: 'radial-gradient(circle at 50% 0%, rgba(15, 23, 42, 0.04) 0%, transparent 60%), linear-gradient(180deg, #FFFFFF 0%, #F1F5F9 100%)'
  }
];

let currentWallpaperIndex = 0;

function cycleMedicalWallpaper() {
  currentWallpaperIndex = (currentWallpaperIndex + 1) % medicalWallpapers.length;
  const wp = medicalWallpapers[currentWallpaperIndex];
  const isLight = document.body.classList.contains('light-glass');
  
  document.body.style.backgroundImage = isLight ? wp.light : wp.dark;
  showMedicalToast("Đã chuyển không gian: " + wp.name, "info");
  playMedicalChime();
}

function toggleGlassThemeMode() {
  document.body.classList.toggle('light-glass');
  const isLight = document.body.classList.contains('light-glass');
  const wp = medicalWallpapers[currentWallpaperIndex];
  
  document.body.style.backgroundImage = isLight ? wp.light : wp.dark;
  if (isLight) {
    showMedicalToast("Đã kích hoạt: Kính Sáng Y Tế Lâm Sàng (Daylight Minimal)", "success");
  } else {
    showMedicalToast("Đã kích hoạt: Kính Trong Suốt Spatial VisionOS (Dark Minimal)", "info");
  }
  playMedicalChime();
}

// ==========================================
// User Interaction Helpers (Export, GPS, Demo)
// ==========================================
const loadPresetPrescription = loadPrescriptionPreset;

function exportPdfSummary() {
  showMedicalToast('Đang tạo bản in / kết xuất PDF hồ sơ bệnh án...', 'info', 2000);
  setTimeout(() => {
    window.print();
  }, 250);
}

function requestUserLocation() {
  const statusText = document.getElementById('gps-status-text');
  if (!navigator.geolocation) {
    showMedicalToast('Trình duyệt không hỗ trợ Geolocation GPS.', 'warning');
    return;
  }
  if (statusText) statusText.innerText = 'Đang định vị GPS...';
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      const { latitude, longitude } = pos.coords;
      if (statusText) statusText.innerText = `Đã định vị (${latitude.toFixed(2)}, ${longitude.toFixed(2)})`;
      showMedicalToast('Đã xác định vị trí GPS thực tế. Khoảng cách đã được đồng bộ.', 'success');
    },
    (err) => {
      if (statusText) statusText.innerText = 'Khu vực: TP.HCM (Khoảng cách ước tính)';
      showMedicalToast('Không thể lấy vị trí GPS thực. Đang dùng mốc ước tính TP.HCM.', 'info');
    },
    { timeout: 8000 }
  );
}

function loadDemoConsultation() {
  switchTab('chat-tab');
  hideFloatingDecorations();
  const container = document.getElementById('chat-messages');
  if (!container) return;

  container.innerHTML = `
    <div class="p-3 mb-3 rounded-2xl bg-sky-950/70 border border-sky-400/40 text-sky-200 text-xs flex items-center justify-between shadow-lg">
      <div class="flex items-center space-x-2">
        <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-sky-500/30 text-sky-300 border border-sky-400/30">MẪU DEMO</span>
        <span>Hội thoại mẫu minh họa quy trình sàng lọc lâm sàng</span>
      </div>
      <button onclick="resetChat()" class="text-[11px] underline text-sky-400 hover:text-white cursor-pointer font-medium">Làm mới hội thoại</button>
    </div>

    <!-- User demo message -->
    <div class="flex flex-col items-end my-1">
      <div class="w-fit max-w-[85%] bg-gradient-to-r from-sky-500/90 to-indigo-600/90 text-white px-4 py-2.5 rounded-2xl rounded-tr-sm text-xs sm:text-sm shadow-lg shadow-sky-500/20 backdrop-blur-md leading-relaxed font-medium text-left break-words border border-white/20">
        <div>Tôi bị ho khan kéo dài 4 ngày nay, kèm đau rát họng và sốt nhẹ 37.8°C, không khó thở. Tôi nên làm gì?</div>
      </div>
      <div class="text-right text-[10px] text-slate-400 mt-1 mr-1">Người bệnh (Bản mẫu)</div>
    </div>

    <!-- Assistant demo response -->
    <div class="flex justify-start max-w-[95%] sm:max-w-xl my-2">
      <div class="glass-card border border-white/10 p-4 sm:p-5 rounded-2xl rounded-tl-sm text-xs sm:text-sm text-slate-200 space-y-3 leading-relaxed shadow-xl w-full backdrop-blur-xl bg-white/[0.06]">
        <div class="flex items-center justify-between pb-2 border-b border-white/10">
          <span class="text-[11px] font-bold text-sky-300">Trợ lý sức khỏe AI • Đánh giá sơ bộ</span>
          <span class="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-400/30 font-semibold">Sàng lọc: Theo dõi &amp; chăm sóc tại nhà</span>
        </div>
        <div class="text-slate-200 font-normal leading-relaxed space-y-2">
          <p><strong>1. Đánh giá sơ bộ & Phân tầng lâm sàng:</strong><br>
          • <strong>Triệu chứng:</strong> Ho khan 4 ngày, rát họng, sốt nhẹ 37.8°C.<br>
          • <strong>Dấu hiệu phủ nhận (an toàn):</strong> Không khó thở, không tức ngực, không nôn.<br>
          • <strong>Hướng xử trí:</strong> Phù hợp theo dõi và chăm sóc ban đầu tại nhà.</p>

          <p><strong>2. Khuyến nghị chăm sóc tại nhà:</strong><br>
          • Nghỉ ngơi trong phòng thoáng khí, uống đủ nước ấm (2 - 2.5 lít/ngày).<br>
          • Súc họng bằng dung dịch nước muối sinh lý 0.9% từ 3 - 4 lần mỗi ngày.<br>
          • Nếu sốt trên 38.5°C gây mệt mỏi, có thể dùng Paracetamol 500mg (1 viên/lần, cách 4-6 giờ, tối đa không quá 3g/ngày và không có tiền sử bệnh gan).</p>

          <p class="text-amber-300 text-xs bg-amber-500/10 p-2.5 rounded-xl border border-amber-400/20">
            ⚠️ <strong>Dấu hiệu cần đi khám ngay:</strong> Sốt cao liên tục &gt; 39°C không hạ sau 48h, khó thở, thở rít, đau tức ngực hoặc khạc đờm lẫn máu.
          </p>
        </div>
      </div>
    </div>
  `;

  container.scrollTop = container.scrollHeight;

  // Cập nhật Dữ kiện Lâm sàng Mẫu vào Live Intake Card & Summary (Tuân thủ Mục 8 & 9)
  const demoFacts = {
    chief_complaint: "Ho khan 4 ngày, đau rát họng, sốt nhẹ 37.8°C",
    present_symptoms: ["Sốt / Thân nhiệt tăng", "Đau rát họng / Nuốt đau", "Ho khan / Ho có đờm"],
    denied_symptoms: ["Khó thở / Hụt hơi", "Đau tức ngực"],
    duration: "4 ngày nay",
    vitals: { temperature: "37.8°C" }
  };

  currentIntakeSummary = {
    part_a_patient_facts: {
      title: "Phần A — Thông tin đã thu thập từ người bệnh",
      chief_complaint: demoFacts.chief_complaint,
      symptoms_present: demoFacts.present_symptoms,
      symptoms_denied: demoFacts.denied_symptoms,
      duration: demoFacts.duration,
      vitals: "temperature: 37.8°C",
      allergies: "Chưa ghi nhận tiền sử dị ứng đặc biệt",
      current_medications: "Chưa ghi nhận thuốc đang dùng",
      attachments_and_observations: "Không có tệp hình ảnh đính kèm",
      missing_or_unclear_info: ["Thông tin cơ bản ban đầu đã đầy đủ"]
    },
    part_b_system_assessment: {
      title: "Phần B — Đánh giá sơ bộ & Hướng tiếp cận chăm sóc",
      triage_status: "Theo dõi & Chăm sóc ban đầu tại nhà",
      triage_badge: "self_care",
      recommended_specialist: "Tai Mũi Họng / Y học gia đình",
      care_approach: "Triệu chứng ở mức độ nhẹ ban đầu. Người bệnh có thể nghỉ ngơi, uống đủ nước ấm, giữ ấm cơ thể và theo dõi diễn biến trong 24-48 giờ tới.",
      sources: [
        { title: "Sore throat", source: "MedlinePlus (NIH)", url: "https://medlineplus.gov/sorethroat.html" },
        { title: "Cough", source: "MedlinePlus (NIH)", url: "https://medlineplus.gov/cough.html" }
      ],
      limitations: "Kết quả do trợ lý AI tổng hợp phục vụ tham khảo và tóm tắt trước khám. Đây KHÔNG phải là chẩn đoán y khoa chính thức thay thế bác sĩ điều trị.",
      version: 1,
      created_at: new Date().toLocaleTimeString('vi-VN') + " hôm nay",
      confirmation_status: "Đã được người bệnh xác nhận lời khai"
    },
    is_confirmed: true,
    version: 1
  };

  updateLiveIntakeCard(demoFacts, 'confirmed', currentIntakeSummary);

  const demoSession = {
    id: 'demo_consultation_ho_sot',
    title: '[MẪU] Ho khan & sốt nhẹ',
    lastMessage: 'Ho khan 4 ngày, đau rát họng, sốt nhẹ 37.8°C...',
    timestamp: Date.now(),
    messageCount: 2,
    messages: [
      { role: 'user', content: 'Tôi bị ho khan 4 ngày nay kèm đau rát họng, sốt nhẹ 37.8°C, không khó thở hay đau tức ngực.' },
      { role: 'assistant', content: 'Chào bạn, mình đã ghi nhận triệu chứng ho khan và sốt nhẹ 37.8°C.\n• Uống nhiều nước ấm và súc họng nước muối sinh lý ấm 3 lần/ngày.\n• Nghỉ ngơi thoáng khí, ăn cháo súp nóng để làm dịu họng.\n• Uống Paracetamol 500mg nếu sốt >38.5°C.\n⚠️ Đi khám ngay: Nếu sốt cao >48h hoặc khó thở.' }
    ],
    facts: demoFacts,
    summary: currentIntakeSummary,
    status: 'confirmed',
    riskLevel: 'Theo dõi tại nhà',
    riskScore: 30,
    riskBadgeClass: 'bg-emerald-500/20 text-emerald-300 border border-emerald-400/30'
  };

  currentConversationId = demoSession.id;
  const existingIdx = chatSessions.findIndex(s => s.id === demoSession.id);
  if (existingIdx !== -1) {
    chatSessions.splice(existingIdx, 1);
  }
  chatSessions.unshift(demoSession);
  saveSessionsToStorage();
  renderChatHistoryList();

  showMedicalToast('Đã nạp hội thoại mẫu (Demo). Đây là dữ liệu minh họa, không phải lịch sử y tế thật.', 'info', 4000);
}

// ==========================================
// Session Management & History Synchronization
// ==========================================

function saveSessionsToStorage() {
  try {
    localStorage.setItem('medimind_chat_sessions_v2', JSON.stringify(chatSessions));
  } catch (e) {
    console.warn('Lỗi lưu lịch sử chat vào localStorage:', e);
  }
}

function formatSessionTime(timestamp) {
  if (!timestamp) return 'Vừa xong';
  const diffSec = Math.floor((Date.now() - timestamp) / 1000);
  if (diffSec < 60) return 'Vừa xong';
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)} phút trước`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)} giờ trước`;
  const d = new Date(timestamp);
  return `${d.getDate()}/${d.getMonth() + 1}`;
}

function saveOrUpdateCurrentSession(lastUserText, triageData, intakeData) {
  if (!currentConversationId) {
    currentConversationId = 'conv_' + Date.now().toString(36) + '_' + Math.random().toString(36).substr(2, 5);
  }

  let session = chatSessions.find(s => s.id === currentConversationId);
  const title = (session && session.title) ? session.title : (lastUserText.length > 30 ? lastUserText.slice(0, 30) + '...' : lastUserText);

  const facts = intakeData?.facts || session?.facts || {};
  const summary = intakeData?.summary || session?.summary || currentIntakeSummary || null;
  const status = intakeData?.status || session?.status || 'collecting';
  const riskLevel = triageData?.risk_level || session?.riskLevel || 'Theo dõi & Chăm sóc';
  const riskScore = triageData?.risk_score ?? session?.riskScore ?? 25;
  const isEmergency = triageData?.is_emergency ?? session?.isEmergency ?? false;

  let riskBadgeClass = 'bg-emerald-500/20 text-emerald-300 border border-emerald-400/30';
  if (isEmergency || riskScore >= 70) {
    riskBadgeClass = 'bg-rose-500/20 text-rose-300 border border-rose-400/30';
  } else if (riskScore >= 35) {
    riskBadgeClass = 'bg-amber-500/20 text-amber-300 border border-amber-400/30';
  }

  const updatedSession = {
    id: currentConversationId,
    title: title,
    lastMessage: triageData?.answer ? triageData.answer.slice(0, 75).replace(/\n/g, ' ') : lastUserText,
    timestamp: Date.now(),
    messageCount: chatHistory.length,
    messages: JSON.parse(JSON.stringify(chatHistory)),
    facts: facts,
    summary: summary,
    status: status,
    riskLevel: riskLevel,
    riskScore: riskScore,
    riskBadgeClass: riskBadgeClass,
    isEmergency: isEmergency
  };

  if (session) {
    const idx = chatSessions.indexOf(session);
    chatSessions.splice(idx, 1);
  }
  chatSessions.unshift(updatedSession);
  if (chatSessions.length > 30) chatSessions.length = 30;
  saveSessionsToStorage();
  renderChatHistoryList();
}

function renderChatHistoryList(filterQuery = '') {
  const historyList = document.getElementById('chat-history-list');
  const historyEmpty = document.getElementById('chat-history-empty');
  if (!historyList) return;

  const query = (filterQuery || '').trim().toLowerCase();
  const filtered = chatSessions.filter(s => {
    if (!query) return true;
    const matchTitle = (s.title || '').toLowerCase().includes(query);
    const matchMsg = (s.lastMessage || '').toLowerCase().includes(query);
    const matchRisk = (s.riskLevel || '').toLowerCase().includes(query);
    return matchTitle || matchMsg || matchRisk;
  });

  if (chatSessions.length === 0) {
    historyList.classList.add('hidden');
    historyList.innerHTML = '';
    if (historyEmpty) historyEmpty.classList.remove('hidden');
    return;
  }

  if (historyEmpty) historyEmpty.classList.add('hidden');
  historyList.classList.remove('hidden');

  if (filtered.length === 0) {
    historyList.innerHTML = `
      <div class="p-3 text-center text-xs text-white/40 italic rounded-xl bg-white/[0.02] border border-white/5">
        Không tìm thấy phiên tư vấn nào khớp với "<strong>${escapeHtml(query)}</strong>"
      </div>
    `;
    return;
  }

  historyList.innerHTML = filtered.map(session => {
    const isActive = session.id === currentConversationId;
    const timeFormatted = formatSessionTime(session.timestamp);

    return `
      <div onclick="loadSession('${session.id}')" 
           class="chat-history-item p-2.5 rounded-xl border transition-all cursor-pointer group relative ${isActive ? 'bg-sky-500/20 border-sky-400/60 shadow-md shadow-sky-500/15 ring-1 ring-sky-400/40' : 'bg-white/[0.03] border-white/10 hover:bg-white/[0.08] hover:border-white/20'}">
        <div class="flex items-center justify-between gap-1.5">
          <div class="flex items-center gap-1.5 min-w-0">
            ${isActive ? '<span class="w-2 h-2 rounded-full bg-sky-400 animate-pulse shrink-0"></span>' : '<span class="w-1.5 h-1.5 rounded-full bg-white/30 shrink-0"></span>'}
            <span class="text-xs font-bold text-white truncate group-hover:text-sky-200 transition-colors">${escapeHtml(session.title || 'Phiên tư vấn')}</span>
          </div>
          <div class="flex items-center gap-1 shrink-0">
            <span class="text-[10px] text-white/40">${timeFormatted}</span>
            <button type="button" onclick="event.stopPropagation(); deleteSession('${session.id}')" class="opacity-0 group-hover:opacity-100 p-0.5 text-white/40 hover:text-rose-400 transition-opacity" title="Xóa phiên tư vấn">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
            </button>
          </div>
        </div>
        <p class="text-[11px] text-white/60 truncate mt-1 leading-snug">${escapeHtml(session.lastMessage || '')}</p>
        <div class="flex items-center justify-between text-[10px] pt-1.5 mt-1 border-t border-white/5">
          <span class="text-sky-300 font-medium">${session.messageCount || 1} tin nhắn</span>
          <span class="px-1.5 py-0.5 rounded text-[9px] font-semibold ${session.riskBadgeClass || 'bg-emerald-500/20 text-emerald-300 border border-emerald-400/30'}">${escapeHtml(session.riskLevel || 'Theo dõi')}</span>
        </div>
      </div>
    `;
  }).join('');
}

function loadSession(sessionId) {
  const session = chatSessions.find(s => s.id === sessionId);
  if (!session) return;

  currentConversationId = session.id;
  currentIntakeSummary = session.summary || null;

  const container = document.getElementById('chat-messages');
  if (container) container.innerHTML = '';
  hideFloatingDecorations();

  chatHistory.length = 0;
  if (session.messages && Array.isArray(session.messages)) {
    session.messages.forEach(msg => {
      chatHistory.push(msg);
      if (msg.role === 'user') {
        let userImgHtml = '';
        if (msg.image) {
          userImgHtml = `
            <div class="mb-2 overflow-hidden rounded-xl border border-white/20 shadow-xs cursor-pointer max-w-[220px]" onclick="openImageModal('${msg.image}', 'Ảnh tổn thương bạn đã gửi', 'Ảnh người bệnh cung cấp')">
              <img src="${msg.image}" alt="Ảnh tải lên" class="w-full h-auto max-h-[160px] object-cover hover:scale-105 transition-transform duration-200">
            </div>
          `;
        }
        const userHtml = `
          <div class="flex flex-col items-end my-1">
            <div class="w-fit max-w-[85%] bg-gradient-to-r from-sky-500/90 to-indigo-600/90 text-white px-4 py-2.5 rounded-2xl rounded-tr-sm text-xs sm:text-sm shadow-lg shadow-sky-500/20 backdrop-blur-md leading-relaxed font-medium text-left break-words border border-white/20">
              ${userImgHtml}
              <div>${escapeHtml(msg.content)}</div>
            </div>
            <div class="text-right text-[10px] text-slate-400 mt-1 mr-1">${translations[currentLang]?.patient_label || 'Bệnh nhân'}</div>
          </div>
        `;
        container.insertAdjacentHTML('beforeend', userHtml);
      } else if (msg.role === 'assistant') {
        let formattedAnswer = escapeHtml(msg.content)
          .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
          .replace(/\*(.*?)\*/g, '<em>$1</em>')
          .replace(/\n/g, '<br>');

        const botHtml = `
          <div class="flex justify-start max-w-[95%] sm:max-w-xl">
            <div class="glass-card border border-white/10 p-4 sm:p-5 rounded-2xl rounded-tl-sm text-xs sm:text-sm text-slate-200 space-y-3 leading-relaxed shadow-xl w-full backdrop-blur-xl bg-white/[0.06]">
              <div class="text-slate-200 font-normal leading-relaxed">${formattedAnswer}</div>
            </div>
          </div>
        `;
        container.insertAdjacentHTML('beforeend', botHtml);
      }
    });
    container.scrollTop = container.scrollHeight;
  }

  if (session.facts) {
    updateLiveIntakeCard(session.facts, session.status || 'collecting', session.summary);
  }

  updateTriagePanel({
    risk_score: session.riskScore || 25,
    risk_level: session.riskLevel || 'Theo dõi & Chăm sóc',
    is_emergency: session.isEmergency || false
  });

  renderChatHistoryList();
}

function deleteSession(sessionId) {
  const idx = chatSessions.findIndex(s => s.id === sessionId);
  if (idx !== -1) {
    chatSessions.splice(idx, 1);
    saveSessionsToStorage();
    if (currentConversationId === sessionId) {
      resetChat();
    } else {
      renderChatHistoryList();
    }
    showMedicalToast('Đã xóa phiên tư vấn khỏi lịch sử.', 'info', 2500);
  }
}

async function syncServerConsultations() {
  if (!currentUser) return;
  try {
    const res = await fetch('/api/consultations').then(r => r.json());
    if (res && res.consultations && res.consultations.length > 0) {
      let hasNew = false;
      res.consultations.forEach(c => {
        const id = 'db_conv_' + c.id;
        if (!chatSessions.some(s => s.id === id || s.title === c.message.slice(0, 30))) {
          hasNew = true;
          chatSessions.push({
            id: id,
            title: c.message.length > 30 ? c.message.slice(0, 30) + '...' : c.message,
            lastMessage: c.answer ? c.answer.slice(0, 75).replace(/\n/g, ' ') : c.message,
            timestamp: Date.now() - 3600000,
            messageCount: 2,
            messages: [
              { role: 'user', content: c.message },
              { role: 'assistant', content: c.answer }
            ],
            riskLevel: c.risk_level || 'Theo dõi tại nhà',
            riskScore: c.risk_score || 30
          });
        }
      });
      if (hasNew) {
        saveSessionsToStorage();
        renderChatHistoryList();
      }
    }
  } catch (err) {
    console.warn('Lỗi đồng bộ lịch sử từ máy chủ:', err);
  }
}

// ==========================================
// Specialized Task-Based Navigation & Filters
// ==========================================
function openNewPrescriptionUpload() {
  switchTab('ocr-tab');
  resetPrescriptionScan();
}

function filterHospitals(category, btnEl) {
  document.querySelectorAll('.hospital-filter-btn').forEach(btn => {
    btn.classList.remove('bg-white/20', 'text-white', 'border', 'border-white/25', 'font-bold', 'shadow-xs');
    btn.classList.add('glass-pill', 'text-slate-300', 'font-semibold');
  });
  if (btnEl) {
    btnEl.classList.remove('glass-pill', 'text-slate-300', 'font-semibold');
    btnEl.classList.add('bg-white/20', 'text-white', 'border', 'border-white/25', 'font-bold', 'shadow-xs');
  }

  const cards = document.querySelectorAll('.hospital-card');
  let matchCount = 0;
  cards.forEach(card => {
    const cats = (card.getAttribute('data-category') || '').split(' ');
    if (category === 'all' || cats.includes(category)) {
      card.classList.remove('hidden');
      matchCount++;
    } else {
      card.classList.add('hidden');
    }
  });

  const noResults = document.getElementById('hospital-no-results');
  if (noResults) {
    noResults.classList.toggle('hidden', matchCount > 0);
  }
}

function initHistorySearch() {
  const searchInput = document.getElementById('history-search-input');
  if (!searchInput) return;

  searchInput.addEventListener('input', (e) => {
    renderChatHistoryList(e.target.value);
  });
}

// ==========================================
// Medical Records (Hồ sơ bệnh án) Interaction Logic (Theo Mẫu Ảnh 5 & 6)
// ==========================================
const medicalPatientsData = {
  minh_anh: {
    id: 'BN-8429',
    name: 'Nguyễn Minh Anh',
    gender: 'Nữ',
    age: 38,
    dob: '12/04/1988',
    blood: 'O+',
    phone: '0901 234 567',
    allergies: ['Penicillin', 'Hải sản'],
    visitCount: 3,
    lastVisitDate: '18/10/2026',
    badge: 'NA',
    records: [
      {
        id: 'rec_1',
        date: '18/10/2026',
        title: 'Viêm họng cấp',
        doctor: 'BS. Lê Thu Hà · Nội tổng quát',
        status: 'Đã hồi phục',
        statusType: 'success',
        icd: 'ICD-10: J02.9',
        vitals: {
          bp: '118/76 mmHg',
          hr: '88 lần/phút',
          temp: '38.2 °C',
          weight: '56.5 kg'
        },
        symptoms: 'Đau họng, sốt nhẹ 38.2°C, khó nuốt 3 ngày',
        labs: 'Xét nghiệm nhanh kháng nguyên liên cầu: âm tính. Bạch cầu 11.2 G/L, tăng nhẹ.',
        doctorNotes: 'Uống đủ nước, tái khám nếu sốt kéo dài trên 3 ngày.',
        followUp: 'Không hẹn tái khám'
      },
      {
        id: 'rec_2',
        date: '02/06/2026',
        title: 'Rối loạn nhịp xoang',
        doctor: 'BS. Phạm Đức Long · Tim mạch',
        status: 'Cần tái khám',
        statusType: 'info',
        icd: 'ICD-10: I49.5',
        vitals: {
          bp: '125/82 mmHg',
          hr: '94 lần/phút',
          temp: '37.0 °C',
          weight: '57.0 kg'
        },
        symptoms: 'Hồi hộp, đánh trống ngực từng cơn khi làm việc căng thẳng',
        labs: 'Điện tâm đồ (ECG): Nhịp xoang nhanh 94 bpm, không rối loạn tái cực ST-T.',
        doctorNotes: 'Hạn chế cà phê và chất kích thích, ngủ đủ 7-8 tiếng/ngày.',
        followUp: 'Tái khám sau 1 tháng'
      },
      {
        id: 'rec_3',
        date: '20/11/2025',
        title: 'Thiếu máu thiếu sắt',
        doctor: 'BS. Lê Thu Hà · Nội tổng quát',
        status: 'Đã hồi phục',
        statusType: 'success',
        icd: 'ICD-10: D50.9',
        vitals: {
          bp: '110/70 mmHg',
          hr: '78 lần/phút',
          temp: '36.8 °C',
          weight: '55.0 kg'
        },
        symptoms: 'Hoa mắt khi đứng dậy nhanh, mệt mỏi nhẹ vào buổi chiều',
        labs: 'Huyết học: Hb 10.8 g/dL (giảm nhẹ), Ferritin huyết thanh 14 ng/mL.',
        doctorNotes: 'Bổ sung viên sắt Ferrovit 1 viên/ngày sau ăn, tăng cường rau xanh đậm.',
        followUp: 'Đã hoàn thành đợt bổ sung sắt 3 tháng'
      }
    ]
  },
  quoc_bao: {
    id: 'BN-5102',
    name: 'Trần Quốc Bảo',
    gender: 'Nam',
    age: 51,
    dob: '05/09/1975',
    blood: 'A+',
    phone: '0918 765 432',
    allergies: ['Aspirin'],
    visitCount: 2,
    lastVisitDate: '15/09/2026',
    badge: 'TB',
    records: [
      {
        id: 'rec_qb1',
        date: '15/09/2026',
        title: 'Tăng huyết áp độ 2',
        doctor: 'BS. Phạm Đức Long · Tim mạch',
        status: 'Cần tái khám',
        statusType: 'info',
        icd: 'ICD-10: I10',
        vitals: {
          bp: '152/95 mmHg',
          hr: '84 lần/phút',
          temp: '36.7 °C',
          weight: '72.0 kg'
        },
        symptoms: 'Nặng đầu vùng sau gáy, hoa mắt khi thức dậy buổi sáng',
        labs: 'Sinh hóa máu: Creatinine 88 umol/L, Acid Uric 390 umol/L, Lipid máu tăng nhẹ.',
        doctorNotes: 'Duy trì thuốc hạ áp hàng ngày vào buổi sáng, ăn giảm muối < 5g/ngày.',
        followUp: 'Tái khám định kỳ sau 30 ngày'
      },
      {
        id: 'rec_qb2',
        date: '10/01/2026',
        title: 'Rối loạn lipid máu hỗn hợp',
        doctor: 'BS. Lê Thu Hà · Nội tổng quát',
        status: 'Đã hồi phục',
        statusType: 'success',
        icd: 'ICD-10: E78.2',
        vitals: {
          bp: '138/88 mmHg',
          hr: '76 lần/phút',
          temp: '36.6 °C',
          weight: '74.2 kg'
        },
        symptoms: 'Khám sức khỏe định kỳ doanh nghiệp, không triệu chứng rầm rộ',
        labs: 'Cholesterol toàn phần 6.2 mmol/L, Triglyceride 2.8 mmol/L.',
        doctorNotes: 'Tập thể dục ít nhất 30 phút/ngày, hạn chế rượu bia và mỡ động vật.',
        followUp: 'Xét nghiệm lại bộ mỡ máu sau 3 tháng'
      }
    ]
  }
};

let activeMedicalPatientKey = 'minh_anh';

function selectPatientProfile(patientKey) {
  const patient = medicalPatientsData[patientKey];
  if (!patient) return;
  activeMedicalPatientKey = patientKey;

  // Update switcher pills styling
  const pillMA = document.getElementById('patient-pill-minh_anh');
  const pillQB = document.getElementById('patient-pill-quoc_bao');

  if (pillMA && pillQB) {
    if (patientKey === 'minh_anh') {
      pillMA.className = 'patient-pill-btn flex items-center space-x-3 px-4 py-2.5 rounded-2xl bg-teal-500/20 text-white shadow-lg shadow-teal-500/10 border border-teal-400/50 backdrop-blur-xl transition-all cursor-pointer';
      pillQB.className = 'patient-pill-btn flex items-center space-x-3 px-4 py-2.5 rounded-2xl glass-pill text-slate-300 hover:text-white hover:bg-white/10 border border-white/10 transition-all cursor-pointer';
    } else {
      pillQB.className = 'patient-pill-btn flex items-center space-x-3 px-4 py-2.5 rounded-2xl bg-teal-500/20 text-white shadow-lg shadow-teal-500/10 border border-teal-400/50 backdrop-blur-xl transition-all cursor-pointer';
      pillMA.className = 'patient-pill-btn flex items-center space-x-3 px-4 py-2.5 rounded-2xl glass-pill text-slate-300 hover:text-white hover:bg-white/10 border border-white/10 transition-all cursor-pointer';
    }
  }

  // Update Left Card
  const heroName = document.getElementById('ehr-hero-name');
  const heroDemo = document.getElementById('ehr-hero-demographics');
  const avatarLarge = document.getElementById('ehr-avatar-large');
  const visitCount = document.getElementById('ehr-visit-count');
  const lastVisit = document.getElementById('ehr-last-visit-date');
  const dobVal = document.getElementById('ehr-dob-val');
  const bloodVal = document.getElementById('ehr-blood-val');
  const phoneVal = document.getElementById('ehr-phone-val');
  const allergiesContainer = document.getElementById('ehr-allergies-container');
  const countBadge = document.getElementById('ehr-records-count-badge');

  if (heroName) heroName.innerText = patient.name;
  if (heroDemo) heroDemo.innerText = `${patient.gender} · ${patient.age} tuổi`;
  if (avatarLarge) avatarLarge.innerText = patient.badge;
  if (visitCount) visitCount.innerText = patient.visitCount;
  if (lastVisit) lastVisit.innerText = patient.lastVisitDate;
  if (dobVal) dobVal.innerText = patient.dob;
  if (bloodVal) bloodVal.innerText = patient.blood;
  if (phoneVal) phoneVal.innerText = patient.phone;
  if (countBadge) countBadge.innerText = `${patient.records.length} hồ sơ`;

  if (allergiesContainer) {
    if (patient.allergies && patient.allergies.length > 0) {
      allergiesContainer.innerHTML = patient.allergies.map(alg => `
        <span class="inline-flex items-center space-x-1 px-2.5 py-1 rounded-lg text-xs font-semibold bg-rose-500/15 text-rose-300 border border-rose-400/30">
          <span>⚠️</span>
          <span>${alg}</span>
        </span>
      `).join('');
    } else {
      allergiesContainer.innerHTML = '<span class="text-xs text-slate-400">Không ghi nhận dị ứng</span>';
    }
  }

  // Render Right Timeline
  renderPatientTimeline(patient.records);
}

function renderPatientTimeline(records) {
  const container = document.getElementById('ehr-timeline-list');
  if (!container) return;

  container.innerHTML = records.map(rec => {
    return `
      <div onclick="openMedicalRecordDetail('${rec.id}')" class="relative group cursor-pointer">
        <!-- Timeline Indicator Dot -->
        <div class="absolute -left-[31px] top-4 w-3.5 h-3.5 rounded-full bg-teal-400 border-2 border-slate-900 shadow-md shadow-teal-400/50"></div>

        <!-- Card Content (Dark Glass) -->
        <div class="glass-card border border-white/10 rounded-2xl p-5 shadow-lg bg-white/[0.03] hover:bg-white/[0.06] hover:border-teal-400/40 hover:shadow-teal-500/10 backdrop-blur-xl transition-all">
          <div class="flex items-start justify-between gap-2">
            <div class="space-y-1">
              <span class="text-xs font-bold text-teal-400 font-mono">${rec.date}</span>
              <h4 class="text-base font-black text-white group-hover:text-teal-300 transition-colors">${rec.title}</h4>
              <p class="text-xs text-slate-400">${rec.doctor}</p>
              <div class="pt-2">
                <span class="px-2.5 py-1 rounded-lg bg-white/5 text-slate-300 text-[11px] font-mono border border-white/10">${rec.icd}</span>
              </div>
            </div>

            <div class="flex items-center self-center pl-2">
              <svg class="w-5 h-5 text-slate-400 group-hover:text-teal-300 group-hover:translate-x-1 transition-all" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="9 18 15 12 9 6"></polyline></svg>
            </div>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

function openMedicalRecordDetail(recordId) {
  const patient = medicalPatientsData[activeMedicalPatientKey];
  if (!patient) return;
  const rec = patient.records.find(r => r.id === recordId) || patient.records[0];
  if (!rec) return;

  const modal = document.getElementById('medical-record-modal');
  if (!modal) return;

  const dateEl = document.getElementById('modal-record-date');
  const titleEl = document.getElementById('modal-record-title');
  const doctorEl = document.getElementById('modal-record-doctor');
  const statusEl = document.getElementById('modal-record-status');
  const icdEl = document.getElementById('modal-record-icd');

  const bpEl = document.getElementById('modal-bp-val');
  const hrEl = document.getElementById('modal-hr-val');
  const tempEl = document.getElementById('modal-temp-val');
  const weightEl = document.getElementById('modal-weight-val');

  const symptomsEl = document.getElementById('modal-symptoms-val');
  const labsEl = document.getElementById('modal-labs-val');
  const notesEl = document.getElementById('modal-notes-val');
  const followupEl = document.getElementById('modal-followup-val');

  if (dateEl) dateEl.innerText = rec.date;
  if (titleEl) titleEl.innerText = rec.title;
  if (doctorEl) doctorEl.innerText = rec.doctor;
  if (icdEl) icdEl.innerText = rec.icd;

  if (statusEl) {
    statusEl.classList.add('hidden');
  }

  if (bpEl) bpEl.innerText = rec.vitals.bp;
  if (hrEl) hrEl.innerText = rec.vitals.hr;
  if (tempEl) tempEl.innerText = rec.vitals.temp;
  if (weightEl) weightEl.innerText = rec.vitals.weight;

  if (symptomsEl) symptomsEl.innerText = rec.symptoms;
  if (labsEl) labsEl.innerText = rec.labs;
  if (notesEl) notesEl.innerText = rec.doctorNotes;
  if (followupEl) followupEl.innerText = rec.followUp;

  modal.classList.remove('hidden');
}

function closeMedicalRecordDetail() {
  const modal = document.getElementById('medical-record-modal');
  if (modal) modal.classList.add('hidden');
}
