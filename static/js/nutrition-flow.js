/* Search → type → options → recipe. The API supplies complete recipes. */
(() => {
  const state = { query: '', type: '', recipes: [], sources: [], avoidance: [], avoidanceNote: '', request: null };
  const el = id => document.getElementById(id);
  const safe = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const artworkIds = new Set(['oat_porridge', 'pumpkin_soup', 'rice_carrot', 'soft_egg', 'sweet_potato', 'chicken_congee', 'tofu_pumpkin', 'warm_water', 'warm_milk', 'oat_drink', 'cucumber_water', 'warm_soy', 'pear_water', 'barley_water']);
  function artwork(recipe) {
    const id = artworkIds.has(recipe.id) ? recipe.id : (state.type === 'drink' ? 'category-drink' : 'category-food');
    return `/static/images/nutrition/${id}.svg?v=1`;
  }
  let initialized = false;

  function sourceLinks(ids) {
    const seen = new Set();
    return ids.map(id => state.sources[id]).filter(Boolean).map(source => {
      try {
        const url = new URL(source.source_url);
        if (url.protocol !== 'https:' || seen.has(url.href)) return '';
        seen.add(url.href);
        return `<a href="${safe(url.href)}" target="_blank" rel="noopener noreferrer">${safe(source.source_title)}</a>`;
      } catch (_) { return ''; }
    }).filter(Boolean).join(' · ');
  }

  function avoidanceMarkup(compact = false) {
    const heading = compact ? 'h3' : 'h2';
    const items = state.avoidance.map(item => {
      let source = '';
      try {
        const url = new URL(item.source_url);
        if (url.protocol === 'https:') source = `<a href="${safe(url.href)}" target="_blank" rel="noopener noreferrer">${safe(item.source_title)}</a>`;
      } catch (_) { /* An invalid source never becomes a clickable link. */ }
      return `<article class="nf-limit-item"><span class="nf-limit-level">${item.level === 'avoid' ? 'Cần tránh' : 'Nên hạn chế'}</span><strong>${safe(item.title)}</strong><p>${safe(item.reason)}</p>${source ? `<div class="nf-source-links">Nguồn: ${source}</div>` : ''}</article>`;
    }).join('');
    return `<${heading} class="nf-limit-title">Nên hạn chế / cần tránh</${heading}><p class="nf-limit-note">${safe(state.avoidanceNote)}</p>${items ? `<div class="nf-limit-items">${items}</div>` : ''}`;
  }

  function show(stage) {
    ['search', 'type', 'results', 'detail'].forEach(name => { el('nf-' + name).hidden = name !== stage; });
    const label = state.query.charAt(0).toLocaleUpperCase('vi-VN') + state.query.slice(1);
    document.querySelectorAll('#doctor-tab .nf-query-label').forEach(node => { node.textContent = label; });
    window.scrollTo({ top: 0, behavior: 'auto' });
  }

  function renderCards() {
    const tag = state.type === 'drink' ? 'NƯỚC UỐNG' : 'THỨC ĂN';
    el('nf-cards').innerHTML = state.recipes.map((recipe, index) => `
      <button type="button" class="nf-card" data-nf-recipe="${index}">
        <span class="nf-art"><img class="nf-food-image" src="${artwork(recipe)}" alt="" width="640" height="440" loading="lazy" decoding="async"><span class="nf-art-tag">${tag}</span></span>
        <span class="nf-card-content"><strong>${safe(recipe.title)}</strong><p>${safe(recipe.subtitle || '')}</p>
        ${recipe.recommendation_reason ? `<span class="nf-reason"><b>Vì sao gợi ý?</b>${safe(recipe.recommendation_reason)}</span>` : ''}
        <span class="nf-card-footer"><span>◷ ${safe(recipe.cooking_time || '')}</span><b>Xem chi tiết →</b></span></span>
      </button>`).join('');
  }

  function renderDetail(recipe) {
    const ingredients = (recipe.ingredients || []).map(item => `<div class="nf-ingredient"><span class="nf-ingredient-name"><span class="nf-ingredient-dot" aria-hidden="true"></span>${safe(item.name)}</span><b>${safe(item.amount)} ${safe(item.unit || '')}</b></div>`).join('');
    const steps = (recipe.steps || []).map((step, i) => `<div class="nf-step"><span class="nf-step-number">${i + 1}</span><span>${safe(step)}</span></div>`).join('');
    const avoid = (recipe.avoid || []).map(safe).join('<br>');
    el('nf-detail-content').innerHTML = `<div class="nf-detail-grid">
      <div class="nf-detail-visual"><div class="nf-art"><img class="nf-food-image" src="${artwork(recipe)}" alt="Minh họa ${safe(recipe.title)}" width="640" height="440" decoding="async"></div><p class="nf-detail-caption">◷ ${safe(recipe.cooking_time || '')} · ${state.type === 'drink' ? 'Nước uống' : 'Thức ăn'}</p></div>
      <article class="nf-detail-copy"><p class="nf-overline">${state.type === 'drink' ? 'NƯỚC UỐNG' : 'THỨC ĂN'}</p><h2>${safe(recipe.title)}</h2><p class="nf-subtitle">${safe(recipe.subtitle || '')}</p>
      ${recipe.recommendation_reason ? `<h3>Vì sao được gợi ý?</h3><div class="nf-benefit"><p>${safe(recipe.recommendation_reason)}</p>${recipe.ai_caution ? `<p class="nf-ai-caution">${safe(recipe.ai_caution)}</p>` : ''}${sourceLinks(recipe.source_ids || []) ? `<p class="nf-source-links">Hướng dẫn tham khảo: ${sourceLinks(recipe.source_ids || [])}</p>` : ''}</div>` : ''}
      <h3>Công dụng / Điểm nổi bật</h3><p class="nf-benefit">${safe(recipe.benefit || 'Thông tin dinh dưỡng đang được cập nhật.')}</p>
      <h3>Nguyên liệu · 1 khẩu phần</h3><div class="nf-ingredients">${ingredients}</div>
      <h3>Cách chế biến</h3><div class="nf-steps">${steps}</div>
      <aside class="nf-avoid"><strong>LƯU Ý CỦA CÔNG THỨC</strong>${avoid || 'Chọn thực phẩm phù hợp với tình trạng và dị ứng của bạn.'}</aside>
      <section class="nf-limit-panel nf-limit-compact">${avoidanceMarkup(true)}</section></article></div>`;
  }

  async function chooseType(type) {
    if (state.request) state.request.abort();
    const controller = new AbortController();
    state.request = controller;
    state.type = type;
    state.recipes = [];
    el('nf-results-title').textContent = type === 'drink' ? 'Các thức uống để tham khảo' : 'Các món ăn để tham khảo';
    el('nf-cards').innerHTML = '';
    el('nf-notice').hidden = true;
    el('nf-selection-info').hidden = true;
    el('nf-selection-info').open = false;
    el('nf-sources').hidden = true;
    el('nf-clarification').hidden = true;
    el('nf-avoidance').hidden = true;
    el('nf-avoidance-jump').hidden = true;
    el('nf-status').textContent = 'Đang tìm gợi ý cho bạn…';
    show('results');
    try {
      const response = await fetch('/api/nutrition/options', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ condition: state.query, recipe_type: type }), signal: controller.signal });
      const body = await response.json();
      if (!response.ok || !body.success || !Array.isArray(body.data?.recipes)) throw new Error(body.error || 'Không thể tải gợi ý.');
      if (state.request !== controller) return;
      state.recipes = body.data.recipes;
      state.sources = Array.isArray(body.data.sources) ? body.data.sources : [];
      state.avoidance = Array.isArray(body.data.avoidance) ? body.data.avoidance : [];
      state.avoidanceNote = body.data.avoidance_note || 'Chưa có danh sách kiêng riêng cho mô tả này.';
      el('nf-avoidance').innerHTML = avoidanceMarkup();
      el('nf-avoidance').hidden = false;
      el('nf-avoidance-jump').hidden = false;
      const notice = el('nf-notice');
      notice.textContent = body.data.notice || '';
      notice.hidden = !body.data.notice;
      const limitations = Array.isArray(body.data.limitations) ? body.data.limitations.join(' ') : '';
      const excluded = Array.isArray(body.data.excluded) ? body.data.excluded.map(item => `${item.title}: ${item.reason}`).join(' ') : '';
      el('nf-selection-copy').textContent = [body.data.selection_explanation || 'Danh sách tham khảo chung, chưa xác nhận mức độ phù hợp theo tình trạng của bạn.', limitations, excluded ? `Món đã loại trước khi gọi Gemini: ${excluded}` : ''].filter(Boolean).join(' ');
      el('nf-selection-info').hidden = false;
      const sources = sourceLinks(state.sources.map((_, id) => id));
      el('nf-sources').innerHTML = sources ? `Hướng dẫn được cung cấp cho bộ gợi ý: ${sources}` : '';
      el('nf-sources').hidden = !sources;
      el('nf-notice').dataset.mode = body.data.provider_status === 'ai_ranked' ? 'ai' : 'general';
      el('nf-edit-query').textContent = state.recipes.length ? 'Bổ sung để gợi ý sát hơn →' : 'Bổ sung mô tả →';
      el('nf-clarification').hidden = !body.data.needs_clarification;
      el('nf-question').textContent = body.data.clarification_question || '';
      el('nf-status').textContent = state.recipes.length || body.data.needs_clarification ? '' : 'Chưa có món phù hợp. Hãy thử tìm kiếm khác.';
      renderCards();
    } catch (error) {
      if (error.name !== 'AbortError') el('nf-status').textContent = 'Không tải được gợi ý. Hãy quay lại và thử lại.';
    } finally {
      if (state.request === controller) state.request = null;
    }
  }

  window.initNutritionStudio = function () {
    if (!el('nf-search')) return;
    if (!initialized) {
      initialized = true;
      el('nf-search-form').addEventListener('submit', event => {
        event.preventDefault();
        const query = el('nf-query').value.trim();
        if (!query) { el('nf-query').focus(); return; }
        state.query = query;
        show('type');
      });
      el('nf-edit-query').addEventListener('click', () => { show('search'); el('nf-query').focus(); });
      el('nf-avoidance-jump').addEventListener('click', () => el('nf-avoidance').scrollIntoView({ behavior: 'smooth', block: 'start' }));
      document.querySelectorAll('[data-nf-type]').forEach(button => button.addEventListener('click', () => chooseType(button.dataset.nfType)));
      document.querySelectorAll('[data-nf-back]').forEach(button => button.addEventListener('click', () => {
        if (state.request) { state.request.abort(); state.request = null; }
        show(button.dataset.nfBack);
      }));
      el('nf-cards').addEventListener('click', event => {
        const button = event.target.closest('[data-nf-recipe]');
        const recipe = button && state.recipes[Number(button.dataset.nfRecipe)];
        if (!recipe) return;
        renderDetail(recipe);
        show('detail');
      });
    }
    show('search');
  };
})();
