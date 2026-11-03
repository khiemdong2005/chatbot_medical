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

  document.getElementById('set-curr-pass').value = '';
  document.getElementById('set-new-pass').value = '';
  document.getElementById('set-confirm-pass').value = '';

  const msg = currentLang === 'en' ? 'Password changed successfully!' : 'Đã thay đổi mật khẩu thành công!';
  showMedicalToast(msg, 'success');
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

function toggleFieldMask(fieldId) {
  fieldMaskState[fieldId] = !fieldMaskState[fieldId];
  const isMasked = fieldMaskState[fieldId];
  const input = document.getElementById(fieldId);
  const eyeIcon = document.getElementById(fieldId + '-eye');
  
  if (!input) return;

  if (isMasked) {
    if (!fieldRealValues[fieldId]) {
      fieldRealValues[fieldId] = input.value;
    }
    input.value = maskFieldValue(fieldRealValues[fieldId], fieldId);
  } else {
    input.value = fieldRealValues[fieldId] !== undefined ? fieldRealValues[fieldId] : input.value;
  }

  // Sync left card if email or phone
  if (fieldId === 'p-email') {
    const cardEmail = document.getElementById('profile-card-email');
    const realEmail = fieldRealValues[fieldId] || input.value;
    if (cardEmail) cardEmail.innerText = isMasked ? maskFieldValue(realEmail, 'p-email') : realEmail;
  } else if (fieldId === 'p-phone') {
    const cardPhone = document.getElementById('profile-card-phone');
    const realPhone = fieldRealValues[fieldId] || input.value;
    if (cardPhone) cardPhone.innerText = isMasked ? maskFieldValue(realPhone, 'p-phone') : realPhone;
  }

  if (eyeIcon) {
    if (isMasked) {
      eyeIcon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l18 18"/>';
    } else {
      eyeIcon.innerHTML = '<path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path stroke-linecap="round" stroke-linejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/>';
    }
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

let currentUser = JSON.parse(localStorage.getItem('medimind_user') || 'null');
if (currentUser && (!currentUser.hasCustomAvatar || currentUser.avatar?.includes('user_avatar.png') || currentUser.avatar?.includes('.svg'))) {
  currentUser.avatar = getDefaultAvatarByGender(currentUser.gender || 'Nam');
  currentUser.hasCustomAvatar = false;
  localStorage.setItem('medimind_user', JSON.stringify(currentUser));
}
if (!currentUser || !currentUser.clinical_id || currentUser.clinical_id.length !== 8 || currentUser.name === 'Luyến Lê Công' || currentUser.name === 'BS. Lê Công Luyến') {
  currentUser = DEFAULT_USER_PROFILE;
  localStorage.setItem('medimind_user', JSON.stringify(currentUser));
}
let pendingTabAfterLogin = null;
let selectedChatImageBase64 = null;

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
    assistant_header_title: "Trợ lý sức khỏe AI",
    assistant_header_subtitle: "Đang trực tuyến • Phác đồ MedlinePlus & Dược thư",
    assistant_btn_summary: "Hồ sơ & Tóm tắt",
    assistant_greeting_title: "Chào bạn, tôi là Trợ lý sức khỏe AI MediMind!",
    assistant_greeting_desc: "Tôi có thể hỗ trợ bạn sàng lọc triệu chứng sơ bộ, giải thích đơn thuốc và gợi ý chuyên khoa khám phù hợp. Bạn đang gặp phải vấn đề sức khỏe nào?",
    quick_1: "🩺 Sốt 38.5°C & đau rát họng",
    quick_2: "⚠️ Đau tức ngực, khó thở",
    quick_3: "💊 Lịch uống đơn thuốc sau ăn?",
    quick_4: "🏥 Gợi ý chuyên khoa khám",
    quick_prompt_text_1: "Tôi bị sốt 38.5 độ và đau rát họng hai hôm nay, nuốt đau",
    quick_prompt_text_2: "Tôi bị đau thắt ngực dữ dội, vã mồ hôi và khó thở lan ra cánh tay trái",
    quick_prompt_text_3: "Sau khi bóc tách đơn thuốc, tôi cần uống thuốc trước hay sau bữa ăn?",
    quick_prompt_text_4: "Tôi bị đau thượng vị cồn cào sau khi ăn thì nên đăng ký khám chuyên khoa nào?",
    chat_input_placeholder: "Mô tả triệu chứng (ví dụ: đau tức ngực, sốt, đau dạ dày) hoặc gửi ảnh đơn thuốc...",
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
    assistant_header_title: "MediMind AI Health Assistant",
    assistant_header_subtitle: "Online • MedlinePlus Guidelines & Formulary",
    assistant_btn_summary: "Record & Summary",
    assistant_greeting_title: "Hello, I am MediMind Clinical AI Assistant!",
    assistant_greeting_desc: "I can assist you with preliminary symptom triage, prescription explanations, and appropriate clinic referrals. What health concern can I help you with today?",
    quick_1: "🩺 Fever 38.5°C & Sore Throat",
    quick_2: "⚠️ Chest Tightness, Dyspnea",
    quick_3: "💊 Post-meal Prescription Schedule?",
    quick_4: "🏥 Specialty Referral Guidance",
    quick_prompt_text_1: "I have had a fever of 38.5 C and sore throat for 2 days, painful swallowing",
    quick_prompt_text_2: "I have intense crushing chest pain, sweating, and shortness of breath radiating to left arm",
    quick_prompt_text_3: "Should I take this medication before or after meals?",
    quick_prompt_text_4: "I feel burning epigastric pain after eating, which specialty should I consult?",
    chat_input_placeholder: "Describe symptoms (e.g. chest pain, fever, stomach ache) or send prescription photo...",
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

  // Floating Chatbox: Show on all tabs except Trợ lý sức khỏe (chat-tab)
  const floatingChat = document.getElementById('floating-chat-container');
  if (floatingChat) {
    if (tabId === 'chat-tab') {
      floatingChat.classList.add('hidden');
    } else {
      floatingChat.classList.remove('hidden');
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
  const container = document.getElementById('chat-messages');
  if (container) container.innerHTML = '';

  const historyList = document.getElementById('chat-history-list');
  const historyEmpty = document.getElementById('chat-history-empty');
  const searchInput = document.getElementById('history-search-input');
  if (searchInput) searchInput.value = '';
  if (historyList) {
    historyList.innerHTML = '';
    historyList.classList.add('hidden');
  }
  if (historyEmpty) historyEmpty.classList.remove('hidden');
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
      // Set Facebook-style default avatar based on gender (Nam, Nữ, Khác)
      currentUser.hasCustomAvatar = false;
      currentUser.avatar = getDefaultAvatarByGender(currentUser.gender || gender);
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

function syncAuthModalTheme() {
  const isLight = document.body.classList.contains('light-glass');
  const card = document.getElementById('auth-modal-card');
  const title = document.getElementById('auth-modal-title');
  const modal = document.getElementById('login-modal');
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
  }
  if (typeof toggleAuthMode === 'function') {
    toggleAuthMode(currentAuthMode);
  }
}

function openLoginModal() {
  syncAuthModalTheme();
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
  const tabLogin = document.getElementById('tab-auth-login');
  const tabReg = document.getElementById('tab-auth-register');

  const isLight = document.body.classList.contains('light-glass');

  if (mode === 'login') {
    if (titleEl) titleEl.innerText = dict.modal_login_title || "Đăng nhập MediMind AI";
    if (loginForm) loginForm.classList.remove('hidden');
    if (regForm) regForm.classList.add('hidden');

    if (tabLogin) {
      if (isLight) {
        tabLogin.className = "flex-1 py-2 px-3 rounded-lg border-2 border-sky-500 bg-white text-sky-600 font-bold shadow-xs transition-all cursor-pointer";
      } else {
        tabLogin.className = "flex-1 py-2 px-3 rounded-lg border border-sky-400/50 bg-sky-500/20 text-sky-300 font-bold shadow-xs transition-all cursor-pointer";
      }
    }
    if (tabReg) {
      if (isLight) {
        tabReg.className = "flex-1 py-2 px-3 rounded-lg border-0 bg-transparent text-slate-500 hover:text-sky-600 font-medium transition-all cursor-pointer";
      } else {
        tabReg.className = "flex-1 py-2 px-3 rounded-lg border-0 bg-transparent text-slate-400 hover:text-white font-medium transition-all cursor-pointer";
      }
    }
  } else {
    if (titleEl) titleEl.innerText = dict.modal_reg_title || "Đăng ký tài khoản MediMind";
    if (loginForm) loginForm.classList.add('hidden');
    if (regForm) regForm.classList.remove('hidden');

    if (tabReg) {
      if (isLight) {
        tabReg.className = "flex-1 py-2 px-3 rounded-lg border-2 border-sky-500 bg-white text-sky-600 font-bold shadow-xs transition-all cursor-pointer";
      } else {
        tabReg.className = "flex-1 py-2 px-3 rounded-lg border border-sky-400/50 bg-sky-500/20 text-sky-300 font-bold shadow-xs transition-all cursor-pointer";
      }
    }
    if (tabLogin) {
      if (isLight) {
        tabLogin.className = "flex-1 py-2 px-3 rounded-lg border-0 bg-transparent text-slate-500 hover:text-sky-600 font-medium transition-all cursor-pointer";
      } else {
        tabLogin.className = "flex-1 py-2 px-3 rounded-lg border-0 bg-transparent text-slate-400 hover:text-white font-medium transition-all cursor-pointer";
      }
    }
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
      body: JSON.stringify({ identifier, email: identifier, password })
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

    if (ehrTitle) ehrTitle.innerText = currentLang === 'en' ? 'My Health Record & Pre-Visit Summary' : 'Hồ sơ của tôi & Tóm tắt trước khám';
    if (ehrSubtitle) ehrSubtitle.innerText = currentLang === 'en' ? ('Automatically synchronized from clinical screenings of ' + currentUser.name) : ('Tự động đồng bộ từ các lượt sàng lọc y tế của ' + currentUser.name);
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
    // Sync Image 1 fields (Registration preserved, others empty on 1st edit)
    const pBirthDate = document.getElementById('p-birthdate');
    const pGender = document.getElementById('p-gender');
    const pPhone = document.getElementById('p-phone');
    const pEmail = document.getElementById('p-email');
    const pCccd = document.getElementById('p-cccd');
    const pIssueDate = document.getElementById('p-issue-date');
    const pBhyt = document.getElementById('p-bhyt');
    const pFacility = document.getElementById('p-facility');
    const pValidFrom = document.getElementById('p-valid-from');
    const pValidTo = document.getElementById('p-valid-to');
    const pIssuePlace = document.getElementById('p-issue-place');
    const pNationality = document.getElementById('p-nationality');
    const pEthnicity = document.getElementById('p-ethnicity');
    const pReligion = document.getElementById('p-religion');
    const pProvince = document.getElementById('p-province');
    const pWard = document.getElementById('p-ward');
    const pAddress = document.getElementById('p-address');

    const cardName = document.getElementById('profile-card-name');
    const cardEmail = document.getElementById('profile-card-email');
    const cardPhone = document.getElementById('profile-card-phone');

    // 1. Preserved from Registration
    if (pBirthDate) pBirthDate.value = currentUser.dob || '04/10/2005';
    if (pGender && currentUser.gender) pGender.value = currentUser.gender;
    
    const phoneVal = currentUser.phone_number || '0347047101';
    fieldRealValues['p-phone'] = phoneVal;
    if (pPhone) pPhone.value = fieldMaskState['p-phone'] ? maskFieldValue(phoneVal, 'p-phone') : phoneVal;

    const emailVal = currentUser.email || 'benhnhan.an@gmail.com';
    fieldRealValues['p-email'] = emailVal;
    if (pEmail) pEmail.value = fieldMaskState['p-email'] ? maskFieldValue(emailVal, 'p-email') : emailVal;

    // 2. Initial edit: Empty if not yet provided by user
    const cccdVal = currentUser.cccd || '';
    fieldRealValues['p-cccd'] = cccdVal;
    if (pCccd) pCccd.value = fieldMaskState['p-cccd'] ? maskFieldValue(cccdVal, 'p-cccd') : cccdVal;

    const issueDateVal = currentUser.issue_date || '';
    fieldRealValues['p-issue-date'] = issueDateVal;
    if (pIssueDate) pIssueDate.value = fieldMaskState['p-issue-date'] ? maskFieldValue(issueDateVal, 'p-issue-date') : issueDateVal;

    const bhytVal = currentUser.bhyt || '';
    fieldRealValues['p-bhyt'] = bhytVal;
    if (pBhyt) pBhyt.value = fieldMaskState['p-bhyt'] ? maskFieldValue(bhytVal, 'p-bhyt') : bhytVal;

    if (pFacility) pFacility.value = currentUser.facility || '';

    const validFromVal = currentUser.valid_from || '';
    fieldRealValues['p-valid-from'] = validFromVal;
    if (pValidFrom) pValidFrom.value = fieldMaskState['p-valid-from'] ? maskFieldValue(validFromVal, 'p-valid-from') : validFromVal;

    const validToVal = currentUser.valid_to || '';
    fieldRealValues['p-valid-to'] = validToVal;
    if (pValidTo) pValidTo.value = fieldMaskState['p-valid-to'] ? maskFieldValue(validToVal, 'p-valid-to') : validToVal;

    if (pIssuePlace) pIssuePlace.value = currentUser.issue_place || '';
    if (pNationality) pNationality.value = currentUser.nationality || 'VN';
    if (pEthnicity) pEthnicity.value = currentUser.ethnicity || '';
    if (pReligion) pReligion.value = currentUser.religion || '';
    
    if (pProvince) {
      pProvince.value = currentUser.province || '';
      handleProvinceChange();
      if (pWard) {
        pWard.value = currentUser.ward || '';
      }
    }
    if (pAddress) pAddress.value = currentUser.address || '';

    if (cardName) cardName.innerText = currentUser.name || 'Nguyễn Văn An';
    if (cardEmail) cardEmail.innerText = fieldMaskState['p-email'] ? maskFieldValue(emailVal, 'p-email') : emailVal;
    if (cardPhone) cardPhone.innerText = fieldMaskState['p-phone'] ? maskFieldValue(phoneVal, 'p-phone') : phoneVal;
    
    
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
      : getDefaultAvatarByGender(currentUser.gender || 'Nam');
    
    if (!currentUser.hasCustomAvatar) {
      currentUser.avatar = avatarUrl;
    }
    
    const topAvatar = document.getElementById('user-avatar-img');
    const dispAvatar = document.getElementById('profile-avatar-display');
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
  } else {
    if (unlogged) unlogged.classList.remove('hidden');
    if (logged) logged.classList.add('hidden');
    if (nameEl) nameEl.innerText = currentLang === 'en' ? 'Guest' : 'Khách';
    if (roleEl) roleEl.innerText = currentLang === 'en' ? 'Not signed in' : 'Chưa đăng nhập';
    if (avatarEl) avatarEl.innerText = '👤';
    if (ehrPatientName) ehrPatientName.innerText = currentLang === 'en' ? 'Not signed in' : 'Chưa đăng nhập';
    if (ehrPatientId) ehrPatientId.innerText = currentLang === 'en' ? 'Please sign in to sync pre-visit summary' : 'Vui lòng đăng nhập để đồng bộ tóm tắt trước khám';
    if (ehrEmpty) ehrEmpty.classList.remove('hidden');
    if (ehrFilled) ehrFilled.classList.add('hidden');

    const historyList = document.getElementById('chat-history-list');
    const historyEmpty = document.getElementById('chat-history-empty');
    if (historyList) {
      historyList.innerHTML = '';
      historyList.classList.add('hidden');
    }
    if (historyEmpty) historyEmpty.classList.remove('hidden');

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
// Initialization & Global Event Listeners
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
  initThemeMode();
  populateDobDropdowns();
  updateAuthUI();
  applyLanguage();
  initHistorySearch();

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

function initThemeMode() {
  const savedTheme = localStorage.getItem('medimind_theme') || 'light';
  if (savedTheme === 'light') {
    document.body.classList.add('light-glass');
    document.body.style.backgroundImage = CLINICAL_CYAN_GLOW.light;
  } else {
    document.body.classList.remove('light-glass');
    document.body.style.backgroundImage = CLINICAL_CYAN_GLOW.dark;
  }
  document.body.style.backgroundAttachment = 'fixed';
}

function toggleGlassThemeMode() {
  document.body.classList.toggle('light-glass');
  const isLight = document.body.classList.contains('light-glass');
  document.body.style.backgroundImage = isLight ? CLINICAL_CYAN_GLOW.light : CLINICAL_CYAN_GLOW.dark;
  document.body.style.backgroundAttachment = 'fixed';
  localStorage.setItem('medimind_theme', isLight ? 'light' : 'dark');
  if (typeof syncAuthModalTheme === 'function') syncAuthModalTheme();
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
  const ehrEmpty = document.getElementById('ehr-content-empty');
  if (ehrEmpty && !ehrEmpty.classList.contains('hidden')) {
    showMedicalToast('Bạn chưa có bản tóm tắt trước khám để kết xuất PDF. Vui lòng hoàn thành buổi sàng lọc với Trợ lý AI trước.', 'warning', 4500);
    return;
  }
  window.print();
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
          <span class="text-[10px] px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-400/30 font-semibold">Nguy cơ: 30/100 (An toàn)</span>
        </div>
        <div class="text-slate-200 font-normal leading-relaxed space-y-2">
          <p><strong>1. Đánh giá sơ bộ & Phân tầng nguy cơ:</strong><br>
          • <strong>Triệu chứng:</strong> Ho khan 4 ngày, rát họng, sốt nhẹ 37.8°C.<br>
          • <strong>Dấu hiệu cảnh báo:</strong> Không ghi nhận khó thở, đau ngực dữ dội hay tím tái.<br>
          • <strong>Phân loại:</strong> Phù hợp theo dõi và chăm sóc ban đầu tại nhà.</p>

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

  const historyList = document.getElementById('chat-history-list');
  const historyEmpty = document.getElementById('chat-history-empty');
  if (historyEmpty) historyEmpty.classList.add('hidden');
  if (historyList) {
    historyList.classList.remove('hidden');
    historyList.innerHTML = `
      <div class="chat-history-item p-3 rounded-xl bg-white/[0.04] border border-sky-500/30 space-y-1 cursor-pointer hover:bg-white/[0.08] transition-all">
        <div class="flex items-center justify-between">
          <span class="text-[10px] font-bold px-1.5 py-0.5 rounded bg-sky-500/20 text-sky-300 border border-sky-400/30">[MẪU] Ho khan &amp; sốt nhẹ</span>
          <span class="text-[10px] text-slate-400">Vừa xong</span>
        </div>
        <p class="text-[11px] text-slate-300 truncate">Ho khan 4 ngày, đau rát họng, sốt nhẹ 37.8°C...</p>
        <div class="flex items-center justify-between text-[10px] text-slate-400 pt-1 border-t border-white/5">
          <span class="text-sky-400 font-semibold">Điểm nguy cơ: 30/100</span>
          <span class="text-emerald-400">An toàn</span>
        </div>
      </div>
    `;
  }

  showMedicalToast('Đã nạp hội thoại mẫu (Demo). Đây là dữ liệu minh họa, không phải lịch sử y tế thật.', 'info', 4000);
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
    const query = e.target.value.trim().toLowerCase();
    const historyList = document.getElementById('chat-history-list');
    if (!historyList) return;

    const items = historyList.querySelectorAll('.chat-history-item');
    if (items.length === 0) return;

    let matchCount = 0;
    items.forEach(item => {
      const text = item.innerText.toLowerCase();
      if (!query || text.includes(query)) {
        item.classList.remove('hidden');
        matchCount++;
      } else {
        item.classList.add('hidden');
      }
    });

    let noMatchNotice = document.getElementById('history-no-match-notice');
    if (matchCount === 0 && query) {
      if (!noMatchNotice) {
        noMatchNotice = document.createElement('div');
        noMatchNotice.id = 'history-no-match-notice';
        noMatchNotice.className = 'p-3 text-center text-xs text-slate-400 bg-white/[0.02] border border-white/5 rounded-xl';
        noMatchNotice.innerHTML = `<span>Không tìm thấy phiên tư vấn nào khớp với "<strong>${escapeHtml(query)}</strong>"</span>`;
        historyList.appendChild(noMatchNotice);
      } else {
        noMatchNotice.innerHTML = `<span>Không tìm thấy phiên tư vấn nào khớp với "<strong>${escapeHtml(query)}</strong>"</span>`;
        noMatchNotice.classList.remove('hidden');
      }
    } else if (noMatchNotice) {
      noMatchNotice.classList.add('hidden');
    }
  });
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

function handleSaveImage1Profile(e) {
  if (e) e.preventDefault();
  const birthDate = document.getElementById('p-birthdate')?.value.trim();
  const gender = document.getElementById('p-gender')?.value || 'Nam';
  
  const getFieldValue = (fieldId, fallback = '') => {
    if (fieldMaskState[fieldId] && fieldRealValues[fieldId] !== undefined) {
      return fieldRealValues[fieldId];
    }
    const val = document.getElementById(fieldId)?.value.trim();
    if (val !== undefined && val !== null) {
      fieldRealValues[fieldId] = val;
      return val;
    }
    return fallback;
  };

  const phone = getFieldValue('p-phone', currentUser?.phone_number || '');
  const email = getFieldValue('p-email', currentUser?.email || '');
  const cccd = getFieldValue('p-cccd');
  const issueDate = getFieldValue('p-issue-date');
  const bhyt = getFieldValue('p-bhyt');
  const facility = document.getElementById('p-facility')?.value.trim() || '';
  const validFrom = getFieldValue('p-valid-from');
  const validTo = getFieldValue('p-valid-to');
  const issuePlace = document.getElementById('p-issue-place')?.value.trim() || '';
  const nationality = document.getElementById('p-nationality')?.value.trim() || 'VN';
  const ethnicity = document.getElementById('p-ethnicity')?.value || '';
  const religion = document.getElementById('p-religion')?.value || '';
  const province = document.getElementById('p-province')?.value || '';
  const ward = document.getElementById('p-ward')?.value.trim() || '';
  const address = document.getElementById('p-address')?.value.trim() || '';

  if (!currentUser) {
    currentUser = { id: 84291908, role: 'patient', badge: 'BN' };
  }

  currentUser.dob = birthDate;
  currentUser.gender = gender;
  currentUser.phone_number = phone || currentUser.phone_number;
  currentUser.email = email || currentUser.email;
  currentUser.cccd = cccd;
  currentUser.issue_date = issueDate;
  currentUser.bhyt = bhyt;
  currentUser.facility = facility;
  currentUser.valid_from = validFrom;
  currentUser.valid_to = validTo;
  currentUser.issue_place = issuePlace;
  currentUser.nationality = nationality;
  currentUser.ethnicity = ethnicity;
  currentUser.religion = religion;
  currentUser.province = province;
  currentUser.ward = ward;
  currentUser.address = address;

  localStorage.setItem('medimind_user', JSON.stringify(currentUser));

  // Sync Left Card
  const cPhone = document.getElementById('profile-card-phone');
  const cEmail = document.getElementById('profile-card-email');
  if (cPhone) cPhone.innerText = fieldMaskState['p-phone'] ? maskFieldValue(currentUser.phone_number, 'p-phone') : (currentUser.phone_number || '');
  if (cEmail) cEmail.innerText = fieldMaskState['p-email'] ? maskFieldValue(currentUser.email, 'p-email') : (currentUser.email || '');

  updateAuthUI();

  const msg = currentLang === 'en' ? 'Information saved successfully!' : 'Đã lưu thông tin thành công!';
  showMedicalToast(msg, 'success');
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
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        user_name: currentUser ? (currentUser.first_name || currentUser.name || 'Bệnh nhân') : 'Bệnh nhân'
      })
    });
    const data = await res.json();
    document.getElementById(typingId)?.remove();

    const isLightMode = document.body.classList.contains('light-glass');
    const botBubble = document.createElement('div');
    botBubble.className = 'flex justify-start';
    botBubble.innerHTML = `
      <div class="max-w-[88%] px-3.5 py-2.5 rounded-2xl rounded-tl-xs ${isLightMode ? 'bg-slate-100 text-slate-800 border border-slate-200' : 'bg-white/10 text-slate-200 border border-white/10'} text-xs leading-relaxed shadow-xs">
        ${data.reply || data.response || 'Hệ thống đã ghi nhận thông tin của bạn.'}
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
