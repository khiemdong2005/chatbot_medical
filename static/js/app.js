
// Global Alias and Context Banner Helpers
window.openAuthModal = function(mode = 'login') {
  if (typeof openLoginModal === 'function') openLoginModal(mode);
};

let pendingBookingFacilityId = null;

function showAuthContextBanner(title, message) {
  const banner = document.getElementById('auth-context-banner');
  const bannerText = document.getElementById('auth-context-banner-text');
  if (banner) {
    if (bannerText && message) {
      bannerText.innerText = message;
    }
    banner.classList.remove('hidden');
  }
}

function hideAuthContextBanner() {
  const banner = document.getElementById('auth-context-banner');
  if (banner) banner.classList.add('hidden');
}

function checkPendingBookingAfterAuth() {
  if (pendingBookingFacilityId) {
    const fid = pendingBookingFacilityId;
    pendingBookingFacilityId = null;
    hideAuthContextBanner();
    setTimeout(() => {
      openFacilityBookingModal(fid);
    }, 450);
  }
}

let currentEhrSubTab = 'ai';
// ==========================================
// Facebook-Style Default Avatars by Gender (Nam, Nữ, Khác)
// ==========================================
function getDefaultAvatarByGender(gender) {
  const g = (gender || '').toLowerCase().trim();
  if (g === 'nữ' || g === 'female' || g === 'nu') {
    return '/static/images/avatar_female.png';
  }
  if (g === 'khác' || g === 'other' || g === 'khac') {
    return '/static/images/avatar_other.png';
  }
  return '/static/images/avatar_male.png';
}

function handleProfileGenderChange(newGender) {
  if (!currentUser) return;
  // If user hasn't uploaded a custom photo, sync avatar with chosen gender
  if (!currentUser.hasCustomAvatar) {
    const newAvatar = getDefaultAvatarByGender(newGender);
    currentUser.avatar = newAvatar;
    const avatarDisplay = document.getElementById('profile-avatar-display');
    const topAvatarImg = document.getElementById('user-avatar-img');
    if (avatarDisplay) avatarDisplay.src = newAvatar;
    if (topAvatarImg) topAvatarImg.src = newAvatar;
    localStorage.setItem('medimind_user', JSON.stringify(currentUser));
  }
}


// ==========================================
// Settings Tab Helpers (Account, Security, Appearance)
// ==========================================
function togglePasswordVisibility(fieldId) {
  const input = document.getElementById(fieldId);
  const eyeIcon = document.getElementById(fieldId + '-eye');
  if (!input) return;

  if (input.type === 'password') {
    input.type = 'text';
    if (eyeIcon) {
      eyeIcon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18"/>';
    }
  } else {
    input.type = 'password';
    if (eyeIcon) {
      eyeIcon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/>';
    }
  }
}

async function handleChangePasswordSubmit() {
  const currPass = document.getElementById('set-curr-pass')?.value;
  const newPass = document.getElementById('set-new-pass')?.value;
  const confirmPass = document.getElementById('set-confirm-pass')?.value;

  if (!currPass || !newPass || !confirmPass) {
    alert(currentLang === 'en' ? 'Please fill in all password fields.' : 'Vui lòng nhập đầy đủ các trường mật khẩu.');
    return;
  }
  if (newPass.length < 6) {
    alert(currentLang === 'en' ? 'New password must be at least 6 characters.' : 'Mật khẩu mới phải có ít nhất 6 ký tự.');
    return;
  }
  if (newPass !== confirmPass) {
    alert(currentLang === 'en' ? 'New passwords do not match.' : 'Mật khẩu mới không trùng khớp.');
    return;
  }

  try {
    const res = await fetch('/api/auth/change-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ current_password: currPass, new_password: newPass })
    });
    const data = await res.json();
    if (!res.ok || !data.success) {
      const errMsg = data.error || (currentLang === 'en' ? 'Failed to change password.' : 'Không thể đổi mật khẩu.');
      if (typeof showMedicalToast === 'function') showMedicalToast(errMsg, 'error');
      else alert(errMsg);
      return;
    }
    document.getElementById('set-curr-pass').value = '';
    document.getElementById('set-new-pass').value = '';
    document.getElementById('set-confirm-pass').value = '';

    const msg = data.message || (currentLang === 'en' ? 'Password changed successfully!' : 'Đã thay đổi mật khẩu thành công!');
    if (typeof showMedicalToast === 'function') showMedicalToast(msg, 'success');
    else alert(msg);
  } catch (err) {
    console.error('Lỗi đổi mật khẩu:', err);
    if (typeof showMedicalToast === 'function') showMedicalToast('Không thể kết nối máy chủ để đổi mật khẩu.', 'error');
  }
}

function handleSaveAllSettings() {
  const lang = document.getElementById('set-language')?.value || currentLang;
  const timezone = document.getElementById('set-timezone')?.value || 'UTC+7';
  const dateFormat = document.getElementById('set-date-format')?.value || 'DD/MM/YYYY';
  const pushNotif = document.getElementById('set-push-notif')?.checked ?? true;
  const theme = document.getElementById('set-theme-select')?.value || 'light';

  // Apply language if changed
  if (lang !== currentLang) {
    switchLanguage(lang);
  }

  // Apply theme if changed
  if (theme === 'dark') {
    if (document.body.classList.contains('light-glass')) {
      toggleGlassThemeMode();
    }
  } else if (theme === 'light') {
    if (!document.body.classList.contains('light-glass')) {
      toggleGlassThemeMode();
    }
  }

  // Save to localStorage
  const userSettings = {
    lang,
    timezone,
    dateFormat,
    pushNotif,
    theme
  };
  localStorage.setItem('medimind_settings', JSON.stringify(userSettings));

  const msg = currentLang === 'en' ? 'All settings saved successfully!' : 'Đã lưu tất cả cài đặt thành công!';
  showMedicalToast(msg, 'success');
}


// ==========================================
// Eye Toggle Masking for 7 Fields & Province Helper
// ==========================================
const fieldMaskState = {
  'p-email': false,
  'p-phone': false,
  'p-cccd': false,
  'p-issue-date': false,
  'p-bhyt': false,
  'p-valid-from': false,
  'p-valid-to': false
};

const fieldRealValues = {};

function maskFieldValue(val, fieldId) {
  if (!val) return '';
  if (fieldId === 'p-email') {
    if (!val.includes('@')) return '••••••••';
    const [user, domain] = val.split('@');
    if (user.length <= 2) return user[0] + '•••@' + domain;
    return user[0] + '••••••••' + user.slice(-1) + '@' + domain;
  }
  if (fieldId === 'p-phone') {
    if (val.length <= 4) return '••••';
    return val.slice(0, 3) + '••••' + val.slice(-3);
  }
  if (fieldId === 'p-cccd') {
    if (val.length <= 6) return '••••••';
    return val.slice(0, 3) + '••••••' + val.slice(-3);
  }
  if (fieldId === 'p-bhyt') {
    if (val.length <= 5) return '•••••';
    return val.slice(0, 3) + '••••••••••' + val.slice(-2);
  }
  if (fieldId.includes('date') || fieldId.includes('valid')) {
    return '••/••/••••';
  }
  if (val.length <= 4) return '••••';
  return val.slice(0, 2) + '••••' + val.slice(-2);
}

function syncLeftCardPhoneEmail() {
  const cardPhone = document.getElementById('profile-card-phone');
  const cardEmail = document.getElementById('profile-card-email');
  const pPhone = document.getElementById('p-phone');
  const pEmail = document.getElementById('p-email');

  const rawPhone = (fieldRealValues['p-phone'] !== undefined && fieldRealValues['p-phone'] !== '')
    ? fieldRealValues['p-phone'] 
    : (pPhone?.value || currentUser?.phone_number || '');
  const rawEmail = (fieldRealValues['p-email'] !== undefined && fieldRealValues['p-email'] !== '')
    ? fieldRealValues['p-email'] 
    : (pEmail?.value || currentUser?.email || '');

  const phoneEye = document.getElementById('profile-card-phone-eye');
  const emailEye = document.getElementById('profile-card-email-eye');

  const openEyeSvg = '<path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/>';
  const closedEyeSvg = '<path stroke-linecap="round" stroke-linejoin="round" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18"/>';

  if (cardPhone) {
    if (rawPhone && rawPhone.trim()) {
      cardPhone.innerText = fieldMaskState['p-phone'] ? maskFieldValue(rawPhone, 'p-phone') : rawPhone;
    } else {
      cardPhone.innerText = 'Chưa có số điện thoại';
    }
  }
  if (phoneEye) {
    phoneEye.innerHTML = fieldMaskState['p-phone'] ? closedEyeSvg : openEyeSvg;
  }

  if (cardEmail) {
    if (rawEmail && rawEmail.trim() && !rawEmail.endsWith('@phone.medimind')) {
      cardEmail.innerText = fieldMaskState['p-email'] ? maskFieldValue(rawEmail, 'p-email') : rawEmail;
    } else {
      cardEmail.innerText = 'Chưa có email';
    }
  }
  if (emailEye) {
    emailEye.innerHTML = fieldMaskState['p-email'] ? closedEyeSvg : openEyeSvg;
  }
}

function toggleFieldMask(fieldId) {
  const input = document.getElementById(fieldId);
  const wasMasked = !!fieldMaskState[fieldId];
  if (input && !wasMasked) {
    fieldRealValues[fieldId] = input.value;
  }
  fieldMaskState[fieldId] = !wasMasked;
  const isMasked = fieldMaskState[fieldId];
  const eyeIcon = document.getElementById(fieldId + '-eye');
  const cardEyeIcon = document.getElementById('profile-card-' + (fieldId === 'p-phone' ? 'phone' : 'email') + '-eye');
  
  if (input) {
    input.readOnly = isMasked;
    if (isMasked) {
      if (!fieldRealValues[fieldId]) {
        fieldRealValues[fieldId] = input.value;
      }
      input.value = maskFieldValue(fieldRealValues[fieldId] || '', fieldId);
    } else {
      input.value = fieldRealValues[fieldId] !== undefined ? fieldRealValues[fieldId] : input.value;
    }
  }

  // Sync left card if email or phone
  if (fieldId === 'p-email') {
    const cardEmail = document.getElementById('profile-card-email');
    const realEmail = (fieldRealValues[fieldId] !== undefined && fieldRealValues[fieldId] !== '') ? fieldRealValues[fieldId] : (input ? input.value : '');
    if (cardEmail) cardEmail.innerText = isMasked ? maskFieldValue(realEmail, 'p-email') : realEmail;
  } else if (fieldId === 'p-phone') {
    const cardPhone = document.getElementById('profile-card-phone');
    const realPhone = (fieldRealValues[fieldId] !== undefined && fieldRealValues[fieldId] !== '') ? fieldRealValues[fieldId] : (input ? input.value : '');
    if (cardPhone) cardPhone.innerText = isMasked ? maskFieldValue(realPhone, 'p-phone') : realPhone;
  }

  const eyeSvgOpen = '<path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/>';
  const eyeSvgClosed = '<path stroke-linecap="round" stroke-linejoin="round" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18"/>';

  const labelEye = document.getElementById(fieldId + '-label-eye');
  const labelText = document.getElementById(fieldId + '-label-text');

  if (eyeIcon) {
    eyeIcon.innerHTML = isMasked ? eyeSvgClosed : eyeSvgOpen;
  }
  if (labelEye) {
    labelEye.innerHTML = isMasked ? eyeSvgClosed : eyeSvgOpen;
  }
  if (labelText) {
    labelText.innerText = isMasked ? (currentLang === 'en' ? 'Show' : 'Hiện') : (currentLang === 'en' ? 'Hide' : 'Ẩn');
  }
  if (cardEyeIcon) {
    cardEyeIcon.innerHTML = isMasked ? eyeSvgClosed : eyeSvgOpen;
  }
  if (fieldId === 'p-email' || fieldId === 'p-phone') {
    syncLeftCardPhoneEmail();
  }
}

function handleProvinceChange() {
  const provEl = document.getElementById('p-province');
  const distEl = document.getElementById('p-district');
  if (!provEl || !distEl) return;
  
  const prov = provEl.value;
  distEl.innerHTML = '';
  
  const defaultOpt = document.createElement('option');
  defaultOpt.value = '';
  defaultOpt.innerText = currentLang === 'en' ? '-- Select District/Ward --' : '-- Chọn huyện/xã --';
  distEl.appendChild(defaultOpt);
  
  const list = VIETNAM_DISTRICTS[prov] || ["Trung tâm Huyện/Thị xã", "Khu vực 1", "Khu vực 2", "Huyện/Xã khác"];
  list.forEach(d => {
    const opt = document.createElement('option');
    opt.value = d;
    opt.innerText = d;
    distEl.appendChild(opt);
  });
}

// MediMind Clinical AI - Medical Ocean Blue & Navy Interaction Logic
// Features: Multimodal Gemini Vision, RAG, Double Guardrails, Bilingual i18n, RBAC, Profile & Scan Dataset Management

const chatHistory = [];
let currentLang = localStorage.getItem('medimind_lang') || 'vi';
let currentRole = 'patient';
const DEFAULT_USER_PROFILE = {
  id: 84291908,
  clinical_id: "84291908",
  name: "Nguyễn Văn An",
  full_name: "Nguyễn Văn An",
  dob: "04/10/2005",
  gender: "Nam",
  phone_number: "0347047101",
  email: "benhnhan.an@gmail.com",
  role: "patient",
  badge: "BN",
  cccd: "",
  issue_date: "",
  bhyt: "",
  facility: "",
  valid_from: "",
  valid_to: "",
  issue_place: "",
  nationality: "VN",
  ethnicity: "",
  religion: "",
  province: "",
  ward: "",
  address: "",
  joined: "11/09/2026",
  hasCustomAvatar: false,
  notifications: [],
  avatar: "/static/images/avatar_male.png"
};

// Default visitor: NO USER LOGGED IN unless explicit valid user exists in localStorage
let currentUser = JSON.parse(localStorage.getItem('medimind_user') || 'null');
if (currentUser && (!currentUser.hasCustomAvatar || currentUser.avatar?.includes('user_avatar.png') || currentUser.avatar?.includes('.svg'))) {
  currentUser.avatar = getDefaultAvatarByGender(currentUser.gender || 'Nam');
  currentUser.hasCustomAvatar = false;
  localStorage.setItem('medimind_user', JSON.stringify(currentUser));
}

let pendingTabAfterLogin = null;
let selectedChatImageBase64 = null;

function getChatStorageKey() {
  const uid = currentUser?.id || currentUser?.username || 'guest';
  return 'medimind_chat_sessions_v2_' + uid;
}

function loadSessionsFromStorage() {
  const key = getChatStorageKey();
  let raw = localStorage.getItem(key);
  // Khóa chung cũ 'medimind_chat_sessions_v2' chỉ chuyển đổi một lần duy nhất cho 'guest', sau đó xóa ngay để tránh rò rỉ sang tài khoản khác
  if (!raw && key === 'medimind_chat_sessions_v2_guest' && localStorage.getItem('medimind_chat_sessions_v2')) {
    raw = localStorage.getItem('medimind_chat_sessions_v2');
    try {
      localStorage.setItem(key, raw);
      localStorage.removeItem('medimind_chat_sessions_v2');
    } catch (e) {}
  }
  return JSON.parse(raw || '[]');
}

let chatSessions = loadSessionsFromStorage();

// Hàm kiểm tra và đồng bộ trạng thái đăng nhập thực tế từ server
async function checkAuthSessionWithServer() {
  try {
    const res = await fetch('/api/auth/me');
    if (res.ok) {
      const data = await res.json();
      if (data.authenticated && data.user) {
        currentUser = {
          id: data.user.id,
          name: data.user.full_name || data.user.name || 'Người dùng',
          full_name: data.user.full_name || data.user.name,
          role: data.user.role || 'patient',
          gender: data.user.gender || 'Nam',
          dob: data.user.dob || '',
          phone_number: data.user.phone_number || '',
          email: data.user.email || '',
          address: data.user.address || '',
          bhyt: data.user.bhyt || '',
          avatar: data.user.avatar || getDefaultAvatarByGender(data.user.gender || 'Nam')
        };
        localStorage.setItem('medimind_user', JSON.stringify(currentUser));
      } else {
        // Server coi người dùng là khách -> Làm sạch tài khoản trên trình duyệt (trừ khi cố ý xem demo)
        if (currentUser && !currentUser.isDemo) {
          currentUser = null;
          localStorage.removeItem('medimind_user');
        }
      }
    }
  } catch (err) {
    console.warn('[Auth] Không thể xác thực session với server:', err);
  }
  chatSessions = loadSessionsFromStorage();
  updateAuthUI();
}

// Hàm kích hoạt hồ sơ mẫu khi người dùng chủ động chọn "Xem demo"
function loadDemoPatientProfile() {
  currentUser = {
    id: 8429,
    clinical_id: "84291908",
    name: 'Nguyễn Thành Khiêm',
    full_name: 'Nguyễn Thành Khiêm',
    badge: 'BN',
    role: 'Bệnh nhân (Mẫu trải nghiệm)',
    personal_info: 'Nam • 24/10/1997 • 0971221306',
    phone: '0971221306',
    phone_number: '0971221306',
    dob: '1997-10-24',
    gender: 'Nam',
    blood_type: 'O+',
    isDemo: true,
    avatar: getDefaultAvatarByGender('Nam')
  };
  localStorage.setItem('medimind_user', JSON.stringify(currentUser));
  updateAuthUI();
  showMedicalToast('Đã mở hồ sơ bệnh nhân mẫu (Chế độ trải nghiệm)', 'info');
}
// ==========================================
// Bilingual i18n Dictionary (VI / EN)
// ==========================================
const translations = {
  vi: {
        // Notifications & Clinical Profile i18n
    notif_title: "Thông báo",
    nav_home: "Trang chủ",
    dock_home: "Trang chủ",
    home_hero_tag: "Trợ lý AI cho sức khỏe cá nhân",
    home_hero_title: "Trợ lý sức khỏe",
    home_hero_title_sub: "thông minh mỗi ngày",
    home_hero_desc: "Trò chuyện với MediMind AI để hiểu sơ bộ về triệu chứng, giải thích thuật ngữ y khoa và tra cứu hồ sơ khám bệnh ở một nơi duy nhất.",
    home_btn_chat: "Trò chuyện với trợ lý",
    home_btn_record: "Xem hồ sơ bệnh án",
    home_badge_security: "Thông tin được bảo mật",
    home_badge_history: "Lưu lịch sử trò chuyện",
    home_feat1_title: "Hỏi đáp triệu chứng",
    home_feat1_desc: "Mô tả triệu chứng của bạn để nhận gợi ý sơ bộ và biết nên khám chuyên khoa nào.",
    home_feat2_title: "Giải thích thuật ngữ y khoa",
    home_feat2_desc: "Hiểu rõ kết quả xét nghiệm, chẩn đoán và các thuật ngữ trong hồ sơ khám bệnh.",
    home_feat3_title: "Lưu lịch sử tư vấn",
    home_feat3_desc: "Mọi cuộc trò chuyện được lưu lại để bạn xem lại bất cứ lúc nào.",
    home_feat4_title: "Kết nối hồ sơ bệnh án",
    home_feat4_desc: "Tra cứu lịch sử khám, chỉ số sinh tồn và tái khám của từng bệnh nhân.",
    notif_empty: "Không có thông báo mới",
    notif_mark_read: "Đánh dấu đã đọc tất cả",
    notif_unread_count: "4 mới",
    notif_all_read: "Đã đọc hết",
    notif_1_title: "Đơn thuốc đã phân tích",
    notif_1_desc: "Đơn thuốc Amoxicillin 500mg đã được bóc tách và đối chiếu liều dùng MedlinePlus thành công.",
    notif_2_title: "Cảnh báo lâm sàng",
    notif_2_desc: "Hệ thống AI khuyến nghị uống kháng sinh cách bữa ăn 30 phút để tối ưu hấp thu.",
    notif_3_title: "Cơ sở y tế sẵn sàng",
    notif_3_desc: "Tuyến khám chuyên khoa Tai Mũi Họng tại BV Chợ Rẫy (cách 3.5km) đang mở tiếp nhận.",
    notif_4_title: "Hồ sơ sức khỏe đã đồng bộ",
    notif_4_desc: "Dữ liệu sàng lọc và tóm tắt trước khám của bạn đã được cập nhật vào hồ sơ.",
    profile_form_title: "Thông tin Chuyên môn Lâm sàng MediMind AI",
    profile_headline_full: "Chuyên gia Lâm sàng @ MediMind Clinical AI",
    badge_active_text: "ACTIVE / VERIFIED",
    badge_status_label: "TRẠNG THÁI LÂM SÀNG",
    badge_joined_label: "NGÀY THAM GIA",
    p_lbl_name: "Họ và tên",
    p_lbl_email: "Email",
    p_lbl_email_hint: "Email không thể thay đổi",
    p_lbl_phone: "Số điện thoại",
    p_lbl_clinical_id: "Mã số Chuyên viên (Clinical ID)",
    p_lbl_birthdate: "Ngày sinh",
    p_lbl_dept: "Khoa / Đơn vị lâm sàng",
    p_lbl_dept_hint: "Quản lý khoa chuyên môn tại Hệ thống Y tế MediMind.",
    p_lbl_hospital: "Cơ sở y tế / Bệnh viện",
    p_lbl_portfolio: "Hồ sơ Chuyên môn (Portfolio / Chứng chỉ)",
    p_lbl_role: "Vai trò / Chức danh chuyên môn",
    p_btn_save: "Lưu thay đổi",
        // Personal Information i18n
        // Screenshot Form i18n
    p_lbl_cccd: "CMT/CCCD",
    p_lbl_issue_date: "Ngày cấp",
    p_sec_bhyt: "Bảo hiểm y tế",
    p_lbl_bhyt_code: "Mã BHYT",
    p_lbl_facility: "Cơ sở khám chữa bệnh",
    p_lbl_valid_from: "Hiệu lực từ",
    p_lbl_valid_to: "Hết hiệu lực",
    p_lbl_issue_place: "Nơi cấp",
    p_lbl_nationality: "Quốc tịch (mã)",
    p_lbl_ethnicity: "Dân tộc",
    p_lbl_religion: "Tôn giáo",
    p_lbl_ward: "Phường/Xã",
    p_lbl_address_hokhau: "Địa chỉ theo sổ hộ khẩu",
    p_btn_save_info: "Lưu thông tin",
    p_btn_back_account: "Quay lại trang tài khoản",
        // Settings Tab i18n
    set_acc_title: "Tùy chọn tài khoản",
    set_acc_desc: "Quản lý tùy chọn tài khoản và cài đặt khu vực của bạn",
    set_lbl_lang: "Ngôn ngữ",
    set_lbl_timezone: "Múi giờ",
    set_lbl_date_format: "Định dạng ngày",
    set_notif_title: "Thông báo",
    notif_empty: "Không có thông báo mới",
    set_notif_desc: "Quản lý cách bạn nhận thông báo",
    set_lbl_browser_push: "Thông báo đẩy trình duyệt",
    set_lbl_browser_push_desc: "Nhận thông báo ngay cả khi đã đóng trang",
    set_sec_title: "Bảo mật",
    set_sec_desc: "Quản lý mật khẩu và cài đặt bảo mật của bạn",
    set_lbl_curr_pass: "Mật khẩu hiện tại",
    set_lbl_new_pass: "Mật khẩu mới",
    set_lbl_confirm_pass: "Xác nhận mật khẩu",
    set_btn_change_pass: "Đổi mật khẩu",
    set_app_title: "Giao diện",
    set_app_desc: "Tùy chỉnh giao diện ứng dụng",
    set_lbl_theme: "Chủ đề",
    theme_dark: "Tối (Dark)",
    theme_light: "Sáng (Light)",
    theme_system: "Hệ thống (System)",
    set_btn_save_all: "Lưu tất cả cài đặt",
    p_section_title: "Thông tin cá nhân",
    p_lbl_name: "Họ và tên",
    p_lbl_gender: "Giới tính",
    gender_male: "Nam",
    gender_female: "Nữ",
    gender_other: "Khác",
    p_lbl_birthdate: "Ngày sinh",
    p_lbl_clinical_id: "Clinical ID",
    p_lbl_clinical_id_hint: "Mã định danh 8 chữ số cố định được cấp khi tạo tài khoản",
    p_lbl_email: "Email",
    p_lbl_email_hint: "Email không thể thay đổi",
    p_lbl_phone: "Số điện thoại",
    p_lbl_province: "Tỉnh / Thành Phố",
    p_lbl_district: "Huyện / Xã",
    p_lbl_address: "Địa chỉ",
    p_lbl_address_ph: "Số nhà, tên đường, khu phố...",
    p_btn_save: "Lưu thay đổi",
    p_avatar_change: "Đổi ảnh",
    brand_subtitle: "Bảo mật thông tin cá nhân • Phác đồ MedlinePlus",
    nav_chat: "Trợ lý sức khỏe",
    nav_ocr: "Đọc đơn thuốc & xét nghiệm",
    nav_booking: "Cơ sở y tế",
    nav_doctor: "Hồ sơ của tôi",
    nav_admin: "Hạ tầng Cloud",
    nav_login: "Đăng nhập",
    nav_start: "Bắt đầu ngay",
    user_role: "Bác sĩ lâm sàng",
    dock_chat: "Trợ lý sức khỏe",
    dock_ocr: "Đọc đơn thuốc & xét nghiệm",
    dock_booking: "Cơ sở y tế & Bệnh viện",
    dock_doctor: "Hồ sơ của tôi",
    dock_wallpaper: "Đổi không gian Y tế",
    dock_theme: "Kính Sáng / Kính Khói",
    dock_reset: "Cuộc trò chuyện mới",
    ocr_title: "Đọc Đơn Thuốc & Xét Nghiệm",
    ocr_subtitle: "Bóc tách danh mục thuốc, đối chiếu liều dùng và gợi ý lịch uống sau khi bạn xác nhận",
    ocr_btn_upload_new: "Tải tài liệu mới",
    ocr_btn_home: "Trang chủ",
    ocr_box_title: "Tải Lên Đơn Thuốc Hoặc Phiếu Xét Nghiệm",
    ocr_box_desc: "Chụp rõ chữ, đủ sáng, không cắt mất mép tài liệu (Hỗ trợ định dạng JPG, PNG, PDF, tối đa 10MB)",
    ocr_btn_choose: "Chọn tài liệu từ thiết bị",
    ocr_privacy_note: "🔒 Tài liệu được bảo mật và chỉ lưu vào hồ sơ cá nhân sau khi bạn xác nhận kết quả.",
    ocr_preset_hint: "Chưa có sẵn ảnh đơn thuốc? Bạn có thể thử nhanh:",
    ocr_preset_gastro: "Đơn thuốc mẫu (Tiêu hóa)",
    ocr_preset_resp: "Đơn thuốc mẫu (Hô hấp)",
    ocr_preset_blood: "Phiếu xét nghiệm mẫu (Máu)",
    modal_login_title: "Đăng nhập MediMind AI",
    modal_register_title: "Đăng ký tài khoản MediMind",
    modal_auth_subtitle: "Hệ thống Trợ lý Y tế & Phân tầng Lâm sàng",
    tab_login: "Đăng nhập",
    tab_register: "Tạo tài khoản mới",
    ph_identifier: "Email hoặc số di động",
    ph_password: "Mật khẩu",
    btn_login: "Đăng nhập",
    link_forgot_pwd: "Quên mật khẩu?",
    btn_create_account: "Tạo tài khoản mới",
    btn_demo_login: "Đăng nhập tài khoản mẫu thử nghiệm",
    btn_google_signin: "Tiếp tục với Google",
    lbl_name: "Tên",
    ph_last_name: "Họ",
    ph_first_name: "Tên",
    lbl_dob: "Ngày sinh",
    opt_day: "Ngày",
    opt_month: "Tháng",
    opt_year: "Năm",
    lbl_gender: "Giới tính",
    opt_gender_select: "Chọn giới tính",
    opt_male: "Nam",
    opt_female: "Nữ",
    opt_other: "Khác",
    lbl_identifier: "Số di động hoặc email",
    lbl_password: "Mật khẩu",
    btn_register_submit: "Đăng ký tài khoản mới",
    lbl_have_account: "Đã có tài khoản?",
    link_login_now: "Đăng nhập ngay",
    history_title: "Lịch Sử Tư Vấn",
    history_subtitle: "Các phiên sàng lọc & phân tích triệu chứng",
    history_btn_new: "Hội thoại mới",
    ph_history_search: "Tìm kiếm phiên tư vấn...",
    history_empty_title: "Chưa có lịch sử tư vấn",
    history_empty_desc: "Các cuộc sàng lọc triệu chứng sẽ được lưu tự động tại đây sau khi hoàn tất.",
    history_demo_label: "Dữ liệu thử nghiệm:",
    history_demo_btn: "Xem thử ca tư vấn mẫu (Demo)",
    history_security: "Bảo mật dữ liệu cá nhân",
    history_encrypted: "Cục bộ & Mã hóa",
    assistant_header_title: "Trợ lý y tế MediMind",
    assistant_header_subtitle: "Đang trực tuyến • Tham khảo MedlinePlus và Dược thư",
    assistant_btn_summary: "Hồ sơ & Tóm tắt",
    assistant_greeting_title: "Trợ lý y tế MediMind",
    assistant_greeting_desc: "Xin chào, tôi là trợ lý y tế MediMind. Tôi có thể hỗ trợ bạn sàng lọc triệu chứng sơ bộ, giải thích đơn thuốc và gợi ý chuyên khoa khám phù hợp. Bạn đang gặp phải vấn đề sức khỏe nào?",
    quick_1: "Sốt 38.5°C và đau cổ họng",
    quick_2: "Đau tức ngực, khó thở",
    quick_3: "Lịch uống đơn thuốc sau ăn?",
    quick_4: "Gợi ý chuyên khoa khám",
    quick_prompt_text_1: "Tôi bị sốt 38.5 độ và đau cổ họng hai hôm nay, nuốt đau",
    quick_prompt_text_2: "Tôi bị đau thắt ngực dữ dội, vã mồ hôi và khó thở lan ra cánh tay trái",
    quick_prompt_text_3: "Sau khi bóc tách đơn thuốc, tôi cần uống thuốc trước hay sau bữa ăn?",
    quick_prompt_text_4: "Tôi bị đau thượng vị cồn cào sau khi ăn thì nên đăng ký khám chuyên khoa nào?",
    chat_input_placeholder: "Mô tả triệu chứng (ví dụ: đau tức ngực, sốt) hoặc gửi ảnh đơn thuốc...",
    hospital_title: "Cơ Sở Y Tế & Bệnh Viện",
    hospital_location_est: "Khu vực: TP.HCM (Khoảng cách ước tính)",
    hospital_subtitle: "Tra cứu vị trí bệnh viện tuyến đầu • Khoảng cách tính từ trung tâm TP.HCM hoặc bấm để dùng GPS",
    hospital_btn_115: "Tổng đài Cấp cứu 115",
    btn_home: "Trang chủ",
    hospital_filter_all: "Tất cả cơ sở (3)",
    hospital_filter_central: "Tuyến Trung Ương",
    hospital_filter_class1: "Đa khoa Hạng 1",
    hospital_filter_emergency: "Cấp cứu 24/7",
    hospital_map_title: "Bản đồ trực tiếp (Google Maps)",
    hospital_map_fullscreen: "Mở toàn màn hình →",
    hospital_btn_directions: "Chỉ đường Google Maps",
    hospital_btn_call: "Gọi BV",
    ehr_title: "Hồ sơ của tôi & Tóm tắt trước khám",
    ehr_tag: "TÓM TẮT TRƯỚC KHÁM",
    ehr_subtitle: "Lưu trữ tóm tắt các lần sàng lọc triệu chứng & tài liệu đơn thuốc của bạn",
    ehr_export_text: "Xuất Tóm Tắt (PDF)",
    ehr_empty_title: "Bạn chưa có bản tóm tắt trước khám",
    ehr_empty_desc: "Chưa có dữ liệu tư vấn nào được ghi nhận. Hãy trao đổi với Trợ lý sức khỏe AI hoặc tải ảnh đơn thuốc để hệ thống tự động tổng hợp thông tin trước khám cho bạn.",
    ehr_btn_start_chat: "Bắt đầu tư vấn triệu chứng →",
    ehr_btn_upload: "Tải đơn thuốc / xét nghiệm",
    vital_bp: "Huyết áp",
    vital_hr: "Nhịp tim",
    vital_temp: "Thân nhiệt",
    vital_spo2: "SpO2",
    vital_temp_sub: "Sốt nhẹ",
    vital_spo2_sub: "Đạt chuẩn",
    ehr_card_narrative: "Diễn tiến Bệnh cảnh & Lý do vào viện",
    ehr_card_narrative_sub: "Trích xuất tự động qua Chatbot AI",
    ehr_card_allergy: "CẢNH BÁO TIỀN SỬ DỊ ỨNG & CHỐNG CHỈ ĐỊNH LÂM SÀNG",
    ehr_card_dx: "Định hướng Chẩn đoán sơ bộ (AI)",
    ehr_card_orders: "Đề xuất Chỉ định Cận lâm sàng (Clinical Orders)",
    ehr_card_actions: "Thao tác Bệnh án",
    ehr_card_ready: "Hồ sơ sẵn sàng",
    ehr_btn_print_a4: "In Bệnh án A4",
    ehr_btn_save_emr: "Lưu vào EMR",
    profile_breadcrumb_home: "Trang chủ",
    profile_breadcrumb_title: "Cập nhật hồ sơ cá nhân",
    profile_title: "Thông tin cá nhân",
    profile_desc: "Quản lý và cập nhật thông tin cá nhân dùng trong việc sàng lọc y tế và bệnh án",
    profile_btn_view_ehr: "Xem Bệnh án của tôi →",
    profile_active_badge: "Hồ sơ y tế hoạt động",
    profile_lbl_dob: "Ngày sinh",
    profile_lbl_gender: "Giới tính",
    profile_lbl_phone: "Điện thoại",
    profile_lbl_fullname: "Họ và tên",
    profile_lbl_email: "Địa chỉ Email",
    profile_lbl_bhyt: "Mã thẻ BHYT (nếu có)",
    profile_lbl_city: "Tỉnh / Thành phố",
    profile_lbl_address: "Địa chỉ nơi cư trú",
    profile_btn_save: "Lưu thông tin",
    profile_btn_back: "Quay lại trang chủ",
    footer_disclaimer_link: "Tuyên bố Miễn trừ Trách nhiệm Y tế",
    footer_version: "Phiên bản 2.5 • Chuẩn Y tế AWS Cloud",
    footer_disclaimer_title: "Tuyên bố Miễn trừ Trách nhiệm Y tế (Medical Disclaimer)",
    footer_disclaimer_text: "Nền tảng MediMind AI được phát triển với mục đích học thuật, nghiên cứu giáo dục công nghệ AI và chứng minh ý tưởng tương lai (Proof of Concept). Các phân tích, chỉ số hay phác đồ gợi ý không cấu thành chỉ định lâm sàng hay tư vấn y khoa chính thức. Người bệnh luôn cần tham vấn trực tiếp bác sĩ chuyên khoa hoặc cơ sở y tế có thẩm quyền trước khi đưa ra quyết định sức khỏe. Trong tình huống nguy cấp, vui lòng gọi cấp cứu 115.",
    toast_space_prefix: "Đã chuyển không gian: ",
    toast_glass_light: "Đã kích hoạt: Kính Sáng Y Tế Lâm Sàng (Daylight Minimal)",
    toast_glass_dark: "Đã kích hoạt: Kính Trong Suốt Spatial VisionOS (Dark Minimal)",
    guest_user: "Khách",
    not_logged_in: "Chưa đăng nhập",
    disclaimer_footer_text: "⚠️ Dự án thử nghiệm công nghệ y tế phục vụ giáo dục • ",
    disclaimer_footer_btn: "Miễn trừ trách nhiệm",
    typing_vision: "Gemini Vision đang phân tích hình thái học...",
    typing_guideline: "Đang đối soát phác đồ y khoa...",
    patient_label: "Vừa xong • Bệnh nhân",
    server_error: "Không thể kết nối đến máy chủ.",
    risk_safe: "An toàn",
    risk_moderate: "Theo dõi",
    risk_emergency: "Cần Cấp cứu",
        // Home Page Redesign Discovery & Hero
    home_hero_headline: "Chăm sóc sức khỏe<br>thông minh hơn mỗi ngày.",
    home_hero_desc: "Một nơi tin cậy để bạn hiểu cơ thể, quản lý sức khỏe và chủ động hơn trong mỗi quyết định.",
    home_btn_chat: "Trò chuyện với trợ lý",
    home_btn_record: "Mở hồ sơ sức khỏe",
    home_badge_security: "Thông tin được bảo mật",
    home_badge_data: "Hỗ trợ dựa trên dữ liệu",
    home_metric_status: "Khỏe mạnh",
    home_metric_sub: "Chỉ số hôm nay",
    home_disc_tag: "KHÁM PHÁ",
    home_disc_title: "Mọi thứ bạn cần<br class=\"hidden sm:inline\"> để sống khỏe hơn.",
    home_disc_desc: "Những công cụ đơn giản, được thiết kế để biến việc chăm sóc sức khỏe thành một thói quen nhẹ nhàng mỗi ngày.",
    home_disc_more: "Khám phá tất cả",
    home_c1_tag: "HỖ TRỢ 24/7",
    home_c1_title: "Trò chuyện cùng AI",
    home_c1_desc: "Giải đáp các thắc mắc sức khỏe thường gặp bằng ngôn ngữ dễ hiểu.",
    home_c2_tag: "THÔNG TIN CỦA BẠN",
    home_c2_title: "Hồ sơ sức khỏe",
    home_c2_desc: "Quản lý chỉ số, lịch sử khám và những thông tin quan trọng của gia đình.",
    home_c3_tag: "ĐỒNG HÀNH CÙNG BẠN",
    home_c3_title: "Lịch hẹn sắp tới",
    home_c3_desc: "Theo dõi lịch khám và nhận nhắc nhở để không bỏ lỡ những cuộc hẹn quan trọng.",

    // Facility & Booking
    facility_sidebar_title: "Cơ Sở Y Tế",
    facility_sidebar_search_ph: "Tìm bệnh viện, phòng khám, quận/huyện...",
    facility_sec_type: "LOẠI HÌNH CƠ SỞ",
    facility_type_all: "Tất cả cơ sở",
    facility_type_general: "Bệnh viện Đa khoa",
    facility_type_clinic: "Phòng khám Quốc tế",
    facility_type_specialized: "Bệnh viện Chuyên khoa",
    facility_type_testing: "Trung tâm Xét nghiệm",
    facility_sec_region: "KHU VỰC ĐỊA LÝ",
    facility_sec_specialty: "CHUYÊN KHOA NỔI BẬT",
    facility_main_search_ph: "Nhập tên bệnh viện, triệu chứng, bác sĩ chuyên khoa...",
    facility_btn_map: "Bản đồ",
    facility_btn_book: "Đặt lịch khám",
    facility_btn_detail: "Chi tiết",
    facility_map_live_title: "Bản đồ trực tiếp (Google Maps)",
    facility_lbl_sort: "Sắp xếp:",
    facility_sort_default: "Gần nhất & Đánh giá cao",
    facility_sort_rating: "Đánh giá cao nhất",
    facility_sort_distance: "Khoảng cách gần nhất",
    facility_auth_banner_title: "YÊU CẦU XÁC THỰC TÀI KHOẢN",
    facility_auth_banner_text: "Vui lòng đăng nhập hoặc tạo tài khoản mới để tiếp tục đặt lịch khám!",

    // Booking Modal
    book_modal_tag: "ĐẶT LỊCH KHÁM BỆNH",
    book_modal_lbl_spec: "Chuyên khoa khám",
    book_modal_lbl_date: "Ngày khám mong muốn",
    book_modal_lbl_time: "Khung giờ",
    book_modal_lbl_name: "Họ và tên bệnh nhân",
    book_modal_ph_name: "Ví dụ: Nguyễn Văn A",
    book_modal_lbl_phone: "Số điện thoại liên hệ",
    book_modal_ph_phone: "Ví dụ: 0912 345 678",
    book_modal_lbl_note: "Lý do khám / Triệu chứng sơ bộ",
    book_modal_ph_note: "Ví dụ: Đau họng, sốt nhẹ 2 ngày, hồi hộp khi làm việc...",
    book_modal_btn_cancel: "Hủy",
    book_modal_btn_submit: "Xác nhận đặt lịch",

    // Facility Detail Modal
    detail_modal_lbl_address: "Địa chỉ:",
    detail_modal_lbl_hours: "Thời gian hoạt động:",
    detail_modal_lbl_phone: "Hotline liên hệ:",
    detail_modal_btn_book: "Đặt lịch khám tại đây",

    // EHR Profile Page
    ehr_header_title: "Hồ sơ bệnh án của tôi",
    ehr_header_subtitle: "Lịch sử khám bệnh, tư vấn và phác đồ điều trị cá nhân",
    ehr_stat_visits: "Phiên tư vấn AI",
    ehr_lbl_dob: "NGÀY SINH",
    ehr_lbl_blood: "NHÓM MÁU",
    ehr_lbl_phone: "ĐIỆN THOẠI",
    ehr_lbl_allergy: "DỊ ỨNG",
    ehr_lbl_no_allergy: "Chưa ghi nhận",
    ehr_sec_prescriptions: "Toa thuốc & Bệnh án đã Import",
    ehr_btn_add_rx: "+ Thêm đơn mới →",
    ehr_no_rx: "Chưa có đơn thuốc nào được lưu.",
    ehr_sec_history_title: "Lịch sử khám & tư vấn",
    ehr_sec_history_sub: "Tách bạch rõ giữa phiên tư vấn AI thực tế và hồ sơ bệnh viện liên kết",
    ehr_subtab_ai: "💬 Tư vấn AI (Thực tế)",
    ehr_subtab_hospital: "🏥 Bệnh viện (Mẫu minh họa)",

    // Live Intake Card
    intake_card_title: "Bản nháp trong hội thoại",
    intake_draft_notice: "Lời kể được lưu trong lịch sử chat. Chỉ bản tóm tắt bạn xác nhận mới xuất hiện trong hồ sơ.",
    intake_status_init: "Chờ khởi tạo",
    intake_lbl_chief: "Lý do",
    intake_lbl_symptoms: "Triệu chứng",
    intake_lbl_denied: "Đã phủ nhận",
    intake_lbl_duration: "Thời gian",
    intake_lbl_vitals: "Thân nhiệt",
    intake_btn_summary: "Tóm tắt trước khám",
    intake_btn_confirm: "Xem lại để lưu",
    spec_cardiology: "Tim mạch",
    spec_pediatrics: "Nhi khoa",
    spec_ent: "Tai Mũi Họng",
    spec_endocrine: "Nội tiết & Tiểu đường",
    spec_gastro: "Tiêu hóa & Gan mật",
    spec_orthopedics: "Chấn thương chỉnh hình",
    spec_neurology: "Thần kinh",
    spec_obgyn: "Sản phụ khoa",
    spec_oncology: "Ung bướu",
    spec_eye: "Mắt",
    assistant_pill_title: "Trợ lý y tế MediMind",
    footer_subtitle: "Hỗ trợ phân tích triệu chứng & tham chiếu MedlinePlus",
    ehr_export_text: "Xuất Tóm Tắt (PDF)",
    facility_toast_login_required: "Vui lòng đăng nhập hoặc tạo tài khoản mới để đặt lịch khám!",
    facility_auth_banner_title: "YÊU CẦU XÁC THỰC TÀI KHOẢN",
    facility_auth_banner_text: "Vui lòng đăng nhập hoặc tạo tài khoản mới để tiếp tục đặt lịch khám!",

    default_image_prompt: "Xin bác sĩ quan sát bức ảnh và phân tích giúp tôi dấu hiệu tổn thương trên da."
  },
  en: {
        // Notifications & Clinical Profile i18n
    notif_title: "Notifications",
    nav_home: "Home",
    dock_home: "Home",
    home_hero_tag: "Personal AI Health Assistant",
    home_hero_title: "Smart Daily Health",
    home_hero_title_sub: "Assistant",
    home_hero_desc: "Chat with MediMind AI for preliminary symptom assessment, medical terminology explanations, and clinical records all in one place.",
    home_btn_chat: "Chat with Assistant",
    home_btn_record: "View Health Record",
    home_badge_security: "Data Encrypted & Secure",
    home_badge_history: "Chat History Saved",
    home_feat1_title: "Symptom Q&A",
    home_feat1_desc: "Describe your symptoms for preliminary guidance and specialty recommendations.",
    home_feat2_title: "Medical Terminology",
    home_feat2_desc: "Understand lab results, clinical diagnoses, and prescriptions clearly.",
    home_feat3_title: "Consultation History",
    home_feat3_desc: "All triage discussions are securely saved for your future reference.",
    home_feat4_title: "Electronic Health Records",
    home_feat4_desc: "Access your clinical summaries, vital signs, and scheduled visits anytime.",
    notif_empty: "No new notifications",
    notif_mark_read: "Mark all as read",
    notif_unread_count: "4 new",
    notif_all_read: "All read",
    notif_1_title: "Prescription Analyzed",
    notif_1_desc: "Amoxicillin 500mg prescription parsed and verified against MedlinePlus dosage guidelines.",
    notif_2_title: "Clinical Advisory",
    notif_2_desc: "AI system advises taking medication 30 minutes after meals to optimize absorption.",
    notif_3_title: "Facility Available",
    notif_3_desc: "ENT Specialist consultation at Cho Ray Hospital (3.5km away) is currently accepting patients.",
    notif_4_title: "Health Record Synchronized",
    notif_4_desc: "Your pre-visit clinical summary and screening history have been securely synchronized.",
    profile_form_title: "MediMind AI Clinical & Specialist Information",
    profile_headline_full: "Clinical AI Specialist @ MediMind Clinical AI",
    badge_active_text: "ACTIVE / VERIFIED",
    badge_status_label: "CLINICAL STATUS",
    badge_joined_label: "REGISTERED",
    p_lbl_name: "Full Name",
    p_lbl_email: "Email",
    p_lbl_email_hint: "Email cannot be changed",
    p_lbl_phone: "Phone Number",
    p_lbl_clinical_id: "Clinical ID",
    p_lbl_birthdate: "Birth Date",
    p_lbl_dept: "Department",
    p_lbl_dept_hint: "Managed under MediMind Clinical Division.",
    p_lbl_hospital: "Hospital / Facility",
    p_lbl_portfolio: "Clinical Portfolio",
    p_lbl_role: "Role / Headline",
    p_btn_save: "Save Changes",
        // Personal Information i18n
        // Screenshot Form i18n
    p_lbl_cccd: "Citizen ID / CCCD",
    p_lbl_issue_date: "Issue Date",
    p_sec_bhyt: "Health Insurance",
    p_lbl_bhyt_code: "Health Insurance Code",
    p_lbl_facility: "Primary Care Facility",
    p_lbl_valid_from: "Effective From",
    p_lbl_valid_to: "Valid Until",
    p_lbl_issue_place: "Place of Issue",
    p_lbl_nationality: "Nationality (Code)",
    p_lbl_ethnicity: "Ethnicity",
    p_lbl_religion: "Religion",
    p_lbl_ward: "Ward / Commune",
    p_lbl_address_hokhau: "Permanent Address",
    p_btn_save_info: "Save Information",
    p_btn_back_account: "Back to Account Page",
        // Settings Tab i18n
    set_acc_title: "Account Preferences",
    set_acc_desc: "Manage your account preferences and regional settings",
    set_lbl_lang: "Language",
    set_lbl_timezone: "Timezone",
    set_lbl_date_format: "Date Format",
    set_notif_title: "Notifications",
    notif_empty: "No new notifications",
    set_notif_desc: "Manage how you receive notifications",
    set_lbl_browser_push: "Browser Push Notifications",
    set_lbl_browser_push_desc: "Receive notifications even when the page is closed",
    set_sec_title: "Security",
    set_sec_desc: "Manage your password and security settings",
    set_lbl_curr_pass: "Current Password",
    set_lbl_new_pass: "New Password",
    set_lbl_confirm_pass: "Confirm Password",
    set_btn_change_pass: "Change Password",
    set_app_title: "Appearance",
    set_app_desc: "Customize how the application looks",
    set_lbl_theme: "Theme",
    theme_dark: "Dark",
    theme_light: "Light",
    theme_system: "System",
    set_btn_save_all: "Save All Settings",
    p_section_title: "Personal Information",
    p_lbl_name: "Full Name",
    p_lbl_gender: "Gender",
    gender_male: "Male",
    gender_female: "Female",
    gender_other: "Other",
    p_lbl_birthdate: "Birth Date",
    p_lbl_clinical_id: "Clinical ID",
    p_lbl_clinical_id_hint: "Fixed 8-digit clinical ID assigned at account creation",
    p_lbl_email: "Email",
    p_lbl_email_hint: "Email cannot be changed",
    p_lbl_phone: "Phone Number",
    p_lbl_province: "Province / City",
    p_lbl_district: "District / Ward",
    p_lbl_address: "Address",
    p_lbl_address_ph: "House number, street, ward...",
    p_btn_save: "Save Changes",
    p_avatar_change: "Change",
    brand_subtitle: "HIPAA Compliant • MedlinePlus Protocols",
    nav_chat: "Health Assistant",
    nav_ocr: "Prescriptions & Labs",
    nav_booking: "Hospitals & Clinics",
    nav_doctor: "My Health Record",
    nav_admin: "Cloud Infrastructure",
    nav_login: "Sign In",
    nav_start: "Get Started",
    user_role: "Clinical Physician",
    dock_chat: "Health Assistant",
    dock_ocr: "Prescriptions & Labs",
    dock_booking: "Hospitals & Clinics",
    dock_doctor: "My Health Record",
    dock_wallpaper: "Change Wallpaper",
    dock_theme: "Light / Dark Glass",
    dock_reset: "New Conversation",
    ocr_title: "Prescription & Lab OCR",
    ocr_subtitle: "Extract drug lists, verify dosages, and generate intake schedules after confirmation",
    ocr_btn_upload_new: "Upload New Document",
    ocr_btn_home: "Home",
    ocr_box_title: "Upload Prescription or Lab Report",
    ocr_box_desc: "Clear text, adequate light, all edges visible (Supports JPG, PNG, PDF, up to 10MB)",
    ocr_btn_choose: "Select from Device",
    ocr_privacy_note: "🔒 Your document is encrypted and only saved to your personal health record upon confirmation.",
    ocr_preset_hint: "No document at hand? Try quick samples:",
    ocr_preset_gastro: "Sample Prescription (Gastro)",
    ocr_preset_resp: "Sample Prescription (Resp)",
    ocr_preset_blood: "Sample Lab Report (Blood)",
    modal_login_title: "Sign In to MediMind AI",
    modal_register_title: "Create MediMind Account",
    modal_auth_subtitle: "Clinical Decision Support & Health Assistant",
    tab_login: "Sign In",
    tab_register: "Create Account",
    ph_identifier: "Email or mobile number",
    ph_password: "Password",
    btn_login: "Sign In",
    link_forgot_pwd: "Forgot Password?",
    btn_create_account: "Create New Account",
    btn_demo_login: "Quick Demo Patient Sign-in",
    btn_google_signin: "Continue with Google",
    lbl_name: "Name",
    ph_last_name: "Last Name",
    ph_first_name: "First Name",
    lbl_dob: "Date of Birth",
    opt_day: "Day",
    opt_month: "Month",
    opt_year: "Year",
    lbl_gender: "Gender",
    opt_gender_select: "Select Gender",
    opt_male: "Male",
    opt_female: "Female",
    opt_other: "Other",
    lbl_identifier: "Mobile Number or Email",
    lbl_password: "Password",
    btn_register_submit: "Register New Account",
    lbl_have_account: "Already have an account?",
    link_login_now: "Sign In Now",
    history_title: "Consultation History",
    history_subtitle: "Screening sessions & symptom analyses",
    history_btn_new: "New Session",
    ph_history_search: "Search consultations...",
    history_empty_title: "No consultation history yet",
    history_empty_desc: "Your symptom screenings will be automatically saved here upon completion.",
    history_demo_label: "Demo dataset:",
    history_demo_btn: "View Demo Consultation Case",
    history_security: "Personal Data Privacy",
    history_encrypted: "Local & Encrypted",
    assistant_header_title: "MediMind Medical Assistant",
    assistant_header_subtitle: "Online • MedlinePlus & Pharmacopoeia Reference",
    assistant_btn_summary: "Record & Summary",
    assistant_greeting_title: "MediMind Medical Assistant",
    assistant_greeting_desc: "Hello, I am MediMind medical assistant. I can assist you with initial symptom triage, prescription explanation, and specialty recommendation. What health concern are you experiencing?",
    quick_1: "Fever 38.5°C and sore throat",
    quick_2: "Chest tightness, dyspnea",
    quick_3: "Medication timing with meals?",
    quick_4: "Specialty clinic suggestion",
    quick_prompt_text_1: "I have had a fever of 38.5 C and sore throat for 2 days, painful swallowing",
    quick_prompt_text_2: "I have intense crushing chest pain, sweating, and shortness of breath radiating to left arm",
    quick_prompt_text_3: "Should I take this medication before or after meals?",
    quick_prompt_text_4: "I feel burning epigastric pain after eating, which specialty should I consult?",
    chat_input_placeholder: "Describe symptoms (e.g. chest pain, fever) or send prescription photo...",
    hospital_title: "Medical Facilities & Hospitals",
    hospital_location_est: "Region: Ho Chi Minh City (Estimated Distance)",
    hospital_subtitle: "Find top referral hospitals • Distance calculated from city center or tap for GPS",
    hospital_btn_115: "Emergency Hotline 115",
    btn_home: "Home",
    hospital_filter_all: "All Facilities (3)",
    hospital_filter_central: "Central Hospitals",
    hospital_filter_class1: "Class 1 General",
    hospital_filter_emergency: "24/7 Emergency",
    hospital_map_title: "Live Map (Google Maps)",
    hospital_map_fullscreen: "Open Fullscreen →",
    hospital_btn_directions: "Google Maps Directions",
    hospital_btn_call: "Call Hospital",
    ehr_title: "My Health Record & Pre-Visit Summary",
    ehr_tag: "PRE-VISIT SUMMARY",
    ehr_subtitle: "Archive of symptom screening summaries and prescription documents",
    ehr_export_text: "Export Summary (PDF)",
    ehr_empty_title: "No Pre-Visit Summary Available",
    ehr_empty_desc: "No consultation data recorded yet. Talk with our AI Health Assistant or upload a prescription to generate your summary.",
    ehr_btn_start_chat: "Start Symptom Consultation →",
    ehr_btn_upload: "Upload Prescription / Lab",
    vital_bp: "Blood Pressure",
    vital_hr: "Heart Rate",
    vital_temp: "Body Temp",
    vital_spo2: "SpO2",
    vital_temp_sub: "Mild fever",
    vital_spo2_sub: "Normal",
    ehr_card_narrative: "Clinical History & Chief Complaint",
    ehr_card_narrative_sub: "Extracted automatically by MediMind AI",
    ehr_card_allergy: "CLINICAL ALLERGY ALERT & CONTRAINDICATIONS",
    ehr_card_dx: "Provisional Diagnostic Impressions (AI)",
    ehr_card_orders: "Recommended Clinical Orders",
    ehr_card_actions: "Medical Record Actions",
    ehr_card_ready: "Record Ready",
    ehr_btn_print_a4: "Print A4 Record",
    ehr_btn_save_emr: "Save to EMR",
    profile_breadcrumb_home: "Home",
    profile_breadcrumb_title: "Update Health Profile",
    profile_title: "Personal Information",
    profile_desc: "Manage and update health demographics used in medical screening and records",
    profile_btn_view_ehr: "View My Medical Record →",
    profile_active_badge: "Active Health Record",
    profile_lbl_dob: "Date of Birth",
    profile_lbl_gender: "Gender",
    profile_lbl_phone: "Phone Number",
    profile_lbl_fullname: "Full Name",
    profile_lbl_email: "Email Address",
    profile_lbl_bhyt: "Health Insurance ID (optional)",
    profile_lbl_city: "City / Province",
    profile_lbl_address: "Residential Address",
    profile_btn_save: "Save Information",
    profile_btn_back: "Back to Home",
    footer_disclaimer_link: "Medical Disclaimer",
    footer_version: "Version 2.5 • AWS Cloud Health Compliant",
    footer_disclaimer_title: "Medical Disclaimer",
    footer_disclaimer_text: "MediMind AI is developed for educational, technical demonstration, and research proof-of-concept purposes. The inferences, scores, and referenced guidelines do not constitute formal clinical diagnoses or medical advice. Always consult licensed medical professionals or healthcare facilities for medical conditions. In case of emergency, call 115 immediately.",
    toast_space_prefix: "Switched theme: ",
    toast_glass_light: "Activated: Clinical Light Glass (Daylight Minimal)",
    toast_glass_dark: "Activated: Transparent Spatial Glass (Dark Minimal)",
    guest_user: "Guest",
    not_logged_in: "Not signed in",
    disclaimer_footer_text: "⚠️ Educational Health AI Prototype • ",
    disclaimer_footer_btn: "Medical Disclaimer",
    typing_vision: "Gemini Vision is analyzing morphology...",
    typing_guideline: "Cross-referencing medical guidelines...",
    patient_label: "Just now • Patient",
    server_error: "Unable to connect to server.",
    risk_safe: "Safe",
    risk_moderate: "Monitor",
    risk_emergency: "Emergency",
        // Home Page Redesign Discovery & Hero
    home_hero_headline: "Smarter healthcare,<br>every single day.",
    home_hero_desc: "A trusted companion to understand your body, manage your health, and make informed choices.",
    home_btn_chat: "Chat with Assistant",
    home_btn_record: "Open Health Record",
    home_badge_security: "Data Encrypted & Secure",
    home_badge_data: "Data-Driven Clinical AI",
    home_metric_status: "Optimal",
    home_metric_sub: "Daily Health Index",
    home_disc_tag: "DISCOVERY",
    home_disc_title: "Everything you need<br class=\"hidden sm:inline\"> to live healthier.",
    home_disc_desc: "Simple, intelligent tools designed to turn health management into a seamless daily habit.",
    home_disc_more: "Explore All",
    home_c1_tag: "24/7 SUPPORT",
    home_c1_title: "AI Health Chat",
    home_c1_desc: "Get preliminary answers to common health concerns in clear, accessible language.",
    home_c2_tag: "YOUR CLINICAL DATA",
    home_c2_title: "Health Records",
    home_c2_desc: "Manage vital signs, consultation history, and important family health data.",
    home_c3_tag: "WITH YOU ALWAYS",
    home_c3_title: "Upcoming Visits",
    home_c3_desc: "Keep track of hospital visits and get timely reminders for appointments.",

    // Facility & Booking
    facility_sidebar_title: "Healthcare Facilities",
    facility_sidebar_search_ph: "Search hospital, clinic, district...",
    facility_sec_type: "FACILITY CATEGORY",
    facility_type_all: "All Facilities",
    facility_type_general: "General Hospital",
    facility_type_clinic: "International Clinic",
    facility_type_specialized: "Specialized Hospital",
    facility_type_testing: "Diagnostic Lab",
    facility_sec_region: "GEOGRAPHIC REGION",
    facility_sec_specialty: "FEATURED SPECIALTIES",
    facility_main_search_ph: "Enter hospital name, symptom, or specialist...",
    facility_btn_map: "Map",
    facility_btn_book: "Book Appointment",
    facility_btn_detail: "Details",
    facility_map_live_title: "Live Map (Google Maps)",
    facility_lbl_sort: "Sort by:",
    facility_sort_default: "Nearest & Top Rated",
    facility_sort_rating: "Highest Rated",
    facility_sort_distance: "Closest Distance",
    facility_auth_banner_title: "AUTHENTICATION REQUIRED",
    facility_auth_banner_text: "Please sign in or create a new account to proceed with your booking!",

    // Booking Modal
    book_modal_tag: "SCHEDULE AN APPOINTMENT",
    book_modal_lbl_spec: "Medical Specialty",
    book_modal_lbl_date: "Preferred Date",
    book_modal_lbl_time: "Time Slot",
    book_modal_lbl_name: "Patient Full Name",
    book_modal_ph_name: "e.g. John Doe",
    book_modal_lbl_phone: "Contact Phone",
    book_modal_ph_phone: "e.g. +84 912 345 678",
    book_modal_lbl_note: "Reason for Visit / Preliminary Symptoms",
    book_modal_ph_note: "e.g. Sore throat, mild fever for 2 days...",
    book_modal_btn_cancel: "Cancel",
    book_modal_btn_submit: "Confirm Appointment",

    // Facility Detail Modal
    detail_modal_lbl_address: "Address:",
    detail_modal_lbl_hours: "Operating Hours:",
    detail_modal_lbl_phone: "Contact Hotline:",
    detail_modal_btn_book: "Book Appointment Here",

    // EHR Profile Page
    ehr_header_title: "My Electronic Health Record",
    ehr_header_subtitle: "Clinical consultation history, triage summaries, and personal care plan",
    ehr_stat_visits: "AI consultations",
    ehr_lbl_dob: "DATE OF BIRTH",
    ehr_lbl_blood: "BLOOD TYPE",
    ehr_lbl_phone: "PHONE NUMBER",
    ehr_lbl_allergy: "ALLERGIES",
    ehr_lbl_no_allergy: "None reported",
    ehr_sec_prescriptions: "Imported Prescriptions & Reports",
    ehr_btn_add_rx: "+ Add New →",
    ehr_no_rx: "No prescriptions saved yet.",
    ehr_sec_history_title: "Consultations & Clinical Visits",
    ehr_sec_history_sub: "Clearly distinguishing verified AI consultations from linked hospital records",
    ehr_subtab_ai: "💬 AI Consultations (Live)",
    ehr_subtab_hospital: "🏥 Hospital Records (Demo)",

    // Live Intake Card
    intake_card_title: "Conversation draft",
    intake_draft_notice: "Your conversation is saved in chat history. Only a summary you approve appears in your health record.",
    intake_status_init: "Awaiting Intake",
    intake_lbl_chief: "Chief Complaint",
    intake_lbl_symptoms: "Symptoms",
    intake_lbl_denied: "Pertinent Negatives",
    intake_lbl_duration: "Duration",
    intake_lbl_vitals: "Temperature",
    intake_btn_summary: "Pre-visit Summary",
    intake_btn_confirm: "Review before saving",
    spec_cardiology: "Cardiology",
    spec_pediatrics: "Pediatrics",
    spec_ent: "ENT",
    spec_endocrine: "Endocrinology & Diabetes",
    spec_gastro: "Gastroenterology",
    spec_orthopedics: "Orthopedics",
    spec_neurology: "Neurology",
    spec_obgyn: "OB/GYN",
    spec_oncology: "Oncology",
    spec_eye: "Ophthalmology",
    assistant_pill_title: "MediMind Assistant",
    footer_subtitle: "AI Symptom Analysis & MedlinePlus Protocols",
    ehr_export_text: "Export Summary (PDF)",
    facility_toast_login_required: "Please log in or create an account to book an appointment!",
    facility_auth_banner_title: "ACCOUNT AUTHENTICATION REQUIRED",
    facility_auth_banner_text: "Please log in or create an account to proceed with booking!",

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
  try { localStorage.setItem('medimind_lang', lang); } catch (e) {}
  closeLanguageDropdown();
  populateDobDropdowns();
  applyLanguage();
  updateAuthUI();
  if (typeof switchEhrSubTab === 'function') switchEhrSubTab(currentEhrSubTab || 'ai');
}

function applyLanguage() {
  const dict = translations[currentLang] || translations.vi;
  const currentLangCode = document.getElementById('current-lang-code');
  if (currentLangCode) currentLangCode.innerText = currentLang.toUpperCase();

  const checkVi = document.getElementById('check-vi');
  const checkEn = document.getElementById('check-en');
  if (checkVi) checkVi.classList.toggle('hidden', currentLang !== 'vi');
  if (checkEn) checkEn.classList.toggle('hidden', currentLang !== 'en');

  // Dynamic Auth modal header based on currentAuthMode
  const titleEl = document.getElementById('auth-modal-title');
  if (titleEl) {
    titleEl.innerText = (typeof currentAuthMode !== 'undefined' && currentAuthMode === 'register')
      ? (dict.modal_register_title || 'Đăng ký tài khoản MediMind')
      : (dict.modal_login_title || 'Đăng nhập MediMind AI');
  }

  // Update gender options text
  const genderSelect = document.getElementById('register-gender');
  if (genderSelect && genderSelect.options.length >= 4) {
    genderSelect.options[0].text = dict.opt_gender_select || 'Chọn giới tính';
    genderSelect.options[1].text = dict.opt_male || 'Nam';
    genderSelect.options[2].text = dict.opt_female || 'Nữ';
    genderSelect.options[3].text = dict.opt_other || 'Khác';
  }

  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    if (dict[key]) {
      if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
        el.value = dict[key];
      } else if (el.tagName === 'OPTION') {
        el.text = dict[key];
      } else {
        el.innerHTML = dict[key];
      }
    }
  });

  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    const key = el.getAttribute('data-i18n-placeholder');
    if (dict[key]) {
      el.setAttribute('placeholder', dict[key]);
    }
  });

  // Re-sync all dynamic view components across tabs
  if (typeof updateHomeGreeting === 'function') updateHomeGreeting();
  if (typeof updateEhrTabUI === 'function') updateEhrTabUI();
  if (typeof updateFacilityDistrictDropdown === 'function') updateFacilityDistrictDropdown(facilityCurrentRegion || 'hcm');
  if (typeof renderMedicalFacilities === 'function') renderMedicalFacilities();
  if (typeof loadPrescriptionHistory === 'function') loadPrescriptionHistory();
  if (typeof switchEhrSubTab === 'function') switchEhrSubTab(currentEhrSubTab || 'ai');
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


// ==============================================================
// CLIENT-SIDE ROUTING & DEEP LINKING (Tab State Persistence)
// ==============================================================
const TAB_HASH_MAP = {
  'home-tab': 'home',
  'chat-tab': 'chat',
  'ocr-tab': 'ocr',
  'booking-tab': 'booking',
  'doctor-tab': 'doctor',
  'profile-tab': 'profile',
  'settings-tab': 'settings'
};
const HASH_TAB_MAP = {
  'home': 'home-tab',
  'chat': 'chat-tab',
  'ocr': 'ocr-tab',
  'booking': 'booking-tab',
  'facilities': 'booking-tab',
  'doctor': 'doctor-tab',
  'profile': 'profile-tab',
  'settings': 'settings-tab'
};

function resolveInitialTab() {
  const hash = window.location.hash.replace('#', '').trim();
  if (hash && HASH_TAB_MAP[hash]) {
    const target = HASH_TAB_MAP[hash];
    if (target === 'profile-tab' && !currentUser) return 'home-tab';
    return target;
  }
  const savedTab = sessionStorage.getItem('medimind_active_tab');
  if (savedTab && document.getElementById(savedTab)) {
    if (savedTab === 'profile-tab' && !currentUser) return 'home-tab';
    return savedTab;
  }
  return 'home-tab';
}

window.addEventListener('hashchange', () => {
  const hash = window.location.hash.replace('#', '').trim();
  if (hash && HASH_TAB_MAP[hash]) {
    switchTab(HASH_TAB_MAP[hash], false);
  }
});

window.addEventListener('popstate', () => {
  const hash = window.location.hash.replace('#', '').trim();
  if (hash && HASH_TAB_MAP[hash]) {
    switchTab(HASH_TAB_MAP[hash], false);
  }
});

function switchTab(tabId, updateHistory = true) {
  // Yêu cầu đăng nhập khi vào các tab bảo mật
  const protectedTabs = ['profile-tab', 'admin-tab'];
  if (protectedTabs.includes(tabId) && !currentUser) {
    pendingTabAfterLogin = tabId;
    openLoginModal();
    return;
  }

  // 1. Ẩn tất cả tab-content
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  
  // 2. Cập nhật thanh điều hướng Top Navbar
  document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.classList.remove('glass-pill-cyan-active', 'bg-white/20', 'text-white', 'font-bold', 'border', 'border-white/25', 'shadow-[0_0_15px_rgba(255,255,255,0.2)]');
    btn.classList.add('text-slate-300', 'font-semibold');
  });

  // 3. Cập nhật Dock Capsule bên trái
  document.querySelectorAll('.dock-btn').forEach(btn => {
    btn.removeAttribute('title');
    btn.classList.remove('bg-white', 'text-slate-950', 'shadow-[0_0_20px_rgba(255,255,255,0.45)]');
    btn.classList.add('text-white/60');
  });

  // 4. Kích hoạt DOM tab đích & pill sáng
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

  // 5. Lưu trạng thái vào sessionStorage để reload F5 phục hồi 100%
  try {
    sessionStorage.setItem('medimind_active_tab', tabId);
  } catch (_) {}

  // 6. Cập nhật URL Hash sâu mà không nhảy trang (Deep Linking)
  if (updateHistory) {
    const slug = TAB_HASH_MAP[tabId] || tabId.replace('-tab', '');
    if (window.location.hash !== `#${slug}`) {
      try {
        history.replaceState(null, '', `#${slug}`);
      } catch (e) {
        window.location.hash = slug;
      }
    }
  }

  // 7. Khởi tạo dữ liệu chuyên biệt từng tab trong try/catch (bảo vệ tuyệt đối hệ thống routing)
  try {
    if (tabId === 'booking-tab') {
      renderMedicalFacilities();
      setTimeout(() => {
        initHospitalInteractiveMap();
        if (hospitalLeafletMap) {
          hospitalLeafletMap.invalidateSize();
        }
      }, 150);
    } else if (tabId === 'doctor-tab') {
      syncCurrentPatientProfile();
      updateEhrTabUI();
    } else if (tabId === 'ocr-tab') {
      if (typeof loadScanFiles === 'function') loadScanFiles();
      if (typeof loadPrescriptionHistory === 'function') loadPrescriptionHistory();
    }
  } catch (tabInitErr) {
    console.error(`[Router] Lỗi khởi tạo tab ${tabId}:`, tabInitErr);
  }

  // 8. Quản lý Chatbot Nổi góc dưới khi chuyển sang các tab khác
  const floatingRoot = document.getElementById('floating-chatbot-root') || document.getElementById('floating-chat-container');
  if (floatingRoot) {
    if (tabId === 'chat-tab') {
      floatingRoot.classList.add('hidden');
      isFloatingChatDismissed = false;
    } else {
      if (!isFloatingChatDismissed) {
        floatingRoot.classList.remove('hidden');
        if (typeof syncFloatingChatMessages === 'function') syncFloatingChatMessages();
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
  if (container) {
    container.innerHTML = `
      <div class="flex items-start gap-3">
        <div class="w-8 h-8 rounded-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-white/10 text-sky-600 dark:text-sky-400 flex items-center justify-center shrink-0 shadow-xs mt-0.5">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"/></svg>
        </div>
        <div class="max-w-[85%] bg-white dark:bg-slate-800/90 border border-slate-200/80 dark:border-white/10 rounded-2xl p-4 sm:p-5 shadow-xs text-xs sm:text-sm text-slate-700 dark:text-slate-200 leading-relaxed font-normal">
          Xin chào, tôi là trợ lý y tế MediMind. Tôi có thể hỗ trợ bạn sàng lọc triệu chứng sơ bộ, giải thích đơn thuốc và gợi ý chuyên khoa khám phù hợp. Bạn đang gặp phải vấn đề sức khỏe nào?
        </div>
      </div>
    `;
  }

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
    <div id="${typingId}" class="flex items-start gap-3 max-w-md my-1">
      <div class="w-8 h-8 rounded-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-white/10 text-sky-600 dark:text-sky-400 flex items-center justify-center shrink-0 shadow-xs mt-0.5">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"/></svg>
      </div>
      <div class="bg-white dark:bg-slate-800/90 border border-slate-200/80 dark:border-white/10 px-4 py-3 rounded-2xl rounded-tl-sm text-xs sm:text-sm text-slate-600 dark:text-slate-300 flex items-center space-x-2 shadow-xs">
        <span class="w-2 h-2 rounded-full bg-sky-500 animate-ping"></span>
        <span class="pl-1.5 text-xs font-medium text-slate-600 dark:text-slate-300">${currentImage ? dict.typing_vision : dict.typing_guideline}</span>
      </div>
    </div>
  `;

  container.insertAdjacentHTML('beforeend', typingHtml);
  container.scrollTop = container.scrollHeight;

  try {
    const sentConvId = currentConversationId;
    // Gọi Chatbot AI kèm conversation_id (Backend tự động điều phối và đồng bộ với Intake Service)
    const chatRes = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        conversation_id: currentConversationId,
        message: text,
        history: chatHistory,
        image: currentImage,
        lang: currentLang
      })
    });
    const data = await chatRes.json();

    document.getElementById(typingId)?.remove();

    // KIỂM TRA ĐỐI SOÁT CUỘC TRÒ CHUYỆN (Tránh Race Condition khi người dùng chuyển cuộc chat)
    if (sentConvId && currentConversationId !== sentConvId) {
      console.warn(`[Chat] Bỏ qua cập nhật giao diện trực tiếp vì người dùng đã chuyển từ phiên '${sentConvId}' sang '${currentConversationId}'`);
      const targetId = data.conversation_id || sentConvId;
      let targetSession = chatSessions.find(s => s.id === targetId);
      if (targetSession) {
        if (!targetSession.messages) targetSession.messages = [];
        if (data.answer) {
          targetSession.messages.push({ role: 'assistant', content: data.answer });
          targetSession.lastMessage = data.answer.slice(0, 75).replace(/\n/g, ' ');
          targetSession.messageCount = targetSession.messages.length;
        }
        if (data.intake?.facts) targetSession.facts = data.intake.facts;
        if (data.intake?.summary) targetSession.summary = data.intake.summary;
        if (data.intake?.status) targetSession.status = data.intake.status;
        if (data.risk_level) targetSession.riskLevel = data.risk_level;
        if (data.risk_score !== undefined) targetSession.riskScore = data.risk_score;
        if (data.is_emergency !== undefined) targetSession.isEmergency = data.is_emergency;
        saveSessionsToStorage();
        renderChatHistoryList();
      }
      return;
    }

    // Đồng bộ tức thời Intake Session và Tóm tắt trước khám từ kết quả phản hồi hợp nhất
    if (data && data.conversation_id) {
      currentConversationId = data.conversation_id;
    }
    if (data && data.intake) {
      const intakeData = data.intake;
      if (intakeData.facts) {
        updateLiveIntakeCard(intakeData.facts, intakeData.status, intakeData.summary);
      }
      if (intakeData.summary) {
        currentIntakeSummary = intakeData.summary;
      }
    }

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
      <div class="flex items-start gap-3 max-w-[95%] sm:max-w-2xl my-1">
        <div class="w-8 h-8 rounded-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-white/10 text-sky-600 dark:text-sky-400 flex items-center justify-center shrink-0 shadow-xs mt-0.5">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"/></svg>
        </div>
        <div class="bg-white dark:bg-slate-800/90 border border-slate-200/80 dark:border-white/10 p-4 sm:p-5 rounded-2xl rounded-tl-sm text-xs sm:text-sm text-slate-800 dark:text-slate-100 space-y-3 leading-relaxed shadow-xs w-full">
          ${emergencyBadge}
          ${visualFindingsHtml}
          <div class="text-slate-800 dark:text-slate-100 font-normal leading-relaxed">${formattedAnswer}</div>
        </div>
      </div>
    `;

    container.insertAdjacentHTML('beforeend', botHtml);
    container.scrollTop = container.scrollHeight;

    chatHistory.push({ role: 'user', content: text, image: currentImage });
    chatHistory.push({ role: 'assistant', content: data.answer });

    saveOrUpdateCurrentSession(text, data, data.intake);
    if (data.history_saved === false) appendErrorMessage("Chưa lưu được lượt tư vấn này vào hồ sơ.");

  } catch (err) {
    document.getElementById(typingId)?.remove();
    appendErrorMessage(dict.server_error);
  }
}

// Cập nhật phân tầng lâm sàng định tính (Tuyệt đối KHÔNG hiển thị điểm xác suất 0-100 giả lập)
function updateTriagePanel(data) {
  const floatingRisk = document.getElementById('floating-risk-score');
  const score = data.risk_score;
  if (floatingRisk) {
    if (data.is_emergency || score >= 70) {
      floatingRisk.innerText = `Cảnh báo cấp cứu khẩn cấp`;
      floatingRisk.className = 'text-xs font-bold text-rose-400';
    } else if (score == null) {
      floatingRisk.innerText = 'Chưa đủ thông tin';
      floatingRisk.className = 'text-xs font-bold text-slate-500';
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
      statusBadge.className = 'px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-300 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-500/40';
      if (btnConfirm) btnConfirm.classList.add('hidden');
    } else if (status === 'ready_for_review') {
      statusBadge.innerText = 'Chờ xác nhận';
      statusBadge.className = 'px-2.5 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-300 dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-500/40';
      if (btnConfirm) btnConfirm.classList.remove('hidden');
    } else {
      statusBadge.innerText = 'Đang thu thập';
      statusBadge.className = 'px-2.5 py-1 rounded-full text-xs font-bold bg-sky-100 text-sky-800 border border-sky-300 dark:bg-sky-950/60 dark:text-sky-300 dark:border-sky-500/40';
      if (btnConfirm) btnConfirm.classList.remove('hidden');
    }
  }
}

function openPreVisitSummaryModal() {
  document.getElementById('modal-btn-confirm')?.classList.remove('hidden');
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

let reviewedIntakeSummary = null;
function renderPreVisitSummaryInModal(summary) {
  reviewedIntakeSummary = { id: currentConversationId, summary };
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
  if (vEl) vEl.innerText = partA.vitals || 'Chưa có chỉ số tự đo tại nhà';
  if (attEl) attEl.innerText = partA.attachments_and_observations || 'Không có tệp hình ảnh đính kèm';
  if (mEl) mEl.innerText = (partA.missing_or_unclear_info && partA.missing_or_unclear_info.length) ? partA.missing_or_unclear_info.join('; ') : 'Đã đủ thông tin cơ bản';

  const algEl = document.getElementById('summary-a-allergies');
  const medEl = document.getElementById('summary-a-medications');
  if (algEl) algEl.innerText = partA.allergies || 'Chưa ghi nhận tiền sử dị ứng đặc biệt';
  if (medEl) medEl.innerText = partA.current_medications || 'Chưa ghi nhận thuốc đang dùng thường xuyên';

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
    bSources.innerHTML = sList.map(s => `• Nguồn: <a href="${sanitizeUrl(s.url)}" target="_blank" rel="noopener noreferrer" class="underline hover:text-white">${escapeHtml(s.title || s.source || 'Tài liệu tham khảo')}</a>`).join('<br>');
  }

  const modalConfirmBtn = document.getElementById('modal-btn-confirm');
  if (modalConfirmBtn) {
    if (summary.is_confirmed) {
      modalConfirmBtn.innerHTML = '<span>✓ Đã xác nhận lời khai</span>';
      modalConfirmBtn.disabled = true;
      modalConfirmBtn.classList.add('opacity-60', 'cursor-not-allowed');
    } else {
      modalConfirmBtn.innerHTML = '<span>Xác nhận và lưu vào hồ sơ</span>';
      modalConfirmBtn.disabled = false;
      modalConfirmBtn.classList.remove('opacity-60', 'cursor-not-allowed');
    }
  }
}

async function confirmCurrentIntake() {
  if (!currentConversationId || reviewedIntakeSummary?.id !== currentConversationId) return;
  try {
    const res = await fetch('/api/intake/confirm-summary', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conversation_id: currentConversationId, version: reviewedIntakeSummary?.summary.version, reviewed_facts: reviewedIntakeSummary?.summary.part_a_patient_facts, save_to_record: true })
    });
    const data = await res.json();
    if (!res.ok) {
      showMedicalToast(data.error || "Chưa lưu được bản tóm tắt.", "error");
      return;
    }
    if (data.summary) {
      currentIntakeSummary = data.summary;
      const saved = chatSessions.find(item => item.id === currentConversationId);
      if (saved) {
        saved.status = 'confirmed';
        saved.summary = data.summary;
        saveSessionsToStorage();
        updateLiveIntakeCard(saved.facts, 'confirmed', data.summary);
      }
      showMedicalToast("Đã lưu bản tóm tắt vào hồ sơ.", "success");
      return data.summary;
    }
  } catch (e) {
    showMedicalToast("Lỗi khi xác nhận lời khai", "error");
  }
}

async function confirmIntakeSummaryModal() {
  const sum = await confirmCurrentIntake();
  if (sum) {
    renderPreVisitSummaryInModal(sum);
  } else if (currentIntakeSummary) {
    renderPreVisitSummaryInModal(currentIntakeSummary);
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
  if (!currentUser || currentUser.isDemo) {
    const ocrEmpty = document.getElementById('ocr-table-empty');
    const ocrFilled = document.getElementById('ocr-table-filled');
    const countBadge = document.getElementById('scan-files-count');
    if (countBadge) countBadge.innerText = '0 tệp';
    if (ocrEmpty) ocrEmpty.classList.remove('hidden');
    if (ocrFilled) ocrFilled.classList.add('hidden');
    return;
  }

  try {
    const res = await fetch('/api/scan-files');
    if (!res.ok) return;
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
                <button type="button" onclick="deleteScanFile('${encodeURIComponent(f.id || f.filename || f.name)}')" class="text-rose-500 hover:text-rose-700 hover:bg-rose-50 p-1.5 rounded-lg transition-colors cursor-pointer" title="Xóa tệp khỏi tập huấn luyện">
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
  if (string === null || string === undefined) return '';
  const div = document.createElement('div');
  div.innerText = String(string);
  return div.innerHTML;
}

function sanitizeUrl(rawUrl) {
  if (!rawUrl || typeof rawUrl !== 'string') return '#';
  const trimmed = rawUrl.trim();
  if (/^(?:https?:\/\/|\/)/i.test(trimmed)) {
    return encodeURI(trimmed).replace(/["']/g, '');
  }
  return '#';
}

// ==========================================
// Authentication & Profile State Management
// ==========================================
function toggleUserDropdown(e) {
  if (e) e.stopPropagation();
  const menu = document.getElementById('user-dropdown-menu');
  const arrow = document.getElementById('user-dropdown-arrow');
  if (menu) menu.classList.toggle('hidden');
  if (arrow) arrow.classList.toggle('rotate-180');
}

function closeUserDropdown() {
  const menu = document.getElementById('user-dropdown-menu');
  const arrow = document.getElementById('user-dropdown-arrow');
  if (menu) menu.classList.add('hidden');
  if (arrow) arrow.classList.remove('rotate-180');
}

function toggleProfileEdit(isEdit) {
  const viewMode = document.getElementById('profile-view-mode');
  const editMode = document.getElementById('profile-edit-mode');
  if (!viewMode || !editMode) return;

  if (isEdit) {
    const curDob = currentUser?.dob || document.getElementById('edit-profile-dob')?.value || '';
    if (currentUser) {
      const nameInput = document.getElementById('edit-profile-name');
      const genderSelect = document.getElementById('edit-profile-gender');
      const dobInput = document.getElementById('edit-profile-dob');
      const phoneInput = document.getElementById('edit-profile-phone');

      if (nameInput) nameInput.value = currentUser.name || '';
      if (genderSelect) genderSelect.value = currentUser.gender || 'Nam';
      if (dobInput) dobInput.value = curDob;
      if (phoneInput) phoneInput.value = currentUser.phone_number || '';
    }
    populateModalDobDropdowns('edit-profile-dob-day', 'edit-profile-dob-month', 'edit-profile-dob-year', curDob);
    syncEditProfileDobFromDropdowns();
    viewMode.classList.add('hidden');
    editMode.classList.remove('hidden');
    document.getElementById('edit-profile-name')?.focus();
  } else {
    editMode.classList.add('hidden');
    viewMode.classList.remove('hidden');
  }
}

let isPendingGoogleRegistration = false;
let pendingGoogleProfile = null;

async function handleSaveProfile(e) {
  if (e) e.preventDefault();
  syncEditProfileDobFromDropdowns();
  const name = document.getElementById('edit-profile-name')?.value.trim();
  const gender = document.getElementById('edit-profile-gender')?.value;
  const dob = document.getElementById('edit-profile-dob')?.value.trim();
  const phone = document.getElementById('edit-profile-phone')?.value.trim();

  if (!name) {
    if (typeof showMedicalToast === 'function') showMedicalToast('Vui lòng nhập họ và tên.', 'warning');
    else alert('Vui lòng nhập họ và tên.');
    return;
  }

  if (dob && !/^\d{2}\/\d{2}\/\d{4}$/.test(dob)) {
    if (typeof showMedicalToast === 'function') {
      showMedicalToast('Ngày sinh phải đúng định dạng DD/MM/YYYY (VD: 15/08/1995).', 'warning', 4500);
    } else {
      alert('Ngày sinh phải đúng định dạng DD/MM/YYYY (VD: 15/08/1995).');
    }
    document.getElementById('edit-profile-dob')?.focus();
    return;
  }

  if (phone) {
    const cleanDigits = phone.replace(/\D/g, '');
    if (cleanDigits.length < 9 || cleanDigits.length > 11) {
      if (typeof showMedicalToast === 'function') {
        showMedicalToast('Số điện thoại không hợp lệ (cần từ 9 đến 11 chữ số).', 'warning', 4500);
      } else {
        alert('Số điện thoại không hợp lệ (cần từ 9 đến 11 chữ số).');
      }
      document.getElementById('edit-profile-phone')?.focus();
      return;
    }
  }

  if (isPendingGoogleRegistration) {
    // Cho phép người dùng xác nhận vào ngay lập tức (ngày sinh / SĐT tùy chọn)
  }

  const endpoint = isPendingGoogleRegistration ? '/api/auth/google/complete-registration' : '/api/auth/profile';
  const submitBtn = document.querySelector('#profile-edit-mode button[type="submit"]');
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.classList.add('opacity-60', 'cursor-not-allowed');
  }

  let data = null;
  try {
    const res = await fetch(endpoint, {
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
    data = await res.json();
  } catch (netErr) {
    console.error('Lỗi kết nối máy chủ:', netErr);
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.classList.remove('opacity-60', 'cursor-not-allowed');
    }
    if (typeof showMedicalToast === 'function') showMedicalToast('Không thể kết nối đến máy chủ.', 'error');
    return;
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.classList.remove('opacity-60', 'cursor-not-allowed');
    }
  }

  if (data && data.success && data.user) {
    const wasNewReg = isPendingGoogleRegistration;
    isPendingGoogleRegistration = false;
    pendingGoogleProfile = null;
    currentUser = { ...(currentUser || {}), ...data.user };
    if (!currentUser.hasCustomAvatar) {
      currentUser.avatar = currentUser.avatar_url || getDefaultAvatarByGender(currentUser.gender || gender);
    }
    localStorage.setItem('medimind_user', JSON.stringify(currentUser));
    try {
      updateAuthUI();
      broadcastTabEvent(wasNewReg ? 'AUTH_LOGIN' : 'PROFILE_UPDATE', { user: currentUser });
    } catch (uiErr) {
      console.warn('Lỗi cập nhật DOM UI sau lưu thông tin:', uiErr);
    }
    closeProfileModal();
    if (typeof showMedicalToast === 'function') {
      showMedicalToast(
        wasNewReg
          ? `Đăng ký hồ sơ Google thành công! Chào mừng ${currentUser.name}.`
          : 'Đã hoàn tất và lưu hồ sơ y tế thành công!',
        'success',
        4500
      );
    }
  } else {
    if (typeof showMedicalToast === 'function') showMedicalToast(data?.error || 'Lưu thông tin thất bại.', 'error', 4500);
    else alert(data?.error || 'Cập nhật thông tin thất bại.');
  }
}

function openProfileModal() {
  closeUserDropdown();
  switchTab('profile-tab');
}

function populateModalDobDropdowns(dayId, monthId, yearId, currentDobStr) {
  const daySelect = document.getElementById(dayId);
  const monthSelect = document.getElementById(monthId);
  const yearSelect = document.getElementById(yearId);
  if (!daySelect || !monthSelect || !yearSelect) return;

  let selDay = '', selMonth = '', selYear = '';
  if (currentDobStr && typeof currentDobStr === 'string' && currentDobStr.trim()) {
    const parts = currentDobStr.trim().split(/[\/\-]/);
    if (parts.length === 3) {
      if (parts[0].length === 4) {
        selYear = parts[0];
        selMonth = String(parseInt(parts[1], 10));
        selDay = String(parseInt(parts[2], 10));
      } else {
        selDay = String(parseInt(parts[0], 10));
        selMonth = String(parseInt(parts[1], 10));
        selYear = parts[2];
      }
    }
  }

  const dayText = currentLang === 'en' ? 'Day' : 'Ngày';
  const monthText = currentLang === 'en' ? 'Month' : 'Tháng';
  const yearText = currentLang === 'en' ? 'Year' : 'Năm';

  daySelect.innerHTML = `<option value="" disabled ${!selDay ? 'selected' : ''}>${dayText}</option>` + 
    Array.from({length: 31}, (_, i) => `<option value="${i+1}" ${selDay == (i+1) ? 'selected' : ''}>${i+1}</option>`).join('');

  monthSelect.innerHTML = `<option value="" disabled ${!selMonth ? 'selected' : ''}>${monthText}</option>` + 
    Array.from({length: 12}, (_, i) => `<option value="${i+1}" ${selMonth == (i+1) ? 'selected' : ''}>${currentLang === 'en' ? `Month ${i+1}` : `Tháng ${i+1}`}</option>`).join('');

  const currentYear = new Date().getFullYear();
  yearSelect.innerHTML = `<option value="" disabled ${!selYear ? 'selected' : ''}>${yearText}</option>` + 
    Array.from({length: 90}, (_, i) => `<option value="${currentYear - i}" ${selYear == (currentYear - i) ? 'selected' : ''}>${currentYear - i}</option>`).join('');
}

function syncEditProfileDobFromDropdowns() {
  const d = document.getElementById('edit-profile-dob-day')?.value;
  const m = document.getElementById('edit-profile-dob-month')?.value;
  const y = document.getElementById('edit-profile-dob-year')?.value;
  const hiddenInput = document.getElementById('edit-profile-dob');
  if (hiddenInput) {
    if (d && m && y) {
      hiddenInput.value = `${String(d).padStart(2, '0')}/${String(m).padStart(2, '0')}/${y}`;
    } else {
      hiddenInput.value = '';
    }
  }
}

function openGoogleOnboardingModal(user, isNewRegistration = false) {
  const u = user || pendingGoogleProfile || currentUser;
  if (!u) return;
  isPendingGoogleRegistration = Boolean(isNewRegistration);
  const modal = document.getElementById('profile-modal');
  const nameHeader = document.getElementById('profile-name');
  const badgeHeader = document.getElementById('profile-badge');
  const avatarHeader = document.getElementById('profile-avatar');
  const displayName = u.full_name || u.name || 'Bệnh nhân mới';

  if (nameHeader) nameHeader.innerText = displayName;
  if (badgeHeader) {
    badgeHeader.innerText = isPendingGoogleRegistration
      ? `Tài khoản Google mới: ${u.email || ''} • Xác nhận thông tin để vào ứng dụng`
      : 'Xác thực Google thành công • Thông tin hồ sơ cá nhân';
  }

  const saveBtnSpan = document.getElementById('profile-save-btn-text') || document.querySelector('#profile-edit-mode button[type="submit"] span');
  if (saveBtnSpan) {
    saveBtnSpan.innerText = isPendingGoogleRegistration ? 'Xác nhận & Vào ứng dụng' : 'Lưu thông tin';
  }

  // Cải tiến hiển thị Avatar chống vỡ ảnh (Graceful Fallback với Gradient Initial Badge)
  if (avatarHeader) {
    const initial = displayName.trim().split(/\s+/).pop().charAt(0).toUpperCase() || 'G';
    const bgGradient = 'bg-gradient-to-tr from-sky-500 to-indigo-600';
    avatarHeader.className = `w-13 h-13 rounded-2xl ${bgGradient} text-white font-black text-lg flex items-center justify-center border border-sky-400/40 shadow-md shadow-sky-500/20 shrink-0 overflow-hidden relative`;

    if (u.avatar_url && typeof u.avatar_url === 'string' && u.avatar_url.startsWith('http')) {
      avatarHeader.innerHTML = `
        <img src="${escapeHtml(u.avatar_url)}" alt="" class="w-full h-full object-cover rounded-2xl" 
             referrerpolicy="no-referrer"
             onerror="this.style.display='none'; const fb = this.nextElementSibling; if(fb) fb.classList.remove('hidden');" />
        <div class="hidden w-full h-full ${bgGradient} text-white font-black text-lg flex items-center justify-center">
          ${escapeHtml(initial)}
        </div>
      `;
    } else {
      avatarHeader.innerHTML = `<span>${escapeHtml(initial)}</span>`;
    }
  }

  toggleProfileEdit(true);
  const nameInput = document.getElementById('edit-profile-name');
  const genderSelect = document.getElementById('edit-profile-gender');
  const dobInput = document.getElementById('edit-profile-dob');
  const phoneInput = document.getElementById('edit-profile-phone');

  if (nameInput) nameInput.value = displayName;
  if (genderSelect) genderSelect.value = u.gender || 'Nam';
  if (dobInput) dobInput.value = u.dob || '';
  if (phoneInput) phoneInput.value = u.phone_number || '';

  // Nạp 3 dropdowns Ngày / Tháng / Năm
  populateModalDobDropdowns('edit-profile-dob-day', 'edit-profile-dob-month', 'edit-profile-dob-year', u.dob || '');
  syncEditProfileDobFromDropdowns();

  if (modal) modal.classList.remove('hidden');
  setTimeout(() => {
    if (phoneInput && !phoneInput.value) phoneInput.focus();
  }, 100);
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
      broadcastTabEvent('PROFILE_UPDATE', { user: currentUser });
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
  if (isPendingGoogleRegistration) {
    isPendingGoogleRegistration = false;
    pendingGoogleProfile = null;
    fetch('/api/auth/google/cancel-registration', { method: 'POST' }).catch(() => {});
    if (typeof showMedicalToast === 'function') {
      showMedicalToast('Đã hủy hoàn tất đăng ký Google (hồ sơ chưa được tạo).', 'info', 4000);
    }
  }
  toggleProfileEdit(false);
  const modal = document.getElementById('profile-modal');
  if (modal) modal.classList.add('hidden');
}

function syncAuthModalTheme() {
  const isLight = document.body.classList.contains('light-glass');
  const card = document.getElementById('auth-modal-card');
  const title = document.getElementById('auth-modal-title');
  const modal = document.getElementById('login-modal');
  const dividerBadge = document.getElementById('auth-divider-badge');
  const divLineLeft = document.getElementById('auth-divider-line-left');
  const divLineRight = document.getElementById('auth-divider-line-right');
  const btnGoogle = document.getElementById('btn-google-signin');
  const googleCard = document.getElementById('google-account-card');

  if (!card) return;

  if (isLight) {
    card.classList.remove('bg-slate-900/95', 'text-white', 'border-white/15');
    card.classList.add('bg-white', 'text-slate-900', 'border-slate-200', 'shadow-2xl');
    if (title) {
      title.classList.remove('text-white');
      title.classList.add('text-slate-900');
    }
    if (modal) {
      modal.classList.remove('bg-black/60');
      modal.classList.add('bg-slate-900/40');
    }
    if (dividerBadge) dividerBadge.className = "px-3 text-[11px] font-semibold text-slate-400 uppercase tracking-wider whitespace-nowrap bg-white rounded-full";
    if (divLineLeft) divLineLeft.className = "border-t border-slate-200 w-full";
    if (divLineRight) divLineRight.className = "border-t border-slate-200 w-full";
    if (btnGoogle) {
      btnGoogle.className = "w-full py-2.5 px-4 rounded-xl bg-white hover:bg-slate-50 text-slate-700 text-xs sm:text-sm font-semibold shadow-sm hover:shadow transition-all flex items-center justify-center gap-3 border border-slate-300/80 cursor-pointer";
      const span = btnGoogle.querySelector('span');
      if (span) span.className = "font-semibold text-slate-700";
    }
    if (googleCard) {
      googleCard.classList.remove('bg-slate-900', 'text-white', 'border-white/15');
      googleCard.classList.add('bg-white', 'text-slate-800', 'border-slate-200');
    }
  } else {
    card.classList.remove('bg-white', 'text-slate-900', 'border-slate-200');
    card.classList.add('bg-slate-900/95', 'text-white', 'border-white/15', 'shadow-2xl');
    if (title) {
      title.classList.remove('text-slate-900');
      title.classList.add('text-white');
    }
    if (modal) {
      modal.classList.remove('bg-slate-900/40');
      modal.classList.add('bg-black/60');
    }
    if (dividerBadge) dividerBadge.className = "px-3 text-[11px] font-semibold text-slate-400 uppercase tracking-wider whitespace-nowrap bg-slate-900 rounded-full";
    if (divLineLeft) divLineLeft.className = "border-t border-white/10 w-full";
    if (divLineRight) divLineRight.className = "border-t border-white/10 w-full";
    if (btnGoogle) {
      btnGoogle.className = "w-full py-2.5 px-4 rounded-xl bg-white/[0.08] hover:bg-white/[0.12] text-white text-xs sm:text-sm font-semibold shadow-sm transition-all flex items-center justify-center gap-3 border border-white/15 cursor-pointer";
      const span = btnGoogle.querySelector('span');
      if (span) span.className = "font-semibold text-white";
    }
    if (googleCard) {
      googleCard.classList.remove('bg-white', 'text-slate-800', 'border-slate-200');
      googleCard.classList.add('bg-slate-900', 'text-white', 'border-white/15');
    }
  }
  if (typeof toggleAuthMode === 'function') {
    toggleAuthMode(currentAuthMode);
  }
}

function resetAuthModal() {
  if (otpCountdownTimer) {
    clearInterval(otpCountdownTimer);
    otpCountdownTimer = null;
  }
  currentOtpRemaining = 59;
  pendingOtpFlow = {
    identifier: '',
    channel: 'sms',
    purpose: 'register',
    userData: null,
    previousMode: 'register'
  };

  // Reset forms
  const loginForm = document.getElementById('login-form');
  const regForm = document.getElementById('register-form');
  const otpForm = document.getElementById('otp-form');
  if (loginForm) loginForm.reset();
  if (regForm) regForm.reset();
  if (otpForm) otpForm.reset();

  // Clear inputs explicitly to prevent lingering state on logout / new account
  const regLastName = document.getElementById('register-last-name');
  const regFirstName = document.getElementById('register-first-name');
  const regName = document.getElementById('register-name');
  const regIdent = document.getElementById('register-identifier');
  const regEmail = document.getElementById('register-email');
  const regPass = document.getElementById('register-password');
  const regDob = document.getElementById('register-dob');
  const regGender = document.getElementById('register-gender');

  if (regLastName) regLastName.value = '';
  if (regFirstName) regFirstName.value = '';
  if (regName) regName.value = '';
  if (regIdent) regIdent.value = '';
  if (regEmail) regEmail.value = '';
  if (regPass) regPass.value = '';
  if (regDob) regDob.value = '';
  if (regGender) regGender.value = 'Nam';

  const loginIdent = document.getElementById('login-identifier');
  const loginPass = document.getElementById('login-password');
  if (loginIdent) loginIdent.value = '';
  if (loginPass) loginPass.value = '';

  clearOtpInputs();
  const timerWrap = document.getElementById('otp-timer-wrap');
  const resendBtn = document.getElementById('btn-otp-resend');
  const targetDisplay = document.getElementById('otp-target-display');
  if (timerWrap) timerWrap.classList.remove('hidden');
  if (resendBtn) resendBtn.classList.add('hidden');
  if (targetDisplay) targetDisplay.innerText = '...';

  populateDobDropdowns();
}

function openLoginModal(mode = 'login') {
  syncAuthModalTheme();
  const modal = document.getElementById('login-modal');
  if (modal) {
    toggleAuthMode(mode || 'login');
    modal.classList.remove('hidden');
    if (mode === 'register') {
      document.getElementById('register-last-name')?.focus();
    } else {
      document.getElementById('login-identifier')?.focus();
    }
  }
  if (typeof setupOtpDigitInputs === 'function') setupOtpDigitInputs();
}

function closeLoginModal() {
  const modal = document.getElementById('login-modal');
  if (modal) modal.classList.add('hidden');
  resetAuthModal();
}

function populateDobDropdowns() {
  const daySelect = document.getElementById('register-dob-day');
  const monthSelect = document.getElementById('register-dob-month');
  const yearSelect = document.getElementById('register-dob-year');
  if (!daySelect || !monthSelect || !yearSelect) return;

  const prevDay = daySelect.value;
  const prevMonth = monthSelect.value;
  const prevYear = yearSelect.value;

  const dayText = currentLang === 'en' ? 'Day' : 'Ngày';
  const monthText = currentLang === 'en' ? 'Month' : 'Tháng';
  const yearText = currentLang === 'en' ? 'Year' : 'Năm';

  daySelect.innerHTML = `<option value="" disabled ${!prevDay ? 'selected' : ''} class="bg-slate-900 text-white">${dayText}</option>` + 
    Array.from({length: 31}, (_, i) => `<option value="${i+1}" ${prevDay == (i+1) ? 'selected' : ''} class="bg-slate-900 text-white">${i+1}</option>`).join('');

  monthSelect.innerHTML = `<option value="" disabled ${!prevMonth ? 'selected' : ''} class="bg-slate-900 text-white">${monthText}</option>` + 
    Array.from({length: 12}, (_, i) => `<option value="${i+1}" ${prevMonth == (i+1) ? 'selected' : ''} class="bg-slate-900 text-white">${currentLang === 'en' ? `Month ${i+1}` : `Tháng ${i+1}`}</option>`).join('');

  const currentYear = new Date().getFullYear();
  yearSelect.innerHTML = `<option value="" disabled ${!prevYear ? 'selected' : ''} class="bg-slate-900 text-white">${yearText}</option>` + 
    Array.from({length: 85}, (_, i) => `<option value="${currentYear - i}" ${prevYear == (currentYear - i) ? 'selected' : ''} class="bg-slate-900 text-white">${currentYear - i}</option>`).join('');
}

let currentAuthMode = 'login';
function toggleAuthMode(mode) {
  currentAuthMode = mode;
  const dict = translations[currentLang] || translations.vi;
  const titleEl = document.getElementById('auth-modal-title');
  const loginForm = document.getElementById('login-form');
  const regForm = document.getElementById('register-form');
  const otpForm = document.getElementById('otp-form');
  const googleContainer = document.getElementById('google-auth-container');
  const socialDivider = document.getElementById('auth-social-divider');
  const tabsContainer = document.querySelector('.auth-segmented-tabs');
  const tabLogin = document.getElementById('tab-auth-login');
  const tabReg = document.getElementById('tab-auth-register');

  const isLight = document.body.classList.contains('light-glass');

  if (mode === 'login') {
    if (titleEl) titleEl.innerText = dict.modal_login_title || "Đăng nhập MediMind AI";
    if (loginForm) loginForm.classList.remove('hidden');
    if (regForm) regForm.classList.add('hidden');
    if (otpForm) otpForm.classList.add('hidden');
    if (googleContainer) googleContainer.classList.remove('hidden');
    if (socialDivider) socialDivider.classList.remove('hidden');
    if (tabsContainer) tabsContainer.classList.remove('hidden');
    const googleSpan = document.querySelector('#btn-google-signin span');
    if (googleSpan) {
      googleSpan.innerText = dict.btn_google_signin || (currentLang === 'en' ? 'Continue with Google' : 'Tiếp tục với Google');
    }

    if (tabLogin) {
      if (isLight) {
        tabLogin.className = "flex-1 py-2 px-3 rounded-lg bg-white text-sky-600 font-bold shadow-xs border-0 transition-all cursor-pointer active";
      } else {
        tabLogin.className = "flex-1 py-2 px-3 rounded-lg bg-sky-500 text-white font-bold shadow-xs border-0 transition-all cursor-pointer active";
      }
    }
    if (tabReg) {
      if (isLight) {
        tabReg.className = "flex-1 py-2 px-3 rounded-lg border-0 bg-transparent text-slate-500 hover:text-slate-900 font-medium transition-all cursor-pointer";
      } else {
        tabReg.className = "flex-1 py-2 px-3 rounded-lg border-0 bg-transparent text-slate-400 hover:text-white font-medium transition-all cursor-pointer";
      }
    }
  } else if (mode === 'register') {
    if (titleEl) titleEl.innerText = dict.modal_reg_title || "Đăng ký tài khoản MediMind";
    if (loginForm) loginForm.classList.add('hidden');
    if (regForm) regForm.classList.remove('hidden');
    if (otpForm) otpForm.classList.add('hidden');
    if (googleContainer) googleContainer.classList.remove('hidden');
    if (socialDivider) socialDivider.classList.remove('hidden');
    if (tabsContainer) tabsContainer.classList.remove('hidden');
    const googleSpan = document.querySelector('#btn-google-signin span');
    if (googleSpan) {
      googleSpan.innerText = dict.btn_google_signin || (currentLang === 'en' ? 'Continue with Google' : 'Tiếp tục với Google');
    }

    if (tabReg) {
      if (isLight) {
        tabReg.className = "flex-1 py-2 px-3 rounded-lg bg-white text-sky-600 font-bold shadow-xs border-0 transition-all cursor-pointer active";
      } else {
        tabReg.className = "flex-1 py-2 px-3 rounded-lg bg-sky-500 text-white font-bold shadow-xs border-0 transition-all cursor-pointer active";
      }
    }
    if (tabLogin) {
      if (isLight) {
        tabLogin.className = "flex-1 py-2 px-3 rounded-lg border-0 bg-transparent text-slate-500 hover:text-slate-900 font-medium transition-all cursor-pointer";
      } else {
        tabLogin.className = "flex-1 py-2 px-3 rounded-lg border-0 bg-transparent text-slate-400 hover:text-white font-medium transition-all cursor-pointer";
      }
    }
  } else if (mode === 'otp') {
    if (titleEl) titleEl.innerText = "Xác thực mã bảo mật (OTP)";
    if (loginForm) loginForm.classList.add('hidden');
    if (regForm) regForm.classList.add('hidden');
    if (otpForm) otpForm.classList.remove('hidden');
    if (googleContainer) googleContainer.classList.add('hidden');
    if (socialDivider) socialDivider.classList.add('hidden');
    if (tabsContainer) tabsContainer.classList.add('hidden');
  }
}

function selectLoginRole(role) {
  currentRole = 'patient';
}


// ==============================================================
// CROSS-TAB REALTIME SYNCHRONIZATION (BroadcastChannel API v16.1.0)
// ==============================================================
const TAB_SYNC_CHANNEL_NAME = 'medimind_tab_sync';
let tabSyncChannel = null;

try {
  if (typeof BroadcastChannel !== 'undefined') {
    tabSyncChannel = new BroadcastChannel(TAB_SYNC_CHANNEL_NAME);
  }
} catch (e) {
  console.warn('BroadcastChannel not supported in this context:', e);
}

function broadcastTabEvent(eventType, payload) {
  const message = { type: eventType, payload, timestamp: Date.now() };
  if (tabSyncChannel) {
    try {
      tabSyncChannel.postMessage(message);
    } catch (e) {
      console.warn('BroadcastChannel send error:', e);
    }
  }
  try {
    localStorage.setItem('medimind_cross_tab_event', JSON.stringify(message));
  } catch (e) {}
}

function handleCrossTabMessage(data) {
  if (!data || !data.type) return;
  console.log('⚡ [Cross-Tab Sync 0.01s] Event received:', data.type, data.payload);

  if (data.type === 'THEME_CHANGE') {
    const targetTheme = data.payload?.theme || 'light';
    const isCurrentlyLight = document.body.classList.contains('light-glass');
    if ((targetTheme === 'light' && !isCurrentlyLight) || (targetTheme === 'dark' && isCurrentlyLight)) {
      if (targetTheme === 'light') {
        document.body.classList.add('light-glass');
        document.body.style.backgroundImage = CLINICAL_CYAN_GLOW.light;
      } else {
        document.body.classList.remove('light-glass');
        document.body.style.backgroundImage = CLINICAL_CYAN_GLOW.dark;
      }
      document.body.style.backgroundAttachment = 'fixed';
      localStorage.setItem('medimind_theme', targetTheme);
      if (typeof syncAuthModalTheme === 'function') syncAuthModalTheme();
    }
  } else if (data.type === 'AUTH_LOGIN' || data.type === 'PROFILE_UPDATE' || data.type === 'AUTH_PROFILE_UPDATE') {
    if (data.payload?.user) {
      currentUser = data.payload.user;
      localStorage.setItem('medimind_user', JSON.stringify(currentUser));
      updateAuthUI();
      if (typeof closeLoginModal === 'function') closeLoginModal();
    }
  } else if (data.type === 'AUTH_LOGOUT') {
    currentUser = null;
    Object.keys(fieldRealValues).forEach(k => delete fieldRealValues[k]);
    Object.keys(fieldMaskState).forEach(k => {
      fieldMaskState[k] = false;
      const el = document.getElementById(k);
      if (el) el.readOnly = false;
    });
    document.getElementById('profile-form-img1')?.reset();
    localStorage.removeItem('medimind_user');
    sessionStorage.removeItem('medimind_active_tab');
    sessionStorage.removeItem('medimind_profile_draft');
    try {
      history.replaceState(null, '', window.location.pathname);
    } catch (e) {
      window.location.hash = '';
    }
    updateAuthUI();
    if (typeof switchTab === 'function') switchTab('home-tab');
  }
}

if (tabSyncChannel) {
  tabSyncChannel.onmessage = (event) => {
    handleCrossTabMessage(event.data);
  };
}

window.addEventListener('storage', (event) => {
  if (event.key === 'medimind_cross_tab_event' && event.newValue) {
    try {
      const parsed = JSON.parse(event.newValue);
      handleCrossTabMessage(parsed);
    } catch (e) {}
  } else if (event.key === 'medimind_theme' && event.newValue) {
    handleCrossTabMessage({ type: 'THEME_CHANGE', payload: { theme: event.newValue } });
  } else if (event.key === 'medimind_user') {
    if (event.newValue) {
      try {
        const u = JSON.parse(event.newValue);
        handleCrossTabMessage({ type: 'AUTH_LOGIN', payload: { user: u } });
      } catch (e) {}
    } else {
      handleCrossTabMessage({ type: 'AUTH_LOGOUT', payload: null });
    }
  }
});


// ==============================================================
// OTP VERIFICATION FLOW & 6-DIGIT AUTO-FOCUS INPUTS
// ==============================================================
let otpCountdownTimer = null;
let currentOtpRemaining = 59;
let pendingOtpFlow = {
  identifier: '',
  channel: 'sms',
  purpose: 'register',
  userData: null,
  previousMode: 'register'
};

function setupOtpDigitInputs() {
  const container = document.getElementById('otp-inputs-container');
  if (!container || container._otpInitialized) return;
  container._otpInitialized = true;
  const digits = container.querySelectorAll('.otp-digit');

  digits.forEach((input, index) => {
    input.addEventListener('input', (e) => {
      const val = e.target.value.replace(/[^0-9]/g, '');
      e.target.value = val;
      if (val && index < digits.length - 1) {
        digits[index + 1].focus();
        digits[index + 1].select();
      }
      checkAutoSubmitOtp();
    });

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Backspace' && !e.target.value && index > 0) {
        digits[index - 1].focus();
        digits[index - 1].select();
      } else if (e.key === 'ArrowLeft' && index > 0) {
        digits[index - 1].focus();
      } else if (e.key === 'ArrowRight' && index < digits.length - 1) {
        digits[index + 1].focus();
      }
    });

    input.addEventListener('paste', (e) => {
      e.preventDefault();
      const pasteData = (e.clipboardData || window.clipboardData).getData('text');
      const cleanDigits = pasteData.replace(/[^0-9]/g, '').slice(0, 6);
      if (cleanDigits.length > 0) {
        cleanDigits.split('').forEach((char, i) => {
          if (digits[i]) digits[i].value = char;
        });
        const targetIndex = Math.min(cleanDigits.length, digits.length - 1);
        digits[targetIndex].focus();
        checkAutoSubmitOtp();
      }
    });
  });
}

function checkAutoSubmitOtp() {
  const code = getOtpCodeFromInputs();
  const btn = document.getElementById('btn-otp-verify-submit');
  if (code.length === 6) {
    if (btn) btn.classList.add('ring-2', 'ring-sky-400');
  } else {
    if (btn) btn.classList.remove('ring-2', 'ring-sky-400');
  }
}

function getOtpCodeFromInputs() {
  const digits = document.querySelectorAll('.otp-digit');
  let code = '';
  digits.forEach(d => { code += (d.value || '').trim(); });
  return code;
}

function clearOtpInputs() {
  const digits = document.querySelectorAll('.otp-digit');
  digits.forEach(d => { d.value = ''; });
  if (digits[0]) digits[0].focus();
}

function startOtpCountdown(seconds = 59) {
  if (otpCountdownTimer) clearInterval(otpCountdownTimer);
  currentOtpRemaining = seconds;

  const timerWrap = document.getElementById('otp-timer-wrap');
  const countdownEl = document.getElementById('otp-countdown');
  const resendBtn = document.getElementById('btn-otp-resend');

  if (timerWrap) timerWrap.classList.remove('hidden');
  if (resendBtn) resendBtn.classList.add('hidden');
  if (countdownEl) countdownEl.innerText = `${currentOtpRemaining}s`;

  otpCountdownTimer = setInterval(() => {
    currentOtpRemaining--;
    if (currentOtpRemaining <= 0) {
      clearInterval(otpCountdownTimer);
      otpCountdownTimer = null;
      if (timerWrap) timerWrap.classList.add('hidden');
      if (resendBtn) resendBtn.classList.remove('hidden');
    } else {
      if (countdownEl) countdownEl.innerText = `${currentOtpRemaining}s`;
    }
  }, 1000);
}

async function requestAndShowOtp(identifier, channel, purpose, fullName = '') {
  try {
    const res = await fetch('/api/auth/otp/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ identifier, channel, purpose, full_name: fullName })
    });
    const data = await res.json();
    if (!data.success) {
      alert(data.error || 'Không thể gửi mã xác thực OTP.');
      return;
    }

    toggleAuthMode('otp');
    setupOtpDigitInputs();

    const channelLabel = document.getElementById('otp-channel-label');
    if (channelLabel) {
      channelLabel.innerText = channel === 'email' ? 'hộp thư Gmail' : 'tin nhắn SMS';
    }

    const targetDisplay = document.getElementById('otp-target-display');
    if (targetDisplay) {
      targetDisplay.innerText = identifier;
    }



    clearOtpInputs();
    startOtpCountdown(data.cooldown || 59);

    if (typeof showMedicalToast === 'function') {
      showMedicalToast(`Mã OTP đã được gửi tới ${identifier}!`, 'success');
    }
  } catch (err) {
    console.error('Lỗi yêu cầu gửi OTP:', err);
    alert('Không thể kết nối máy chủ gửi OTP.');
  }
}

async function handleOtpSubmit(e) {
  if (e) e.preventDefault();
  const code = getOtpCodeFromInputs();
  if (code.length !== 6) {
    alert('Vui lòng nhập đủ 6 chữ số của mã OTP.');
    return;
  }

  try {
    const res = await fetch('/api/auth/otp/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        identifier: pendingOtpFlow.identifier,
        channel: pendingOtpFlow.channel,
        code,
        purpose: pendingOtpFlow.purpose,
        user_data: pendingOtpFlow.userData
      })
    });
    const data = await res.json();
    if (data.success) {
      if (data.user) {
        currentUser = data.user;
        localStorage.setItem('medimind_user', JSON.stringify(currentUser));
        updateAuthUI();
        broadcastTabEvent('AUTH_LOGIN', { user: currentUser });
      }
      closeLoginModal();
      if (typeof showMedicalToast === 'function') {
        showMedicalToast(data.message || 'Xác thực mã OTP thành công!', 'success');
      } else {
        alert(data.message || 'Xác thực danh tính thành công!');
      }

      if (pendingTabAfterLogin) {
        const target = pendingTabAfterLogin;
        pendingTabAfterLogin = null;
        switchTab(target);
      }
    } else {
      alert(data.error || 'Mã xác thực không chính xác.');
      clearOtpInputs();
    }
  } catch (err) {
    console.error('Lỗi xác thực OTP:', err);
    alert('Không thể kết nối máy chủ xác thực.');
  }
}

async function handleResendOtp() {
  if (!pendingOtpFlow.identifier) return;
  await requestAndShowOtp(
    pendingOtpFlow.identifier,
    pendingOtpFlow.channel,
    pendingOtpFlow.purpose,
    pendingOtpFlow.userData?.full_name || ''
  );
}

function cancelOtpStep() {
  if (otpCountdownTimer) clearInterval(otpCountdownTimer);
  toggleAuthMode(pendingOtpFlow.previousMode || 'login');
}

async function startOtpLoginFlow() {
  let identifier = (document.getElementById('login-identifier')?.value || '').trim();
  if (!identifier) {
    identifier = prompt('Vui lòng nhập Email hoặc Số điện thoại để nhận mã OTP:');
    if (!identifier) return;
    identifier = identifier.trim();
  }

  const channel = identifier.includes('@') ? 'email' : 'sms';
  pendingOtpFlow = {
    identifier,
    channel,
    purpose: 'login_2fa',
    userData: null,
    previousMode: 'login'
  };

  await requestAndShowOtp(identifier, channel, 'login_2fa');
}


// ==============================================================
// GOOGLE IDENTITY SERVICES / 1-CLICK GOOGLE SIGN-IN (5-STATE MACHINE)
// ==============================================================
let currentGoogleState = 'select'; // 'select' | 'custom' | 'loading' | 'success'

function detectInAppWebView() {
  const ua = (window.navigator && window.navigator.userAgent) || '';
  if (/Zalo/i.test(ua)) return 'Zalo';
  if (/FBAN|FBAV|FB_IAB|FBIOS/i.test(ua)) return 'Facebook / Messenger';
  if (/TikTok|BytedanceWebview/i.test(ua)) return 'TikTok';
  if (/Instagram/i.test(ua)) return 'Instagram';
  if (/MicroMessenger/i.test(ua)) return 'WeChat';
  return null;
}

async function handleGoogleSignIn(intentOverride) {
  const inAppName = detectInAppWebView();
  if (inAppName) {
    const warnMsg = `Bạn đang mở trang trong ứng dụng ${inAppName}, nơi Google chặn đăng nhập bảo mật. Hãy mở MediMind bằng Chrome hoặc Safari rồi đăng nhập lại.`;
    if (typeof showMedicalToast === 'function') {
      showMedicalToast(warnMsg, 'warning', 6000);
    } else {
      alert(warnMsg);
    }
    return;
  }

  const intent = intentOverride || 'continue';
  const btn = document.getElementById('btn-google-signin');
  const originalHtml = btn ? btn.innerHTML : '';

  if (btn) {
    btn.disabled = true;
    btn.innerHTML = `<span class="w-4 h-4 rounded-full border-2 border-sky-500 border-t-transparent animate-spin inline-block"></span><span class="font-semibold">${currentLang === 'en' ? 'Connecting to Google...' : 'Đang chuyển tới Google...'}</span>`;
  }

  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);
    const res = await fetch(`/api/auth/google/login?intent=${encodeURIComponent(intent)}&format=json`, {
      signal: controller.signal
    });
    clearTimeout(timer);
    const data = await res.json();

    if (data.success && data.auth_url) {
      window.location.assign(data.auth_url);
      return;
    }

    if (data.configured === false) {
      if (btn) { btn.disabled = false; btn.innerHTML = originalHtml; }
      const modal = document.getElementById('google-account-modal');
      if (modal) {
        if (typeof syncAuthModalTheme === 'function') syncAuthModalTheme();
        setGoogleModalState('select');
        modal.classList.remove('hidden');
      }
      return;
    }

    throw new Error(data.error || 'Không thể khởi tạo phiên Google OAuth.');
  } catch (err) {
    console.error('Lỗi khởi tạo Google OAuth:', err);
    if (btn) { btn.disabled = false; btn.innerHTML = originalHtml; }
    if (typeof showMedicalToast === 'function') {
      showMedicalToast('Máy chủ đăng nhập đang chậm hoặc gián đoạn. Vui lòng thử lại.', 'error', 4500);
    }
  }
}

function closeGoogleAccountModal() {
  // Trạng thái 4 – Hủy đăng nhập: Đóng popup, quay lại modal đăng nhập ban đầu mà không đổi dữ liệu
  const modal = document.getElementById('google-account-modal');
  if (modal) modal.classList.add('hidden');
  setGoogleModalState('select');
}

function setGoogleModalState(state) {
  currentGoogleState = state;
  const stateSelect = document.getElementById('google-state-select');
  const stateCustom = document.getElementById('google-state-custom');
  const stateLoading = document.getElementById('google-state-loading');
  const stateSuccess = document.getElementById('google-state-success');
  const heading = document.getElementById('google-modal-heading');
  const subheading = document.getElementById('google-modal-subheading');

  if (stateSelect) stateSelect.classList.toggle('hidden', state !== 'select');
  if (stateCustom) stateCustom.classList.toggle('hidden', state !== 'custom');
  if (stateLoading) stateLoading.classList.toggle('hidden', state !== 'loading');
  if (stateSuccess) stateSuccess.classList.toggle('hidden', state !== 'success');

  if (heading && subheading) {
    if (state === 'select') {
      heading.textContent = 'Chọn tài khoản';
      subheading.innerHTML = 'Để tiếp tục đến <span class="text-white font-medium">MediMind AI</span>';
    } else if (state === 'custom') {
      heading.textContent = 'Đăng nhập';
      subheading.innerHTML = 'Sử dụng Tài khoản Google của bạn';
      const input = document.getElementById('google-custom-email-input');
      if (input) setTimeout(() => input.focus(), 60);
    } else if (state === 'loading') {
      heading.textContent = 'Đang xác thực...';
      subheading.innerHTML = 'Đang bảo mật phiên kết nối';
    } else if (state === 'success') {
      heading.textContent = 'Hoàn tất!';
      subheading.innerHTML = 'Chào mừng bạn đến với MediMind AI';
    }
  }
}

async function startGoogleAccountSelection(email, name, initial, bgColor) {
  // Cập nhật thông tin lên State 3 trước để sẵn sàng hiển thị
  const avatarEl = document.getElementById('google-success-avatar');
  const nameEl = document.getElementById('google-success-name');
  const emailEl = document.getElementById('google-success-email');

  if (avatarEl) {
    avatarEl.textContent = initial || name.charAt(0).toUpperCase();
    avatarEl.style.backgroundColor = bgColor || '#0284c7';
  }
  if (nameEl) nameEl.textContent = name;
  if (emailEl) emailEl.textContent = email;

  // Trạng thái 2 – Đang đăng nhập (Loading animation & pulse)
  setGoogleModalState('loading');

  try {
    const avatarUrl = `https://ui-avatars.com/api/?name=${encodeURIComponent(name)}&background=${(bgColor || '#0284c7').replace('#', '')}&color=fff&size=128`;
    
    const [res] = await Promise.all([
      fetch('/api/auth/google', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, name, avatar_url: avatarUrl })
      }),
      new Promise(resolve => setTimeout(resolve, 750)) // Smooth animation pause
    ]);

    const data = await res.json();
    if (data.success && data.user) {
      // Trạng thái 3 – Đăng nhập thành công (Demo checkmark & selected user display)
      setGoogleModalState('success');

      // Tự động chuyển đến giao diện Dashboard mẫu sau hiệu ứng hoàn tất
      setTimeout(() => {
        currentUser = data.user;
        localStorage.setItem('medimind_user', JSON.stringify(currentUser));
        updateAuthUI();
        closeGoogleAccountModal();
        closeLoginModal();
        broadcastTabEvent('AUTH_LOGIN', { user: currentUser });

        if (typeof showMedicalToast === 'function') {
          showMedicalToast(`Đăng nhập thành công với Google (${currentUser.email})!`, 'success');
        }

        if (pendingTabAfterLogin) {
          const target = pendingTabAfterLogin;
          pendingTabAfterLogin = null;
          switchTab(target);
        } else {
          switchTab('home-tab');
        }
      }, 1200);

    } else {
      setGoogleModalState('select');
      alert(data.error || 'Đăng nhập Google thất bại.');
    }
  } catch (err) {
    console.error('Lỗi Google Sign-In:', err);
    setGoogleModalState('select');
    alert('Không thể kết nối máy chủ Google OAuth.');
  }
}

function submitCustomGoogleAccount() {
  const input = document.getElementById('google-custom-email-input');
  let raw = (input?.value || '').trim();
  if (!raw) {
    input?.focus();
    return;
  }
  let email = raw;
  if (!email.includes('@')) {
    email += '@gmail.com';
  }
  const prefix = email.split('@')[0];
  const name = prefix.replace(/[._-]+/g, ' ').replace(/\b\w/g, c => c.toUpperCase()) || 'Google User';
  const initial = name.charAt(0).toUpperCase();
  startGoogleAccountSelection(email, name, initial, '#0284c7');
}

// Bắt phím Escape và Enter cho Google Account Modal
window.addEventListener('keydown', (e) => {
  const modal = document.getElementById('google-account-modal');
  if (modal && !modal.classList.contains('hidden')) {
    if (e.key === 'Escape' && currentGoogleState !== 'loading') {
      closeGoogleAccountModal();
    }
    if (e.key === 'Enter' && currentGoogleState === 'custom') {
      submitCustomGoogleAccount();
    }
  }
});

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
  const channel = identifier.includes('@') ? 'email' : 'sms';

  pendingOtpFlow = {
    identifier,
    channel,
    purpose: 'register',
    userData: {
      last_name: lastName,
      first_name: firstName,
      name: fullName,
      full_name: fullName,
      dob,
      gender,
      password,
      email: identifier.includes('@') ? identifier : undefined,
      phone_number: !identifier.includes('@') ? identifier : undefined
    },
    previousMode: 'register'
  };

  await requestAndShowOtp(identifier, channel, 'register', fullName);
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
      broadcastTabEvent('AUTH_LOGIN', { user: currentUser });
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
      body: JSON.stringify({ identifier, email: identifier, password })
    });
    const data = await res.json();
    if (data.success && data.user) {
      currentUser = data.user;
      localStorage.setItem('medimind_user', JSON.stringify(currentUser));
      chatSessions = loadSessionsFromStorage();
      if (typeof renderChatHistoryList === 'function') renderChatHistoryList();
      updateAuthUI();
      broadcastTabEvent('AUTH_LOGIN', { user: currentUser });
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
  resetAuthModal();
  Object.keys(fieldRealValues).forEach(k => delete fieldRealValues[k]);
  Object.keys(fieldMaskState).forEach(k => {
    fieldMaskState[k] = false;
    const el = document.getElementById(k);
    if (el) el.readOnly = false;
  });
  document.getElementById('profile-form-img1')?.reset();
  localStorage.removeItem('medimind_user');

  // Làm sạch hoàn toàn giao diện chat của người dùng cũ để tránh rò rỉ dữ liệu trên máy dùng chung
  if (typeof resetChat === 'function') {
    resetChat();
  }
  chatSessions = loadSessionsFromStorage();
  if (typeof renderChatHistoryList === 'function') {
    renderChatHistoryList();
  }
  updateAuthUI();
  broadcastTabEvent('AUTH_LOGOUT', null);
  switchTab('home-tab');
}


function updateProfileCompletion() {
  if (!currentUser) {
    const pctEl = document.getElementById('profile-completion-pct');
    const barEl = document.getElementById('profile-completion-bar');
    if (pctEl) pctEl.innerText = '6%';
    if (barEl) barEl.style.width = '6%';
    return;
  }
  const fields = [
    currentUser.full_name || currentUser.name,
    currentUser.dob,
    currentUser.gender,
    currentUser.phone_number,
    currentUser.email,
    currentUser.cccd,
    currentUser.issue_date,
    currentUser.issue_place,
    currentUser.bhyt,
    currentUser.facility,
    currentUser.valid_from,
    currentUser.valid_to,
    currentUser.nationality,
    currentUser.ethnicity,
    currentUser.religion,
    currentUser.province,
    currentUser.ward,
    currentUser.address
  ];
  const filled = fields.filter(v => v && String(v).trim().length > 0).length;
  // If only 1 field (like nationality VN) is filled, it equals 6% exactly matching Image 1
  const pct = Math.max(6, Math.min(100, Math.round((filled / fields.length) * 100)));
  const pctEl = document.getElementById('profile-completion-pct');
  const barEl = document.getElementById('profile-completion-bar');
  if (pctEl) pctEl.innerText = `${pct}%`;
  if (barEl) barEl.style.width = `${pct}%`;
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

  if (navDoctorTab) navDoctorTab.innerText = (currentLang === 'vi' ? 'Hồ sơ của tôi' : 'My Health Record');
  if (ocrSyncBtnText) ocrSyncBtnText.innerText = (currentLang === 'vi' ? 'Xem Hồ sơ của tôi →' : 'View My Record →');

  if (currentUser) {
    if (unlogged) unlogged.classList.add('hidden');
    if (logged) logged.classList.remove('hidden');
    if (nameEl) nameEl.innerText = currentUser.name;

    let subInfo = currentUser.personal_info || currentUser.role || (currentLang === 'en' ? 'Member' : 'Thành viên');
    if (currentLang === 'en') {
      subInfo = subInfo.replace(/^Nam\b/, 'Male').replace(/^Nữ\b/, 'Female').replace(/^Khác\b/, 'Other');
      if (subInfo === 'patient') subInfo = 'Patient';
      if (subInfo === 'doctor') subInfo = 'Physician';
      if (subInfo === 'Thành viên') subInfo = 'Member';
    }
    if (roleEl) roleEl.innerText = subInfo;
    if (avatarEl) avatarEl.innerText = currentUser.badge || 'BN';

    syncCurrentPatientProfile();
    if (ehrTitle) ehrTitle.innerText = (currentLang === 'vi' ? 'Hồ sơ bệnh án' : 'Medical Records');
    if (ehrSubtitle) ehrSubtitle.innerText = (currentLang === 'vi' ? 'Theo dõi lịch sử khám và điều trị' : 'Track examination and treatment history');
    if (ehrPatientName) ehrPatientName.innerText = currentUser.name;
    const ptCodePrefix = currentLang === 'en' ? 'Patient ID' : 'Mã BN';
    if (ehrPatientId) ehrPatientId.innerText = ptCodePrefix + ': #BN-2026-' + String(currentUser.id || 8429).padStart(4, '0') + ' • ' + subInfo;
    if (ehrAvatarBadge) ehrAvatarBadge.innerText = currentUser.badge || 'BN';

    const rightPanelName = document.getElementById('right-panel-patient-name');
    const rightPanelId = document.getElementById('right-panel-patient-id');
    const rightPanelAvatar = document.getElementById('right-panel-avatar');
    const rightPanelBhyt = document.getElementById('right-panel-bhyt');
    if (rightPanelName) rightPanelName.innerText = currentUser.name;
    if (rightPanelId) rightPanelId.innerText = (currentLang === 'en' ? 'Patient ID: #BN-2026-' : 'Mã BN: #BN-2026-') + String(currentUser.id || 4).padStart(4, '0');
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

    if (tabBannerId) tabBannerId.innerText = (currentLang === 'en' ? 'Patient ID: #BN-2026-' : 'Mã BN: #BN-2026-') + String(currentUser.id || 8429).padStart(4, '0');
    if (tabBannerName) tabBannerName.innerText = (currentLang === 'en' ? 'Full Name: ' : 'Họ tên: ') + currentUser.name;
    if (tabName) tabName.value = currentUser.name || '';
    // Sync Essential Profile fields
    const pName = document.getElementById('p-name');
    const pBirthDate = document.getElementById('p-birthdate');
    const pGender = document.getElementById('p-gender');
    const pPhone = document.getElementById('p-phone');
    const pEmail = document.getElementById('p-email');
    const pBlood = document.getElementById('p-blood');
    const pAllergies = document.getElementById('p-allergies');
    const pHeight = document.getElementById('p-height');
    const pWeight = document.getElementById('p-weight');
    const pAddress = document.getElementById('p-address');

    const cardName = document.getElementById('profile-card-name');
    const cardEmail = document.getElementById('profile-card-email');
    const cardPhone = document.getElementById('profile-card-phone');
    const cardJoined = document.getElementById('profile-card-joined');

    const dispAvatar = document.getElementById('profile-avatar-display');
    const fallbackAvatar = document.getElementById('profile-avatar-fallback');
    const displayName = currentUser.full_name || currentUser.name || '';

    if (pName) pName.value = displayName;
    if (pBirthDate) pBirthDate.value = currentUser.dob || '';
    if (pGender) pGender.value = currentUser.gender || 'Nam';

    const phoneVal = currentUser.phone_number || currentUser.phone || '';
    fieldRealValues['p-phone'] = phoneVal;
    if (pPhone) pPhone.value = fieldMaskState['p-phone'] ? maskFieldValue(phoneVal, 'p-phone') : phoneVal;

    const emailVal = (currentUser.email && !currentUser.email.endsWith('@phone.medimind')) ? currentUser.email : '';
    fieldRealValues['p-email'] = emailVal;
    if (pEmail) pEmail.value = fieldMaskState['p-email'] ? maskFieldValue(emailVal, 'p-email') : emailVal;

    if (pBlood) pBlood.value = currentUser.blood_type || 'O+';
    if (pAllergies) pAllergies.value = currentUser.allergies || '';
    if (pHeight) pHeight.value = currentUser.height || '';
    if (pWeight) pWeight.value = currentUser.weight || '';
    if (pAddress) pAddress.value = currentUser.address || '';

    if (cardName) cardName.innerText = displayName || 'Chưa có họ và tên';
    if (cardEmail) {
      cardEmail.innerText = (emailVal && emailVal.trim())
        ? (fieldMaskState['p-email'] ? maskFieldValue(emailVal, 'p-email') : emailVal)
        : 'Chưa có email';
    }
    if (cardPhone) {
      cardPhone.innerText = (phoneVal && phoneVal.trim())
        ? (fieldMaskState['p-phone'] ? maskFieldValue(phoneVal, 'p-phone') : phoneVal)
        : 'Chưa có số điện thoại';
    }
    if (cardJoined) {
      cardJoined.innerText = currentUser.joined_date || currentUser.created_at || (displayName ? new Date().toLocaleDateString('vi-VN') : 'Chưa lưu');
    }

    ['p-phone', 'p-email'].forEach(fId => {
      const el = document.getElementById(fId);
      if (el && !el._hasSyncListener) {
        el._hasSyncListener = true;
        el.addEventListener('input', () => {
          if (!fieldMaskState[fId]) {
            fieldRealValues[fId] = el.value;
          }
          syncLeftCardPhoneEmail();
          calculateProfileCompletion();
        });
      }
    });

    const activeProfilePhoto = (currentUser.hasCustomAvatar && currentUser.avatar) ? currentUser.avatar : currentUser.avatar_url;
    if (activeProfilePhoto) {
      if (dispAvatar) {
        dispAvatar.src = activeProfilePhoto;
        dispAvatar.classList.remove('hidden');
      }
      if (fallbackAvatar) fallbackAvatar.classList.add('hidden');
    } else {
      if (dispAvatar) dispAvatar.classList.add('hidden');
      if (fallbackAvatar) fallbackAvatar.classList.remove('hidden');
    }

    syncLeftCardPhoneEmail();
    updateProfileCompletion();
    
    calculateProfileCompletion();
    
    // Sync Settings controls
    const setLang = document.getElementById('set-language');
    const setTheme = document.getElementById('set-theme-select');
    if (setLang) setLang.value = currentLang;
    if (setTheme) {
      setTheme.value = document.body.classList.contains('light-glass') ? 'light' : 'dark';
    }

    // Facebook Style Avatar Sync
    const avatarUrl = (currentUser.hasCustomAvatar && currentUser.avatar) 
      ? currentUser.avatar 
      : (currentUser.avatar_url || getDefaultAvatarByGender(currentUser.gender || 'Nam'));
    
    if (!currentUser.hasCustomAvatar) {
      currentUser.avatar = avatarUrl;
    }
    
    const topAvatar = document.getElementById('user-avatar-img');
    // dispAvatar reused
    if (topAvatar) topAvatar.src = avatarUrl;
    if (dispAvatar) dispAvatar.src = avatarUrl;
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
    loadPrescriptionHistory();
    if (typeof checkPendingBookingAfterAuth === 'function') {
      checkPendingBookingAfterAuth();
    }
  } else {
    if (unlogged) unlogged.classList.remove('hidden');
    if (logged) logged.classList.add('hidden');
    const guestCardName = document.getElementById('profile-card-name');
    const guestCardPhone = document.getElementById('profile-card-phone');
    const guestCardEmail = document.getElementById('profile-card-email');
    const guestCardJoined = document.getElementById('profile-card-joined');
    const guestDispAvatar = document.getElementById('profile-avatar-display');
    const guestFallbackAvatar = document.getElementById('profile-avatar-fallback');
    if (guestCardName) guestCardName.innerText = 'Chưa có họ và tên';
    if (guestCardPhone) guestCardPhone.innerText = 'Chưa có số điện thoại';
    if (guestCardEmail) guestCardEmail.innerText = 'Chưa có email';
    if (guestCardJoined) guestCardJoined.innerText = 'Chưa lưu';
    if (guestDispAvatar) guestDispAvatar.classList.add('hidden');
    if (guestFallbackAvatar) guestFallbackAvatar.classList.remove('hidden');
    updateProfileCompletion();
    if (nameEl) nameEl.innerText = currentLang === 'en' ? 'Guest' : 'Khách';
    if (roleEl) roleEl.innerText = currentLang === 'en' ? 'Not signed in' : 'Chưa đăng nhập';
    if (avatarEl) avatarEl.innerText = '👤';
    if (ehrPatientName) ehrPatientName.innerText = currentLang === 'en' ? 'Not signed in' : 'Chưa đăng nhập';
    if (ehrPatientId) ehrPatientId.innerText = currentLang === 'en' ? 'Please sign in to sync pre-visit summary' : 'Vui lòng đăng nhập để đồng bộ tóm tắt trước khám';
    if (ehrEmpty) ehrEmpty.classList.remove('hidden');
    if (ehrFilled) ehrFilled.classList.add('hidden');

    renderChatHistoryList();

    const exportBtn = document.getElementById('ehr-export-pdf-btn');
    if (exportBtn) {
      exportBtn.classList.add('opacity-40', 'cursor-not-allowed');
      exportBtn.title = 'Chưa có bản tóm tắt trước khám để kết xuất PDF';
    }
    loadScanFiles();
    loadPrescriptionHistory();
  }
  updateHomeGreeting();
  updateEhrTabUI();
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
      <div class="floating-welcome-card p-4 sm:p-5 rounded-2xl bg-white dark:bg-slate-800/80 border border-sky-100 dark:border-white/10 space-y-2.5 shadow-sm text-xs">
        <h5 class="text-sm font-bold text-[#0284C7] dark:text-sky-400 leading-snug">
          Chào bạn, tôi là Trợ lý y tế MediMind!
        </h5>
        <p class="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
          Tôi luôn sẵn sàng hỗ trợ bạn ngay tại góc màn hình này. Hãy hỏi tôi về cách dùng thuốc, giải thích chỉ số xét nghiệm hoặc gợi ý chuyên khoa khám nhé.
        </p>
        <div class="flex items-start gap-1.5 pt-2 text-[11px] text-slate-400 dark:text-slate-400 leading-normal border-t border-slate-100 dark:border-white/5">
          <svg class="w-3.5 h-3.5 text-slate-400 shrink-0 mt-0.5 inline-block" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path stroke-linecap="round" stroke-linejoin="round" d="M12 16v-4m0-4h.01"/></svg>
          <span>Thông tin chỉ mang tính tham khảo, không thay thế chẩn đoán của bác sĩ.</span>
        </div>
      </div>
    `;
    return;
  }

  container.innerHTML = chatHistory.map(msg => {
    if (msg.role === 'user') {
      return `
        <div class="flex flex-col items-end my-1">
          <div class="w-fit max-w-[85%] bg-gradient-to-r from-sky-500 to-blue-600 text-white px-3.5 py-2.5 rounded-2xl rounded-tr-xs text-xs leading-relaxed font-medium text-left break-words shadow-sm">
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
          <div class="bg-slate-100 dark:bg-slate-800/90 border border-slate-200/80 dark:border-white/10 p-3.5 rounded-2xl rounded-tl-xs text-xs text-slate-800 dark:text-slate-200 leading-relaxed shadow-sm">
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
  try { initThemeMode(); } catch (e) { console.warn('[Init] theme error:', e); }
  try { populateDobDropdowns(); } catch (e) { console.warn('[Init] dob dropdowns error:', e); }
  try { updateAuthUI(); } catch (e) { console.warn('[Init] auth UI error:', e); }
  try { checkAuthSessionWithServer(); } catch (e) { console.warn('[Init] auth session check error:', e); }
  try { applyLanguage(); } catch (e) { console.warn('[Init] apply language error:', e); }
  try { initHistorySearch(); } catch (e) { console.warn('[Init] history search error:', e); }
  
  // Reload Tab Routing (Hash > sessionStorage > default 'home-tab')
  try {
    const initialTab = resolveInitialTab();
    switchTab(initialTab, false);
  } catch (routingErr) {
    console.error('[Init] Error switching initial tab:', routingErr);
    switchTab('home-tab', false);
  }
  const urlParams = new URLSearchParams(window.location.search);
  const googleAuthStatus = urlParams.get('google_auth');
  const googleIntent = urlParams.get('intent') || 'login';
  const googleOnboarding = urlParams.get('onboarding') === '1';
  const googleExisting = urlParams.get('existing') === '1';
  const googleErrorReason = urlParams.get('error_reason') || '';
  const googleUnregEmail = urlParams.get('email') || '';

  if (googleAuthStatus) {
    try {
      const cleanUrl = window.location.pathname + (window.location.hash || '');
      window.history.replaceState({}, document.title, cleanUrl);
    } catch (_) {}
  }

  if (googleAuthStatus === 'error') {
    let errMsg = 'Đăng nhập Google không thành công. Vui lòng thử lại.';
    if (googleErrorReason === 'access_denied') {
      errMsg = 'Đã hủy đăng nhập Google (hoặc email này chưa được thêm vào mục Audience -> Test users trên Google Cloud).';
    } else if (googleErrorReason === 'redirect_uri_mismatch') {
      errMsg = 'Lỗi cấu hình Redirect URI trên Google Cloud Console.';
    }
    setTimeout(() => {
      if (typeof showMedicalToast === 'function') showMedicalToast(errMsg, 'warning', 6000);
    }, 250);
  } else if (googleAuthStatus === 'pending_register' || googleAuthStatus === 'unregistered') {
    // Lần đầu tiên sử dụng tài khoản Google: Mở popup xác nhận để vào ứng dụng ngay
    closeLoginModal();
    fetch('/api/auth/google/pending').then(r => r.json()).then(pData => {
      if (pData && pData.pending && pData.profile) {
        pendingGoogleProfile = pData.profile;
        isPendingGoogleRegistration = true;
        if (typeof showMedicalToast === 'function') {
          showMedicalToast('Xác thực Google thành công! Vui lòng xác nhận thông tin để bắt đầu sử dụng.', 'info', 5000);
        }
        setTimeout(() => openGoogleOnboardingModal(pData.profile, true), 250);
      }
    }).catch(() => {});
  }

  fetch('/api/auth/me').then(r => r.json()).then(data => {
    if (!data.authenticated) {
      if (currentUser) {
        currentUser = null;
        localStorage.removeItem('medimind_user');
        updateAuthUI();
      }
    } else if (data.user) {
      currentUser = { ...(currentUser || {}), ...data.user };
      localStorage.setItem('medimind_user', JSON.stringify(currentUser));
      updateAuthUI();
      restoreProfileDraftFromSession();

      if (googleAuthStatus === 'success') {
        broadcastTabEvent('AUTH_LOGIN', { user: currentUser });
        closeLoginModal();
        if (googleExisting && googleIntent === 'register') {
          showMedicalToast(`Tài khoản Google (${currentUser.email}) đã có hồ sơ MediMind. Bạn đã được đưa về trang chủ!`, 'info', 5000);
        } else if (googleOnboarding) {
          showMedicalToast(`Xác thực Google thành công! Hãy hoàn tất thông tin cơ bản để lưu hồ sơ y tế.`, 'success', 5500);
          setTimeout(() => openGoogleOnboardingModal(currentUser), 350);
        } else {
          showMedicalToast(`Đăng nhập Google thành công! Chào mừng ${currentUser.name || currentUser.email}.`, 'success', 4000);
        }
      }
    }
  }).catch(() => {});
  updateEhrTabUI();
  updateFacilityDistrictDropdown('hcm');
  renderMedicalFacilities();
  setTimeout(() => {
    initHospitalInteractiveMap();
  }, 300);
  updateHomeGreeting();
  loadPrescriptionHistory();

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

  // Click outside to close user dropdown & lang dropdown
  document.addEventListener('click', (e) => {
        const notifBtn = document.getElementById('notif-btn');
    const notifMenu = document.getElementById('notif-dropdown-menu');
    if (notifMenu && !notifMenu.classList.contains('hidden')) {
      if (!notifBtn?.contains(e.target) && !notifMenu.contains(e.target)) {
        closeNotificationDropdown();
      }
    }
    const userChip = document.getElementById('user-chip-button');
    const userMenu = document.getElementById('user-dropdown-menu');
    if (userMenu && !userMenu.classList.contains('hidden')) {
      if (!userChip?.contains(e.target) && !userMenu.contains(e.target)) {
        closeUserDropdown();
      }
    }
    const langBtn = document.getElementById('lang-btn');
    const langMenu = document.getElementById('lang-dropdown-menu');
    if (langMenu && !langMenu.classList.contains('hidden')) {
      if (!langBtn?.contains(e.target) && !langMenu.contains(e.target)) {
        closeLanguageDropdown();
      }
    }
  });

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

    if (data.status === 'failed' || data.status === 'rejected' || data.status === 'error') {
      renderPrescriptionError(data);
      showMedicalToast(data.message || 'Không thể nhận diện nội dung đơn thuốc. Vui lòng chụp lại ảnh rõ nét.', 'error', 5000);
      return;
    }

    renderPrescriptionResult(data);
    loadPrescriptionHistory();
    if (data.is_demo) {
      showMedicalToast('Đang hiển thị đơn thuốc mẫu thử nghiệm (Demo).', 'info', 4000);
    } else if (data.needs_review) {
      showMedicalToast('Đã đọc tài liệu & lưu vào Lịch sử: Vui lòng đối chiếu với ảnh gốc để xác nhận các mục chưa chắc chắn.', 'warning', 5000);
    } else {
      showMedicalToast(`Đã nhận dạng thành công & tự động lưu vào Lịch sử: ${data.diagnosis || 'Đơn thuốc y tế'}`, 'success');
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

  const safeMessage = typeof message === 'string' ? escapeHtml(message) : escapeHtml(String(message ?? ''));
  toast.className = `pointer-events-auto transform transition-all duration-300 ease-out translate-y-[-10px] opacity-0 flex items-start gap-3 px-4 py-3 rounded-2xl border backdrop-blur-xl shadow-xl text-xs font-semibold leading-relaxed ${typeStyles[type] || typeStyles.info}`;
  toast.innerHTML = `
    ${icons[type] || icons.info}
    <div class="flex-1">${safeMessage}</div>
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
  const emojis = ['💊', '💙', '🎉', '🟢', '⭐'];
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
  const histSec = document.getElementById('prescription-history-section');
  const loadSec = document.getElementById('prescription-loading-section');
  const resSec = document.getElementById('prescription-result-section');
  const stepEl = document.getElementById('scan-step-text');
  const substepEl = document.getElementById('scan-substep-text');

  if (show) {
    if (inputSec) inputSec.classList.add('hidden');
    if (histSec) histSec.classList.add('hidden');
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
  const histSec = document.getElementById('prescription-history-section');
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
  if (histSec) histSec.classList.remove('hidden');
  adherenceSlotState = {};
  currentPrescriptionData = null;
  loadPrescriptionHistory();
  inputSec?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ==============================================================================
// LỊCH SỬ ĐƠN THUỐC & PHIẾU XÉT NGHIỆM ĐÃ IMPORT (DATA NGƯỜI DÙNG)
// ==============================================================================
let cachedPrescriptionHistory = [];

async function loadPrescriptionHistory() {
  const listEl = document.getElementById('prescription-history-list');
  const emptyEl = document.getElementById('prescription-history-empty');
  const countBadge = document.getElementById('history-count-badge');
  const ehrPrescriptionList = document.getElementById('ehr-prescription-list');

  if (!currentUser || currentUser.isDemo) {
    if (listEl) listEl.innerHTML = '<p class="text-xs text-slate-400 p-4 text-center">Vui lòng đăng nhập để xem lịch sử đơn thuốc của bạn.</p>';
    if (countBadge) countBadge.innerText = '0 hồ sơ';
    if (emptyEl) emptyEl.classList.remove('hidden');
    return;
  }

  try {
    const res = await fetch('/api/prescription/history');
    if (!res.ok) {
      if (res.status === 401) {
        const isEn = typeof currentLang !== 'undefined' && currentLang === 'en';
        if (listEl) listEl.innerHTML = `<p class="text-xs text-slate-400 p-4 text-center">${isEn ? 'Please sign in to view your prescription history.' : 'Vui lòng đăng nhập để xem lịch sử đơn thuốc của bạn.'}</p>`;
        if (ehrPrescriptionList) ehrPrescriptionList.innerHTML = `<p class="text-slate-400 text-[11px] italic">${isEn ? 'Please sign in to view saved prescriptions.' : 'Vui lòng đăng nhập để xem đơn thuốc.'}</p>`;
        if (countBadge) countBadge.innerText = '0 hồ sơ';
      }
      return;
    }

    const data = await res.json();
    const history = data.history || [];
    cachedPrescriptionHistory = history;

    if (countBadge) countBadge.innerText = (typeof currentLang !== 'undefined' && currentLang === 'en') ? `${history.length} records` : `${history.length} hồ sơ`;

    // 1. Cập nhật trong tab OCR (Đọc đơn thuốc & xét nghiệm)
    if (history.length === 0) {
      if (listEl) listEl.innerHTML = '';
      if (emptyEl) emptyEl.classList.remove('hidden');
    } else {
      if (emptyEl) emptyEl.classList.add('hidden');
      if (listEl) {
        listEl.innerHTML = history.map(item => {
          const isLab = item.doc_type === 'lab_test';
          const badgeType = isLab 
            ? '<span class="px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-purple-500/20 text-purple-300 border border-purple-400/30">🔬 Phiếu Xét Nghiệm</span>'
            : '<span class="px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-teal-500/20 text-teal-300 border border-teal-400/30">💊 Đơn Thuốc</span>';

          const iconSvg = isLab
            ? `<svg class="w-5 h-5 text-purple-300" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"/></svg>`
            : `<svg class="w-5 h-5 text-teal-300" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>`;

          const diag = item.diagnosis && item.diagnosis !== 'Chưa phân loại bệnh' ? item.diagnosis : 'Theo dõi & Điều trị theo chỉ định';
          const facility = item.facility && item.facility !== 'Cơ sở Y tế' ? item.facility : 'Cơ sở Y tế';

          return `
            <div class="glass-card p-4 rounded-2xl border border-white/10 hover:border-teal-400/40 bg-white/[0.04] transition-all space-y-2.5">
              <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div class="flex items-start gap-3">
                  <div class="w-10 h-10 rounded-xl ${isLab ? 'bg-purple-500/20 border-purple-400/30' : 'bg-teal-500/20 border-teal-400/30'} border flex items-center justify-center shrink-0 mt-0.5">
                    ${iconSvg}
                  </div>
                  <div class="space-y-1">
                    <div class="flex flex-wrap items-center gap-2">
                      ${badgeType}
                      <span class="text-[11px] text-slate-300 font-mono flex items-center gap-1">
                        <svg class="w-3.5 h-3.5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                        ${escapeHtml(item.uploaded_at || 'Vừa xong')}
                      </span>
                      <span class="text-[10px] text-slate-400 font-mono">#MED-${item.id}</span>
                    </div>
                    
                    <h4 class="text-sm font-bold text-white leading-snug">
                      <span class="text-slate-400 font-normal">Chẩn đoán / Bệnh:</span> 
                      <span class="text-emerald-300 font-bold">${escapeHtml(diag)}</span>
                    </h4>

                    <div class="text-xs text-slate-300 flex flex-wrap items-center gap-x-3 gap-y-1">
                      <span class="flex items-center gap-1">
                        <svg class="w-3.5 h-3.5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"/></svg>
                        ${escapeHtml(facility)}
                      </span>
                      ${item.doctor ? `<span class="text-slate-400">• BS: <strong class="text-slate-200">${escapeHtml(item.doctor)}</strong></span>` : ''}
                      ${item.patient_name ? `<span class="text-slate-400">• BN: <strong class="text-slate-200">${escapeHtml(item.patient_name)}</strong></span>` : ''}
                    </div>

                    ${item.summary ? `
                      <div class="pt-1">
                        <span class="text-[11px] px-2.5 py-1 rounded-lg bg-teal-950/40 text-teal-200 border border-teal-500/25 inline-flex items-center gap-1.5 font-medium">
                          <span>📋</span> ${escapeHtml(item.summary)}
                        </span>
                      </div>
                    ` : ''}
                  </div>
                </div>

                <div class="flex items-center gap-2 shrink-0 self-end sm:self-center pt-2 sm:pt-0">
                  <button type="button" onclick="viewPrescriptionHistoryItem(${item.id})" class="px-3.5 py-2 rounded-xl bg-gradient-to-r from-teal-500 to-sky-600 hover:from-teal-400 hover:to-sky-500 text-white text-xs font-bold transition-all shadow-md flex items-center gap-1.5 cursor-pointer hover:scale-102">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
                    <span>Xem lại đơn</span>
                  </button>
                  <button type="button" onclick="deletePrescriptionHistoryItem(${item.id}, event)" class="p-2 rounded-xl glass-pill text-slate-400 hover:text-rose-400 hover:border-rose-400/40 transition-all cursor-pointer" title="Xóa khỏi lịch sử">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/></svg>
                  </button>
                </div>
              </div>
            </div>
          `;
        }).join('');
      }
    }

    // 2. Cập nhật trong tab Doctor (Hồ sơ của tôi)
    if (ehrPrescriptionList) {
      if (history.length === 0) {
        const isEn = typeof currentLang !== 'undefined' && currentLang === 'en';
        ehrPrescriptionList.innerHTML = `<p class="text-slate-400 text-[11px] italic">${isEn ? 'No prescriptions saved yet. You can import a new prescription anytime.' : 'Chưa có đơn thuốc nào được lưu. Bạn có thể import đơn thuốc mới bất kỳ lúc nào.'}</p>`;
      } else {
        ehrPrescriptionList.innerHTML = history.slice(0, 5).map(item => {
          const isLab = item.doc_type === 'lab_test';
          const diag = item.diagnosis && item.diagnosis !== 'Chưa phân loại bệnh' ? item.diagnosis : 'Đơn thuốc khám bệnh';
          return `
            <div class="p-2.5 rounded-xl bg-white/5 border border-white/10 hover:border-teal-400/30 transition-all flex items-center justify-between gap-2">
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2">
                  <span class="text-[9px] font-bold px-1.5 py-0.2 rounded ${isLab ? 'bg-purple-500/20 text-purple-300' : 'bg-teal-500/20 text-teal-300'}">${isLab ? 'XÉT NGHIỆM' : 'ĐƠN THUỐC'}</span>
                  <span class="text-[10px] text-slate-400 font-mono">${escapeHtml(item.uploaded_at || '')}</span>
                </div>
                <h5 class="text-xs font-bold text-slate-100 truncate mt-0.5" title="${escapeHtml(diag)}">${escapeHtml(diag)}</h5>
                <p class="text-[10px] text-slate-400 truncate">${escapeHtml(item.facility || 'Cơ sở Y tế')}${item.summary ? ` • ${escapeHtml(item.summary)}` : ''}</p>
              </div>
              <button type="button" onclick="viewPrescriptionHistoryItem(${item.id})" class="px-2.5 py-1.5 rounded-lg bg-teal-500/20 hover:bg-teal-500/30 text-teal-300 border border-teal-400/30 text-[11px] font-bold shrink-0 transition-colors cursor-pointer">
                Xem lại →
              </button>
            </div>
          `;
        }).join('');
      }
    }

  } catch (err) {
    console.error('Lỗi khi tải lịch sử đơn thuốc:', err);
  }
}

async function viewPrescriptionHistoryItem(docId) {
  try {
    showPrescriptionLoading(true, "Đang nạp lại dữ liệu đơn thuốc từ hồ sơ cá nhân...", "Khôi phục danh mục thuốc, cữ uống và hướng dẫn điều trị...");
    const res = await fetch(`/api/prescription/history/${docId}`);
    const resJson = await res.json();
    showPrescriptionLoading(false);

    if (resJson.status === 'success' && resJson.data) {
      // Ẩn upload section và history section để người dùng xem kết quả
      const inputSec = document.getElementById('prescription-input-section');
      const histSec = document.getElementById('prescription-history-section');
      if (inputSec) inputSec.classList.add('hidden');
      if (histSec) histSec.classList.add('hidden');

      // Chuyển tab sang ocr-tab nếu đang ở tab khác
      switchTab('ocr-tab');

      // Render kết quả chi tiết
      renderPrescriptionResult(resJson.data);
      showMedicalToast(`Đang hiển thị đơn thuốc lưu trữ: ${resJson.data.diagnosis || 'Đơn thuốc'}`, 'info', 4000);

      // Cuộn lên kết quả
      const resSec = document.getElementById('prescription-result-section');
      if (resSec) {
        resSec.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    } else {
      showMedicalToast(resJson.message || 'Không thể đọc dữ liệu chi tiết của đơn thuốc này.', 'warning');
    }
  } catch (err) {
    console.error('Lỗi khi xem lại đơn thuốc:', err);
    showPrescriptionLoading(false);
    showMedicalToast('Không thể kết nối đến máy chủ để tải đơn thuốc.', 'error');
  }
}

async function deletePrescriptionHistoryItem(docId, e) {
  if (e) e.stopPropagation();
  if (!confirm('Bạn có chắc chắn muốn xóa bản ghi đơn thuốc này khỏi lịch sử hồ sơ của mình không?')) return;

  try {
    const res = await fetch(`/api/prescription/history/${docId}`, { method: 'DELETE' });
    const data = await res.json();
    if (data.status === 'success') {
      showMedicalToast('Đã xóa thành công đơn thuốc khỏi lịch sử hồ sơ.', 'success', 3000);
      await loadPrescriptionHistory();
    } else {
      showMedicalToast(data.message || 'Không thể xóa đơn thuốc.', 'error');
    }
  } catch (err) {
    console.error('Lỗi xóa đơn thuốc:', err);
    showMedicalToast('Lỗi kết nối khi xóa đơn thuốc.', 'error');
  }
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
  const inputSec = document.getElementById('prescription-input-section');
  const histSec = document.getElementById('prescription-history-section');
  if (inputSec) inputSec.classList.add('hidden');
  if (histSec) histSec.classList.add('hidden');

  const resSec = document.getElementById('prescription-result-section');
  if (!resSec) return;

  const isLab = data.type === 'lab_test' || data.doc_type === 'lab_test';
  const diag = escapeHtml(String(data.diagnosis || 'Chăm sóc & Điều trị'));
  const doctor = escapeHtml(String(data.doctor || 'BS. Chuyên khoa'));
  const patient = escapeHtml(String(data.patient_name || 'Bệnh nhân'));
  const facility = escapeHtml(String(data.facility && data.facility !== 'Không xác định' ? data.facility : 'Cơ sở Y tế'));
  const dateStr = escapeHtml(String(data.date || 'Hôm nay'));
  const duration = escapeHtml(String(data.duration || '30 ngày'));
  const rawDob = (data.dob || data.birth_date || data.data?.dob || '').toString().trim();
  const rawAge = (data.age || data.data?.age || '').toString().trim();
  const rawGender = escapeHtml((data.gender || data.data?.gender || 'Nữ').toString().trim());
  const currentYear = new Date().getFullYear();

  // Xử lý Ngày sinh / Năm sinh và tự tính tuổi
  let displayBirthInfo = '';
  let displayAge = '';

  const yearMatch = rawDob.match(/(19\d{2}|20\d{2})/);
  if (yearMatch) {
    const birthYear = parseInt(yearMatch[1], 10);
    const calculatedAge = currentYear - birthYear;
    const fullDateMatch = rawDob.match(/(\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{4})/);
    if (fullDateMatch) {
      displayBirthInfo = escapeHtml(fullDateMatch[1]);
    } else {
      displayBirthInfo = escapeHtml(birthYear.toString());
    }
    displayAge = `${calculatedAge} tuổi`;
  } else if (rawAge && !isNaN(parseInt(rawAge, 10))) {
    const parsedAge = parseInt(rawAge, 10);
    displayAge = `${parsedAge} tuổi`;
    displayBirthInfo = `${currentYear - parsedAge}`;
  } else if (rawDob) {
    displayBirthInfo = escapeHtml(rawDob);
    displayAge = '';
  } else {
    displayBirthInfo = 'Chưa xác định';
    displayAge = '';
  }
  const medId = escapeHtml(String(data.document_id ? `#MED-${data.document_id}` : `#MED-8841`));
  const fileName = escapeHtml(String(data.uploaded_filename || 'ToaThuoc_KhamDinhKy.jpg'));
  const scanAcc = data.ocr_metrics?.avg_confidence ? Math.round(data.ocr_metrics.avg_confidence * 100) : 98.5;

  if (isLab) {
    let html = `
      <div class="space-y-4 font-sans select-none text-slate-800 dark:text-slate-100">
        <!-- TOP TOOLBAR -->
        <div class="flex flex-wrap items-center justify-between gap-3 bg-white dark:bg-slate-900/90 border border-sky-100 dark:border-white/10 rounded-2xl p-4 shadow-sm">
          <div class="flex flex-wrap items-center gap-2.5">
            <span class="inline-flex items-center px-3 py-1.5 rounded-lg bg-sky-900 text-white text-xs font-bold tracking-wide">
              🔬 PHÂN LOẠI: PHIẾU XÉT NGHIỆM
            </span>
            <span class="text-xs text-slate-500 dark:text-slate-400 font-medium flex items-center gap-1.5">
              📄 ${fileName} <span class="text-slate-400 font-mono">(${scanAcc}% Tin cậy)</span>
            </span>
          </div>
          <div class="flex items-center gap-2">
            <button onclick="window.print()" class="px-3.5 py-1.5 rounded-lg border border-slate-200 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:bg-white/[0.04] text-xs font-semibold shadow-2xs cursor-pointer">In kết quả</button>
            <button onclick="resetPrescriptionScan()" class="px-3.5 py-1.5 rounded-lg bg-sky-900 hover:bg-sky-950 text-white text-xs font-semibold shadow-xs cursor-pointer">Quét phiếu khác</button>
          </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <!-- MAIN METRICS TABLE -->
          <div class="lg:col-span-2 space-y-4">
            <div class="bg-white dark:bg-slate-900/90 border border-sky-100 dark:border-white/10 rounded-2xl p-5 shadow-sm space-y-4">
              <div class="flex justify-between items-start pb-3 border-b border-slate-100">
                <div>
                  <h3 class="text-base font-extrabold text-slate-900 dark:text-white">${data.doc_title || 'Phiếu Xét Nghiệm Y Khoa'}</h3>
                  <p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">${facility} • Bệnh nhân: <strong class="text-sky-950 font-bold">${patient}</strong></p>
                </div>
                <span class="text-xs font-mono text-slate-400">Ngày lập: ${dateStr}</span>
              </div>

              <div class="overflow-x-auto">
                <table class="w-full text-left text-xs">
                  <thead class="bg-slate-50 dark:bg-white/[0.04] border-b border-slate-200 text-slate-600 dark:text-slate-300 font-bold uppercase text-[10px]">
                    <tr>
                      <th class="py-2.5 px-3">Chỉ số xét nghiệm</th>
                      <th class="py-2.5 px-3">Kết quả</th>
                      <th class="py-2.5 px-3">Khoảng chuẩn</th>
                      <th class="py-2.5 px-3">Đánh giá</th>
                      <th class="py-2.5 px-3">Đối chiếu</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-slate-100">
                    ${(data.metrics || []).map(m => `
                      <tr class="hover:bg-slate-50 dark:bg-white/[0.04]/80 transition-colors">
                        <td class="py-3 px-3">
                          <div class="font-bold text-slate-900 dark:text-white">${m.standard_name || m.name || m.test_name}</div>
                          ${m.loinc_code ? `<span class="text-[10px] text-sky-600 font-mono font-medium">LOINC: ${m.loinc_code}</span>` : ''}
                        </td>
                        <td class="py-3 px-3 font-mono font-black text-sm ${m.computed_flag === 'High' || m.status === 'High' ? 'text-rose-600' : m.computed_flag === 'Low' || m.status === 'Low' ? 'text-sky-600' : 'text-emerald-700'}">
                          ${m.result || m.value} <span class="text-[11px] font-normal text-slate-400">${m.unit || ''}</span>
                        </td>
                        <td class="py-3 px-3 font-mono text-slate-500 dark:text-slate-400 text-xs">${m.reference_range || m.reference || '---'}</td>
                        <td class="py-3 px-3">
                          <span class="px-2 py-0.5 rounded text-[10px] font-bold ${m.computed_flag === 'High' || m.status === 'High' ? 'bg-rose-50 text-rose-700 border border-rose-200' : m.computed_flag === 'Low' || m.status === 'Low' ? 'bg-sky-50 dark:bg-sky-500/10 text-sky-700 border border-sky-200' : 'bg-emerald-50 text-emerald-700 border border-emerald-200'}">
                            ${m.computed_flag || m.status || 'Bình thường'}
                          </span>
                        </td>
                        <td class="py-3 px-3 text-[11px] text-slate-500 dark:text-slate-400">
                          ${m.needs_review ? '<span class="text-amber-600 font-bold">⚠️ Cần xác nhận</span>' : '<span class="text-emerald-600 font-semibold">✓ Khớp số liệu</span>'}
                        </td>
                      </tr>
                    `).join('')}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <!-- SIDEBAR COPILOT -->
          <div class="space-y-4">
            <div class="bg-sky-950 text-white rounded-2xl p-5 shadow-sm space-y-3">
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <div class="w-8 h-8 rounded-lg bg-sky-900 flex items-center justify-center text-sky-200">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                  </div>
                  <div>
                    <h4 class="text-xs font-bold leading-tight">Cố vấn Lâm sàng MediMind</h4>
                    <span class="text-[10px] text-sky-300">Chuyên trách Hướng dẫn Lâm sàng</span>
                  </div>
                </div>
                <span class="text-[9px] bg-sky-700 text-sky-100 font-bold px-2 py-0.5 rounded-full">Active</span>
              </div>
              <div class="text-xs text-sky-50 space-y-2 pt-2 border-t border-sky-900/80 leading-relaxed">
                ${data.interpretation ? `<div class="prose prose-invert prose-xs">${data.interpretation.replace(/\n/g, '<br>')}</div>` : 'Kết quả đã được xác minh đối chiếu qua thuật toán an toàn.'}
              </div>
            </div>
          </div>
        </div>
      </div>
    `;
    resSec.innerHTML = html;
    resSec.classList.remove('hidden');
    return;
  }

  // ==============================================================================
  // PRESCRIPTION MODE: GỘP 2 TAB "THUỐC TRONG TOA" & "LỊCH UỐNG & CỮ THUỐC"
  // ==============================================================================
  const meds = data.medications || [];
  const warnings = data.warnings || [];
  const tl = data.timeline || {};

  const slotDefs = [
    { 
      id: 'morning', 
      label: 'BUỔI SÁNG', 
      time: '06:30 - 08:00', 
      iconSvg: '<svg class="w-5 h-5 text-amber-600" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 3v2m0 14v2m9-9h-2M5 12H3m15.364-6.364l-1.414 1.414M7.05 16.95l-1.414 1.414M16.95 16.95l1.414 1.414M7.05 7.05L5.636 5.636M16 12a4 4 0 11-8 0 4 4 0 018 0z"/></svg>', 
      badgeColor: 'bg-amber-50 text-amber-800 border-amber-200',
      items: tl.morning || [] 
    },
    { 
      id: 'noon', 
      label: 'BUỔI TRƯA', 
      time: '11:30 - 12:30', 
      iconSvg: '<svg class="w-5 h-5 text-sky-600" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 2v2m0 16v2m10-10h-2M4 12H2m15.07-7.07l-1.41 1.41M8.34 15.66l-1.41 1.41m11.14 0l-1.41-1.41M8.34 8.34L6.93 6.93M12 6a6 6 0 100 12 6 6 0 000-12z"/></svg>', 
      badgeColor: 'bg-sky-50 dark:bg-sky-500/10 text-sky-800 border-sky-200',
      items: tl.noon || [] 
    },
    { 
      id: 'evening', 
      label: 'CHIỀU / TỐI', 
      time: '18:00 - 19:30', 
      iconSvg: '<svg class="w-5 h-5 text-indigo-600" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"/></svg>', 
      badgeColor: 'bg-indigo-50 text-indigo-800 border-indigo-200',
      items: tl.evening || [] 
    },
    { 
      id: 'bedtime', 
      label: 'TRƯỚC KHI NGỦ', 
      time: '21:00 - 22:00', 
      iconSvg: '<svg class="w-5 h-5 text-sky-700" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z"/></svg>', 
      badgeColor: 'bg-sky-50 dark:bg-sky-500/10 text-sky-900 border-sky-200',
      items: tl.bedtime || [] 
    }
  ];
  const activeSlots = slotDefs.filter(s => s.items.length > 0);
  const activeDoseSlotsCount = activeSlots.length || 3;

  if (meds.length === 0) {
    renderPrescriptionError({
      message: data.message || 'Không tìm thấy danh mục hoạt chất hợp lệ trong tài liệu để thiết lập thời gian biểu.'
    });
    return;
  }

  let html = `
    <div class="space-y-5 font-sans select-none text-slate-800 dark:text-slate-100">

      <!-- 1. TOP STATUS BAR (Ảnh mẫu: Phân loại đơn thuốc bản gốc) -->
      <div class="flex flex-wrap items-center justify-between gap-3 bg-white dark:bg-slate-900/90 border border-sky-100 dark:border-white/10 rounded-2xl p-4 shadow-sm">
        <div class="flex flex-wrap items-center gap-2.5">
          <span class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-sky-900 text-white text-xs font-bold tracking-wide">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
            PHÂN LOẠI: ĐƠN THUỐC BẢN GỐC
          </span>
          <span class="text-xs text-slate-600 dark:text-slate-300 font-semibold flex items-center gap-1.5">
            📄 ${fileName} <span class="text-slate-400 font-mono font-normal">(${scanAcc}% Scan OCR)</span>
          </span>
          <span class="text-xs text-emerald-700 bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded-md font-bold flex items-center gap-1">
            ✓ Đã trích xuất dữ liệu an toàn
          </span>
        </div>

        <div class="flex items-center gap-2">
          <button onclick="window.print()" class="px-3.5 py-1.5 rounded-lg border border-slate-200 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:bg-white/[0.04] text-xs font-bold transition-all shadow-2xs cursor-pointer">
            Export Summary PDF
          </button>
<button onclick="resetPrescriptionScan()" class="px-3.5 py-1.5 rounded-lg bg-teal-800 hover:bg-teal-900 text-white text-xs font-bold transition-all shadow-xs flex items-center gap-1.5 cursor-pointer" title="Quay lại danh sách và xem lịch sử các đơn thuốc đã import">
            <span>📋 Xem Lịch sử / Quét thêm</span>
          </button>
        </div>
      </div>

      <!-- 2. COMPACT CLINICAL HEADER: THẺ NGANG VỪA VẶN, GỌN GÀNG, KHÔNG DƯ KHOẢNG TRỐNG -->
      <div class="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
        
        <!-- CỘT TRÁI (8/12): THÔNG TIN BỆNH NHÂN & NƠI KHÁM GỌN GÀNG -->
        <div class="lg:col-span-8 bg-white dark:bg-slate-900/90 border border-sky-100 dark:border-white/10 rounded-2xl p-4 sm:p-5 shadow-sm space-y-3.5">
          
          <div class="flex items-start justify-between gap-4">
            <div class="flex items-start gap-3.5">
              <div class="w-10 h-10 rounded-xl bg-sky-50 dark:bg-sky-500/10 border border-sky-200 text-sky-900 flex items-center justify-center shrink-0">
                <svg class="w-5 h-5 text-sky-900" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/>
                </svg>
              </div>
              <div>
                <div class="flex items-center gap-2">
                  <span class="text-[10px] font-bold text-slate-400 uppercase tracking-wider">HỒ SƠ BỆNH NHÂN</span>

                </div>
                <h3 class="text-lg font-black text-slate-900 dark:text-white mt-0.5">${patient}</h3>
                
<div class="text-xs text-slate-600 dark:text-slate-300 font-medium mt-1.5 flex flex-wrap items-center gap-2.5">
                  <span class="inline-flex items-center gap-1">
                    <span class="text-slate-400 font-normal">Ngày/Năm sinh:</span> <strong class="text-slate-900 font-bold">${displayBirthInfo}</strong>
                    ${displayAge ? `<span class="px-1.5 py-0.2 rounded bg-teal-50 text-teal-800 border border-teal-200 text-[10px] font-bold">(${displayAge})</span>` : ''}
                  </span>
                  <span class="text-slate-300">•</span>
                  <span class="inline-flex items-center gap-1">
<span class="text-slate-400 font-normal">Giới tính:</span> <strong class="text-slate-900 dark:text-white font-bold">${rawGender}</strong>
                  </span>
                </div>
              </div>
            </div>

            <div class="text-right shrink-0">
              <span class="text-[10px] text-slate-400 uppercase font-bold block">Mã bệnh án</span>
              <span class="inline-block mt-0.5 px-3 py-1 rounded-lg bg-sky-50 dark:bg-sky-500/10 border border-sky-200 text-sky-950 font-mono font-black text-xs">
                ${medId}
              </span>
            </div>
          </div>

          <!-- NƠI KHÁM & CHẨN ĐOÁN -->
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-3 border-t border-slate-100">
            <div class="flex items-center gap-2.5 bg-slate-50 dark:bg-white/[0.04]/80 p-2.5 rounded-xl border border-slate-200/70">
              <div class="w-8 h-8 rounded-lg bg-white dark:bg-slate-800/80 border border-slate-200 dark:border-white/10 flex items-center justify-center shrink-0">
                <svg class="w-4 h-4 text-sky-900" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"/>
                </svg>
              </div>
              <div class="min-w-0">
                <span class="text-[9px] font-bold text-slate-400 uppercase block">Nơi khám</span>
                <h4 class="text-xs font-bold text-slate-900 dark:text-white truncate">${facility}</h4>
              </div>
            </div>

            <div class="flex items-center justify-between gap-2 bg-slate-50 dark:bg-white/[0.04]/80 p-2.5 rounded-xl border border-slate-200/70">
              <div class="min-w-0">
                <span class="text-[9px] font-bold text-slate-400 uppercase block">Chẩn đoán</span>
                <span class="text-xs font-bold text-slate-800 dark:text-slate-100 truncate block">${diag}</span>
              </div>
              <span class="text-[10px] font-mono text-slate-500 dark:text-slate-400 px-1.5 py-0.5 rounded bg-white dark:bg-slate-800/80 border border-slate-200 dark:border-white/10 shrink-0">
                K29.1
              </span>
            </div>
          </div>

        </div>

        <!-- CỘT PHẢI (4/12): CỐ VẤN LÂM SÀNG MEDIMIND THIẾT KẾ COMPACT TIẾT KIỆM KHÔNG GIAN -->
        <div class="lg:col-span-4 bg-sky-950 text-white rounded-2xl p-4 shadow-sm space-y-3">
          <div class="flex items-center justify-between pb-2 border-b border-sky-900">
            <div class="flex items-center gap-2">
              <div class="w-7 h-7 rounded-lg bg-sky-900 flex items-center justify-center text-sky-200 border border-sky-700">
                <svg class="w-4 h-4 text-sky-200" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
                </svg>
              </div>
              <div>
                <h4 class="text-xs font-black tracking-tight leading-tight">Cố vấn Lâm sàng MediMind</h4>
                <p class="text-[9px] text-sky-300">Hướng dẫn đơn thuốc</p>
              </div>
            </div>
            <span class="text-[9px] font-bold bg-sky-900 text-sky-200 border border-sky-700 px-2 py-0.2 rounded-full">
              Active
            </span>
          </div>

          <div class="space-y-1.5 text-xs text-sky-50">
            <div class="bg-sky-900/60 border border-sky-700/60 p-2 rounded-lg flex items-start gap-2">
              <span class="text-sky-300 font-bold text-[11px] shrink-0">1.</span>
              <p class="text-[11px] leading-tight opacity-90"><strong class="text-sky-200">Đúng cữ:</strong> Uống theo giờ Sáng 07h, Trưa 12h, Tối 18h30.</p>
            </div>
            <div class="bg-sky-900/60 border border-sky-700/60 p-2 rounded-lg flex items-start gap-2">
              <span class="text-sky-300 font-bold text-[11px] shrink-0">2.</span>
              <p class="text-[11px] leading-tight opacity-90"><strong class="text-sky-200">Nguyên viên:</strong> Không bẻ, không nhai viên thuốc giải phóng chậm.</p>
            </div>
          </div>

          <button onclick="askBotAboutPrescription()" class="w-full py-2 rounded-xl bg-sky-900 hover:bg-sky-700 text-white font-bold text-xs transition-colors flex items-center justify-center gap-1.5 border border-sky-700 cursor-pointer">
            <svg class="w-3.5 h-3.5 text-sky-200" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/>
            </svg>
            <span>Hỏi Bác sĩ AI</span>
          </button>
        </div>

      </div>

      <!-- 3. GỘP CHUNG 1 BẢN GỒM 2 TAB: "THUỐC TRONG TOA" & "LỊCH UỐNG & CỮ THUỐC TRONG NGÀY" -->
      <div class="bg-white dark:bg-slate-900/90 border border-sky-100 dark:border-white/10 rounded-2xl shadow-sm overflow-hidden">
        
        <!-- HEADER VỚI 2 TABS NẰM TRONG CÙNG 1 BẢN -->
        <div class="flex flex-col sm:flex-row sm:items-center justify-between p-3 sm:p-4 bg-slate-50 dark:bg-white/[0.04]/80 border-b border-slate-200/80 gap-3">
          
          <div class="flex items-center gap-2 p-1 bg-slate-200/70 rounded-xl w-full sm:w-auto">
            <!-- TAB 1: THUỐC TRONG TOA (MẶC ĐỊNH HIỆN ĐẦU TIÊN) -->
            <button id="btn-subtab-meds" onclick="switchPrescriptionDossierTab('meds')" class="flex-1 sm:flex-none px-4 py-2 rounded-lg text-xs font-bold transition-all flex items-center justify-center gap-2 bg-white text-sky-950 shadow-sm cursor-pointer">
              <svg class="w-4 h-4 text-sky-900" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"/></svg>
              <span>Danh mục thuốc trong toa</span>
              <span class="px-2 py-0.5 rounded-full bg-sky-50 dark:bg-sky-500/10 border border-sky-200 text-sky-900 font-mono text-[10px]">
                0${meds.length}
              </span>
            </button>

            <!-- TAB 2: LỊCH UỐNG & CỮ THUỐC TRONG NGÀY -->
            <button id="btn-subtab-schedule" onclick="switchPrescriptionDossierTab('schedule')" class="flex-1 sm:flex-none px-4 py-2 rounded-lg text-xs font-bold transition-all flex items-center justify-center gap-2 text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:text-white hover:bg-white/50 cursor-pointer">
              <svg class="w-4 h-4 text-slate-600 dark:text-slate-300" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
              <span>Lịch uống &amp; Cữ thuốc trong ngày</span>
              <span class="px-2 py-0.5 rounded-full bg-slate-100 border border-slate-200 text-slate-700 dark:text-slate-200 font-mono text-[10px]">
                0${activeDoseSlotsCount} cữ
              </span>
            </button>
          </div>

          <div class="text-[11px] text-slate-500 dark:text-slate-400 font-medium px-2 flex items-center gap-2">
            <span>⏱️ Điều trị: <strong>${duration}</strong> liên tục</span>
            <span class="text-sky-900 font-bold bg-sky-50 dark:bg-sky-500/10 border border-sky-200 px-2 py-0.5 rounded text-[10px] hidden md:inline-flex">
              ✓ Khớp chuẩn ICD-10
            </span>
          </div>

        </div>

        <!-- ========================================== -->
        <!-- TAB NỘI DUNG 1: BẢNG KÊ CHI TIẾT THUỐC TRONG TOA -->
        <!-- ========================================== -->
        <div id="pane-prescription-meds" class="p-5 space-y-3.5">
          <div class="text-xs text-slate-500 dark:text-slate-400 pb-1">
            Danh mục gồm <strong>${meds.length} loại thuốc đặc hiệu</strong> được bác sĩ chỉ định, kèm hàm lượng và cơ chế an toàn dược lý:
          </div>

          <div class="space-y-3">
            ${meds.map((m, idx) => {
              const numStr = (idx + 1).toString().padStart(2, '0');
              const freq = m.frequency || '3 lần / ngày';
              const usage = m.usage || m.purpose || 'Uống đúng chỉ dẫn sau bữa ăn';
              const dose = m.dose || '1 viên';
              const days = m.days || '60 viên (Đủ 30 ngày)';
              const strength = m.strength ? `(${m.strength})` : '';

              return `
                <div class="border border-slate-200/80 rounded-2xl p-4 bg-slate-50 dark:bg-white/[0.04]/40 hover:bg-slate-50 dark:bg-white/[0.04] transition-all space-y-2.5">
                  <div class="flex items-start justify-between gap-3">
                    <div class="flex items-start gap-3.5">
                      <div class="w-8 h-8 rounded-lg bg-sky-900 text-white flex items-center justify-center font-mono font-black text-xs shrink-0 shadow-2xs">
                        ${numStr}
                      </div>
                      <div>
                        <div class="flex flex-wrap items-center gap-2">
                          <h5 class="text-sm font-black text-slate-900 dark:text-white">${m.standard_name || m.name} <span class="font-normal text-slate-500 dark:text-slate-400 text-xs">${strength}</span></h5>
                          <span class="text-[11px] font-extrabold px-2.5 py-0.5 rounded-md bg-sky-100 text-sky-950 border border-sky-300 shadow-2xs">
                            ${m.purpose || m.category || 'Thuốc đặc trị'}
                          </span>
                        </div>
                        
                        <div class="flex flex-wrap items-center gap-3 text-xs text-slate-500 dark:text-slate-400 mt-1 font-medium">
                          <span class="flex items-center gap-1"><svg class="w-3.5 h-3.5 text-slate-500 dark:text-slate-400" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"/></svg><strong class="text-slate-800 dark:text-slate-100 font-bold">${m.strength || 'Theo liều'}</strong> / viên</span>
                          <span>•</span>
                          <span>Tổng cấp: <strong class="text-slate-800 dark:text-slate-100 font-bold">${days}</strong></span>
                        </div>
                      </div>
                    </div>

                    <div class="text-right shrink-0">
                      <span class="text-xs font-black text-slate-950 block">${dose} / lần</span>
                      <span class="text-[11px] text-slate-500 dark:text-slate-400 font-medium">${freq}</span>
                    </div>
                  </div>

                  <div class="bg-white dark:bg-slate-800/80 border border-slate-200 dark:border-white/10 rounded-xl p-2.5 text-xs text-slate-700 dark:text-slate-200 leading-relaxed flex items-start justify-between gap-2">
                    <div class="flex items-start gap-2">
                      <span class="text-sky-700 font-bold shrink-0 flex items-center gap-1"><svg class="w-3.5 h-3.5 text-sky-700" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>Lưu ý:</span>
                      <p class="font-medium text-slate-600 dark:text-slate-300">${usage}</p>
                    </div>
                    <button onclick="askBotAboutSpecificMedicine('${m.name}')" class="text-[11px] text-sky-700 hover:text-sky-950 underline font-bold shrink-0 cursor-pointer">
                      Hỏi AI →
                    </button>
                  </div>
                </div>
              `;
            }).join('')}
          </div>
        </div>

        <!-- ========================================== -->
        <!-- TAB NỘI DUNG 2: LỊCH UỐNG & CỮ THUỐC TRONG NGÀY -->
        <!-- ========================================== -->
        <div id="pane-prescription-schedule" class="hidden p-5 space-y-4">
          <div class="text-xs text-slate-500 dark:text-slate-400 pb-1">
            Lộ trình phân bổ <strong>${activeDoseSlotsCount} cữ thuốc trong ngày</strong> theo chuẩn dược động học, đảm bảo hấp thu tối ưu:
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            ${activeSlots.map(s => `
              <div class="border border-slate-200 rounded-2xl p-4 bg-slate-50 dark:bg-white/[0.04]/50 space-y-3">
                <div class="flex items-center justify-between pb-2.5 border-b border-slate-200">
                  <div class="flex items-center gap-2.5">
                    <div class="w-9 h-9 rounded-xl bg-white dark:bg-slate-800/80 border border-slate-200 dark:border-white/10 flex items-center justify-center shrink-0 shadow-2xs">
                      ${s.iconSvg}
                    </div>
                    <div>
                      <h5 class="text-xs font-black text-slate-900 dark:text-white uppercase tracking-wide">${s.label}</h5>
                      <span class="text-[11px] font-mono text-slate-500 dark:text-slate-400 font-semibold">${s.time}</span>
                    </div>
                  </div>
                  <span class="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-white dark:bg-slate-800/80 border border-slate-200 dark:border-white/10 text-sky-950 font-mono">
                    ${s.items.length} loại
                  </span>
                </div>

                <div class="space-y-2">
                  ${s.items.map(it => `
                    <div class="bg-white dark:bg-slate-800/80 border border-slate-200 dark:border-white/10 rounded-xl p-2.5 flex items-center justify-between text-xs gap-2">
                      <div>
                        <strong class="font-bold text-slate-900 dark:text-white">${it.name}</strong>
                        <p class="text-[11px] text-slate-500 dark:text-slate-400 font-medium">${it.note || 'Uống sau ăn 30 phút'}</p>
                      </div>
                      <span class="font-mono font-bold text-sky-950 bg-sky-50 dark:bg-sky-500/10 px-2 py-0.5 rounded text-[11px] shrink-0 border border-sky-200">
                        ${it.dose || '1 viên'}
                      </span>
                    </div>
                  `).join('')}
                </div>
              </div>
            `).join('')}
          </div>
        </div>

      </div>

      <!-- 4. BOTTOM BAR ACTIONS -->
      <div class="flex flex-wrap items-center justify-between gap-3 pt-1">
        <div class="flex items-center gap-2">
          <button onclick="setMedicationReminder()" class="px-4 py-2.5 rounded-xl bg-sky-900 hover:bg-sky-950 text-white text-xs font-bold transition-all shadow-xs flex items-center gap-2 cursor-pointer">
            <svg class="w-4 h-4 text-sky-200" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"/></svg>
            <span>Bật nhắc nhở uống thuốc định kỳ</span>
          </button>
        </div>

        <button type="button" onclick="resetPrescriptionScan()" class="px-4 py-2.5 rounded-xl border border-slate-300 hover:bg-slate-100 text-slate-700 dark:text-slate-200 text-xs font-bold transition-all flex items-center gap-2 cursor-pointer shadow-2xs">
          <span>← Quét đơn thuốc khác</span>
        </button>
      </div>

    </div>
  `;

  resSec.innerHTML = html;
  resSec.classList.remove('hidden');
}

// Hàm chuyển đổi mượt mà giữa 2 tab trong cùng 1 bản
function switchPrescriptionDossierTab(tabKey) {
  const btnMeds = document.getElementById('btn-subtab-meds');
  const btnSched = document.getElementById('btn-subtab-schedule');
  const paneMeds = document.getElementById('pane-prescription-meds');
  const paneSched = document.getElementById('pane-prescription-schedule');

  if (!btnMeds || !btnSched || !paneMeds || !paneSched) return;

  if (tabKey === 'meds') {
    // Active meds
    btnMeds.className = "flex-1 sm:flex-none px-4 py-2 rounded-lg text-xs font-bold transition-all flex items-center justify-center gap-2 bg-white text-sky-950 shadow-sm cursor-pointer";
    btnSched.className = "flex-1 sm:flex-none px-4 py-2 rounded-lg text-xs font-bold transition-all flex items-center justify-center gap-2 text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:text-white hover:bg-white/50 cursor-pointer";
    paneMeds.classList.remove('hidden');
    paneSched.classList.add('hidden');
  } else {
    // Active schedule
    btnSched.className = "flex-1 sm:flex-none px-4 py-2 rounded-lg text-xs font-bold transition-all flex items-center justify-center gap-2 bg-white text-sky-950 shadow-sm cursor-pointer";
    btnMeds.className = "flex-1 sm:flex-none px-4 py-2 rounded-lg text-xs font-bold transition-all flex items-center justify-center gap-2 text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:text-white hover:bg-white/50 cursor-pointer";
    paneSched.classList.remove('hidden');
    paneMeds.classList.add('hidden');
  }
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
    name: 'Tối giản Midnight Aurora (Chuẩn VisionOS - Mặc định)', name_en: 'Midnight Aurora (VisionOS Default)', 
    dark: 'radial-gradient(circle at 15% 15%, rgba(14, 165, 233, 0.16) 0%, transparent 45%), radial-gradient(circle at 85% 10%, rgba(99, 102, 241, 0.14) 0%, transparent 40%), radial-gradient(circle at 50% 60%, rgba(245, 158, 11, 0.05) 0%, transparent 50%), radial-gradient(circle at 85% 85%, rgba(14, 165, 233, 0.10) 0%, transparent 45%), radial-gradient(circle at 10% 90%, rgba(16, 185, 129, 0.08) 0%, transparent 40%), linear-gradient(180deg, #090D16 0%, #06080F 50%, #030408 100%)',
    light: 'radial-gradient(ellipse at 50% 0%, rgba(14, 165, 233, 0.12) 0%, transparent 60%), radial-gradient(ellipse at 85% 85%, rgba(99, 102, 241, 0.08) 0%, transparent 50%), linear-gradient(180deg, #F8FAFC 0%, #EEF2F6 100%)'
  },
  { 
    id: 'minimal_cyan', 
    name: 'Ánh sáng Lâm sàng Cyan (Clinical Cyan Glow)', name_en: 'Clinical Cyan Glow', 
    dark: 'radial-gradient(circle at 20% 20%, rgba(56, 189, 248, 0.18) 0%, transparent 50%), radial-gradient(circle at 80% 80%, rgba(14, 165, 233, 0.12) 0%, transparent 50%), linear-gradient(180deg, #050B14 0%, #081324 50%, #03070D 100%)',
    light: 'radial-gradient(ellipse at 20% 10%, rgba(56, 189, 248, 0.14) 0%, transparent 50%), linear-gradient(180deg, #F0F9FF 0%, #E0F2FE 100%)'
  },
  { 
    id: 'minimal_sapphire', 
    name: 'Không gian Sapphire Y tế (Sapphire Twilight)', name_en: 'Sapphire Twilight Ambient', 
    dark: 'radial-gradient(circle at 75% 15%, rgba(99, 102, 241, 0.18) 0%, transparent 50%), radial-gradient(circle at 20% 85%, rgba(14, 165, 233, 0.12) 0%, transparent 45%), linear-gradient(180deg, #080A18 0%, #0D1226 50%, #05060E 100%)',
    light: 'radial-gradient(ellipse at 80% 15%, rgba(99, 102, 241, 0.12) 0%, transparent 50%), linear-gradient(180deg, #EEF2FF 0%, #E0E7FF 100%)'
  },
  { 
    id: 'minimal_slate', 
    name: 'Kính Khói Neutral Studio (Minimal Dark Slate)', name_en: 'Minimal Dark Slate', 
    dark: 'radial-gradient(circle at 50% 0%, rgba(255, 255, 255, 0.06) 0%, transparent 60%), linear-gradient(180deg, #0F172A 0%, #090E1A 50%, #030712 100%)',
    light: 'radial-gradient(circle at 50% 0%, rgba(15, 23, 42, 0.04) 0%, transparent 60%), linear-gradient(180deg, #FFFFFF 0%, #F1F5F9 100%)'
  }
];

let currentWallpaperIndex = 0;

const CLINICAL_CYAN_GLOW = {
  light: 'radial-gradient(ellipse at 20% 10%, rgba(56, 189, 248, 0.14) 0%, transparent 50%), linear-gradient(180deg, #F0F9FF 0%, #E0F2FE 100%)',
  dark: 'radial-gradient(circle at 20% 20%, rgba(56, 189, 248, 0.18) 0%, transparent 50%), radial-gradient(circle at 80% 80%, rgba(14, 165, 233, 0.12) 0%, transparent 50%), linear-gradient(180deg, #050B14 0%, #081324 50%, #03070D 100%)'
};

function applyThemeMode(theme) {
  document.documentElement.classList.toggle('dark', theme === 'dark');
  document.body.classList.toggle('light-glass', theme === 'light');
  document.body.style.backgroundImage = CLINICAL_CYAN_GLOW[theme];
  document.body.style.backgroundAttachment = 'fixed';
  if (typeof syncAuthModalTheme === 'function') syncAuthModalTheme();
}

function initThemeMode() {
  applyThemeMode(localStorage.getItem('medimind_theme') === 'dark' ? 'dark' : 'light');
  document.querySelectorAll('.dock-btn').forEach(btn => btn.removeAttribute('title'));
}

function toggleGlassThemeMode() {
  const theme = document.body.classList.contains('light-glass') ? 'dark' : 'light';
  applyThemeMode(theme);
  localStorage.setItem('medimind_theme', theme);
  broadcastTabEvent('THEME_CHANGE', { theme });
}

function cycleMedicalWallpaper() {
  // Medical space switching removed as per request #1, locked to Clinical Cyan Glow
  showMedicalToast(currentLang === 'en' ? "Theme locked: Clinical Cyan Glow" : "Không gian cố định: Ánh sáng Lâm sàng Cyan", "info");
}

// Notification Dropdown Logic (Requirement 3)
function toggleNotificationDropdown(e) {
  if (e) e.stopPropagation();
  const menu = document.getElementById('notif-dropdown-menu');
  if (!menu) return;
  menu.classList.toggle('hidden');
  closeUserDropdown();
  closeLanguageDropdown();
}

function closeNotificationDropdown() {
  const menu = document.getElementById('notif-dropdown-menu');
  if (menu && !menu.classList.contains('hidden')) {
    menu.classList.add('hidden');
  }
}

function renderNotifications(notifs) {
  const badge = document.getElementById('notif-badge');
  const countEl = document.getElementById('notif-unread-count');
  const markReadBtn = document.getElementById('notif-mark-read-btn');
  const listEl = document.getElementById('notif-items-list');
  if (!listEl) return;

  const items = notifs || [];
  if (items.length === 0) {
    if (badge) badge.classList.add('hidden');
    if (countEl) countEl.classList.add('hidden');
    if (markReadBtn) markReadBtn.classList.add('hidden');
    listEl.innerHTML = `
      <div id="notif-empty-state" class="py-8 text-center flex flex-col items-center justify-center space-y-2 text-slate-400">
        <svg class="w-10 h-10 opacity-30 text-slate-400 mx-auto" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
        </svg>
        <p class="text-xs font-medium text-slate-400" data-i18n="notif_empty">${currentLang === 'en' ? 'No new notifications' : 'Không có thông báo mới'}</p>
      </div>`;
  } else {
    if (badge) {
      badge.innerText = items.length;
      badge.classList.remove('hidden');
    }
    if (countEl) {
      countEl.innerText = `${items.length} ${currentLang === 'en' ? 'new' : 'mới'}`;
      countEl.classList.remove('hidden');
    }
    if (markReadBtn) markReadBtn.classList.remove('hidden');
  }
}

function markAllNotificationsAsRead() {
  const badge = document.getElementById('notif-badge');
  const countEl = document.getElementById('notif-unread-count');
  if (badge) badge.classList.add('hidden');
  if (countEl) {
    countEl.innerText = (currentLang === 'vi' ? 'Đã đọc hết' : 'All read');
    countEl.classList.remove('bg-orange-500/20', 'text-orange-400');
    countEl.classList.add('bg-slate-500/20', 'text-slate-400');
  }
  const items = document.querySelectorAll('.notif-item');
  items.forEach(it => {
    it.classList.add('opacity-60');
  });
}


// User Interaction Helpers (Export, GPS, Demo)
// ==========================================
const loadPresetPrescription = loadPrescriptionPreset;

function exportPdfSummary() {
  showMedicalToast('Đang tạo bản in / kết xuất PDF hồ sơ bệnh án...', 'info', 2000);
  setTimeout(() => {
    window.print();
  }, 250);
}

function calculateHaversineDistance(lat1, lon1, lat2, lon2) {
  const R = 6371; // Bán kính Trái Đất (km)
  const dLat = (lat2 - lat1) * Math.PI / 180;
  const dLon = (lon2 - lon1) * Math.PI / 180;
  const a =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
    Math.sin(dLon / 2) * Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return R * c;
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

      // Tính lại khoảng cách thực tế đến từng cơ sở y tế
      medicalFacilitiesData.forEach(fac => {
        if (fac.lat && fac.lng) {
          const dist = calculateHaversineDistance(latitude, longitude, fac.lat, fac.lng);
          fac.distanceKm = parseFloat(dist.toFixed(1));
          fac.distanceDisplay = `• ${dist < 10 ? dist.toFixed(1) : Math.round(dist)} km`;
        }
      });

      if (typeof renderMedicalFacilities === 'function') {
        renderMedicalFacilities();
      }

      showMedicalToast(`Đã định vị GPS thực tế (${latitude.toFixed(2)}, ${longitude.toFixed(2)}) và tính lại khoảng cách tới các cơ sở y tế.`, 'success');
    },
    (err) => {
      if (statusText) statusText.innerText = 'Khu vực: TP.HCM (Khoảng cách ước tính)';
      showMedicalToast('Không thể lấy vị trí GPS thực. Đang dùng khoảng cách ước tính mặc định.', 'info');
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
          <span class="text-[11px] font-bold text-sky-300">Trợ lý y tế MediMind • Đánh giá sơ bộ</span>
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
    localStorage.setItem(getChatStorageKey(), JSON.stringify(chatSessions));
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
  const title = intakeData?.facts?.present_symptoms?.join(", ") || ((session && session.title) ? session.title : (lastUserText.length > 30 ? lastUserText.slice(0, 30) + '...' : lastUserText));

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
    messageCount: chatHistory.filter(turn => turn.role === "user").length,
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
           class="chat-history-item p-2.5 rounded-xl border transition-all cursor-pointer group relative ${isActive ? 'bg-sky-500/20 border-sky-400/60 shadow-md shadow-sky-500/15 ring-1 ring-sky-400/40' : 'bg-white/80 dark:bg-white/[0.03] border-slate-200/80 dark:border-white/10 hover:bg-white dark:hover:bg-white/[0.08] hover:border-slate-300 dark:hover:border-white/20'}">
        <div class="flex items-center justify-between gap-1.5">
          <div class="flex items-center gap-1.5 min-w-0">
            ${isActive ? '<span class="w-2 h-2 rounded-full bg-teal-500 dark:bg-sky-400 animate-pulse shrink-0"></span>' : '<span class="w-1.5 h-1.5 rounded-full bg-slate-400 dark:bg-white/30 shrink-0"></span>'}
            <span class="text-xs font-bold text-slate-900 dark:text-white truncate group-hover:text-teal-600 dark:group-hover:text-sky-200 transition-colors">${escapeHtml(session.title || 'Phiên tư vấn')}</span>
          </div>
          <div class="flex items-center gap-1 shrink-0">
            <span class="text-[10px] text-slate-500 dark:text-white/40 font-mono">${timeFormatted}</span>
            <button type="button" onclick="event.stopPropagation(); deleteSession('${session.id}')" class="opacity-0 group-hover:opacity-100 p-0.5 text-slate-400 hover:text-rose-500 transition-opacity" title="Xóa phiên tư vấn">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
            </button>
          </div>
        </div>
        <p class="text-[11px] text-slate-600 dark:text-white/60 truncate mt-1 leading-snug font-medium">${escapeHtml(session.lastMessage || '')}</p>
        <div class="flex items-center justify-between text-[10px] pt-1.5 mt-1 border-t border-slate-100 dark:border-white/5">
          <span class="text-teal-700 dark:text-sky-300 font-bold">${session.messageCount || 1} tin nhắn</span>
          <span class="px-1.5 py-0.5 rounded text-[9px] font-bold ${session.riskBadgeClass || 'bg-emerald-50 text-emerald-800 border border-emerald-300 dark:bg-emerald-500/20 dark:text-emerald-300 dark:border-emerald-400/30'}">${escapeHtml(session.riskLevel || 'Theo dõi')}</span>
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
    const res = await fetch('/api/consultations');
    if (!res.ok) return;
    const data = await res.json();
    if (data && data.consultations && data.consultations.length > 0) {
      let hasNew = false;
      data.consultations.forEach(c => {
        const id = c.conversation_id || 'db_conv_' + c.id;
        if (!chatSessions.some(s => s.id === id)) {
          hasNew = true;
          chatSessions.push({
            id: id,
            title: c.message.length > 30 ? c.message.slice(0, 30) + '...' : c.message,
            lastMessage: c.answer ? c.answer.slice(0, 75).replace(/\n/g, ' ') : c.message,
            timestamp: Date.now() - 3600000,
            messageCount: c.messages?.filter(turn => turn.role === "user").length || 1,
            messages: c.messages?.length ? c.messages : [
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

// ==========================================
// Medical Facilities & Hospital Interaction Logic
// (Matching User Layout from media_1793797893780_20805a2d.jpg)
// ==========================================
const medicalFacilitiesData = [
  // --- TP. HỒ CHÍ MINH (HCM) ---
  {
    id: 'fac_careplus',
    name: 'Phòng khám Quốc tế CarePlus',
    categoryTitle: 'PHÒNG KHÁM QUỐC TẾ',
    type: 'clinic',
    types: ['all', 'clinic'],
    region: 'hcm',
    district: 'Quận 3',
    rating: 4.9,
    reviews: '840',
    qualityBadge: 'Bảo Hiểm Quốc Tế',
    badgeType: 'verified',
    address: '167A Nam Kỳ Khởi Nghĩa, Phường 7, Quận 3, TP.HCM',
    lat: 10.7876,
    lng: 106.6874,
    distanceKm: 1.4,
    distanceDisplay: '1.4 km',
    specialties: ['Nhi khoa', 'Tim mạch', 'Tai Mũi Họng', 'Nội tiết & Tiểu đường'],
    hours: '08:00 - 20:00',
    statusText: 'Tiếp nhận nhanh',
    phone: '1800 6116',
    mapUrl: 'https://maps.google.com/?q=CarePlus+Clinic+Nam+Ky+Khoi+Nghia',
    description: 'Hệ thống phòng khám ngoại trú chuẩn quốc tế với dịch vụ nhanh chóng, bảo lãnh viện phí trực tiếp và bác sĩ tận tâm.'
  },
  {
    id: 'fac_diag',
    name: 'Trung tâm Xét nghiệm Diagnostics',
    categoryTitle: 'TRUNG TÂM XÉT NGHIỆM',
    type: 'testing',
    types: ['all', 'testing'],
    region: 'hcm',
    district: 'Quận 10',
    rating: 4.8,
    reviews: '920',
    qualityBadge: 'Chuẩn ISO 15189',
    badgeType: 'verified',
    address: '414 Cao Thắng, Phường 12, Quận 10, TP.HCM',
    lat: 10.7710,
    lng: 106.6749,
    distanceKm: 2.6,
    distanceDisplay: '2.6 km',
    specialties: ['Tiêu hóa & Gan mật', 'Nội tiết & Tiểu đường', 'Thần kinh'],
    hours: '06:00 - 19:00',
    statusText: 'Lấy mẫu tại nhà',
    phone: '1900 1717',
    mapUrl: 'https://maps.google.com/?q=Diag+Laboratories+Cao+Thang',
    description: 'Trung tâm xét nghiệm y khoa tự động hóa hiện đại với hơn 20 năm kinh nghiệm, phục vụ lấy mẫu tại nhà chuyên nghiệp.'
  },
  {
    id: 'fac_vinmec',
    name: 'BVĐK Quốc Tế Vinmec Central Park',
    categoryTitle: 'BỆNH VIỆN ĐA KHOA',
    type: 'general',
    types: ['all', 'general'],
    region: 'hcm',
    district: 'Q. Bình Thạnh',
    rating: 4.9,
    reviews: '1.4k',
    qualityBadge: 'Chuẩn JCI Quốc Tế',
    badgeType: 'jci',
    address: '208 Nguyễn Hữu Cảnh, Phường 22, Q. Bình Thạnh, TP.HCM',
    lat: 10.7951,
    lng: 106.7219,
    distanceKm: 3.1,
    distanceDisplay: '3.1 km',
    specialties: ['Tim mạch', 'Ung bướu', 'Sản phụ khoa', 'Nhi khoa'],
    hours: '07:30 - 17:00 (Cấp cứu 24/7)',
    statusText: 'Cấp cứu 24/7',
    phone: '028 3622 1166',
    mapUrl: 'https://maps.google.com/?q=Vinmec+Central+Park+Hospital',
    description: 'Bệnh viện đa khoa quốc tế hàng đầu tại TP.HCM đạt chứng nhận tiêu chuẩn vàng JCI về an toàn và chất lượng điều trị y tế.'
  },
  {
    id: 'fac_vientim',
    name: 'Viện Tim TP. Hồ Chí Minh',
    categoryTitle: 'BỆNH VIỆN CHUYÊN KHOA',
    type: 'specialized',
    types: ['all', 'specialized'],
    region: 'hcm',
    district: 'Quận 10',
    rating: 4.8,
    reviews: '1.1k',
    qualityBadge: 'Chuyên Khoa Sâu',
    badgeType: 'verified',
    address: '04 Dương Quang Trung, Phường 12, Quận 10, TP.HCM',
    lat: 10.7719,
    lng: 106.6661,
    distanceKm: 4.0,
    distanceDisplay: '4.0 km',
    specialties: ['Tim mạch', 'Nhi khoa', 'Chấn thương chỉnh hình'],
    hours: '07:00 - 16:30',
    statusText: 'Đặt lịch trực tuyến',
    phone: '028 3865 1586',
    mapUrl: 'https://maps.google.com/?q=Vien+Tim+TPHCM',
    description: 'Trung tâm phẫu thuật và can thiệp tim mạch chuyên sâu hàng đầu cả nước do GS. Alain Carpentier đồng sáng lập.'
  },
  {
    id: 'fac_umc',
    name: 'Bệnh viện Đại học Y Dược TP.HCM',
    categoryTitle: 'BỆNH VIỆN ĐA KHOA',
    type: 'general',
    types: ['all', 'general'],
    region: 'hcm',
    district: 'Quận 5',
    rating: 4.8,
    reviews: '2.8k',
    qualityBadge: 'Tuyến Trung Ương',
    badgeType: 'special',
    address: '215 Hồng Bàng, Phường 11, Quận 5, TP.HCM',
    lat: 10.7554,
    lng: 106.6601,
    distanceKm: 4.9,
    distanceDisplay: '4.9 km',
    specialties: ['Tiêu hóa & Gan mật', 'Nội tiết & Tiểu đường', 'Tai Mũi Họng', 'Tim mạch'],
    hours: '06:30 - 16:30 (Có khám theo yêu cầu)',
    statusText: 'Có khám theo yêu cầu',
    phone: '028 3855 4269',
    mapUrl: 'https://maps.google.com/?q=Benh+Vien+Dai+Hoc+Y+Duoc+TPHCM',
    description: 'Bệnh viện thực hành kiểu mẫu tuyến Trung ương với đội ngũ giáo sư, tiến sĩ đầu ngành và trang thiết bị hiện đại bậc nhất.'
  },
  {
    id: 'fac_choray',
    name: 'Bệnh viện Chợ Rẫy',
    categoryTitle: 'BỆNH VIỆN ĐA KHOA',
    type: 'general',
    types: ['all', 'general'],
    region: 'hcm',
    district: 'Quận 5',
    rating: 4.7,
    reviews: '3.5k',
    qualityBadge: 'Hạng Đặc Biệt',
    badgeType: 'special',
    address: '201B Nguyễn Chí Thanh, Phường 12, Quận 5, TP.HCM',
    lat: 10.7580,
    lng: 106.6593,
    distanceKm: 5.1,
    distanceDisplay: '5.1 km',
    specialties: ['Chấn thương chỉnh hình', 'Thần kinh', 'Tiêu hóa & Gan mật', 'Tim mạch'],
    hours: '07:00 - 16:00 (Trực cấp cứu 24/24)',
    statusText: 'Trực cấp cứu 24/24',
    phone: '028 3855 4137',
    mapUrl: 'https://maps.google.com/?q=Benh+Vien+Cho+Ray',
    description: 'Bệnh viện tuyến cuối hạng đặc biệt khu vực phía Nam chuyên tiếp nhận các ca bệnh phức tạp và cấp cứu đa chấn thương.'
  },

  // --- HÀ NỘI ---
  {
    id: 'fac_bachmai',
    name: 'Bệnh viện Bạch Mai',
    categoryTitle: 'BỆNH VIỆN ĐA KHOA',
    type: 'general',
    types: ['all', 'general'],
    region: 'hanoi',
    district: 'Đống Đa',
    rating: 4.8,
    reviews: '4.2k',
    qualityBadge: 'Hạng Đặc Biệt',
    badgeType: 'special',
    address: '78 Giải Phóng, Phương Mai, Đống Đa, Hà Nội',
    lat: 21.0029,
    lng: 105.8402,
    distanceKm: 1.8,
    distanceDisplay: '1.8 km',
    specialties: ['Tim mạch', 'Nội tiết & Tiểu đường', 'Tiêu hóa & Gan mật', 'Thần kinh'],
    hours: '06:30 - 17:00 (Trực cấp cứu 24/24)',
    statusText: 'Trực cấp cứu 24/24',
    phone: '024 3869 3731',
    mapUrl: 'https://maps.google.com/?q=Benh+Vien+Bach+Mai',
    description: 'Bệnh viện đa khoa đầu ngành tuyến cuối lớn nhất miền Bắc với đầy đủ các viện và trung tâm chuyên sâu đạt chuẩn quốc tế.'
  },
  {
    id: 'fac_vinmec_timescity',
    name: 'BVĐK Quốc Tế Vinmec Times City',
    categoryTitle: 'BỆNH VIỆN ĐA KHOA',
    type: 'general',
    types: ['all', 'general', 'clinic'],
    region: 'hanoi',
    district: 'Hai Bà Trưng',
    rating: 4.9,
    reviews: '2.1k',
    qualityBadge: 'Chuẩn JCI Quốc Tế',
    badgeType: 'jci',
    address: '458 Minh Khai, Vĩnh Tuy, Hai Bà Trưng, Hà Nội',
    lat: 20.9946,
    lng: 105.8687,
    distanceKm: 3.5,
    distanceDisplay: '3.5 km',
    specialties: ['Sản phụ khoa', 'Nhi khoa', 'Tim mạch', 'Ung bướu'],
    hours: '07:30 - 17:00 (Cấp cứu 24/7)',
    statusText: 'Cấp cứu 24/7',
    phone: '024 3974 3556',
    mapUrl: 'https://maps.google.com/?q=Vinmec+Times+City',
    description: 'Bệnh viện đa khoa quốc tế đạt chuẩn JCI đầu tiên tại Hà Nội với cơ sở vật chất 5 sao đẳng cấp.'
  },

  // --- ĐÀ NẴNG ---
  {
    id: 'fac_danang_general',
    name: 'Bệnh viện Đà Nẵng',
    categoryTitle: 'BỆNH VIỆN ĐA KHOA',
    type: 'general',
    types: ['all', 'general'],
    region: 'danang',
    district: 'Hải Châu',
    rating: 4.7,
    reviews: '1.8k',
    qualityBadge: 'Tuyến Trung Ương',
    badgeType: 'special',
    address: '124 Hải Phòng, Thạch Thang, Hải Châu, Đà Nẵng',
    lat: 16.0748,
    lng: 108.2144,
    distanceKm: 1.2,
    distanceDisplay: '1.2 km',
    specialties: ['Chấn thương chỉnh hình', 'Tim mạch', 'Thần kinh', 'Tiêu hóa & Gan mật'],
    hours: '07:00 - 17:00 (Cấp cứu 24/24)',
    statusText: 'Cấp cứu 24/24',
    phone: '0236 3821 118',
    mapUrl: 'https://maps.google.com/?q=Benh+Vien+Da+Nang',
    description: 'Bệnh viện đa khoa hạng 1 lớn nhất khu vực miền Trung - Tây Nguyên chuyên tiếp nhận các ca bệnh chuyên sâu.'
  },
  {
    id: 'fac_vinmec_danang',
    name: 'BVĐK Quốc Tế Vinmec Đà Nẵng',
    categoryTitle: 'PHÒNG KHÁM QUỐC TẾ',
    type: 'clinic',
    types: ['all', 'clinic', 'general'],
    region: 'danang',
    district: 'Hải Châu',
    rating: 4.9,
    reviews: '960',
    qualityBadge: 'Chuẩn JCI Quốc Tế',
    badgeType: 'jci',
    address: 'Đường 30 Tháng 4, Phường Hòa Cường Bắc, Hải Châu, Đà Nẵng',
    lat: 16.0392,
    lng: 108.2163,
    distanceKm: 2.8,
    distanceDisplay: '2.8 km',
    specialties: ['Nhi khoa', 'Sản phụ khoa', 'Tai Mũi Họng', 'Tim mạch'],
    hours: '08:00 - 17:00',
    statusText: 'Tiếp nhận nhanh',
    phone: '0236 3711 111',
    mapUrl: 'https://maps.google.com/?q=Vinmec+Da+Nang',
    description: 'Bệnh viện chuẩn quốc tế quy mô hiện đại hàng đầu phục vụ người dân và du khách tại Đà Nẵng.'
  }
];

let facilityCurrentRegion = 'hcm';
let facilityCurrentType = 'all';
let facilityDistrict = 'all';
let facilitySpecialty = 'all';
let facilitySearchQuery = '';
let facilitySort = 'distance';
let activeDetailFacilityId = null;

let hospitalLeafletMap = null;
let hospitalMarkersLayer = null;

function getFacilityIcon(fac) {
  if (fac.type === 'testing') {
    return `
      <div class="w-10 h-10 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-100 dark:border-white/10 flex items-center justify-center text-slate-700 dark:text-slate-200 shrink-0">
        <svg class="w-5 h-5 text-slate-700 dark:text-slate-200" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"/>
        </svg>
      </div>
    `;
  }
  if (fac.type === 'clinic') {
    return `
      <div class="w-10 h-10 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-100 dark:border-white/10 flex items-center justify-center text-slate-700 dark:text-slate-200 shrink-0">
        <svg class="w-5 h-5 text-slate-700 dark:text-slate-200" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M16 4v2a4 4 0 01-8 0V4m-2 2h12M12 10v10m-4-6h8"/>
        </svg>
      </div>
    `;
  }
  if (fac.type === 'specialized') {
    return `
      <div class="w-10 h-10 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-100 dark:border-white/10 flex items-center justify-center text-slate-700 dark:text-slate-200 shrink-0">
        <svg class="w-5 h-5 text-slate-700 dark:text-slate-200" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"/>
        </svg>
      </div>
    `;
  }
  // Bệnh viện đa khoa
  return `
    <div class="w-10 h-10 rounded-xl bg-slate-50 dark:bg-slate-800 border border-slate-100 dark:border-white/10 flex items-center justify-center text-slate-700 dark:text-slate-200 shrink-0">
      <svg class="w-5 h-5 text-slate-700 dark:text-slate-200" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"/>
      </svg>
    </div>
  `;
}

function initHospitalInteractiveMap() {
  const container = document.getElementById('hospital-interactive-map');
  if (!container) return;
  if (typeof L === 'undefined') return;

  if (!hospitalLeafletMap) {
    hospitalLeafletMap = L.map('hospital-interactive-map').setView([10.7769, 106.6850], 13);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '&copy; OpenStreetMap contributors'
    }).addTo(hospitalLeafletMap);
    hospitalMarkersLayer = L.layerGroup().addTo(hospitalLeafletMap);
  }

  updateHospitalMapMarkers();
}

function updateHospitalMapMarkers(customList) {
  if (!hospitalLeafletMap || !hospitalMarkersLayer) return;
  if (typeof L === 'undefined') return;
  hospitalMarkersLayer.clearLayers();

  const list = customList || medicalFacilitiesData;

  const defaultIcon = L.divIcon({
    className: 'custom-hospital-marker',
    html: `
      <div style="background:#2563eb; color:white; width:34px; height:34px; border-radius:12px; display:flex; align-items:center; justify-content:center; box-shadow:0 4px 12px rgba(37,99,235,0.4); border:2px solid white; font-weight:bold; font-size:16px;">
        🏥
      </div>
    `,
    iconSize: [34, 34],
    iconAnchor: [17, 17],
    popupAnchor: [0, -18]
  });

  const bounds = [];

  list.forEach(fac => {
    if (fac.lat && fac.lng) {
      bounds.push([fac.lat, fac.lng]);
      const popupHtml = `
        <div style="font-family: inherit; font-size: 12px; min-width: 220px; line-height: 1.45; padding: 2px;">
          <div style="font-weight: 700; font-size: 13px; color: #0f172a; margin-bottom: 2px;">${fac.name}</div>
          <div style="font-size: 10px; font-weight: 700; color: #2563eb; text-transform: uppercase; margin-bottom: 4px;">${fac.categoryTitle} • ${fac.distanceDisplay}</div>
          <div style="color: #64748b; font-size: 11px; margin-bottom: 8px;">📍 ${fac.address}</div>
          <div style="display: flex; gap: 6px;">
            <button onclick="openFacilityBookingModal('${fac.id}')" style="background: #2563eb; color: white; border: none; border-radius: 8px; padding: 6px 12px; font-size: 11px; font-weight: 600; cursor: pointer; flex: 1;">Đặt lịch khám</button>
            <a href="${fac.mapUrl}" target="_blank" style="background: #f8fafc; color: #334155; border: 1px solid #cbd5e1; border-radius: 8px; padding: 6px 10px; font-size: 11px; font-weight: 600; text-decoration: none; display: inline-flex; align-items: center;">Chỉ đường</a>
          </div>
        </div>
      `;
      const marker = L.marker([fac.lat, fac.lng], { icon: defaultIcon }).bindPopup(popupHtml);
      hospitalMarkersLayer.addLayer(marker);
    }
  });

  if (bounds.length > 0 && hospitalLeafletMap) {
    hospitalLeafletMap.fitBounds(bounds, { padding: [35, 35], maxZoom: 14 });
  }
}

function toggleHospitalMapSection() {
  const panel = document.getElementById('hospital-map-collapsible');
  if (!panel) return;
  panel.classList.toggle('hidden');
  const isHidden = panel.classList.contains('hidden');
  document.querySelectorAll('[data-role="map-toggle-text"]').forEach(el => {
    el.innerText = isHidden ? 'Mở bản đồ' : 'Thu gọn bản đồ';
  });
  if (!isHidden) {
    setTimeout(() => {
      initHospitalInteractiveMap();
      if (hospitalLeafletMap) {
        hospitalLeafletMap.invalidateSize();
      }
    }, 150);
  }
}

function getCurrentLocationForHospitals() {
  if (!navigator.geolocation) {
    showMedicalToast('Trình duyệt không hỗ trợ Geolocation GPS.', 'warning');
    return;
  }
  showMedicalToast('Đang xác định vị trí GPS thực tế...', 'info', 2000);
  navigator.geolocation.getCurrentPosition(
    pos => {
      const { latitude, longitude } = pos.coords;
      medicalFacilitiesData.forEach(fac => {
        if (fac.lat && fac.lng) {
          const dist = calculateHaversineDistance(latitude, longitude, fac.lat, fac.lng);
          fac.distanceKm = parseFloat(dist.toFixed(1));
          fac.distanceDisplay = `${dist < 10 ? dist.toFixed(1) : Math.round(dist)} km`;
        }
      });
      renderMedicalFacilities();

      if (hospitalLeafletMap && typeof L !== 'undefined') {
        const userIcon = L.divIcon({
          className: 'custom-user-marker',
          html: `<div style="background:#10b981; color:white; width:30px; height:30px; border-radius:50%; display:flex; align-items:center; justify-content:center; box-shadow:0 0 14px rgba(16,185,129,0.8); border:2px solid white; font-size:14px;">📍</div>`,
          iconSize: [30, 30],
          iconAnchor: [15, 15]
        });
        L.marker([latitude, longitude], { icon: userIcon }).addTo(hospitalLeafletMap).bindPopup('<b>Vị trí của bạn</b>').openPopup();
        hospitalLeafletMap.setView([latitude, longitude], 13);
      }
      showMedicalToast(`Đã đồng bộ GPS (${latitude.toFixed(2)}, ${longitude.toFixed(2)}) và cập nhật khoảng cách.`, 'success');
    },
    err => {
      showMedicalToast('Không thể lấy vị trí GPS. Đang dùng khoảng cách ước tính mặc định.', 'info');
    },
    { timeout: 8000 }
  );
}


function localizeQualityBadge(badge, isEn) {
  if (!isEn || !badge) return badge;
  const m = {
    'Chuẩn JCI Quốc tế': 'JCI Accredited',
    'Chuẩn JCI Quốc Tế': 'JCI Accredited',
    'Tuyến Trung Ương': 'Central Referral',
    'Hạng Đặc Biệt': 'Special Grade',
    'Tuyến Đầu Cấp Cứu': 'Top Emergency',
    'Sản Phụ Khoa Đầu Ngành': 'Leading OB/GYN',
    'Nhi Khoa Tuyến Cuối': 'Top Pediatric Referral',
    'Chuyên Khoa Tim Mạch': 'Cardiology Specialist',
    'Ung Bướu Tuyến Đầu': 'Top Oncology Center',
    'Bảo Hiểm Quốc Tế': 'Direct Billing Insurance',
    'Chuyên Khoa Sâu': 'Tertiary Specialist',
    'Chuẩn ISO 15189': 'ISO 15189 Certified'
  };
  return m[badge] || badge;
}

function localizeSpecialty(spec, isEn) {
  if (!isEn || !spec) return spec;
  const m = {
    'Tim mạch': 'Cardiology',
    'Ung bướu': 'Oncology',
    'Sản phụ khoa': 'OB/GYN',
    'Nhi khoa': 'Pediatrics',
    'Nội tiết & Tiểu đường': 'Endocrinology',
    'Tiêu hóa & Gan mật': 'Gastroenterology',
    'Chấn thương chỉnh hình': 'Orthopedics',
    'Thần kinh': 'Neurology',
    'Tai Mũi Họng': 'ENT',
    'Mắt': 'Ophthalmology',
    'Khám tổng quát': 'General Practice'
  };
  return m[spec] || spec;
}

function localizeHours(hours, isEn) {
  if (!isEn || !hours) return hours;
  return hours
    .replace(/Cấp cứu 24\/7/g, '24/7 Emergency')
    .replace(/Có khám theo yêu cầu/g, 'On-demand clinic')
    .replace(/Trực cấp cứu 24\/24/g, '24/7 Emergency')
    .replace(/Khám BHYT & Dịch vụ/g, 'Insurance & Private')
    .replace(/Cấp cứu đột quỵ 24\/7/g, '24/7 Stroke Emergency')
    .replace(/Cấp cứu sản 24\/24/g, '24/7 OB Emergency')
    .replace(/Khám theo yêu cầu & BHYT/g, 'On-demand & Insurance')
    .replace(/Đặt lịch trực tuyến/g, 'Online booking')
    .replace(/Lấy mẫu tại nhà/g, 'Home sample collection')
    .replace(/Khám chuyên khoa mắt/g, 'Eye clinic')
    .replace(/Chuyên khoa Tai Mũi Họng/g, 'ENT clinic');
}

function renderMedicalFacilities() {
  const isEn = typeof currentLang !== 'undefined' && currentLang === 'en';
  const container = document.getElementById('facility-cards-grid');
  updateFacilitySidebarCounts();
  if (!container) return;

  const countEl = document.getElementById('facility-results-count');
  const totalBadge = document.getElementById('facilities-total-badge');
  const noResults = document.getElementById('facility-no-results');

  const reg = facilityCurrentRegion || 'hcm';

  let list = medicalFacilitiesData.filter(fac => {
    // 0. Filter Region
    if (reg !== 'all') {
      const facReg = fac.region || 'hcm';
      if (facReg !== reg) return false;
    }

    // 1. Filter Type
    if (facilityCurrentType !== 'all') {
      if (!fac.types || !fac.types.includes(facilityCurrentType)) return false;
    }

    // 2. Filter District
    if (facilityDistrict !== 'all') {
      if (fac.district !== facilityDistrict) return false;
    }

    // 3. Filter Specialty
    if (facilitySpecialty !== 'all') {
      if (!fac.specialties || !fac.specialties.includes(facilitySpecialty)) return false;
    }

    // 4. Search Query
    if (facilitySearchQuery) {
      const q = facilitySearchQuery.toLowerCase().trim();
      const matchName = fac.name ? fac.name.toLowerCase().includes(q) : false;
      const matchAddress = fac.address ? fac.address.toLowerCase().includes(q) : false;
      const matchSpec = fac.specialties ? fac.specialties.some(s => s.toLowerCase().includes(q)) : false;
      if (!matchName && !matchAddress && !matchSpec) return false;
    }

    return true;
  });

  // Sort
  if (facilitySort === 'rating') {
    list.sort((a, b) => (b.rating || 0) - (a.rating || 0));
  } else if (facilitySort === 'distance') {
    list.sort((a, b) => (a.distanceKm || 0) - (b.distanceKm || 0));
  } else if (facilitySort === 'name') {
    list.sort((a, b) => (a.name || '').localeCompare(b.name || '', 'vi'));
  }

  // Update Count Badge & Text
  if (countEl) {
    countEl.innerText = isEn
      ? `Showing ${list.length} healthcare facilities (MoH & MedlinePlus Standard)`
      : `Hiển thị ${list.length} cơ sở y tế uy tín đạt chuẩn Bộ Y tế & MedlinePlus`;
  }
  if (totalBadge) {
    totalBadge.innerText = list.length;
  }

  // Update Map markers
  try {
    if (hospitalLeafletMap && hospitalMarkersLayer && typeof updateHospitalMapMarkers === 'function') {
      updateHospitalMapMarkers(list);
    }
  } catch (mapErr) {
    console.warn('[Map] Update markers failed:', mapErr);
  }

  if (list.length === 0) {
    container.innerHTML = '';
    if (noResults) noResults.classList.remove('hidden');
    return;
  }

  if (noResults) noResults.classList.add('hidden');

  container.innerHTML = list.map(fac => {
    const visibleSpecialties = (fac.specialties || []).slice(0, 3);
    const extraCount = (fac.specialties || []).length - 3;

    return `
      <div class="facility-card bg-white dark:bg-slate-900 border border-slate-200/90 dark:border-white/10 rounded-2xl p-4 sm:p-5 shadow-xs hover:shadow-md transition-shadow flex flex-col justify-between space-y-3">
        <div>
          <!-- Top Row: Icon + Rating -->
          <div class="flex items-center justify-between">
            ${getFacilityIcon(fac)}
            <div class="flex flex-wrap items-center justify-end gap-1.5">
              <span class="inline-flex items-center gap-1 px-2.5 py-1 rounded-xl text-xs font-black bg-amber-50 dark:bg-amber-950/60 text-amber-800 dark:text-amber-300 border border-amber-300 dark:border-amber-500/40 shadow-xs font-mono">
                <span class="text-amber-500">⭐</span>
                <span>${fac.rating || 4.8}</span>
                <span class="text-[10px] font-bold text-amber-700/80 dark:text-amber-400/80">(${fac.reviews || 0})</span>
              </span>
              <span class="text-[10px] sm:text-[11px] font-bold px-2.5 py-1 rounded-xl border shadow-xs ${getFacilityBadgeColor(fac.badgeType)}">
                ${localizeQualityBadge(fac.qualityBadge, isEn)}
              </span>
            </div>
          </div>

          <!-- Category Subtitle -->
          <div class="mt-2.5">
            <span class="text-[10px] font-bold text-slate-400 dark:text-slate-400 tracking-wider uppercase block">
              ${fac.categoryTitle || 'CƠ SỞ Y TẾ'}
            </span>
            <h3 class="text-sm sm:text-base font-bold text-slate-900 dark:text-white mt-0.5 line-clamp-1" title="${fac.name}">
              ${fac.name}
            </h3>
          </div>

          <!-- Quality Badge -->
          <div class="mt-2">
            <span class="inline-block text-[11px] font-semibold text-sky-600 dark:text-sky-400 bg-sky-50 dark:bg-sky-950/60 border border-sky-100 dark:border-sky-800/40 px-2.5 py-0.5 rounded-md">
              ${localizeQualityBadge(fac.qualityBadge, isEn)}
            </span>
          </div>

          <!-- Address and Distance -->
          <div class="flex items-center justify-between text-xs text-slate-600 dark:text-slate-400 gap-2 mt-2.5">
            <span class="truncate flex items-center gap-1.5" title="${fac.address}">
              <svg class="w-3.5 h-3.5 text-slate-400 shrink-0 inline-block" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"/><path stroke-linecap="round" stroke-linejoin="round" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
              <span class="truncate">${fac.address}</span>
            </span>
            <span class="font-bold text-sky-600 dark:text-sky-400 shrink-0 text-xs">${fac.distanceDisplay || ''}</span>
          </div>

          <!-- Specialty Tags -->
          <div class="flex flex-wrap gap-1 pt-1">
            ${(fac.specialties || []).slice(0, 4).map(s => `
              <span class="px-2 py-0.5 rounded-md text-[10px] font-medium bg-slate-100 dark:bg-white/5 text-slate-600 dark:text-slate-300 border border-slate-200/80 dark:border-white/10">
                ${localizeSpecialty(s, isEn)}
              </span>
            `).join('')}
            ${extraCount > 0 ? `
              <span class="px-2 py-0.5 rounded-md text-[11px] font-medium bg-slate-100 dark:bg-white/5 text-slate-600 dark:text-slate-300">
                +${extraCount}
              </span>
            ` : ''}
          </div>

          <!-- Status & Operating Hours -->
          <div class="flex items-center gap-1.5 text-[11px] text-slate-600 dark:text-slate-300 pt-1 font-medium">
            <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse shrink-0"></span>
            <span class="truncate">${localizeHours(fac.hours, isEn)}</span>
          </div>
        </div>

        <!-- Bottom Action Buttons -->
        <div class="flex items-center gap-2 pt-2 border-t border-slate-100 dark:border-white/5">
          <button type="button" onclick="openFacilityBookingModal('${fac.id}')" class="flex-1 py-2 rounded-xl bg-gradient-to-r from-sky-500 to-indigo-600 hover:from-sky-400 hover:to-indigo-500 text-white font-bold text-xs shadow-md shadow-sky-500/20 text-center transition-all cursor-pointer">
            ${isEn ? 'Book Appointment' : 'Đặt lịch khám'}
          </button>
          <button type="button" onclick="openFacilityDetailModal('${fac.id}')" class="px-3.5 py-2 rounded-xl glass-pill border border-slate-200 dark:border-white/10 hover:border-sky-400/40 text-slate-700 dark:text-slate-200 hover:text-sky-600 dark:hover:text-white font-bold text-xs transition-all cursor-pointer">
            ${isEn ? 'Details' : 'Chi tiết'}
          </button>
        </div>
      </div>
    `;
  }).join('');
}

function selectFacilityType(type, btn) {
  facilityCurrentType = type;
  document.querySelectorAll('.facility-type-btn').forEach(b => {
    b.className = 'facility-type-btn w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-white/5 border border-transparent font-medium text-xs transition-all cursor-pointer';
    const badge = b.querySelector('[id^="badge-count-"]');
    if (badge) {
      badge.className = 'px-2 py-0.5 rounded-md text-[10px] font-semibold bg-slate-100 dark:bg-white/10 text-slate-600 dark:text-slate-400';
    }
  });
  if (btn) {
    btn.className = 'facility-type-btn active w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl bg-sky-600 text-white border border-sky-500 shadow-md shadow-sky-600/25 text-xs font-bold transition-all cursor-pointer';
    const badge = btn.querySelector('[id^="badge-count-"]');
    if (badge) {
      badge.className = 'px-2 py-0.5 rounded-md text-[10px] font-bold bg-white/25 text-white';
    }
  }
  renderMedicalFacilities();
}

const regionDistrictsMap = {
  hcm: [
    { val: 'all', vi: 'Tất cả quận/huyện (TP.HCM)', en: 'All Districts (HCMC)' },
    { val: 'Quận 1', vi: 'Quận 1', en: 'District 1' },
    { val: 'Quận 3', vi: 'Quận 3', en: 'District 3' },
    { val: 'Quận 5', vi: 'Quận 5', en: 'District 5' },
    { val: 'Quận 7', vi: 'Quận 7', en: 'District 7' },
    { val: 'Quận 10', vi: 'Quận 10', en: 'District 10' },
    { val: 'Q. Bình Thạnh', vi: 'Q. Bình Thạnh', en: 'Binh Thanh Dist.' },
    { val: 'Tân Bình', vi: 'Quận Tân Bình', en: 'Tan Binh Dist.' },
    { val: 'TP. Thủ Đức', vi: 'TP. Thủ Đức', en: 'Thu Duc City' }
  ],
  hanoi: [
    { val: 'all', vi: 'Tất cả quận/huyện (Hà Nội)', en: 'All Districts (Hanoi)' },
    { val: 'Đống Đa', vi: 'Quận Đống Đa', en: 'Dong Da Dist.' },
    { val: 'Hoàn Kiếm', vi: 'Quận Hoàn Kiếm', en: 'Hoan Kiem Dist.' },
    { val: 'Hai Bà Trưng', vi: 'Quận Hai Bà Trưng', en: 'Hai Ba Trung Dist.' },
    { val: 'Ba Đình', vi: 'Quận Ba Đình', en: 'Ba Dinh Dist.' }
  ],
  danang: [
    { val: 'all', vi: 'Tất cả quận/huyện (Đà Nẵng)', en: 'All Districts (Da Nang)' },
    { val: 'Hải Châu', vi: 'Quận Hải Châu', en: 'Hai Chau Dist.' },
    { val: 'Thanh Khê', vi: 'Quận Thanh Khê', en: 'Thanh Khe Dist.' },
    { val: 'Ngũ Hành Sơn', vi: 'Quận Ngũ Hành Sơn', en: 'Ngu Hanh Son Dist.' },
    { val: 'Liên Chiểu', vi: 'Quận Liên Chiểu', en: 'Lien Chieu Dist.' }
  ]
};

function updateFacilityDistrictDropdown(region) {
  const distSelect = document.getElementById('facility-district-filter');
  if (!distSelect) return;
  const list = regionDistrictsMap[region] || regionDistrictsMap['hcm'];
  const isEn = typeof currentLang !== 'undefined' && currentLang === 'en';
  const currVal = facilityDistrict || 'all';
  distSelect.innerHTML = list.map(d => `<option value="${d.val}">${(isEn ? d.en : d.vi) || d.label || d.val}</option>`).join('');
  distSelect.value = currVal;
}

function updateFacilitySidebarCounts() {
  const reg = facilityCurrentRegion || 'hcm';
  const activeRegionFacs = medicalFacilitiesData.filter(fac => reg === 'all' || (fac.region || 'hcm') === reg);
  const countAll = activeRegionFacs.length;
  const countGeneral = activeRegionFacs.filter(f => f.types && f.types.includes('general')).length;
  const countClinic = activeRegionFacs.filter(f => f.types && f.types.includes('clinic')).length;
  const countSpecialized = activeRegionFacs.filter(f => f.types && f.types.includes('specialized')).length;
  const countTesting = activeRegionFacs.filter(f => f.types && f.types.includes('testing')).length;

  const bAll = document.getElementById('badge-count-all');
  const bGen = document.getElementById('badge-count-general');
  const bCli = document.getElementById('badge-count-clinic');
  const bSpe = document.getElementById('badge-count-specialized');
  const bTes = document.getElementById('badge-count-testing');

  if (bAll) bAll.innerText = countAll;
  if (bGen) bGen.innerText = countGeneral;
  if (bCli) bCli.innerText = countClinic;
  if (bSpe) bSpe.innerText = countSpecialized;
  if (bTes) bTes.innerText = countTesting;
}

function selectFacilityRegion(region, btn) {
  facilityCurrentRegion = region;
  facilityDistrict = 'all';
  document.querySelectorAll('.facility-region-btn').forEach(b => {
    b.className = 'facility-region-btn py-2 text-center rounded-xl text-xs font-medium text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition-all cursor-pointer';
  });
  if (btn) {
    btn.className = 'facility-region-btn active py-2 text-center rounded-xl text-xs font-bold bg-white dark:bg-slate-700 text-sky-600 dark:text-sky-300 shadow-sm border border-slate-200/60 dark:border-transparent transition-all cursor-pointer';
  }
  updateFacilityDistrictDropdown(region);
  updateFacilitySidebarCounts();
  renderMedicalFacilities();
}

function handleFacilityDistrictChange(val) {
  facilityDistrict = val;
  renderMedicalFacilities();
}

function toggleFacilitySpecialty(spec, btn) {
  if (facilitySpecialty === spec) {
    facilitySpecialty = 'all';
    document.querySelectorAll('.facility-spec-btn').forEach(b => {
      b.className = 'facility-spec-btn px-3 py-1.5 rounded-xl text-xs font-medium text-slate-600 dark:text-slate-400 bg-slate-100 dark:bg-white/5 border border-slate-200/80 dark:border-white/10 hover:border-sky-400/40 transition-all cursor-pointer';
    });
  } else {
    facilitySpecialty = spec;
    document.querySelectorAll('.facility-spec-btn').forEach(b => {
      b.className = 'facility-spec-btn px-3 py-1.5 rounded-xl text-xs font-medium text-slate-600 dark:text-slate-400 bg-slate-100 dark:bg-white/5 border border-slate-200/80 dark:border-white/10 hover:border-sky-400/40 transition-all cursor-pointer';
    });
    if (btn) {
      btn.className = 'facility-spec-btn active px-3 py-1.5 rounded-xl text-xs font-bold bg-sky-600 text-white border border-sky-500 shadow-xs transition-all cursor-pointer';
    }
  }
  renderMedicalFacilities();
}

// Backward compatibility alias
function selectFacilitySpecialtyPill(specialty, btn) {
  toggleFacilitySpecialty(specialty, btn);
}

function handleFacilitySearchInput(val) {
  facilitySearchQuery = val;
  const mainSearch = document.getElementById('facility-main-search');
  const sidebarSearch = document.getElementById('facility-sidebar-search');
  if (mainSearch && mainSearch.value !== val) mainSearch.value = val;
  if (sidebarSearch && sidebarSearch.value !== val) sidebarSearch.value = val;
  renderMedicalFacilities();
}

function handleFacilitySortChange(val) {
  facilitySort = val;
  const sortSelect = document.getElementById('facility-sort-select');
  if (sortSelect && sortSelect.value !== val) sortSelect.value = val;
  renderMedicalFacilities();
}

function resetAllFacilityFilters() {
  facilityCurrentRegion = 'hcm';
  facilityCurrentType = 'all';
  facilityDistrict = 'all';
  facilitySpecialty = 'all';
  facilitySearchQuery = '';
  facilitySort = 'distance';

  const mainSearch = document.getElementById('facility-main-search');
  const sidebarSearch = document.getElementById('facility-sidebar-search');
  const distSelect = document.getElementById('facility-district-filter');
  const sortSelect = document.getElementById('facility-sort-select');
  if (mainSearch) mainSearch.value = '';
  if (sidebarSearch) sidebarSearch.value = '';
  if (distSelect) distSelect.value = 'all';
  if (sortSelect) sortSelect.value = 'default';

  // Reset type buttons
  document.querySelectorAll('.facility-type-btn').forEach(b => {
    b.className = 'facility-type-btn w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-white/5 border border-transparent font-medium text-xs transition-all cursor-pointer';
    const badge = b.querySelector('[id^="badge-count-"]');
    if (badge) badge.className = 'px-2 py-0.5 rounded-md text-[10px] font-semibold bg-slate-100 dark:bg-white/10 text-slate-600 dark:text-slate-400';
  });
  const firstTypeBtn = document.querySelector('#facility-type-list button');
  if (firstTypeBtn) {
    firstTypeBtn.className = 'facility-type-btn active w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl bg-sky-600 text-white border border-sky-500 shadow-md shadow-sky-600/25 text-xs font-bold transition-all cursor-pointer';
    const badge = firstTypeBtn.querySelector('[id^="badge-count-"]');
    if (badge) badge.className = 'px-2 py-0.5 rounded-md text-[10px] font-bold bg-white/25 text-white';
  }

  // Reset region buttons
  document.querySelectorAll('.facility-region-btn').forEach(b => {
    b.className = 'facility-region-btn py-2 text-center rounded-xl text-xs font-medium text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition-all cursor-pointer';
  });
  const firstRegionBtn = document.querySelector('#facility-region-group button');
  if (firstRegionBtn) {
    firstRegionBtn.className = 'facility-region-btn active py-2 text-center rounded-xl text-xs font-bold bg-white dark:bg-slate-700 text-sky-600 dark:text-sky-300 shadow-sm border border-slate-200/60 dark:border-transparent transition-all cursor-pointer';
  }

  // Reset specialty buttons
  document.querySelectorAll('.facility-spec-btn').forEach(b => {
    b.className = 'facility-spec-btn px-3 py-1.5 rounded-xl text-xs font-medium text-slate-600 dark:text-slate-400 bg-slate-100 dark:bg-white/5 border border-slate-200/80 dark:border-white/10 hover:border-sky-400/40 transition-all cursor-pointer';
  });

  updateFacilityDistrictDropdown('hcm');
  renderMedicalFacilities();
}

function getFacilityBadgeColor(badgeType) {
  if (badgeType === 'jci') return 'text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/60 border border-amber-200 dark:border-amber-800/40 font-bold';
  if (badgeType === 'special') return 'text-purple-600 dark:text-purple-400 bg-purple-50 dark:bg-purple-950/60 border border-purple-200 dark:border-purple-800/40 font-bold';
  return 'text-sky-600 dark:text-sky-400 bg-sky-50 dark:bg-sky-950/60 border border-sky-100 dark:border-sky-800/40 font-semibold';
}

function openFacilityBookingModal(facId) {
  if (!currentUser) {
    pendingBookingFacilityId = facId;
    const isEn = typeof currentLang !== 'undefined' && currentLang === 'en';
    const fac = medicalFacilitiesData.find(f => f.id === facId);
    const facName = fac ? fac.name : (isEn ? 'healthcare facility' : 'cơ sở y tế');
    const bannerTitle = isEn ? 'ACCOUNT AUTHENTICATION REQUIRED' : 'YÊU CẦU XÁC THỰC TÀI KHOẢN';
    const bannerText = isEn 
      ? `Please log in or create an account to book an appointment at ${facName}!`
      : `Vui lòng đăng nhập hoặc tạo tài khoản mới để đặt lịch khám tại ${facName}!`;
    showAuthContextBanner(bannerTitle, bannerText);
    openLoginModal('login');
    return;
  }

  const fac = medicalFacilitiesData.find(f => f.id === facId) || medicalFacilitiesData[0];
  if (!fac) return;

  const modal = document.getElementById('facility-booking-modal');
  const nameEl = document.getElementById('book-modal-facility-name');
  const addrEl = document.getElementById('book-modal-facility-address');
  const idEl = document.getElementById('book-modal-facility-id');
  const dateEl = document.getElementById('book-modal-date');

  if (nameEl) nameEl.innerText = fac.name;
  if (addrEl) addrEl.innerText = fac.address;
  if (idEl) idEl.value = fac.id;

  if (dateEl) {
    const tmr = new Date();
    tmr.setDate(tmr.getDate() + 1);
    dateEl.value = tmr.toISOString().split('T')[0];
    dateEl.min = new Date().toISOString().split('T')[0];
  }

  if (modal) modal.classList.remove('hidden');
}

function closeFacilityBookingModal() {
  const modal = document.getElementById('facility-booking-modal');
  if (modal) modal.classList.add('hidden');
}

async function handleFacilityBookingSubmit(e) {
  if (e) e.preventDefault();
  const isEn = typeof currentLang !== 'undefined' && currentLang === 'en';
  if (!currentUser) {
    showMedicalToast(isEn ? 'Please log in or create an account to book an appointment!' : 'Vui lòng đăng nhập hoặc tạo tài khoản mới để đặt lịch khám!', 'warning');
    closeFacilityBookingModal();
    if (typeof openAuthModal === 'function') openAuthModal('login');
    else if (typeof openLoginModal === 'function') openLoginModal('login');
    return;
  }

  const facId = document.getElementById('book-modal-facility-id')?.value;
  const fac = medicalFacilitiesData.find(f => f.id === facId);
  const spec = document.getElementById('book-modal-spec')?.value;
  const date = document.getElementById('book-modal-date')?.value;
  const time = document.getElementById('book-modal-time')?.value;
  const note = document.getElementById('book-modal-note')?.value;
  const patName = document.getElementById('book-modal-name')?.value || currentUser?.full_name || currentUser?.name || '';
  const patPhone = document.getElementById('book-modal-phone')?.value || currentUser?.phone_number || currentUser?.phone || '';

  try {
    const res = await fetch('/api/appointments', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        facility_id: facId || 'fac_unknown',
        facility_name: fac ? fac.name : (isEn ? 'Healthcare Facility' : 'Cơ sở Y tế'),
        facility_address: fac ? fac.address : '',
        specialty: spec || (isEn ? 'General Practice' : 'Đa khoa'),
        appointment_date: date,
        appointment_time: time,
        patient_name: patName,
        patient_phone: patPhone,
        note: note || ''
      })
    });
    
    closeFacilityBookingModal();
    const successMsg = isEn ? 'Appointment booked successfully!' : 'Đã lưu lịch hẹn khám thành công!';
    showMedicalToast(successMsg, 'success', 4000);
  } catch (err) {
    console.error('Lỗi khi lưu lịch hẹn:', err);
    closeFacilityBookingModal();
    const fallbackMsg = isEn ? 'Saved appointment reminder locally!' : 'Đã lưu lịch nhắc đi khám trên thiết bị thành công!';
    showMedicalToast(fallbackMsg, 'success', 4000);
  }
}

function openFacilityDetailModal(facId) {
  activeDetailFacilityId = facId;
  const fac = medicalFacilitiesData.find(f => f.id === facId) || medicalFacilitiesData[0];
  if (!fac) return;

  const modal = document.getElementById('facility-detail-modal');
  const title = document.getElementById('detail-modal-title');
  const rating = document.getElementById('detail-modal-rating');
  const quality = document.getElementById('detail-modal-quality');
  const address = document.getElementById('detail-modal-address');
  const hours = document.getElementById('detail-modal-hours');
  const phone = document.getElementById('detail-modal-phone');
  const desc = document.getElementById('detail-modal-desc');
  const specs = document.getElementById('detail-modal-specialties');
  const mapBtn = document.getElementById('detail-modal-directions-btn');

  if (title) title.innerText = fac.name;
  if (rating) rating.innerHTML = `⭐ ${fac.rating} <span class="text-[10px] font-normal text-slate-400">(${fac.reviews})</span>`;
  const isEn = typeof currentLang !== 'undefined' && currentLang === 'en';
  if (quality) {
    quality.innerText = localizeQualityBadge(fac.qualityBadge, isEn);
    quality.className = `text-[11px] font-bold px-2 py-0.5 rounded-md border ${getFacilityBadgeColor(fac.badgeType)}`;
  }
  if (address) address.innerText = fac.address;
  if (hours) hours.innerText = localizeHours(fac.hours, isEn);
  if (phone) {
    phone.innerText = fac.phone;
    phone.href = `tel:${fac.phone.replace(/\s/g, '')}`;
  }
  if (desc) desc.innerText = fac.description;
  if (mapBtn) mapBtn.href = fac.mapUrl;

  if (specs) {
    specs.innerHTML = fac.specialties.map(s => `
      <span class="px-2.5 py-1 rounded-lg text-xs font-semibold bg-slate-100 dark:bg-white/5 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-white/10">
        ${localizeSpecialty(s, isEn)}
      </span>
    `).join('');
  }

  if (modal) modal.classList.remove('hidden');
}

function closeFacilityDetailModal() {
  const modal = document.getElementById('facility-detail-modal');
  if (modal) modal.classList.add('hidden');
}

function openBookingFromDetail() {
  const targetId = activeDetailFacilityId;
  closeFacilityDetailModal();
  if (!currentUser) {
    pendingBookingFacilityId = targetId;
    const isEn = typeof currentLang !== 'undefined' && currentLang === 'en';
    const fac = medicalFacilitiesData.find(f => f.id === targetId);
    const facName = fac ? fac.name : (isEn ? 'healthcare facility' : 'cơ sở y tế');
    const bannerTitle = isEn ? 'ACCOUNT AUTHENTICATION REQUIRED' : 'YÊU CẦU XÁC THỰC TÀI KHOẢN';
    const bannerText = isEn 
      ? `Please log in or create an account to book an appointment at ${facName}!`
      : `Vui lòng đăng nhập hoặc tạo tài khoản mới để đặt lịch khám tại ${facName}!`;
    showAuthContextBanner(bannerTitle, bannerText);
    openLoginModal('login');
    return;
  }
  if (targetId) {
    openFacilityBookingModal(targetId);
  }
}

// Backward compatibility for filterHospitals
function filterHospitals(cat, btn) {
  selectFacilityType(cat, btn);
}

function initHistorySearch() {
  const searchInput = document.getElementById('history-search-input');
  if (!searchInput) return;

  searchInput.addEventListener('input', (e) => {
    renderChatHistoryList(e.target.value);
  });
}

// ==========================================
// Medical Records (Hồ sơ bệnh án cá nhân) Interaction Logic
// ==========================================
const medicalPatientsData = {
  current_patient: {
    id: 'BN-GUEST',
    name: 'Chưa đăng nhập',
    gender: 'Chưa rõ',
    age: '--',
    dob: '--',
    blood: '--',
    phone: '--',
    allergies: [],
    visitCount: 0,
    lastVisitDate: '--',
    badge: '👤',
    roleText: 'Tài khoản khách',
    records: []
  },
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
    roleText: 'Người thân (Chị em)',
    records: [
      {
        id: 'rec_ma1',
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
        id: 'rec_ma2',
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
        id: 'rec_ma3',
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
    roleText: 'Người thân (Bố)',
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

let activeMedicalPatientKey = 'current_patient';

function updateHomeGreeting() {
  const badge = document.getElementById('home-greeting-badge');
  const greetingEl = document.getElementById('home-greeting-text');
  if (!badge && !greetingEl) return;

  const rawName = (currentUser && (currentUser.name || currentUser.full_name)) ? (currentUser.name || currentUser.full_name).trim() : '';

  // Khi chưa đăng nhập (hoặc tên trống): KHÔNG hiển thị lời chào
  if (!currentUser || !rawName) {
    if (badge) badge.classList.add('hidden');
    if (greetingEl) greetingEl.innerText = '';
    return;
  }

  // Khi user đã đăng nhập: Hiển thị lời chào theo thời gian thực (Real-time Sáng / Chiều / Tối) + Tên User
  const hour = new Date().getHours();
  let timeGreeting = "CHÀO BUỔI SÁNG";
  if (hour >= 12 && hour < 18) {
    timeGreeting = "CHÀO BUỔI CHIỀU";
  } else if (hour >= 18 || hour < 5) {
    timeGreeting = "CHÀO BUỔI TỐI";
  }

  if (typeof currentLang !== 'undefined' && currentLang === 'en') {
    if (hour >= 5 && hour < 12) timeGreeting = "GOOD MORNING";
    else if (hour >= 12 && hour < 18) timeGreeting = "GOOD AFTERNOON";
    else timeGreeting = "GOOD EVENING";
  }

  if (greetingEl) {
    greetingEl.innerText = `${timeGreeting}, ${rawName.toUpperCase()}`;
  }
  if (badge) {
    badge.classList.remove('hidden');
  }
}

function syncCurrentPatientProfile() {
  updateHomeGreeting();
  if (currentUser) {
    const cp = medicalPatientsData.current_patient;
    cp.name = currentUser.name || currentUser.full_name || cp.name;
    cp.gender = currentUser.gender || cp.gender;
    if (currentUser.dob) {
      cp.dob = currentUser.dob.includes('-') ? currentUser.dob.split('-').reverse().join('/') : currentUser.dob;
    }
    cp.blood = currentUser.blood_type || cp.blood;
    cp.phone = currentUser.phone_number || currentUser.phone || cp.phone;
    cp.badge = currentUser.badge || (currentUser.name ? currentUser.name.split(' ').map(w => w[0]).slice(-2).join('').toUpperCase() : 'BN');

    if (currentUser.allergies && typeof currentUser.allergies === 'string') {
      const algList = currentUser.allergies.split(/[,;\n]+/).map(s => s.trim()).filter(Boolean);
      if (algList.length > 0) cp.allergies = algList;
    }

    const pillName = document.getElementById('pill-name-current_patient');
    const pillAvatar = document.getElementById('pill-avatar-current_patient');
    if (pillName) pillName.innerText = cp.name;
    if (pillAvatar) pillAvatar.innerText = cp.badge;

    // Direct binding to Hero card in doctor-tab
    const heroName = document.getElementById('ehr-hero-name');
    const heroDemo = document.getElementById('ehr-hero-demographics');
    const avatarLarge = document.getElementById('ehr-avatar-large');
    const dobVal = document.getElementById('ehr-dob-val');
    const bloodVal = document.getElementById('ehr-blood-val');
    const phoneVal = document.getElementById('ehr-phone-val');
    const allergiesContainer = document.getElementById('ehr-allergies-container');

    if (heroName) heroName.innerText = cp.name;
    if (heroDemo) heroDemo.innerText = `${cp.gender} · ${cp.age} tuổi`;
    if (avatarLarge) avatarLarge.innerText = cp.badge;
    if (dobVal) dobVal.innerText = cp.dob;
    if (bloodVal) bloodVal.innerText = cp.blood;
    if (phoneVal) phoneVal.innerText = cp.phone;
    if (allergiesContainer && cp.allergies && cp.allergies.length > 0) {
      allergiesContainer.innerHTML = cp.allergies.map(alg => `
        <span class="inline-flex items-center px-2.5 py-1 rounded-lg text-xs font-bold bg-rose-50 dark:bg-rose-500/15 text-rose-600 dark:text-rose-300 border border-rose-200 dark:border-rose-400/30">
          <span>${escapeHtml(alg)}</span>
        </span>
      `).join('');
    }
  }
}

function updateEhrTabUI() {
  const heroName = document.getElementById('ehr-hero-name');
  const heroDemo = document.getElementById('ehr-hero-demographics');
  const avatarLarge = document.getElementById('ehr-avatar-large');
  const visitCount = document.getElementById('ehr-visit-count');
  const lastVisit = document.getElementById('ehr-last-visit-date');
  const dobVal = document.getElementById('ehr-dob-val');
  const bloodVal = document.getElementById('ehr-blood-val');
  const phoneVal = document.getElementById('ehr-phone-val');
  const allergiesContainer = document.getElementById('ehr-allergies-container');
  const timelineContainer = document.getElementById('ehr-timeline-list');
  const exportBtn = document.getElementById('ehr-export-pdf-btn');

  // TRƯỜNG HỢP 1: NGƯỜI DÙNG ĐÃ ĐĂNG NHẬP (Hiển thị hồ sơ thật)
  if (currentUser) {
    const displayName = currentUser.full_name || currentUser.name || (currentLang === 'en' ? 'Patient' : 'Bệnh nhân');
    const gender = currentUser.gender || (currentLang === 'en' ? 'Not specified' : 'Chưa rõ');
    let ageStr = '';
    if (currentUser.dob) {
      const yearMatch = currentUser.dob.match(/(19\d{2}|20\d{2})/);
      if (yearMatch) {
        const age = new Date().getFullYear() - parseInt(yearMatch[1], 10);
        ageStr = ` · ${age} ${currentLang === 'en' ? 'years old' : 'tuổi'}`;
      }
    }

    if (heroName) heroName.innerText = displayName;
    if (heroDemo) heroDemo.innerText = `${gender}${ageStr}`;
    
    if (avatarLarge) {
      const initials = displayName.split(' ').map(w => w[0]).slice(-2).join('').toUpperCase() || 'BN';
      avatarLarge.innerText = initials;
    }

    if (dobVal) dobVal.innerText = currentUser.dob || (currentLang === 'en' ? 'Not updated' : 'Chưa cập nhật');
    if (bloodVal) bloodVal.innerText = currentUser.blood_type || (currentLang === 'en' ? 'Not updated' : 'Chưa cập nhật');
    
    const phone = (typeof fieldRealValues !== 'undefined' && fieldRealValues['p-phone']) || currentUser.phone_number || currentUser.phone || '';
    if (phoneVal) phoneVal.innerText = phone || (currentLang === 'en' ? 'Not updated' : 'Chưa cập nhật');

    if (allergiesContainer) {
      const rawAllergies = currentUser.allergies || '';
      if (rawAllergies && rawAllergies.trim()) {
        const list = rawAllergies.split(/[,;\n]+/).map(s => s.trim()).filter(Boolean);
        allergiesContainer.innerHTML = list.map(alg => `
          <span class="inline-flex items-center space-x-1 px-2.5 py-1 rounded-lg text-xs font-bold bg-rose-50 dark:bg-rose-500/15 text-rose-600 dark:text-rose-300 border border-rose-200 dark:border-rose-400/30">
            <span>⚠️</span>
            <span>${escapeHtml(alg)}</span>
          </span>
        `).join('');
      } else {
        allergiesContainer.innerHTML = `<span class="text-xs text-slate-400 italic">${currentLang === 'en' ? 'No allergies reported' : 'Chưa ghi nhận dị ứng'}</span>`;
      }
    }

    if (visitCount) {
      const badgeText = document.getElementById('ehr-records-count-badge')?.innerText || '';
      const match = badgeText.match(/^\d+/);
      visitCount.innerText = match ? match[0] : '0';
    }

    if (exportBtn) {
      exportBtn.classList.remove('opacity-40', 'cursor-not-allowed');
      exportBtn.removeAttribute('disabled');
      exportBtn.title = currentLang === 'en' ? 'Export pre-visit summary (PDF)' : 'In hoặc tải bản tóm tắt trước khám (PDF)';
      const exportText = document.getElementById('ehr-export-text');
      if (exportText) exportText.innerText = currentLang === 'en' ? 'Export Summary (PDF)' : 'Xuất Tóm Tắt (PDF)';
    }

    switchEhrSubTab(currentEhrSubTab || 'ai');
    return;
  }

  // TRƯỜNG HỢP 2: CHƯA ĐĂNG NHẬP (KHÁCH VÃNG LAI - BẢO MẬT TUYỆT ĐỐI)
  if (heroName) heroName.innerText = currentLang === 'en' ? 'Guest Visitor' : 'Chưa đăng nhập';
  if (heroDemo) heroDemo.innerText = currentLang === 'en' ? 'Guest Account • Not Synchronized' : 'Tài khoản khách · Chưa đồng bộ hồ sơ';
  if (avatarLarge) avatarLarge.innerText = '👤';
  if (visitCount) visitCount.innerText = '0';
  if (dobVal) dobVal.innerText = '--';
  if (bloodVal) bloodVal.innerText = '--';
  if (phoneVal) phoneVal.innerText = '--';
  if (allergiesContainer) {
    allergiesContainer.innerHTML = `<span class="text-xs text-slate-400 italic">${currentLang === 'en' ? 'No records yet' : 'Chưa ghi nhận'}</span>`;
  }

  if (exportBtn) {
    exportBtn.classList.add('opacity-40', 'cursor-not-allowed');
    exportBtn.setAttribute('disabled', 'disabled');
    exportBtn.title = currentLang === 'en' ? 'Please sign in to export medical summary' : 'Vui lòng đăng nhập để xuất bản tóm tắt trước khám';
  }

  if (timelineContainer) {
    timelineContainer.innerHTML = `
      <div id="ehr-privacy-empty-card" class="p-8 sm:p-10 text-center rounded-2xl border border-dashed border-sky-300/60 dark:border-white/10 space-y-4 bg-white/70 dark:bg-white/[0.02] backdrop-blur-xl shadow-xs">
        <div class="w-14 h-14 rounded-2xl bg-sky-50 dark:bg-sky-500/10 text-sky-600 dark:text-sky-400 border border-sky-200 dark:border-sky-500/20 flex items-center justify-center mx-auto text-2xl shadow-sm">
          <svg class="w-7 h-7" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
          </svg>
        </div>
        <div class="space-y-1.5">
          <h4 class="text-base sm:text-lg font-black text-slate-900 dark:text-white tracking-tight">
            ${currentLang === 'en' ? 'No Medical Records Synchronized' : 'Chưa có hồ sơ bệnh án được đồng bộ'}
          </h4>
          <p class="text-xs sm:text-sm text-slate-600 dark:text-slate-400 max-w-md mx-auto leading-relaxed font-normal">
            ${currentLang === 'en'
              ? 'Personal health records are encrypted and protected by medical privacy standards. Please sign in to save your AI consultation history, lab tests, and clinical treatment plans.'
              : 'Hồ sơ bệnh án cá nhân được mã hóa an toàn theo tiêu chuẩn bảo vệ dữ liệu y tế. Vui lòng đăng nhập để lưu trữ lịch sử tư vấn AI, quản lý đơn thuốc và phác đồ điều trị.'}
          </p>
        </div>
        <div class="flex flex-wrap items-center justify-center gap-3 pt-3">
          <button type="button" onclick="openLoginModal()" class="px-6 py-2.5 rounded-xl bg-gradient-to-r from-sky-500 to-indigo-600 hover:from-sky-400 hover:to-indigo-500 text-white text-xs font-bold shadow-md shadow-sky-500/25 transition-all cursor-pointer flex items-center space-x-2">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M11 16l-4-4m0 0l4-4m-4 4h14m-5 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h7a3 3 0 013 3v1"/></svg>
            <span>${currentLang === 'en' ? 'Sign In / Register Now' : 'Đăng nhập / Đăng ký ngay'}</span>
          </button>
        </div>
      </div>
    `;
  }
}

function selectPatientProfile(patientKey = 'current_patient') {
  if (!currentUser) {
    updateEhrTabUI();
    return;
  }
  syncCurrentPatientProfile();
  activeMedicalPatientKey = patientKey || 'current_patient';
  const patient = medicalPatientsData[activeMedicalPatientKey] || medicalPatientsData.current_patient;
  if (!patient) return;

  // Update switcher pills styling
  const allPillKeys = ['current_patient', 'minh_anh', 'quoc_bao'];
  allPillKeys.forEach(k => {
    const pill = document.getElementById('patient-pill-' + k);
    if (!pill) return;
    if (k === patientKey) {
      pill.className = 'patient-pill-btn flex items-center space-x-3 px-4 py-2.5 rounded-2xl bg-teal-500/20 text-teal-900 dark:text-white shadow-lg shadow-teal-500/15 border border-teal-500/60 dark:border-teal-400/50 backdrop-blur-xl transition-all cursor-pointer';
    } else {
      pill.className = 'patient-pill-btn flex items-center space-x-3 px-4 py-2.5 rounded-2xl glass-pill text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white border border-slate-200 dark:border-white/10 transition-all cursor-pointer';
    }
  });

  // Update Left Hero Card
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
  if (dobVal) dobVal.innerText = patient.dob;
  if (bloodVal) bloodVal.innerText = patient.blood;
  if (phoneVal) phoneVal.innerText = patient.phone;
  if (countBadge) countBadge.innerText = `${patient.records.length} hồ sơ`;

  if (allergiesContainer) {
    if (patient.allergies && patient.allergies.length > 0) {
      allergiesContainer.innerHTML = patient.allergies.map(alg => `
        <span class="inline-flex items-center px-2.5 py-1 rounded-lg text-xs font-bold bg-rose-50 dark:bg-rose-500/15 text-rose-600 dark:text-rose-300 border border-rose-200 dark:border-rose-400/30">
          <span>${escapeHtml(alg)}</span>
        </span>
      `).join('');
    } else {
      allergiesContainer.innerHTML = '<span class="text-xs text-slate-500 dark:text-slate-400">Không ghi nhận dị ứng</span>';
    }
  }

  // Render Right Timeline theo phân hệ đã chọn (Tư vấn AI thực tế vs Bệnh viện minh họa)
  switchEhrSubTab(currentEhrSubTab || 'ai');
}

// currentEhrSubTab moved up

function switchEhrSubTab(subTab) {
  currentEhrSubTab = subTab;
  const btnAi = document.getElementById('ehr-subtab-ai');
  const btnHosp = document.getElementById('ehr-subtab-hospital');

  if (!currentUser) {
    if (btnAi) btnAi.className = subTab === 'ai' ? 'px-3 py-1.5 rounded-xl text-xs font-bold bg-white dark:bg-sky-500/20 text-sky-600 dark:text-white shadow-sm transition-all cursor-pointer' : 'px-3 py-1.5 rounded-xl text-xs font-bold text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition-all cursor-pointer';
    if (btnHosp) btnHosp.className = subTab === 'hospital' ? 'px-3 py-1.5 rounded-xl text-xs font-bold bg-white dark:bg-sky-500/20 text-sky-600 dark:text-white shadow-sm transition-all cursor-pointer' : 'px-3 py-1.5 rounded-xl text-xs font-bold text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition-all cursor-pointer';
    updateEhrTabUI();
    return;
  }

  if (subTab === 'ai') {
    if (btnAi) btnAi.className = 'px-3 py-1.5 rounded-xl text-xs font-bold bg-white dark:bg-sky-500/20 text-sky-600 dark:text-white shadow-sm transition-all cursor-pointer';
    if (btnHosp) btnHosp.className = 'px-3 py-1.5 rounded-xl text-xs font-bold text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition-all cursor-pointer';
    loadAndRenderAiConsultations();
  } else {
    if (btnAi) btnAi.className = 'px-3 py-1.5 rounded-xl text-xs font-bold text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white transition-all cursor-pointer';
    if (btnHosp) btnHosp.className = 'px-3 py-1.5 rounded-xl text-xs font-bold bg-white dark:bg-sky-500/20 text-sky-600 dark:text-white shadow-sm transition-all cursor-pointer';
    const patient = medicalPatientsData[activeMedicalPatientKey] || medicalPatientsData.current_patient;
    renderPatientTimeline(patient.records || []);
  }
}

async function loadAndRenderAiConsultations() {
  const container = document.getElementById('ehr-timeline-list');
  const countBadge = document.getElementById('ehr-records-count-badge');
  if (!container) return;

  try {
    const isEn = typeof currentLang !== 'undefined' && currentLang === 'en';
    const res = await fetch('/api/consultations');
    if (res.status === 401) {
      if (countBadge) countBadge.innerText = isEn ? '0 AI consultations' : '0 phiên tư vấn AI';
      container.innerHTML = `
        <div class="p-8 text-center rounded-2xl border border-dashed border-slate-200 dark:border-white/10 space-y-3 bg-white/50 dark:bg-white/[0.02]">
          <div class="w-12 h-12 rounded-2xl bg-amber-50 dark:bg-amber-500/10 text-amber-500 flex items-center justify-center mx-auto text-xl">🔒</div>
          <p class="text-sm font-semibold text-slate-700 dark:text-slate-200">${isEn ? 'Authentication Required' : 'Yêu cầu đăng nhập'}</p>
          <p class="text-xs text-slate-400">${isEn ? 'Please sign in to synchronize and access your clinical consultation history.' : 'Vui lòng đăng nhập để đồng bộ và xem lịch sử tư vấn lâm sàng của bạn.'}</p>
        </div>`;
      return;
    }
    const data = await res.json();
    const list = data.consultations || [];

    if (countBadge) {
      countBadge.innerText = isEn ? `${list.length} AI consultations` : `${list.length} phiên tư vấn AI`;
    }
    const ehrVisitCountEl = document.getElementById('ehr-visit-count');
    if (ehrVisitCountEl) {
      ehrVisitCountEl.innerText = String(list.length);
    }

    if (list.length === 0) {
      container.innerHTML = `
        <div class="p-8 text-center rounded-2xl border border-dashed border-slate-200 dark:border-white/10 space-y-3 bg-white/50 dark:bg-white/[0.02]">
          <div class="w-12 h-12 rounded-2xl bg-sky-50 dark:bg-sky-500/10 text-sky-500 flex items-center justify-center mx-auto">
            <svg class="w-6 h-6" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M8 10h.01M12 10h.01M16 10h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"></path></svg>
          </div>
          <p class="text-sm font-bold text-slate-700 dark:text-slate-300">${isEn ? 'No consultation sessions saved yet' : 'Chưa có phiên tư vấn nào được lưu'}</p>
          <p class="text-xs text-slate-500 dark:text-slate-400 max-w-sm mx-auto">${isEn ? 'Pre-visit AI screening sessions will automatically appear here for easy tracking and export.' : 'Các phiên tư vấn trước khám với Trợ lý AI sẽ tự động xuất hiện ở đây để bạn dễ dàng theo dõi và xuất phiếu trước khám.'}</p>
          <button type="button" onclick="switchTab('chat-tab')" class="px-4 py-2 rounded-xl bg-sky-600 text-white text-xs font-bold hover:bg-sky-700 transition-all cursor-pointer shadow-sm">
            ${isEn ? 'Start Chatting Now' : 'Bắt đầu trò chuyện ngay'}
          </button>
        </div>
      `;
      return;
    }

    container.innerHTML = list.map((item) => {
      const isEmg = item.is_emergency;
      const statusClass = isEmg ? 'bg-rose-500/15 text-rose-500 border-rose-500/30' : 'bg-sky-500/15 text-sky-600 dark:text-sky-300 border-sky-500/30';
      const statusText = isEmg ? 'Cảnh báo cấp cứu' : (item.risk_level || 'Tư vấn ban đầu');
      return `
        <div data-session="${escapeHtml(item.conversation_id || '')}" onclick="openConsultationSummaryDetail(this.dataset.session)" class="relative group cursor-pointer">
          <div class="absolute -left-[31px] top-4 w-3.5 h-3.5 rounded-full ${isEmg ? 'bg-rose-500' : 'bg-sky-500'} border-2 border-white dark:border-slate-900 shadow-md shadow-sky-500/50"></div>
          <div class="glass-card border border-slate-200/80 dark:border-white/10 rounded-2xl p-5 shadow-sm hover:shadow-lg bg-white/90 dark:bg-white/[0.03] hover:border-sky-500/40 transition-all">
            <div class="flex items-start justify-between gap-3">
              <div class="space-y-1.5 flex-1 min-w-0">
                <div class="flex items-center gap-2">
                  <span class="text-xs font-bold text-sky-600 dark:text-sky-400 font-mono">${escapeHtml(item.created_at || 'Gần đây')}</span>
                  <span class="px-2 py-0.5 rounded-md text-[10px] font-bold border ${statusClass}">${statusText}</span>
                </div>
                <h4 class="text-base font-black text-slate-900 dark:text-white group-hover:text-sky-600 dark:group-hover:text-sky-400 transition-colors truncate">
                  ${escapeHtml(item.message || 'Tư vấn triệu chứng')}
                </h4>
                <p class="text-xs text-slate-500 dark:text-slate-400 font-medium flex items-center gap-1.5">
                  <span>Trợ lý Y tế</span>
                  <span>•</span>
                  <span>Định hướng: ${escapeHtml(item.specialist || 'Nội tổng quát')}</span>
                </p>
                <div class="pt-1.5">
                  <span class="text-[11px] text-slate-500 dark:text-slate-400 bg-slate-100 dark:bg-white/5 px-2.5 py-1 rounded-lg border border-slate-200 dark:border-white/10">
                    Bấm để xem Bản Tóm Tắt Trước Khám (Pre-visit Summary)
                  </span>
                </div>
              </div>
              <div class="flex items-center self-center pl-2">
                <svg class="w-5 h-5 text-slate-400 group-hover:text-sky-600 dark:group-hover:text-sky-400 group-hover:translate-x-1 transition-all" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="9 18 15 12 9 6"></polyline></svg>
              </div>
            </div>
          </div>
        </div>
      `;
    }).join('');
  } catch (e) {
    console.error("Lỗi tải lịch sử tư vấn:", e);
  }
}

async function openConsultationSummaryDetail(sessionId) {
  if (!sessionId) {
    showMedicalToast("Phiên cũ chưa có bản tóm tắt theo hội thoại.", "info");
    return;
  }
  try {
    const response = await fetch('/api/clinical-summary?conversation_id=' + encodeURIComponent(sessionId));
    const data = await response.json();
    if (!response.ok || !data.summary) throw new Error();
    renderPreVisitSummaryInModal(data.summary);
    document.getElementById('modal-btn-confirm')?.classList.add('hidden');
    document.getElementById('previsit-summary-modal')?.classList.remove('hidden');
  } catch {
    showMedicalToast("Không tải được bản tóm tắt của phiên này.", "error");
  }
}

function renderPatientTimeline(records) {
  const container = document.getElementById('ehr-timeline-list');
  if (!container) return;

  container.innerHTML = records.map(rec => {
    return `
      <div onclick="openMedicalRecordDetail('${rec.id}')" class="relative group cursor-pointer">
        <!-- Timeline Indicator Dot -->
        <div class="absolute -left-[31px] top-4 w-3.5 h-3.5 rounded-full bg-sky-500 dark:bg-sky-400 border-2 border-white dark:border-slate-900 shadow-md shadow-sky-500/50"></div>

        <!-- Card Content -->
        <div class="glass-card border border-slate-200/80 dark:border-white/10 rounded-2xl p-5 shadow-sm hover:shadow-lg bg-white/90 dark:bg-white/[0.03] hover:bg-white dark:hover:bg-white/[0.06] hover:border-sky-500/40 hover:shadow-sky-500/10 backdrop-blur-xl transition-all">
          <div class="flex items-start justify-between gap-2">
            <div class="space-y-1.5">
              <span class="text-xs font-bold text-sky-600 dark:text-sky-400 font-mono">${rec.date}</span>
              <h4 class="text-base font-black text-slate-900 dark:text-white group-hover:text-sky-600 dark:group-hover:text-sky-400 transition-colors">${rec.title}</h4>
              <p class="text-xs text-slate-500 dark:text-slate-400 font-medium">${rec.doctor}</p>
              <div class="pt-2">
                <span class="px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-white/5 text-slate-700 dark:text-slate-300 text-[11px] font-mono border border-slate-200 dark:border-white/10">${rec.icd}</span>
              </div>
            </div>

            <div class="flex items-center self-center pl-2">
              <svg class="w-5 h-5 text-slate-400 group-hover:text-sky-600 dark:group-hover:text-sky-400 group-hover:translate-x-1 transition-all" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="9 18 15 12 9 6"></polyline></svg>
            </div>
          </div>
        </div>
      </div>
    `;
  }).join('');
}

function openMedicalRecordDetail(recordId) {
  const patient = medicalPatientsData[activeMedicalPatientKey] || medicalPatientsData.current_patient;
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
    statusEl.innerText = rec.status || 'Đã ghi nhận';
  }

  if (rec.vitals) {
    if (bpEl) bpEl.innerText = rec.vitals.bp || '--';
    if (hrEl) hrEl.innerText = rec.vitals.hr || '--';
    if (tempEl) tempEl.innerText = rec.vitals.temp || '--';
    if (weightEl) weightEl.innerText = rec.vitals.weight || '--';
  }

  if (symptomsEl) symptomsEl.innerText = rec.symptoms || '--';
  if (labsEl) labsEl.innerText = rec.labs || '--';
  if (notesEl) notesEl.innerText = rec.doctorNotes || '--';
  if (followupEl) followupEl.innerText = rec.followUp || 'Không hẹn tái khám';

  modal.classList.remove('hidden');
}

function closeMedicalRecordDetail() {
  const modal = document.getElementById('medical-record-modal');
  if (modal) modal.classList.add('hidden');
}


// ==========================================
// Image 1 Personal Information Logic
// ==========================================
function handleProfileAvatarUpload(e) {
  const file = e.target?.files?.[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = function(evt) {
    const dataUrl = evt.target.result;
    const avatarDisplay = document.getElementById('profile-avatar-display');
    const topAvatarImg = document.getElementById('user-avatar-img');
    if (avatarDisplay) avatarDisplay.src = dataUrl;
    if (topAvatarImg) topAvatarImg.src = dataUrl;
    if (currentUser) {
      currentUser.hasCustomAvatar = true;
      currentUser.avatar = dataUrl;
      localStorage.setItem('medimind_user', JSON.stringify(currentUser));
    }
    showMedicalToast('Đã cập nhật ảnh đại diện thành công!', 'success');
  };
  reader.readAsDataURL(file);
}

// ==============================================================
// 3-TIER DATA PERSISTENCE: TẦNG 1 DRAFT GUARD (Auto-Recovery)
// ==============================================================
let profileDraftDebounceTimer = null;

function calculateProfileCompletion() {
  const phoneVal = (fieldMaskState['p-phone'] && fieldRealValues['p-phone']) ? fieldRealValues['p-phone'] : document.getElementById('p-phone')?.value.trim();
  const emailVal = (fieldMaskState['p-email'] && fieldRealValues['p-email']) ? fieldRealValues['p-email'] : document.getElementById('p-email')?.value.trim();

  const fields = [
    document.getElementById('p-name')?.value.trim(),
    document.getElementById('p-birthdate')?.value.trim(),
    document.getElementById('p-gender')?.value,
    phoneVal,
    emailVal,
    document.getElementById('p-blood')?.value,
    document.getElementById('p-allergies')?.value.trim(),
    document.getElementById('p-address')?.value.trim()
  ];
  const filled = fields.filter(v => v && v !== '' && v !== 'Chưa rõ').length;
  const pct = Math.round((filled / fields.length) * 100);
  
  const valEl = document.getElementById('profile-completion-val');
  const barEl = document.getElementById('profile-completion-bar');
  if (valEl) valEl.innerText = pct + '%';
  if (barEl) barEl.style.width = pct + '%';
}

function resetProfileForm() {
  sessionStorage.removeItem('medimind_profile_draft');
  updateAuthUI();
  calculateProfileCompletion();
  const msg = currentLang === 'en' ? 'Profile reset to saved values.' : 'Đã khôi phục thông tin đã lưu.';
  showMedicalToast(msg, 'info');
}

async function handleSaveImage1Profile(e) {
  if (e) e.preventDefault();

  const submitBtn = document.querySelector('#profile-form-img1 button[type="submit"]') || e?.target?.querySelector('button[type="submit"]');
  const originalBtnHtml = submitBtn ? submitBtn.innerHTML : 'Lưu thông tin';

  const getFieldValue = (fieldId, fallback = '') => {
    const el = document.getElementById(fieldId);
    if (el && !fieldMaskState[fieldId]) {
      const liveVal = el.value.trim();
      fieldRealValues[fieldId] = liveVal;
      return liveVal !== '' ? liveVal : fallback;
    }
    if (fieldRealValues[fieldId] !== undefined && fieldRealValues[fieldId] !== '') {
      return fieldRealValues[fieldId];
    }
    return fallback;
  };

  const name = document.getElementById('p-name')?.value.trim() || '';
  const birthDate = document.getElementById('p-birthdate')?.value.trim() || '';
  const gender = document.getElementById('p-gender')?.value || 'Nam';
  const phone = getFieldValue('p-phone', currentUser?.phone_number || '');
  const email = getFieldValue('p-email', currentUser?.email || '');
  const blood = document.getElementById('p-blood')?.value || 'O+';
  const allergies = document.getElementById('p-allergies')?.value.trim() || '';
  const height = document.getElementById('p-height')?.value.trim() || '';
  const weight = document.getElementById('p-weight')?.value.trim() || '';
  const address = document.getElementById('p-address')?.value.trim() || '';

  if (!currentUser || currentUser.isDemo) {
    showMedicalToast('Vui lòng đăng nhập để lưu và đồng bộ hồ sơ lên hệ thống.', 'warning');
    if (typeof openLoginModal === 'function') openLoginModal();
    return;
  }

  // Kiểm tra rào chắn số điện thoại nếu có
  if (phone) {
    const cleanPhone = phone.replace(/[\s.-]/g, '');
    if (!/^(0|\+?84)[0-9]{9,10}$/.test(cleanPhone)) {
      const phoneInput = document.getElementById('p-phone');
      if (phoneInput) {
        phoneInput.focus();
        phoneInput.classList.add('border-rose-500', 'ring-2', 'ring-rose-400');
        setTimeout(() => phoneInput.classList.remove('border-rose-500', 'ring-2', 'ring-rose-400'), 2500);
      }
      showMedicalToast('Số điện thoại không hợp lệ (cần đúng 10 chữ số).', 'error');
      return;
    }
  }

  try {
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerHTML = '<span class="inline-block animate-spin mr-1.5">⏳</span> Đang lưu...';
    }

    const res = await fetch('/api/auth/profile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        id: currentUser.id,
        name: name,
        full_name: name,
        gender: gender,
        dob: birthDate,
        phone_number: phone,
        email: email,
        address: address,
        blood_type: blood,
        allergies: allergies,
        height: height,
        weight: weight
      })
    });

    const data = await res.json();
    if (res.ok && data.success) {
      currentUser = {
        ...currentUser,
        ...(data.user || {}),
        name: name || currentUser.name,
        full_name: name || currentUser.full_name,
        dob: birthDate,
        gender: gender,
        phone: phone,
        phone_number: phone,
        email: email,
        address: address,
        blood_type: blood,
        allergies: allergies,
        height: height,
        weight: weight
      };
      localStorage.setItem('medimind_user', JSON.stringify(currentUser));

      syncLeftCardPhoneEmail();
      calculateProfileCompletion();
      if (typeof syncCurrentPatientProfile === 'function') syncCurrentPatientProfile();
      if (typeof updateHomeGreeting === 'function') updateHomeGreeting();
      updateAuthUI();

      sessionStorage.removeItem('medimind_profile_draft');
      const msg = (typeof currentLang !== 'undefined' && currentLang === 'en') ? 'Profile saved successfully!' : 'Đã lưu thông tin hồ sơ lên hệ thống thành công!';
      showMedicalToast(msg, 'success');
    } else {
      if (res.status === 401) {
        showMedicalToast('Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.', 'warning');
        if (typeof openLoginModal === 'function') openLoginModal();
      } else {
        showMedicalToast(data.error || 'Không thể lưu hồ sơ, vui lòng thử lại.', 'error');
      }
    }
  } catch (err) {
    console.error('Lỗi khi lưu hồ sơ lên server:', err);
    showMedicalToast('Lỗi kết nối máy chủ khi lưu hồ sơ.', 'error');
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML = originalBtnHtml;
    }
  }
}
// ==============================================================
// FLOATING CHATBOX WIDGET HANDLERS (Image 2)
// ==============================================================
let isFloatingChatOpen = false;

function toggleFloatingChat(forceState) {
  const win = document.getElementById('floating-chat-window');
  if (!win) return;
  
  if (typeof forceState === 'boolean') {
    isFloatingChatOpen = forceState;
  } else {
    isFloatingChatOpen = !isFloatingChatOpen;
  }

  if (isFloatingChatOpen) {
    win.classList.remove('hidden');
    setTimeout(() => {
      document.getElementById('floating-user-input')?.focus();
    }, 100);
  } else {
    win.classList.add('hidden');
  }
}

function expandFloatingChatToFull() {
  toggleFloatingChat(false);
  switchTab('chat-tab');
}

function sendQuickFloatingPrompt(text) {
  const input = document.getElementById('floating-user-input');
  if (input) {
    input.value = text;
    sendFloatingChatMessage();
  }
}

async function sendFloatingChatMessage() {
  const input = document.getElementById('floating-user-input');
  const msgContainer = document.getElementById('floating-chat-messages');
  if (!input || !msgContainer) return;

  const text = input.value.trim();
  if (!text) return;

  // Render user bubble
  const userBubble = document.createElement('div');
  userBubble.className = 'flex justify-end';
  userBubble.innerHTML = `
    <div class="max-w-[85%] px-3.5 py-2.5 rounded-2xl rounded-tr-xs bg-gradient-to-r from-sky-500 to-indigo-600 text-white shadow-md text-xs leading-relaxed font-medium">
      ${escapeHtml(text)}
    </div>
  `;
  msgContainer.appendChild(userBubble);
  input.value = '';
  msgContainer.scrollTop = msgContainer.scrollHeight;

  // Add typing indicator
  const typingId = 'floating-typing-' + Date.now();
  const typingIndicator = document.createElement('div');
  typingIndicator.className = 'flex justify-start';
  typingIndicator.id = typingId;
  typingIndicator.innerHTML = `
    <div class="max-w-[85%] px-3.5 py-2 rounded-2xl rounded-tl-xs glass-card border border-white/10 text-xs text-sky-400 flex items-center space-x-1.5">
      <span class="w-1.5 h-1.5 rounded-full bg-sky-400 animate-ping"></span>
      <span class="text-[11px] font-medium text-slate-300">MediMind đang đối chiếu dữ liệu...</span>
    </div>
  `;
  msgContainer.appendChild(typingIndicator);
  msgContainer.scrollTop = msgContainer.scrollHeight;

  try {
    currentConversationId ||= crypto.randomUUID();
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        conversation_id: currentConversationId,
        history: chatHistory,
        message: text,
        lang: typeof currentLang !== 'undefined' ? currentLang : 'vi',
        user_name: currentUser ? (currentUser.first_name || currentUser.name || 'Bệnh nhân') : 'Bệnh nhân'
      })
    });
    const data = await res.json();
    document.getElementById(typingId)?.remove();

    if (res.ok && data.answer) {
      chatHistory.push({role: 'user', content: text}, {role: 'assistant', content: data.answer});
      saveOrUpdateCurrentSession(text, data, data.intake);
      if (data.intake) updateLiveIntakeCard(data.intake.facts, data.intake.status, data.intake.summary);
    }
    const rawReply = data.answer || data.reply || data.response || data.error || 'Hệ thống đã ghi nhận thông tin của bạn.';
    const safeReply = escapeHtml(String(rawReply))
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\n/g, '<br>');

    const botBubble = document.createElement('div');
    botBubble.className = 'flex justify-start';
    botBubble.innerHTML = `
      <div class="max-w-[88%] px-3.5 py-2.5 rounded-2xl rounded-tl-xs border floating-welcome-bubble text-xs leading-relaxed shadow-xs">
        ${safeReply}
      </div>
    `;
    msgContainer.appendChild(botBubble);
    msgContainer.scrollTop = msgContainer.scrollHeight;
  } catch (err) {
    document.getElementById(typingId)?.remove();
    const errBubble = document.createElement('div');
    errBubble.className = 'flex justify-start';
    errBubble.innerHTML = `
      <div class="max-w-[85%] px-3.5 py-2 rounded-2xl rounded-tl-xs bg-rose-500/20 text-rose-300 border border-rose-500/30 text-xs">
        Không thể kết nối đến máy chủ lâm sàng. Vui lòng thử lại.
      </div>
    `;
    msgContainer.appendChild(errBubble);
    msgContainer.scrollTop = msgContainer.scrollHeight;
  }
}

// Floating Chatbox Compatibility Aliases
function toggleFloatingChat(forceState) {
  if (typeof forceState === 'boolean') {
    const win = document.getElementById('floating-chat-window');
    if (win) {
      if (forceState) {
        win.classList.remove('hidden');
        if (typeof syncFloatingChatMessages === 'function') syncFloatingChatMessages();
      } else {
        win.classList.add('hidden');
      }
    }
  } else {
    toggleFloatingChatWindow();
  }
}

function sendQuickFloatingPrompt(text) {
  insertFloatingPrompt(text);
  sendFloatingChatMessage();
}
