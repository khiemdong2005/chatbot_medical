const PrevisitIntake = (() => {
  const dialog = document.getElementById('previsit-intake');
  const el = name => document.getElementById('previsit-' + name);
  const tr = (vi, en) => currentLang === 'en' ? en : vi;
  const key = account => 'medimind_previsit_id:' + account;
  const handoffKey = 'medimind_previsit_after_login';
  let state = null;
  let source = 'chat';
  let opener;
  let busy = false;
  let notice = '';
  let retry = null;
  let editor = null;
  let reviewRequested = false;
  let historyRequested = false;
  let view = '';

  function readId(account = chatAccountKey()) {
    try { return localStorage.getItem(key(account)); } catch (_) { return null; }
  }

  function rememberId(account, id) {
    try {
      if (id) localStorage.setItem(key(account), id);
      else localStorage.removeItem(key(account));
    } catch (_) { }
  }

  async function request(path, payload) {
    const response = await fetch('/api/intake/' + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...payload, flow: 'previsit', lang: currentLang })
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.success === false) {
      throw Object.assign(new Error(extractApiErrorMessage(data, fallbackError())), { status: response.status });
    }
    return data;
  }

  function fallbackError() {
    return tr('Chưa thể cập nhật thông tin. Bạn có thể thử lại.', 'Your information could not be updated. Please try again.');
  }

  function renderTranscript(question, visible) {
    const log = el('transcript');
    const turns = [...(state?.transcript || [])];
    if (question) turns.push({ role: 'assistant', text: question });
    log.hidden = !visible || !turns.length;
    log.setAttribute('aria-label', tr('Đoạn hội thoại hỏi bệnh', 'Pre-visit conversation'));
    const common = turns.findIndex(({ role, text }, index) => {
      const turn = log.children[index];
      return turn?.dataset.role !== role || turn.lastElementChild.textContent !== text;
    });
    const unchanged = common === -1 ? turns.length : common;
    const changed = unchanged !== log.children.length || unchanged !== turns.length;
    while (log.children.length > unchanged) log.lastElementChild.remove();
    for (const { role, text } of turns.slice(unchanged)) {
      const turn = document.createElement('div');
      turn.className = 'previsit-turn';
      turn.dataset.role = role;
      const speaker = document.createElement('span');
      speaker.className = 'previsit-speaker';
      speaker.textContent = role === 'user' ? tr('Bạn', 'You') : 'MediMind';
      const bubble = document.createElement('p');
      bubble.className = 'previsit-bubble';
      bubble.textContent = text;
      turn.append(speaker, bubble);
      log.append(turn);
    }
    return changed;
  }

  function updateSendButton() {
    el('next').disabled = busy || !el('answer').value.trim();
  }

  function render() {
    const summary = state?.summary;
    const confirmed = Boolean(summary?.is_confirmed);
    const emergency = state?.status === 'emergency';
    const canReview = !emergency && Boolean(summary?.summary_available);
    const canShowReview = canReview && (confirmed || reviewRequested || !state.next_question);
    const showingHistory = canShowReview && historyRequested;
    const reviewing = canShowReview && !showingHistory;
    const showingQuestion = !emergency && !canShowReview && Boolean(state?.next_question);
    const previousView = view;
    view = showingHistory ? 'history' : reviewing ? 'review' : emergency ? 'urgent' : 'chat';
    const saving = tr('Đang cập nhật…', 'Updating…');
    el('title').textContent = reviewing ? tr('Tóm tắt trước khám', 'Pre-visit summary')
      : showingHistory ? tr('Cuộc trò chuyện', 'Conversation') : tr('Hỏi bệnh trước khám', 'Pre-visit questions');
    el('close').setAttribute('aria-label', tr('Đóng', 'Close'));
    el('stage').textContent = reviewing
      ? (confirmed ? tr('Bạn đã xác nhận lời khai', 'You confirmed these answers')
        : tr('Kiểm tra thông tin trước khi xác nhận', 'Review before confirming'))
      : tr('Chuẩn bị thông tin cho buổi khám', 'Prepare for your appointment');

    const displayNotice = notice || (emergency ? state.answer : '') || (!state && busy ? saving : '');
    el('notice').textContent = displayNotice;
    el('notice').hidden = !displayNotice;
    el('notice').dataset.tone = emergency || notice ? 'alert' : '';
    el('retry').hidden = !retry;
    el('retry').disabled = busy;
    el('retry').textContent = tr('Thử lại', 'Try again');

    const transcriptChanged = renderTranscript(showingQuestion ? state.next_question : '',
      showingQuestion || showingHistory);
    el('question-form').hidden = !showingQuestion;
    const inputLabel = tr('Nhập tin nhắn', 'Type a message');
    el('answer').setAttribute('aria-label', inputLabel);
    el('answer').placeholder = inputLabel + '…';
    el('answer').readOnly = busy;
    el('skip').hidden = !showingQuestion || !state.can_skip;
    el('skip').textContent = tr('Bỏ qua câu này', 'Skip this question');
    el('skip').disabled = busy;
    el('next').textContent = busy && showingQuestion ? tr('Đang gửi…', 'Sending…') : tr('Gửi', 'Send');
    updateSendButton();
    el('peek').hidden = !showingQuestion || !canReview || Boolean(state?.needs_red_flag_confirmation);
    el('peek').disabled = busy;
    el('peek').textContent = tr('Xem tóm tắt', 'View summary');

    el('review').hidden = !reviewing;
    el('edit-form').hidden = !editor;
    el('review-actions').hidden = !reviewing || Boolean(editor);
    el('history-actions').hidden = !showingHistory;
    el('back-review').textContent = tr('Về tóm tắt', 'Back to summary');
    if (!reviewing) {
      if (notice || emergency) el('body').scrollTop = 0;
      else if (transcriptChanged || previousView !== view) el('body').scrollTop = el('body').scrollHeight;
      return;
    }
    renderFacts();
    if (previousView !== view) el('body').scrollTop = 0;
    el('review-heading').textContent = tr('Thông tin bạn cung cấp', 'Information you provided');
    el('view-history').hidden = !state.transcript?.length;
    el('view-history').textContent = tr('Xem cuộc trò chuyện', 'View conversation');
    el('view-history').disabled = busy;
    el('edit-cancel').textContent = tr('Huỷ', 'Cancel');
    el('edit-save').textContent = busy ? saving : tr('Lưu chỉnh sửa', 'Save changes');
    el('edit-value').readOnly = busy;
    el('edit-save').disabled = busy;
    el('edit-cancel').disabled = busy;
    el('new').hidden = !confirmed;
    el('new').disabled = busy;
    el('new').textContent = tr('Phiên mới', 'New intake');
    const finish = el('finish');
    finish.disabled = busy;
    finish.textContent = busy ? saving : confirmed
      ? (source === 'booking' ? tr('Quay lại đặt lịch', 'Back to booking') : tr('Đặt lịch khám', 'Book an appointment'))
      : state.next_question ? tr('Tiếp tục trả lời', 'Continue answering')
        : !currentUser ? tr('Đăng nhập để xác nhận', 'Sign in to confirm')
          : tr('Xác nhận và lưu vào hồ sơ', 'Confirm and save to record');
    if (!confirmed && !state.next_question && summary.ready_to_finalize === false) finish.disabled = true;
  }

  function renderFacts() {
    const facts = state.facts || {};
    const summary = state.summary.part_a_patient_facts || {};
    const container = el('facts');
    container.replaceChildren();
    const symptoms = addFactGroup(container, tr('Triệu chứng và diễn biến', 'Symptoms and changes'));
    const rows = [
      ['chief_complaint', tr('Lý do đi khám', 'Reason for visit'), facts.chief_complaint],
      ['duration', tr('Bắt đầu từ', 'Started'), facts.duration],
      ['present_symptoms', tr('Triệu chứng đã ghi nhận', 'Reported symptoms'), facts.present_symptoms],
      ['denied_symptoms', tr('Triệu chứng bạn cho biết không có', 'Symptoms you reported absent'), facts.denied_symptoms],
      ['activity_impact', tr('Ảnh hưởng đến sinh hoạt', 'Impact on daily activities'), facts.activity_impact]
    ];
    for (const [field, label, value] of rows) {
      let present = Array.isArray(value) ? value.join(', ') : value;
      if (field === 'activity_impact' && value === 'không') present = tr('Không ảnh hưởng', 'No impact');
      if (field === 'activity_impact' && value === 'có') present = tr('Có ảnh hưởng', 'Affected');
      if (present) appendFact(symptoms, label, present, { field, label, value });
    }
    const painLabels = {
      location: tr('Vị trí đau', 'Pain location'),
      severity: tr('Mức độ đau tự đánh giá', 'Self-reported pain level'),
      quality: tr('Tính chất đau', 'Pain description'),
      pattern: tr('Diễn biến cơn đau', 'Pain pattern')
    };
    for (const [part, label] of Object.entries(painLabels)) {
      const value = facts.pain?.[part];
      if (value !== undefined && value !== null && value !== '') {
        appendFact(symptoms, label, String(value), { field: 'pain', label, value, part });
      }
    }
    if (Object.keys(facts.vitals || {}).length) {
      appendFact(symptoms, tr('Chỉ số tự đo', 'Self-reported measurements'), summary.vitals);
    }

    const history = addFactGroup(container, tr('Thuốc, dị ứng và bệnh sử', 'Medicines, allergies and medical history'));
    const fields = {
      medications: tr('Thuốc đã khai', 'Reported medicines'),
      allergies: tr('Dị ứng', 'Allergies'),
      conditions: tr('Bệnh sử liên quan', 'Relevant medical history')
    };
    for (const [part, label] of Object.entries(fields)) {
      const entry = summary.patient_reported_history?.[part];
      const value = entry?.text || '';
      if (!entry && Array.isArray(facts[part]) && facts[part].length) {
        appendFact(history, label, facts[part].join(', '), { field: part, label, value: facts[part] });
        continue;
      }
      const title = {
        denied: part === 'medications' ? '' : tr('Bạn cho biết không có', 'You reported none'),
        unknown: tr('Chưa rõ', 'Unsure'),
        skipped: tr('Đã bỏ qua', 'Skipped')
      }[entry?.status];
      const detail = title && value ? title + ' · ' + value : title || value || tr('Chưa cung cấp', 'Not provided');
      appendFact(history, label, detail, { field: 'patient_reported_history', part, label, value }, !value);
    }

    const answers = summary.contextual_answers || [];
    if (answers.length) {
      const extra = addFactGroup(container, tr('Thông tin bổ sung', 'Additional details'));
      for (const [index, entry] of answers.entries()) {
        const label = contextualLabel(entry.question);
        appendFact(extra, label, entry.answer,
          { field: 'contextual_answers', label, value: entry.answer, index });
      }
    }
  }

  function contextualLabel(question) {
    if (/^(Bạn đau ở vị trí|Where is the pain)/i.test(question)) return tr('Vị trí bạn mô tả', 'Pain location as described');
    if (/^(Cơn đau có cảm giác|What does the pain feel)/i.test(question)) return tr('Tính chất bạn mô tả', 'Pain as described');
    if (/^(Trên thang 0 đến 10|On a scale of 0 to 10)/i.test(question)) return tr('Mức độ bạn mô tả', 'Severity as described');
    if (/^(Từ khi bắt đầu|Since it started)/i.test(question)) return tr('Diễn biến', 'Changes since onset');
    return question;
  }

  function addFactGroup(container, label) {
    const group = document.createElement('section');
    group.className = 'previsit-fact-group';
    const heading = document.createElement('h4');
    heading.textContent = label;
    const list = document.createElement('dl');
    group.append(heading, list);
    container.append(group);
    return list;
  }

  function appendFact(list, label, value, edit, missing = false) {
    const row = document.createElement('div');
    row.className = 'previsit-fact';
    const term = document.createElement('dt');
    term.textContent = label;
    const description = document.createElement('dd');
    description.textContent = value;
    description.dataset.muted = String(missing);
    row.append(term, description);
    if (edit) {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = missing ? tr('Thêm', 'Add') : tr('Sửa', 'Edit');
      button.setAttribute('aria-label', button.textContent + ' · ' + label);
      button.disabled = busy;
      button.addEventListener('click', () => {
        editor = edit;
        el('edit-label').textContent = label;
        el('edit-value').value = Array.isArray(edit.value) ? edit.value.join(', ') : edit.value;
        render();
        el('edit-value').focus();
      });
      row.append(button);
    }
    list.append(row);
  }

  async function update(action) {
    if (busy) return;
    const account = chatAccountKey();
    busy = true;
    notice = '';
    retry = null;
    render();
    try {
      await action(account);
    } catch (error) {
      if (account === chatAccountKey()) notice = error.message || fallbackError();
    } finally {
      busy = false;
      render();
    }
  }

  async function loadSession(id, { handoff = false, fresh = false } = {}) {
    await update(async account => {
      let data;
      try {
        data = await request('session', { conversation_id: id });
        if (!data.conversation_id) throw new Error(fallbackError());
      } catch (error) {
        if (!id || ![403, 404].includes(error.status)) {
          retry = () => loadSession(id, { handoff, fresh });
          throw error;
        }
        if (account !== chatAccountKey()) return;
        if (handoff) {
          retry = () => loadSession(readId());
          throw new Error(tr('Không thể mở lại phiên hỏi bệnh sau khi đăng nhập.', 'This intake could not be reopened after signing in.'));
        }
        rememberId(account, null);
        retry = () => loadSession(null, { fresh: true });
        throw new Error(tr('Phiên hỏi bệnh này không còn khả dụng.', 'This intake is no longer available.'));
      }
      if (account !== chatAccountKey()) return;
      state = data;
      editor = null;
      reviewRequested = false;
      historyRequested = false;
      el('answer').value = '';
      rememberId(account, data.conversation_id);
      if (handoff) rememberId('guest', null);
      if (fresh) checkAndPrepareBookingPreVisitSummary();
    });
    focusCurrentStep();
  }

  function focusCurrentStep() {
    if (!dialog.open) return;
    if (!el('question-form').hidden) el('answer').focus();
    else if (!el('review').hidden) el('review-heading').focus();
    else if (!el('history-actions').hidden) el('back-review').focus();
    else if (!el('retry').hidden) el('retry').focus();
    else el('close').focus();
  }

  function open(from = 'chat', handoffId = null) {
    if (dialog.open) return;
    source = from;
    opener = document.activeElement;
    if (!busy) {
      state = null;
      editor = null;
      reviewRequested = false;
      historyRequested = false;
      el('answer').value = '';
    }
    dialog.showModal();
    el('body').scrollTop = 0;
    if (!busy) loadSession(handoffId || readId(), { handoff: Boolean(handoffId) });
  }

  async function send(skip = false) {
    if (!state || busy) return;
    const message = el('answer').value.trim();
    if (!skip && !message) {
      el('answer').focus();
      return;
    }
    await update(async account => {
      const data = await write('message', { message, skip });
      if (account !== chatAccountKey()) return;
      state = data;
      reviewRequested = false;
      el('answer').value = '';
    });
    focusCurrentStep();
  }

  async function write(path, payload) {
    const { conversation_id, version } = state;
    try {
      return await request(path, { ...payload, conversation_id, expected_version: version });
    } catch (error) {
      if (error.status === 409) retry = () => loadSession(conversation_id);
      throw error;
    }
  }

  async function saveEdit() {
    if (!editor || busy) return;
    let value = el('edit-value').value.trim();
    if (!value && editor.field === 'chief_complaint') {
      el('edit-value').focus();
      return;
    }
    const { field, index, part } = editor;
    if (index !== undefined) {
      const answer = value;
      const answers = [...state.summary.part_a_patient_facts.contextual_answers];
      if (answer) answers[index] = { ...answers[index], answer };
      else answers.splice(index, 1);
      value = answers;
    } else if (field === 'patient_reported_history') {
      const history = { ...state.summary.part_a_patient_facts.patient_reported_history };
      if (value) history[part] = { text: value };
      else delete history[part];
      value = history;
    } else if (part) {
      const pain = { ...state.facts.pain };
      if (value) pain[part] = value;
      else delete pain[part];
      value = pain;
    } else if (Array.isArray(editor.value)) {
      value = value.split(',').map(item => item.trim()).filter(Boolean);
    }
    await update(async account => {
      const data = await write('update-fact', { field, value });
      if (account !== chatAccountKey()) return;
      state = data;
      editor = null;
      checkAndPrepareBookingPreVisitSummary();
    });
    if (!editor) focusCurrentStep();
  }

  async function finish() {
    const summary = state?.summary;
    if (!summary || busy) return;
    if (summary.is_confirmed) {
      if (source !== 'booking') opener = null;
      dialog.close();
      if (source === 'booking') checkAndPrepareBookingPreVisitSummary();
      else switchTab('booking-tab');
      return;
    }
    if (state.next_question) {
      reviewRequested = false;
      render();
      focusCurrentStep();
      return;
    }
    if (!currentUser) {
      try { sessionStorage.setItem(handoffKey, state.conversation_id); } catch (_) { }
      opener = null;
      dialog.close();
      openLoginModal('login');
      return;
    }
    await update(async account => {
      const id = state.conversation_id;
      try {
        const data = await request('confirm-summary', {
          conversation_id: id, version: summary.version,
          reviewed_facts: summary.part_a_patient_facts, save_to_record: true
        });
        if (account !== chatAccountKey()) return;
        state = { ...state, summary: data.summary };
        checkAndPrepareBookingPreVisitSummary();
      } catch (error) {
        if (error.status === 409) retry = () => loadSession(id);
        throw error;
      }
    });
    focusCurrentStep();
  }

  function resumeAfterLogin() {
    let id;
    try {
      id = sessionStorage.getItem(handoffKey);
      sessionStorage.removeItem(handoffKey);
    } catch (_) { }
    if (id) setTimeout(() => { if (currentUser) open('chat', id); }, 0);
  }

  async function bookingSummary() {
    const id = readId();
    if (!id) return null;
    const response = await fetch('/api/intake/summary/' + encodeURIComponent(id), { cache: 'no-store' });
    if (!response.ok) return null;
    const { summary } = await response.json();
    return summary?.is_confirmed ? { id, version: summary.version } : null;
  }

  el('close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('close', () => { if (!dialog.open) opener?.focus(); });
  dialog.addEventListener('click', event => { if (event.target === dialog) dialog.close(); });
  el('question-form').addEventListener('submit', event => { event.preventDefault(); send(); });
  el('answer').addEventListener('input', updateSendButton);
  el('answer').addEventListener('keydown', event => {
    if (event.key !== 'Enter' || event.shiftKey || event.isComposing) return;
    event.preventDefault();
    el('question-form').requestSubmit();
  });
  el('skip').addEventListener('click', () => send(true));
  el('peek').addEventListener('click', () => { reviewRequested = true; render(); focusCurrentStep(); });
  el('view-history').addEventListener('click', () => { historyRequested = true; render(); focusCurrentStep(); });
  el('back-review').addEventListener('click', () => { historyRequested = false; render(); focusCurrentStep(); });
  el('retry').addEventListener('click', () => retry?.());
  el('new').addEventListener('click', () => loadSession(null, { fresh: true }));
  el('finish').addEventListener('click', finish);
  el('edit-form').addEventListener('submit', event => { event.preventDefault(); saveEdit(); });
  el('edit-cancel').addEventListener('click', () => { editor = null; render(); focusCurrentStep(); });
  window.addEventListener('medimind:langchange', () => { if (dialog && dialog.open) render(); });

  return { open, resumeAfterLogin, bookingSummary };
})();
