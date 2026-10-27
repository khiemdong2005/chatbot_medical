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



let selectedChatImageBase64 = null;
let selectedChatImageName = '';

function handleChatImageSelected(input) {
  if (!input.files || input.files.length === 0) return;
  const file = input.files[0];
  selectedChatImageName = file.name;
  
  const reader = new FileReader();
  reader.onload = function(e) {
    selectedChatImageBase64 = e.target.result;
    const previewContainer = document.getElementById('chat-image-preview-container');
    const thumb = document.getElementById('chat-image-preview-thumb');
    const nameEl = document.getElementById('chat-image-preview-name');
    if (previewContainer && thumb && nameEl) {
      thumb.src = selectedChatImageBase64;
      nameEl.textContent = file.name;
      previewContainer.classList.remove('hidden');
    }
  };
  reader.readAsDataURL(file);
}

function clearChatImagePreview() {
  selectedChatImageBase64 = null;
  selectedChatImageName = '';
  const input = document.getElementById('chat-image-input');
  if (input) input.value = '';
  const previewContainer = document.getElementById('chat-image-preview-container');
  if (previewContainer) previewContainer.classList.add('hidden');
}

function openImageModal(url, title = 'Ảnh tham khảo đối chiếu y khoa', stage = '', caption = '') {
  const modal = document.getElementById('image-lightbox-modal');
  const img = document.getElementById('lightbox-img');
  const titleEl = document.getElementById('lightbox-title');
  const stageEl = document.getElementById('lightbox-stage');
  const captionEl = document.getElementById('lightbox-caption');
  
  if (!modal || !img) return;
  img.src = url;
  if (titleEl) titleEl.textContent = title;
  if (stageEl) stageEl.textContent = stage;
  if (captionEl) {
    captionEl.textContent = caption || title;
    captionEl.style.display = caption ? 'block' : 'none';
  }
  modal.classList.remove('hidden');
}

function closeImageModal() {
  const modal = document.getElementById('image-lightbox-modal');
  if (modal) modal.classList.add('hidden');
}

function resetChat() {
  showFloatingDecorations();
  clearChatImagePreview();
  chatHistory.length = 0;
  const container = document.getElementById('chat-messages');
  if (!container) return;
  container.innerHTML = '';
}

async function sendChatMessage() {
  const input = document.getElementById('user-input');
  let text = input.value.trim();
  const currentImage = selectedChatImageBase64;

  if (!text && !currentImage) return;
  if (!text && currentImage) {
    text = "Xin bác sĩ quan sát bức ảnh và phân tích giúp tôi dấu hiệu tổn thương trên da.";
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
      <div class="text-right text-[10px] text-slate-400 mt-1 mr-1">Vừa xong • Bệnh nhân</div>
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
        <span class="pl-1.5 text-xs font-medium text-slate-500">${currentImage ? 'Gemini Vision đang phân tích hình thái học...' : 'Đang đối soát phác đồ y khoa...'}</span>
      </div>
    </div>
  `;

  container.insertAdjacentHTML('beforeend', typingHtml);
  container.scrollTop = container.scrollHeight;

  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, history: chatHistory, image: currentImage })
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

    // Thư viện đối chiếu lâm sàng 3 ảnh mẫu (Clinical Atlas)
    let clinicalAtlasHtml = '';
    if (data.clinical_atlas && data.clinical_atlas.reference_images && data.clinical_atlas.reference_images.length > 0) {
      const atlas = data.clinical_atlas;
      clinicalAtlasHtml = `
        <div class="pt-3 border-t border-slate-200/80 space-y-2.5">
          <div class="flex items-center justify-between">
            <div class="flex items-center space-x-1.5">
              <span class="text-xs">🔍</span>
              <span class="text-[11px] font-extrabold text-slate-800 uppercase tracking-wide">
                Hình ảnh đối chiếu y khoa: ${escapeHtml(atlas.disease_name)}
              </span>
            </div>
            <span class="text-[10px] text-[#0284C7] font-semibold bg-sky-50 px-2 py-0.5 rounded-full border border-sky-200">
              3 ảnh mẫu tham khảo
            </span>
          </div>
          <p class="text-[11px] text-slate-600 leading-relaxed bg-white p-2.5 rounded-xl border border-slate-200">
            ${escapeHtml(atlas.description)}
          </p>
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-2">
            ${atlas.reference_images.map((img, idx) => `
              <div class="bg-white border border-slate-200 hover:border-[#0284C7] rounded-xl overflow-hidden shadow-2xs transition-all cursor-pointer group flex flex-col" onclick="openImageModal('${img.url}', '${escapeHtml(atlas.disease_name)}', '${escapeHtml(img.stage)}', '${escapeHtml(img.caption)}')">
                <div class="relative h-24 bg-slate-100 overflow-hidden">
                  <img src="${img.url}" alt="${escapeHtml(img.caption)}" class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300">
                  <span class="absolute top-1 left-1 text-[9px] font-bold px-1.5 py-0.5 rounded-md bg-slate-900/80 text-white backdrop-blur-xs">
                    Ảnh ${idx + 1}
                  </span>
                </div>
                <div class="p-2 flex-1 flex flex-col justify-between">
                  <div class="text-[10px] font-bold text-slate-800 leading-tight group-hover:text-[#0284C7] line-clamp-2">
                    ${escapeHtml(img.caption)}
                  </div>
                  <div class="text-[9px] text-[#0284C7] font-semibold mt-1">
                    ${escapeHtml(img.stage)}
                  </div>
                </div>
              </div>
            `).join('')}
          </div>
          <div class="text-[9px] text-slate-400 italic text-center pt-0.5">
            * Nhấn vào từng ảnh để phóng to đối chiếu. Hình ảnh từ Thư viện MediMind Clinical Atlas.
          </div>
        </div>
      `;
    }

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
      <div class="flex justify-start max-w-[90%] sm:max-w-xl">
        <div class="bg-[#F1F5F9] border border-slate-200/80 p-4 rounded-2xl rounded-tl-sm text-sm text-slate-800 space-y-2.5 leading-relaxed shadow-xs w-full">
          ${emergencyBadge}
          ${visualFindingsHtml}
          <div class="text-slate-800 font-normal">${formattedAnswer}</div>
          ${clinicalAtlasHtml}
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



async function quickLogin(type) {

  let identifier = 'benhnhan.an@gmail.com';

  let password = 'MatKhau123@';



  if (type === 'doctor' || (type === 'google' && currentRole === 'doctor')) {

    identifier = 'bacsi.an@medimind.vn';

  }



  try {

    const res = await fetch('/api/auth/login', {

      method: 'POST',

      headers: { 'Content-Type': 'application/json' },

      body: JSON.stringify({ identifier, password, role: currentRole })

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

      body: JSON.stringify({ identifier, password, role: currentRole })

    });



    const data = await res.json();

    if (data.success && data.user) {

      currentUser = data.user;

      localStorage.setItem('medimind_user', JSON.stringify(currentUser));

      updateAuthUI();

      closeLoginModal();

      document.getElementById('login-form')?.reset();

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

