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
let pendingTabAfterLogin = null;

function switchTab(tabId) {
  // Yêu cầu đăng nhập tài khoản cho Đọc đơn thuốc (ocr-tab) và Bệnh án của tôi (doctor-tab)
  const protectedTabs = ['ocr-tab', 'doctor-tab', 'profile-tab'];
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
  if (tabId === 'ocr-tab') {
    loadScanFiles();
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
    // Tự động đồng bộ triệu chứng và Triage mới vào Bệnh án
    const ehrComplaint = document.getElementById('ehr-chief-complaint');
    const ehrHpi = document.getElementById('ehr-hpi');
    const ehrBadge = document.getElementById('ehr-triage-badge');
    const ehrDate = document.getElementById('ehr-triage-date');
    if (ehrComplaint) ehrComplaint.innerText = text;
    if (ehrHpi) ehrHpi.innerText = 'Bệnh nhân báo triệu chứng: "' + text + '". Hệ thống Gemini AI phân tầng chuyên khoa ' + (data.specialist || 'Nội tổng quát') + ' vào lúc ' + new Date().toLocaleTimeString('vi-VN') + '.';
    if (ehrBadge) ehrBadge.innerText = 'Triage: ' + (data.risk_level || 'Theo dõi') + ' (' + (data.risk_score || 35) + '/100)';
    if (ehrDate) ehrDate.innerText = new Date().toLocaleDateString('vi-VN');
    if (currentUser) {
      currentUser.hasMedicalRecord = true;
      localStorage.setItem('medimind_user', JSON.stringify(currentUser));
      const ehrEmpty = document.getElementById('ehr-content-empty');
      const ehrFilled = document.getElementById('ehr-content-filled');
      if (ehrEmpty) ehrEmpty.classList.add('hidden');
      if (ehrFilled) ehrFilled.classList.remove('hidden');
    }
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
function triggerFileUpload() {
  // Kiểm tra đăng nhập khi bấm Chọn tệp từ máy tính
  if (!currentUser) {
    pendingTabAfterLogin = 'ocr-tab';
    openLoginModal();
    return;
  }
  const fileInput = document.getElementById('lab-file-input');
  if (fileInput) {
    fileInput.value = '';
    fileInput.click(); // Mở cửa sổ chọn tệp máy tính (Windows File Explorer dialog)
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
// Authentication State Management (Bệnh nhân & Bác sĩ)
// ==========================================
let currentRole = 'patient';
let currentUser = JSON.parse(localStorage.getItem('medimind_user') || 'null');
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
let currentAuthMode = 'login'; // 'login' hoặc 'register'
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
      if (pendingTabAfterLogin) {
        const target = pendingTabAfterLogin;
        pendingTabAfterLogin = null;
        switchTab(target);
      }
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
body: JSON.stringify({ identifier, password, role: currentRole })
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
  const ocrEmpty = document.getElementById('ocr-table-empty');
  const ocrFilled = document.getElementById('ocr-table-filled');
  const ocrCards = document.getElementById('ocr-cards-filled');

  if (navDoctorTab) navDoctorTab.innerText = '📋 Bệnh án của tôi';
  if (ocrSyncBtnText) ocrSyncBtnText.innerText = 'Xem Bệnh án của tôi →';

  if (currentUser) {
    if (unlogged) unlogged.classList.add('hidden');
    if (logged) logged.classList.remove('hidden');
    if (nameEl) nameEl.innerText = currentUser.name;

    // Đồng bộ thông tin cá nhân (Giới tính, Ngày sinh, SĐT) bên dưới phần tên
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

    // Đồng bộ vào trang Tab Cập Nhật Hồ Sơ Cá Nhân (Chuẩn Ảnh 2)
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
// Bắt phím Enter trong ô nhập & Khởi tạo auth
document.addEventListener('DOMContentLoaded', () => {
populateDobDropdowns();
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
closeProfileModal();
closeUserDropdown();
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

const profileModal = document.getElementById('profile-modal');
if (profileModal) {
profileModal.addEventListener('click', (e) => {
if (e.target === profileModal) closeProfileModal();
});
}

document.addEventListener('click', (e) => {
  const authLogged = document.getElementById('auth-logged');
  if (authLogged && !authLogged.contains(e.target)) {
    closeUserDropdown();
  }
});
});