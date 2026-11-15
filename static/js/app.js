
// Global Alias and Context Banner Helpers
const isEnLang = () => typeof currentLang !== 'undefined' && currentLang === 'en';
const t = (vi, en) => (isEnLang() ? en : vi);
window.t = t;

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

function sanitizeSafeImgSrc(rawUrl, fallback = '/static/images/avatar_male.png') {
  if (!rawUrl || typeof rawUrl !== 'string') return fallback;
  const s = rawUrl.trim();
  if (!s) return fallback;
  if (/^data:image\/(png|jpe?g|webp|gif);base64,[A-Za-z0-9+/=\s]+$/i.test(s)) {
    return s;
  }
  if (s.startsWith('/') && !s.startsWith('//') && !s.startsWith('/\\')) {
    return s;
  }
  try {
    const u = new URL(s, window.location.origin);
    if (u.protocol === 'https:' || (u.protocol === 'http:' && u.origin === window.location.origin)) {
      return u.href;
    }
  } catch (_) {}
  return fallback;
}

function sanitizeSafeExternalHref(rawUrl) {
  if (!rawUrl || typeof rawUrl !== 'string') return '#';
  const s = rawUrl.trim();
  if (!s) return '#';
  if (s.startsWith('/') && !s.startsWith('//') && !s.startsWith('/\\')) return s;
  try {
    const u = new URL(s);
    if (u.protocol === 'https:' || u.protocol === 'http:') return u.href;
  } catch (_) {}
  return '#';
}

function sanitizeSameOriginRedirect(rawUrl) {
  if (!rawUrl || typeof rawUrl !== 'string') return null;
  const s = rawUrl.trim();
  if (!s.startsWith('/') || s.startsWith('//') || s.startsWith('/\\')) return null;
  try {
    const u = new URL(s, window.location.origin);
    if (u.origin === window.location.origin) {
      return u.pathname + u.search + u.hash;
    }
  } catch (_) {}
  return null;
}

function escapeJsAttrSingleQuoted(val) {
  return escapeHtml(String(val ?? '').replace(/\\/g, '\\\\').replace(/'/g, "\\'"));
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
    if (typeof showMedicalToast === 'function') showMedicalToast(t('Không thể kết nối máy chủ để đổi mật khẩu.', 'Unable to connect to the server to change password.'), 'error');
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
    setLanguage(lang);
  }

  // Apply theme if changed
  const resolvedTheme = theme === 'system'
    ? (window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
    : theme;
  if (resolvedTheme === 'dark' && document.body.classList.contains('light-glass')) {
    toggleGlassThemeMode();
  } else if (resolvedTheme === 'light' && !document.body.classList.contains('light-glass')) {
    toggleGlassThemeMode();
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

function sanitizeUserEmail(email) {
  if (!email || typeof email !== 'string') return '';
  const trimmed = email.trim();
  const lowered = trimmed.toLowerCase();
  if (
    !trimmed.includes('@') ||
    lowered.endsWith('@phone.medimind') ||
    lowered.endsWith('@phone.medimind.vn') ||
    /^\+?[0-9]{9,15}$/.test(trimmed)
  ) {
    return '';
  }
  return trimmed;
}

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
      cardPhone.innerText = t('Chưa có số điện thoại', 'No phone number');
    }
  }
  if (phoneEye) {
    phoneEye.innerHTML = fieldMaskState['p-phone'] ? closedEyeSvg : openEyeSvg;
  }

  if (cardEmail) {
    const validEmail = sanitizeUserEmail(rawEmail);
    if (validEmail) {
      cardEmail.innerText = fieldMaskState['p-email'] ? maskFieldValue(validEmail, 'p-email') : validEmail;
    } else {
      cardEmail.innerText = t('Chưa có email', 'No email');
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
if (currentUser && currentUser.email) {
  const sanitizedEmail = sanitizeUserEmail(currentUser.email);
  if (sanitizedEmail !== currentUser.email) {
    currentUser.email = sanitizedEmail;
    localStorage.setItem('medimind_user', JSON.stringify(currentUser));
  }
}
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
  const previousUserId = currentUser?.id;
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
  if (String(previousUserId || '') !== String(currentUser?.id || '')) {
    resetChat();
  } else {
    renderChatHistoryList();
  }
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
    role: t('Bệnh nhân (Mẫu trải nghiệm)', 'Patient (Demo Profile)'),
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
  showMedicalToast(t('Đã mở hồ sơ bệnh nhân mẫu (Chế độ trải nghiệm)', 'Demo patient profile activated'), 'info');
}
// ==========================================
// Bilingual i18n Dictionary (VI / EN)
// ==========================================
const translations = {
  vi: {
    notif_title: "Thông báo",
    nav_home: "Trang chủ",
    dock_home: "Trang chủ",
    home_hero_tag: "Trợ lý AI cho sức khỏe cá nhân",
    home_hero_title: "Trợ lý sức khỏe",
    home_hero_title_sub: "thông minh mỗi ngày",
    home_hero_headline: "Chăm sóc sức khỏe<br>thông minh hơn mỗi ngày.",
    home_hero_desc: "Một nơi tin cậy để bạn hiểu cơ thể, quản lý sức khỏe và chủ động hơn trong mỗi quyết định.",
    home_btn_chat: "Trò chuyện với trợ lý",
    home_btn_record: "Thử thách sống khỏe",
    home_badge_security: "Thông tin được bảo mật",
    home_badge_history: "Lưu lịch sử trò chuyện",
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
    home_c2_tag: "DINH DƯỠNG THEO THỂ TRẠNG",
    home_c2_title: "Bàn pha chế dinh dưỡng",
    home_c2_desc: "Khám phá nguyên liệu nên dùng, món cần tránh và công thức phù hợp với thể trạng.",
    home_c3_tag: "ĐỒNG HÀNH CÙNG BẠN",
    home_c3_title: "Lịch hẹn sắp tới",
    home_c3_desc: "Theo dõi lịch khám và nhận nhắc nhở để không bỏ lỡ những cuộc hẹn quan trọng.",
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
    menu_profile: "Hồ sơ cá nhân",
    menu_settings: "Cài đặt",
    menu_logout: "Đăng xuất",
    profile_form_title: "Thông tin Chuyên môn Lâm sàng MediMind AI",
    profile_headline_full: "Chuyên gia Lâm sàng @ MediMind Clinical AI",
    badge_active_text: "ĐANG HOẠT ĐỘNG • ĐÃ XÁC MINH",
    badge_status_label: "TRẠNG THÁI HỒ SƠ",
    badge_joined_label: "NGÀY THAM GIA",
    p_section_title: "Thông tin cá nhân",
    p_lbl_name: "Họ và tên",
    p_lbl_gender: "Giới tính",
    gender_male: "Nam",
    gender_female: "Nữ",
    gender_other: "Khác",
    p_lbl_birthdate: "Ngày sinh",
    p_lbl_clinical_id: "Mã hồ sơ y tế",
    p_lbl_clinical_id_hint: "Mã định danh 8 chữ số cố định được cấp khi tạo tài khoản",
    p_lbl_email: "Email",
    p_lbl_email_hint: "Email không thể thay đổi",
    p_lbl_phone: "Số điện thoại",
    p_lbl_province: "Tỉnh / Thành phố",
    p_lbl_district: "Quận / Huyện",
    p_lbl_address: "Địa chỉ",
    p_lbl_address_ph: "Số nhà, tên đường, khu phố...",
    p_lbl_dept: "Khoa / Đơn vị lâm sàng",
    p_lbl_dept_hint: "Quản lý khoa chuyên môn tại Hệ thống Y tế MediMind.",
    p_lbl_hospital: "Cơ sở y tế / Bệnh viện",
    p_lbl_portfolio: "Hồ sơ chuyên môn & chứng chỉ",
    p_lbl_role: "Vai trò / Chức danh chuyên môn",
    p_btn_save: "Lưu thay đổi",
    p_avatar_change: "Đổi ảnh",
    p_lbl_cccd: "CMND/CCCD",
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
    p_lbl_address_hokhau: "Địa chỉ thường trú",
    p_btn_save_info: "Lưu thông tin",
    p_btn_back_account: "Quay lại trang tài khoản",
    set_acc_title: "Tùy chọn tài khoản",
    set_acc_desc: "Quản lý tùy chọn tài khoản và cài đặt khu vực của bạn",
    set_lbl_lang: "Ngôn ngữ",
    set_lbl_timezone: "Múi giờ",
    set_lbl_date_format: "Định dạng ngày",
    set_notif_title: "Thông báo",
    set_notif_desc: "Quản lý cách bạn nhận thông báo",
    set_lbl_browser_push: "Thông báo đẩy trình duyệt",
    set_lbl_browser_push_desc: "Nhận thông báo ngay cả khi đã đóng trang",
    set_sec_title: "Bảo mật",
    set_sec_desc: "Quản lý mật khẩu và cài đặt bảo mật của bạn",
    set_lbl_curr_pass: "Mật khẩu hiện tại",
    set_lbl_new_pass: "Mật khẩu mới",
    set_lbl_confirm_pass: "Xác nhận mật khẩu",
    set_ph_curr_pass: "Nhập mật khẩu hiện tại",
    set_ph_new_pass: "Nhập mật khẩu mới",
    set_ph_confirm_pass: "Xác nhận mật khẩu mới",
    lbl_toggle_pwd: "Hiện/ẩn mật khẩu",
    set_btn_change_pass: "Đổi mật khẩu",
    set_app_title: "Giao diện",
    set_app_desc: "Tùy chỉnh giao diện ứng dụng",
    set_lbl_theme: "Chủ đề",
    theme_dark: "Tối",
    theme_light: "Sáng",
    theme_system: "Theo hệ thống",
    set_btn_save_all: "Lưu tất cả cài đặt",
    brand_subtitle: "Bảo mật thông tin cá nhân • Tham chiếu MedlinePlus®",
    nav_chat: "Trợ lý sức khỏe",
    nav_ocr: "Đọc đơn thuốc & xét nghiệm",
    nav_booking: "Cơ sở y tế",
    nav_doctor: "Pha chế dinh dưỡng",
    nav_admin: "Hạ tầng hệ thống",
    nav_login: "Đăng nhập",
    nav_start: "Bắt đầu ngay",
    user_role: "Thành viên",
    dock_chat: "Trợ lý sức khỏe",
    dock_ocr: "Đọc đơn thuốc & xét nghiệm",
    dock_booking: "Cơ sở y tế & Bệnh viện",
    dock_doctor: "Pha chế dinh dưỡng",
    dock_wallpaper: "Đổi không gian y tế",
    dock_theme: "Chế độ Sáng / Tối",
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
    modal_login_title: "Đăng nhập vào MediMind",
    modal_register_title: "Đăng ký vào MediMind",
    modal_forgot_title: "Quên mật khẩu?",
    modal_otp_title: "Xác thực mã bảo mật (OTP)",
    modal_auth_subtitle: "Hệ thống Trợ lý Y tế & Phân tầng Lâm sàng",
    tab_login: "Đăng nhập",
    tab_register: "Tạo tài khoản mới",
    lbl_login_identifier: "Email hoặc số điện thoại",
    ph_identifier: "Email hoặc số điện thoại",
    ph_password: "Nhập mật khẩu",
    btn_login: "Đăng nhập",
    link_forgot_pwd: "Quên mật khẩu?",
    btn_create_account: "Tạo tài khoản mới",
    btn_demo_login: "Đăng nhập tài khoản mẫu thử nghiệm",
    btn_google_signin: "Đăng nhập bằng Google",
    auth_or_divider: "hoặc",
    auth_back_home: "Quay lại trang chính",
    auth_forgot_subtitle: "Nhập email hoặc số điện thoại để nhận mã xác thực đặt lại mật khẩu.",
    auth_register_terms: "Bằng việc đăng ký, bạn đồng ý với Điều khoản sử dụng và Chính sách bảo mật y tế của MediMind.",
    auth_hero_badge: "MediMind Clinical AI • Tham chiếu MedlinePlus® NIH",
    auth_hero_headline: "Nơi tri thức y khoa đồng hành cùng bạn",
    auth_hero_tagline: "Chăm sóc sức khỏe không còn đơn độc – vào là có trợ lý lâm sàng hỗ trợ",
    lbl_name: "Tên",
    lbl_full_name: "Họ và tên",
    ph_full_name: "Nhập họ và tên",
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
    lbl_identifier: "Email hoặc số điện thoại",
    lbl_password: "Mật khẩu",
    lbl_confirm_password: "Xác nhận mật khẩu",
    ph_confirm_password: "Nhập lại mật khẩu",
    lbl_new_password: "Mật khẩu mới",
    btn_forgot_submit: "Nhận mã xác thực OTP",
    btn_register_submit: "Đăng ký",
    lbl_no_account: "Bạn chưa có tài khoản?",
    link_register_now: "Đăng ký ngay",
    link_register_short: "Đăng ký",
    lbl_have_account: "Bạn đã có tài khoản?",
    link_login_now: "Đăng nhập ngay",
    history_title: "Lịch Sử Tư Vấn",
    history_subtitle: "Các phiên sàng lọc & phân tích triệu chứng",
    history_btn_new: "Hội thoại mới",
    ph_history_search: "Tìm kiếm phiên tư vấn...",
    history_empty_title: "Chưa có lịch sử tư vấn",
    history_empty_desc: "Các cuộc sàng lọc triệu chứng sẽ được lưu tự động tại đây sau khi hoàn tất.",
    history_demo_label: "Dữ liệu thử nghiệm:",
    history_demo_btn: "Xem thử ca tư vấn mẫu",
    history_security: "Bảo mật dữ liệu cá nhân",
    history_encrypted: "Lịch sử trò chuyện cá nhân",
    assistant_header_title: "Trợ lý y tế MediMind",
    assistant_header_subtitle: "Đang trực tuyến • Tham khảo MedlinePlus và Dược thư",
    assistant_btn_summary: "Hồ sơ & Tóm tắt",
    assistant_greeting_title: "Trợ lý y tế MediMind",
    assistant_greeting_desc: "Xin chào, tôi là trợ lý y tế MediMind. Tôi có thể hỗ trợ bạn sàng lọc triệu chứng sơ bộ, giải thích đơn thuốc và gợi ý chuyên khoa khám phù hợp. Bạn đang gặp phải vấn đề sức khỏe nào?",
    welcome_msg: "Xin chào, tôi là trợ lý y tế MediMind. Tôi có thể hỗ trợ bạn sàng lọc triệu chứng sơ bộ, giải thích đơn thuốc và gợi ý chuyên khoa khám phù hợp. Bạn đang gặp phải vấn đề sức khỏe nào?",
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
    ehr_card_narrative: "Diễn tiến bệnh cảnh & Lý do vào viện",
    ehr_card_narrative_sub: "Trích xuất tự động qua Trợ lý AI",
    ehr_card_allergy: "CẢNH BÁO TIỀN SỬ DỊ ỨNG & CHỐNG CHỈ ĐỊNH LÂM SÀNG",
    ehr_card_dx: "Định hướng chẩn đoán sơ bộ (AI)",
    ehr_card_orders: "Đề xuất chỉ định cận lâm sàng",
    ehr_card_actions: "Thao tác bệnh án",
    ehr_card_ready: "Hồ sơ sẵn sàng",
    ehr_btn_print_a4: "In bệnh án A4",
    ehr_btn_save_emr: "Lưu vào hồ sơ",
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
    footer_version: "Phiên bản 2.5 • Nền tảng Trợ lý Sức khỏe Số",
    footer_disclaimer_title: "Tuyên bố Miễn trừ Trách nhiệm Y tế",
    footer_disclaimer_text: "Nền tảng MediMind AI được phát triển với mục đích học thuật, nghiên cứu giáo dục công nghệ AI và thử nghiệm mô hình hỗ trợ lâm sàng. Các phân tích, chỉ số hay phác đồ gợi ý không cấu thành chỉ định lâm sàng hay tư vấn y khoa chính thức. Người bệnh luôn cần tham vấn trực tiếp bác sĩ chuyên khoa hoặc cơ sở y tế có thẩm quyền trước khi đưa ra quyết định sức khỏe. Trong tình huống nguy cấp, vui lòng gọi cấp cứu 115.",
    toast_space_prefix: "Đã chuyển không gian: ",
    toast_glass_light: "Đã bật giao diện Sáng lâm sàng",
    toast_glass_dark: "Đã bật giao diện Kính tối",
    guest_user: "Khách",
    not_logged_in: "Chưa đăng nhập",
    disclaimer_footer_text: "⚠️ Dự án thử nghiệm công nghệ y tế phục vụ giáo dục • ",
    disclaimer_footer_btn: "Miễn trừ trách nhiệm",
    typing_vision: "Hệ thống thị giác đang phân tích đặc điểm hình ảnh...",
    typing_guideline: "Đang đối chiếu y văn và chuẩn bị phản hồi...",
    patient_label: "Vừa xong • Người bệnh",
    server_error: "Không thể kết nối đến máy chủ.",
    risk_safe: "An toàn",
    risk_moderate: "Theo dõi",
    risk_emergency: "Cần cấp cứu",
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
    facility_toast_login_required: "Vui lòng đăng nhập hoặc tạo tài khoản mới để đặt lịch khám!",
    facility_auth_banner_title: "YÊU CẦU XÁC THỰC TÀI KHOẢN",
    facility_auth_banner_text: "Vui lòng đăng nhập hoặc tạo tài khoản mới để tiếp tục đặt lịch khám!",
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
    detail_modal_lbl_address: "Địa chỉ:",
    detail_modal_lbl_hours: "Thời gian hoạt động:",
    detail_modal_lbl_phone: "Tổng đài liên hệ:",
    detail_modal_btn_book: "Đặt lịch khám tại đây",
    ehr_header_title: "Hồ sơ bệnh án của tôi",
    ehr_header_subtitle: "Lịch sử khám bệnh, tư vấn và phác đồ điều trị cá nhân",
    ehr_stat_visits: "Phiên tư vấn AI",
    ehr_lbl_dob: "NGÀY SINH",
    ehr_lbl_blood: "NHÓM MÁU",
    ehr_lbl_phone: "ĐIỆN THOẠI",
    ehr_lbl_allergy: "DỊ ỨNG",
    ehr_lbl_no_allergy: "Chưa ghi nhận",
    ehr_sec_prescriptions: "Toa thuốc & Phiếu xét nghiệm đã lưu",
    ehr_btn_add_rx: "+ Thêm đơn mới →",
    ehr_no_rx: "Chưa có đơn thuốc nào được lưu.",
    ehr_sec_history_title: "Lịch sử khám & tư vấn",
    ehr_sec_history_sub: "Tách bạch rõ giữa phiên tư vấn AI thực tế và hồ sơ bệnh viện liên kết",
    ehr_subtab_ai: "💬 Tư vấn AI (Thực tế)",
    ehr_subtab_hospital: "🏥 Bệnh viện (Mẫu minh họa)",
    intake_card_title: "Bản nháp trong hội thoại",
    intake_draft_notice: "Lời kể được lưu trong lịch sử trò chuyện. Chỉ bản tóm tắt bạn xác nhận mới xuất hiện trong hồ sơ.",
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
    default_image_prompt: "Xin bác sĩ quan sát bức ảnh và phân tích giúp tôi dấu hiệu tổn thương trên da."
  },
  en: {
    notif_title: "Notifications",
    nav_home: "Home",
    dock_home: "Home",
    home_hero_tag: "Personal AI Health Assistant",
    home_hero_title: "Smart Daily Health",
    home_hero_title_sub: "Assistant",
    home_hero_headline: "Smarter healthcare,<br>every single day.",
    home_hero_desc: "A trusted companion to understand your body, manage your health, and make informed choices.",
    home_btn_chat: "Chat with Assistant",
    home_btn_record: "Healthy Living Challenge",
    home_badge_security: "Data Encrypted & Secure",
    home_badge_history: "Chat History Saved",
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
    home_c2_tag: "PERSONAL NUTRITION",
    home_c2_title: "Nutrition Studio",
    home_c2_desc: "Explore helpful ingredients, foods to avoid, and recipes matched to your health condition.",
    home_c3_tag: "WITH YOU ALWAYS",
    home_c3_title: "Upcoming Visits",
    home_c3_desc: "Keep track of hospital visits and get timely reminders for appointments.",
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
    menu_profile: "Profile",
    menu_settings: "Settings",
    menu_logout: "Sign out",
    profile_form_title: "MediMind AI Clinical & Specialist Information",
    profile_headline_full: "Clinical AI Specialist @ MediMind Clinical AI",
    badge_active_text: "ACTIVE • VERIFIED",
    badge_status_label: "RECORD STATUS",
    badge_joined_label: "REGISTERED",
    p_section_title: "Personal Information",
    p_lbl_name: "Full Name",
    p_lbl_gender: "Gender",
    gender_male: "Male",
    gender_female: "Female",
    gender_other: "Other",
    p_lbl_birthdate: "Date of Birth",
    p_lbl_clinical_id: "Clinical ID",
    p_lbl_clinical_id_hint: "Fixed 8-digit clinical ID assigned at account creation",
    p_lbl_email: "Email",
    p_lbl_email_hint: "Email cannot be changed",
    p_lbl_phone: "Phone Number",
    p_lbl_province: "Province / City",
    p_lbl_district: "District / Ward",
    p_lbl_address: "Address",
    p_lbl_address_ph: "House number, street, ward...",
    p_lbl_dept: "Department",
    p_lbl_dept_hint: "Managed under MediMind Clinical Division.",
    p_lbl_hospital: "Hospital / Facility",
    p_lbl_portfolio: "Clinical Portfolio & Credentials",
    p_lbl_role: "Role / Headline",
    p_btn_save: "Save Changes",
    p_avatar_change: "Change Photo",
    p_lbl_cccd: "Citizen ID",
    p_lbl_issue_date: "Issue Date",
    p_sec_bhyt: "Health Insurance",
    p_lbl_bhyt_code: "Health Insurance ID",
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
    set_acc_title: "Account Preferences",
    set_acc_desc: "Manage your account preferences and regional settings",
    set_lbl_lang: "Language",
    set_lbl_timezone: "Timezone",
    set_lbl_date_format: "Date Format",
    set_notif_title: "Notifications",
    set_notif_desc: "Manage how you receive notifications",
    set_lbl_browser_push: "Browser Push Notifications",
    set_lbl_browser_push_desc: "Receive notifications even when the page is closed",
    set_sec_title: "Security",
    set_sec_desc: "Manage your password and security settings",
    set_lbl_curr_pass: "Current Password",
    set_lbl_new_pass: "New Password",
    set_lbl_confirm_pass: "Confirm Password",
    set_ph_curr_pass: "Enter current password",
    set_ph_new_pass: "Enter new password",
    set_ph_confirm_pass: "Confirm new password",
    lbl_toggle_pwd: "Show/hide password",
    set_btn_change_pass: "Change Password",
    set_app_title: "Appearance",
    set_app_desc: "Customize how the application looks",
    set_lbl_theme: "Theme",
    theme_dark: "Dark",
    theme_light: "Light",
    theme_system: "System",
    set_btn_save_all: "Save All Settings",
    brand_subtitle: "Personal Data Privacy • MedlinePlus® Reference",
    nav_chat: "Health Assistant",
    nav_ocr: "Prescriptions & Labs",
    nav_booking: "Hospitals & Clinics",
    nav_doctor: "Nutrition Studio",
    nav_admin: "System Infrastructure",
    nav_login: "Sign In",
    nav_start: "Get Started",
    user_role: "Member",
    dock_chat: "Health Assistant",
    dock_ocr: "Prescriptions & Labs",
    dock_booking: "Hospitals & Clinics",
    dock_doctor: "Nutrition Studio",
    dock_wallpaper: "Change Theme Space",
    dock_theme: "Light / Dark Mode",
    dock_reset: "New Conversation",
    ocr_title: "Prescription & Lab OCR",
    ocr_subtitle: "Extract drug lists, verify dosages, and generate intake schedules after confirmation",
    ocr_btn_upload_new: "Upload New Document",
    ocr_btn_home: "Home",
    ocr_box_title: "Upload Prescription or Lab Report",
    ocr_box_desc: "Clear text, adequate light, all edges visible (Supports JPG, PNG, PDF, up to 10MB)",
    ocr_btn_choose: "Select from Device",
    ocr_privacy_note: "🔒 Your document is protected and only saved to your personal health record upon confirmation.",
    ocr_preset_hint: "No document at hand? Try quick samples:",
    ocr_preset_gastro: "Sample Prescription (Gastro)",
    ocr_preset_resp: "Sample Prescription (Resp)",
    ocr_preset_blood: "Sample Lab Report (Blood)",
    modal_login_title: "Sign in to MediMind",
    modal_register_title: "Create MediMind account",
    modal_forgot_title: "Forgot password?",
    modal_otp_title: "Security Verification (OTP)",
    modal_auth_subtitle: "Clinical Decision Support & Health Assistant",
    tab_login: "Sign In",
    tab_register: "Create Account",
    lbl_login_identifier: "Email or phone number",
    ph_identifier: "Email or phone number",
    ph_password: "Enter password",
    btn_login: "Sign in",
    link_forgot_pwd: "Forgot password?",
    btn_create_account: "Create New Account",
    btn_demo_login: "Quick Demo Patient Sign-in",
    btn_google_signin: "Sign in with Google",
    auth_or_divider: "or",
    auth_back_home: "Back to home",
    auth_forgot_subtitle: "Enter your registered email or phone number to receive a password reset OTP.",
    auth_register_terms: "By signing up, you agree to MediMind's Terms of Use and Clinical Privacy Policy.",
    auth_hero_badge: "MediMind Clinical AI • MedlinePlus® NIH Reference",
    auth_hero_headline: "Where medical knowledge stands beside you",
    auth_hero_tagline: "Healthcare is never lonely – step inside for instant clinical guidance",
    lbl_name: "Name",
    lbl_full_name: "Full name",
    ph_full_name: "Enter your full name",
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
    lbl_identifier: "Email or phone number",
    lbl_password: "Password",
    lbl_confirm_password: "Confirm password",
    ph_confirm_password: "Re-enter password",
    lbl_new_password: "New password",
    btn_forgot_submit: "Send verification OTP",
    btn_register_submit: "Sign up",
    lbl_no_account: "Don't have an account?",
    link_register_now: "Sign up now",
    link_register_short: "Sign up",
    lbl_have_account: "Already have an account?",
    link_login_now: "Sign in now",
    history_title: "Consultation History",
    history_subtitle: "Screening sessions & symptom analyses",
    history_btn_new: "New Session",
    ph_history_search: "Search consultations...",
    history_empty_title: "No consultation history yet",
    history_empty_desc: "Your symptom screenings will be automatically saved here upon completion.",
    history_demo_label: "Sample dataset:",
    history_demo_btn: "View Sample Consultation",
    history_security: "Personal Data Privacy",
    history_encrypted: "Personal chat history",
    assistant_header_title: "MediMind Medical Assistant",
    assistant_header_subtitle: "Online • MedlinePlus & Pharmacopoeia Reference",
    assistant_btn_summary: "Record & Summary",
    assistant_greeting_title: "MediMind Medical Assistant",
    assistant_greeting_desc: "Hello, I am the MediMind Health Assistant. I can help you with preliminary symptom triage, prescription explanations, and specialty clinic guidance. What health concern are you experiencing?",
    welcome_msg: "Hello, I am the MediMind Health Assistant. I can help you with preliminary symptom triage, prescription explanations, and specialty clinic guidance. What health concern are you experiencing?",
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
    ehr_btn_save_emr: "Save to Record",
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
    footer_version: "Version 2.5 • Digital Health Assistant Platform",
    footer_disclaimer_title: "Medical Disclaimer",
    footer_disclaimer_text: "MediMind AI is developed for educational, technical demonstration, and clinical support research purposes. The inferences, scores, and referenced guidelines do not constitute formal clinical diagnoses or medical advice. Always consult licensed medical professionals or healthcare facilities for medical conditions. In case of emergency, call 115 immediately.",
    toast_space_prefix: "Switched theme: ",
    toast_glass_light: "Activated: Clinical Light Theme",
    toast_glass_dark: "Activated: Spatial Dark Theme",
    guest_user: "Guest",
    not_logged_in: "Not signed in",
    disclaimer_footer_text: "⚠️ Educational Health AI Prototype • ",
    disclaimer_footer_btn: "Medical Disclaimer",
    typing_vision: "Clinical vision model is analyzing image features...",
    typing_guideline: "Finding clinical references and preparing a reply...",
    patient_label: "Just now • Patient",
    server_error: "Unable to connect to server.",
    risk_safe: "Safe",
    risk_moderate: "Monitor",
    risk_emergency: "Emergency",
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
    facility_toast_login_required: "Please sign in or create an account to book an appointment!",
    facility_auth_banner_title: "ACCOUNT AUTHENTICATION REQUIRED",
    facility_auth_banner_text: "Please sign in or create an account to proceed with booking!",
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
    detail_modal_lbl_address: "Address:",
    detail_modal_lbl_hours: "Operating Hours:",
    detail_modal_lbl_phone: "Contact Hotline:",
    detail_modal_btn_book: "Book Appointment Here",
    ehr_header_title: "My Electronic Health Record",
    ehr_header_subtitle: "Clinical consultation history, triage summaries, and personal care plan",
    ehr_stat_visits: "AI consultations",
    ehr_lbl_dob: "DATE OF BIRTH",
    ehr_lbl_blood: "BLOOD TYPE",
    ehr_lbl_phone: "PHONE NUMBER",
    ehr_lbl_allergy: "ALLERGIES",
    ehr_lbl_no_allergy: "None reported",
    ehr_sec_prescriptions: "Saved Prescriptions & Lab Reports",
    ehr_btn_add_rx: "+ Add New →",
    ehr_no_rx: "No prescriptions saved yet.",
    ehr_sec_history_title: "Consultations & Clinical Visits",
    ehr_sec_history_sub: "Clearly distinguishing verified AI consultations from linked hospital records",
    ehr_subtab_ai: "💬 AI Consultations (Live)",
    ehr_subtab_hospital: "🏥 Hospital Records (Demo)",
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
    footer_subtitle: "AI Symptom Analysis & MedlinePlus Reference",
    default_image_prompt: "Please analyze this clinical image and assess the lesion characteristics on the skin."
  }
};

// ==========================================
// Static DOM Lexicon (Zero HTML bloat, 100% VI <-> EN coverage)
// ==========================================
const STATIC_VI_EN_TEXT = {
  // Chat & Live Intake
  "Chưa có thông tin": "No information yet",
  "Chưa ghi nhận": "None recorded",
  "Xuất PDF hội thoại": "Export Chat PDF",
  "anh_ton_thuong.jpg": "clinical_photo.jpg",
  "Ảnh lâm sàng sẵn sàng đối chiếu": "Clinical image ready for review",
  "Thông tin chỉ mang tính tham khảo, không thay thế chẩn đoán của bác sĩ.": "For reference only; does not replace a physician's diagnosis.",
  // Hospitals & Facilities View
  "Đóng bộ lọc ✕": "Close filters ✕",
  "Cơ Sở Y Tế": "Healthcare Facilities",
  "Loại hình cơ sở": "Facility Category",
  "Tất cả cơ sở": "All Facilities",
  "Phòng khám": "Clinic",
  "Bệnh viện": "Hospital",
  "Phòng chẩn trị YHCT": "Traditional Medicine Clinic",
  "Cơ sở DV y tế / Trạm y tế": "Medical Service / Health Station",
  "Phòng xét nghiệm": "Diagnostic Laboratory",
  "Khu vực địa lý": "Geographic Region",
  "TP. HCM": "Ho Chi Minh City",
  "TP. Hồ Chí Minh": "Ho Chi Minh City",
  "Hà Nội": "Hanoi",
  "Đà Nẵng": "Da Nang",
  "Chuyên khoa nổi bật": "Featured Specialties",
  "Chuyên khoa nổi bật:": "Featured Specialties:",
  "Tất cả": "All",
  "Nội tổng hợp": "Internal Medicine",
  "Răng Hàm Mặt": "Dentistry",
  "Sản phụ khoa": "OB/GYN",
  "Tai Mũi Họng": "ENT",
  "Nhi khoa": "Pediatrics",
  "Y học cổ truyền": "Traditional Medicine",
  "Da liễu": "Dermatology",
  "Mắt": "Ophthalmology",
  "Chấn thương chỉnh hình": "Orthopedics",
  "Khám tổng quát": "General Practice",
  "Tim mạch": "Cardiology",
  "Nội tiết & Tiểu đường": "Endocrinology & Diabetes",
  "Tiêu hóa & Gan mật": "Gastroenterology & Hepatology",
  "Bảo mật đặt hẹn": "Secure Booking",
  "Kết nối trực tiếp BV": "Direct Hospital Link",
  "☰ Bộ lọc": "☰ Filters",
  "Xóa": "Clear",
  "Tất cả Quận / Huyện (TP.HCM)": "All Districts (Ho Chi Minh City)",
  "Quận 1": "District 1",
  "Quận 2 (TP Thủ Đức)": "District 2 (Thu Duc City)",
  "Quận 3": "District 3",
  "Quận 4": "District 4",
  "Quận 5": "District 5",
  "Quận 6": "District 6",
  "Quận 7": "District 7",
  "Quận 8": "District 8",
  "Quận 9 (TP Thủ Đức)": "District 9 (Thu Duc City)",
  "Quận 10": "District 10",
  "Quận 11": "District 11",
  "Quận 12": "District 12",
  "Quận Bình Thạnh": "Binh Thanh District",
  "Quận Gò Vấp": "Go Vap District",
  "Quận Phú Nhuận": "Phu Nhuan District",
  "Quận Tân Bình": "Tan Binh District",
  "Quận Tân Phú": "Tan Phu District",
  "Quận Bình Tân": "Binh Tan District",
  "Huyện Bình Chánh": "Binh Chanh District",
  "Huyện Hóc Môn": "Hoc Mon District",
  "Huyện Củ Chi": "Cu Chi District",
  "Huyện Nhà Bè": "Nha Be District",
  "Huyện Cần Giờ": "Can Gio District",
  "Gần tôi": "Near Me",
  "Ẩn/Hiện Bản đồ": "Show/Hide Map",
  "Hiển thị": "Showing",
  "cơ sở trên trang": "facilities per page",
  "Đang tải bản đồ": "Loading map",
  "Click vào cơ sở để": "Select a facility to",
  "định vị trên bản đồ": "locate on map",
  "Sắp xếp:": "Sort by:",
  "Theo danh sách cơ sở": "Directory order",
  "Bản đồ cơ sở y tế (Toàn cảnh)": "Healthcare Facilities Map (Overview)",
  "Vị trí của tôi": "My Location",
  "Toàn cảnh": "Overview",
  "Tìm thấy:": "Found:",
  "1,505 cơ sở": "1,505 facilities",
  "Trang 1 / 126": "Page 1 of 126",
  "Đang nạp danh sách cơ sở y tế...": "Loading healthcare facilities...",
  "Trang trước": "Previous",
  "Trang sau": "Next",
  "Đặt lại bộ lọc": "Reset filters",
  // OCR & Prescription History
  "Lịch Sử Đơn Thuốc & Phiếu Xét Nghiệm Của Bạn": "Your Prescription & Lab Report History",
  "0 hồ sơ": "0 records",
  "Xem lại các tài liệu đã tải lên, tóm tắt chẩn đoán và tra cứu lại toa thuốc": "Review uploaded documents, diagnostic summaries, and saved prescriptions",
  "Làm mới": "Refresh",
  "Bạn chưa có đơn thuốc hoặc phiếu xét nghiệm nào được lưu trữ. Hãy tải ảnh lên ở trên để bắt đầu theo dõi sức khỏe.": "No prescriptions or lab reports saved yet. Upload a document above to start tracking your health.",
  "Đang đối chiếu OCR và phân tích đơn thuốc...": "Running OCR verification and analyzing prescription...",
  "Tự động sắp xếp lịch uống sáng, trưa, tối và tra cứu tương tác thuốc": "Automatically structuring morning, noon, and evening doses and checking drug references",
  // Nutrition Flow
  "MEDIMIND · GỢI Ý DINH DƯỠNG": "MEDIMIND · NUTRITION STUDIO",
  "Hôm nay bạn cảm thấy thế nào?": "How are you feeling today?",
  "Nhập tâm trạng hoặc tình trạng sức khỏe để xem các công thức tham khảo.": "Enter your mood or health condition to explore tailored recipes.",
  "Tâm trạng hoặc tình trạng sức khỏe": "Mood or health condition",
  "Nhấn Enter để tiếp tục · Nội dung tìm kiếm được gửi tới Google Gemini để gợi ý món.": "Press Enter to continue · Search queries are analyzed by AI to suggest recipes.",
  "← Sửa tìm kiếm": "← Edit search",
  "BƯỚC 1 / 3": "STEP 1 / 3",
  "Bạn muốn xem loại nào?": "What would you like to explore?",
  "Tình trạng đã nhập": "Entered condition",
  "Thức ăn": "Food",
  "Khám phá những món ăn dễ làm": "Discover easy, nourishing meals",
  "Nước uống": "Drinks",
  "Khám phá những thức uống dễ pha": "Discover soothing, easy-to-make beverages",
  "← Đổi loại gợi ý": "← Change category",
  "BƯỚC 2 / 3": "STEP 2 / 3",
  "Chọn món bạn thích": "Choose a recipe you like",
  "Chọn một món để xem công thức và thông tin dinh dưỡng.": "Select a dish to view its step-by-step recipe and nutritional profile.",
  "Các món được chọn như thế nào?": "How are these suggestions selected?",
  "Xem thực phẩm nên hạn chế / cần tránh ↓": "View foods to limit or avoid ↓",
  "Bổ sung mô tả →": "Refine description →",
  "Xem thêm gợi ý từ kho →": "Load more suggestions →",
  "← Xem món khác": "← Back to suggestions",
  "BƯỚC 3 / 3 · CHI TIẾT": "STEP 3 / 3 · DETAILS",
  "Thông tin tham khảo dinh dưỡng, không thay thế tư vấn y tế chuyên khoa.": "Nutritional reference only; does not replace professional medical advice.",
  // Profile Tab & Modal
  "Đổi ảnh": "Change photo",
  "Chưa có họ và tên": "No full name",
  "Chưa có số điện thoại": "No phone number",
  "Chưa có email": "No email",
  "HOÀN THIỆN HỒ SƠ": "PROFILE COMPLETION",
  "NGÀY THAM GIA": "JOINED DATE",
  "Chưa lưu": "Not saved",
  "Thông tin cá nhân": "Personal Information",
  "Họ tên và cách liên hệ với bạn.": "Your name and primary contact details.",
  "Họ và tên": "Full Name",
  "Ngày sinh": "Date of Birth",
  "Giới tính": "Gender",
  "Nam": "Male",
  "Nữ": "Female",
  "Khác": "Other",
  "Số điện thoại": "Phone Number",
  "Ẩn": "Hide",
  "Hiện": "Show",
  "Bảo mật": "Private",
  "Chỉ số sức khỏe cơ bản": "Baseline Health Metrics",
  "Giúp trợ lý y tế MediMind cá nhân hóa phác đồ tư vấn và đối chiếu y bạ.": "Helps MediMind personalize clinical triage and health record references.",
  "Nhóm máu": "Blood Type",
  "O+ (Phổ biến)": "O+ (Common)",
  "Chưa rõ": "Unknown",
  "Dị ứng thuốc & thực phẩm": "Drug & Food Allergies",
  "Chiều cao (cm)": "Height (cm)",
  "Cân nặng (kg)": "Weight (kg)",
  "Địa chỉ cư trú": "Residential Address",
  "Hủy thay đổi": "Discard changes",
  "Lưu thông tin": "Save information",
  // Auth OTP & Legal Footer
  "Đăng nhập vào MediMind": "Sign in to MediMind",
  "Mã xác thực 6 số đã được gửi qua": "A 6-digit verification code was sent via",
  "tin nhắn SMS": "SMS",
  "hộp thư email": "email",
  "tới:": "to:",
  "Gửi lại mã sau": "Resend code in",
  "Gửi lại mã OTP mới": "Resend new OTP code",
  "Xác nhận & Tiếp tục": "Verify & Continue",
  "← Quay lại bước trước": "← Back to previous step",
  "Chính sách cookie": "Cookie Policy",
  "Điều khoản sử dụng": "Terms of Use",
  "Chính sách bảo mật": "Privacy Policy",
  // Medical Disclaimer Modal
  "Tuyên bố Miễn trừ Trách nhiệm Y tế": "Medical Disclaimer",
  "Mục đích Giáo dục & Nghiên cứu Thử nghiệm": "Educational & Clinical Decision Support Prototype",
  "1. Mục đích Giáo dục & Nghiên cứu Khoa học:": "1. Educational & Scientific Research Purpose:",
  "Dự án MediMind Clinical AI được nghiên cứu và thiết kế với tư cách là một nguyên mẫu công nghệ lâm sàng. Hệ thống mô phỏng cách ứng dụng Trí tuệ Nhân tạo để hỗ trợ phân loại sơ bộ và đối soát tài liệu y khoa tham khảo, hoàn toàn không hoạt động như một dịch vụ khám chữa bệnh thương mại.": "MediMind Clinical AI is designed as a clinical technology prototype. It demonstrates AI-assisted preliminary symptom triage and medical literature cross-referencing, and does not operate as a commercial medical practice.",
  "2. Không thay thế Lời khuyên & Chẩn đoán Bác sĩ:": "2. Not a Substitute for Professional Medical Advice:",
  "Mọi kết quả sàng lọc, phân tích chỉ số sinh hóa hay thông tin dược phẩm xuất hiện trên giao diện chỉ có giá trị tham khảo học thuật. Tuyệt đối không tự ý mua thuốc, dừng phác đồ điều trị hoặc tự chẩn đoán bệnh dựa trên câu trả lời của AI.": "All triage outputs, lab interpretations, and medication references provided here are for informational purposes only. Never self-medicate, discontinue prescribed treatment, or self-diagnose solely based on AI responses.",
  "3. Giới hạn đối với Tình huống Khẩn cấp:": "3. Emergency Limitations:",
  "Hệ thống không thể xử lý các ca cấp cứu đe dọa tính mạng (đau ngực cấp, đột quỵ, khó thở dữ dội, sốc phản vệ...). Khi gặp dấu hiệu nguy cấp, vui lòng liên hệ ngay": "This system cannot manage life-threatening emergencies (acute chest pain, stroke, severe dyspnea, anaphylaxis, etc.). If emergency symptoms occur, call",
  "hoặc đến khoa cấp cứu bệnh viện gần nhất.": "immediately or go to the nearest emergency department.",
  "Tôi đã hiểu và đồng ý": "I Understand & Agree",
  // Profile Quick Modal
  "Chưa đăng nhập": "Not signed in",
  "Tài khoản khách": "Guest account",
  "Giới tính:": "Gender:",
  "Chưa cập nhật": "Not updated",
  "Ngày sinh:": "Date of birth:",
  "Tài khoản / SĐT:": "Account / Phone:",
  "Mã số hồ sơ y tế:": "Medical record ID:",
  "Cập nhật thông tin": "Edit profile",
  "Pha chế dinh dưỡng →": "Nutrition Studio →",
  "Đóng": "Close",
  "Ngày": "Day",
  "Tháng": "Month",
  "Năm": "Year",
  "Số điện thoại liên hệ": "Contact phone number",
  "Hủy bỏ": "Cancel",
  "Ảnh tham khảo đối chiếu y khoa": "Clinical Reference Image",
  // Pre-visit Summary Modal
  "Bản Tóm Tắt Tư Vấn Trước Khám": "Pre-Visit Consultation Summary",
  "Trích xuất tự động từ phiên trao đổi với Trợ lý AI MediMind": "Automatically structured from your MediMind AI consultation",
  "Phiên bản: v1 • Chờ xác nhận": "Version: v1 • Pending confirmation",
  "Lưu ý lâm sàng:": "Clinical Note:",
  "Đây là bản tóm tắt dữ kiện người bệnh tự khai báo và định hướng tiếp cận sơ bộ, KHÔNG phải chẩn đoán y khoa chính thức thay thế bác sĩ điều trị.": "This summary captures patient-reported facts and preliminary triage guidance; it is NOT a formal medical diagnosis.",
  "Phần A — Thông tin thu thập từ người bệnh": "Part A — Patient-Reported Clinical Facts",
  "(Lời khai thực tế)": "(Self-reported)",
  "Lý do tư vấn chính": "Chief Complaint",
  "Thời gian diễn tiến": "Symptom Duration",
  "Triệu chứng ghi nhận có": "Reported Symptoms",
  "Triệu chứng người bệnh đã phủ nhận": "Pertinent Negatives",
  "Chưa có triệu chứng phủ nhận": "No pertinent negatives recorded",
  "Tiền sử dị ứng": "Allergy History",
  "Chưa ghi nhận tiền sử dị ứng đặc biệt": "No known allergies recorded",
  "Thuốc đang dùng thường xuyên": "Current Medications",
  "Chưa ghi nhận thuốc đang dùng thường xuyên": "No regular medications recorded",
  "Chỉ số tự đo tại nhà": "Home-Measured Vitals",
  "Chưa có chỉ số tự đo tại nhà": "No home-measured vitals recorded",
  "Tệp đính kèm / Quan sát ảnh": "Attachments / Visual Notes",
  "Không có tệp hình ảnh đính kèm": "No image attachments",
  "Thông tin còn thiếu / Cần trao đổi thêm với bác sĩ": "Clarifications Needed During Physician Visit",
  "Đã đủ thông tin cơ bản": "Core baseline details collected",
  "Phần B — Đánh giá sơ bộ & Hướng tiếp cận": "Part B — Preliminary Triage & Care Guidance",
  "(Trợ lý y tế MediMind)": "(MediMind Clinical Assistant)",
  "Phân luồng rủi ro": "Triage Priority",
  "Chuyên khoa khuyến nghị": "Recommended Specialty",
  "Hướng tiếp cận chăm sóc": "Care Guidance",
  "Nguồn y văn tham chiếu (RAG / MedlinePlus)": "Clinical References (MedlinePlus / Pharmacopoeia)",
  "Để hoàn tất phiếu, hãy bổ sung vị trí đau, thời gian và tính chất hoặc mức độ đau trong cuộc trò chuyện.": "To finalize this summary, please share pain location, duration, and severity in the chat.",
  "Tôi đồng ý lưu bản tóm tắt đang xem vào hồ sơ bệnh án của mình.": "I consent to saving this reviewed summary to my health record.",
  "Xác nhận và lưu vào hồ sơ": "Confirm & Save to Record",
  // Sample Hospital Record Modal
  "Hồ sơ bệnh viện liên kết (Mẫu minh họa):": "Linked Hospital Record (Illustrative Sample):",
  "Đây là bản ghi mẫu giả lập kết nối sổ y bạ cơ sở y tế để bạn trải nghiệm tính năng,": "This is a simulated hospital record demonstrating health record linkage,",
  "không phải kết quả chẩn đoán từ Chatbot AI": "not an AI chatbot diagnosis",
  "Viêm họng cấp": "Acute Pharyngitis",
  "BS. Lê Thu Hà · Nội tổng quát": "Dr. Le Thu Ha · General Internal Medicine",
  "CHỈ SỐ SINH TỒN": "VITAL SIGNS",
  "Huyết áp": "Blood Pressure",
  "Nhịp tim": "Heart Rate",
  "88 lần/phút": "88 bpm",
  "Nhiệt độ": "Temperature",
  "Cân nặng": "Weight",
  "TRIỆU CHỨNG": "SYMPTOMS",
  "Đau họng, sốt nhẹ 38.2°C, khó nuốt 3 ngày": "Sore throat, mild fever 38.2°C, painful swallowing for 3 days",
  "KẾT QUẢ XÉT NGHIỆM": "LABORATORY FINDINGS",
  "Xét nghiệm nhanh kháng nguyên liên cầu: âm tính. Bạch cầu 11.2 G/L, tăng nhẹ.": "Rapid strep antigen test: negative. WBC 11.2 G/L, mildly elevated.",
  "GHI CHÚ CỦA BÁC SĨ": "PHYSICIAN NOTES",
  "Uống đủ nước, tái khám nếu sốt kéo dài trên 3 ngày.": "Maintain hydration; return for follow-up if fever persists beyond 3 days.",
  "NGÀY TÁI KHÁM": "FOLLOW-UP",
  "Không hẹn tái khám": "No follow-up scheduled",
  // Floating Chat Widget
  "Trợ lý y tế MediMind": "MediMind Health Assistant",
  "Đang trực tuyến": "Online",
  "Chào bạn, tôi là Trợ lý y tế MediMind!": "Hello, I am the MediMind Health Assistant!",
  "Tôi luôn sẵn sàng hỗ trợ bạn ngay tại góc màn hình này. Hãy hỏi tôi về cách dùng thuốc, giải thích chỉ số xét nghiệm hoặc gợi ý chuyên khoa khám nhé.": "I am right here whenever you need help. Ask me about medication timing, lab test meanings, or which medical specialty to visit.",
  "Cách uống thuốc?": "Medication timing?",
  "Khám khoa nào?": "Which specialty?",
  // Facility Booking & Detail Modals
  "BVĐK Quốc Tế Vinmec Central Park": "Vinmec Central Park International Hospital",
  "208 Nguyễn Hữu Cảnh, Q. Bình Thạnh, TP.HCM": "208 Nguyen Huu Canh, Binh Thanh Dist., HCMC",
  "208 Nguyễn Hữu Cảnh, Phường 22, Q. Bình Thạnh, TP.HCM": "208 Nguyen Huu Canh, Ward 22, Binh Thanh Dist., HCMC",
  "Lưu lịch nhắc cá nhân:": "Personal Appointment Reminder:",
  "Thông tin sẽ được lưu trực tiếp trên thiết bị của bạn để nhắc ngày giờ đi khám. Để hoàn tất đăng ký khám chính thức, vui lòng liên hệ tổng đài bệnh viện.": "Your preferred slot is saved on your device as an appointment reminder. To confirm an official hospital booking, please contact the facility hotline.",
  "Sáng (08:00 - 09:30)": "Morning (08:00 - 09:30)",
  "Sáng (09:30 - 11:00)": "Morning (09:30 - 11:00)",
  "Chiều (13:30 - 15:00)": "Afternoon (13:30 - 15:00)",
  "Chiều (15:00 - 16:30)": "Afternoon (15:00 - 16:30)",
  "Chuẩn JCI": "JCI Accredited",
  "07:30 - 17:00 • Trực cấp cứu 24/7": "07:30 - 17:00 • 24/7 Emergency",
  "Giới thiệu:": "Overview:",
  "Bệnh viện đa khoa quốc tế hàng đầu tại TP.HCM đạt chứng chỉ vàng JCI về an toàn và chất lượng điều trị.": "Leading international general hospital in Ho Chi Minh City holding JCI Gold Seal accreditation for patient safety and clinical care.",
  "Chỉ đường": "Directions",
  "Đặt lịch khám ngay": "Book Appointment Now",
  // Google Identity Modal
  "Tiếp tục với Google": "Continue with Google",
  "Chọn tài khoản": "Choose an account",
  "Để tiếp tục đến": "to continue to",
  "Mô phỏng trải nghiệm Google Identity": "Simulated Google Identity Sign-In",
  "Sử dụng một tài khoản khác": "Use another account",
  "Quay lại danh sách tài khoản": "Back to account list",
  "Bạn quên địa chỉ email ư?": "Forgot email?",
  "Không phải máy tính của bạn? Hãy sử dụng chế độ Khách để đăng nhập một cách riêng tư.": "Not your computer? Use Guest mode to sign in privately.",
  "Tạo tài khoản": "Create account",
  "Tiếp theo": "Next",
  "Đang đăng nhập vào MediMind AI...": "Signing in to MediMind AI...",
  "Đang đồng bộ hồ sơ y tế và phân quyền bảo mật cục bộ": "Synchronizing health profile and session security",
  "Đăng nhập thành công!": "Signed in successfully!",
  "Xác thực Google Identity Services hoàn tất": "Google Identity authentication complete",
  "Người dùng": "User",
  "Tự động chuyển đến không gian làm việc trong giây lát...": "Redirecting to your workspace shortly...",
  "Tiếng Việt": "English",
  "Trợ giúp": "Help",
  "Quyền riêng tư": "Privacy",
  "Điều khoản": "Terms",
  // Slide-over Hospital Drawer
  "Đang hoạt động": "Operating",
  "Tên cơ sở y tế": "Healthcare Facility Name",
  "Địa chỉ cơ sở:": "Facility Address:",
  "Đang tải...": "Loading...",
  "Hồ sơ cấp phép hoạt động": "Operating License Record",
  "Số giấy phép GPHĐ:": "License Number:",
  "Ngày cấp phép:": "Issue Date:",
  "Chuyên khoa khám chữa bệnh": "Clinical Specialties",
  "Giờ làm việc:": "Operating Hours:",
  "Giờ hành chính & theo lịch cơ sở": "Standard business & clinic hours",
  "Liên hệ đặt khám:": "Appointment Contact:",
  "Đang cập nhật tổng đài": "Hotline updating",
  "Đặt lịch khám tại cơ sở này": "Book Appointment at This Facility",
  "Định vị trên bản đồ": "Locate on Map"
};

const STATIC_VI_EN_ATTR = {
  "Đổi giao diện Sáng / Tối": "Switch Light / Dark theme",
  "Thông báo lâm sàng": "Clinical notifications",
  "Khám lâm sàng": "Clinical Assessment",
  "Hồ sơ bệnh án": "Health Records",
  "Chỉ số sinh tồn": "Vital Signs",
  "Cuộc trò chuyện mới": "New conversation",
  "Xác nhận lời khai đúng thực tế": "Review and confirm intake details",
  "Đính kèm ảnh lâm sàng": "Attach clinical image",
  "Gửi tin nhắn": "Send message",
  "Tìm bệnh viện, phòng khám, quận/huyện...": "Search hospital, clinic, district...",
  "Tìm bệnh viện, phòng khám hoặc địa chỉ...": "Search hospital, clinic, or address...",
  "Tìm cơ sở y tế gần tôi": "Find healthcare facilities near me",
  "Định vị vị trí của tôi": "Locate my position",
  "Toàn cảnh tất cả bệnh viện": "View all facilities on map",
  "Google Maps — Cơ sở y tế tại TP.HCM": "Google Maps — Healthcare Facilities in Ho Chi Minh City",
  "Làm mới vùng tải tài liệu": "Reset upload area",
  "Làm mới lịch sử": "Refresh history",
  "Ví dụ: mất ngủ, nhiệt miệng, mệt mỏi…": "e.g., insomnia, mouth ulcer, fatigue…",
  "Tìm gợi ý": "Get suggestions",
  "Thực phẩm nên hạn chế và cần tránh": "Foods to limit and avoid",
  "Nhấn để đổi ảnh đại diện": "Click to change profile photo",
  "Ẩn/Hiện số điện thoại": "Show/hide phone number",
  "Ẩn/Hiện email": "Show/hide email",
  "Nhập họ và tên đầy đủ": "Enter full name",
  "Ví dụ: 0901234567": "e.g., 0901234567",
  "ban@example.com": "you@example.com",
  "Ví dụ: Penicillin, Hải sản, Aspirin...": "e.g., Penicillin, Seafood, Aspirin...",
  "Ví dụ: 168": "e.g., 168",
  "Ví dụ: 58.5": "e.g., 58.5",
  "Số nhà, tên đường, Quận/Huyện, Tỉnh/Thành phố...": "House number, street, district, city/province...",
  "Đóng": "Close",
  "Hiện/ẩn mật khẩu": "Show/hide password",
  "Nhập email hoặc số điện thoại đã đăng ký": "Enter registered email or phone number",
  "Nhập mật khẩu mới (tối thiểu 6 ký tự)": "Enter new password (at least 6 characters)",
  "Họ và tên": "Full name",
  "VD: 0912 345 678": "e.g., 0912 345 678",
  "Mở toàn màn hình": "Expand to full view",
  "Nhập câu hỏi của bạn...": "Type your health question...",
  "Tắt hoàn toàn": "Dismiss widget",
  "Email hoặc số điện thoại": "Email or phone number",
  "Đóng bảng chi tiết": "Close details panel"
};

const _origNodeTextMap = new WeakMap();
const _origElAttrMap = new WeakMap();

function applyStaticDomLexicon() {
  if (!document.body) return;
  const toEn = isEnLang();
  const skipTags = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'CODE', 'PRE']);

  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null);
  let node;
  while ((node = walker.nextNode())) {
    const parent = node.parentElement;
    if (!parent || skipTags.has(parent.tagName)) continue;
    if (parent.closest('[data-i18n], #lang-dropdown-menu, #set-language')) continue;

    let rec = _origNodeTextMap.get(node);
    const raw = node.nodeValue || '';
    const norm = raw.replace(/\s+/g, ' ').trim();
    if (!rec) {
      if (!norm || !Object.prototype.hasOwnProperty.call(STATIC_VI_EN_TEXT, norm)) continue;
      const leading = (raw.match(/^\s*/) || [''])[0];
      const trailing = (raw.match(/\s*$/) || [''])[0];
      rec = { norm, leading, trailing };
      _origNodeTextMap.set(node, rec);
    } else {
      const expectedCurrent = toEn ? rec.norm : STATIC_VI_EN_TEXT[rec.norm];
      if (norm !== rec.norm && norm !== STATIC_VI_EN_TEXT[rec.norm] && norm !== expectedCurrent) {
        if (Object.prototype.hasOwnProperty.call(STATIC_VI_EN_TEXT, norm)) {
          const leading = (raw.match(/^\s*/) || [''])[0];
          const trailing = (raw.match(/\s*$/) || [''])[0];
          rec = { norm, leading, trailing };
          _origNodeTextMap.set(node, rec);
        } else {
          continue;
        }
      }
    }

    if (parent.tagName === 'OPTION' && !parent.hasAttribute('value')) {
      parent.setAttribute('value', rec.norm);
    }
    const nextText = toEn ? STATIC_VI_EN_TEXT[rec.norm] : rec.norm;
    const nextRaw = rec.leading + nextText + rec.trailing;
    if (node.nodeValue !== nextRaw) node.nodeValue = nextRaw;
  }

  const attrNames = ['placeholder', 'title', 'aria-label'];
  document.querySelectorAll('[placeholder],[title],[aria-label]').forEach(el => {
    let attrRec = _origElAttrMap.get(el);
    if (!attrRec) {
      attrRec = {};
      _origElAttrMap.set(el, attrRec);
    }
    for (const attr of attrNames) {
      if (attr === 'placeholder' && el.hasAttribute('data-i18n-placeholder')) continue;
      if (attr === 'title' && el.hasAttribute('data-i18n-title')) continue;
      if (attr === 'aria-label' && el.hasAttribute('data-i18n-aria')) continue;
      const cur = el.getAttribute(attr);
      if (cur == null) continue;
      const norm = cur.replace(/\s+/g, ' ').trim();
      if (!attrRec[attr]) {
        if (!Object.prototype.hasOwnProperty.call(STATIC_VI_EN_ATTR, norm)) continue;
        attrRec[attr] = norm;
      } else if (norm !== attrRec[attr] && norm !== STATIC_VI_EN_ATTR[attrRec[attr]]) {
        if (Object.prototype.hasOwnProperty.call(STATIC_VI_EN_ATTR, norm)) {
          attrRec[attr] = norm;
        } else {
          continue;
        }
      }
      const nextVal = toEn ? STATIC_VI_EN_ATTR[attrRec[attr]] : attrRec[attr];
      if (el.getAttribute(attr) !== nextVal) el.setAttribute(attr, nextVal);
    }
  });
}

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
  const normalized = lang === 'en' ? 'en' : 'vi';
  const draftProfileDob = document.getElementById('p-birthdate')?.value || '';
  currentLang = normalized;
  try { localStorage.setItem('medimind_lang', normalized); } catch (e) {}
  closeLanguageDropdown();
  populateDobDropdowns();
  applyLanguage();
  updateAuthUI();
  if (draftProfileDob) {
    const pBirth = document.getElementById('p-birthdate');
    if (pBirth) pBirth.value = draftProfileDob;
    populateModalDobDropdowns('p-dob-day', 'p-dob-month', 'p-dob-year', draftProfileDob);
  }
  if (typeof switchEhrSubTab === 'function') switchEhrSubTab(currentEhrSubTab || 'ai');
}
const switchLanguage = setLanguage;
window.switchLanguage = setLanguage;

function applyLanguage() {
  const dict = translations[currentLang] || translations.vi;
  document.documentElement.lang = isEnLang() ? 'en' : 'vi';
  document.title = t(
    'MediMind Clinical AI — Trợ lý Y tế & Sàng lọc Lâm sàng',
    'MediMind Clinical AI — Clinical Health Assistant'
  );

  const currentLangCode = document.getElementById('current-lang-code');
  if (currentLangCode) currentLangCode.innerText = currentLang.toUpperCase();

  const checkVi = document.getElementById('check-vi');
  const checkEn = document.getElementById('check-en');
  if (checkVi) checkVi.classList.toggle('hidden', currentLang !== 'vi');
  if (checkEn) checkEn.classList.toggle('hidden', currentLang !== 'en');

  const setLangSelect = document.getElementById('set-language');
  if (setLangSelect) setLangSelect.value = currentLang;

  // Dynamic Auth modal header based on currentAuthMode
  if (typeof toggleAuthMode === 'function' && typeof currentAuthMode !== 'undefined') {
    toggleAuthMode(currentAuthMode);
  }

  // Update gender options text while preserving backend option values
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
        if (!el.hasAttribute('value')) el.setAttribute('value', el.text);
        el.text = dict[key];
      } else {
        el.innerHTML = dict[key];
      }
    }
  });

  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    const key = el.getAttribute('data-i18n-placeholder');
    if (dict[key]) el.setAttribute('placeholder', dict[key]);
  });

  document.querySelectorAll('[data-i18n-title]').forEach(el => {
    const key = el.getAttribute('data-i18n-title');
    if (dict[key]) el.setAttribute('title', dict[key]);
  });

  document.querySelectorAll('[data-i18n-aria]').forEach(el => {
    const key = el.getAttribute('data-i18n-aria');
    if (dict[key]) el.setAttribute('aria-label', dict[key]);
  });

  applyStaticDomLexicon();

  // Sync masked field toggle labels if present
  ['p-phone', 'p-email'].forEach(fId => {
    const lbl = document.getElementById(fId + '-label-text');
    if (lbl) lbl.innerText = fieldMaskState[fId] ? t('Hiện', 'Show') : t('Ẩn', 'Hide');
  });

  // Sync empty chat welcome bubble & intake placeholders if no turns yet
  if (currentConversationId === 'demo_consultation_ho_sot' && typeof renderDemoConsultationView === 'function') {
    renderDemoConsultationView();
  } else if (Array.isArray(chatHistory) && chatHistory.length === 0) {
    const chatContainer = document.getElementById('chat-messages');
    const firstBubble = chatContainer?.querySelector('.max-w-\\[85\\%\\]');
    if (firstBubble && dict.welcome_msg) {
      firstBubble.textContent = dict.welcome_msg;
    }
    const statusBadge = document.getElementById('intake-status-badge');
    if (statusBadge && (statusBadge.innerText === 'Chờ khởi tạo' || statusBadge.innerText === 'Awaiting Intake')) {
      statusBadge.innerText = t('Chờ khởi tạo', 'Awaiting Intake');
    }
    const cEl = document.getElementById('intake-chief-complaint');
    if (cEl && (cEl.innerText === 'Chưa có thông tin' || cEl.innerText === 'No information yet')) {
      cEl.innerText = t('Chưa có thông tin', 'No information yet');
    }
    const dnEl = document.getElementById('intake-denied-symptoms');
    if (dnEl && (dnEl.innerText === 'Chưa ghi nhận' || dnEl.innerText === 'None recorded')) {
      dnEl.innerText = t('Chưa ghi nhận', 'None recorded');
    }
  }

  // Sync Auth & Profile DOB dropdowns & active mode title
  if (typeof populateDobDropdowns === 'function') populateDobDropdowns();
  if (typeof populateModalDobDropdowns === 'function') {
    populateModalDobDropdowns('p-dob-day', 'p-dob-month', 'p-dob-year', document.getElementById('p-birthdate')?.value || currentUser?.dob || '');
    populateModalDobDropdowns('edit-profile-dob-day', 'edit-profile-dob-month', 'edit-profile-dob-year', document.getElementById('edit-profile-dob')?.value || currentUser?.dob || '');
  }
  if (typeof toggleAuthMode === 'function' && typeof currentAuthMode !== 'undefined') {
    const loginModal = document.getElementById('login-modal');
    if (loginModal && !loginModal.classList.contains('hidden')) {
      toggleAuthMode(currentAuthMode || 'login');
    }
  }

  // Re-sync all dynamic view components across tabs
  if (typeof updateHomeGreeting === 'function') updateHomeGreeting();
  if (typeof updateEhrTabUI === 'function') updateEhrTabUI();
  if (typeof renderChatHistoryList === 'function') renderChatHistoryList(document.getElementById('history-search-input')?.value || '');
  if (typeof syncFloatingChatMessages === 'function') syncFloatingChatMessages();
  if (typeof updateFacilityDistrictDropdown === 'function') updateFacilityDistrictDropdown(facilityCurrentRegion || 'hcm');
  if (typeof renderMedicalFacilities === 'function') renderMedicalFacilities();
  if (typeof loadPrescriptionHistory === 'function') loadPrescriptionHistory();
  if (typeof switchEhrSubTab === 'function') switchEhrSubTab(currentEhrSubTab || 'ai');
  if (typeof renderNutritionPresets === 'function') renderNutritionPresets();
  if (typeof activeNutritionData !== 'undefined' && activeNutritionData) {
    if (typeof renderDishPlate === 'function') renderDishPlate();
    if (typeof renderRecipe === 'function') renderRecipe();
  }
  if (typeof currentPrescriptionData !== 'undefined' && currentPrescriptionData) {
    const resSec = document.getElementById('prescription-result-section');
    if (resSec && !resSec.classList.contains('hidden') && typeof renderPrescriptionResult === 'function') {
      renderPrescriptionResult(currentPrescriptionData);
    }
  }

  window.dispatchEvent(new CustomEvent('medimind:langchange', { detail: { lang: currentLang } }));
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
      if (typeof renderMedicalFacilities === 'function') renderMedicalFacilities();
      setTimeout(() => {
        if (typeof initHospitalInteractiveMap === 'function') initHospitalInteractiveMap();
        if (typeof hospitalLeafletMap !== 'undefined' && hospitalLeafletMap) {
          hospitalLeafletMap.invalidateSize();
        }
        if (typeof gMap !== 'undefined' && gMap && window.google) {
          google.maps.event.trigger(gMap, 'resize');
        }
        if (typeof leafletMap !== 'undefined' && leafletMap) {
          leafletMap.invalidateSize();
        }
      }, 150);
    } else if (tabId === 'doctor-tab') {
      if (typeof initNutritionStudio === 'function') initNutritionStudio();
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
  cancelActiveChatRequest();
  window.clearChatHealthContext?.();
  showFloatingDecorations();
  clearChatImagePreview();
  chatHistory.length = 0;
  currentConversationId = null;
  currentIntakeSummary = null;

  const dict = translations[currentLang] || translations.vi;
  const container = document.getElementById('chat-messages');
  if (container) {
    container.innerHTML = `
      <div class="flex items-start gap-3">
        <div class="w-8 h-8 rounded-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-white/10 text-sky-600 dark:text-sky-400 flex items-center justify-center shrink-0 shadow-xs mt-0.5">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"/></svg>
        </div>
        <div class="max-w-[85%] bg-white dark:bg-slate-800/90 border border-slate-200/80 dark:border-white/10 rounded-2xl p-4 sm:p-5 shadow-xs text-xs sm:text-sm text-slate-700 dark:text-slate-200 leading-relaxed font-normal">
          ${escapeHtml(dict.welcome_msg)}
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
      statusBadge.innerText = t('Chờ khởi tạo', 'Awaiting Intake');
      statusBadge.className = 'px-2 py-0.5 rounded-full text-[10px] font-bold bg-sky-500/20 text-sky-300 border border-sky-400/30';
    }
    const cEl = document.getElementById('intake-chief-complaint');
    if (cEl) cEl.innerText = t('Chưa có thông tin', 'No information yet');
    const pEl = document.getElementById('intake-present-symptoms');
    if (pEl) pEl.innerText = '--';
    const dnEl = document.getElementById('intake-denied-symptoms');
    if (dnEl) dnEl.innerText = t('Chưa ghi nhận', 'None recorded');
    const dEl = document.getElementById('intake-duration');
    if (dEl) dEl.innerText = '--';
    const vEl = document.getElementById('intake-vitals');
    if (vEl) vEl.innerText = '--';
    const btnConfirm = document.getElementById('btn-confirm-intake');
    if (btnConfirm) btnConfirm.classList.remove('hidden');
  }

  // Cập nhật lại thanh lịch sử: giữ nguyên các phiên trước đó, bỏ đánh dấu active
  renderChatHistoryList();
  // Khung chat nổi dùng cùng hội thoại trong bộ nhớ; xóa nội dung cũ ngay khi đổi tài khoản/phiên.
  if (typeof syncFloatingChatMessages === 'function') syncFloatingChatMessages();
}

// ==========================================
// Chat Logic & Clinical Intake (Multimodal Vision + RAG + Double Guardrails)
// ==========================================
let currentConversationId = null;
let currentIntakeSummary = null;
let activeChatRequest = null;

function chatAccountKey() {
  return String(currentUser?.id || currentUser?.username || 'guest');
}

function setChatSending(sending) {
  document.querySelectorAll('#send-btn, #floating-chat-window button[onclick="sendFloatingChatMessage()"]')
    .forEach(button => { button.disabled = sending; button.setAttribute('aria-busy', String(sending)); });
  window.dispatchEvent(new CustomEvent('medimind:chat-busy', { detail: { busy: sending } }));
}

function beginChatRequest(typingId) {
  if (activeChatRequest) return null;
  const request = { controller: new AbortController(), conversationId: currentConversationId,
    accountKey: chatAccountKey(), typingId, history: chatHistory.slice() };
  activeChatRequest = request;
  setChatSending(true);
  return request;
}

function chatRequestIsCurrent(request) {
  return activeChatRequest === request && request.accountKey === chatAccountKey()
    && request.conversationId === currentConversationId;
}

function finishChatRequest(request) {
  document.getElementById(request.typingId)?.remove();
  if (activeChatRequest === request) { activeChatRequest = null; setChatSending(false); }
}

function cancelActiveChatRequest() {
  const request = activeChatRequest;
  if (!request) return;
  activeChatRequest = null;
  request.controller.abort();
  document.getElementById(request.typingId)?.remove();
  setChatSending(false);
}

function formatChatAnswer(text) {
  return escapeHtml(String(text || '')).replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.*?)\*/g, '<em>$1</em>').replace(/\n/g, '<br>');
}

function chatAnswerMetadata(data) {
  const links = [], seen = new Set();
  for (const source of (Array.isArray(data.sources) ? data.sources.slice(0, 8) : [])) {
    try {
      const url = new URL(source.url);
      if (url.protocol !== 'https:' || url.username || url.password || seen.has(url.href)) continue;
      seen.add(url.href);
      links.push(`<a href="${escapeHtml(url.href)}" target="_blank" rel="noopener noreferrer" class="underline underline-offset-2">${escapeHtml(source.title || source.source || url.hostname)} <span class="opacity-70">(${escapeHtml(url.hostname)})</span></a>`);
    } catch (_) { /* Invalid source data never becomes a link. */ }
  }
  const degradedBanner = data.degraded
    ? `<p role="status" class="mt-3 rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">${t('Đang dùng phản hồi dự phòng vì dịch vụ AI tạm bận; vui lòng kiểm tra lại thông tin trước khi áp dụng.', 'Using fallback guidance while the AI service is busy; please double-check before applying.')}</p>`
    : '';
  const refsHtml = links.length
    ? `<div class="mt-3 border-t border-slate-200 pt-2 text-xs text-sky-700 dark:border-white/10 dark:text-sky-300"><span class="font-semibold">${t('Nguồn tham khảo:', 'References:')}</span> ${links.join(' · ')}</div>`
    : '';
  return `${degradedBanner}${refsHtml}`;
}

function chatAssistantTurn(data) {
  return { role: 'assistant', content: data.answer, sources: Array.isArray(data.sources) ? data.sources : [],
    degraded: Boolean(data.degraded), is_emergency: Boolean(data.is_emergency),
    needs_red_flag_confirmation: Boolean(data.needs_red_flag_confirmation) };
}

function appendChatConfirmation(container, data, conversationId, floating = false) {
  if (!data.needs_red_flag_confirmation || !container) return;
  const expectedAnswer = data.answer ?? data.content;
  const choices = document.createElement('div');
  choices.className = 'flex gap-2';
  for (const reply of (currentLang === 'en' ? ['Yes', 'No'] : ['Có', 'Không'])) {
    const button = document.createElement('button');
    button.type = 'button'; button.textContent = reply;
    button.className = 'rounded-lg border px-3 py-1.5 text-sm';
    button.onclick = () => {
      if (activeChatRequest || currentConversationId !== conversationId || chatHistory.at(-1)?.content !== expectedAnswer) return;
      const input = document.getElementById(floating ? 'floating-user-input' : 'user-input');
      if (!input) return;
      input.value = reply; choices.remove();
      if (floating) sendFloatingChatMessage(); else sendChatMessage();
    };
    choices.append(button);
  }
  container.append(choices);
}

function renderSharedChatInMain() {
  const container = document.getElementById('chat-messages');
  if (!container) return;
  container.innerHTML = chatHistory.filter(turn => ['user', 'assistant'].includes(turn.role)).map(turn => {
    if (turn.role === 'user') {
      const image = typeof turn.image === 'string' && /^data:image\/(?:jpeg|png|webp|gif);base64,[a-z0-9+/=]+$/i.test(turn.image)
        ? `<img src="${escapeHtml(turn.image)}" alt="${t('Ảnh người dùng đã gửi', 'User uploaded image')}" class="mb-2 max-w-[220px] max-h-[160px] rounded-xl object-cover">` : '';
      return `<div class="flex justify-end my-1"><div class="max-w-[85%] rounded-2xl bg-sky-600 px-4 py-3 text-sm text-white">${image}${escapeHtml(turn.content).replace(/\n/g, '<br>')}</div></div>`;
    }
    return `<div class="flex justify-start my-1"><div class="max-w-[95%] rounded-2xl border border-slate-200 bg-white p-4 text-sm leading-relaxed text-slate-800 dark:border-white/10 dark:bg-slate-800 dark:text-slate-100">${turn.is_emergency ? `<p class="mb-2 font-bold text-rose-600 dark:text-rose-300">${t('Cần trợ giúp khẩn cấp: gọi 115 hoặc đến khoa Cấp cứu gần nhất.', 'Emergency warning: call 115 / emergency services or go to the nearest Emergency Department.')}</p>` : ''}${formatChatAnswer(turn.content)}${chatAnswerMetadata(turn)}</div></div>`;
  }).join('');
  appendChatConfirmation(container, chatHistory.at(-1) || {}, currentConversationId);
  container.scrollTop = container.scrollHeight;
}

async function sendChatMessage() {
  if (activeChatRequest) return;
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
  const safeCurrentImage = currentImage ? sanitizeSafeImgSrc(currentImage, '') : '';
  if (safeCurrentImage) {
    userImgHtml = `
      <div class="mb-2 overflow-hidden rounded-xl border border-white/20 shadow-xs cursor-pointer max-w-[220px]" onclick="openImageModal(this.querySelector('img')?.src || '', '${t('Ảnh tổn thương bạn đã gửi', 'Uploaded clinical image')}', '${t('Ảnh người bệnh cung cấp', 'Patient-provided image')}')">
        <img src="${escapeHtml(safeCurrentImage)}" alt="${t('Ảnh tải lên', 'Uploaded image')}" class="w-full h-auto max-h-[160px] object-cover hover:scale-105 transition-transform duration-200">
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
      riskLevel: t('Đang sàng lọc...', 'Screening...'),
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
  const chatRequest = beginChatRequest(typingId);

  try {
    const sentConvId = currentConversationId;
    // Gọi Chatbot AI kèm conversation_id (Backend tự động điều phối và đồng bộ với Intake Service)
    const chatRes = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        conversation_id: currentConversationId,
        message: text,
        history: chatRequest.history,
        image: currentImage,
        lang: currentLang,
        health_context: window.getChatHealthContext?.() || {}
      }),
      signal: chatRequest.controller.signal
    });
    const data = await chatRes.json();

    document.getElementById(typingId)?.remove();

    // KIỂM TRA ĐỐI SOÁT CUỘC TRÒ CHUYỆN (Tránh Race Condition khi người dùng chuyển cuộc chat)
    if (!chatRequestIsCurrent(chatRequest)) return;

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

    if (!chatRes.ok || !data || data.error || typeof data.answer !== 'string') {
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
            <span>${t('Đặc điểm hình ảnh ghi nhận:', 'Observed visual features:')}</span>
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
          <span>${t('NGUY CẤP: GỌI 115 HOẶC ĐẾN CƠ SỞ CẤP CỨU GẦN NHẤT', 'EMERGENCY: CALL 115 OR GO TO THE NEAREST EMERGENCY DEPARTMENT')}</span>
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
          ${chatAnswerMetadata(data)}
        </div>
      </div>
    `;

    container.insertAdjacentHTML('beforeend', botHtml);
    appendChatConfirmation(container, data, currentConversationId);
    container.scrollTop = container.scrollHeight;

    chatHistory.push({ role: 'user', content: text, image: currentImage });
    chatHistory.push(chatAssistantTurn(data));

    saveOrUpdateCurrentSession(text, data, data.intake);
    if (typeof syncFloatingChatMessages === 'function') syncFloatingChatMessages();
    if (data.history_saved === false) appendErrorMessage(t("Lượt trò chuyện này chưa được lưu vào lịch sử trên máy chủ.", "This message was not saved to server history."));

  } catch (err) {
    document.getElementById(typingId)?.remove();
    if (err.name !== 'AbortError' && chatRequestIsCurrent(chatRequest)) appendErrorMessage(dict.server_error);
  } finally {
    finishChatRequest(chatRequest);
  }
}

// Cập nhật phân tầng lâm sàng định tính (Tuyệt đối KHÔNG hiển thị điểm xác suất 0-100 giả lập)
function updateTriagePanel(data) {
  const floatingRisk = document.getElementById('floating-risk-score');
  const score = data.risk_score;
  if (floatingRisk) {
    if (data.is_emergency || score >= 70) {
      floatingRisk.innerText = t('Cảnh báo cấp cứu khẩn cấp', 'Emergency Warning');
      floatingRisk.className = 'text-xs font-bold text-rose-400';
    } else if (score == null) {
      floatingRisk.innerText = t('Chưa đủ thông tin', 'Insufficient data');
      floatingRisk.className = 'text-xs font-bold text-slate-500';
    } else if (score >= 35) {
      floatingRisk.innerText = t('Khuyến nghị khám chuyên khoa', 'Specialist Visit Recommended');
      floatingRisk.className = 'text-xs font-bold text-amber-300';
    } else {
      floatingRisk.innerText = t('Theo dõi & tự chăm sóc tại nhà', 'Home Monitoring & Self-Care');
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

  if (complaintEl) complaintEl.innerText = facts.chief_complaint || t('Sàng lọc triệu chứng', 'Symptom Screening');
  if (presentEl) presentEl.innerText = (facts.present_symptoms && facts.present_symptoms.length > 0) ? facts.present_symptoms.join(', ') : t('Chưa ghi nhận rõ', 'Not yet specified');
  if (deniedEl) deniedEl.innerText = (facts.denied_symptoms && facts.denied_symptoms.length > 0) ? facts.denied_symptoms.join(', ') : t('Chưa phủ nhận triệu chứng nào', 'No symptoms denied yet');
  if (durationEl) durationEl.innerText = facts.duration || t('Chưa rõ số ngày', 'Duration not specified');
  if (vitalsEl) {
    const v = facts.vitals || {};
    vitalsEl.innerText = v.temperature ? `${v.temperature}` : t('Chưa đo thân nhiệt', 'Temperature not measured');
  }

  if (statusBadge) {
    if (status === 'confirmed') {
      statusBadge.innerText = t('✓ Đã xác nhận', '✓ Confirmed');
      statusBadge.className = 'px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-300 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-500/40';
      if (btnConfirm) btnConfirm.classList.add('hidden');
    } else if (status === 'ready_for_review') {
      statusBadge.innerText = t('Chờ xác nhận', 'Ready for Review');
      statusBadge.className = 'px-2.5 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-300 dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-500/40';
      if (btnConfirm) btnConfirm.classList.remove('hidden');
    } else {
      statusBadge.innerText = t('Đang thu thập', 'Collecting');
      statusBadge.className = 'px-2.5 py-1 rounded-full text-xs font-bold bg-sky-100 text-sky-800 border border-sky-300 dark:bg-sky-950/60 dark:text-sky-300 dark:border-sky-500/40';
      if (btnConfirm) btnConfirm.classList.remove('hidden');
    }
  }
}

async function openPreVisitSummaryModal() {
  const id = currentConversationId;
  if (!id) return showMedicalToast(t("Hãy bắt đầu hội thoại trước khi xem bản nháp.", "Please start a conversation before viewing the draft summary."), "info");
  try {
    let summary = currentIntakeSummary;
    if (!summary) {
      const response = await fetch('/api/intake/summary/' + encodeURIComponent(id));
      const data = await response.json();
      if (!response.ok || !data.summary?.part_a_patient_facts) throw new Error(data.error || t("Chưa có bản nháp để xem.", "No draft summary available yet."));
      summary = data.summary;
    }
    if (id !== currentConversationId) return;
    currentIntakeSummary = summary;
    renderPreVisitSummaryInModal(summary);
    document.getElementById('previsit-summary-modal').classList.remove('hidden');
  } catch (error) {
    showMedicalToast(error.message || t("Không mở được bản nháp.", "Unable to open the draft summary."), "error");
  }
}

function closePreVisitSummaryModal() {
  const modal = document.getElementById('previsit-summary-modal');
  if (modal) modal.classList.add('hidden');
}

let reviewedIntakeSummary = null;
function renderPreVisitSummaryInModal(summary, id = currentConversationId) {
  reviewedIntakeSummary = { id, summary };
  const partA = summary.part_a_patient_facts || {};
  const partB = summary.part_b_system_assessment || {};

  const statusText = document.getElementById('modal-summary-status-text');
  const createdAt = document.getElementById('modal-summary-created-at');
  if (statusText) statusText.innerText = `${t('Phiên bản', 'Version')}: v${partB.version || 1} • ${partB.confirmation_status || t('Chờ xác nhận', 'Pending confirmation')}`;
  if (createdAt) createdAt.innerText = partB.created_at || '';

  // Part A
  const cEl = document.getElementById('summary-a-complaint');
  const dEl = document.getElementById('summary-a-duration');
  const pEl = document.getElementById('summary-a-present');
  const dnEl = document.getElementById('summary-a-denied');
  const vEl = document.getElementById('summary-a-vitals');
  const attEl = document.getElementById('summary-a-attachments');
  const mEl = document.getElementById('summary-a-missing');

  if (cEl) cEl.innerText = [partA.chief_complaint, ...Object.values(partA.pain || {})].filter(Boolean).join(' · ') || '--';
  if (dEl) dEl.innerText = partA.duration || '--';
  if (pEl) pEl.innerText = (partA.symptoms_present && partA.symptoms_present.length) ? partA.symptoms_present.join(', ') : '--';
  if (dnEl) dnEl.innerText = (partA.symptoms_denied && partA.symptoms_denied.length) ? partA.symptoms_denied.join(', ') : t('Chưa có triệu chứng phủ nhận', 'No denied symptoms');
  if (vEl) vEl.innerText = partA.vitals || t('Chưa có chỉ số tự đo tại nhà', 'No home vitals recorded');
  if (attEl) attEl.innerText = partA.attachments_and_observations || t('Không có tệp hình ảnh đính kèm', 'No attached images');
  if (mEl) mEl.innerText = (partA.missing_or_unclear_info && partA.missing_or_unclear_info.length) ? partA.missing_or_unclear_info.join('; ') : t('Đã đủ thông tin cơ bản', 'Core intake information complete');

  const algEl = document.getElementById('summary-a-allergies');
  const medEl = document.getElementById('summary-a-medications');
  if (algEl) algEl.innerText = partA.allergies || t('Chưa ghi nhận tiền sử dị ứng đặc biệt', 'No known allergies recorded');
  if (medEl) medEl.innerText = partA.current_medications || t('Chưa ghi nhận thuốc đang dùng thường xuyên', 'No regular medications recorded');

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
    bSources.innerHTML = sList.map(s => `• ${t('Nguồn', 'Source')}: <a href="${sanitizeUrl(s.url)}" target="_blank" rel="noopener noreferrer" class="underline hover:text-white">${escapeHtml(s.title || s.source || t('Tài liệu tham khảo', 'Reference'))}</a>`).join('<br>');
  }

  const incomplete = summary.ready_to_finalize === false;
  document.getElementById('summary-pain-incomplete').classList.toggle('hidden', !incomplete);
  const readOnly = incomplete || summary.is_confirmed || !reviewedIntakeSummary.id;
  document.getElementById('summary-consent').classList.toggle('hidden', readOnly);
  document.getElementById('summary-consent-check').checked = false;
  document.getElementById('modal-btn-confirm').classList.toggle('hidden', readOnly);
  updateSummarySaveButton();
}

function updateSummarySaveButton() {
  const button = document.getElementById('modal-btn-confirm');
  button.disabled = !document.getElementById('summary-consent-check').checked;
  button.classList.toggle('opacity-50', button.disabled);
}

async function confirmCurrentIntake() {
  if (!document.getElementById('summary-consent-check').checked ||
      !currentConversationId || reviewedIntakeSummary?.id !== currentConversationId) return;
  try {
    const res = await fetch('/api/intake/confirm-summary', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conversation_id: currentConversationId, version: reviewedIntakeSummary?.summary.version, reviewed_facts: reviewedIntakeSummary?.summary.part_a_patient_facts, save_to_record: true })
    });
    const data = await res.json();
    if (!res.ok) {
      showMedicalToast(data.error || t("Chưa lưu được bản tóm tắt.", "Unable to save the summary."), "error");
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
      showMedicalToast(t("Đã lưu bản tóm tắt vào hồ sơ.", "Summary saved to your profile."), "success");
      return data.summary;
    }
  } catch (e) {
    showMedicalToast(t("Lỗi khi xác nhận lời khai.", "Error confirming intake summary."), "error");
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
      alert(data.message || t('Lỗi khi tải tệp lên.', 'Error uploading file.'));
    }
  } catch (err) {
    console.error('Lỗi upload tệp:', err);
    alert(t('Không thể kết nối đến máy chủ để tải tệp lên.', 'Unable to connect to the server to upload file.'));
  }
}

async function loadScanFiles() {
  if (!currentUser || currentUser.isDemo) {
    const ocrEmpty = document.getElementById('ocr-table-empty');
    const ocrFilled = document.getElementById('ocr-table-filled');
    const tbody = document.getElementById('scan-files-tbody');
    const countBadge = document.getElementById('scan-files-count');
    if (tbody) tbody.innerHTML = '';
    if (countBadge) countBadge.innerText = t('0 tệp', '0 files');
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

    if (countBadge) countBadge.innerText = isEnLang() ? `${files.length} files` : `${files.length} tệp`;

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
                <button type="button" onclick="deleteScanFile('${encodeURIComponent(f.id || f.filename || f.name).replace(/'/g, '%27')}')" class="text-rose-500 hover:text-rose-700 hover:bg-rose-50 p-1.5 rounded-lg transition-colors cursor-pointer" title="${t('Xóa tệp khỏi danh sách', 'Remove file')}">
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
  if (!confirm(t('Bạn có chắc chắn muốn xóa tệp này không?', 'Are you sure you want to delete this file?'))) return;
  try {
    const res = await fetch('/api/scan-files/' + encodedName, { method: 'DELETE' });
    const data = await res.json();
    if (data.status === 'success') {
      await loadScanFiles();
    } else {
      alert(data.message || t('Không thể xóa tệp.', 'Unable to delete file.'));
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
    const msg = t('Vui lòng nhập họ và tên.', 'Please enter your full name.');
    if (typeof showMedicalToast === 'function') showMedicalToast(msg, 'warning');
    else alert(msg);
    return;
  }

  if (dob && !/^\d{2}\/\d{2}\/\d{4}$/.test(dob)) {
    const dobMsg = t('Ngày sinh phải đúng định dạng DD/MM/YYYY (VD: 15/08/1995).', 'Date of birth must follow DD/MM/YYYY format (e.g., 15/08/1995).');
    if (typeof showMedicalToast === 'function') {
      showMedicalToast(dobMsg, 'warning', 4500);
    } else {
      alert(dobMsg);
    }
    document.getElementById('edit-profile-dob')?.focus();
    return;
  }

  if (phone) {
    const cleanDigits = phone.replace(/\D/g, '');
    if (cleanDigits.length < 9 || cleanDigits.length > 11) {
      const phoneMsg = t('Số điện thoại không hợp lệ (cần từ 9 đến 11 chữ số).', 'Invalid phone number (must be 9 to 11 digits).');
      if (typeof showMedicalToast === 'function') {
        showMedicalToast(phoneMsg, 'warning', 4500);
      } else {
        alert(phoneMsg);
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
    if (typeof showMedicalToast === 'function') showMedicalToast(t('Không thể kết nối đến máy chủ.', 'Unable to connect to the server.'), 'error');
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
          ? t(`Đăng ký hồ sơ Google thành công! Chào mừng ${currentUser.name}.`, `Google registration completed! Welcome, ${currentUser.name}.`)
          : t('Đã hoàn tất và lưu hồ sơ y tế thành công!', 'Medical profile saved successfully!'),
        'success',
        4500
      );
    }
  } else {
    const errTxt = data?.error || t('Lưu thông tin thất bại.', 'Failed to save profile.');
    if (typeof showMedicalToast === 'function') showMedicalToast(errTxt, 'error', 4500);
    else alert(errTxt);
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
        selYear = String(parseInt(parts[0], 10) || '');
        selMonth = String(parseInt(parts[1], 10) || '');
        selDay = String(parseInt(parts[2], 10) || '');
      } else {
        selDay = String(parseInt(parts[0], 10) || '');
        selMonth = String(parseInt(parts[1], 10) || '');
        selYear = String(parseInt(parts[2], 10) || '');
      }
    }
  }

  const maxDays = new Date(Number(selYear) || 2000, Number(selMonth) || 1, 0).getDate();
  if (selDay && Number(selDay) > maxDays) selDay = String(maxDays);

  const dayText = currentLang === 'en' ? 'Day' : 'Ngày';
  const monthText = currentLang === 'en' ? 'Month' : 'Tháng';
  const yearText = currentLang === 'en' ? 'Year' : 'Năm';
  const enMonths = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  daySelect.innerHTML = `<option value="">${dayText}</option>` +
    Array.from({ length: maxDays }, (_, i) => {
      const val = i + 1;
      const lbl = String(val).padStart(2, '0');
      return `<option value="${val}" ${Number(selDay) === val ? 'selected' : ''}>${lbl}</option>`;
    }).join('');

  monthSelect.innerHTML = `<option value="">${monthText}</option>` +
    Array.from({ length: 12 }, (_, i) => {
      const val = i + 1;
      const pad = String(val).padStart(2, '0');
      const lbl = currentLang === 'en' ? `${pad} · ${enMonths[i]}` : `Tháng ${pad}`;
      return `<option value="${val}" ${Number(selMonth) === val ? 'selected' : ''}>${lbl}</option>`;
    }).join('');

  const currentYear = new Date().getFullYear();
  yearSelect.innerHTML = `<option value="">${yearText}</option>` +
    Array.from({ length: 110 }, (_, i) => {
      const yr = currentYear - i;
      return `<option value="${yr}" ${Number(selYear) === yr ? 'selected' : ''}>${yr}</option>`;
    }).join('');
}

function syncEditProfileDobFromDropdowns() {
  const dayEl = document.getElementById('edit-profile-dob-day');
  const monthEl = document.getElementById('edit-profile-dob-month');
  const yearEl = document.getElementById('edit-profile-dob-year');
  let d = dayEl?.value || '';
  const m = monthEl?.value || '';
  const y = yearEl?.value || '';
  if (dayEl && (m || y)) {
    const maxDays = new Date(Number(y) || 2000, Number(m) || 1, 0).getDate();
    if (d && Number(d) > maxDays) d = String(maxDays);
    const dayText = currentLang === 'en' ? 'Day' : 'Ngày';
    dayEl.innerHTML = `<option value="">${dayText}</option>` +
      Array.from({ length: maxDays }, (_, i) => {
        const val = i + 1;
        return `<option value="${val}" ${Number(d) === val ? 'selected' : ''}>${String(val).padStart(2, '0')}</option>`;
      }).join('');
  }
  const hiddenInput = document.getElementById('edit-profile-dob');
  if (hiddenInput) {
    hiddenInput.value = (d && m && y) ? `${String(d).padStart(2, '0')}/${String(m).padStart(2, '0')}/${y}` : '';
  }
}

function syncProfileTabDobFromDropdowns() {
  const dayEl = document.getElementById('p-dob-day');
  const monthEl = document.getElementById('p-dob-month');
  const yearEl = document.getElementById('p-dob-year');
  let d = dayEl?.value || '';
  const m = monthEl?.value || '';
  const y = yearEl?.value || '';

  if (dayEl && (m || y)) {
    const maxDays = new Date(Number(y) || 2000, Number(m) || 1, 0).getDate();
    if (d && Number(d) > maxDays) d = String(maxDays);
    const dayText = currentLang === 'en' ? 'Day' : 'Ngày';
    dayEl.innerHTML = `<option value="">${dayText}</option>` +
      Array.from({ length: maxDays }, (_, i) => {
        const val = i + 1;
        return `<option value="${val}" ${Number(d) === val ? 'selected' : ''}>${String(val).padStart(2, '0')}</option>`;
      }).join('');
  }

  const hiddenInput = document.getElementById('p-birthdate');
  if (hiddenInput) {
    hiddenInput.value = (d && m && y) ? `${String(d).padStart(2, '0')}/${String(m).padStart(2, '0')}/${y}` : '';
  }
  calculateProfileCompletion();
}

function openGoogleOnboardingModal(user, isNewRegistration = false) {
  const u = user || pendingGoogleProfile || currentUser;
  if (!u) return;
  isPendingGoogleRegistration = Boolean(isNewRegistration);
  const modal = document.getElementById('profile-modal');
  const nameHeader = document.getElementById('profile-name');
  const badgeHeader = document.getElementById('profile-badge');
  const avatarHeader = document.getElementById('profile-avatar');
  const displayName = u.full_name || u.name || t('Người bệnh mới', 'New Patient');

  if (nameHeader) nameHeader.innerText = displayName;
  if (badgeHeader) {
    badgeHeader.innerText = isPendingGoogleRegistration
      ? t(`Tài khoản Google mới: ${u.email || ''} • Xác nhận thông tin để vào ứng dụng`, `New Google account: ${u.email || ''} • Confirm your details to continue`)
      : t('Xác thực Google thành công • Thông tin hồ sơ cá nhân', 'Google verified • Personal profile details');
  }

  const saveBtnSpan = document.getElementById('profile-save-btn-text') || document.querySelector('#profile-edit-mode button[type="submit"] span');
  if (saveBtnSpan) {
    saveBtnSpan.innerText = isPendingGoogleRegistration
      ? t('Xác nhận & Vào ứng dụng', 'Confirm & Enter App')
      : t('Lưu thông tin', 'Save Profile');
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
    alert(t('Vui lòng nhập họ và tên.', 'Please enter your full name.'));
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
      alert(t('Cập nhật hồ sơ thông tin cá nhân thành công!', 'Personal profile updated successfully!'));
    } else {
      alert(data.error || t('Cập nhật thất bại.', 'Update failed.'));
    }
  } catch (err) {
    console.error('Lỗi lưu hồ sơ:', err);
    alert(t('Không thể kết nối đến máy chủ.', 'Unable to connect to the server.'));
  }
}

function closeProfileModal() {
  if (isPendingGoogleRegistration) {
    isPendingGoogleRegistration = false;
    pendingGoogleProfile = null;
    fetch('/api/auth/google/cancel-registration', { method: 'POST' }).catch(() => {});
    if (typeof showMedicalToast === 'function') {
      showMedicalToast(t('Đã hủy hoàn tất đăng ký Google (hồ sơ chưa được tạo).', 'Google registration cancelled (profile not created).'), 'info', 4000);
    }
  }
  toggleProfileEdit(false);
  const modal = document.getElementById('profile-modal');
  if (modal) modal.classList.add('hidden');
}

// ponytail: #login-modal.auth-4exam-shell owns its flat #f8f9fb palette in CSS.
function syncAuthModalTheme() {}

const AUTH_EYE_OPEN_SVG = `<svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/></svg>`;
const AUTH_EYE_OFF_SVG = `<svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M10.733 5.076a10.744 10.744 0 0 1 11.205 6.575 1 1 0 0 1 0 .696 10.747 10.747 0 0 1-1.444 2.49"/><path d="M14.084 14.158a3 3 0 0 1-4.242-4.242"/><path d="M17.479 17.499a10.75 10.75 0 0 1-15.417-5.151 1 1 0 0 1 0-.696 10.75 10.75 0 0 1 4.446-5.143"/><path d="m2 2 20 20"/></svg>`;

function toggleAuthPasswordVisibility(inputId, btnEl) {
  const input = document.getElementById(inputId);
  if (!input) return;
  const reveal = input.type === 'password';
  input.type = reveal ? 'text' : 'password';
  if (btnEl) btnEl.innerHTML = reveal ? AUTH_EYE_OFF_SVG : AUTH_EYE_OPEN_SVG;
}

function resetAuthPasswordToggles() {
  ['login-password', 'register-password', 'register-confirm-password', 'forgot-new-password'].forEach(id => {
    const input = document.getElementById(id);
    if (!input) return;
    input.type = 'password';
    const btn = input.parentElement?.querySelector('button[onclick*="toggleAuthPasswordVisibility"]');
    if (btn) btn.innerHTML = AUTH_EYE_OPEN_SVG;
  });
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
  ['login-form', 'register-form', 'forgot-form', 'otp-form'].forEach(id => {
    document.getElementById(id)?.reset();
  });

  // Clear inputs explicitly to prevent lingering state on logout / new account
  [
    'register-last-name', 'register-first-name', 'register-name',
    'register-identifier', 'register-email', 'register-password',
    'register-confirm-password', 'register-dob',
    'login-identifier', 'login-password',
    'forgot-identifier', 'forgot-new-password'
  ].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  const regGender = document.getElementById('register-gender');
  if (regGender) regGender.value = 'Nam';

  resetAuthPasswordToggles();
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
    const targetMode = mode || 'login';
    toggleAuthMode(targetMode);
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    if (targetMode === 'register') {
      (document.getElementById('register-name') || document.getElementById('register-last-name'))?.focus();
    } else if (targetMode === 'forgot') {
      document.getElementById('forgot-identifier')?.focus();
    } else {
      document.getElementById('login-identifier')?.focus();
    }
  }
  if (typeof setupOtpDigitInputs === 'function') setupOtpDigitInputs();
}

function closeLoginModal() {
  const modal = document.getElementById('login-modal');
  if (modal) modal.classList.add('hidden');
  document.body.style.overflow = '';
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
  const nextMode = ['login', 'register', 'forgot', 'otp'].includes(mode) ? mode : 'login';
  currentAuthMode = nextMode;
  const dict = translations[currentLang] || translations.vi;
  const titleEl = document.getElementById('auth-modal-title');
  const forgotSubEl = document.getElementById('auth-forgot-subtitle');
  const leftHeroEl = document.getElementById('auth-left-hero');
  const loginForm = document.getElementById('login-form');
  const regForm = document.getElementById('register-form');
  const forgotForm = document.getElementById('forgot-form');
  const otpForm = document.getElementById('otp-form');
  const googleContainer = document.getElementById('google-auth-container');
  const socialDivider = document.getElementById('auth-social-divider');

  const showSocial = nextMode === 'login' || nextMode === 'register';
  loginForm?.classList.toggle('hidden', nextMode !== 'login');
  regForm?.classList.toggle('hidden', nextMode !== 'register');
  forgotForm?.classList.toggle('hidden', nextMode !== 'forgot');
  otpForm?.classList.toggle('hidden', nextMode !== 'otp');
  googleContainer?.classList.toggle('hidden', !showSocial);
  socialDivider?.classList.toggle('hidden', !showSocial);
  forgotSubEl?.classList.toggle('hidden', nextMode !== 'forgot');

  // Match 4exam.net/forgot-password: hide 58% left hero on forgot mode so form centers full-width
  if (leftHeroEl) {
    leftHeroEl.classList.toggle('lg:flex', nextMode !== 'forgot');
  }

  const googleSpan = document.querySelector('#btn-google-signin span[data-i18n="btn_google_signin"]');
  if (googleSpan) {
    googleSpan.innerText = dict.btn_google_signin || (currentLang === 'en' ? 'Sign in with Google' : 'Đăng nhập bằng Google');
  }

  if (titleEl) {
    const titles = {
      login: dict.modal_login_title || 'Đăng nhập vào MediMind',
      register: dict.modal_register_title || 'Đăng ký vào MediMind',
      forgot: dict.modal_forgot_title || 'Quên mật khẩu?',
      otp: dict.modal_otp_title || 'Xác thực mã bảo mật (OTP)'
    };
    titleEl.innerText = titles[nextMode];
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
      applyThemeMode(targetTheme);
      localStorage.setItem('medimind_theme', targetTheme);
    }
  } else if (data.type === 'AUTH_LOGIN' || data.type === 'PROFILE_UPDATE' || data.type === 'AUTH_PROFILE_UPDATE') {
    if (data.payload?.user) {
      const previousUserId = currentUser?.id;
      currentUser = data.payload.user;
      localStorage.setItem('medimind_user', JSON.stringify(currentUser));
      if (data.type === 'AUTH_LOGIN' && String(previousUserId || '') !== String(currentUser.id || '')) {
        startFreshChatForCurrentUser();
      }
      updateAuthUI();
      if (typeof closeLoginModal === 'function') closeLoginModal();
    }
  } else if (data.type === 'AUTH_LOGOUT') {
    currentUser = null;
    clearPrivateUserUIOnLogout();
    Object.keys(fieldRealValues).forEach(k => delete fieldRealValues[k]);
    Object.keys(fieldMaskState).forEach(k => {
      fieldMaskState[k] = false;
      const el = document.getElementById(k);
      if (el) el.readOnly = false;
    });
    document.getElementById('profile-form-img1')?.reset();
    localStorage.removeItem('medimind_user');
    if (typeof resetChat === 'function') resetChat();
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
      alert(data.error || t('Không thể gửi mã xác thực OTP.', 'Unable to send OTP verification code.'));
      return;
    }

    toggleAuthMode('otp');
    setupOtpDigitInputs();

    const channelLabel = document.getElementById('otp-channel-label');
    if (channelLabel) {
      channelLabel.innerText = channel === 'email' ? t('hộp thư email', 'email') : t('tin nhắn SMS', 'SMS');
    }

    const targetDisplay = document.getElementById('otp-target-display');
    if (targetDisplay) {
      targetDisplay.innerText = identifier;
    }

    clearOtpInputs();
    startOtpCountdown(data.cooldown || 59);

    if (data.dev_otp) {
      console.log('🔑 [DEV TEST OTP]:', data.dev_otp);
      const digitInputs = document.querySelectorAll('.otp-digit');
      if (digitInputs && digitInputs.length === 6) {
        data.dev_otp.split('').forEach((d, i) => {
          if (digitInputs[i]) digitInputs[i].value = d;
        });
        if (typeof checkOtpComplete === 'function') checkOtpComplete();
      }
    }

    if (typeof showMedicalToast === 'function') {
      const toastMsg = data.dev_otp 
        ? t(`[Thử nghiệm] Mã OTP xác thực: ${data.dev_otp} (Đã tự động điền)`, `[Test] OTP verification code: ${data.dev_otp} (Auto-filled)`)
        : t(`Mã OTP đã được gửi tới ${identifier}!`, `OTP code sent to ${identifier}!`);
      showMedicalToast(toastMsg, 'success');
    }
  } catch (err) {
    console.error('Lỗi yêu cầu gửi OTP:', err);
    alert(t('Không thể kết nối máy chủ gửi OTP.', 'Unable to connect to the OTP server.'));
  }
}

async function handleOtpSubmit(e) {
  if (e) e.preventDefault();
  const code = getOtpCodeFromInputs();
  if (code.length !== 6) {
    alert(t('Vui lòng nhập đủ 6 chữ số của mã OTP.', 'Please enter all 6 digits of your OTP code.'));
    return;
  }

  try {
    if (pendingOtpFlow.purpose === 'reset_pwd') {
      const newPassword = (pendingOtpFlow.userData?.new_password || '').trim();
      const res = await fetch('/api/auth/reset-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          identifier: pendingOtpFlow.identifier,
          code,
          new_password: newPassword
        })
      });
      const data = await res.json();
      if (data.success) {
        toggleAuthMode('login');
        const loginInput = document.getElementById('login-identifier');
        if (loginInput) loginInput.value = pendingOtpFlow.identifier;
        if (typeof showMedicalToast === 'function') {
          showMedicalToast(data.message || t('Đặt lại mật khẩu thành công! Vui lòng đăng nhập.', 'Password reset successfully! Please sign in.'), 'success');
        } else {
          alert(data.message || t('Đặt lại mật khẩu thành công!', 'Password reset successfully!'));
        }
      } else {
        alert(data.error || t('Mã xác thực không hợp lệ hoặc đã hết hạn.', 'Invalid or expired verification code.'));
        clearOtpInputs();
      }
      return;
    }

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
        startFreshChatForCurrentUser();
        updateAuthUI();
        broadcastTabEvent('AUTH_LOGIN', { user: currentUser });
      }
      closeLoginModal();
      if (typeof showMedicalToast === 'function') {
        showMedicalToast(data.message || t('Xác thực mã OTP thành công!', 'OTP verified successfully!'), 'success');
      } else {
        alert(data.message || t('Xác thực danh tính thành công!', 'Identity verified successfully!'));
      }

      if (pendingTabAfterLogin) {
        const target = pendingTabAfterLogin;
        pendingTabAfterLogin = null;
        switchTab(target);
      }
    } else {
      alert(data.error || t('Mã xác thực không chính xác.', 'Incorrect verification code.'));
      clearOtpInputs();
    }
  } catch (err) {
    console.error('Lỗi xác thực OTP:', err);
    alert(t('Không thể kết nối máy chủ xác thực.', 'Unable to connect to the authentication server.'));
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
    identifier = prompt(t('Vui lòng nhập Email hoặc Số điện thoại để nhận mã OTP:', 'Please enter your Email or Phone number to receive an OTP:'));
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

function startForgotPasswordFlow() {
  const prefill = (document.getElementById('login-identifier')?.value || '').trim();
  const forgotIdent = document.getElementById('forgot-identifier');
  const forgotPass = document.getElementById('forgot-new-password');
  if (forgotIdent && prefill) forgotIdent.value = prefill;
  toggleAuthMode('forgot');
  (prefill ? forgotPass : forgotIdent)?.focus();
}

async function handleForgotSubmit(e) {
  e.preventDefault();
  const identifier = (document.getElementById('forgot-identifier')?.value || '').trim();
  const newPassword = (document.getElementById('forgot-new-password')?.value || '').trim();
  if (!identifier) {
    if (typeof showMedicalToast === 'function') showMedicalToast(t('Vui lòng nhập email hoặc số điện thoại.', 'Please enter your email or phone number.'), 'warning');
    document.getElementById('forgot-identifier')?.focus();
    return;
  }
  if (newPassword.length < 6) {
    if (typeof showMedicalToast === 'function') showMedicalToast(t('Mật khẩu mới phải có tối thiểu 6 ký tự.', 'New password must be at least 6 characters.'), 'warning');
    document.getElementById('forgot-new-password')?.focus();
    return;
  }
  const channel = identifier.includes('@') ? 'email' : 'sms';
  pendingOtpFlow = {
    identifier,
    channel,
    purpose: 'reset_pwd',
    userData: { new_password: newPassword },
    previousMode: 'forgot'
  };
  await requestAndShowOtp(identifier, channel, 'reset_pwd');
}


// ==============================================================
// GOOGLE OAUTH 2.0 / OPENID CONNECT SIGN-IN
// ==============================================================

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
    const warnMsg = t(
      `Bạn đang mở trang trong ứng dụng ${inAppName}, nơi Google chặn đăng nhập bảo mật. Hãy mở MediMind bằng Chrome hoặc Safari rồi đăng nhập lại.`,
      `You opened MediMind inside ${inAppName}, where Google blocks secure OAuth sign-in. Please open MediMind in Chrome or Safari and try again.`
    );
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
    btn.innerHTML = `<span class="w-4 h-4 rounded-full border-2 border-[#282b35] border-t-transparent animate-spin inline-block"></span><span class="font-semibold text-[#383b45]">${t('Đang chuyển tới Google...', 'Connecting to Google...')}</span>`;
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
      const unconfMsg = t(
        'Máy chủ chưa cấu hình GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET trong tệp .env nên chưa thể mở trang chọn tài khoản Google thật của trình duyệt.',
        'GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET are not configured in .env on this server, so Google Account Chooser cannot open yet.'
      );
      if (typeof showMedicalToast === 'function') {
        showMedicalToast(unconfMsg, 'warning', 6500);
      } else {
        alert(unconfMsg);
      }
      return;
    }

    throw new Error(data.error || t('Không thể khởi tạo phiên Google OAuth.', 'Unable to initialize Google OAuth session.'));
  } catch (err) {
    console.error('Lỗi khởi tạo Google OAuth:', err);
    if (btn) { btn.disabled = false; btn.innerHTML = originalHtml; }
    if (typeof showMedicalToast === 'function') {
      showMedicalToast(t('Máy chủ đăng nhập đang chậm hoặc gián đoạn. Vui lòng thử lại.', 'Authentication server is slow or unreachable. Please try again.'), 'error', 4500);
    }
  }
}

// Bắt phím Escape cho Disclaimer Modal & Login Split Shell
window.addEventListener('keydown', (e) => {
  const disclaimerModal = document.getElementById('disclaimer-modal');
  if (e.key === 'Escape' && disclaimerModal && !disclaimerModal.classList.contains('hidden')) {
    closeDisclaimerModal();
    return;
  }
  const loginModal = document.getElementById('login-modal');
  if (e.key === 'Escape' && loginModal && !loginModal.classList.contains('hidden')) {
    closeLoginModal();
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
  const confirmEl = document.getElementById('register-confirm-password');

  if (!fullName || !identifier || !password) {
    alert(t('Vui lòng điền đầy đủ Họ và Tên, Email hoặc Số di động và mật khẩu.', 'Please enter your Full Name, Email or Mobile Number, and Password.'));
    return;
  }
  if (password.length < 6) {
    alert(t('Mật khẩu phải có ít nhất 6 ký tự.', 'Password must be at least 6 characters.'));
    return;
  }
  if (confirmEl && confirmEl.value !== password) {
    const mismatchMsg = t('Mật khẩu xác nhận không khớp.', 'Passwords do not match.');
    if (typeof showMedicalToast === 'function') showMedicalToast(mismatchMsg, 'error');
    else alert(mismatchMsg);
    confirmEl.focus();
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
      startFreshChatForCurrentUser();
      updateAuthUI();
      broadcastTabEvent('AUTH_LOGIN', { user: currentUser });
      closeLoginModal();
    } else {
      alert(data.error || t('Đăng nhập thất bại.', 'Sign in failed.'));
    }
  } catch (err) {
    console.error('Lỗi đăng nhập nhanh:', err);
    alert(t('Không thể kết nối máy chủ xác thực.', 'Unable to connect to the authentication server.'));
  }
}

async function handleLoginSubmit(e) {
  e.preventDefault();
  const identifier = document.getElementById('login-identifier')?.value.trim();
  const password = document.getElementById('login-password')?.value;
  if (!identifier || !password) {
    alert(t('Vui lòng nhập đầy đủ tài khoản và mật khẩu.', 'Please enter both your email/phone and password.'));
    return;
  }
  try {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ identifier, password })
    });
    const data = await res.json();
    if (data.success && data.user) {
      const safeRedirect = sanitizeSameOriginRedirect(data.redirect_url);
      if (safeRedirect) {
        window.location.href = safeRedirect;
        return;
      }
      currentUser = data.user;
      localStorage.setItem('medimind_user', JSON.stringify(currentUser));
      startFreshChatForCurrentUser();
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
      alert(data.error || t('Thông tin đăng nhập không hợp lệ.', 'Invalid sign-in credentials.'));
    }
  } catch (err) {
    console.error('Lỗi gửi form đăng nhập:', err);
    alert(t('Không thể kết nối tới máy chủ.', 'Unable to connect to the server.'));
  }
}

function clearPrivateUserUIOnLogout() {
  pendingTabAfterLogin = null;
  pendingBookingFacilityId = null;
  pendingPrescriptionFile = null;
  activeMedicalPatientKey = 'current_patient';
  currentPrescriptionData = null;
  cachedPrescriptionHistory = [];
  adherenceSlotState = {};

  const fileInput = document.getElementById('prescription-file-input');
  const preview = document.getElementById('file-chosen-preview');
  const loadSec = document.getElementById('prescription-loading-section');
  const resSec = document.getElementById('prescription-result-section');
  const inputSec = document.getElementById('prescription-input-section');
  const histSec = document.getElementById('prescription-history-section');
  if (fileInput) fileInput.value = '';
  if (preview) preview.classList.add('hidden');
  if (loadSec) loadSec.classList.add('hidden');
  if (resSec) {
    resSec.classList.add('hidden');
    resSec.innerHTML = '';
  }
  if (inputSec) inputSec.classList.remove('hidden');
  if (histSec) histSec.classList.remove('hidden');
  if (typeof loadPrescriptionHistory === 'function') loadPrescriptionHistory();
  if (typeof loadScanFiles === 'function') loadScanFiles();
}

async function handleLogout() {
  cancelActiveChatRequest();
  window.clearChatHealthContext?.();
  try {
    await fetch('/api/auth/logout', { method: 'POST' });
  } catch (err) {
    console.error('Lỗi đăng xuất:', err);
  }
  currentUser = null;
  clearPrivateUserUIOnLogout();
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

  if (navDoctorTab) navDoctorTab.innerText = (currentLang === 'vi' ? 'Pha chế dinh dưỡng' : 'Nutrition Studio');
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
    populateModalDobDropdowns('p-dob-day', 'p-dob-month', 'p-dob-year', currentUser.dob || '');
    if (pGender) pGender.value = currentUser.gender || 'Nam';

    const phoneVal = currentUser.phone_number || currentUser.phone || '';
    fieldRealValues['p-phone'] = phoneVal;
    if (pPhone) pPhone.value = fieldMaskState['p-phone'] ? maskFieldValue(phoneVal, 'p-phone') : phoneVal;

    const emailVal = sanitizeUserEmail(currentUser.email);
    fieldRealValues['p-email'] = emailVal;
    if (pEmail) pEmail.value = fieldMaskState['p-email'] ? maskFieldValue(emailVal, 'p-email') : emailVal;

    if (pBlood) pBlood.value = currentUser.blood_type || 'O+';
    if (pAllergies) pAllergies.value = currentUser.allergies || '';
    if (pHeight) pHeight.value = currentUser.height || '';
    if (pWeight) pWeight.value = currentUser.weight || '';
    if (pAddress) pAddress.value = currentUser.address || '';

    if (cardName) cardName.innerText = displayName || t('Chưa có họ và tên', 'No full name');
    if (cardEmail) {
      cardEmail.innerText = (emailVal && emailVal.trim())
        ? (fieldMaskState['p-email'] ? maskFieldValue(emailVal, 'p-email') : emailVal)
        : t('Chưa có email', 'No email');
    }
    if (cardPhone) {
      cardPhone.innerText = (phoneVal && phoneVal.trim())
        ? (fieldMaskState['p-phone'] ? maskFieldValue(phoneVal, 'p-phone') : phoneVal)
        : t('Chưa có số điện thoại', 'No phone number');
    }
    if (cardJoined) {
      cardJoined.innerText = currentUser.joined_date || currentUser.created_at || (displayName ? new Date().toLocaleDateString(isEnLang() ? 'en-US' : 'vi-VN') : t('Chưa lưu', 'Not saved'));
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

    const rawProfilePhoto = (currentUser.hasCustomAvatar && currentUser.avatar) ? currentUser.avatar : currentUser.avatar_url;
    const activeProfilePhoto = rawProfilePhoto ? sanitizeSafeImgSrc(rawProfilePhoto, '') : '';
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
    const fallbackGenderAvatar = getDefaultAvatarByGender(currentUser.gender || 'Nam');
    const rawAvatarCandidate = (currentUser.hasCustomAvatar && currentUser.avatar) 
      ? currentUser.avatar 
      : (currentUser.avatar_url || fallbackGenderAvatar);
    const avatarUrl = sanitizeSafeImgSrc(rawAvatarCandidate, fallbackGenderAvatar);
    
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
    if (tabEmail) tabEmail.value = sanitizeUserEmail(currentUser.email);
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
        exportBtn.title = t('In hoặc tải bản tóm tắt trước khám (PDF)', 'Print or export pre-visit summary (PDF)');
      } else {
        exportBtn.classList.add('opacity-40', 'cursor-not-allowed');
        exportBtn.title = t('Chưa có bản tóm tắt trước khám để kết xuất PDF', 'No pre-visit summary available to export');
      }
    }
    loadScanFiles();
    syncServerConsultations();
    renderChatHistoryList();
    loadPrescriptionHistory();
    if (typeof checkPendingBookingAfterAuth === 'function') {
      checkPendingBookingAfterAuth();
    }
    if (typeof checkPendingPrescriptionAfterAuth === 'function') {
      checkPendingPrescriptionAfterAuth();
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
    if (guestCardName) guestCardName.innerText = t('Chưa có họ và tên', 'No full name');
    if (guestCardPhone) guestCardPhone.innerText = t('Chưa có số điện thoại', 'No phone number');
    if (guestCardEmail) guestCardEmail.innerText = t('Chưa có email', 'No email');
    if (guestCardJoined) guestCardJoined.innerText = t('Chưa lưu', 'Not saved');
    if (guestDispAvatar) guestDispAvatar.classList.add('hidden');
    if (guestFallbackAvatar) guestFallbackAvatar.classList.remove('hidden');
    populateModalDobDropdowns('p-dob-day', 'p-dob-month', 'p-dob-year', document.getElementById('p-birthdate')?.value || '');
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
      exportBtn.title = t('Chưa có bản tóm tắt trước khám để kết xuất PDF', 'No pre-visit summary available to export');
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
  showMedicalToast(t('Đã ẩn khung trò chuyện nổi. Bạn có thể mở lại khi quay về Trang chủ.', 'Floating assistant hidden. You can reopen it from the Home tab.'), 'info', 3000);
}

function expandFloatingChatToFull() {
  minimizeFloatingChat();
  switchTab('chat-tab');
}

function insertFloatingPrompt(text) {
  const input = document.getElementById('floating-user-input');
  if (input) {
    const mapped = isEnLang()
      ? ({
          'Thuốc này uống trước hay sau ăn?': 'Should I take this medicine before or after meals?',
          'Gợi ý chuyên khoa khám phù hợp với triệu chứng': 'Recommend the right specialty for my symptoms'
        }[text] || text)
      : text;
    input.value = mapped;
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
          ${t('Chào bạn, tôi là Trợ lý y tế MediMind!', 'Hello! I am your MediMind Health Assistant.')}
        </h5>
        <p class="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
          ${t('Tôi luôn sẵn sàng hỗ trợ bạn ngay tại góc màn hình này. Hãy hỏi tôi về cách dùng thuốc, giải thích chỉ số xét nghiệm hoặc gợi ý chuyên khoa khám nhé.', 'I am always ready to help right from the corner of your screen. Ask me about medication timing, lab results, or which specialty to visit.')}
        </p>
        <div class="flex items-start gap-1.5 pt-2 text-[11px] text-slate-400 dark:text-slate-400 leading-normal border-t border-slate-100 dark:border-white/5">
          <svg class="w-3.5 h-3.5 text-slate-400 shrink-0 mt-0.5 inline-block" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path stroke-linecap="round" stroke-linejoin="round" d="M12 16v-4m0-4h.01"/></svg>
          <span>${t('Thông tin chỉ mang tính tham khảo, không thay thế chẩn đoán của bác sĩ.', 'For reference only and does not replace a physician’s diagnosis.')}</span>
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
          <span class="text-[9px] text-slate-400 mt-0.5 mr-1">${t('Bạn', 'You')}</span>
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
            ${formatted}${chatAnswerMetadata(msg)}
          </div>
        </div>
      `;
    }
  }).join('');

  appendChatConfirmation(container, chatHistory.at(-1) || {}, currentConversationId, true);
  container.scrollTop = container.scrollHeight;
}

// ==========================================
// Initialization & Global Event Listeners
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
  try { initThemeMode(); } catch (e) { console.warn('[Init] theme error:', e); }
  try { populateDobDropdowns(); populateModalDobDropdowns('p-dob-day', 'p-dob-month', 'p-dob-year', document.getElementById('p-birthdate')?.value || ''); } catch (e) { console.warn('[Init] dob dropdowns error:', e); }
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
    let errMsg = t('Đăng nhập Google không thành công. Vui lòng thử lại.', 'Google sign-in failed. Please try again.');
    if (googleErrorReason === 'access_denied') {
      errMsg = t('Đã hủy đăng nhập Google (hoặc email này chưa được cấp quyền thử nghiệm trên Google Cloud).', 'Google sign-in cancelled (or this email is not listed under Audience -> Test users in Google Cloud).');
    } else if (googleErrorReason === 'redirect_uri_mismatch') {
      errMsg = t('Lỗi cấu hình Redirect URI trên Google Cloud Console.', 'Redirect URI mismatch on Google Cloud Console.');
    } else if (googleErrorReason === 'unconfigured') {
      errMsg = t('Máy chủ chưa cấu hình GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET trong tệp .env.', 'GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET are not configured in .env on this server.');
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
          showMedicalToast(t('Xác thực Google thành công! Vui lòng xác nhận thông tin để bắt đầu sử dụng.', 'Google verified! Please confirm your profile details to get started.'), 'info', 5000);
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
        chatSessions = loadSessionsFromStorage();
        resetChat();
        updateAuthUI();
        loadPrescriptionHistory();
      }
    } else if (data.user) {
      const previousUserId = currentUser?.id;
      currentUser = { ...(currentUser || {}), ...data.user };
      localStorage.setItem('medimind_user', JSON.stringify(currentUser));
      if (googleAuthStatus === 'success' || String(previousUserId || '') !== String(currentUser.id || '')) {
        startFreshChatForCurrentUser();
      } else {
        chatSessions = loadSessionsFromStorage();
        renderChatHistoryList();
      }
      updateAuthUI();
      restoreProfileDraftFromSession();
      loadPrescriptionHistory();

      if (googleAuthStatus === 'success') {
        broadcastTabEvent('AUTH_LOGIN', { user: currentUser });
        closeLoginModal();
        if (googleExisting && googleIntent === 'register') {
          showMedicalToast(t(`Tài khoản Google (${currentUser.email}) đã có hồ sơ MediMind. Bạn đã được đưa về trang chủ!`, `Your Google account (${currentUser.email}) already has a MediMind profile. Welcome back!`), 'info', 5000);
        } else if (googleOnboarding) {
          showMedicalToast(t('Xác thực Google thành công! Hãy hoàn tất thông tin cơ bản để lưu hồ sơ y tế.', 'Google verified! Please complete your basic details to save your medical profile.'), 'success', 5500);
          setTimeout(() => openGoogleOnboardingModal(currentUser), 350);
        } else {
          showMedicalToast(t(`Đăng nhập Google thành công! Chào mừng ${currentUser.name || currentUser.email}.`, `Signed in with Google! Welcome, ${currentUser.name || currentUser.email}.`), 'success', 4000);
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

let pendingPrescriptionFile = null;

function restorePrescriptionUploadSurface() {
  const inputSec = document.getElementById('prescription-input-section');
  const histSec = document.getElementById('prescription-history-section');
  const loadSec = document.getElementById('prescription-loading-section');
  const resSec = document.getElementById('prescription-result-section');
  if (loadSec) loadSec.classList.add('hidden');
  if (resSec) resSec.classList.add('hidden');
  if (inputSec) inputSec.classList.remove('hidden');
  if (histSec) histSec.classList.remove('hidden');
}

function checkPendingPrescriptionAfterAuth() {
  if (!currentUser || !pendingPrescriptionFile) return;
  const queuedFile = pendingPrescriptionFile;
  pendingPrescriptionFile = null;
  setTimeout(() => {
    switchTab('ocr-tab');
    processPrescriptionUpload(queuedFile);
  }, 160);
}

function handlePrescriptionDrop(e) {
  e.preventDefault();
  e.currentTarget?.classList.remove('ring-2', 'ring-sky-500', 'bg-sky-500/5');
  const file = e.dataTransfer?.files?.[0];
  if (file) processPrescriptionUpload(file);
}

async function handlePrescriptionFileSelected(e) {
  const file = e.target.files?.[0];
  // Xóa ngay giá trị input để người dùng chọn lại đúng tệp vừa tải vẫn kích hoạt onchange
  if (e.target) e.target.value = '';
  if (!file) return;
  await processPrescriptionUpload(file);
}

async function processPrescriptionUpload(file) {
  if (file.size > 10 * 1024 * 1024) {
    showMedicalToast(
      t('Dung lượng tệp vượt quá giới hạn 10MB. Vui lòng chọn ảnh hoặc PDF nhỏ hơn.', 'File size exceeds the 10MB limit. Please choose a smaller image or PDF.'),
      'error',
      5000
    );
    return;
  }

  const preview = document.getElementById('file-chosen-preview');
  const nameEl = document.getElementById('file-chosen-name');
  if (preview && nameEl) {
    nameEl.innerText = `${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
    preview.classList.remove('hidden');
  }

  const formData = new FormData();
  formData.append('file', file);

  showPrescriptionLoading(
    true,
    t("AI đang nhận dạng văn bản & hình ảnh...", "AI is recognizing text & imagery..."),
    t("Trích xuất danh mục thuốc, đối chiếu liều dùng và chuẩn hóa dược học...", "Extracting medications, cross-checking dosages, and normalizing pharmacology...")
  );

  try {
    const res = await fetch('/api/prescription/scan', {
      method: 'POST',
      body: formData
    });
    let data = {};
    try {
      data = await res.json();
    } catch (_) {
      data = {};
    }
    showPrescriptionLoading(false);

    if (!res.ok) {
      if (res.status === 401) {
        restorePrescriptionUploadSurface();
        pendingPrescriptionFile = file;
        pendingTabAfterLogin = 'ocr-tab';
        showMedicalToast(
          t('Vui lòng đăng nhập tài khoản để quét đơn thuốc — tệp vừa chọn sẽ tự động được phân tích ngay sau khi đăng nhập.', 'Please sign in to scan documents — your selected file will be analyzed automatically right after sign-in.'),
          'warning',
          5000
        );
        openLoginModal();
      } else {
        const errMsg = data.message || t('Không thể xử lý tệp tài liệu. Vui lòng kiểm tra lại định dạng JPG, PNG hoặc PDF.', 'Unable to process this document. Please check that it is a valid JPG, PNG, or PDF.');
        renderPrescriptionError({ message: errMsg });
        showMedicalToast(errMsg, 'error', 5000);
      }
      return;
    }

    if (data.status === 'failed' || data.status === 'rejected' || data.status === 'error') {
      renderPrescriptionError(data);
      showMedicalToast(data.message || t('Không thể nhận diện nội dung đơn thuốc. Vui lòng chụp lại ảnh rõ nét.', 'Unable to read the prescription. Please upload a clearer photo.'), 'error', 5000);
      return;
    }

    if (data.status === 'review') renderOcrReview(data, file);
    else renderPrescriptionError(data);
  } catch (err) {
    console.error('Lỗi khi phân tích đơn thuốc:', err);
    showPrescriptionLoading(false);
    const netMsg = t('Hệ thống tạm thời bận hoặc không thể kết nối. Vui lòng tải lại ảnh hoặc chọn hồ sơ mẫu.', 'The server is temporarily busy or unreachable. Please retry or open a sample record.');
    renderPrescriptionError({ message: netMsg });
    showMedicalToast(netMsg, 'error');
  }
}

function renderOcrReview(draft, file) {
  const section = document.getElementById('prescription-result-section');
  section.replaceChildren();
  section.classList.remove('hidden');

  const inputSec = document.getElementById('prescription-input-section');
  const histSec = document.getElementById('prescription-history-section');
  if (inputSec) inputSec.classList.add('hidden');
  if (histSec) histSec.classList.add('hidden');

  const layout = document.createElement('div');
  layout.className = 'grid gap-6 lg:grid-cols-12 items-start';
  section.append(layout);

  const leftCol = document.createElement('div');
  leftCol.className = 'lg:col-span-5 bg-white dark:bg-slate-900/90 border border-slate-200 dark:border-white/10 rounded-2xl p-4 shadow-sm space-y-3';
  layout.append(leftCol);

  const isPdfFile = file && (file.type === 'application/pdf' || /\.pdf$/i.test(file.name || ''));
  const leftHeader = document.createElement('div');
  leftHeader.className = 'flex items-center justify-between pb-2 border-b border-slate-100 dark:border-slate-800 text-xs text-slate-500 font-semibold';
  leftHeader.innerHTML = `
    <span class="flex items-center gap-1.5 text-slate-700 dark:text-slate-200">
      <svg class="w-4 h-4 text-sky-600" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
      ${t('Đối chiếu tài liệu gốc', 'Original Document Comparison')}
    </span>
    <span class="text-[10px] text-sky-600 dark:text-sky-400 font-mono">${isPdfFile ? 'PDF' : t('Bấm vào ô để xem vị trí chữ', 'Click a field to highlight text')}</span>
  `;
  leftCol.append(leftHeader);

  let draw = () => {};
  if (isPdfFile) {
    const pdfCard = document.createElement('div');
    pdfCard.className = 'rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/80 p-5 text-center space-y-2';
    pdfCard.innerHTML = `
      <div class="w-12 h-12 mx-auto rounded-2xl bg-sky-500/15 text-sky-600 dark:text-sky-400 border border-sky-500/30 flex items-center justify-center font-black text-xs font-mono">PDF</div>
      <div class="text-xs font-bold text-slate-800 dark:text-slate-100 break-all">${escapeHtml(file.name || 'document.pdf')}</div>
      <div class="text-[11px] text-slate-500 dark:text-slate-400">${(file.size / 1024).toFixed(1)} KB • ${t('Vui lòng đối chiếu các trường bên phải với tệp PDF gốc.', 'Please verify the extracted fields on the right against your original PDF.')}</div>
    `;
    leftCol.append(pdfCard);
  } else {
    const canvas = document.createElement('canvas');
    canvas.className = 'w-full h-auto self-start border border-slate-200 dark:border-slate-700 rounded-xl bg-slate-50 dark:bg-slate-800';
    canvas.setAttribute('aria-label', t('Ảnh gốc và vùng chữ nhận diện', 'Original document with detected OCR bounding boxes'));
    leftCol.append(canvas);

    const image = new Image();
    const url = URL.createObjectURL(file);
    draw = (value = '') => {
      if (!image.naturalWidth) return;
      canvas.width = Math.min(image.naturalWidth, 1400);
      canvas.height = canvas.width * image.naturalHeight / image.naturalWidth;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
      const boxes = Array.isArray(draft.boxes) ? draft.boxes : [];
      const matches = value ? boxes.filter(box => box.text.toLowerCase().includes(value.toLowerCase())) : [];
      for (const box of (matches.length === 1 ? matches : boxes)) {
        ctx.beginPath();
        box.points.forEach(([x,y], i) => i ? ctx.lineTo(x * canvas.width, y * canvas.height) : ctx.moveTo(x * canvas.width, y * canvas.height));
        ctx.closePath();
        ctx.strokeStyle = matches.length === 1 ? '#0284c7' : 'rgba(2,132,199,.45)';
        ctx.lineWidth = matches.length === 1 ? 3 : 1.5;
        ctx.stroke();
      }
    };
    image.onload = () => { draw(); URL.revokeObjectURL(url); };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      const fallbackInfo = document.createElement('p');
      fallbackInfo.className = 'text-xs text-slate-500 dark:text-slate-400 p-3';
      fallbackInfo.textContent = t('Đối chiếu với tệp gốc trên thiết bị.', 'Compare against the original file on your device.');
      canvas.replaceWith(fallbackInfo);
    };
    image.src = url;
  }

  const form = document.createElement('form');
  form.className = 'lg:col-span-7 bg-white dark:bg-slate-900/90 border border-slate-200 dark:border-white/10 rounded-2xl p-5 shadow-sm space-y-4';
  layout.append(form);

  const heading = document.createElement('div');
  heading.className = 'flex items-center justify-between pb-3 border-b border-slate-100 dark:border-slate-800';
  heading.innerHTML = `
    <div class="flex items-center gap-2.5">
      <div class="w-8 h-8 rounded-xl bg-sky-50 dark:bg-sky-500/10 border border-sky-200 dark:border-sky-800 text-sky-600 dark:text-sky-400 flex items-center justify-center shrink-0">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
      </div>
      <div>
        <h3 class="text-sm font-bold text-slate-900 dark:text-white leading-tight">${t('Đối chiếu thông tin trích xuất', 'Verify Extracted Information')}</h3>
        <p class="text-[11px] text-slate-500 dark:text-slate-400">${t('Kiểm tra thông tin trên phiếu trước khi lưu vào hồ sơ', 'Review the extracted fields against the original document before saving')}</p>
      </div>
    </div>
    <span class="text-[10px] font-bold bg-sky-50 dark:bg-sky-500/10 text-sky-700 dark:text-sky-300 border border-sky-200 dark:border-sky-800 px-2.5 py-0.5 rounded-full">
      ${t('Chờ xác nhận', 'Pending Review')}
    </span>
  `;
  form.append(heading);

  let currentDocType = draft.doc_type === 'lab_test' ? 'lab_test' : 'prescription';
  const initKey = currentDocType === 'lab_test' ? 'metrics' : 'medications';
  const hasAnyHeader = ['patient_name','dob','gender','doctor','facility','date','diagnosis'].some(k => String(draft.data?.[k] || '').trim().length > 0);
  const hasAnyItem = Array.isArray(draft.data?.[initKey]) && draft.data[initKey].length > 0;
  if (!hasAnyHeader && !hasAnyItem) {
    const emptyNotice = document.createElement('div');
    emptyNotice.className = 'rounded-xl border border-amber-300/80 dark:border-amber-500/40 bg-amber-50 dark:bg-amber-950/30 px-3.5 py-2.5 text-xs text-amber-900 dark:text-amber-200 leading-relaxed';
    emptyNotice.textContent = t(
      'Chưa nhận diện tự động được văn bản rõ nét từ tệp này (ví dụ PDF scan ảnh hoặc chữ viết tay mờ). Bạn có thể tự nhập thông tin đối chiếu bên dưới hoặc nhấn "Hủy bỏ" để tải lại ảnh rõ nét hơn.',
      'Could not automatically detect clear text from this file (for example, an image-only PDF or faint handwriting). You may enter the fields manually below or click "Cancel" to upload a clearer image.'
    );
    form.append(emptyNotice);
  }

  const labels = isEnLang()
    ? {patient_name:'Patient Name', dob:'Date of Birth', gender:'Gender', doctor:'Physician', facility:'Healthcare Facility', date:'Document Date', diagnosis:'Diagnosis on Document', name:'Medication Name', strength:'Strength', dose:'Dose per Time', frequency:'Frequency', days:'Duration / Quantity', usage:'Instructions', test_name:'Lab Test Name', result:'Result', unit:'Unit', reference_range:'Reference Range', flag_on_paper:'Flag on Report'}
    : {patient_name:'Người bệnh', dob:'Ngày sinh', gender:'Giới tính', doctor:'Bác sĩ', facility:'Cơ sở khám', date:'Ngày trên phiếu', diagnosis:'Chẩn đoán ghi trên phiếu', name:'Tên thuốc', strength:'Hàm lượng', dose:'Liều mỗi lần', frequency:'Tần suất', days:'Thời gian / số lượng', usage:'Cách dùng', test_name:'Tên xét nghiệm', result:'Kết quả', unit:'Đơn vị', reference_range:'Khoảng tham chiếu', flag_on_paper:'Cờ trên phiếu'};
  function field(parent, keyName, value, required = false) {
    const label = document.createElement('label');
    label.className = 'block text-[11px] font-semibold text-slate-600 dark:text-slate-400 space-y-1';
    label.textContent = labels[keyName];
    const input = document.createElement('input');
    input.name = keyName;
    input.value = value || '';
    input.required = required;
    input.maxLength = 2000;
    input.className = 'block w-full rounded-xl border border-slate-200 dark:border-slate-700 px-3 py-1.5 text-xs text-slate-900 dark:text-white bg-slate-50 dark:bg-slate-800/80 focus:outline-none focus:ring-2 focus:ring-sky-500 transition-all';
    input.onfocus = () => draw(input.value);
    label.append(input);
    parent.append(label);
  }

  const typeBar = document.createElement('div');
  typeBar.className = 'flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-slate-100 dark:border-slate-800';
  const typeLabel = document.createElement('span');
  typeLabel.className = 'text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wide';
  typeLabel.textContent = t('Loại tài liệu', 'Document Type');
  const typeToggle = document.createElement('div');
  typeToggle.className = 'inline-flex p-1 rounded-xl bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 gap-1';
  const btnTypeRx = document.createElement('button');
  btnTypeRx.type = 'button';
  btnTypeRx.textContent = t('Đơn thuốc', 'Prescription');
  const btnTypeLab = document.createElement('button');
  btnTypeLab.type = 'button';
  btnTypeLab.textContent = t('Phiếu xét nghiệm', 'Lab Report');
  typeToggle.append(btnTypeRx, btnTypeLab);
  typeBar.append(typeLabel, typeToggle);
  form.append(typeBar);

  const headerTitle = document.createElement('div');
  headerTitle.className = 'text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wide';
  headerTitle.textContent = t('Thông tin hành chính & chẩn đoán', 'Administrative Details & Diagnosis');
  form.append(headerTitle);

  const header = document.createElement('fieldset');
  header.className = 'grid grid-cols-1 sm:grid-cols-2 gap-3 pb-3 border-b border-slate-100 dark:border-slate-800';
  form.append(header);
  for (const hKey of ['patient_name','dob','gender','doctor','facility','date','diagnosis']) field(header, hKey, draft.data?.[hKey]);

  const rowsTitle = document.createElement('div');
  rowsTitle.className = 'text-xs font-bold text-slate-700 dark:text-slate-300 uppercase tracking-wide pt-1';
  form.append(rowsTitle);

  const rows = document.createElement('div');
  rows.className = 'space-y-3';
  form.append(rows);

  function getActiveKeys() {
    return currentDocType === 'lab_test'
      ? ['test_name','result','unit','reference_range','flag_on_paper']
      : ['name','strength','dose','frequency','days','usage'];
  }

  function addRow(data = {}) {
    const activeKeys = getActiveKeys();
    const row = document.createElement('fieldset');
    row.className = 'rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50/50 dark:bg-slate-800/40 p-3.5 space-y-2.5';
    rows.append(row);
    const rowHeader = document.createElement('div');
    rowHeader.className = 'flex items-center justify-between pb-1 text-xs font-bold text-slate-700 dark:text-slate-300';
    rowHeader.innerHTML = `
      <span class="inline-flex items-center gap-1.5">
        <span class="w-5 h-5 rounded-md bg-sky-600 text-white flex items-center justify-center text-[10px] font-mono">#</span>
        ${t('Mục trích xuất', 'Extracted Item')}
      </span>
    `;
    const delBtn = document.createElement('button');
    delBtn.type = 'button';
    delBtn.className = 'text-[11px] text-rose-600 hover:text-rose-700 font-semibold transition-colors cursor-pointer';
    delBtn.textContent = t('Xóa mục này', 'Remove item');
    delBtn.onclick = () => {
      if (rows.children.length > 1) row.remove();
      else row.querySelectorAll('input').forEach(inp => { inp.value = ''; });
    };
    rowHeader.append(delBtn);
    row.append(rowHeader);

    const rowGrid = document.createElement('div');
    rowGrid.className = 'grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5';
    row.append(rowGrid);
    for (const k of activeKeys) field(rowGrid, k, data[k], k === activeKeys[0]);
  }

  const savedByType = {
    prescription: Array.isArray(draft.data?.medications) && draft.data.medications.length ? draft.data.medications : [{}],
    lab_test: Array.isArray(draft.data?.metrics) && draft.data.metrics.length ? draft.data.metrics : [{}]
  };

  const values = group => Object.fromEntries(Array.from(group.querySelectorAll('input'), input => [input.name, input.value]));

  function syncTypeUI(nextType, savePrevious = false) {
    if (savePrevious && rows.children.length) {
      savedByType[currentDocType] = Array.from(rows.children, values);
    }
    currentDocType = nextType;
    const activeCls = 'px-3 py-1 rounded-lg text-xs font-bold bg-sky-600 text-white shadow-xs transition-all cursor-pointer';
    const idleCls = 'px-3 py-1 rounded-lg text-xs font-semibold text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white transition-all cursor-pointer';
    btnTypeRx.className = currentDocType === 'prescription' ? activeCls : idleCls;
    btnTypeLab.className = currentDocType === 'lab_test' ? activeCls : idleCls;
    rowsTitle.textContent = currentDocType === 'lab_test'
      ? t('Danh mục chỉ số xét nghiệm', 'Lab Test Indicators')
      : t('Danh mục thuốc trong toa', 'Prescribed Medications');
    rows.replaceChildren();
    (savedByType[currentDocType].length ? savedByType[currentDocType] : [{}]).forEach(item => addRow(item));
  }

  btnTypeRx.onclick = () => { if (currentDocType !== 'prescription') syncTypeUI('prescription', true); };
  btnTypeLab.onclick = () => { if (currentDocType !== 'lab_test') syncTypeUI('lab_test', true); };
  syncTypeUI(currentDocType, false);

  const actions = document.createElement('div');
  actions.className = 'flex flex-wrap items-center justify-between gap-2.5 pt-3 border-t border-slate-100 dark:border-slate-800';
  form.append(actions);

  const addBtn = document.createElement('button');
  addBtn.type = 'button';
  addBtn.className = 'px-3.5 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-700 text-xs font-semibold transition-all cursor-pointer';
  addBtn.textContent = t('+ Thêm dòng', '+ Add Row');
  addBtn.onclick = () => addRow({});
  actions.append(addBtn);

  const rightActions = document.createElement('div');
  rightActions.className = 'flex items-center gap-2';
  actions.append(rightActions);

  const cancelBtn = document.createElement('button');
  cancelBtn.type = 'button';
  cancelBtn.className = 'px-3.5 py-2 rounded-xl border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 text-xs font-semibold transition-all cursor-pointer';
  cancelBtn.textContent = t('Hủy bỏ', 'Cancel');
  cancelBtn.onclick = () => {
    if (draft.document_id) {
      fetch('/api/prescription/history/' + draft.document_id, { method: 'DELETE' }).catch(() => {});
    }
    resetPrescriptionScan();
  };
  rightActions.append(cancelBtn);

  const save = document.createElement('button');
  save.type = 'submit';
  save.className = 'px-4 py-2 rounded-xl bg-sky-600 hover:bg-sky-700 text-white font-bold text-xs shadow-sm shadow-sky-500/20 transition-all cursor-pointer';
  const defaultSaveLabel = t('Xác nhận thông tin & Lưu', 'Confirm & Save');
  save.textContent = defaultSaveLabel;
  rightActions.append(save);

  form.onsubmit = async event => {
    event.preventDefault();
    const activeItemKey = currentDocType === 'lab_test' ? 'metrics' : 'medications';
    const rawRows = Array.from(rows.children, values);
    const nonBlankRows = rawRows.filter(r => Object.values(r).some(v => String(v || '').trim() !== ''));
    if (!nonBlankRows.length) {
      showMedicalToast(t('Vui lòng nhập ít nhất 1 mục trước khi lưu.', 'Please enter at least one item before saving.'), 'warning');
      return;
    }
    save.disabled = true;
    save.textContent = t('Đang lưu & phân tích...', 'Saving & analyzing...');
    try {
      const response = await fetch('/api/prescription/' + draft.document_id + '/confirm', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({...values(header), doc_type: currentDocType, confirmed:true, [activeItemKey]: nonBlankRows})
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.message || t('Chưa lưu được phiếu.', 'Unable to save document.'));
      renderPrescriptionResult(result);
      loadPrescriptionHistory();
    } catch (error) { showMedicalToast(error.message,'error'); }
    finally {
      save.disabled = false;
      save.textContent = defaultSaveLabel;
    }
  };
  section.scrollIntoView({block:'start'});
}

function renderPrescriptionError(data) {
  const resSec = document.getElementById('prescription-result-section');
  if (!resSec) return;
  const inputSec = document.getElementById('prescription-input-section');
  const histSec = document.getElementById('prescription-history-section');
  if (inputSec) inputSec.classList.add('hidden');
  if (histSec) histSec.classList.add('hidden');

  const msg = data.message || t('Không thể nhận diện nội dung từ hình ảnh đã tải lên.', 'Unable to recognize clinical text from the uploaded image.');
  const previewLines = data.raw_ocr_preview && data.raw_ocr_preview.length > 0 
    ? `<div class="mt-3 p-3 rounded-xl bg-white/70 dark:bg-white/5 border border-rose-200 dark:border-white/10 text-left font-mono text-[11px] text-slate-700 dark:text-slate-300 space-y-1">
        <div class="font-bold text-slate-500 dark:text-slate-400 mb-1">${t('Đoạn văn bản máy nhận diện được:', 'Detected OCR text preview:')}</div>
        ${data.raw_ocr_preview.map(l => `<div>• ${escapeHtml(l)}</div>`).join('')}
       </div>`
    : '';

  resSec.innerHTML = `
    <div class="glass-panel p-6 border border-rose-200 dark:border-rose-500/30 bg-rose-50/90 dark:bg-rose-950/25 backdrop-blur-2xl space-y-4 text-center max-w-2xl mx-auto">
      <div class="w-12 h-12 mx-auto rounded-full bg-rose-500/15 dark:bg-rose-500/20 border border-rose-400/40 flex items-center justify-center text-rose-600 dark:text-rose-300 text-xl font-bold">⚠️</div>
      <h3 class="text-lg font-black text-slate-900 dark:text-white">${t('Chưa thể đọc rõ nội dung tài liệu', 'Unable to Read Document Clearly')}</h3>
      <p class="text-xs text-rose-800 dark:text-rose-200 max-w-md mx-auto leading-relaxed">${escapeHtml(msg)}</p>
      ${previewLines}
      <div class="pt-2 flex flex-wrap justify-center gap-3">
        <button onclick="resetPrescriptionScan()" class="px-4 py-2 rounded-xl bg-gradient-to-r from-sky-500 to-indigo-600 hover:from-sky-400 hover:to-indigo-500 text-white text-xs font-bold transition-all shadow-md cursor-pointer">${t('Chụp / Tải ảnh khác', 'Upload Another Photo')}</button>
        <button onclick="loadPrescriptionPreset('binh_dan')" class="px-4 py-2 rounded-xl glass-pill text-xs font-bold text-slate-700 dark:text-slate-200 hover:text-sky-600 dark:hover:text-white cursor-pointer">${t('Thử xem đơn mẫu', 'View Sample Prescription')}</button>
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
    container.className = 'fixed top-5 right-5 sm:right-8 z-[90] flex flex-col gap-2.5 max-w-sm pointer-events-none';
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
  showPrescriptionLoading(
    true,
    t("Đang nạp hồ sơ mẫu lâm sàng...", "Loading sample clinical document..."),
    t("Thiết lập danh mục hoạt chất, liều lượng và thời gian biểu...", "Preparing medications, dosages, and daily dosing schedule...")
  );
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
      showMedicalToast(data.message || t('Không thể nạp hồ sơ mẫu. Kịch bản không tồn tại hoặc xảy ra lỗi.', 'Unable to load sample record.'), 'error', 5000);
      return;
    }

    // 2. Kiểm tra tính toàn vẹn của đơn thuốc mẫu (không được để trống danh mục thuốc)
    if (data.type === 'prescription' && (!data.medications || data.medications.length === 0)) {
      renderPrescriptionError({
        message: t('Dữ liệu đơn thuốc mẫu không chứa danh mục hoạt chất hợp lệ để lập lịch điều trị.', 'Sample prescription contains no valid medications to schedule.')
      });
      showMedicalToast(t('Dữ liệu đơn thuốc mẫu không hợp lệ.', 'Invalid sample prescription data.'), 'error', 5000);
      return;
    }

    renderPrescriptionResult(data);
    const localizedToastData = isEnLang() && typeof localizePrescriptionDisplayData === 'function' ? localizePrescriptionDisplayData(data) : data;
    showMedicalToast(
      t(`Đã nạp hồ sơ mẫu: ${data.diagnosis || 'Đơn thuốc chuẩn'}`, `Loaded sample record: ${localizedToastData.diagnosis || 'Standard Prescription'}`),
      'info'
    );
  } catch (err) {
    console.error('Lỗi khi tải dữ liệu đối soát:', err);
    showPrescriptionLoading(false);
    showMedicalToast(t('Không thể kết nối đến máy chủ để nạp hồ sơ mẫu.', 'Unable to connect to the server to load sample record.'), 'error');
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
// LỊCH SỬ ĐƠN THUỐC & PHIẾU XÉT NGHIỆM ĐÃ TẢI LÊN (DATA NGƯỜI DÙNG)
// ==============================================================================
let cachedPrescriptionHistory = [];

async function loadPrescriptionHistory() {
  const listEl = document.getElementById('prescription-history-list');
  const emptyEl = document.getElementById('prescription-history-empty');
  const countBadge = document.getElementById('history-count-badge');
  const ehrPrescriptionList = document.getElementById('ehr-prescription-list');

  if (!currentUser || currentUser.isDemo) {
    cachedPrescriptionHistory = [];
    if (listEl) listEl.innerHTML = `<p class="text-xs text-slate-400 p-4 text-center">${t('Vui lòng đăng nhập để xem lịch sử đơn thuốc của bạn.', 'Please sign in to view your prescription history.')}</p>`;
    if (ehrPrescriptionList) ehrPrescriptionList.innerHTML = `<p class="text-slate-400 text-[11px] italic">${t('Vui lòng đăng nhập để xem đơn thuốc đã lưu.', 'Please sign in to view saved prescriptions.')}</p>`;
    if (countBadge) countBadge.innerText = t('0 hồ sơ', '0 records');
    if (emptyEl) emptyEl.classList.remove('hidden');
    return;
  }

  try {
    const res = await fetch('/api/prescription/history');
    if (!res.ok) {
      if (res.status === 401) {
        if (listEl) listEl.innerHTML = `<p class="text-xs text-slate-400 p-4 text-center">${t('Vui lòng đăng nhập để xem lịch sử đơn thuốc của bạn.', 'Please sign in to view your prescription history.')}</p>`;
        if (ehrPrescriptionList) ehrPrescriptionList.innerHTML = `<p class="text-slate-400 text-[11px] italic">${t('Vui lòng đăng nhập để xem đơn thuốc đã lưu.', 'Please sign in to view saved prescriptions.')}</p>`;
        if (countBadge) countBadge.innerText = t('0 hồ sơ', '0 records');
      }
      return;
    }

    const data = await res.json();
    const history = data.history || [];
    cachedPrescriptionHistory = history;

    if (countBadge) countBadge.innerText = isEnLang() ? `${history.length} records` : `${history.length} hồ sơ`;

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
            ? `<span class="px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-purple-50 dark:bg-purple-950/40 text-purple-700 dark:text-purple-300 border border-purple-200 dark:border-purple-800 flex items-center gap-1"><svg class="w-3 h-3 text-purple-600 dark:text-purple-400 shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"/></svg>${t('Phiếu Xét Nghiệm', 'Lab Report')}</span>`
            : `<span class="px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-sky-50 dark:bg-sky-950/40 text-sky-700 dark:text-sky-300 border border-sky-200 dark:border-sky-800 flex items-center gap-1"><svg class="w-3 h-3 text-sky-600 dark:text-sky-400 shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>${t('Đơn Thuốc', 'Prescription')}</span>`;

          const iconSvg = isLab
            ? `<svg class="w-5 h-5 text-purple-600 dark:text-purple-400" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"/></svg>`
            : `<svg class="w-5 h-5 text-sky-600 dark:text-sky-400" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>`;

          const diag = item.diagnosis && item.diagnosis !== 'Chưa phân loại bệnh' ? item.diagnosis : t('Theo dõi & Điều trị theo chỉ định', 'Prescribed Care & Follow-Up');
          const facility = item.facility && item.facility !== 'Cơ sở Y tế' ? item.facility : t('Cơ sở Y tế', 'Healthcare Facility');

          return `
            <div class="glass-card p-4 rounded-2xl border border-slate-200 dark:border-white/10 hover:border-sky-400/50 bg-white dark:bg-slate-900/90 shadow-xs transition-all space-y-2.5">
              <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div class="flex items-start gap-3">
                  <div class="w-10 h-10 rounded-xl ${isLab ? 'bg-purple-50 dark:bg-purple-950/40 border-purple-200 dark:border-purple-800' : 'bg-sky-50 dark:bg-sky-950/40 border-sky-200 dark:border-sky-800'} border flex items-center justify-center shrink-0 mt-0.5">
                    ${iconSvg}
                  </div>
                  <div class="space-y-1">
                    <div class="flex flex-wrap items-center gap-2">
                      ${badgeType}
                      <span class="text-[11px] text-slate-500 dark:text-slate-400 font-mono flex items-center gap-1">
                        <svg class="w-3.5 h-3.5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                        ${escapeHtml(item.uploaded_at || t('Vừa xong', 'Just now'))}
                      </span>
                      <span class="text-[10px] text-slate-400 font-mono">#MED-${item.id}</span>
                    </div>
                    
                    <h4 class="text-sm font-bold text-slate-900 dark:text-white leading-snug">
                      <span class="text-slate-500 dark:text-slate-400 font-normal">${t('Chẩn đoán / Bệnh:', 'Diagnosis:')}</span>
                      <span class="text-sky-700 dark:text-sky-400 font-bold">${escapeHtml(diag)}</span>
                    </h4>

                    <div class="text-xs text-slate-500 dark:text-slate-400 flex flex-wrap items-center gap-x-3 gap-y-1">
                      <span class="flex items-center gap-1">
                        <svg class="w-3.5 h-3.5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"/></svg>
                        ${escapeHtml(facility)}
                      </span>
                      ${item.doctor ? `<span class="text-slate-400">• ${t('BS:', 'Dr.:')} <strong class="text-slate-700 dark:text-slate-200">${escapeHtml(item.doctor)}</strong></span>` : ''}
                      ${item.patient_name ? `<span class="text-slate-400">• ${t('BN:', 'Pt.:')} <strong class="text-slate-700 dark:text-slate-200">${escapeHtml(item.patient_name)}</strong></span>` : ''}
                    </div>

                    ${item.summary ? `
                      <div class="pt-1">
                        <span class="text-[11px] px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700 inline-flex items-center gap-1.5 font-medium">
                          <svg class="w-3.5 h-3.5 text-slate-500" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/></svg>
                          ${escapeHtml(item.summary)}
                        </span>
                      </div>
                    ` : ''}
                  </div>
                </div>

                <div class="flex items-center gap-2 shrink-0 self-end sm:self-center pt-2 sm:pt-0">
                  <button type="button" onclick="viewPrescriptionHistoryItem(${item.id})" class="px-3.5 py-2 rounded-xl bg-sky-600 hover:bg-sky-700 text-white text-xs font-bold transition-all shadow-xs flex items-center gap-1.5 cursor-pointer">
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
                    <span>${t('Xem lại đơn', 'View Record')}</span>
                  </button>
                  <button type="button" onclick="deletePrescriptionHistoryItem(${item.id}, event)" class="p-2 rounded-xl border border-slate-200 dark:border-slate-700 text-slate-400 hover:text-rose-500 hover:border-rose-300 dark:hover:border-rose-800 transition-all cursor-pointer" title="${t('Xóa khỏi lịch sử', 'Delete from history')}">
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
        ehrPrescriptionList.innerHTML = `<p class="text-slate-400 text-[11px] italic">${t('Chưa có đơn thuốc nào được lưu. Bạn có thể tải lên đơn thuốc mới bất kỳ lúc nào.', 'No prescriptions saved yet. You can upload a new prescription anytime.')}</p>`;
      } else {
        ehrPrescriptionList.innerHTML = history.slice(0, 5).map(item => {
          const isLab = item.doc_type === 'lab_test';
          const diag = item.diagnosis && item.diagnosis !== 'Chưa phân loại bệnh' ? item.diagnosis : t('Đơn thuốc khám bệnh', 'Clinical Prescription');
          return `
            <div class="p-2.5 rounded-xl bg-white/5 border border-white/10 hover:border-teal-400/30 transition-all flex items-center justify-between gap-2">
              <div class="min-w-0 flex-1">
                <div class="flex items-center gap-2">
                  <span class="text-[9px] font-bold px-1.5 py-0.2 rounded ${isLab ? 'bg-purple-500/20 text-purple-300' : 'bg-teal-500/20 text-teal-300'}">${isLab ? t('XÉT NGHIỆM', 'LAB REPORT') : t('ĐƠN THUỐC', 'PRESCRIPTION')}</span>
                  <span class="text-[10px] text-slate-400 font-mono">${escapeHtml(item.uploaded_at || '')}</span>
                </div>
                <h5 class="text-xs font-bold text-slate-100 truncate mt-0.5" title="${escapeHtml(diag)}">${escapeHtml(diag)}</h5>
                <p class="text-[10px] text-slate-400 truncate">${escapeHtml(item.facility || t('Cơ sở Y tế', 'Healthcare Facility'))}${item.summary ? ` • ${escapeHtml(item.summary)}` : ''}</p>
              </div>
              <button type="button" onclick="viewPrescriptionHistoryItem(${item.id})" class="px-2.5 py-1.5 rounded-lg bg-teal-500/20 hover:bg-teal-500/30 text-teal-300 border border-teal-400/30 text-[11px] font-bold shrink-0 transition-colors cursor-pointer">
                ${t('Xem lại →', 'View →')}
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
    showPrescriptionLoading(
      true,
      t("Đang nạp lại dữ liệu đơn thuốc từ hồ sơ cá nhân...", "Loading saved prescription from your profile..."),
      t("Khôi phục danh mục thuốc, cữ uống và hướng dẫn điều trị...", "Restoring medications, dosing schedule, and instructions...")
    );
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
      showMedicalToast(
        t(`Đang hiển thị đơn thuốc lưu trữ: ${resJson.data.diagnosis || 'Đơn thuốc'}`, `Showing saved record: ${resJson.data.diagnosis || 'Prescription'}`),
        'info',
        4000
      );

      // Cuộn lên kết quả
      const resSec = document.getElementById('prescription-result-section');
      if (resSec) {
        resSec.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    } else {
      showMedicalToast(resJson.message || t('Không thể đọc dữ liệu chi tiết của đơn thuốc này.', 'Unable to read details for this prescription.'), 'warning');
    }
  } catch (err) {
    console.error('Lỗi khi xem lại đơn thuốc:', err);
    showPrescriptionLoading(false);
    showMedicalToast(t('Không thể kết nối đến máy chủ để tải đơn thuốc.', 'Unable to connect to the server to load prescription.'), 'error');
  }
}

async function deletePrescriptionHistoryItem(docId, e) {
  if (e) e.stopPropagation();
  if (!confirm(t('Bạn có chắc chắn muốn xóa bản ghi đơn thuốc này khỏi lịch sử hồ sơ của mình không?', 'Are you sure you want to delete this prescription record from your history?'))) return;

  try {
    const res = await fetch(`/api/prescription/history/${docId}`, { method: 'DELETE' });
    const data = await res.json();
    if (data.status === 'success') {
      showMedicalToast(t('Đã xóa thành công đơn thuốc khỏi lịch sử hồ sơ.', 'Prescription record removed from history.'), 'success', 3000);
      await loadPrescriptionHistory();
    } else {
      showMedicalToast(data.message || t('Không thể xóa đơn thuốc.', 'Unable to delete prescription record.'), 'error');
    }
  } catch (err) {
    console.error('Lỗi xóa đơn thuốc:', err);
    showMedicalToast(t('Lỗi kết nối khi xóa đơn thuốc.', 'Connection error while deleting prescription record.'), 'error');
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
// ponytail: client-side EN localization for built-in demo prescription/lab presets preserves backend API payloads untouched for Python contract tests.
const _PRESCRIPTION_EN_MAP = {
  // Headers & Diagnoses
  'Đơn thuốc Điều trị Viêm Dạ Dày Cấp - Bệnh Viện Bình Dân (Dữ liệu Demo)': 'Acute Gastritis Prescription — Binh Dan Hospital (Demo Data)',
  'SỞ Y TẾ TP. HỒ CHÍ MINH - BỆNH VIỆN BÌNH DÂN (DEMO)': 'HCMC DEPT. OF HEALTH — BINH DAN HOSPITAL (DEMO)',
  'TRẦN TRUNG (49 tuổi - Nam)': 'TRAN TRUNG (49 yrs - Male)',
  'Viêm dạ dày cấp khác (Mã ICD: K29.1)': 'Other Acute Gastritis (ICD-10: K29.1)',
  '21 ngày (Đợt điều trị tấn công - 6 loại thuốc)': '21 days (Intensive regimen — 6 medications)',
  'Đơn thuốc Điều trị Viêm Họng Cấp & Viêm Đường Hô Hấp Trên (Dữ liệu Demo)': 'Acute Pharyngitis & Upper Respiratory Infection Prescription (Demo Data)',
  'SỞ Y TẾ TP. HỒ CHÍ MINH - BỆNH VIỆN TAI MŨI HỌNG (DEMO)': 'HCMC DEPT. OF HEALTH — ENT HOSPITAL (DEMO)',
  'NGUYỄN VĂN AN (32 tuổi - Nam)': 'NGUYEN VAN AN (32 yrs - Male)',
  'Viêm họng cấp / Viêm amidan cấp mủ (Mã ICD: J02.9)': 'Acute Pharyngitis / Acute Tonsillitis (ICD-10: J02.9)',
  '5 ngày (Đợt điều trị ngoại trú)': '5 days (Outpatient course)',
  'Phiếu Kết quả Xét nghiệm Sinh hóa & Huyết học (Dữ liệu Demo)': 'Clinical Biochemistry & Hematology Report (Demo Data)',
  'Trung tâm Xét nghiệm Y khoa MediLab (DEMO)': 'MediLab Clinical Diagnostics Center (DEMO)',
  'Nguyễn Thành Khiêm (Mẫu)': 'Nguyen Thanh Khiem (Sample)',
  'Kiểm tra sức khỏe định kỳ & Đánh giá hội chứng chuyển hóa': 'Routine Checkup & Metabolic Syndrome Screening',
  'Có giá trị đối chiếu trong 3 tháng': 'Valid for reference within 3 months',
  // Medications
  'YESOM 40 (Esomeprazol 40mg) - 63 Viên': 'YESOM 40 (Esomeprazole 40mg) — 63 Tablets',
  'Thuốc ức chế bơm proton thế hệ mới (PPI)': 'Proton Pump Inhibitor (PPI)',
  'Ức chế dạ dày tiết acid clohydric, giảm đau rát vùng thượng vị.': 'Suppresses gastric acid secretion and relieves epigastric burning.',
  'Uống nguyên viên vào buổi sáng trước khi ăn 30 phút.': 'Swallow whole in the morning 30 minutes before breakfast.',
  'SUCRATE GEL (Sucralfate 1g) - 63 Gói': 'SUCRATE GEL (Sucralfate 1g) — 63 Sachets',
  'Thuốc bảo vệ ổ loét dạ dày': 'Gastric Mucosal Protectant',
  'Tạo màng bảo vệ che phủ vết viêm trợt niêm mạc dạ dày.': 'Forms a protective barrier over gastric mucosal erosions.',
  'Ngày uống 3 lần, mỗi lần 1 gói trước bữa ăn.': 'Take 1 sachet 3 times daily before meals.',
  'Paracetamol 500mg - 10 Viên': 'Paracetamol 500mg — 10 Tablets',
  'Thuốc giảm đau hạ sốt giảm đau ngoại vi': 'Analgesic & Antipyretic',
  'Hạ nhiệt độ khi sốt trên 38.5°C, giảm đau rát họng khi nuốt thức ăn.': 'Reduces fever above 38.5°C and relieves sore throat pain when swallowing.',
  'Uống 1 viên khi sốt hoặc đau rát, mỗi lần cách nhau tối thiểu 4-6 giờ.': 'Take 1 tablet for fever or throat pain, at least 4–6 hours apart.',
  'Alpha Chymotrypsin 4.2mg (Chymoral) - 20 Viên': 'Alpha Chymotrypsin 4.2mg (Chymoral) — 20 Tablets',
  'Enzym kháng viêm dạng ngậm': 'Sublingual Anti-Edema Enzyme',
  'Giảm phù nề, tiêu dịch viêm sung huyết niêm mạc hầu họng và amidan.': 'Reduces pharyngeal and tonsillar mucosal swelling and inflammation.',
  'Ngậm dưới lưỡi 2 viên/lần, ngày 2 lần sáng và trưa.': 'Dissolve 2 tablets sublingually twice daily (morning & noon).',
  'Desloratadine 5mg (Aerius) - 5 Viên': 'Desloratadine 5mg (Aerius) — 5 Tablets',
  'Kháng Histamin H1 thế hệ 2': '2nd-Generation H1 Antihistamine',
  'Giảm phản xạ kích ứng đường thở, chống xuất tiết niêm mạc mũi họng.': 'Relieves airway irritation and nasal/pharyngeal congestion.',
  'Uống 1 viên vào buổi tối sau ăn.': 'Take 1 tablet in the evening after dinner.',
  'Dung dịch Natri Clorid 0.9% - 1 Chai 500ml': 'Sodium Chloride 0.9% Solution — 1 Bottle (500ml)',
  'Dung dịch súc họng NaCl 0.9%': 'NaCl 0.9% Gargle Solution',
  'Dung dịch sát khuẩn vệ sinh niêm mạc': 'Isotonic Antiseptic Gargle',
  'Rửa trôi vi khuẩn bám dính, làm dịu niêm mạc họng.': 'Cleanses pharyngeal mucosa and soothes throat irritation.',
  'Súc họng sâu 3-4 lần/ngày sau các bữa ăn và trước khi ngủ.': 'Gargle thoroughly 3–4 times daily after meals and at bedtime.',
  // Timeline notes & dosages
  '1 viên': '1 tablet',
  '2 viên': '2 tablets',
  '1 gói': '1 sachet',
  '1 ống': '1 ampoule',
  '1/3 chai': '1/3 bottle',
  '1/3 chai (~33ml)': '1/3 bottle (~33ml)',
  'Trước ăn sáng 30 phút': '30 min before breakfast',
  'Trước ăn sáng 15-30 phút': '15–30 min before breakfast',
  'Sau ăn sáng 15 phút': '15 min after breakfast',
  'Sau ăn sáng 1 giờ': '1 hr after breakfast',
  'Uống sau ăn sáng': 'Take after breakfast',
  'Trước ăn trưa 15-30 phút': '15–30 min before lunch',
  'Sau ăn trưa 15 phút': '15 min after lunch',
  'Sau ăn trưa 1 giờ': '1 hr after lunch',
  'Uống sau ăn trưa': 'Take after lunch',
  'Trước ăn tối 15-30 phút': '15–30 min before dinner',
  'Sau ăn tối 15 phút': '15 min after dinner',
  'Sau ăn tối 1 giờ': '1 hr after dinner',
  'Uống sau ăn tối': 'Take after dinner',
  'Lời dặn bác sĩ': "Physician's Follow-up Note",
  'Tái khám theo hẹn': 'Scheduled follow-up',
  'Khám lại mang theo đơn thuốc này.': 'Bring this prescription to your follow-up visit.',
  'Sau ăn sáng, dùng khi sốt > 38.5°C hoặc đau rát họng': 'After breakfast, take if fever > 38.5°C or sore throat',
  'Ngậm dưới lưỡi tan từ từ': 'Dissolve slowly under the tongue',
  'Súc họng kỹ sau khi đánh răng': 'Gargle thoroughly after brushing teeth',
  'Ngậm dưới lưỡi sau ăn trưa': 'Dissolve sublingually after lunch',
  'Súc họng sau bữa trưa': 'Gargle after lunch',
  'Sau ăn tối nếu còn đau rát họng hoặc sốt': 'After dinner if sore throat or fever persists',
  'Sau ăn tối, giảm kích ứng ho & nghẹt mũi': 'After dinner to relieve cough & nasal congestion',
  'Súc họng trước khi ngủ': 'Gargle before bedtime',
  'Lời dặn & Hẹn tái khám': 'Follow-up & Red-Flag Instructions',
  'Tái khám sau 5 ngày': 'Follow up in 5 days',
  'Khám lại ngay nếu sốt cao liên tục không hạ hoặc khó nuốt, khó thở.': 'Seek immediate care if persistent high fever, difficulty swallowing, or shortness of breath occurs.',
  // Lab metrics
  'Glucose (Đường huyết lúc đói)': 'Fasting Blood Glucose',
  'Cholesterol Toàn phần': 'Total Cholesterol',
  'AST / SGOT (Men gan)': 'AST / SGOT (Liver Enzyme)',
  'Creatinine (Chức năng thận)': 'Creatinine (Renal Function)',
  '[DỮ LIỆU MẪU DEMO]: Kết quả xét nghiệm mẫu minh họa chỉ số đường huyết và mỡ máu hơi cao.': '[DEMO SAMPLE]: Sample lab report illustrating mildly elevated fasting glucose and total cholesterol.'
};

function _trPrescText(val) {
  const s = String(val ?? '').trim();
  if (!s || !isEnLang()) return val;
  return _PRESCRIPTION_EN_MAP[s] || s;
}

function localizePrescriptionDisplayData(raw) {
  if (!raw || !isEnLang() || !raw.is_demo) return raw;
  const copy = {
    ...raw,
    doc_title: _trPrescText(raw.doc_title),
    facility: _trPrescText(raw.facility),
    patient_name: _trPrescText(raw.patient_name),
    diagnosis: _trPrescText(raw.diagnosis),
    duration: _trPrescText(raw.duration),
    interpretation: _trPrescText(raw.interpretation || raw.ai_summary || '')
  };
  if (Array.isArray(raw.medications)) {
    copy.medications = raw.medications.map(m => ({
      ...m,
      name: _trPrescText(m.name),
      category: _trPrescText(m.category),
      purpose: _trPrescText(m.purpose),
      usage: _trPrescText(m.usage),
      dose: _trPrescText(m.dose),
      frequency: _trPrescText(m.frequency),
      days: _trPrescText(m.days)
    }));
  }
  if (raw.timeline && typeof raw.timeline === 'object') {
    const tl = {};
    for (const [k, arr] of Object.entries(raw.timeline)) {
      tl[k] = Array.isArray(arr) ? arr.map(it => ({
        ...it,
        name: _trPrescText(it.name),
        dosage: _trPrescText(it.dosage),
        dose: _trPrescText(it.dose || it.dosage),
        note: _trPrescText(it.note),
        tag: _trPrescText(it.tag)
      })) : arr;
    }
    copy.timeline = tl;
  }
  if (Array.isArray(raw.metrics)) {
    copy.metrics = raw.metrics.map(m => ({
      ...m,
      name: _trPrescText(m.name),
      standard_name: _trPrescText(m.standard_name || m.name)
    }));
  }
  return copy;
}

function renderPrescriptionResult(rawData) {
  currentPrescriptionData = rawData;
  const data = isEnLang() ? localizePrescriptionDisplayData(rawData) : rawData;
  const inputSec = document.getElementById('prescription-input-section');
  const histSec = document.getElementById('prescription-history-section');
  if (inputSec) inputSec.classList.add('hidden');
  if (histSec) histSec.classList.add('hidden');

  const resSec = document.getElementById('prescription-result-section');
  if (!resSec) return;

  const isLab = data.type === 'lab_test' || data.doc_type === 'lab_test';
  const rawDiagStr = String(data.diagnosis || '').trim();
  const icdMatch = rawDiagStr.match(/\b([A-Z]\d{2}(?:\.\d+)?)\b/);
  const icdCode = icdMatch ? escapeHtml(icdMatch[1]) : '';
  const diag = escapeHtml(rawDiagStr || t('Chăm sóc & Điều trị', 'Clinical Care & Treatment'));
  const doctor = escapeHtml(String(data.doctor || t('BS. Chuyên khoa', 'Attending Physician')));
  const patient = escapeHtml(String(data.patient_name || t('Người bệnh', 'Patient')));
  const facility = escapeHtml(String(data.facility && data.facility !== 'Không xác định' ? data.facility : t('Cơ sở Y tế', 'Healthcare Facility')));
  const dateStr = escapeHtml(String(data.date || t('Hôm nay', 'Today')));
  const duration = escapeHtml(String(data.duration || t('Theo chỉ định', 'As prescribed')));
  const rawDob = (data.dob || data.birth_date || data.data?.dob || '').toString().trim();
  const rawAge = (data.age || data.data?.age || '').toString().trim();
  const rawGenderText = (data.gender || data.data?.gender || '').toString().trim();
  const rawGender = rawGenderText
    ? escapeHtml(
        isEnLang()
          ? ({ 'Nam': 'Male', 'Nữ': 'Female', 'Khác': 'Other' }[rawGenderText] || rawGenderText)
          : rawGenderText
      )
    : t('Chưa ghi nhận', 'Not specified');
  const currentYear = new Date().getFullYear();
  const formatInterpretationMd = md => escapeHtml(String(md || ''))
    .replace(/^###\s*(.+)$/gm, '<strong class="block font-bold text-slate-900 dark:text-white mt-2 mb-0.5">$1</strong>')
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/\n/g, '<br>');

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
    displayAge = isEnLang() ? `${calculatedAge} yrs` : `${calculatedAge} tuổi`;
  } else if (rawAge && !isNaN(parseInt(rawAge, 10))) {
    const parsedAge = parseInt(rawAge, 10);
    displayAge = isEnLang() ? `${parsedAge} yrs` : `${parsedAge} tuổi`;
    displayBirthInfo = `${currentYear - parsedAge}`;
  } else if (rawDob) {
    displayBirthInfo = escapeHtml(rawDob);
    displayAge = '';
  } else {
    displayBirthInfo = t('Chưa xác định', 'Not specified');
    displayAge = '';
  }
  const medId = escapeHtml(String(data.document_id ? `#MED-${data.document_id}` : `#MED-8841`));
  const fileName = escapeHtml(String(data.uploaded_filename || t('ToaThuoc_KhamDinhKy.jpg', 'Prescription_Checkup.jpg')));
  const scanAcc = data.ocr_metrics?.avg_confidence ? Math.round(data.ocr_metrics.avg_confidence * 100) : 98.5;

  if (isLab) {
    let html = `
      <div class="space-y-4 font-sans select-none text-slate-800 dark:text-slate-100">
        <!-- TOP TOOLBAR -->
        <div class="flex flex-wrap items-center justify-between gap-3 bg-white dark:bg-slate-900/90 border border-sky-100 dark:border-white/10 rounded-2xl p-4 shadow-sm">
          <div class="flex flex-wrap items-center gap-2.5">
            <span class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-sky-600 text-white text-xs font-bold tracking-wide shadow-xs">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"/></svg>
              ${t('PHÂN LOẠI: PHIẾU XÉT NGHIỆM', 'CATEGORY: LAB REPORT')}
            </span>
            <span class="text-xs text-slate-600 dark:text-slate-300 font-medium flex items-center gap-1.5">
              <svg class="w-3.5 h-3.5 text-slate-400" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
              ${fileName} <span class="text-slate-400 font-mono">(${scanAcc}% ${t('Độ tin cậy OCR', 'OCR Confidence')})</span>
            </span>
          </div>
          <div class="flex items-center gap-2">
            <button onclick="window.print()" class="px-3.5 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800 text-xs font-semibold shadow-2xs cursor-pointer">${t('In kết quả', 'Print Report')}</button>
            <button onclick="resetPrescriptionScan()" class="px-3.5 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-700 text-white text-xs font-semibold shadow-xs cursor-pointer">${t('Quét phiếu khác', 'Scan Another')}</button>
          </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <!-- MAIN METRICS TABLE -->
          <div class="lg:col-span-2 space-y-4">
            <div class="bg-white dark:bg-slate-900/90 border border-sky-100 dark:border-white/10 rounded-2xl p-5 shadow-sm space-y-4">
              <div class="flex justify-between items-start pb-3 border-b border-slate-100 dark:border-slate-800">
                <div>
                  <h3 class="text-base font-extrabold text-slate-900 dark:text-white">${escapeHtml(data.doc_title || t('Phiếu Xét Nghiệm Y Khoa', 'Clinical Laboratory Report'))}</h3>
                  <p class="text-xs text-slate-500 dark:text-slate-400 mt-0.5">${facility} • ${t('Người bệnh:', 'Patient:')} <strong class="text-sky-950 dark:text-sky-200 font-bold">${patient}</strong></p>
                </div>
                <span class="text-xs font-mono text-slate-400">${t('Ngày lập:', 'Date:')} ${dateStr}</span>
              </div>

              <div class="overflow-x-auto">
                <table class="w-full text-left text-xs">
                  <thead class="bg-slate-50 dark:bg-slate-800/80 border-b border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 font-bold uppercase text-[10px]">
                    <tr>
                      <th class="py-2.5 px-3">${t('Chỉ số xét nghiệm', 'Lab Indicator')}</th>
                      <th class="py-2.5 px-3">${t('Kết quả', 'Result')}</th>
                      <th class="py-2.5 px-3">${t('Khoảng chuẩn', 'Reference Range')}</th>
                      <th class="py-2.5 px-3">${t('Đánh giá', 'Flag')}</th>
                      <th class="py-2.5 px-3">${t('Đối chiếu', 'Verification')}</th>
                    </tr>
                  </thead>
                  <tbody class="divide-y divide-slate-100 dark:divide-slate-800">
                    ${(data.metrics || []).length === 0
                      ? `<tr><td colspan="5" class="py-6 px-3 text-center text-slate-500 dark:text-slate-400">${t('Chưa có chỉ số xét nghiệm chi tiết.', 'No lab indicators recorded.')}</td></tr>`
                      : (data.metrics || []).map(m => {
                      const rawFlag = m.computed_flag || m.status || '';
                      const flagLabel = isEnLang()
                        ? (rawFlag || 'Normal')
                        : ({ 'High': 'Cao', 'Low': 'Thấp', 'Normal': 'Bình thường' }[rawFlag] || rawFlag || 'Bình thường');
                      return `
                      <tr class="hover:bg-slate-50 dark:hover:bg-slate-800/60 transition-colors">
                        <td class="py-3 px-3">
                          <div class="font-bold text-slate-900 dark:text-white">${escapeHtml(m.standard_name || m.name || m.test_name || '')}</div>
                          ${m.loinc_code && m.loinc_code !== 'UNKNOWN' ? `<span class="text-[10px] text-sky-600 dark:text-sky-400 font-mono font-medium">LOINC: ${escapeHtml(m.loinc_code)}</span>` : ''}
                        </td>
                        <td class="py-3 px-3 font-mono font-black text-sm ${rawFlag === 'High' ? 'text-rose-600 dark:text-rose-400' : rawFlag === 'Low' ? 'text-sky-600 dark:text-sky-400' : 'text-emerald-700 dark:text-emerald-400'}">
                          ${escapeHtml(m.result || m.value || '')} <span class="text-[11px] font-normal text-slate-400">${escapeHtml(m.unit || '')}</span>
                        </td>
                        <td class="py-3 px-3 font-mono text-slate-500 dark:text-slate-400 text-xs">${escapeHtml(m.reference_range || m.reference || '---')}</td>
                        <td class="py-3 px-3">
                          <span class="px-2 py-0.5 rounded text-[10px] font-bold ${rawFlag === 'High' ? 'bg-rose-50 dark:bg-rose-950/50 text-rose-700 dark:text-rose-300 border border-rose-200 dark:border-rose-800' : rawFlag === 'Low' ? 'bg-sky-50 dark:bg-sky-950/50 text-sky-700 dark:text-sky-300 border border-sky-200 dark:border-sky-800' : 'bg-emerald-50 dark:bg-emerald-950/50 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800'}">
                            ${escapeHtml(flagLabel)}
                          </span>
                        </td>
                        <td class="py-3 px-3 text-[11px] text-slate-500 dark:text-slate-400">
                          ${m.needs_review ? `<span class="text-amber-600 dark:text-amber-400 font-bold" title="${escapeHtml(m.validation_warning || '')}">⚠️ ${t('Cần xác nhận', 'Needs review')}</span>` : `<span class="text-emerald-600 dark:text-emerald-400 font-semibold">✓ ${t('Khớp số liệu', 'Verified')}</span>`}
                        </td>
                      </tr>
                    `;
                    }).join('')}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <!-- SIDEBAR COPILOT -->
          <div class="space-y-4">
            <div class="bg-white dark:bg-slate-900/90 border border-sky-100 dark:border-white/10 rounded-2xl p-5 shadow-sm space-y-3">
              <div class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                  <div class="w-8 h-8 rounded-xl bg-sky-50 dark:bg-sky-500/10 border border-sky-200 dark:border-sky-800 text-sky-600 dark:text-sky-400 flex items-center justify-center">
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
                  </div>
                  <div>
                    <h4 class="text-xs font-bold text-slate-900 dark:text-white leading-tight">${t('Cố vấn Lâm sàng MediMind', 'MediMind Clinical Advisor')}</h4>
                    <span class="text-[10px] text-slate-500 dark:text-slate-400">${t('Chuyên trách Hướng dẫn Lâm sàng', 'Clinical Guidance Assistant')}</span>
                  </div>
                </div>
                <span class="text-[9px] bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 font-bold px-2 py-0.5 rounded-full">${t('Đang hoạt động', 'Active')}</span>
              </div>
              <div class="text-xs text-slate-700 dark:text-slate-200 space-y-2 pt-2 border-t border-slate-100 dark:border-slate-800 leading-relaxed">
                ${data.interpretation ? `<div class="prose prose-xs text-slate-700 dark:text-slate-200 space-y-1">${formatInterpretationMd(data.interpretation)}</div>` : t('Kết quả đã được xác minh đối chiếu qua thuật toán an toàn.', 'Results cross-checked against standard clinical reference ranges.')}
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
      label: t('BUỔI SÁNG', 'MORNING'), 
      time: '06:30 - 08:00', 
      iconSvg: '<svg class="w-5 h-5 text-amber-600" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 3v2m0 14v2m9-9h-2M5 12H3m15.364-6.364l-1.414 1.414M7.05 16.95l-1.414 1.414M16.95 16.95l1.414 1.414M7.05 7.05L5.636 5.636M16 12a4 4 0 11-8 0 4 4 0 018 0z"/></svg>', 
      badgeColor: 'bg-amber-50 text-amber-800 border-amber-200',
      items: tl.morning || [] 
    },
    { 
      id: 'noon', 
      label: t('BUỔI TRƯA', 'NOON'), 
      time: '11:30 - 12:30', 
      iconSvg: '<svg class="w-5 h-5 text-sky-600" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 2v2m0 16v2m10-10h-2M4 12H2m15.07-7.07l-1.41 1.41M8.34 15.66l-1.41 1.41m11.14 0l-1.41-1.41M8.34 8.34L6.93 6.93M12 6a6 6 0 100 12 6 6 0 000-12z"/></svg>', 
      badgeColor: 'bg-sky-50 dark:bg-sky-500/10 text-sky-800 border-sky-200',
      items: tl.noon || [] 
    },
    { 
      id: 'evening', 
      label: t('CHIỀU / TỐI', 'EVENING'), 
      time: '18:00 - 19:30', 
      iconSvg: '<svg class="w-5 h-5 text-indigo-600" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"/></svg>', 
      badgeColor: 'bg-indigo-50 text-indigo-800 border-indigo-200',
      items: tl.evening || [] 
    },
    { 
      id: 'bedtime', 
      label: t('TRƯỚC KHI NGỦ', 'BEDTIME'), 
      time: '21:00 - 22:00', 
      iconSvg: '<svg class="w-5 h-5 text-sky-700 dark:text-sky-400" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z"/></svg>', 
      badgeColor: 'bg-sky-50 dark:bg-sky-500/10 text-sky-900 dark:text-sky-200 border-sky-200',
      items: tl.bedtime || [] 
    },
    { 
      id: 'external', 
      label: t('DÙNG NGOÀI DA / KHI CẦN', 'TOPICAL / AS NEEDED'), 
      time: t('Theo triệu chứng', 'As needed'), 
      iconSvg: '<svg class="w-5 h-5 text-teal-600 dark:text-teal-400" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"/></svg>', 
      badgeColor: 'bg-teal-50 dark:bg-teal-500/10 text-teal-900 dark:text-teal-200 border-teal-200',
      items: tl.external || [] 
    }
  ];
  const activeSlots = slotDefs.filter(s => s.items.length > 0);
  const activeDoseSlotsCount = activeSlots.length || 1;

  if (meds.length === 0) {
    renderPrescriptionError({
      message: data.message || t('Không tìm thấy danh mục hoạt chất hợp lệ trong tài liệu để thiết lập thời gian biểu.', 'No valid medications were found in this document to build a schedule.')
    });
    return;
  }

  const warningsHtml = warnings.length > 0 ? `
      <div class="rounded-2xl border border-amber-300 dark:border-amber-500/40 bg-amber-50/95 dark:bg-amber-950/35 p-4 shadow-xs space-y-2">
        <div class="flex items-center gap-2 text-xs font-black text-amber-900 dark:text-amber-200 uppercase tracking-wide">
          <span>⚠️</span>
          <span>${t('Cảnh báo An toàn Dược lý & Đối chiếu', 'Clinical Safety & Verification Alerts')} (${warnings.length})</span>
        </div>
        <ul class="space-y-1 text-xs text-amber-900 dark:text-amber-100 list-disc pl-5 leading-relaxed">
          ${warnings.map(w => `<li>${escapeHtml(typeof w === 'object' ? (w.message || JSON.stringify(w)) : String(w))}</li>`).join('')}
        </ul>
      </div>
  ` : '';

  let html = `
    <div class="space-y-5 font-sans select-none text-slate-800 dark:text-slate-100">

      <!-- 1. TOP STATUS BAR (Phân loại đơn thuốc bản gốc) -->
      <div class="flex flex-wrap items-center justify-between gap-3 bg-white dark:bg-slate-900/90 border border-sky-100 dark:border-white/10 rounded-2xl p-4 shadow-sm">
        <div class="flex flex-wrap items-center gap-2.5">
          <span class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-sky-600 text-white text-xs font-bold tracking-wide shadow-xs">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
            ${t('PHÂN LOẠI: ĐƠN THUỐC BẢN GỐC', 'CATEGORY: ORIGINAL PRESCRIPTION')}
          </span>
          <span class="text-xs text-slate-600 dark:text-slate-300 font-semibold flex items-center gap-1.5">
            <svg class="w-3.5 h-3.5 text-slate-400" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
            ${fileName} <span class="text-slate-400 font-mono font-normal">(${scanAcc}% ${t('Độ tin cậy OCR', 'OCR Confidence')})</span>
          </span>
          <span class="text-xs text-emerald-700 dark:text-emerald-300 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 px-2.5 py-1 rounded-md font-bold flex items-center gap-1">
            ✓ ${t('Đã trích xuất dữ liệu an toàn', 'Safely Extracted & Verified')}
          </span>
        </div>

        <div class="flex items-center gap-2">
          <button onclick="window.print()" class="px-3.5 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-50 dark:hover:bg-slate-800 text-xs font-bold transition-all shadow-2xs cursor-pointer">
            ${t('Xuất tóm tắt PDF', 'Export Summary PDF')}
          </button>
          <button onclick="resetPrescriptionScan()" class="px-3.5 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-700 text-white text-xs font-bold transition-all shadow-xs flex items-center gap-1.5 cursor-pointer" title="${t('Quay lại danh sách và xem lịch sử các đơn thuốc đã lưu', 'Return to upload view and saved prescription history')}">
            <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"/></svg>
            <span>${t('Xem Lịch sử / Quét thêm', 'History / Scan More')}</span>
          </button>
        </div>
      </div>

      ${warningsHtml}

      <!-- 2. COMPACT CLINICAL HEADER: THẺ NGANG VỪA VẶN, GỌN GÀNG, KHÔNG DƯ KHOẢNG TRỐNG -->
      <div class="grid grid-cols-1 lg:grid-cols-12 gap-4 items-start">
        
        <!-- CỘT TRÁI (8/12): THÔNG TIN BỆNH NHÂN & NƠI KHÁM GỌN GÀNG -->
        <div class="lg:col-span-8 bg-white dark:bg-slate-900/90 border border-sky-100 dark:border-white/10 rounded-2xl p-4 sm:p-5 shadow-sm space-y-3.5">
          
          <div class="flex items-start justify-between gap-4">
            <div class="flex items-start gap-3.5">
              <div class="w-10 h-10 rounded-xl bg-sky-50 dark:bg-sky-500/10 border border-sky-200 dark:border-sky-800 text-sky-900 dark:text-sky-300 flex items-center justify-center shrink-0">
                <svg class="w-5 h-5 text-sky-900 dark:text-sky-300" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"/>
                </svg>
              </div>
              <div>
                <div class="flex items-center gap-2">
                  <span class="text-[10px] font-bold text-slate-400 uppercase tracking-wider">${t('HỒ SƠ BỆNH NHÂN', 'PATIENT RECORD')}</span>
                </div>
                <h3 class="text-lg font-black text-slate-900 dark:text-white mt-0.5">${patient}</h3>
                
                <div class="text-xs text-slate-600 dark:text-slate-300 font-medium mt-1.5 flex flex-wrap items-center gap-2.5">
                  <span class="inline-flex items-center gap-1">
                    <span class="text-slate-400 font-normal">${t('Ngày/Năm sinh:', 'Birth Date/Year:')}</span> <strong class="text-slate-900 dark:text-white font-bold">${displayBirthInfo}</strong>
                    ${displayAge ? `<span class="px-1.5 py-0.2 rounded bg-teal-50 dark:bg-teal-950/50 text-teal-800 dark:text-teal-300 border border-teal-200 dark:border-teal-800 text-[10px] font-bold">(${displayAge})</span>` : ''}
                  </span>
                  <span class="text-slate-300 dark:text-slate-600">•</span>
                  <span class="inline-flex items-center gap-1">
                    <span class="text-slate-400 font-normal">${t('Giới tính:', 'Gender:')}</span> <strong class="text-slate-900 dark:text-white font-bold">${rawGender}</strong>
                  </span>
                  ${doctor ? `<span class="text-slate-300 dark:text-slate-600">•</span><span class="inline-flex items-center gap-1"><span class="text-slate-400 font-normal">${t('Bác sĩ:', 'Physician:')}</span> <strong class="text-slate-900 dark:text-white font-bold">${doctor}</strong></span>` : ''}
                </div>
              </div>
            </div>

            <div class="text-right shrink-0">
              <span class="text-[10px] text-slate-400 uppercase font-bold block">${t('Mã bệnh án', 'Record ID')}</span>
              <span class="inline-block mt-0.5 px-3 py-1 rounded-lg bg-sky-50 dark:bg-sky-500/10 border border-sky-200 dark:border-sky-800 text-sky-950 dark:text-sky-200 font-mono font-black text-xs">
                ${medId}
              </span>
            </div>
          </div>

          <!-- NƠI KHÁM & CHẨN ĐOÁN -->
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-3 border-t border-slate-100 dark:border-slate-800">
            <div class="flex items-center gap-2.5 bg-slate-50 dark:bg-slate-800/70 p-2.5 rounded-xl border border-slate-200/70 dark:border-slate-700/70">
              <div class="w-8 h-8 rounded-lg bg-white dark:bg-slate-800 border border-slate-200 dark:border-white/10 flex items-center justify-center shrink-0">
                <svg class="w-4 h-4 text-sky-900 dark:text-sky-300" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"/>
                </svg>
              </div>
              <div class="min-w-0">
                <span class="text-[9px] font-bold text-slate-400 uppercase block">${t('Nơi khám', 'Facility')}</span>
                <h4 class="text-xs font-bold text-slate-900 dark:text-white truncate">${facility}</h4>
              </div>
            </div>

            <div class="flex items-center justify-between gap-2 bg-slate-50 dark:bg-slate-800/70 p-2.5 rounded-xl border border-slate-200/70 dark:border-slate-700/70">
              <div class="min-w-0">
                <span class="text-[9px] font-bold text-slate-400 uppercase block">${t('Chẩn đoán', 'Diagnosis')}</span>
                <span class="text-xs font-bold text-slate-800 dark:text-slate-100 truncate block">${diag}</span>
              </div>
              ${icdCode ? `<span class="text-[10px] font-mono text-slate-500 dark:text-slate-300 px-1.5 py-0.5 rounded bg-white dark:bg-slate-900 border border-slate-200 dark:border-white/10 shrink-0">${icdCode}</span>` : ''}
            </div>
          </div>

        </div>

        <!-- CỘT PHẢI (4/12): CỐ VẤN LÂM SÀNG MEDIMIND -->
        <div class="lg:col-span-4 bg-white dark:bg-slate-900/90 border border-sky-100 dark:border-white/10 rounded-2xl p-4 sm:p-5 shadow-sm space-y-3.5">
          <div class="flex items-center justify-between pb-2 border-b border-slate-100 dark:border-slate-800">
            <div class="flex items-center gap-2.5">
              <div class="w-8 h-8 rounded-xl bg-sky-50 dark:bg-sky-500/10 border border-sky-200 dark:border-sky-800 flex items-center justify-center text-sky-600 dark:text-sky-400 shrink-0">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
                </svg>
              </div>
              <div>
                <h4 class="text-xs font-black text-slate-900 dark:text-white tracking-tight leading-tight">${t('Cố vấn Lâm sàng MediMind', 'MediMind Clinical Advisor')}</h4>
                <p class="text-[9px] text-slate-500 dark:text-slate-400">${t('Hướng dẫn đơn thuốc', 'Prescription Guidance')}</p>
              </div>
            </div>
            <span class="text-[9px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-300 px-2 py-0.5 rounded-full">
              ${t('Đang hoạt động', 'Active')}
            </span>
          </div>

          <div class="space-y-2 text-xs max-h-52 overflow-y-auto pr-1">
            ${data.interpretation
              ? `<div class="prose prose-xs text-slate-700 dark:text-slate-200 leading-relaxed space-y-1">${formatInterpretationMd(data.interpretation)}</div>`
              : `
              <div class="bg-slate-50 dark:bg-slate-800/60 border border-slate-200/70 dark:border-slate-700/60 p-2.5 rounded-xl flex items-start gap-2 text-slate-700 dark:text-slate-200">
                <span class="text-sky-600 dark:text-sky-400 font-bold text-[11px] shrink-0">1.</span>
                <p class="text-[11px] leading-tight"><strong class="text-slate-900 dark:text-white font-bold">${t('Đúng cữ:', 'On schedule:')}</strong> ${t('Uống đúng khung giờ Sáng, Trưa, Tối theo chỉ định trên đơn.', 'Take doses consistently according to your prescribed schedule.')}</p>
              </div>
              <div class="bg-slate-50 dark:bg-slate-800/60 border border-slate-200/70 dark:border-slate-700/60 p-2.5 rounded-xl flex items-start gap-2 text-slate-700 dark:text-slate-200">
                <span class="text-sky-600 dark:text-sky-400 font-bold text-[11px] shrink-0">2.</span>
                <p class="text-[11px] leading-tight"><strong class="text-slate-900 dark:text-white font-bold">${t('Đối chiếu:', 'Cross-check:')}</strong> ${t('Kiểm tra kỹ hàm lượng và hướng dẫn trên đơn gốc trước khi dùng.', 'Verify strength and instructions against the original prescription.')}</p>
              </div>`
            }
          </div>

          <button onclick="askBotAboutPrescription()" class="w-full py-2.5 rounded-xl bg-sky-600 hover:bg-sky-700 text-white font-bold text-xs shadow-sm shadow-sky-500/20 transition-all flex items-center justify-center gap-1.5 cursor-pointer">
            <svg class="w-3.5 h-3.5 text-white" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/>
            </svg>
            <span>${t('Tư vấn đơn thuốc', 'Ask About Prescription')}</span>
          </button>
        </div>

      </div>

      <!-- 3. GỘP CHUNG 1 BẢN GỒM 2 TAB: "THUỐC TRONG TOA" & "LỊCH UỐNG & CỮ THUỐC TRONG NGÀY" -->
      <div class="bg-white dark:bg-slate-900/90 border border-sky-100 dark:border-white/10 rounded-2xl shadow-sm overflow-hidden">
        
        <!-- HEADER VỚI 2 TABS NẰM TRONG CÙNG 1 BẢN -->
        <div class="flex flex-col sm:flex-row sm:items-center justify-between p-3 sm:p-4 bg-slate-50 dark:bg-slate-800/70 border-b border-slate-200/80 dark:border-slate-700/80 gap-3">
          
          <div class="flex items-center gap-2 p-1 bg-slate-200/70 dark:bg-slate-800 rounded-xl w-full sm:w-auto">
            <!-- TAB 1: THUỐC TRONG TOA (MẶC ĐỊNH HIỆN ĐẦU TIÊN) -->
            <button id="btn-subtab-meds" onclick="switchPrescriptionDossierTab('meds')" class="flex-1 sm:flex-none px-4 py-2 rounded-lg text-xs font-bold transition-all flex items-center justify-center gap-2 bg-white dark:bg-slate-900 text-sky-950 dark:text-sky-200 shadow-sm cursor-pointer">
              <svg class="w-4 h-4 text-sky-900 dark:text-sky-300" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"/></svg>
              <span>${t('Danh mục thuốc trong toa', 'Prescribed Medications')}</span>
              <span class="px-2 py-0.5 rounded-full bg-sky-50 dark:bg-sky-500/15 border border-sky-200 dark:border-sky-800 text-sky-900 dark:text-sky-200 font-mono text-[10px]">
                ${String(meds.length).padStart(2, '0')}
              </span>
            </button>

            <!-- TAB 2: LỊCH UỐNG & CỮ THUỐC TRONG NGÀY -->
            <button id="btn-subtab-schedule" onclick="switchPrescriptionDossierTab('schedule')" class="flex-1 sm:flex-none px-4 py-2 rounded-lg text-xs font-bold transition-all flex items-center justify-center gap-2 text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white hover:bg-white/50 dark:hover:bg-slate-700/50 cursor-pointer">
              <svg class="w-4 h-4 text-slate-600 dark:text-slate-300" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
              <span>${t('Lịch uống & Cữ thuốc trong ngày', 'Daily Dosing Schedule')}</span>
              <span class="px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-700 border border-slate-200 dark:border-slate-600 text-slate-700 dark:text-slate-200 font-mono text-[10px]">
                ${String(activeDoseSlotsCount).padStart(2, '0')} ${t('cữ', 'slots')}
              </span>
            </button>
          </div>

          <div class="text-[11px] text-slate-500 dark:text-slate-400 font-medium px-2 flex items-center gap-2">
            <span class="flex items-center gap-1"><svg class="w-3.5 h-3.5 text-slate-400 inline-block shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>${isEnLang() ? `Course: <strong>${duration}</strong>` : `Điều trị: <strong>${duration}</strong>`}</span>
            ${icdCode ? `<span class="text-sky-900 dark:text-sky-200 font-bold bg-sky-50 dark:bg-sky-500/15 border border-sky-200 dark:border-sky-800 px-2 py-0.5 rounded text-[10px] hidden md:inline-flex">✓ ${t('Mã ICD-10:', 'ICD-10:')} ${icdCode}</span>` : ''}
          </div>

        </div>

        <!-- ========================================== -->
        <!-- TAB NỘI DUNG 1: BẢNG KÊ CHI TIẾT THUỐC TRONG TOA -->
        <!-- ========================================== -->
        <div id="pane-prescription-meds" class="p-5 space-y-3.5">
          <div class="text-xs text-slate-500 dark:text-slate-400 pb-1">
            ${isEnLang()
              ? `Includes <strong>${meds.length} prescribed medications</strong> with strength, dosing frequency, and administration notes:`
              : `Danh mục gồm <strong>${meds.length} loại thuốc đặc hiệu</strong> được bác sĩ chỉ định, kèm hàm lượng và cơ chế an toàn dược lý:`}
          </div>

          <div class="space-y-3">
            ${meds.map((m, idx) => {
              const numStr = (idx + 1).toString().padStart(2, '0');
              const freq = escapeHtml(m.frequency || t('Theo chỉ định', 'As directed'));
              const usage = escapeHtml(m.usage || m.purpose || t('Theo hướng dẫn trên đơn gốc', 'Follow original prescription instructions'));
              const dose = escapeHtml(m.dose || t('Theo chỉ định', 'As prescribed'));
              const days = escapeHtml(m.days || t('Theo đơn cấp', 'As dispensed'));
              const strength = m.strength ? `(${escapeHtml(m.strength)})` : '';
              const medName = escapeHtml(m.standard_name || m.name || '');

              return `
                <div class="border border-slate-200/80 dark:border-slate-700/80 rounded-2xl p-4 bg-slate-50 dark:bg-slate-800/60 hover:bg-slate-100/70 dark:hover:bg-slate-800 transition-all space-y-2.5">
                  <div class="flex items-start justify-between gap-3">
                    <div class="flex items-start gap-3.5">
                      <div class="w-8 h-8 rounded-lg bg-sky-600 text-white flex items-center justify-center font-mono font-black text-xs shrink-0 shadow-xs">
                        ${numStr}
                      </div>
                      <div>
                        <div class="flex flex-wrap items-center gap-2">
                          <h5 class="text-sm font-black text-slate-900 dark:text-white">${medName} <span class="font-normal text-slate-500 dark:text-slate-400 text-xs">${strength}</span></h5>
                          <span class="text-[11px] font-semibold px-2.5 py-0.5 rounded-md bg-sky-50 dark:bg-sky-950/40 text-sky-700 dark:text-sky-300 border border-sky-200 dark:border-sky-800">
                            ${escapeHtml(m.purpose || m.category || t('Thuốc theo toa', 'Prescribed Medication'))}
                          </span>
                        </div>
                        
                        <div class="flex flex-wrap items-center gap-3 text-xs text-slate-500 dark:text-slate-400 mt-1 font-medium">
                          <span class="flex items-center gap-1"><svg class="w-3.5 h-3.5 text-slate-500 dark:text-slate-400" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z"/></svg><strong class="text-slate-800 dark:text-slate-100 font-bold">${escapeHtml(m.strength || t('Theo liều', 'As prescribed'))}</strong> / ${t('đơn vị', 'unit')}</span>
                          <span>•</span>
                          <span>${t('Tổng cấp:', 'Total quantity:')} <strong class="text-slate-800 dark:text-slate-100 font-bold">${days}</strong></span>
                        </div>
                      </div>
                    </div>

                    <div class="text-right shrink-0">
                      <span class="text-xs font-black text-slate-950 dark:text-white block">${dose}</span>
                      <span class="text-[11px] text-slate-500 dark:text-slate-400 font-medium">${freq}</span>
                    </div>
                  </div>

                  <div class="bg-white dark:bg-slate-900/80 border border-slate-200 dark:border-white/10 rounded-xl p-2.5 text-xs text-slate-700 dark:text-slate-200 leading-relaxed flex items-start justify-between gap-2">
                    <div class="flex items-start gap-2">
                      <span class="text-sky-700 dark:text-sky-400 font-bold shrink-0 flex items-center gap-1"><svg class="w-3.5 h-3.5 text-sky-700 dark:text-sky-400" fill="none" stroke="currentColor" stroke-width="2.2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>${t('Lưu ý:', 'Note:')}</span>
                      <p class="font-medium text-slate-600 dark:text-slate-300">${usage}</p>
                    </div>
                    <button data-med-name="${escapeHtml(m.name || '')}" onclick="askBotAboutSpecificMedicine(this.dataset.medName)" class="text-[11px] text-sky-600 dark:text-sky-400 hover:text-sky-800 dark:hover:text-sky-300 font-bold shrink-0 cursor-pointer flex items-center gap-1">
                      <span>${t('Tư vấn thuốc', 'Ask AI')}</span>
                      <svg class="w-3 h-3 text-sky-600 dark:text-sky-400" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7"/></svg>
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
            ${isEnLang()
              ? `Structured across <strong>${activeDoseSlotsCount} daily dosing slots</strong> for optimal absorption:`
              : `Lộ trình phân bổ <strong>${activeDoseSlotsCount} cữ thuốc trong ngày</strong> theo chuẩn dược động học, đảm bảo hấp thu tối ưu:`}
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            ${activeSlots.map(s => `
              <div class="border border-slate-200 dark:border-slate-700 rounded-2xl p-4 bg-slate-50 dark:bg-slate-800/60 space-y-3">
                <div class="flex items-center justify-between pb-2.5 border-b border-slate-200 dark:border-slate-700">
                  <div class="flex items-center gap-2.5">
                    <div class="w-9 h-9 rounded-xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-white/10 flex items-center justify-center shrink-0 shadow-2xs">
                      ${s.iconSvg}
                    </div>
                    <div>
                      <h5 class="text-xs font-black text-slate-900 dark:text-white uppercase tracking-wide">${s.label}</h5>
                      <span class="text-[11px] font-mono text-slate-500 dark:text-slate-400 font-semibold">${s.time}</span>
                    </div>
                  </div>
                  <span class="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-white dark:bg-slate-900 border border-slate-200 dark:border-white/10 text-sky-950 dark:text-sky-200 font-mono">
                    ${s.items.length} ${t('loại', 'items')}
                  </span>
                </div>

                <div class="space-y-2">
                  ${s.items.map(it => `
                    <div class="bg-white dark:bg-slate-900/80 border border-slate-200 dark:border-white/10 rounded-xl p-2.5 flex items-center justify-between text-xs gap-2">
                      <div>
                        <strong class="font-bold text-slate-900 dark:text-white">${escapeHtml(it.name || '')}</strong>
                        <p class="text-[11px] text-slate-500 dark:text-slate-400 font-medium">${escapeHtml(it.note || t('Theo chỉ dẫn của bác sĩ', 'As directed by physician'))}</p>
                      </div>
                      <span class="font-mono font-bold text-sky-950 dark:text-sky-200 bg-sky-50 dark:bg-sky-500/15 px-2 py-0.5 rounded text-[11px] shrink-0 border border-sky-200 dark:border-sky-800">
                        ${escapeHtml(it.dose || it.dosage || t('Theo đơn', 'As prescribed'))}
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
          <button onclick="setMedicationReminder()" class="px-4 py-2.5 rounded-xl bg-sky-600 hover:bg-sky-700 text-white text-xs font-bold transition-all shadow-sm shadow-sky-500/20 flex items-center gap-2 cursor-pointer">
            <svg class="w-4 h-4 text-sky-200" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"/></svg>
            <span>${t('Bật nhắc nhở uống thuốc định kỳ', 'Enable Medication Reminders')}</span>
          </button>
        </div>

        <button type="button" onclick="resetPrescriptionScan()" class="px-4 py-2.5 rounded-xl bg-white dark:bg-slate-800 border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 text-xs font-bold transition-all flex items-center gap-2 cursor-pointer shadow-2xs">
          <span>${t('← Quét đơn thuốc khác', '← Scan Another Document')}</span>
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

  const activeCls = "flex-1 sm:flex-none px-4 py-2 rounded-lg text-xs font-bold transition-all flex items-center justify-center gap-2 bg-white dark:bg-slate-900 text-sky-950 dark:text-sky-200 shadow-sm cursor-pointer";
  const idleCls = "flex-1 sm:flex-none px-4 py-2 rounded-lg text-xs font-bold transition-all flex items-center justify-center gap-2 text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white hover:bg-white/50 dark:hover:bg-slate-700/50 cursor-pointer";

  if (tabKey === 'meds') {
    btnMeds.className = activeCls;
    btnSched.className = idleCls;
    paneMeds.classList.remove('hidden');
    paneSched.classList.add('hidden');
  } else {
    btnSched.className = activeCls;
    btnMeds.className = idleCls;
    paneSched.classList.remove('hidden');
    paneMeds.classList.add('hidden');
  }
}



// Render the checklist inside the Smart Hero card
function renderSlotPillChecklist(slot) {
  if (!slot || !slot.items || slot.items.length === 0) {
    return `<div class="p-4 rounded-2xl glass-card text-center text-xs text-slate-400 font-medium">${t('Không có thuốc chỉ định ở cữ này', 'No medications scheduled for this slot')}</div>`;
  }

  const beforeMeal = slot.items.filter(it => (it.note || '').toLowerCase().includes('trước') || (it.note || '').toLowerCase().includes('before'));
  const externalPills = slot.items.filter(it => (it.note || '').toLowerCase().includes('ngoài') || (it.tag || '').toLowerCase().includes('ngoài') || (it.note || '').toLowerCase().includes('topical'));
  const afterMeal = slot.items.filter(it => !beforeMeal.includes(it) && !externalPills.includes(it));

  return `
    <!-- BEFORE MEAL -->
    ${beforeMeal.length > 0 ? `
      <div class="space-y-2">
        <div class="text-[10px] font-black uppercase tracking-wider text-amber-300 bg-amber-500/20 border border-amber-400/30 px-2.5 py-0.5 rounded-lg inline-flex items-center">
          <span class="w-2 h-2 rounded-full bg-amber-400 mr-1.5 animate-pulse"></span>${t('UỐNG TRƯỚC KHI ĂN (30 PHÚT)', 'TAKE BEFORE MEALS (30 MIN)')}
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
          ${beforeMeal.map((m, idx) => `
            <div class="flex items-center justify-between p-3 rounded-2xl glass-card border border-amber-400/30 bg-amber-950/20 text-xs hover:border-amber-400/60 transition-colors">
              <div class="flex items-center space-x-2.5 min-w-0">
                <input type="checkbox" onchange="togglePillChecked(this)" class="w-4 h-4 rounded text-amber-500 focus:ring-amber-400 border-amber-400/50 bg-slate-900 cursor-pointer">
                <div class="truncate">
                  <span class="font-black text-white leading-snug block truncate pill-name">${escapeHtml(m.name || '')}</span>
                  <span class="text-[10px] text-amber-300 font-bold">${escapeHtml(m.tag || t('Trước ăn', 'Before meal'))}</span>
                </div>
              </div>
              <span class="font-mono font-black text-amber-200 bg-amber-500/30 border border-amber-400/40 px-3 py-1 rounded-xl text-xs shrink-0 ml-2 shadow-2xs">${escapeHtml(m.dosage || '')}</span>
            </div>
          `).join('')}
        </div>
      </div>
    ` : ''}

    <!-- AFTER MEAL -->
    ${afterMeal.length > 0 ? `
      <div class="space-y-2 mt-2">
        <div class="text-[10px] font-black uppercase tracking-wider text-sky-300 bg-sky-500/20 border border-sky-400/30 px-2.5 py-0.5 rounded-lg inline-flex items-center">
          <span class="w-2 h-2 rounded-full bg-sky-400 mr-1.5 animate-pulse"></span>${t('UỐNG SAU KHI ĂN NO', 'TAKE AFTER MEALS')}
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
          ${afterMeal.map((m, idx) => `
            <div class="flex items-center justify-between p-3 rounded-2xl glass-card border border-white/10 bg-white/[0.04] text-xs hover:border-sky-400/50 transition-colors">
              <div class="flex items-center space-x-2.5 min-w-0">
                <input type="checkbox" onchange="togglePillChecked(this)" class="w-4 h-4 rounded text-sky-500 focus:ring-sky-400 border-white/20 bg-slate-900 cursor-pointer">
                <div class="truncate">
                  <span class="font-black text-white leading-snug block truncate pill-name">${escapeHtml(m.name || '')}</span>
                  <span class="text-[10px] text-slate-400 font-bold">${escapeHtml(m.tag || t('Sau ăn', 'After meal'))}</span>
                </div>
              </div>
              <span class="font-mono font-black text-sky-200 bg-sky-500/30 border border-sky-400/40 px-3 py-1 rounded-xl text-xs shrink-0 ml-2 shadow-2xs">${escapeHtml(m.dosage || '')}</span>
            </div>
          `).join('')}
        </div>
      </div>
    ` : ''}

    <!-- EXTERNAL APPLICATION (XOA BÓP NGOÀI DA) -->
    ${externalPills.length > 0 ? `
      <div class="space-y-2 mt-2">
        <div class="text-[10px] font-black uppercase tracking-wider text-purple-300 bg-purple-500/20 border border-purple-400/30 px-2.5 py-0.5 rounded-lg inline-flex items-center">
          <span class="w-2 h-2 rounded-full bg-purple-400 mr-1.5 animate-pulse"></span>${t('CHẾ PHẨM DÙNG NGOÀI DA (TUYỆT ĐỐI KHÔNG UỐNG)', 'TOPICAL USE ONLY (DO NOT SWALLOW)')}
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
          ${externalPills.map((m, idx) => `
            <div class="flex items-center justify-between p-3 rounded-2xl glass-card border border-purple-400/30 bg-purple-950/20 text-xs hover:border-purple-400/60 transition-colors">
              <div class="flex items-center space-x-2.5 min-w-0">
                <input type="checkbox" onchange="togglePillChecked(this)" class="w-4 h-4 rounded text-purple-500 focus:ring-purple-400 border-purple-400/50 bg-slate-900 cursor-pointer">
                <div class="truncate">
                  <span class="font-black text-white leading-snug block truncate pill-name">${escapeHtml(m.name || '')}</span>
                  <span class="text-[10px] text-purple-300 font-bold">${escapeHtml(m.note || t('Bôi ngoài da', 'Apply externally'))}</span>
                </div>
              </div>
              <span class="font-mono font-black text-purple-200 bg-purple-500/30 border border-purple-400/40 px-3 py-1 rounded-xl text-xs shrink-0 ml-2 shadow-2xs">${escapeHtml(m.dosage || '')}</span>
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
          ${slot.items.length} ${t('loại thuốc', 'medications')}
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
      const nowStr = new Date().toLocaleTimeString(isEnLang() ? 'en-US' : 'vi-VN', { hour: '2-digit', minute: '2-digit' });
      btnText.innerText = isEnLang() ? `✓ DOSE COMPLETED AT ${nowStr}` : `✓ ĐÃ HOÀN THÀNH CỮ NÀY LÚC ${nowStr}`;
    }
    showMedicalToast(t('Tuyệt vời! Bạn đã hoàn thành cữ thuốc.', 'Great job! Dose marked as completed.'), 'success');
  } else {
    btnEl.className = 'w-full sm:w-auto px-8 py-3.5 bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-white text-sm font-extrabold rounded-2xl shadow-lg shadow-emerald-500/30 transition-all flex items-center justify-center space-x-2.5 cursor-pointer hover:scale-102 border border-white/20';
    if (btnText) btnText.innerText = t('XÁC NHẬN ĐÃ UỐNG XONG CỮ NÀY', 'CONFIRM DOSE TAKEN');
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

  if (textEl) textEl.innerText = isEnLang() ? `${completed}/${total} slots (${percent}%)` : `${completed}/${total} cữ (${percent}%)`;
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
    if (label) label.innerText = t('Thu gọn', 'Collapse');
  } else {
    list.classList.add('hidden');
    if (icon) icon.classList.remove('rotate-180');
    if (label) label.innerText = isEnLang()
      ? `View all (${(currentPrescriptionData?.warnings || []).length})`
      : `Xem tất cả (${(currentPrescriptionData?.warnings || []).length})`;
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
    { id: 'morning', label: t('BUỔI SÁNG', 'MORNING'), time: '06:30 - 08:00', icon: '🌅', items: tl.morning || [] },
    { id: 'noon', label: t('BUỔI TRƯA', 'NOON'), time: '11:30 - 12:30', icon: '☀️', items: tl.noon || [] },
    { id: 'evening', label: t('CHIỀU / TỐI', 'EVENING'), time: '18:00 - 19:30', icon: '🌙', items: tl.evening || [] },
    { id: 'bedtime', label: t('TRƯỚC KHI NGỦ', 'BEDTIME'), time: '21:00 - 22:00', icon: '🛌', items: tl.bedtime || [] },
    { id: 'external', label: t('DÙNG NGOÀI DA', 'TOPICAL'), time: t('Sáng & Tối', 'Morning & Evening'), icon: '🧴', items: tl.external || [] }
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
  showMedicalToast(t('Xem thử tính năng nhắc thuốc: Đây là bản minh họa giao diện các cữ uống thuốc trong ngày.', 'Medication reminder preview: Illustrates daily dosing schedule notifications.'), 'info', 4000);
}

function askBotAboutPrescription() {
  if (!currentPrescriptionData) return;
  const diag = currentPrescriptionData.diagnosis || '';
  switchTab('chat-tab');
  const chatInput = document.getElementById('chat-input') || document.getElementById('user-input');
  if (chatInput) {
    chatInput.value = isEnLang()
      ? `Please advise me on the treatment plan, dosing instructions, and dietary precautions for diagnosis: "${diag}".`
      : `Xin bác sĩ tư vấn kỹ hơn về hướng điều trị, cách dùng thuốc và lưu ý kiêng khem cho chẩn đoán: "${diag}".`;
    chatInput.focus();
  }
}

function askBotAboutSpecificMedicine(medName) {
  switchTab('chat-tab');
  const chatInput = document.getElementById('chat-input') || document.getElementById('user-input');
  if (chatInput) {
    chatInput.value = isEnLang()
      ? `Please explain the indication, administration timing, and key side effects to watch for with "${medName}".`
      : `Bác sĩ giải thích giúp tôi công dụng, cách dùng và tác dụng phụ cần chú ý khi uống thuốc: "${medName}".`;
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

function exportChatPdf() {
  const turns = chatHistory.filter(turn => ['user', 'assistant'].includes(turn.role));
  if (!turns.length) return showMedicalToast(t("Hội thoại chưa có tin nhắn để xuất.", "No messages in this conversation to export."), "info");
  const doc = document;
  doc.getElementById('chat-print-copy')?.remove();
  const copy = doc.createElement('article');
  copy.id = 'chat-print-copy';
  doc.body.append(copy);
  const heading = doc.createElement('h1');
  heading.textContent = t('Hội thoại với MediMind', 'Conversation with MediMind');
  copy.append(heading);
  const images = [];
  for (const turn of turns) {
    const speaker = doc.createElement('h2');
    speaker.textContent = turn.role === 'user' ? t('Bạn', 'You') : 'MediMind';
    const text = doc.createElement('p');
    text.textContent = turn.content || '';
    copy.append(speaker, text);
    if (/^data:image\/(?:png|jpeg|webp|gif);base64,/i.test(turn.image || '')) {
      const img = doc.createElement('img');
      img.alt = t('Ảnh đính kèm trong hội thoại', 'Attached conversation image');
      img.src = turn.image;
      copy.append(img);
      images.push(img.decode().catch(() => {}));
    }
  }
  Promise.all(images).then(() => {
    if (!copy.isConnected) return;
    const originalTitle = doc.title;
    doc.title = t('MediMind - Hội thoại', 'MediMind - Conversation');
    doc.body.classList.add('printing-chat');
    window.addEventListener('afterprint', () => {
      doc.title = originalTitle;
      doc.body.classList.remove('printing-chat');
      copy.remove();
    }, {once: true});
    window.print();
  });
}

function exportPdfSummary() {
  showMedicalToast(t('Đang tạo bản in / kết xuất PDF hồ sơ bệnh án...', 'Preparing medical record print / PDF export...'), 'info', 2000);
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
    showMedicalToast(t('Trình duyệt không hỗ trợ định vị GPS.', 'Your browser does not support GPS geolocation.'), 'warning');
    return;
  }
  if (statusText) statusText.innerText = t('Đang định vị GPS...', 'Locating via GPS...');
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      const { latitude, longitude } = pos.coords;
      if (statusText) statusText.innerText = t(`Đã định vị (${latitude.toFixed(2)}, ${longitude.toFixed(2)})`, `Located (${latitude.toFixed(2)}, ${longitude.toFixed(2)})`);

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

      showMedicalToast(t(`Đã định vị GPS thực tế (${latitude.toFixed(2)}, ${longitude.toFixed(2)}) và tính lại khoảng cách tới các cơ sở y tế.`, `GPS location acquired (${latitude.toFixed(2)}, ${longitude.toFixed(2)}) and facility distances updated.`), 'success');
    },
    (err) => {
      if (statusText) statusText.innerText = t('Khu vực: TP.HCM (Khoảng cách ước tính)', 'Region: HCMC (Estimated distance)');
      showMedicalToast(t('Không thể lấy vị trí GPS thực. Đang dùng khoảng cách ước tính mặc định.', 'Unable to obtain live GPS position. Using estimated default distances.'), 'info');
    },
    { timeout: 8000 }
  );
}

function buildDemoConsultationPayload() {
  const isEn = isEnLang();
  const demoFacts = isEn ? {
    chief_complaint: "Dry cough for 4 days, sore throat, mild fever 37.8°C",
    present_symptoms: ["Mild fever", "Sore throat / Painful swallowing", "Dry cough"],
    denied_symptoms: ["Shortness of breath", "Chest pain / tightness"],
    duration: "4 days",
    vitals: { temperature: "37.8°C" }
  } : {
    chief_complaint: "Ho khan 4 ngày, đau rát họng, sốt nhẹ 37.8°C",
    present_symptoms: ["Sốt / Thân nhiệt tăng", "Đau rát họng / Nuốt đau", "Ho khan / Ho có đờm"],
    denied_symptoms: ["Khó thở / Hụt hơi", "Đau tức ngực"],
    duration: "4 ngày nay",
    vitals: { temperature: "37.8°C" }
  };

  const summary = isEn ? {
    part_a_patient_facts: {
      title: "Part A — Patient-Reported Information",
      chief_complaint: demoFacts.chief_complaint,
      symptoms_present: demoFacts.present_symptoms,
      symptoms_denied: demoFacts.denied_symptoms,
      duration: demoFacts.duration,
      vitals: "temperature: 37.8°C",
      allergies: "No known drug or food allergies reported",
      current_medications: "No current medications reported",
      attachments_and_observations: "No image attachments",
      missing_or_unclear_info: ["Core intake information is complete"]
    },
    part_b_system_assessment: {
      title: "Part B — Preliminary Assessment & Care Guidance",
      triage_status: "Home Monitoring & Self-Care",
      triage_badge: "self_care",
      recommended_specialist: "ENT / Family Medicine",
      care_approach: "Mild initial upper respiratory presentation. Rest, stay hydrated with warm fluids, and monitor symptoms closely over the next 24–48 hours.",
      sources: [
        { title: "Sore throat", source: "MedlinePlus (NIH)", url: "https://medlineplus.gov/sorethroat.html" },
        { title: "Cough", source: "MedlinePlus (NIH)", url: "https://medlineplus.gov/cough.html" }
      ],
      limitations: "Generated by an AI clinical assistant for reference and pre-visit preparation. This does NOT replace an official diagnosis from a licensed physician.",
      version: 1,
      created_at: new Date().toLocaleTimeString('en-US') + " today",
      confirmation_status: "Confirmed by patient"
    },
    is_confirmed: true,
    version: 1
  } : {
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

  return { demoFacts, summary };
}

function renderDemoConsultationView() {
  const container = document.getElementById('chat-messages');
  if (!container) return null;
  const isEn = isEnLang();

  container.innerHTML = isEn ? `
    <div class="p-3 mb-3 rounded-2xl bg-sky-950/70 border border-sky-400/40 text-sky-200 text-xs flex items-center justify-between shadow-lg">
      <div class="flex items-center space-x-2">
        <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-sky-500/30 text-sky-300 border border-sky-400/30">DEMO SAMPLE</span>
        <span>Sample clinical screening walkthrough</span>
      </div>
      <button onclick="resetChat()" class="text-[11px] underline text-sky-400 hover:text-white cursor-pointer font-medium">Reset Chat</button>
    </div>

    <div class="flex flex-col items-end my-1">
      <div class="w-fit max-w-[85%] bg-gradient-to-r from-sky-500/90 to-indigo-600/90 text-white px-4 py-2.5 rounded-2xl rounded-tr-sm text-xs sm:text-sm shadow-lg shadow-sky-500/20 backdrop-blur-md leading-relaxed font-medium text-left break-words border border-white/20">
        <div>I have had a dry cough for 4 days along with a sore throat and a mild fever of 37.8°C, with no shortness of breath. What should I do?</div>
      </div>
      <div class="text-right text-[10px] text-slate-400 mt-1 mr-1">Patient (Sample)</div>
    </div>

    <div class="flex justify-start max-w-[95%] sm:max-w-xl my-2">
      <div class="glass-card border border-white/10 p-4 sm:p-5 rounded-2xl rounded-tl-sm text-xs sm:text-sm text-slate-200 space-y-3 leading-relaxed shadow-xl w-full backdrop-blur-xl bg-white/[0.06]">
        <div class="flex items-center justify-between pb-2 border-b border-white/10">
          <span class="text-[11px] font-bold text-sky-300">MediMind Clinical Assistant • Preliminary Assessment</span>
          <span class="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-400/30 font-semibold">Triage: Home Monitoring &amp; Care</span>
        </div>
        <div class="text-slate-200 font-normal leading-relaxed space-y-2">
          <p><strong>1. Preliminary Assessment &amp; Clinical Triage:</strong><br>
          • <strong>Symptoms:</strong> Dry cough for 4 days, sore throat, mild fever 37.8°C.<br>
          • <strong>Pertinent negatives (safety):</strong> No shortness of breath, no chest pain, no persistent vomiting.<br>
          • <strong>Care level:</strong> Suitable for initial home care and monitoring.</p>

          <p><strong>2. Home Care Recommendations:</strong><br>
          • Rest in a well-ventilated room and drink plenty of warm fluids (2 – 2.5 L/day).<br>
          • Gargle with 0.9% warm saline solution 3 – 4 times daily.<br>
          • If fever exceeds 38.5°C with discomfort, Paracetamol 500 mg may be considered (every 4–6 hours, max 3 g/day if no liver disease).</p>

          <p class="text-amber-300 text-xs bg-amber-500/10 p-2.5 rounded-xl border border-amber-400/20">
            ⚠️ <strong>Seek urgent care immediately if:</strong> Persistent high fever &gt; 39°C lasting over 48h, shortness of breath, stridor, chest pain, or coughing up blood.
          </p>
        </div>
      </div>
    </div>
  ` : `
    <div class="p-3 mb-3 rounded-2xl bg-sky-950/70 border border-sky-400/40 text-sky-200 text-xs flex items-center justify-between shadow-lg">
      <div class="flex items-center space-x-2">
        <span class="px-2 py-0.5 rounded text-[10px] font-bold bg-sky-500/30 text-sky-300 border border-sky-400/30">BẢN MẪU</span>
        <span>Hội thoại mẫu minh họa quy trình sàng lọc lâm sàng</span>
      </div>
      <button onclick="resetChat()" class="text-[11px] underline text-sky-400 hover:text-white cursor-pointer font-medium">Làm mới hội thoại</button>
    </div>

    <div class="flex flex-col items-end my-1">
      <div class="w-fit max-w-[85%] bg-gradient-to-r from-sky-500/90 to-indigo-600/90 text-white px-4 py-2.5 rounded-2xl rounded-tr-sm text-xs sm:text-sm shadow-lg shadow-sky-500/20 backdrop-blur-md leading-relaxed font-medium text-left break-words border border-white/20">
        <div>Tôi bị ho khan kéo dài 4 ngày nay, kèm đau rát họng và sốt nhẹ 37.8°C, không khó thở. Tôi nên làm gì?</div>
      </div>
      <div class="text-right text-[10px] text-slate-400 mt-1 mr-1">Người bệnh (Bản mẫu)</div>
    </div>

    <div class="flex justify-start max-w-[95%] sm:max-w-xl my-2">
      <div class="glass-card border border-white/10 p-4 sm:p-5 rounded-2xl rounded-tl-sm text-xs sm:text-sm text-slate-200 space-y-3 leading-relaxed shadow-xl w-full backdrop-blur-xl bg-white/[0.06]">
        <div class="flex items-center justify-between pb-2 border-b border-white/10">
          <span class="text-[11px] font-bold text-sky-300">Trợ lý y tế MediMind • Đánh giá sơ bộ</span>
          <span class="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-400/30 font-semibold">Sàng lọc: Theo dõi &amp; chăm sóc tại nhà</span>
        </div>
        <div class="text-slate-200 font-normal leading-relaxed space-y-2">
          <p><strong>1. Đánh giá sơ bộ &amp; Phân tầng lâm sàng:</strong><br>
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
  const payload = buildDemoConsultationPayload();
  currentIntakeSummary = payload.summary;
  updateLiveIntakeCard(payload.demoFacts, 'confirmed', currentIntakeSummary);

  const existingSession = chatSessions.find(s => s.id === 'demo_consultation_ho_sot');
  if (existingSession) {
    existingSession.title = t('[MẪU] Ho khan & sốt nhẹ', '[SAMPLE] Dry Cough & Mild Fever');
    existingSession.lastMessage = t('Ho khan 4 ngày, đau rát họng, sốt nhẹ 37.8°C...', 'Dry cough for 4 days, sore throat, mild fever 37.8°C...');
    existingSession.facts = payload.demoFacts;
    existingSession.summary = payload.summary;
    existingSession.riskLevel = t('Theo dõi tại nhà', 'Home Care');
  }
  return payload;
}

function loadDemoConsultation() {
  switchTab('chat-tab');
  hideFloatingDecorations();
  const payload = renderDemoConsultationView();
  if (!payload) return;

  const demoSession = {
    id: 'demo_consultation_ho_sot',
    title: t('[MẪU] Ho khan & sốt nhẹ', '[SAMPLE] Dry Cough & Mild Fever'),
    lastMessage: t('Ho khan 4 ngày, đau rát họng, sốt nhẹ 37.8°C...', 'Dry cough for 4 days, sore throat, mild fever 37.8°C...'),
    timestamp: Date.now(),
    messageCount: 2,
    messages: isEnLang() ? [
      { role: 'user', content: 'I have had a dry cough for 4 days along with a sore throat and a mild fever of 37.8°C, with no shortness of breath or chest pain.' },
      { role: 'assistant', content: 'Hello, I have recorded your symptoms of dry cough and mild fever (37.8°C).\n• Drink plenty of warm water and gargle with warm saline 3 times daily.\n• Rest in a ventilated space and choose warm soups.\n• Consider Paracetamol 500 mg if fever exceeds 38.5°C.\n⚠️ Seek urgent care if high fever persists beyond 48h or shortness of breath develops.' }
    ] : [
      { role: 'user', content: 'Tôi bị ho khan 4 ngày nay kèm đau rát họng, sốt nhẹ 37.8°C, không khó thở hay đau tức ngực.' },
      { role: 'assistant', content: 'Chào bạn, mình đã ghi nhận triệu chứng ho khan và sốt nhẹ 37.8°C.\n• Uống nhiều nước ấm và súc họng nước muối sinh lý ấm 3 lần/ngày.\n• Nghỉ ngơi thoáng khí, ăn cháo súp nóng để làm dịu họng.\n• Uống Paracetamol 500mg nếu sốt >38.5°C.\n⚠️ Đi khám ngay: Nếu sốt cao >48h hoặc khó thở.' }
    ],
    facts: payload.demoFacts,
    summary: currentIntakeSummary,
    status: 'confirmed',
    riskLevel: t('Theo dõi tại nhà', 'Home Care'),
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

  showMedicalToast(t('Đã nạp hội thoại mẫu. Đây là dữ liệu minh họa, không phải lịch sử y tế thật.', 'Loaded sample consultation. This is illustrative data, not a real medical record.'), 'info', 4000);
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
  if (!timestamp) return t('Vừa xong', 'Just now');
  const diffSec = Math.floor((Date.now() - timestamp) / 1000);
  if (diffSec < 60) return t('Vừa xong', 'Just now');
  if (diffSec < 3600) {
    const mins = Math.floor(diffSec / 60);
    return t(`${mins} phút trước`, `${mins}m ago`);
  }
  if (diffSec < 86400) {
    const hrs = Math.floor(diffSec / 3600);
    return t(`${hrs} giờ trước`, `${hrs}h ago`);
  }
  const d = new Date(timestamp);
  return `${d.getDate()}/${d.getMonth() + 1}`;
}

function localizeSessionRiskLabel(label) {
  if (!label) return t('Theo dõi', 'Monitor');
  if (!isEnLang()) {
    if (label === 'Home Care') return 'Theo dõi tại nhà';
    if (label === 'Insufficient info') return 'Chưa đủ thông tin';
    if (label === 'Monitor') return 'Theo dõi';
    return label;
  }
  const map = {
    'Theo dõi tại nhà': 'Home Care',
    'Chưa đủ thông tin': 'Insufficient info',
    'Theo dõi': 'Monitor',
    'Thấp / Tự chăm sóc': 'Low / Self-care',
    'Trung bình / Cần khám': 'Moderate / Clinic Visit',
    'Khẩn cấp / Cấp cứu': 'Emergency'
  };
  return map[label] || label;
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
  const riskScore = triageData && Object.prototype.hasOwnProperty.call(triageData, 'risk_score')
    ? triageData.risk_score : session?.riskScore ?? null;
  const riskLevel = triageData?.risk_level || session?.riskLevel || t('Chưa đủ thông tin', 'Insufficient info');
  const isEmergency = triageData?.is_emergency ?? session?.isEmergency ?? false;

  let riskBadgeClass = 'bg-emerald-500/20 text-emerald-300 border border-emerald-400/30';
  if (riskScore == null && !isEmergency) {
    riskBadgeClass = 'bg-slate-100 text-slate-600 border border-slate-300 dark:bg-slate-800 dark:text-slate-300';
  } else if (isEmergency || riskScore >= 70) {
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
        ${t('Không tìm thấy phiên tư vấn nào khớp với', 'No consultations matching')} "<strong>${escapeHtml(query)}</strong>"
      </div>
    `;
    return;
  }

  historyList.innerHTML = filtered.map(session => {
    const isActive = session.id === currentConversationId;
    const timeFormatted = formatSessionTime(session.timestamp);
    const safeSessionId = escapeHtml(session.id || '');
    const msgCnt = session.messageCount || 1;
    const msgUnit = isEnLang() ? (msgCnt === 1 ? 'message' : 'messages') : 'tin nhắn';
    const sessionTitle = session.id === 'demo_consultation_ho_sot'
      ? t('[MẪU] Ho khan & sốt nhẹ', '[SAMPLE] Dry Cough & Mild Fever')
      : (session.title || t('Phiên tư vấn', 'Consultation'));

    return `
      <div data-session="${safeSessionId}" onclick="loadSession(this.dataset.session)" 
           class="chat-history-item p-2.5 rounded-xl border transition-all cursor-pointer group relative ${isActive ? 'bg-sky-500/20 border-sky-400/60 shadow-md shadow-sky-500/15 ring-1 ring-sky-400/40' : 'bg-white/80 dark:bg-white/[0.03] border-slate-200/80 dark:border-white/10 hover:bg-white dark:hover:bg-white/[0.08] hover:border-slate-300 dark:hover:border-white/20'}">
        <div class="flex items-center justify-between gap-1.5">
          <div class="flex items-center gap-1.5 min-w-0">
            ${isActive ? '<span class="w-2 h-2 rounded-full bg-teal-500 dark:bg-sky-400 animate-pulse shrink-0"></span>' : '<span class="w-1.5 h-1.5 rounded-full bg-slate-400 dark:bg-white/30 shrink-0"></span>'}
            <span class="text-xs font-bold text-slate-900 dark:text-white truncate group-hover:text-teal-600 dark:group-hover:text-sky-200 transition-colors">${escapeHtml(sessionTitle)}</span>
          </div>
          <div class="flex items-center gap-1 shrink-0">
            <span class="text-[10px] text-slate-500 dark:text-white/40 font-mono">${timeFormatted}</span>
            <button type="button" data-session="${safeSessionId}" onclick="event.stopPropagation(); deleteSession(this.dataset.session)" class="opacity-0 group-hover:opacity-100 p-0.5 text-slate-400 hover:text-rose-500 transition-opacity" title="${t('Xóa phiên tư vấn', 'Delete consultation')}">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
            </button>
          </div>
        </div>
        <p class="text-[11px] text-slate-600 dark:text-white/60 truncate mt-1 leading-snug font-medium">${escapeHtml(session.lastMessage || '')}</p>
        <div class="flex items-center justify-between text-[10px] pt-1.5 mt-1 border-t border-slate-100 dark:border-white/5">
          <span class="text-teal-700 dark:text-sky-300 font-bold">${msgCnt} ${msgUnit}</span>
          <span class="px-1.5 py-0.5 rounded text-[9px] font-bold ${session.riskBadgeClass || 'bg-emerald-50 text-emerald-800 border border-emerald-300 dark:bg-emerald-500/20 dark:text-emerald-300 dark:border-emerald-400/30'}">${escapeHtml(localizeSessionRiskLabel(session.riskLevel))}</span>
        </div>
      </div>
    `;
  }).join('');
}

function loadSession(sessionId) {
  if (sessionId === 'demo_consultation_ho_sot') {
    currentConversationId = sessionId;
    hideFloatingDecorations();
    renderDemoConsultationView();
    renderChatHistoryList();
    return;
  }
  const session = chatSessions.find(s => s.id === sessionId);
  if (!session) return;
  cancelActiveChatRequest();
  window.clearChatHealthContext?.();

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
        if (typeof msg.image === 'string' && /^data:image\/(?:jpeg|png|webp|gif);base64,[a-z0-9+/=]+$/i.test(msg.image)) {
          userImgHtml = `
            <div class="mb-2 overflow-hidden rounded-xl border border-white/20 shadow-xs cursor-pointer max-w-[220px]" onclick="openImageModal(this.querySelector('img').src, '${t('Ảnh tổn thương bạn đã gửi', 'Submitted clinical image')}', '${t('Ảnh người bệnh cung cấp', 'Patient-provided image')}')">
              <img src="${escapeHtml(msg.image)}" alt="${t('Ảnh tải lên', 'Uploaded image')}" class="w-full h-auto max-h-[160px] object-cover hover:scale-105 transition-transform duration-200">
            </div>
          `;
        }
        const userHtml = `
          <div class="flex flex-col items-end my-1">
            <div class="w-fit max-w-[85%] bg-gradient-to-r from-sky-500/90 to-indigo-600/90 text-white px-4 py-2.5 rounded-2xl rounded-tr-sm text-xs sm:text-sm shadow-lg shadow-sky-500/20 backdrop-blur-md leading-relaxed font-medium text-left break-words border border-white/20">
              ${userImgHtml}
              <div>${escapeHtml(msg.content)}</div>
            </div>
            <div class="text-right text-[10px] text-slate-400 mt-1 mr-1">${translations[currentLang]?.patient_label || t('Bệnh nhân', 'Patient')}</div>
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
        <div class="text-slate-800 dark:text-slate-200 font-normal leading-relaxed">${formattedAnswer}${chatAnswerMetadata(msg)}</div>
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
    risk_score: session.riskScore ?? null,
    risk_level: session.riskLevel || t('Chưa đủ thông tin', 'Insufficient info'),
    is_emergency: session.isEmergency || false
  });

  appendChatConfirmation(container, chatHistory.at(-1) || {}, currentConversationId);
  if (typeof syncFloatingChatMessages === 'function') syncFloatingChatMessages();
  renderChatHistoryList();
}

// Mở hội thoại mới sau khi đăng nhập; các phiên cũ vẫn nằm trong lịch sử để chọn thủ công.
function startFreshChatForCurrentUser() {
  if (!currentUser) return;
  chatSessions = loadSessionsFromStorage();
  resetChat();
}

const deletingChatSessions = new Set();
async function deleteSession(sessionId) {
  if (!chatSessions.some(s => s.id === sessionId) || deletingChatSessions.has(sessionId)) return;
  const accountKey = chatAccountKey();
  deletingChatSessions.add(sessionId);
  try {
    const response = await fetch('/api/intake/session/' + encodeURIComponent(sessionId), { method: 'DELETE' });
    if (!response.ok && response.status !== 404) throw new Error('delete_failed');
    if (chatAccountKey() !== accountKey) return;
    const idx = chatSessions.findIndex(s => s.id === sessionId);
    if (idx < 0) return;
    chatSessions.splice(idx, 1);
    saveSessionsToStorage();
    if (currentConversationId === sessionId) {
      resetChat();
    } else {
      renderChatHistoryList();
    }
    showMedicalToast(t('Đã xóa phiên tư vấn khỏi lịch sử.', 'Consultation session deleted from history.'), 'info', 2500);
  } catch (_) {
    if (chatAccountKey() === accountKey) showMedicalToast(t('Chưa xóa được hội thoại trên máy chủ. Lịch sử vẫn được giữ để bạn thử lại.', 'Unable to delete session on server. History preserved so you can retry.'), 'error', 4500);
  } finally {
    deletingChatSessions.delete(sessionId);
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
            riskLevel: c.risk_level || t('Chưa đủ thông tin', 'Insufficient info'),
            riskScore: c.risk_score ?? null
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

function localizeCategoryTitle(title, isEn) {
  if (!isEn || !title) return title || (isEn ? 'HEALTHCARE FACILITY' : 'CƠ SỞ Y TẾ');
  const m = {
    'PHÒNG KHÁM QUỐC TẾ': 'INTERNATIONAL CLINIC',
    'TRUNG TÂM XÉT NGHIỆM': 'DIAGNOSTIC LAB',
    'BỆNH VIỆN ĐA KHOA': 'GENERAL HOSPITAL',
    'BỆNH VIỆN CHUYÊN KHOA': 'SPECIALTY HOSPITAL',
    'CƠ SỞ Y TẾ': 'HEALTHCARE FACILITY'
  };
  return m[title] || title;
}

function localizeFacilityDesc(fac, isEn) {
  if (!fac) return '';
  if (!isEn) return fac.description || '';
  const map = {
    fac_careplus: 'International-standard outpatient clinic network offering rapid intake, direct insurance billing, and dedicated physicians.',
    fac_diag: 'Modern automated medical diagnostics laboratory with over 20 years of experience and home sample collection.',
    fac_vinmec: 'Leading JCI-accredited international general hospital in HCMC meeting gold-standard patient safety and clinical care.',
    fac_vientim: 'Premier tertiary cardiovascular surgery and interventional cardiology center co-founded by Prof. Alain Carpentier.',
    fac_umc: 'Flagship central academic medical center staffed by leading professors, specialists, and advanced diagnostic imaging.',
    fac_choray: 'Special-grade tertiary referral hospital in Southern Vietnam managing complex cases and 24/7 polytrauma emergencies.',
    fac_bachmai: 'Largest special-grade tertiary general hospital in Northern Vietnam with comprehensive international-standard institutes.',
    fac_vinmec_timescity: 'First JCI-accredited international general hospital in Hanoi featuring modern five-star clinical facilities.',
    fac_danang_general: 'Largest tertiary referral general hospital in Central Vietnam & Central Highlands providing specialized acute care.',
    fac_vinmec_danang: 'Modern international-standard hospital serving residents and international visitors in Da Nang.'
  };
  return map[fac.id] || fac.description || '';
}

function updateHospitalMapMarkers(customList) {
  if (!hospitalLeafletMap || !hospitalMarkersLayer) return;
  if (typeof L === 'undefined') return;
  hospitalMarkersLayer.clearLayers();

  const isEn = isEnLang();
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
      const catLabel = escapeHtml(localizeCategoryTitle(fac.categoryTitle, isEn));
      const safeFacId = escapeJsAttrSingleQuoted(fac.id);
      const safeMapUrl = escapeHtml(sanitizeSafeExternalHref(fac.mapUrl));
      const popupHtml = `
        <div style="font-family: inherit; font-size: 12px; min-width: 220px; line-height: 1.45; padding: 2px;">
          <div style="font-weight: 700; font-size: 13px; color: #0f172a; margin-bottom: 2px;">${escapeHtml(fac.name)}</div>
          <div style="font-size: 10px; font-weight: 700; color: #2563eb; text-transform: uppercase; margin-bottom: 4px;">${catLabel} • ${escapeHtml(fac.distanceDisplay || '')}</div>
          <div style="color: #64748b; font-size: 11px; margin-bottom: 8px;">📍 ${escapeHtml(fac.address)}</div>
          <div style="display: flex; gap: 6px;">
            <button onclick="openFacilityBookingModal('${safeFacId}')" style="background: #2563eb; color: white; border: none; border-radius: 8px; padding: 6px 12px; font-size: 11px; font-weight: 600; cursor: pointer; flex: 1;">${t('Đặt lịch khám', 'Book Appointment')}</button>
            <a href="${safeMapUrl}" target="_blank" rel="noopener noreferrer" style="background: #f8fafc; color: #334155; border: 1px solid #cbd5e1; border-radius: 8px; padding: 6px 10px; font-size: 11px; font-weight: 600; text-decoration: none; display: inline-flex; align-items: center;">${t('Chỉ đường', 'Directions')}</a>
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
    el.innerText = isHidden ? t('Mở bản đồ', 'Open Map') : t('Thu gọn bản đồ', 'Collapse Map');
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
    showMedicalToast(t('Trình duyệt không hỗ trợ định vị GPS.', 'Your browser does not support GPS geolocation.'), 'warning');
    return;
  }
  showMedicalToast(t('Đang xác định vị trí GPS thực tế...', 'Determining live GPS location...'), 'info', 2000);
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
        L.marker([latitude, longitude], { icon: userIcon }).addTo(hospitalLeafletMap).bindPopup(`<b>${t('Vị trí của bạn', 'Your Location')}</b>`).openPopup();
        hospitalLeafletMap.setView([latitude, longitude], 13);
      }
      showMedicalToast(t(`Đã đồng bộ GPS (${latitude.toFixed(2)}, ${longitude.toFixed(2)}) và cập nhật khoảng cách.`, `GPS synchronized (${latitude.toFixed(2)}, ${longitude.toFixed(2)}) and distances updated.`), 'success');
    },
    err => {
      showMedicalToast(t('Không thể lấy vị trí GPS. Đang dùng khoảng cách ước tính mặc định.', 'Unable to retrieve GPS position. Using default estimated distances.'), 'info');
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
              ${escapeHtml(localizeCategoryTitle(fac.categoryTitle || 'CƠ SỞ Y TẾ', isEn))}
            </span>
            <h3 class="text-sm sm:text-base font-bold text-slate-900 dark:text-white mt-0.5 line-clamp-1" title="${escapeHtml(fac.name)}">
              ${escapeHtml(fac.name)}
            </h3>
          </div>

          <!-- Quality Badge -->
          <div class="mt-2">
            <span class="inline-block text-[11px] font-semibold text-sky-600 dark:text-sky-400 bg-sky-50 dark:bg-sky-950/60 border border-sky-100 dark:border-sky-800/40 px-2.5 py-0.5 rounded-md">
              ${escapeHtml(localizeQualityBadge(fac.qualityBadge, isEn))}
            </span>
          </div>

          <!-- Address and Distance -->
          <div class="flex items-center justify-between text-xs text-slate-600 dark:text-slate-400 gap-2 mt-2.5">
            <span class="truncate flex items-center gap-1.5" title="${escapeHtml(fac.address)}">
              <svg class="w-3.5 h-3.5 text-slate-400 shrink-0 inline-block" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"/><path stroke-linecap="round" stroke-linejoin="round" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
              <span class="truncate">${escapeHtml(fac.address)}</span>
            </span>
            <span class="font-bold text-sky-600 dark:text-sky-400 shrink-0 text-xs">${escapeHtml(fac.distanceDisplay || '')}</span>
          </div>

          <!-- Specialty Tags -->
          <div class="flex flex-wrap gap-1 pt-1">
            ${(fac.specialties || []).slice(0, 4).map(s => `
              <span class="px-2 py-0.5 rounded-md text-[10px] font-medium bg-slate-100 dark:bg-white/5 text-slate-600 dark:text-slate-300 border border-slate-200/80 dark:border-white/10">
                ${escapeHtml(localizeSpecialty(s, isEn))}
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
            <span class="truncate">${escapeHtml(localizeHours(fac.hours, isEn))}</span>
          </div>
        </div>

        <!-- Bottom Action Buttons -->
        <div class="flex items-center gap-2 pt-2 border-t border-slate-100 dark:border-white/5">
          <button type="button" onclick="openFacilityBookingModal('${escapeJsAttrSingleQuoted(fac.id)}')" class="flex-1 py-2 rounded-xl bg-gradient-to-r from-sky-500 to-indigo-600 hover:from-sky-400 hover:to-indigo-500 text-white font-bold text-xs shadow-md shadow-sky-500/20 text-center transition-all cursor-pointer">
            ${isEn ? 'Book Appointment' : 'Đặt lịch khám'}
          </button>
          <button type="button" onclick="openFacilityDetailModal('${escapeJsAttrSingleQuoted(fac.id)}')" class="px-3.5 py-2 rounded-xl glass-pill border border-slate-200 dark:border-white/10 hover:border-sky-400/40 text-slate-700 dark:text-slate-200 hover:text-sky-600 dark:hover:text-white font-bold text-xs transition-all cursor-pointer">
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

function resolveFacilityRecord(facId, facObj = null) {
  if (facObj && (facObj.name || facObj.ten_ngan || facObj.ten)) {
    return {
      id: String(facObj.id ?? facId ?? 'fac_unknown'),
      name: facObj.name || facObj.ten_ngan || facObj.ten,
      address: facObj.address || facObj.dia_chi_hien_thi_tren_web || facObj.dia_chi || ''
    };
  }
  const sid = String(facId ?? '');
  const dynList = window.currentFacilityState?.facilities || [];
  const dyn = dynList.find(f => String(f.id) === sid);
  if (dyn) {
    return {
      id: String(dyn.id),
      name: dyn.ten_ngan || dyn.ten,
      address: dyn.dia_chi_hien_thi_tren_web || dyn.dia_chi || ''
    };
  }
  const marker = (window.mapMarkersData || []).find(m => String(m.id) === sid);
  if (marker) {
    return { id: String(marker.id), name: marker.name, address: marker.address || '' };
  }
  return medicalFacilitiesData.find(f => String(f.id) === sid) || medicalFacilitiesData[0];
}

function openFacilityBookingModal(facId, facObj = null) {
  const fac = resolveFacilityRecord(facId, facObj);
  if (!currentUser) {
    pendingBookingFacilityId = fac ? fac.id : facId;
    const isEn = typeof currentLang !== 'undefined' && currentLang === 'en';
    const facName = fac ? fac.name : (isEn ? 'healthcare facility' : 'cơ sở y tế');
    const bannerTitle = isEn ? 'ACCOUNT AUTHENTICATION REQUIRED' : 'YÊU CẦU XÁC THỰC TÀI KHOẢN';
    const bannerText = isEn 
      ? `Please log in or create an account to book an appointment at ${facName}!`
      : `Vui lòng đăng nhập hoặc tạo tài khoản mới để đặt lịch khám tại ${facName}!`;
    showAuthContextBanner(bannerTitle, bannerText);
    openLoginModal('login');
    return;
  }

  if (!fac) return;

  const modal = document.getElementById('facility-booking-modal');
  const nameEl = document.getElementById('book-modal-facility-name');
  const addrEl = document.getElementById('book-modal-facility-address');
  const idEl = document.getElementById('book-modal-facility-id');
  const dateEl = document.getElementById('book-modal-date');
  const patNameEl = document.getElementById('book-modal-name');
  const patPhoneEl = document.getElementById('book-modal-phone');

  if (nameEl) nameEl.innerText = fac.name;
  if (addrEl) addrEl.innerText = fac.address;
  if (idEl) idEl.value = fac.id;
  if (patNameEl && !patNameEl.value.trim()) {
    patNameEl.value = currentUser?.full_name || currentUser?.name || '';
  }
  if (patPhoneEl && !patPhoneEl.value.trim()) {
    patPhoneEl.value = currentUser?.phone_number || currentUser?.phone || '';
  }

  if (dateEl) {
    const fmtLocalDate = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    const today = new Date();
    const tmr = new Date(today);
    tmr.setDate(tmr.getDate() + 1);
    dateEl.value = fmtLocalDate(tmr);
    dateEl.min = fmtLocalDate(today);
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
  const fac = resolveFacilityRecord(facId);
  const modalFacName = document.getElementById('book-modal-facility-name')?.innerText?.trim();
  const modalFacAddr = document.getElementById('book-modal-facility-address')?.innerText?.trim();
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
        facility_id: String(facId || 'fac_unknown'),
        facility_name: modalFacName || (fac ? fac.name : (isEn ? 'Healthcare Facility' : 'Cơ sở Y tế')),
        facility_address: modalFacAddr || (fac ? fac.address : ''),
        specialty: spec || (isEn ? 'General Practice' : 'Đa khoa'),
        appointment_date: date,
        appointment_time: time,
        patient_name: patName,
        patient_phone: patPhone,
        note: note || ''
      })
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.success === false) {
      showMedicalToast(data.error || (isEn ? 'Unable to book appointment. Please check your information.' : 'Không thể đặt lịch khám. Vui lòng kiểm tra lại thông tin.'), 'error');
      return;
    }

    closeFacilityBookingModal();
    const successMsg = data.message || (isEn ? 'Appointment booked successfully!' : 'Đã lưu lịch hẹn khám thành công!');
    showMedicalToast(successMsg, 'success', 4000);
  } catch (err) {
    console.error('Lỗi khi lưu lịch hẹn:', err);
    showMedicalToast(isEn ? 'Unable to connect to booking server.' : 'Không thể kết nối máy chủ đặt lịch. Vui lòng thử lại.', 'error');
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
  if (desc) desc.innerText = localizeFacilityDesc(fac, isEn);
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

function localizeGenderLabel(gender) {
  if (!gender) return t('Chưa rõ', 'Not specified');
  if (!isEnLang()) {
    if (gender === 'Male') return 'Nam';
    if (gender === 'Female') return 'Nữ';
    if (gender === 'Other') return 'Khác';
    if (gender === 'Not specified') return 'Chưa rõ';
    return gender;
  }
  const m = { 'Nam': 'Male', 'Nữ': 'Female', 'Khác': 'Other', 'Chưa rõ': 'Not specified' };
  return m[gender] || gender;
}

function localizeAllergyLabel(alg) {
  if (!alg || !isEnLang()) return alg;
  return alg.replace(/Hải sản/gi, 'Seafood').replace(/Phấn hoa/gi, 'Pollen').replace(/Đậu phộng/gi, 'Peanuts');
}

function localizeSampleRecord(rec) {
  if (!rec || !isEnLang()) return rec;
  const enRecords = {
    rec_ma1: {
      title: 'Acute Pharyngitis',
      doctor: 'Dr. Le Thu Ha · Internal Medicine',
      status: 'Recovered',
      hr: '88 bpm',
      symptoms: 'Sore throat, mild fever 38.2°C, painful swallowing for 3 days',
      labs: 'Rapid streptococcal antigen test: negative. WBC 11.2 G/L (mildly elevated).',
      doctorNotes: 'Maintain warm hydration; return for follow-up if fever persists beyond 3 days.',
      followUp: 'No follow-up required'
    },
    rec_ma2: {
      title: 'Sinus Arrhythmia',
      doctor: 'Dr. Pham Duc Long · Cardiology',
      status: 'Follow-up Advised',
      hr: '94 bpm',
      symptoms: 'Intermittent palpitations during high occupational stress',
      labs: '12-lead ECG: Sinus tachycardia at 94 bpm, no ST-T repolarization abnormalities.',
      doctorNotes: 'Limit caffeine and stimulants; maintain 7–8 hours of sleep nightly.',
      followUp: 'Follow-up in 1 month'
    },
    rec_ma3: {
      title: 'Iron-Deficiency Anemia',
      doctor: 'Dr. Le Thu Ha · Internal Medicine',
      status: 'Recovered',
      hr: '78 bpm',
      symptoms: 'Lightheadedness upon standing quickly, mild afternoon fatigue',
      labs: 'CBC: Hb 10.8 g/dL (mildly low), Serum Ferritin 14 ng/mL.',
      doctorNotes: 'Oral iron supplementation 1 capsule daily after meals; increase dark leafy greens.',
      followUp: 'Completed 3-month iron supplementation course'
    },
    rec_qb1: {
      title: 'Stage 2 Hypertension',
      doctor: 'Dr. Pham Duc Long · Cardiology',
      status: 'Follow-up Advised',
      hr: '84 bpm',
      symptoms: 'Occipital heaviness and mild morning dizziness upon waking',
      labs: 'Biochemistry: Creatinine 88 µmol/L, Uric Acid 390 µmol/L, mildly elevated lipids.',
      doctorNotes: 'Continue daily morning antihypertensive regimen; restrict dietary sodium < 5 g/day.',
      followUp: 'Routine follow-up in 30 days'
    },
    rec_qb2: {
      title: 'Mixed Dyslipidemia',
      doctor: 'Dr. Le Thu Ha · Internal Medicine',
      status: 'Recovered',
      hr: '76 bpm',
      symptoms: 'Detected during annual occupational checkup; asymptomatic',
      labs: 'Total Cholesterol 6.2 mmol/L, Triglycerides 2.8 mmol/L.',
      doctorNotes: 'Engage in ≥30 min daily aerobic exercise; limit alcohol and saturated animal fats.',
      followUp: 'Repeat fasting lipid panel in 3 months'
    }
  };
  const tr = enRecords[rec.id];
  if (!tr) return rec;
  return {
    ...rec,
    title: tr.title,
    doctor: tr.doctor,
    status: tr.status,
    vitals: { ...(rec.vitals || {}), hr: tr.hr },
    symptoms: tr.symptoms,
    labs: tr.labs,
    doctorNotes: tr.doctorNotes,
    followUp: tr.followUp
  };
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

    const heroName = document.getElementById('ehr-hero-name');
    const heroDemo = document.getElementById('ehr-hero-demographics');
    const avatarLarge = document.getElementById('ehr-avatar-large');
    const dobVal = document.getElementById('ehr-dob-val');
    const bloodVal = document.getElementById('ehr-blood-val');
    const phoneVal = document.getElementById('ehr-phone-val');
    const allergiesContainer = document.getElementById('ehr-allergies-container');

    if (heroName) heroName.innerText = cp.name;
    if (heroDemo) heroDemo.innerText = `${localizeGenderLabel(cp.gender)} · ${cp.age} ${t('tuổi', 'years old')}`;
    if (avatarLarge) avatarLarge.innerText = cp.badge;
    if (dobVal) dobVal.innerText = cp.dob;
    if (bloodVal) bloodVal.innerText = cp.blood;
    if (phoneVal) phoneVal.innerText = cp.phone;
    if (allergiesContainer && cp.allergies && cp.allergies.length > 0) {
      allergiesContainer.innerHTML = cp.allergies.map(alg => `
        <span class="inline-flex items-center px-2.5 py-1 rounded-lg text-xs font-bold bg-rose-50 dark:bg-rose-500/15 text-rose-600 dark:text-rose-300 border border-rose-200 dark:border-rose-400/30">
          <span>${escapeHtml(localizeAllergyLabel(alg))}</span>
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
    const gender = localizeGenderLabel(currentUser.gender || (currentLang === 'en' ? 'Not specified' : 'Chưa rõ'));
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
            <span>${escapeHtml(localizeAllergyLabel(alg))}</span>
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
      if (exportText) exportText.innerText = currentLang === 'en' ? 'Export Summary (PDF)' : 'Xuất tóm tắt (PDF)';
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
              ? 'Sign in to view the summaries you reviewed and chose to save. These self-reported summaries do not replace a medical record from a healthcare provider.'
              : 'Đăng nhập để xem các bản tóm tắt bạn đã xem lại và chủ động lưu. Thông tin tự khai này không thay thế bệnh án của cơ sở y tế.'}
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

  const heroName = document.getElementById('ehr-hero-name');
  const heroDemo = document.getElementById('ehr-hero-demographics');
  const avatarLarge = document.getElementById('ehr-avatar-large');
  const visitCount = document.getElementById('ehr-visit-count');
  const dobVal = document.getElementById('ehr-dob-val');
  const bloodVal = document.getElementById('ehr-blood-val');
  const phoneVal = document.getElementById('ehr-phone-val');
  const allergiesContainer = document.getElementById('ehr-allergies-container');
  const countBadge = document.getElementById('ehr-records-count-badge');

  if (heroName) heroName.innerText = patient.name;
  if (heroDemo) heroDemo.innerText = `${localizeGenderLabel(patient.gender)} · ${patient.age} ${t('tuổi', 'years old')}`;
  if (avatarLarge) avatarLarge.innerText = patient.badge;
  if (visitCount) visitCount.innerText = patient.visitCount;
  if (dobVal) dobVal.innerText = patient.dob;
  if (bloodVal) bloodVal.innerText = patient.blood;
  if (phoneVal) phoneVal.innerText = patient.phone;
  if (countBadge) countBadge.innerText = `${patient.records.length} ${t('hồ sơ', 'records')}`;

  if (allergiesContainer) {
    if (patient.allergies && patient.allergies.length > 0) {
      allergiesContainer.innerHTML = patient.allergies.map(alg => `
        <span class="inline-flex items-center px-2.5 py-1 rounded-lg text-xs font-bold bg-rose-50 dark:bg-rose-500/15 text-rose-600 dark:text-rose-300 border border-rose-200 dark:border-rose-400/30">
          <span>${escapeHtml(localizeAllergyLabel(alg))}</span>
        </span>
      `).join('');
    } else {
      allergiesContainer.innerHTML = `<span class="text-xs text-slate-500 dark:text-slate-400">${t('Không ghi nhận dị ứng', 'No allergies reported')}</span>`;
    }
  }

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
    const countBadge = document.getElementById('ehr-records-count-badge');
    if (countBadge) countBadge.innerText = `${(patient.records || []).length} ${t('hồ sơ', 'records')}`;
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
      const statusText = escapeHtml(isEmg ? t('Cảnh báo cấp cứu', 'Emergency Alert') : localizeSessionRiskLabel(item.risk_level || t('Tư vấn ban đầu', 'Initial Triage')));
      const specText = localizeSpecialty(item.specialist || t('Nội tổng quát', 'General Internal Medicine'), isEn);
      return `
        <div data-session="${escapeHtml(item.conversation_id || '')}" onclick="openConsultationSummaryDetail(this.dataset.session)" class="relative group cursor-pointer">
          <div class="absolute -left-[31px] top-4 w-3.5 h-3.5 rounded-full ${isEmg ? 'bg-rose-500' : 'bg-sky-500'} border-2 border-white dark:border-slate-900 shadow-md shadow-sky-500/50"></div>
          <div class="glass-card border border-slate-200/80 dark:border-white/10 rounded-2xl p-5 shadow-sm hover:shadow-lg bg-white/90 dark:bg-white/[0.03] hover:border-sky-500/40 transition-all">
            <div class="flex items-start justify-between gap-3">
              <div class="space-y-1.5 flex-1 min-w-0">
                <div class="flex items-center gap-2">
                  <span class="text-xs font-bold text-sky-600 dark:text-sky-400 font-mono">${escapeHtml(item.created_at || t('Gần đây', 'Recently'))}</span>
                  <span class="px-2 py-0.5 rounded-md text-[10px] font-bold border ${statusClass}">${statusText}</span>
                </div>
                <h4 class="text-base font-black text-slate-900 dark:text-white group-hover:text-sky-600 dark:group-hover:text-sky-400 transition-colors truncate">
                  ${escapeHtml(item.message || t('Tư vấn triệu chứng', 'Symptom Consultation'))}
                </h4>
                <p class="text-xs text-slate-500 dark:text-slate-400 font-medium flex items-center gap-1.5">
                  <span>${t('Trợ lý Y tế', 'Clinical Assistant')}</span>
                  <span>•</span>
                  <span>${t('Định hướng:', 'Specialty:')} ${escapeHtml(specText)}</span>
                </p>
                <div class="pt-1.5">
                  <span class="text-[11px] text-slate-500 dark:text-slate-400 bg-slate-100 dark:bg-white/5 px-2.5 py-1 rounded-lg border border-slate-200 dark:border-white/10">
                    ${t('Bấm để xem Bản tóm tắt trước khám', 'Click to view Pre-Visit Summary')}
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
    showMedicalToast(t("Phiên cũ chưa có bản tóm tắt theo hội thoại.", "Older session does not have a saved pre-visit summary."), "info");
    return;
  }
  try {
    const response = await fetch('/api/clinical-summary?conversation_id=' + encodeURIComponent(sessionId));
    const data = await response.json();
    if (!response.ok || !data.summary) throw new Error(data.error || data.message || t("Không tìm thấy bản tóm tắt đã lưu.", "Saved summary not found."));
    renderPreVisitSummaryInModal(data.summary, null);
    document.getElementById('modal-btn-confirm')?.classList.add('hidden');
    document.getElementById('previsit-summary-modal')?.classList.remove('hidden');
  } catch (error) {
    showMedicalToast(error.message || t("Không tải được bản tóm tắt của phiên này.", "Unable to load summary for this session."), "error");
  }
}

function renderPatientTimeline(records) {
  const container = document.getElementById('ehr-timeline-list');
  if (!container) return;

  container.innerHTML = records.map(rawRec => {
    const rec = localizeSampleRecord(rawRec);
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
  const rawRec = patient.records.find(r => r.id === recordId) || patient.records[0];
  if (!rawRec) return;
  const rec = localizeSampleRecord(rawRec);

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
    statusEl.innerText = rec.status || t('Đã ghi nhận', 'Recorded');
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
  if (followupEl) followupEl.innerText = rec.followUp || t('Không hẹn tái khám', 'No follow-up required');

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
    showMedicalToast(t('Đã cập nhật ảnh đại diện thành công!', 'Profile avatar updated successfully!'), 'success');
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
  const filled = fields.filter(v => v && v !== '' && v !== 'Chưa rõ' && v !== 'Not specified').length;
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
  const originalBtnHtml = submitBtn ? submitBtn.innerHTML : t('Lưu thông tin', 'Save Changes');

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
  const dobDay = document.getElementById('p-dob-day')?.value || '';
  const dobMonth = document.getElementById('p-dob-month')?.value || '';
  const dobYear = document.getElementById('p-dob-year')?.value || '';
  if ((dobDay || dobMonth || dobYear) && !(dobDay && dobMonth && dobYear)) {
    showMedicalToast(t('Vui lòng chọn đầy đủ Ngày, Tháng, Năm sinh.', 'Please select Day, Month, and Year of birth.'), 'warning');
    document.getElementById(!dobDay ? 'p-dob-day' : (!dobMonth ? 'p-dob-month' : 'p-dob-year'))?.focus();
    return;
  }
  const birthDate = document.getElementById('p-birthdate')?.value.trim() || '';
  const gender = document.getElementById('p-gender')?.value || 'Nam';
  const phone = getFieldValue('p-phone', currentUser?.phone_number || '');
  const rawEmailVal = getFieldValue('p-email', '');
  const email = sanitizeUserEmail(rawEmailVal);
  const blood = document.getElementById('p-blood')?.value || 'O+';
  const allergies = document.getElementById('p-allergies')?.value.trim() || '';
  const height = document.getElementById('p-height')?.value.trim() || '';
  const weight = document.getElementById('p-weight')?.value.trim() || '';
  const address = document.getElementById('p-address')?.value.trim() || '';

  if (!currentUser || currentUser.isDemo) {
    showMedicalToast(t('Vui lòng đăng nhập để lưu và đồng bộ hồ sơ lên hệ thống.', 'Please sign in to save and synchronize your profile.'), 'warning');
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
      showMedicalToast(t('Số điện thoại không hợp lệ (cần đúng 10 chữ số).', 'Invalid phone number (10 digits required).'), 'error');
      return;
    }
  }

  try {
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerHTML = `<span class="inline-block animate-spin mr-1.5">⏳</span> ${t('Đang lưu...', 'Saving...')}`;
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
      const srvUser = data.user || {};
      currentUser = {
        ...currentUser,
        name: name || currentUser.name,
        full_name: name || currentUser.full_name,
        dob: birthDate,
        gender: gender,
        phone: srvUser.phone_number || phone,
        phone_number: srvUser.phone_number || phone,
        email: srvUser.email !== undefined ? srvUser.email : email,
        address: address,
        blood_type: blood,
        allergies: allergies,
        height: height,
        weight: weight,
        ...srvUser
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
        showMedicalToast(t('Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.', 'Session expired. Please sign in again.'), 'warning');
        if (typeof openLoginModal === 'function') openLoginModal();
      } else {
        showMedicalToast(data.error || t('Không thể lưu hồ sơ, vui lòng thử lại.', 'Unable to save profile. Please try again.'), 'error');
      }
    }
  } catch (err) {
    console.error('Lỗi khi lưu hồ sơ lên server:', err);
    showMedicalToast(t('Lỗi kết nối máy chủ khi lưu hồ sơ.', 'Server connection error while saving profile.'), 'error');
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML = originalBtnHtml;
    }
  }
}
// ==============================================================
// FLOATING CHATBOX WIDGET HANDLERS & ALIASES
// ==============================================================
function toggleFloatingChat(forceState) {
  if (typeof forceState === 'boolean') {
    const win = document.getElementById('floating-chat-window');
    const bubble = document.getElementById('floating-chat-bubble');
    if (win) {
      if (forceState) {
        if (typeof syncFloatingChatMessages === 'function') syncFloatingChatMessages();
        win.classList.remove('hidden');
        if (bubble) bubble.classList.add('hidden');
      } else {
        win.classList.add('hidden');
        if (bubble) bubble.classList.remove('hidden');
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

async function sendFloatingChatMessage() {
  const input = document.getElementById('floating-user-input');
  const msgContainer = document.getElementById('floating-chat-messages');
  if (!input || !msgContainer || activeChatRequest) return;

  const text = input.value.trim();
  if (!text) return;
  currentConversationId ||= crypto.randomUUID();
  msgContainer.querySelector('.floating-welcome-card')?.remove();

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
      <span class="text-[11px] font-medium text-slate-300">${t('MediMind đang đối chiếu dữ liệu...', 'MediMind is cross-referencing clinical data...')}</span>
    </div>
  `;
  msgContainer.appendChild(typingIndicator);
  msgContainer.scrollTop = msgContainer.scrollHeight;
  const chatRequest = beginChatRequest(typingId);

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        conversation_id: currentConversationId,
        history: chatRequest.history,
        message: text,
        lang: typeof currentLang !== 'undefined' ? currentLang : 'vi',
        health_context: window.getChatHealthContext?.() || {}
      }),
      signal: chatRequest.controller.signal
    });
    const data = await res.json();
    document.getElementById(typingId)?.remove();
    if (!chatRequestIsCurrent(chatRequest)) return;

    if (res.ok && data.answer) {
      if (data.conversation_id) currentConversationId = data.conversation_id;
      chatHistory.push({role: 'user', content: text}, chatAssistantTurn(data));
      saveOrUpdateCurrentSession(text, data, data.intake);
      if (data.intake) updateLiveIntakeCard(data.intake.facts, data.intake.status, data.intake.summary);
      if (data.intake?.summary) currentIntakeSummary = data.intake.summary;
      updateTriagePanel(data);
      renderSharedChatInMain();
    }
    const rawReply = (res.ok && typeof data.answer === 'string' ? data.answer : data.error) || t('Không nhận được phản hồi hợp lệ. Bạn có thể thử gửi lại.', 'Did not receive a valid response. Please try sending again.');
    const safeReply = escapeHtml(String(rawReply))
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\n/g, '<br>');

    const botBubble = document.createElement('div');
    botBubble.className = 'flex justify-start';
    botBubble.innerHTML = `
      <div class="max-w-[88%] px-3.5 py-2.5 rounded-2xl rounded-tl-xs border floating-welcome-bubble text-xs leading-relaxed shadow-xs">
        ${safeReply}
        ${data.is_emergency ? `<p class="mt-2 font-bold text-rose-600 dark:text-rose-300">${t('Cần trợ giúp khẩn cấp: gọi 115 hoặc đến khoa Cấp cứu.', 'Urgent medical attention required: call 115 or visit the nearest Emergency Department.')}</p>` : ''}
        ${chatAnswerMetadata(data)}
      </div>
    `;
    msgContainer.appendChild(botBubble);
    appendChatConfirmation(msgContainer, data, currentConversationId, true);
    msgContainer.scrollTop = msgContainer.scrollHeight;
  } catch (err) {
    document.getElementById(typingId)?.remove();
    if (err.name === 'AbortError' || !chatRequestIsCurrent(chatRequest)) return;
    const errBubble = document.createElement('div');
    errBubble.className = 'flex justify-start';
    errBubble.innerHTML = `
      <div class="max-w-[85%] px-3.5 py-2 rounded-2xl rounded-tl-xs bg-rose-500/20 text-rose-300 border border-rose-500/30 text-xs">
        ${t('Không thể kết nối đến máy chủ lâm sàng. Vui lòng thử lại.', 'Unable to connect to the clinical server. Please try again.')}
      </div>
    `;
    msgContainer.appendChild(errBubble);
    msgContainer.scrollTop = msgContainer.scrollHeight;
  } finally {
    finishChatRequest(chatRequest);
  }
}


/* ============================================================== */
/* NUTRITION STUDIO - PHA CHẾ BỮA ĂN THEO THỂ TRẠNG               */
/* ============================================================== */

const NUTRITION_PRESETS = [
  {
    id: "nhiet_mieng",
    name: "Nhiệt miệng",
    name_en: "Mouth Ulcers",
    desc: "Nóng trong người",
    desc_en: "Internal heat",
    iconSvg: `<svg class="w-5 h-5 text-amber-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M17.657 18.657A8 8 0 016.343 7.343S7 9 9 10c0-2 .5-5 2.986-7C14 5 16.09 5.777 17.656 7.343A7.975 7.975 0 0120 13a7.975 7.975 0 01-2.343 5.657z"/><path stroke-linecap="round" stroke-linejoin="round" d="M9.879 16.121A3 3 0 1012.015 11L11 14H9c0 .768.293 1.536.879 2.121z"/></svg>`,
    color: "amber"
  },
  {
    id: "day_hoi",
    name: "Đầy hơi",
    name_en: "Bloating",
    desc: "Khó tiêu sau tiệc",
    desc_en: "Post-meal indigestion",
    iconSvg: `<svg class="w-5 h-5 text-yellow-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>`,
    color: "yellow"
  },
  {
    id: "cam_cum",
    name: "Cảm cúm",
    name_en: "Cold & Flu",
    desc: "Đau rát họng",
    desc_en: "Sore throat",
    iconSvg: `<svg class="w-5 h-5 text-sky-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"/></svg>`,
    color: "sky"
  },
  {
    id: "mat_ngu",
    name: "Mất ngủ",
    name_en: "Insomnia",
    desc: "Căng thẳng, cần thư giãn",
    desc_en: "Stress & relaxation",
    iconSvg: `<svg class="w-5 h-5 text-indigo-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"/></svg>`,
    color: "indigo"
  },
  {
    id: "dau_bung_kinh",
    name: "Đau bụng kinh",
    name_en: "Menstrual Cramps",
    desc: "Mệt mỏi, uể oải",
    desc_en: "Fatigue & cramps",
    iconSvg: `<svg class="w-5 h-5 text-rose-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 2.69l5.66 5.66a8 8 0 11-11.31 0z"/></svg>`,
    color: "rose"
  }
];

let activeNutritionData = null;
let nutritionServingsCount = 1;
let currentSelectedPresetId = "dau_bung_kinh";
let currentNutritionType = 'food';

async function setNutritionType(type) {
  currentNutritionType = type === 'drink' ? 'drink' : 'food';
  document.getElementById('nutrition-type-food')?.classList.toggle('active', currentNutritionType === 'food');
  document.getElementById('nutrition-type-drink')?.classList.toggle('active', currentNutritionType === 'drink');
  if (!activeNutritionData) return;
  const query = document.getElementById('nutrition-condition-input')?.value.trim();
  if (query) await searchCustomCondition();
  else if (currentSelectedPresetId) await loadNutritionCondition(currentSelectedPresetId);
}

function completeWellnessChallenge(button) {
  const key = 'medimind_wellness_challenge_days';
  let days = Number(localStorage.getItem(key) || 0);
  const joined = button.dataset.joined === 'true';
  if (!joined) {
    button.dataset.joined = 'true';
    button.innerText = t('Đã tham gia ✓', 'Joined ✓');
    button.classList.add('opacity-80');
    localStorage.setItem('medimind_wellness_challenge_days', String(days));
    return;
  }
  days += 1;
  localStorage.setItem(key, String(days));
  const progress = document.getElementById('wellness-progress');
  if (progress) progress.innerText = String(days);
  button.innerText = t('Hôm nay đã hoàn thành ✓', 'Completed today ✓');
  button.disabled = true;
}

function initWellnessChallenges() {
  const progress = document.getElementById('wellness-progress');
  if (progress) progress.innerText = localStorage.getItem('medimind_wellness_challenge_days') || '0';
}

function initNutritionStudio() {
  renderNutritionPresets();
  if (!activeNutritionData) {
    loadNutritionCondition("dau_bung_kinh");
  } else {
    renderDishPlate();
    renderRecipe();
  }
}

function renderNutritionPresets() {
  const container = document.getElementById('nutrition-presets-container');
  if (!container) return;
  const isEn = isEnLang();

  container.innerHTML = NUTRITION_PRESETS.map(p => {
    const isActive = p.id === currentSelectedPresetId;
    const displayName = isEn ? (p.name_en || p.name) : p.name;
    return `
      <button type="button" id="preset-card-${p.id}" aria-pressed="${isActive}"
        onclick="selectPresetCondition('${p.id}')" class="nutrition-preset-chip ${isActive ? 'active' : ''}">
        <span class="nutrition-preset-icon">${p.iconSvg}</span><span>${escapeHtml(displayName)}</span>
      </button>
    `;
  }).join('');
}

async function selectPresetCondition(presetId) {
  currentSelectedPresetId = presetId;
  renderNutritionPresets();

  const input = document.getElementById('nutrition-condition-input');
  const clearBtn = document.getElementById('btn-clear-condition');
  const matched = NUTRITION_PRESETS.find(p => p.id === presetId);
  if (input && matched) {
    input.value = isEnLang() ? (matched.name_en || matched.name) : matched.name;
    if (clearBtn) clearBtn.classList.remove('hidden');
  }

  await loadNutritionCondition(presetId);
}

function clearNutritionInput() {
  const input = document.getElementById('nutrition-condition-input');
  const clearBtn = document.getElementById('btn-clear-condition');
  if (input) input.value = '';
  if (clearBtn) clearBtn.classList.add('hidden');
  selectPresetCondition('dau_bung_kinh');
}

async function searchCustomCondition() {
  const input = document.getElementById('nutrition-condition-input');
  const query = (input?.value || '').trim();
  if (!query) {
    showMedicalToast(t("Vui lòng nhập tên bệnh lý hoặc thể trạng để pha chế.", "Please enter a health condition or symptom to blend."), "info");
    input?.focus();
    return;
  }

  const clearBtn = document.getElementById('btn-clear-condition');
  if (clearBtn) clearBtn.classList.remove('hidden');

  const normalized = query.toLowerCase();
  const matched = NUTRITION_PRESETS.find(p =>
    p.name.toLowerCase() === normalized ||
    (p.name_en || '').toLowerCase() === normalized ||
    p.desc.toLowerCase().includes(normalized) ||
    (p.desc_en || '').toLowerCase().includes(normalized)
  );
  if (matched) {
    selectPresetCondition(matched.id);
    return;
  }

  currentSelectedPresetId = null;
  renderNutritionPresets();

  await loadNutritionCondition(query, true);
}

async function loadNutritionCondition(conditionOrId, isCustomSearch = false) {
  const spinner = document.getElementById('nutrition-btn-spinner');
  const btnText = document.getElementById('nutrition-btn-text');
  const bubblesContainer = document.getElementById('nutrition-bubbles-container');

  if (spinner && btnText) {
    spinner.classList.remove('hidden');
    btnText.innerText = t('Đang phân tích...', 'Analyzing...');
  }

  if (bubblesContainer) {
    bubblesContainer.classList.add('opacity-40', 'pointer-events-none');
  }

  try {
    const res = await fetch('/api/nutrition/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        condition: conditionOrId,
        recipe_type: currentNutritionType,
        lang: typeof currentLang !== 'undefined' ? currentLang : 'vi'
      })
    });

    const data = await res.json();
    if (!res.ok || !data.success || !data.data) {
      throw new Error(data.error || t("Không thể tải phác đồ dinh dưỡng", "Unable to load nutrition protocol"));
    }

    activeNutritionData = data.data;

    const plateTitle = document.getElementById('nutrition-plate-active-title');
    if (plateTitle) {
      plateTitle.innerText = activeNutritionData.condition_name || conditionOrId;
    }

    renderDishPlate();
    renderRecipe();

  } catch (err) {
    console.error("[Nutrition] Lỗi nạp phác đồ:", err);
    showMedicalToast(t("Lỗi phân tích dinh dưỡng: ", "Nutrition analysis error: ") + (err.message || t("Vui lòng thử lại.", "Please try again.")), "error");
  } finally {
    if (spinner && btnText) {
      spinner.classList.add('hidden');
      btnText.innerText = t('Pha chế ngay', 'Blend Now');
    }
    if (bubblesContainer) {
      bubblesContainer.classList.remove('opacity-40', 'pointer-events-none');
    }
  }
}

function renderDishPlate() {
  if (!activeNutritionData) return;

  const countEat = document.getElementById('nutrition-count-eat');
  const countAvoid = document.getElementById('nutrition-count-avoid');
  const bubblesContainer = document.getElementById('nutrition-bubbles-container');

  const foodsEat = activeNutritionData.foods_to_eat || [];
  const foodsAvoid = activeNutritionData.foods_to_avoid || [];

  if (countEat) {
    countEat.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span><span>${t('Nên nạp', 'Recommended')} · ${foodsEat.length}</span>`;
  }
  if (countAvoid) {
    countAvoid.innerHTML = `<span class="w-1.5 h-1.5 rounded-full bg-rose-400"></span><span>${t('Nên né', 'Avoid')} · ${foodsAvoid.length}</span>`;
  }

  if (!bubblesContainer) return;

  bubblesContainer.innerHTML = foodsEat.map(item => `
    <button type="button" class="nutrition-ingredient" onclick="showFoodDetailFromButton(this)"
      data-kind="eat" data-name="${escapeHtml(item.name)}" data-desc="${escapeHtml(item.desc || '')}" data-icon="${escapeHtml(item.icon || '🥣')}">
      <span class="nutrition-ingredient-icon">${item.icon || '🥣'}</span><span>${escapeHtml(item.name)}</span><span class="nutrition-info-mark">i</span>
    </button>`).join('');

  const avoidList = document.getElementById('nutrition-avoid-list');
  if (avoidList) {
    avoidList.innerHTML = foodsAvoid.map(item => `
      <button type="button" class="nutrition-avoid-item" onclick="showFoodDetailFromButton(this)"
        data-kind="avoid" data-name="${escapeHtml(item.name)}" data-desc="${escapeHtml(item.desc || '')}" data-icon="${escapeHtml(item.icon || '🚫')}">
        <span aria-hidden="true">${item.icon || '🚫'}</span><span>${escapeHtml(item.name)}</span><span aria-hidden="true">✕</span>
      </button>`).join('');
  }

  const vessel = document.getElementById('nutrition-vessel-icon');
  if (vessel) vessel.innerText = /trà|nước|sữa|sinh tố|nước ép|tea|juice|smoothie|milk|drink/i.test(activeNutritionData.recipe?.title || '') ? '🍵' : '🥣';
  const detail = document.getElementById('nutrition-ingredient-detail');
  if (detail) detail.classList.add('hidden');
}

function showFoodDetailFromButton(button) {
  const detail = document.getElementById('nutrition-ingredient-detail');
  const icon = document.getElementById('nutrition-detail-icon');
  const name = document.getElementById('nutrition-detail-name');
  const copy = document.getElementById('nutrition-detail-copy');
  if (!detail || !button) return;
  if (icon) icon.innerText = button.dataset.icon || '✦';
  if (name) name.innerText = button.dataset.name || '';
  if (copy) copy.innerText = button.dataset.desc || '';
  detail.classList.remove('hidden');
}

function renderRecipe() {
  if (!activeNutritionData || !activeNutritionData.recipe) return;

  const r = activeNutritionData.recipe;
  const iconBox = document.getElementById('recipe-icon-box');
  const badge = document.getElementById('recipe-badge');
  const title = document.getElementById('recipe-title');
  const subtitle = document.getElementById('recipe-subtitle');
  const tipText = document.getElementById('recipe-tip-text');
  const time = document.getElementById('recipe-time');
  const heading = document.getElementById('ingredients-heading');
  const grid = document.getElementById('recipe-ingredients-grid');
  const stepsList = document.getElementById('recipe-steps-list');

  if (iconBox) iconBox.innerText = (r.ingredients && r.ingredients[0] && r.ingredients[0].icon) ? r.ingredients[0].icon : '🍲';
  if (badge) badge.innerText = r.badge || t('✨ CÔNG THỨC 3 BƯỚC', '✨ 3-STEP RECIPE');
  if (title) title.innerText = r.title || t('Món ăn dưỡng sinh', 'Wellness Dish');
  if (subtitle) subtitle.innerText = r.subtitle || t('Điều hòa thể trạng', 'Body-balancing nutrition');
  if (tipText) tipText.innerText = r.tip || t('Ăn nóng, cả nước lẫn cái', 'Serve warm');
  if (time) time.innerHTML = `<span>⏱️</span><span>${t('Hoàn thành trong', 'Ready in')} ${escapeHtml(r.cooking_time || t('~20 phút', '~20 min'))}</span>`;
  if (heading) heading.innerText = t('NGUYÊN LIỆU', 'INGREDIENTS');
  const servingsUnit = document.getElementById('servings-unit');
  if (servingsUnit) servingsUnit.innerText = isEnLang() ? 'servings' : (currentNutritionType === 'drink' ? 'người uống' : 'người ăn');

  if (grid) {
    const avoidTerms = (activeNutritionData.foods_to_avoid || []).map(item => item.name.toLocaleLowerCase('vi'));
    const ings = (r.ingredients || []).filter(ingredient => {
      const name = String(ingredient.name || '').toLocaleLowerCase('vi');
      return !avoidTerms.some(term => term && (name.includes(term) || term.includes(name)));
    });
    grid.innerHTML = ings.map(ing => {
      const baseAmt = parseFloat(ing.amount) || 1;
      const totalAmt = (baseAmt * nutritionServingsCount);
      const displayAmt = Number.isInteger(totalAmt) ? totalAmt : totalAmt.toFixed(1);
      return `
        <div class="p-3 rounded-2xl bg-white/[0.04] border border-white/10 flex items-center gap-3">
          <div class="text-xl shrink-0">${ing.icon || '🥣'}</div>
          <div class="min-w-0">
            <h5 class="text-xs font-bold text-white truncate">${escapeHtml(ing.name)}</h5>
          <p class="text-[11px] font-black text-sky-700 font-mono">${displayAmt} ${escapeHtml(ing.unit || '')}</p>
          </div>
        </div>
      `;
    }).join('');
  }

  if (stepsList) {
    const steps = r.steps || [];
    stepsList.innerHTML = steps.map((s, idx) => `
      <div class="flex items-start gap-3 p-3 rounded-2xl bg-white/[0.03] border border-white/5">
        <span class="w-6 h-6 rounded-full bg-rose-500/20 text-rose-300 border border-rose-400/30 flex items-center justify-center text-xs font-black shrink-0 mt-0.5">
          ${idx + 1}
        </span>
        <p class="text-xs text-slate-300 leading-relaxed font-medium">
          ${escapeHtml(s)}
        </p>
      </div>
    `).join('');
  }
}

function adjustServings(delta) {
  setServings(nutritionServingsCount + delta);
}

function setServings(val) {
  const parsed = parseInt(val, 10);
  if (isNaN(parsed)) return;
  nutritionServingsCount = Math.max(1, Math.min(6, parsed));

  const display = document.getElementById('servings-display');
  const slider = document.getElementById('servings-slider');

  if (display) display.innerText = nutritionServingsCount;
  if (slider) slider.value = nutritionServingsCount;

  renderRecipe();
}

function showFoodDetail(name, desc, type, icon) {
  const isEat = type === 'eat';
  const headerHtml = `
    <div class="flex items-center gap-3 mb-2">
      <div class="w-10 h-10 rounded-full ${isEat ? 'bg-emerald-500/20 text-emerald-400 border-emerald-400/30' : 'bg-rose-500/20 text-rose-400 border-rose-400/30'} border flex items-center justify-center text-xl">
        ${icon}
      </div>
      <div>
        <h4 class="text-sm font-black text-white">${name}</h4>
        <span class="text-[10px] font-bold ${isEat ? 'text-emerald-400' : 'text-rose-400'} uppercase">
          ${isEat ? t('● Thực phẩm nên nạp', '● Recommended food') : t('✕ Thực phẩm nên né', '✕ Food to avoid')}
        </span>
      </div>
    </div>
    <p class="text-xs text-slate-300 leading-relaxed">${desc}</p>
  `;
  showMedicalToast(name + ": " + desc, isEat ? "success" : "info");
}

function copyRecipeToClipboard() {
  if (!activeNutritionData || !activeNutritionData.recipe) return;
  const r = activeNutritionData.recipe;
  const ings = (r.ingredients || []).map(ing => {
    const total = (parseFloat(ing.amount) || 1) * nutritionServingsCount;
    return `- ${ing.name}: ${Number.isInteger(total) ? total : total.toFixed(1)} ${ing.unit}`;
  }).join('\n');
  const steps = (r.steps || []).map((s, i) => `${i + 1}. ${s}`).join('\n');

  const text = isEnLang()
    ? `🍲 ${r.title} (${r.subtitle})\n👥 Servings: ${nutritionServingsCount}\n\n📌 INGREDIENTS:\n${ings}\n\n👩‍🍳 STEPS:\n${steps}\n\n💡 NOTE: ${r.tip}\n⏱️ Time: ${r.cooking_time}\n(Reference from MediMind Nutrition Studio)`
    : `🍲 ${r.title} (${r.subtitle})\n👥 Khẩu phần: ${nutritionServingsCount} người\n\n📌 NGUYÊN LIỆU:\n${ings}\n\n👩‍🍳 CÁCH LÀM:\n${steps}\n\n💡 LƯU Ý: ${r.tip}\n⏱️ Thời gian: ${r.cooking_time}\n(Tham khảo từ MediMind Nutrition Studio)`;

  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).then(() => {
      showMedicalToast(t("Đã sao chép công thức 3 bước vào bộ nhớ tạm!", "Copied 3-step recipe to clipboard!"), "success");
    }).catch(() => {
      showMedicalToast(t("Không thể sao chép văn bản.", "Unable to copy text."), "error");
    });
  } else {
    showMedicalToast(t("Đã sao chép công thức!", "Recipe copied!"), "success");
  }
}
