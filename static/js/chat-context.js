/* Optional, self-reported context for this page only. No browser/database storage. */
(() => {
  let applied = {};
  let hasSubmitted = false;
  let panel;
  const fields = ['age', 'gender', 'pregnancy', 'allergies', 'medications', 'conditions'];
  const isEn = () => typeof currentLang !== 'undefined' && currentLang === 'en';
  const copy = {
    vi: {
      title: 'Thông tin sức khỏe',
      optional: 'Không bắt buộc',
      emptyStatus: 'Chưa thêm thông tin',
      activeStatus: n => `Đang dùng ${n} mục tự khai`,
      notice: 'Thông tin tự khai được gửi cùng tin nhắn tới Gemini, không lưu vào hồ sơ tài khoản. Nội dung được nhắc lại trong câu trả lời vẫn thuộc lịch sử chat; bạn có thể xóa cuộc chat để xóa lịch sử đó.',
      labels: {
        age: 'Tuổi',
        gender: 'Giới tính',
        pregnancy: 'Thai kỳ / cho con bú',
        allergies: 'Dị ứng',
        medications: 'Thuốc đang dùng',
        conditions: 'Bệnh nền tự khai'
      },
      allergiesFull: 'Dị ứng thuốc hoặc thực phẩm',
      placeholders: {
        age: 'Ví dụ: 25',
        allergies: 'Nếu có, ghi tên và phản ứng từng gặp',
        medications: 'Tên thuốc hoặc thực phẩm bổ sung bạn đang dùng',
        conditions: 'Ví dụ: bệnh đã được bác sĩ chẩn đoán'
      },
      genderOpts: { unspecified: 'Chưa cung cấp', female: 'Nữ', male: 'Nam', other: 'Khác' },
      pregOpts: { unspecified: 'Chưa cung cấp', pregnant: 'Đang mang thai', breastfeeding: 'Đang cho con bú', not_pregnant: 'Không mang thai' },
      submitBtn: 'Dùng cho cuộc trò chuyện này',
      clearBtn: 'Xóa thông tin bổ sung',
      appliedResult: list => `Lượt hỏi tiếp theo sẽ kèm: ${list}. Bạn có thể sửa hoặc xóa bất kỳ lúc nào.`,
      emptyResult: 'Không có thông tin bổ sung được gửi kèm.'
    },
    en: {
      title: 'Health Context',
      optional: 'Optional',
      emptyStatus: 'No context added',
      activeStatus: n => `Using ${n} self-reported item${n > 1 ? 's' : ''}`,
      notice: 'Self-reported details are sent with your message to Gemini and are not stored in your account profile. Any details echoed in replies remain part of chat history; delete the chat to remove them.',
      labels: {
        age: 'Age',
        gender: 'Sex / Gender',
        pregnancy: 'Pregnancy / Breastfeeding',
        allergies: 'Allergies',
        medications: 'Current medications',
        conditions: 'Known conditions'
      },
      allergiesFull: 'Drug or food allergies',
      placeholders: {
        age: 'e.g. 25',
        allergies: 'If any, list substance and reaction',
        medications: 'Medications or supplements you currently take',
        conditions: 'e.g. physician-diagnosed conditions'
      },
      genderOpts: { unspecified: 'Not specified', female: 'Female', male: 'Male', other: 'Other' },
      pregOpts: { unspecified: 'Not specified', pregnant: 'Pregnant', breastfeeding: 'Breastfeeding', not_pregnant: 'Not pregnant' },
      submitBtn: 'Apply to this conversation',
      clearBtn: 'Clear health context',
      appliedResult: list => `Next message will include: ${list}. You can edit or clear this anytime.`,
      emptyResult: 'No additional health context will be sent.'
    }
  };
  const dict = () => (isEn() ? copy.en : copy.vi);

  function syncPanelLanguage() {
    if (!panel) return;
    const d = dict();
    const titleEl = panel.querySelector('[data-ctx-title]');
    const optEl = panel.querySelector('[data-ctx-optional]');
    const noticeEl = panel.querySelector('[data-ctx-notice]');
    if (titleEl) titleEl.textContent = d.title + ' ';
    if (optEl) optEl.textContent = d.optional;
    if (noticeEl) noticeEl.textContent = d.notice;

    panel.querySelectorAll('[data-ctx-label]').forEach(el => {
      const k = el.getAttribute('data-ctx-label');
      el.textContent = k === 'allergies_full' ? d.allergiesFull : (d.labels[k] || '');
    });
    panel.querySelectorAll('[data-ctx-ph]').forEach(el => {
      const k = el.getAttribute('data-ctx-ph');
      if (d.placeholders[k]) el.setAttribute('placeholder', d.placeholders[k]);
    });
    panel.querySelectorAll('select[name="gender"] option').forEach(opt => {
      if (d.genderOpts[opt.value]) opt.textContent = d.genderOpts[opt.value];
    });
    panel.querySelectorAll('select[name="pregnancy"] option').forEach(opt => {
      if (d.pregOpts[opt.value]) opt.textContent = d.pregOpts[opt.value];
    });
    const submitBtn = panel.querySelector('[data-context-submit]');
    const clearBtn = panel.querySelector('[data-context-clear]');
    if (submitBtn) submitBtn.textContent = d.submitBtn;
    if (clearBtn) clearBtn.textContent = d.clearBtn;

    const included = fields.filter(key => Object.prototype.hasOwnProperty.call(applied, key));
    const statusEl = panel.querySelector('[data-context-status]');
    const resultEl = panel.querySelector('[data-context-result]');
    if (statusEl) statusEl.textContent = included.length ? d.activeStatus(included.length) : d.emptyStatus;
    if (resultEl && hasSubmitted) {
      resultEl.textContent = included.length
        ? d.appliedResult(included.map(key => d.labels[key]).join(', '))
        : d.emptyResult;
    }
  }

  window.getChatHealthContext = () => ({ ...applied });
  window.clearChatHealthContext = () => {
    applied = {};
    hasSubmitted = false;
    if (!panel) return;
    panel.querySelector('form').reset();
    panel.querySelector('[data-context-status]').textContent = dict().emptyStatus;
    panel.querySelector('[data-context-result]').textContent = '';
    panel.open = false;
  };

  function initialize() {
    const messages = document.getElementById('chat-messages');
    if (!messages || document.getElementById('chat-health-context')) return;
    panel = document.createElement('details');
    panel.id = 'chat-health-context';
    panel.className = 'chat-health-context';
    panel.innerHTML = `
      <summary><span><span data-ctx-title></span><small data-ctx-optional></small></span><span data-context-status></span></summary>
      <div class="chat-context-body">
        <p class="chat-context-notice" data-ctx-notice></p>
        <form autocomplete="off">
          <fieldset>
            <div class="chat-context-grid">
              <label><span data-ctx-label="age"></span><input name="age" data-ctx-ph="age" type="number" min="0" max="120" step="1" inputmode="numeric"></label>
              <label><span data-ctx-label="gender"></span><select name="gender"><option value="unspecified"></option><option value="female"></option><option value="male"></option><option value="other"></option></select></label>
              <label class="chat-context-wide"><span data-ctx-label="pregnancy"></span><select name="pregnancy"><option value="unspecified"></option><option value="pregnant"></option><option value="breastfeeding"></option><option value="not_pregnant"></option></select></label>
              <label class="chat-context-wide"><span data-ctx-label="allergies_full"></span><textarea name="allergies" data-ctx-ph="allergies" maxlength="600" rows="2"></textarea></label>
              <label class="chat-context-wide"><span data-ctx-label="medications"></span><textarea name="medications" data-ctx-ph="medications" maxlength="600" rows="2"></textarea></label>
              <label class="chat-context-wide"><span data-ctx-label="conditions"></span><textarea name="conditions" data-ctx-ph="conditions" maxlength="600" rows="2"></textarea></label>
            </div>
            <div class="chat-context-actions"><button type="submit" data-context-submit></button><button type="button" data-context-clear></button></div>
          </fieldset>
        </form>
        <p class="chat-context-result" data-context-result role="status" aria-live="polite"></p>
      </div>`;
    messages.before(panel);
    syncPanelLanguage();
    const form = panel.querySelector('form');
    form.addEventListener('submit', event => {
      event.preventDefault();
      if (!form.reportValidity()) return;
      const values = new FormData(form);
      const next = {};
      for (const key of fields) {
        const value = String(values.get(key) || '').trim();
        if (key === 'age') { if (value !== '') next.age = Number(value); }
        else if (value && value !== 'unspecified') next[key] = value;
      }
      applied = next;
      hasSubmitted = true;
      syncPanelLanguage();
    });
    panel.querySelector('[data-context-clear]').addEventListener('click', () => {
      window.clearChatHealthContext();
    });
    window.addEventListener('medimind:chat-busy', event => { form.querySelector('fieldset').disabled = Boolean(event.detail?.busy); });
    window.addEventListener('medimind:langchange', syncPanelLanguage);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, { once: true });
  else initialize();
})();
