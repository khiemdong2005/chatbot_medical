// MediMind Clinical AI - Medical Ocean Blue & Navy Interaction Logic
// Clean typography, Ocean Blue #0284C7 accent, Navy #0F2942 highlights

const chatHistory = [];

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
  chatHistory.length = 0;
  const container = document.getElementById('chat-messages');
  if (!container) return;
  container.innerHTML = `
    <!-- Message 1: Initial Bot Greeting -->
    <div class="flex justify-start">
      <div class="bg-[#F1F5F9] text-slate-700 px-4 py-3 rounded-2xl rounded-tl-sm text-xs sm:text-sm font-normal max-w-[85%] leading-relaxed shadow-2xs">
        Xin chào! Hôm nay bạn cảm thấy thế nào?
      </div>
    </div>

    <!-- Message 2: User Bubble (Medical Ocean Blue) -->
    <div class="flex justify-end">
      <div class="bg-[#0284C7] text-white px-5 py-3 rounded-2xl rounded-tr-sm text-xs sm:text-sm shadow-xs leading-relaxed font-medium max-w-[80%]">
        Tôi bị đau họng và hơi sốt.
      </div>
    </div>

    <!-- Message 3: Structured Follow-up Bot Response with Medical Advice Bullets & Citation -->
    <div class="flex justify-start">
      <div class="bg-[#F1F5F9] border border-slate-200/60 text-slate-700 p-4 sm:p-5 rounded-2xl rounded-tl-sm text-xs sm:text-sm font-normal max-w-[95%] sm:max-w-[90%] leading-relaxed shadow-xs space-y-2.5">
        <p class="font-medium text-slate-800">
          Mình hiểu rồi. Với triệu chứng đau họng và sốt nhẹ, dưới đây là các biện pháp chăm sóc ban đầu:
        </p>
        <ul class="space-y-1.5 text-slate-600 pl-1 text-xs sm:text-[13px]">
          <li class="flex items-start space-x-2">
            <span class="text-[#0284C7] font-bold mt-0.5">•</span>
            <span>Súc họng nước muối ấm (0.9%) từ 3 - 4 lần/ngày giúp kháng viêm và dịu niêm mạc.</span>
          </li>
          <li class="flex items-start space-x-2">
            <span class="text-[#0284C7] font-bold mt-0.5">•</span>
            <span>Uống nhiều nước ấm, nghỉ ngơi tại phòng thoáng khí và kiểm tra thân nhiệt định kỳ.</span>
          </li>
          <li class="flex items-start space-x-2">
            <span class="text-[#0284C7] font-bold mt-0.5">•</span>
            <span>Nếu sốt trên 38.5°C hoặc đau rát tăng mạnh, hãy dùng Paracetamol theo liều và tư vấn y tế.</span>
          </li>
        </ul>
        <div class="pt-2 border-t border-slate-200/80 flex items-center justify-between text-[11px] text-slate-500">
          <div class="flex items-center space-x-1.5 font-semibold text-slate-700">
            <svg class="w-3.5 h-3.5 text-[#0284C7]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"></path>
            </svg>
            <span>Nguồn: MedlinePlus</span>
          </div>
          <span class="text-[11px] text-slate-500 font-medium">Khuyến cáo lâm sàng</span>
        </div>
      </div>
    </div>
  `;
}

async function sendChatMessage() {
  const input = document.getElementById('user-input');
  const text = input.value.trim();
  if (!text) return;

  hideFloatingDecorations();

  const container = document.getElementById('chat-messages');

  // 1. User Message (Clean Medical Ocean Blue Bubble - Perfect Padding & Wrap)
  const userHtml = `
    <div class="flex flex-col items-end my-1">
      <div class="w-fit max-w-[80%] bg-[#0284C7] text-white px-4 py-2.5 rounded-2xl rounded-tr-sm text-xs sm:text-sm shadow-xs leading-relaxed font-medium text-left break-words">
        ${escapeHtml(text)}
      </div>
      <div class="text-right text-[10px] text-slate-400 mt-1 mr-1">Vừa xong • Bệnh nhân</div>
    </div>
  `;
  container.insertAdjacentHTML('beforeend', userHtml);
  input.value = '';
  container.scrollTop = container.scrollHeight;

  // 2. Typing Indicator (Soft Hospital Gray)
  const typingId = 'typing-' + Date.now();
  const typingHtml = `
    <div id="${typingId}" class="flex justify-start max-w-md">
      <div class="bg-[#F1F5F9] border border-slate-200/80 px-4 py-3 rounded-2xl rounded-tl-sm text-xs sm:text-sm text-slate-600 flex items-center space-x-2 shadow-xs">
        <span class="w-1.5 h-1.5 rounded-full bg-[#0284C7] animate-bounce"></span>
        <span class="w-1.5 h-1.5 rounded-full bg-[#0284C7] animate-bounce" style="animation-delay: 0.15s"></span>
        <span class="w-1.5 h-1.5 rounded-full bg-[#0284C7] animate-bounce" style="animation-delay: 0.3s"></span>
        <span class="pl-1.5 text-xs font-medium text-slate-500">Đang đối soát phác đồ y khoa...</span>
      </div>
    </div>
  `;
  container.insertAdjacentHTML('beforeend', typingHtml);
  container.scrollTop = container.scrollHeight;

  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, history: chatHistory })
    });

    const data = await response.json();
    document.getElementById(typingId)?.remove();

    if (data.error) {
      appendErrorMessage(data.error);
      return;
    }

    // Cập nhật Triage Panel & Lịch sử
    updateTriagePanel(data);

    // Format Markdown cơ bản
    let formattedAnswer = escapeHtml(data.answer)
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/\n/g, '<br>');

    // Thẻ Dược phẩm tham khảo
    let medicationsHtml = '';
    if (data.medications && data.medications.length > 0) {
      medicationsHtml = `
        <div class="pt-2.5 border-t border-slate-200/80 space-y-2">
          <div class="flex items-center justify-between">
            <span class="text-[11px] font-bold text-slate-700 uppercase tracking-wider">Dược phẩm tham khảo:</span>
            <span class="text-[10px] text-[#0284C7] font-semibold">Chuẩn Dược thư Quốc gia</span>
          </div>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
            ${data.medications.slice(0, 2).map(med => `
              <div class="bg-white border border-slate-200 hover:border-[#0284C7] p-2.5 rounded-xl space-y-1 transition-all shadow-xs">
                <div class="flex justify-between items-center">
                  <span class="text-xs font-bold text-slate-900">${escapeHtml(med.name)}</span>
                  <span class="text-[9px] font-bold px-1.5 py-0.5 rounded-full border ${med.type_badge}">
                    ${escapeHtml(med.type.split(' ')[0])}
                  </span>
                </div>
                <div class="text-[10px] text-[#0284C7] font-semibold">${escapeHtml(med.strength)} • ${escapeHtml(med.category)}</div>
                <div class="text-[10px] text-slate-600 bg-slate-50 p-1.5 rounded-lg border border-slate-100">
                  ${escapeHtml(med.instructions)}
                </div>
              </div>
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
      <div class="flex justify-start max-w-[90%] sm:max-w-lg">
        <div class="bg-[#F1F5F9] border border-slate-200/80 p-4 rounded-2xl rounded-tl-sm text-sm text-slate-800 space-y-2.5 leading-relaxed shadow-xs w-full">
          ${emergencyBadge}
          <div class="text-slate-800 font-normal">${formattedAnswer}</div>
          ${medicationsHtml}
          ${(data.medications && data.medications.length > 0) || data.is_emergency ? `
          <div class="pt-1 flex items-center space-x-2">
            <button onclick="switchTab('booking-tab')" class="text-xs font-bold text-[#0284C7] hover:text-[#0369A1] flex items-center space-x-1">
              <span>Tìm bệnh viện gần nhất</span>
              <span>→</span>
            </button>
          </div>` : ''}
        </div>
      </div>
    `;

    container.insertAdjacentHTML('beforeend', botHtml);
    container.scrollTop = container.scrollHeight;

    chatHistory.push({ role: 'user', content: text });
    chatHistory.push({ role: 'assistant', content: data.answer });

  } catch (err) {
    document.getElementById(typingId)?.remove();
    appendErrorMessage("Không thể kết nối đến máy chủ.");
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
  const errHtml = `
    <div class="bg-red-50 border border-red-200 p-2.5 rounded-xl text-xs text-red-600 font-medium">
      ${escapeHtml(msg)}
    </div>
  `;
  container.insertAdjacentHTML('beforeend', errHtml);
  container.scrollTop = container.scrollHeight;
}

function simulateUploadLab() {
  alert("Đã kết nối với Amazon S3 Medical Storage.\nTệp xét nghiệm mẫu đã được phân tích chỉ số sinh hóa thành công!");
}

function escapeHtml(string) {
  const div = document.createElement('div');
  div.innerText = string;
  return div.innerHTML;
}

// ==========================================
// Authentication State Management (Bệnh nhân & Bác sĩ)
// ==========================================
let currentRole = 'patient';
let currentUser = JSON.parse(localStorage.getItem('medimind_user') || 'null');

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

function selectLoginRole(role) {
  currentRole = role;
  const patientBtn = document.getElementById('role-btn-patient');
  const doctorBtn = document.getElementById('role-btn-doctor');
  const label = document.getElementById('login-identifier-label');
  const input = document.getElementById('login-identifier');

  if (role === 'doctor') {
    doctorBtn.className = 'py-2 text-xs font-bold rounded-xl transition-all bg-white text-[#0284C7] shadow-xs';
    patientBtn.className = 'py-2 text-xs font-medium rounded-xl transition-all text-slate-600 hover:text-slate-900';
    if (label) label.innerText = 'Mã số Bác sĩ hoặc Email bệnh viện';
    if (input) input.placeholder = 'bacsi.an@medimind.vn hoặc BS-8429';
  } else {
    patientBtn.className = 'py-2 text-xs font-bold rounded-xl transition-all bg-white text-[#0284C7] shadow-xs';
    doctorBtn.className = 'py-2 text-xs font-medium rounded-xl transition-all text-slate-600 hover:text-slate-900';
    if (label) label.innerText = 'Email hoặc Số điện thoại';
    if (input) input.placeholder = 'vidu@medimind.vn hoặc 0912...';
  }
}

function quickLogin(type) {
  if (type === 'google') {
    currentUser = {
      name: currentRole === 'doctor' ? 'BS. CKI Nguyễn Văn An' : 'Nguyễn Văn An',
      role: currentRole === 'doctor' ? 'Bác sĩ lâm sàng' : 'Bệnh nhân',
      roleType: currentRole,
      badge: currentRole === 'doctor' ? 'BS' : 'BN',
      email: currentRole === 'doctor' ? 'bacsi.an@hospital.gov.vn' : 'an.nguyen@gmail.com'
    };
  } else if (type === 'doctor') {
    currentUser = {
      name: 'BS. CKI Nguyễn Văn An',
      role: 'Bác sĩ lâm sàng',
      roleType: 'doctor',
      badge: 'BS',
      email: 'bacsi.an@medimind.vn'
    };
  } else {
    currentUser = {
      name: 'Nguyễn Văn An',
      role: 'Bệnh nhân',
      roleType: 'patient',
      badge: 'BN',
      email: 'benhnhan.an@gmail.com'
    };
  }
  localStorage.setItem('medimind_user', JSON.stringify(currentUser));
  updateAuthUI();
  closeLoginModal();
}

function handleLoginSubmit(e) {
  e.preventDefault();
  const identifier = document.getElementById('login-identifier')?.value.trim() || 'Người dùng';
  
  if (currentRole === 'doctor') {
    currentUser = {
      name: identifier.includes('@') ? identifier.split('@')[0] : 'BS. ' + identifier,
      role: 'Bác sĩ lâm sàng',
      roleType: 'doctor',
      badge: 'BS',
      email: identifier
    };
  } else {
    currentUser = {
      name: identifier,
      role: 'Bệnh nhân',
      roleType: 'patient',
      badge: 'BN',
      email: identifier
    };
  }
  localStorage.setItem('medimind_user', JSON.stringify(currentUser));
  updateAuthUI();
  closeLoginModal();
}

function handleLogout() {
  currentUser = null;
  localStorage.removeItem('medimind_user');
  updateAuthUI();
}

function updateAuthUI() {
  const unlogged = document.getElementById('auth-unlogged');
  const logged = document.getElementById('auth-logged');
  const nameEl = document.getElementById('user-display-name');
  const roleEl = document.getElementById('user-role-badge');
  const avatarEl = document.getElementById('user-avatar-badge');

  if (currentUser) {
    if (unlogged) unlogged.classList.add('hidden');
    if (logged) logged.classList.remove('hidden');
    if (nameEl) nameEl.innerText = currentUser.name;
    if (roleEl) roleEl.innerText = currentUser.role;
    if (avatarEl) avatarEl.innerText = currentUser.badge || (currentUser.roleType === 'doctor' ? 'BS' : 'BN');
  } else {
    if (unlogged) unlogged.classList.remove('hidden');
    if (logged) logged.classList.add('hidden');
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

// Bắt phím Enter trong ô nhập & Khởi tạo auth
document.addEventListener('DOMContentLoaded', () => {
  updateAuthUI();
  
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

  // Đóng modal khi bấm phím Escape hoặc click ra ngoài modal
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeLoginModal();
      closeDisclaimerModal();
    }
  });

  const modal = document.getElementById('login-modal');
  if (modal) {
    modal.addEventListener('click', (e) => {
      if (e.target === modal) closeLoginModal();
    });
  }

  const disclaimerModal = document.getElementById('disclaimer-modal');
  if (disclaimerModal) {
    disclaimerModal.addEventListener('click', (e) => {
      if (e.target === disclaimerModal) closeDisclaimerModal();
    });
  }
});
