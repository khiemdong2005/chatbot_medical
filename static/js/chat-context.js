/* Optional, self-reported context for this page only. No browser/database storage. */
(() => {
  let applied = {};
  let panel;
  const fields = ['age', 'gender', 'pregnancy', 'allergies', 'medications', 'conditions'];
  const labels = { age: 'Tuổi', gender: 'Giới tính', pregnancy: 'Thai kỳ / cho con bú',
    allergies: 'Dị ứng', medications: 'Thuốc đang dùng', conditions: 'Bệnh nền tự khai' };

  window.getChatHealthContext = () => ({ ...applied });
  window.clearChatHealthContext = () => {
    applied = {};
    if (!panel) return;
    panel.querySelector('form').reset();
    panel.querySelector('[data-context-status]').textContent = 'Chưa thêm thông tin';
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
      <summary><span>Thông tin sức khỏe <small>Không bắt buộc</small></span><span data-context-status>Chưa thêm thông tin</span></summary>
      <div class="chat-context-body">
        <p class="chat-context-notice">Thông tin tự khai được gửi cùng tin nhắn tới Gemini, không lưu vào hồ sơ tài khoản. Nội dung được nhắc lại trong câu trả lời vẫn thuộc lịch sử chat; bạn có thể xóa cuộc chat để xóa lịch sử đó.</p>
        <form autocomplete="off">
          <fieldset>
            <div class="chat-context-grid">
              <label>Tuổi<input name="age" type="number" min="0" max="120" step="1" inputmode="numeric" placeholder="Ví dụ: 25"></label>
              <label>Giới tính<select name="gender"><option value="unspecified">Chưa cung cấp</option><option value="female">Nữ</option><option value="male">Nam</option><option value="other">Khác</option></select></label>
              <label class="chat-context-wide">Thai kỳ / cho con bú<select name="pregnancy"><option value="unspecified">Chưa cung cấp</option><option value="pregnant">Đang mang thai</option><option value="breastfeeding">Đang cho con bú</option><option value="not_pregnant">Không mang thai</option></select></label>
              <label class="chat-context-wide">Dị ứng thuốc hoặc thực phẩm<textarea name="allergies" maxlength="600" rows="2" placeholder="Nếu có, ghi tên và phản ứng từng gặp"></textarea></label>
              <label class="chat-context-wide">Thuốc đang dùng<textarea name="medications" maxlength="600" rows="2" placeholder="Tên thuốc hoặc thực phẩm bổ sung bạn đang dùng"></textarea></label>
              <label class="chat-context-wide">Bệnh nền tự khai<textarea name="conditions" maxlength="600" rows="2" placeholder="Ví dụ: bệnh đã được bác sĩ chẩn đoán"></textarea></label>
            </div>
            <div class="chat-context-actions"><button type="submit">Dùng cho cuộc trò chuyện này</button><button type="button" data-context-clear>Xóa thông tin bổ sung</button></div>
          </fieldset>
        </form>
        <p class="chat-context-result" data-context-result role="status" aria-live="polite"></p>
      </div>`;
    messages.before(panel);
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
      const included = fields.filter(key => Object.prototype.hasOwnProperty.call(applied, key));
      panel.querySelector('[data-context-status]').textContent = included.length ? `Đang dùng ${included.length} mục tự khai` : 'Chưa thêm thông tin';
      panel.querySelector('[data-context-result]').textContent = included.length
        ? `Lượt hỏi tiếp theo sẽ kèm: ${included.map(key => labels[key]).join(', ')}. Bạn có thể sửa hoặc xóa bất kỳ lúc nào.`
        : 'Không có thông tin bổ sung được gửi kèm.';
    });
    panel.querySelector('[data-context-clear]').addEventListener('click', () => {
      window.clearChatHealthContext();
    });
    window.addEventListener('medimind:chat-busy', event => { form.querySelector('fieldset').disabled = Boolean(event.detail?.busy); });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, { once: true });
  else initialize();
})();
