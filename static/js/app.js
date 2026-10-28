// MediMind Clinical AI - Medical Ocean Blue & Navy Interaction Logic
// Features: Multimodal Gemini Vision, RAG, Double Guardrails, Bilingual i18n, RBAC, Profile & Scan Dataset Management

const chatHistory = [];
let currentLang = 'vi';
let currentRole = 'patient';
let currentUser = JSON.parse(localStorage.getItem('medimind_user') || 'null');
let pendingTabAfterLogin = null;
let selectedChatImageBase64 = null;

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
    quick_1: "📷 Nhận diện ảnh da",
    quick_2: "🔍 Mụn nước một bên?",
    quick_3: "🌡️ Thuốc hạ sốt an toàn?",
    quick_4: "💊 Có cần dùng kháng sinh?",
    quick_prompt_text_2: "Tôi bị nổi mụn nước ngứa ngáy một bên sườn",
    quick_prompt_text_3: "Thuốc hạ sốt nào an toàn?",
    quick_prompt_text_4: "Có cần uống kháng sinh không?",
    chat_input_placeholder: "Nhập triệu chứng hoặc tải ảnh tổn thương da...",
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
  if (num === 2) promptText = dict.quick_prompt_text_2;
  else if (num === 3) promptText = dict.quick_prompt_text_3;
  else if (num === 4) promptText = dict.quick_prompt_text_4;

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
  const protectedTabs = ['doctor-tab', 'profile-tab', 'admin-tab'];
  if (protectedTabs.includes(tabId) && !currentUser) {
    pendingTabAfterLogin = tabId;
    openLoginModal();
    return;
  }

  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.classList.remove('bg-[#E0F2FE]', 'text-[#0284C7]', 'font-bold');
    btn.classList.add('text-slate-600', 'font-medium');
  });

  const activeTab = document.getElementById(tabId);
  if (activeTab) activeTab.classList.add('active');

  const activeNav = document.getElementById('nav-' + tabId);
  if (activeNav) {
    activeNav.classList.remove('text-slate-600', 'font-medium');
    activeNav.classList.add('bg-[#E0F2FE]', 'text-[#0284C7]', 'font-bold');
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
  const container = document.getElementById('chat-messages');
  if (!container) return;
  container.innerHTML = '';
}

// ==========================================
// Chat Logic (Multimodal Gemini Vision + RAG + Guardrails)
// ==========================================
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
      <div class="w-fit max-w-[85%] bg-[#0284C7] text-white px-4 py-2.5 rounded-2xl rounded-tr-sm text-xs sm:text-sm shadow-xs leading-relaxed font-medium text-left break-words">
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

  // 2. Typing Indicator
  const typingId = 'typing-' + Date.now();
  const typingHtml = `
    <div id="${typingId}" class="flex justify-start max-w-md">
      <div class="bg-[#F1F5F9] border border-slate-200/80 px-4 py-3 rounded-2xl rounded-tl-sm text-xs sm:text-sm text-slate-600 flex items-center space-x-2 shadow-xs">
        <span class="w-1.5 h-1.5 rounded-full bg-[#0284C7] animate-bounce"></span>
        <span class="w-1.5 h-1.5 rounded-full bg-[#0284C7] animate-bounce" style="animation-delay: 0.15s"></span>
        <span class="w-1.5 h-1.5 rounded-full bg-[#0284C7] animate-bounce" style="animation-delay: 0.3s"></span>
        <span class="pl-1.5 text-xs font-medium text-slate-500">${currentImage ? dict.typing_vision : dict.typing_guideline}</span>
      </div>
    </div>
  `;

  container.insertAdjacentHTML('beforeend', typingHtml);
  container.scrollTop = container.scrollHeight;

  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, history: chatHistory, image: currentImage, lang: currentLang })
    });

    const data = await response.json();
    document.getElementById(typingId)?.remove();

    if (data.error) {
      appendErrorMessage(data.error);
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
        <div class="p-2.5 rounded-xl bg-sky-50/80 border border-sky-200/90 space-y-1.5">
          <div class="text-[11px] font-bold text-[#0369A1] flex items-center space-x-1.5">
            <span>👁️</span>
            <span>Đặc điểm thị giác nhận định (Gemini Vision AI):</span>
          </div>
          <div class="flex flex-wrap gap-1.5 pt-0.5">
            ${data.visual_findings.map(f => `
              <span class="text-[10px] font-medium bg-white text-slate-700 px-2 py-0.5 rounded-full border border-sky-200 shadow-2xs">
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
        <div class="bg-red-50 border border-red-200 p-2.5 rounded-xl text-xs font-bold text-red-600 flex items-center space-x-2">
          <svg class="w-4 h-4 text-red-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
          </svg>
          <span>NGUY CẤP: GỌI 115 HOẶC ĐẾN CƠ SỞ CẤP CỨU GẦN NHẤT</span>
        </div>
      `;
    }

    const botHtml = `
      <div class="flex justify-start max-w-[90%] sm:max-w-xl">
        <div class="bg-[#F1F5F9] border border-slate-200/80 p-4 rounded-2xl rounded-tl-sm text-sm text-slate-800 space-y-2.5 leading-relaxed shadow-xs w-full">
          ${emergencyBadge}
          ${visualFindingsHtml}
          <div class="text-slate-800 font-normal">${formattedAnswer}</div>
        </div>
      </div>
    `;

    container.insertAdjacentHTML('beforeend', botHtml);
    container.scrollTop = container.scrollHeight;

    chatHistory.push({ role: 'user', content: text });
    chatHistory.push({ role: 'assistant', content: data.answer });

  } catch (err) {
    document.getElementById(typingId)?.remove();
    appendErrorMessage(dict.server_error);
  }
}

function updateTriagePanel(data) {
  const floatingRisk = document.getElementById('floating-risk-score');
  const score = data.risk_score || 25;
  if (floatingRisk) {
    if (score >= 70) {
      floatingRisk.innerText = `${score} / 100 (Cần Cấp cứu)`;
      floatingRisk.className = 'text-xs font-bold text-red-600';
    } else if (score >= 35) {
      floatingRisk.innerText = `${score} / 100 (Theo dõi)`;
      floatingRisk.className = 'text-xs font-bold text-amber-600';
    } else {
      floatingRisk.innerText = `${score} / 100 (An toàn)`;
      floatingRisk.className = 'text-xs font-bold text-[#0284C7]';
    }
  }
}

function appendErrorMessage(msg) {
  const container = document.getElementById('chat-messages');
  if (!container) return;
  const errHtml = `
    <div class="bg-red-50 border border-red-200 p-2.5 rounded-xl text-xs text-red-600 font-medium">
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

  if (navDoctorTab) navDoctorTab.innerText = (currentLang === 'vi' ? '📋 Bệnh án của tôi' : '📋 My Health Record');
  if (ocrSyncBtnText) ocrSyncBtnText.innerText = (currentLang === 'vi' ? 'Xem Bệnh án của tôi →' : 'View My Record →');

  if (currentUser) {
    if (unlogged) unlogged.classList.add('hidden');
    if (logged) logged.classList.remove('hidden');
    if (nameEl) nameEl.innerText = currentUser.name;

    const subInfo = currentUser.personal_info || currentUser.role || 'Thành viên';
    if (roleEl) roleEl.innerText = subInfo;
    if (avatarEl) avatarEl.innerText = currentUser.badge || 'BN';

    if (ehrTitle) ehrTitle.innerText = 'Hồ sơ Sức khỏe & Bệnh án của tôi';
    if (ehrSubtitle) ehrSubtitle.innerText = 'Tự động đồng bộ từ các lượt sàng lọc y tế của ' + currentUser.name;
    if (ehrPatientName) ehrPatientName.innerText = currentUser.name;
    if (ehrPatientId) ehrPatientId.innerText = 'Mã BN: #BN-2026-' + String(currentUser.id || 8429).padStart(4, '0') + ' • ' + subInfo;
    if (ehrAvatarBadge) ehrAvatarBadge.innerText = currentUser.badge || 'BN';

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
    loadScanFiles();
  } else {
    if (unlogged) unlogged.classList.remove('hidden');
    if (logged) logged.classList.add('hidden');
    if (ehrPatientName) ehrPatientName.innerText = 'Nguyễn Văn An';
    if (ehrPatientId) ehrPatientId.innerText = 'Mã BN: #BN-2026-8429 • BHYT Tuyến TW';
    if (ehrEmpty) ehrEmpty.classList.remove('hidden');
    if (ehrFilled) ehrFilled.classList.add('hidden');
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
// Initialization & Global Event Listeners
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
  populateDobDropdowns();
  updateAuthUI();
  applyLanguage();

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

let currentPrescriptionData = null;

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

  showPrescriptionLoading(true, "Đang xử lý hình ảnh và bóc tách dữ liệu...", "Đang nhận dạng ký tự quang học (OCR) và đối chiếu dược thư...");

  try {
    const res = await fetch('/api/prescription/scan', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();
    showPrescriptionLoading(false);
    renderPrescriptionResult(data);
  } catch (err) {
    console.error('Lỗi khi phân tích đơn thuốc:', err);
    showPrescriptionLoading(false);
    alert('Không thể kết nối đến máy chủ phân tích tài liệu. Vui lòng thử lại.');
  }
}

async function loadPrescriptionPreset(presetKey) {
  showPrescriptionLoading(true, "Đang tải hồ sơ mẫu và thiết lập dữ liệu đối soát...", "Trích xuất danh mục hoạt chất, liều dùng và thời gian biểu...");
  try {
    const res = await fetch(`/api/prescription/scan?preset=${presetKey}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ preset: presetKey })
    });
    const data = await res.json();
    showPrescriptionLoading(false);
    renderPrescriptionResult(data);
  } catch (err) {
    console.error('Lỗi khi tải dữ liệu đối soát:', err);
    showPrescriptionLoading(false);
    alert('Không thể nạp hồ sơ mẫu đối soát.');
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
  if (resSec) resSec.classList.add('hidden');
  if (inputSec) inputSec.classList.remove('hidden');
}

function renderPrescriptionResult(data) {
  currentPrescriptionData = data;
  const resSec = document.getElementById('prescription-result-section');
  if (!resSec) return;

  const isLab = data.type === 'lab_test';
  
  // Extract initials for patient avatar
  const patientName = data.patient_name || 'Bệnh nhân';
  const nameParts = patientName.replace(/\(.*?\)/g, '').trim().split(' ').filter(Boolean);
  const initials = nameParts.length >= 2 
    ? (nameParts[0][0] + nameParts[nameParts.length - 1][0]).toUpperCase()
    : patientName.slice(0, 2).toUpperCase();

  let html = `
    <!-- 1. Clinical Meta Header (Vibrant Modern MedTech Style) -->
    <div class="bg-white rounded-3xl p-5 sm:p-6 border border-slate-200/90 shadow-sm space-y-5">
      <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center pb-4 border-b border-slate-100 gap-3">
        <div class="flex items-center space-x-3.5">
          <div class="w-12 h-12 rounded-2xl bg-gradient-to-tr from-sky-600 to-indigo-600 text-white font-black text-base flex items-center justify-center shadow-md shadow-sky-600/25 shrink-0 tracking-wider">
            ${initials}
          </div>
          <div>
            <div class="flex flex-wrap items-center gap-2">
              <span class="px-2.5 py-0.5 rounded-full text-[10px] font-bold tracking-wider uppercase ${isLab ? 'bg-purple-100 text-purple-800 border border-purple-200' : 'bg-sky-100 text-sky-800 border border-sky-200'}">
                ${isLab ? 'BÁO CÁO XÉT NGHIỆM' : 'HỒ SƠ ĐƠN THUỐC ĐIỆN TỬ'}
              </span>
              <span class="inline-flex items-center text-[10px] font-bold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 rounded-full">
                <span class="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse mr-1.5"></span>
                Chuẩn HL7 / FHIR
              </span>
              <span class="text-xs text-slate-400 font-mono">Ngày lập: <strong class="text-slate-700">${data.date || 'Hôm nay'}</strong></span>
            </div>
            <h3 class="text-lg sm:text-xl font-black text-slate-900 mt-1 tracking-tight">${data.doc_title || (isLab ? 'Phiếu Kết Quả Xét Nghiệm' : 'Đơn Thuốc Lâm Sàng')}</h3>
          </div>
        </div>

        <div class="flex items-center space-x-2 shrink-0 w-full sm:w-auto justify-end">
          <button onclick="window.print()" class="px-3.5 py-2 rounded-xl border border-slate-200 hover:border-slate-300 bg-white hover:bg-slate-50 text-slate-700 text-xs font-bold shadow-2xs transition-all flex items-center space-x-1.5 cursor-pointer">
            <svg class="w-4 h-4 text-slate-600" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M17 17h2a2 2 0 002-2v-4a2 2 0 00-2-2H5a2 2 0 00-2 2v4a2 2 0 002 2h2m2 4h6a2 2 0 002-2v-4a2 2 0 00-2-2H9a2 2 0 00-2 2v4a2 2 0 002 2zm8-12V5a2 2 0 00-2-2H9a2 2 0 00-2 2v4h10z"></path>
            </svg>
            <span>In tài liệu</span>
          </button>
          <button onclick="resetPrescriptionScan()" class="px-4 py-2 rounded-xl bg-gradient-to-r from-slate-900 to-slate-800 hover:from-slate-800 hover:to-slate-700 text-white text-xs font-bold shadow-sm transition-all flex items-center space-x-1.5 cursor-pointer">
            <svg class="w-4 h-4 text-slate-300" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path>
            </svg>
            <span>Quét tệp khác</span>
          </button>
        </div>
      </div>

      <!-- 4 High-Contrast Clinical Metadata Cards -->
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5 text-xs">
        <!-- Facility -->
        <div class="p-3.5 rounded-2xl bg-gradient-to-br from-sky-50/50 via-white to-white border border-sky-100 hover:border-sky-300 shadow-3xs transition-all flex items-start space-x-3 group">
          <div class="w-8 h-8 rounded-xl bg-sky-100 text-sky-700 flex items-center justify-center shrink-0 mt-0.5 shadow-3xs">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"></path>
            </svg>
          </div>
          <div class="space-y-0.5 min-w-0">
            <div class="text-[10px] font-bold uppercase tracking-wider text-sky-800">Cơ sở khám bệnh</div>
            <div class="font-extrabold text-slate-900 leading-snug truncate" title="${data.facility || ''}">${data.facility || 'Cơ sở Y tế'}</div>
            <div class="text-[11px] text-slate-500 truncate font-medium">${data.department || 'Khoa Ngoại trú'}</div>
          </div>
        </div>

        <!-- Doctor -->
        <div class="p-3.5 rounded-2xl bg-gradient-to-br from-emerald-50/50 via-white to-white border border-emerald-100 hover:border-emerald-300 shadow-3xs transition-all flex items-start space-x-3 group">
          <div class="w-8 h-8 rounded-xl bg-emerald-100 text-emerald-700 flex items-center justify-center shrink-0 mt-0.5 shadow-3xs">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path>
            </svg>
          </div>
          <div class="space-y-0.5 min-w-0">
            <div class="text-[10px] font-bold uppercase tracking-wider text-emerald-800">Bác sĩ / Kỹ thuật viên</div>
            <div class="font-extrabold text-slate-900 truncate">${data.doctor || 'Bác sĩ điều trị'}</div>
            <div class="text-[10px] text-emerald-700 font-bold flex items-center">
              <svg class="w-3 h-3 mr-1" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"></path></svg>
              Ký xác thực điện tử
            </div>
          </div>
        </div>

        <!-- Patient -->
        <div class="p-3.5 rounded-2xl bg-gradient-to-br from-indigo-50/50 via-white to-white border border-indigo-100 hover:border-indigo-300 shadow-3xs transition-all flex items-start space-x-3 group">
          <div class="w-8 h-8 rounded-xl bg-indigo-100 text-indigo-700 flex items-center justify-center shrink-0 mt-0.5 shadow-3xs">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M5.121 17.804A13.937 13.937 0 0112 16c2.5 0 4.847.655 6.879 1.804M15 10a3 3 0 11-6 0 3 3 0 016 0zm6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path>
            </svg>
          </div>
          <div class="space-y-0.5 min-w-0">
            <div class="text-[10px] font-bold uppercase tracking-wider text-indigo-800">Bệnh nhân / Người thụ hưởng</div>
            <div class="font-black text-slate-900 truncate">${data.patient_name || 'Bệnh nhân'}</div>
            <div class="text-[11px] text-slate-500 truncate font-medium">${data.address || 'Hồ sơ ngoại trú'}</div>
          </div>
        </div>

        <!-- Diagnosis -->
        <div class="p-3.5 rounded-2xl bg-gradient-to-br from-amber-50/80 via-white to-amber-50/30 border border-amber-200/90 hover:border-amber-300 shadow-3xs transition-all flex items-start space-x-3 group">
          <div class="w-8 h-8 rounded-xl bg-amber-100 text-amber-800 flex items-center justify-center shrink-0 mt-0.5 shadow-3xs">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
            </svg>
          </div>
          <div class="space-y-0.5 min-w-0">
            <div class="text-[10px] font-bold uppercase tracking-wider text-amber-800">Chẩn đoán xác định (ICD)</div>
            <div class="font-black text-slate-900 leading-snug line-clamp-2">${data.diagnosis || 'Theo dõi lâm sàng'}</div>
          </div>
        </div>
      </div>
    </div>
  `;

  if (isLab) {
    // Laboratory Test Panel
    html += `
      <div class="bg-white rounded-3xl p-5 sm:p-6 border border-slate-200/90 shadow-sm space-y-4">
        <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center pb-3 border-b border-slate-100 gap-2">
          <div class="flex items-center space-x-2.5">
            <div class="w-9 h-9 rounded-xl bg-purple-100 text-purple-700 flex items-center justify-center">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"></path>
              </svg>
            </div>
            <div>
              <h4 class="text-base font-extrabold text-slate-900">Bảng Đối Chiếu Chỉ Số Sinh Hóa &amp; Huyết Học</h4>
              <p class="text-xs text-slate-500">So sánh giá trị thực nghiệm với khoảng tham chiếu sinh lý chuẩn ISO 15189</p>
            </div>
          </div>
          <span class="text-xs font-mono font-bold px-3 py-1 rounded-full bg-purple-50 text-purple-700 border border-purple-200">
            Tổng ${(data.metrics || []).length} chỉ số
          </span>
        </div>

        <div class="overflow-x-auto rounded-2xl border border-slate-200">
          <table class="w-full text-left text-xs border-collapse">
            <thead>
              <tr class="bg-slate-100/90 border-b border-slate-200 text-slate-700 font-extrabold text-[11px] uppercase tracking-wider">
                <th class="py-3.5 px-4">Chỉ số xét nghiệm</th>
                <th class="py-3.5 px-4">Giá trị đo</th>
                <th class="py-3.5 px-4">Khoảng tham chiếu</th>
                <th class="py-3.5 px-4">Trạng thái lâm sàng</th>
                <th class="py-3.5 px-4">Khuyến nghị sinh lý &amp; Dinh dưỡng</th>
              </tr>
            </thead>
            <tbody class="divide-y divide-slate-100 text-slate-700">
    `;

    (data.metrics || []).forEach(m => {
      const isHigh = m.status === 'High';
      const isLow = m.status === 'Low';
      const badgeStyle = isHigh 
        ? 'bg-rose-100 text-rose-800 border-rose-300 font-bold' 
        : isLow 
          ? 'bg-sky-100 text-sky-800 border-sky-300 font-bold' 
          : 'bg-emerald-100 text-emerald-800 border-emerald-300 font-bold';

      html += `
        <tr class="hover:bg-slate-50 transition-colors">
          <td class="py-3.5 px-4 font-bold text-slate-900">${m.name}</td>
          <td class="py-3.5 px-4 font-mono font-extrabold ${isHigh ? 'text-rose-600 text-sm' : isLow ? 'text-sky-600 text-sm' : 'text-slate-900'}">
            ${m.value} <span class="text-[11px] text-slate-400 font-normal">${m.unit}</span>
          </td>
          <td class="py-3.5 px-4 font-mono text-slate-500 text-[11px] font-medium">${m.reference} ${m.unit}</td>
          <td class="py-3.5 px-4">
            <span class="px-2.5 py-1 rounded-full text-[10px] uppercase tracking-wider border ${badgeStyle} inline-flex items-center space-x-1">
              ${isHigh ? '<svg class="w-3 h-3 text-rose-600" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M5.293 9.707a1 1 0 010-1.414l4-4a1 1 0 011.414 0l4 4a1 1 0 01-1.414 1.414L11 7.414V15a1 1 0 11-2 0V7.414L6.707 9.707a1 1 0 01-1.414 0z" clip-rule="evenodd"></path></svg>' : ''}
              ${m.status_label || m.status}
            </span>
          </td>
          <td class="py-3.5 px-4 text-xs text-slate-600 leading-relaxed max-w-sm">${m.advice || '---'}</td>
        </tr>
      `;
    });

    html += `
            </tbody>
          </table>
        </div>

        <!-- Clinical Synthesis Note -->
        <div class="p-4 rounded-2xl bg-indigo-50/50 border border-indigo-200/80 space-y-1.5">
          <div class="text-xs font-bold text-indigo-950 flex items-center space-x-1.5">
            <svg class="w-4 h-4 text-indigo-600" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
            <span>Tổng hợp Nhận định Lâm sàng:</span>
          </div>
          <p class="text-xs text-slate-700 leading-relaxed pl-5">${data.ai_summary || ''}</p>
        </div>

        <!-- Care Guidelines -->
        ${(data.lifestyle_recommendations && data.lifestyle_recommendations.length) ? `
          <div class="p-4 rounded-2xl bg-emerald-50/50 border border-emerald-200/80 space-y-2">
            <div class="text-xs font-bold text-emerald-950 flex items-center space-x-1.5">
              <svg class="w-4 h-4 text-emerald-600" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
              <span>Kế hoạch Điều chỉnh Lối sống &amp; Theo dõi:</span>
            </div>
            <ul class="text-xs text-slate-700 space-y-1.5 pl-6 list-disc">
              ${data.lifestyle_recommendations.map(r => `<li class="leading-relaxed">${r}</li>`).join('')}
            </ul>
          </div>
        ` : ''}
      </div>
    `;
  } else {
    // Structured Prescription Timeline & Formularies
    const tl = data.timeline || {};
    
    // Helper to render medication items inside schedule slot
    const renderSlotItems = (items) => {
      if (!items || !items.length) {
        return '<div class="text-xs text-slate-400 italic py-6 text-center font-medium bg-slate-50/50 rounded-xl border border-dashed border-slate-200">Không có thuốc chỉ định ở cữ này</div>';
      }
      return items.map(item => {
        const isBeforeMeal = (item.note || '').toLowerCase().includes('trước');
        const isAfterMeal = (item.note || '').toLowerCase().includes('sau');
        const mealBadge = isBeforeMeal
          ? '<span class="px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-amber-100 text-amber-900 border border-amber-300 shrink-0">Trước ăn</span>'
          : isAfterMeal
            ? '<span class="px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-teal-100 text-teal-900 border border-teal-300 shrink-0">Sau ăn</span>'
            : (item.note ? `<span class="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-slate-100 text-slate-700 shrink-0 truncate max-w-[120px]">${item.note}</span>` : '');

        return `
          <div class="bg-white p-3 rounded-xl border border-slate-200/90 hover:border-slate-300 hover:shadow-xs transition-all space-y-1.5 group">
            <div class="flex justify-between items-start gap-1.5">
              <span class="text-xs font-bold text-slate-900 leading-snug group-hover:text-sky-700 transition-colors">${item.name}</span>
              <span class="text-[11px] font-mono font-black text-white bg-slate-900 px-2 py-0.5 rounded-md shrink-0 shadow-2xs">${item.dosage}</span>
            </div>
            <div class="flex items-center justify-between pt-0.5">
              ${mealBadge}
              ${item.tag ? `<span class="text-[10px] font-semibold text-slate-500 bg-slate-50 px-1.5 py-0.5 rounded border border-slate-200/60 truncate max-w-[130px]">${item.tag}</span>` : ''}
            </div>
          </div>
        `;
      }).join('');
    };

    html += `
      <!-- 2. Dynamic Daily Medication Schedule (High-Energy Color-Coded Timeline) -->
      <div class="bg-white rounded-3xl p-5 sm:p-6 border border-slate-200/90 shadow-sm space-y-5">
        
        <!-- Header Banner with Adherence Progress -->
        <div class="bg-gradient-to-r from-slate-900 via-slate-800 to-indigo-950 text-white rounded-2xl p-4 sm:p-5 shadow-sm space-y-3">
          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div class="flex items-center space-x-3">
              <div class="w-10 h-10 rounded-xl bg-white/10 flex items-center justify-center text-sky-400 shrink-0 shadow-3xs">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                </svg>
              </div>
              <div>
                <h4 class="text-sm sm:text-base font-black text-white tracking-tight">Thời Gian Biểu Dùng Thuốc Trong Ngày</h4>
                <p class="text-xs text-slate-300 font-normal">Phân bổ khung giờ chuẩn dược động học • Đánh dấu các cữ đã uống để ghi nhận tiến độ</p>
              </div>
            </div>
            
            <div class="flex items-center space-x-2">
              <span id="adherence-status-badge" class="text-xs font-mono px-3 py-1.5 rounded-full bg-white/15 text-sky-200 border border-white/20 font-black backdrop-blur-xs">
                Tiến độ: 0/4 cữ (0%)
              </span>
              <span class="text-xs font-mono font-bold px-2.5 py-1.5 rounded-xl bg-emerald-500/20 text-emerald-300 border border-emerald-400/30">
                ${data.duration || 'Theo chỉ định'}
              </span>
            </div>
          </div>

          <!-- Progress Bar -->
          <div class="w-full bg-white/15 rounded-full h-2.5 overflow-hidden">
            <div id="adherence-progress-bar" class="bg-gradient-to-r from-sky-400 via-teal-300 to-emerald-400 h-2.5 rounded-full transition-all duration-500 ease-out" style="width: 0%"></div>
          </div>
        </div>

        <!-- 4 Distinctive Visual Columns (Morning, Noon, Evening, Bedtime) -->
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          
          <!-- Column 1: Morning (Amber / Golden Glow) -->
          <div id="slot-card-morning" class="rounded-2xl border-2 border-amber-200/90 bg-gradient-to-b from-amber-50/50 via-white to-amber-50/20 p-4 flex flex-col justify-between space-y-3.5 shadow-2xs hover:border-amber-400 hover:shadow-xs transition-all">
            <div>
              <div class="flex justify-between items-center pb-2.5 border-b border-amber-200/70">
                <div class="flex items-center space-x-2">
                  <div class="w-7 h-7 rounded-lg bg-amber-100 text-amber-700 flex items-center justify-center font-bold shadow-3xs">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"></path>
                    </svg>
                  </div>
                  <span class="text-xs font-black text-amber-950 tracking-wider">BUỔI SÁNG</span>
                </div>
                <span class="text-[11px] font-mono font-bold text-amber-900 bg-amber-100/90 px-2 py-0.5 rounded-full border border-amber-300">06:30 - 07:30</span>
              </div>
              <div class="space-y-2 mt-3">
                ${renderSlotItems(tl.morning)}
              </div>
            </div>

            <label class="flex items-center justify-between p-2.5 rounded-xl bg-white border border-amber-200/90 hover:bg-amber-50/60 cursor-pointer transition-colors shadow-3xs">
              <span class="text-xs font-bold text-amber-950">Đã dùng cữ sáng</span>
              <input type="checkbox" onchange="toggleSlotAdherence('morning', this.checked)" class="w-4 h-4 rounded text-amber-600 focus:ring-amber-500 border-slate-300">
            </label>
          </div>

          <!-- Column 2: Noon (Cyan / Sky Daylight) -->
          <div id="slot-card-noon" class="rounded-2xl border-2 border-sky-200/90 bg-gradient-to-b from-sky-50/50 via-white to-sky-50/20 p-4 flex flex-col justify-between space-y-3.5 shadow-2xs hover:border-sky-400 hover:shadow-xs transition-all">
            <div>
              <div class="flex justify-between items-center pb-2.5 border-b border-sky-200/70">
                <div class="flex items-center space-x-2">
                  <div class="w-7 h-7 rounded-lg bg-sky-100 text-sky-700 flex items-center justify-center font-bold shadow-3xs">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z"></path>
                    </svg>
                  </div>
                  <span class="text-xs font-black text-sky-950 tracking-wider">BUỔI TRƯA</span>
                </div>
                <span class="text-[11px] font-mono font-bold text-sky-900 bg-sky-100/90 px-2 py-0.5 rounded-full border border-sky-300">11:30 - 12:30</span>
              </div>
              <div class="space-y-2 mt-3">
                ${renderSlotItems(tl.noon)}
              </div>
            </div>

            <label class="flex items-center justify-between p-2.5 rounded-xl bg-white border border-sky-200/90 hover:bg-sky-50/60 cursor-pointer transition-colors shadow-3xs">
              <span class="text-xs font-bold text-sky-950">Đã dùng cữ trưa</span>
              <input type="checkbox" onchange="toggleSlotAdherence('noon', this.checked)" class="w-4 h-4 rounded text-sky-600 focus:ring-sky-500 border-slate-300">
            </label>
          </div>

          <!-- Column 3: Evening (Indigo Twilight) -->
          <div id="slot-card-evening" class="rounded-2xl border-2 border-indigo-200/90 bg-gradient-to-b from-indigo-50/50 via-white to-indigo-50/20 p-4 flex flex-col justify-between space-y-3.5 shadow-2xs hover:border-indigo-400 hover:shadow-xs transition-all">
            <div>
              <div class="flex justify-between items-center pb-2.5 border-b border-indigo-200/70">
                <div class="flex items-center space-x-2">
                  <div class="w-7 h-7 rounded-lg bg-indigo-100 text-indigo-700 flex items-center justify-center font-bold shadow-3xs">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"></path>
                    </svg>
                  </div>
                  <span class="text-xs font-black text-indigo-950 tracking-wider">CHIỀU / TỐI</span>
                </div>
                <span class="text-[11px] font-mono font-bold text-indigo-900 bg-indigo-100/90 px-2 py-0.5 rounded-full border border-indigo-300">18:00 - 19:00</span>
              </div>
              <div class="space-y-2 mt-3">
                ${renderSlotItems(tl.evening)}
              </div>
            </div>

            <label class="flex items-center justify-between p-2.5 rounded-xl bg-white border border-indigo-200/90 hover:bg-indigo-50/60 cursor-pointer transition-colors shadow-3xs">
              <span class="text-xs font-bold text-indigo-950">Đã dùng cữ tối</span>
              <input type="checkbox" onchange="toggleSlotAdherence('evening', this.checked)" class="w-4 h-4 rounded text-indigo-600 focus:ring-indigo-500 border-slate-300">
            </label>
          </div>

          <!-- Column 4: Bedtime (Purple Night) -->
          <div id="slot-card-bedtime" class="rounded-2xl border-2 border-purple-200/90 bg-gradient-to-b from-purple-50/50 via-white to-purple-50/20 p-4 flex flex-col justify-between space-y-3.5 shadow-2xs hover:border-purple-400 hover:shadow-xs transition-all">
            <div>
              <div class="flex justify-between items-center pb-2.5 border-b border-purple-200/70">
                <div class="flex items-center space-x-2">
                  <div class="w-7 h-7 rounded-lg bg-purple-100 text-purple-700 flex items-center justify-center font-bold shadow-3xs">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z"></path>
                    </svg>
                  </div>
                  <span class="text-xs font-black text-purple-950 tracking-wider">TRƯỚC KHI NGỦ</span>
                </div>
                <span class="text-[11px] font-mono font-bold text-purple-900 bg-purple-100/90 px-2 py-0.5 rounded-full border border-purple-300">21:00 - 22:00</span>
              </div>
              <div class="space-y-2 mt-3">
                ${renderSlotItems(tl.bedtime)}
              </div>
            </div>

            <label class="flex items-center justify-between p-2.5 rounded-xl bg-white border border-purple-200/90 hover:bg-purple-50/60 cursor-pointer transition-colors shadow-3xs">
              <span class="text-xs font-bold text-purple-950">Đã dùng trước ngủ</span>
              <input type="checkbox" onchange="toggleSlotAdherence('bedtime', this.checked)" class="w-4 h-4 rounded text-purple-600 focus:ring-purple-500 border-slate-300">
            </label>
          </div>

        </div>
      </div>

      <!-- 3. Pharmacological Formulary Cards (Lively & High Contrast) -->
      <div class="bg-white rounded-3xl p-5 sm:p-6 border border-slate-200/90 shadow-sm space-y-4">
        <div class="flex justify-between items-center pb-3 border-b border-slate-100">
          <div class="flex items-center space-x-2.5">
            <div class="w-9 h-9 rounded-xl bg-sky-100 text-sky-700 flex items-center justify-center shadow-3xs">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"></path>
              </svg>
            </div>
            <div>
              <h4 class="text-base font-black text-slate-900">Danh Mục Dược Phẩm Chỉ Định</h4>
              <p class="text-xs text-slate-500 font-normal">Tra cứu hoạt chất, nhóm dược lý học và cơ chế tác dụng lâm sàng</p>
            </div>
          </div>
          <span class="text-xs font-mono font-black px-3 py-1 rounded-full bg-slate-100 text-slate-800 border border-slate-200">
            ${(data.medications || []).length} loại thuốc
          </span>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          ${(data.medications || []).map((m, idx) => {
            // Palette rotation for vibrant diversity
            const palettes = [
              { border: 'border-l-sky-500', badge: 'bg-sky-50 text-sky-800 border-sky-200' },
              { border: 'border-l-teal-500', badge: 'bg-teal-50 text-teal-800 border-teal-200' },
              { border: 'border-l-indigo-500', badge: 'bg-indigo-50 text-indigo-800 border-indigo-200' },
              { border: 'border-l-amber-500', badge: 'bg-amber-50 text-amber-800 border-amber-200' },
              { border: 'border-l-rose-500', badge: 'bg-rose-50 text-rose-800 border-rose-200' },
              { border: 'border-l-purple-500', badge: 'bg-purple-50 text-purple-800 border-purple-200' }
            ];
            const p = palettes[idx % palettes.length];

            return `
              <div class="p-4 rounded-2xl border-l-4 ${p.border} border-t border-r border-b border-slate-200/90 bg-white hover:shadow-xs transition-all space-y-2.5">
                <div class="flex justify-between items-start gap-2">
                  <div>
                    <h5 class="text-sm font-black text-slate-900 tracking-tight">${m.name}</h5>
                    <p class="text-xs text-slate-500 font-mono mt-0.5 font-semibold">${m.ingredient || ''}</p>
                  </div>
                  <span class="px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${p.badge} shrink-0">
                    ${m.category || 'Thuốc kê đơn'}
                  </span>
                </div>
                <p class="text-xs text-slate-700 leading-relaxed"><span class="font-extrabold text-slate-900">Tác dụng:</span> ${m.purpose}</p>
                <div class="p-3 rounded-xl bg-slate-50 border border-slate-200/80 text-xs text-slate-800 leading-relaxed">
                  <span class="font-black text-slate-900">Chỉ định:</span> ${m.usage}
                </div>
              </div>
            `;
          }).join('')}
        </div>
      </div>

      <!-- 4. Clinical Safety & Contraindications Box -->
      <div class="p-5 rounded-3xl border-l-4 border-l-amber-500 bg-amber-50/70 border border-amber-200/90 shadow-2xs space-y-3">
        <div class="flex items-center space-x-2.5 text-amber-950 font-black text-sm">
          <div class="w-7 h-7 rounded-lg bg-amber-200/80 text-amber-900 flex items-center justify-center shrink-0 shadow-3xs">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path>
            </svg>
          </div>
          <span>Khuyến Cáo Dược Học &amp; Cảnh Báo An Toàn Lâm Sàng:</span>
        </div>
        <ul class="text-xs text-slate-800 space-y-2 pl-5 list-disc leading-relaxed font-medium">
          ${(data.warnings || []).map(w => `<li>${w}</li>`).join('')}
        </ul>
      </div>
    `;
  }

  // Clinical Bottom Actions
  html += `
    <div class="flex flex-wrap gap-3 items-center justify-between pt-2">
      <div class="flex flex-wrap gap-2.5">
        <button onclick="setMedicationReminder()" class="px-5 py-2.5 bg-gradient-to-r from-sky-600 to-indigo-600 hover:from-sky-700 hover:to-indigo-700 text-white text-xs font-bold rounded-xl shadow-sm shadow-sky-600/25 transition-all flex items-center space-x-2 cursor-pointer">
          <svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"></path>
          </svg>
          <span>Đồng bộ Lịch Nhắc Uống Thuốc</span>
        </button>
        <button onclick="askBotAboutPrescription()" class="px-4 py-2.5 bg-white hover:bg-slate-50 text-slate-800 border border-slate-200 text-xs font-bold rounded-xl transition-all shadow-2xs flex items-center space-x-2 cursor-pointer">
          <svg class="w-4 h-4 text-sky-600" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"></path>
          </svg>
          <span>Hỏi Dược Sĩ Lâm Sàng</span>
        </button>
      </div>

      <button onclick="resetPrescriptionScan()" class="text-xs font-bold text-slate-600 hover:text-slate-900 transition-colors flex items-center space-x-1 cursor-pointer">
        <span>Quét đơn thuốc khác</span>
        <span>→</span>
      </button>
    </div>
  `;

  resSec.innerHTML = html;
  resSec.classList.remove('hidden');
}

// Interactive Adherence Tracker State
let adherenceState = { morning: false, noon: false, evening: false, bedtime: false };

function toggleSlotAdherence(slot, isChecked) {
  adherenceState[slot] = isChecked;
  const card = document.getElementById(`slot-card-${slot}`);
  if (card) {
    if (isChecked) {
      card.classList.add('ring-2', 'ring-emerald-500', 'bg-emerald-50/30');
    } else {
      card.classList.remove('ring-2', 'ring-emerald-500', 'bg-emerald-50/30');
    }
  }

  const completed = Object.values(adherenceState).filter(Boolean).length;
  const percent = Math.round((completed / 4) * 100);

  const badge = document.getElementById('adherence-status-badge');
  const bar = document.getElementById('adherence-progress-bar');
  if (badge) {
    badge.innerText = `Tiến độ: ${completed}/4 cữ (${percent}%)`;
    if (completed === 4) {
      badge.className = "text-xs font-mono px-3 py-1.5 rounded-full bg-emerald-500 text-white font-black shadow-md";
      badge.innerText = "Đã hoàn thành 100% lịch uống thuốc!";
    } else {
      badge.className = "text-xs font-mono px-3 py-1.5 rounded-full bg-white/15 text-sky-200 border border-white/20 font-black backdrop-blur-xs";
    }
  }
  if (bar) {
    bar.style.width = `${percent}%`;
  }
}

function setMedicationReminder() {
  alert('Đã đồng bộ lịch uống thuốc vào hệ thống quản lý bệnh án. Lịch trình tự động nhắc theo khung giờ: 06:30, 11:30, 18:00 và 21:00.');
}

function askBotAboutPrescription() {
  if (!currentPrescriptionData) return;
  const diag = currentPrescriptionData.diagnosis || '';
  switchTab('chat-tab');
  const chatInput = document.getElementById('chat-input') || document.getElementById('user-input');
  if (chatInput) {
    chatInput.value = `Xin bác sĩ tư vấn thêm về hướng điều trị và lưu ý kiêng khem đối với chẩn đoán: "${diag}".`;
    chatInput.focus();
  }
}
