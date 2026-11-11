/* Search → type → options → recipe. The API supplies complete recipes. */
(() => {
  const state = { query: '', type: '', recipes: [], sources: [], avoidance: [], avoidanceNote: '', request: null };
  const el = id => document.getElementById(id);
  const safe = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const artworkIds = new Set(['oat_porridge', 'pumpkin_soup', 'rice_carrot', 'soft_egg', 'sweet_potato', 'chicken_congee', 'tofu_pumpkin', 'warm_water', 'warm_milk', 'oat_drink', 'cucumber_water', 'warm_soy', 'pear_water', 'barley_water']);
  // ponytail: keyword-based SVG mapping avoids hosting thousands of food photos. Upgrade to CDN photos when real image dataset is available.
  function matchArtwork(recipe) {
    if (recipe && recipe.id && artworkIds.has(recipe.id)) return recipe.id;
    const text = ((recipe?.title || '') + ' ' + (recipe?.display_title || '') + ' ' + (recipe?.subtitle || '') + ' ' + (recipe?.benefit || '') + ' ' + (recipe?.ingredients || []).map(i => i.name || '').join(' ')).toLowerCase();
    if (state.type === 'drink') {
      if (/đậu nành|đậu xanh|mè đen|sữa đậu|soya?/.test(text)) return 'warm_soy';
      if (/yến mạch|oat/.test(text)) return 'oat_drink';
      if (/sữa|milk|cream/.test(text)) return 'warm_milk';
      if (/dưa leo|dưa chuột|chanh|bạc hà|cucumber/.test(text)) return 'cucumber_water';
      if (/lê|táo|trái cây|hoa quả|lựu|cam|bưởi|pear|apple/.test(text)) return 'pear_water';
      if (/lúa mạch|gạo lứt|ý dĩ|thảo mộc|trà|barley/.test(text)) return 'barley_water';
      return 'warm_water';
    }
    if (/đậu hũ|đậu phụ|tàu hũ|tofu|hẹ/.test(text)) return 'tofu_pumpkin';
    if (/cháo|bổi|congee|porridge/.test(text)) {
      if (/phô mai|sữa|ngũ cốc|yến mạch|chuối/.test(text)) return 'oat_porridge';
      if (/cà rốt|khoai tây|củ dền|rau củ/.test(text)) return 'rice_carrot';
      return 'chicken_congee';
    }
    if (/bí đỏ|súp bí|pumpkin/.test(text)) return 'pumpkin_soup';
    if (/trứng|hấp trứng|egg/.test(text)) return 'soft_egg';
    if (/khoai lang|khoai môn|khoai sọ|sweet potato/.test(text)) return 'sweet_potato';
    if (/cà rốt|khoai tây|súp|canh|rau củ|mọc|thịt bằm|hầm/.test(text)) return 'rice_carrot';
    if (/yến mạch|oat/.test(text)) return 'oat_porridge';
    return 'category-food';
  }
  function artwork(recipe) {
    if (recipe.source_image_url && (recipe.source_image_url.startsWith('/static/') || recipe.source_image_url.startsWith('http'))) {
      return recipe.source_image_url;
    }
    return fallbackArtwork(recipe);
  }
  function fallbackArtwork(recipe) { return `/static/images/nutrition/${matchArtwork(recipe)}.svg?v=2`; }
  function imageLabel(recipe) {
    if (artwork(recipe).includes('.svg') || artwork(recipe) === fallbackArtwork(recipe)) return 'Minh họa nhóm món';
    if (recipe.image_match_method === 'approximate_title_match') return 'Ảnh tham khảo · cần kiểm tra';
    return ['exact_normalized_title', 'reference_title_match'].includes(recipe.image_match_method) ? 'Ảnh tham khảo cùng tên món' : 'Ảnh từ nguồn dữ liệu';
  }
  function recipeImage(recipe) {
    const src = artwork(recipe), fallback = fallbackArtwork(recipe);
    return `<img class="nf-food-image" src="${safe(src)}" data-fallback="${safe(fallback)}" alt="${safe(recipe.title)}" width="640" height="440" loading="lazy" decoding="async" onerror="this.onerror=null;this.src=this.dataset.fallback;const note=this.parentElement.querySelector('.nf-art-note');if(note)note.textContent='Minh họa nhóm món'">`;
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

  function recipeSourceUrl(value) {
    try {
      const url = new URL(value);
      if (url.protocol !== 'https:' || url.username || url.password || (url.port && url.port !== '443')) return '';
      const host = url.hostname.toLowerCase();
      if (host === 'kingfoodmart.com' && url.pathname.startsWith('/bai-viet/cong-thuc-nau-an/')) return url.href;
      if (host === 'banhcanhcualinh.com' && url.pathname === '/banh-canh-cua-hai-san') return url.href;
      if (host === 'phucgiaan.com' && url.pathname === '/') return url.href;
      if (host === 'phacheviet.com' && url.pathname === '/blogs/cong-thuc/cong-thuc-pha-che-tra-dao') return url.href;
      if (host === 'naungon.com' && url.pathname === '/index.php' && url.searchParams.has('id')) return url.href;
      if (host === 'nhathuoclongchau.com.vn' && url.pathname === '/bai-viet/sua-hat-chia-co-tac-dung-gi-cach-lam-sua-hat-chia-ngon-va-bo.html') return url.href;
      if (host === 'www.thatlangon.com' && url.pathname === '/cong-thuc/cach-lam-sua-bap/') return url.href;
      if (host === 'cathuonghang.com' && url.pathname === '/mon-ngon-tu-ca/246-mon-an-an-healhy-ca-tam-nuong-rau-cu-day-du-duong-chat.html') return url.href;
      if (host === 'dienmaycholon.com' && url.pathname === '/mon-ngon/cach-nau-che-khoai-lang') return url.href;
      const recipeHosts = new Set(['en.wikibooks.org', 'monngonmoingay.com', 'www.monngonmoingay.com', 'cooky.vn', 'www.cooky.vn']);
      if (recipeHosts.has(host)) return url.href;
      const repository = '/quocan55/a-new-dataset-and-empirical-evaluation-for-vietnamese-food-recommendation-system';
      const path = url.pathname.toLowerCase();
      if (host === 'github.com' && (path === repository || path.startsWith(repository + '/'))) return url.href;
    } catch (_) { /* Only known source hosts can become recipe credit links. */ }
    return '';
  }

  function recipeCredit(recipe) {
    if (!recipe.imported) return '';
    const provider = recipe.source_provider || 'Nguồn công thức';
    const sourceUrl = recipeSourceUrl(recipe.revision_url || recipe.source_url);
    const datasetUrl = recipeSourceUrl(recipe.dataset_url);
    const imageSource = recipeSourceUrl(recipe.image_source_page);
    const sourceLabel = sourceUrl.startsWith('https://github.com/') ? 'Kho dữ liệu nghiên cứu' : recipe.source_title || recipe.title;
    const source = sourceUrl ? `<a href="${safe(sourceUrl)}" target="_blank" rel="noopener noreferrer">${safe(sourceLabel)}</a>` : safe(recipe.source_title || recipe.title);
    const attribution = recipe.source_attribution || recipe.attribution || (provider === 'Wikibooks Cookbook' ? 'Wikibooks contributors' : provider === 'ViFoodRec' ? 'Nhóm tác giả ViFoodRec' : '');
    const license = recipe.license === 'CC-BY-SA-4.0' || recipe.license === 'CC BY-SA 4.0'
      ? 'Giấy phép <a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" rel="noopener noreferrer">CC BY-SA 4.0</a>.'
      : 'Kho dữ liệu chưa công bố giấy phép tái sử dụng.';
    const language = recipe.language === 'vi'
      ? 'Nguyên liệu và cách làm theo bản tiếng Việt của nguồn dữ liệu.'
      : `Nguyên liệu và cách làm giữ bản gốc tiếng Anh.${recipe.display_title && recipe.display_title !== recipe.title ? ' Tên món được dịch tự động.' : ''}`;
    return `<div class="nf-recipe-credit">Nguồn: ${safe(provider)} · ${source}<br>${safe(attribution)}${datasetUrl && datasetUrl !== sourceUrl ? ` · <a href="${safe(datasetUrl)}" target="_blank" rel="noopener noreferrer">Kho dữ liệu</a>` : ''}${imageSource ? `<br>Ảnh tham khảo cùng tên món: <a href="${safe(imageSource)}" target="_blank" rel="noopener noreferrer">${safe(new URL(imageSource).hostname)}</a>` : ''}<br>${license} ${language}<br>Nhãn nguyên liệu được quét tự động; chưa được xác minh y khoa cho từng món.</div>`;
  }

  function renderCards() {
    const tag = state.type === 'drink' ? 'NƯỚC UỐNG' : 'THỨC ĂN';
    el('nf-cards').innerHTML = state.recipes.map((recipe, index) => `
      <button type="button" class="nf-card" data-nf-recipe="${index}">
        <span class="nf-art">${recipeImage(recipe)}<span class="nf-art-tag">${tag}</span>${recipe.imported ? `<span class="nf-art-note">${imageLabel(recipe)}</span>` : ''}</span>
        <span class="nf-card-content"><strong>${safe(recipe.display_title || recipe.title)}</strong><p>${safe(recipe.subtitle || '')}</p>
        ${recipe.imported ? `<span class="nf-import-label">Nguồn: ${safe(recipe.source_provider || 'Nguồn công thức')}</span>` : ''}
        ${recipe.recommendation_reason ? `<span class="nf-reason"><span class="nf-reason-header"><svg viewBox="0 0 20 20" fill="currentColor" width="12" height="12" aria-hidden="true"><path d="M11 3a1 1 0 10-2 0v1a1 1 0 102 0V3zM15.657 5.757a1 1 0 00-1.414-1.414l-.707.707a1 1 0 001.414 1.414l.707-.707zM18 10a1 1 0 01-1 1h-1a1 1 0 110-2h1a1 1 0 011 1zM5.05 6.464A1 1 0 106.464 5.05l-.707-.707a1 1 0 00-1.414 1.414l.707.707zM5 10a1 1 0 01-1 1H3a1 1 0 110-2h1a1 1 0 011 1zM8 16v-1h4v1a2 2 0 11-4 0zM12 14H8a4 4 0 01-.8-7.92 4.002 4.002 0 017.6 0A4 4 0 0112 14z"/></svg> Vì sao gợi ý?</span><span class="nf-reason-text">${safe(recipe.recommendation_reason)}</span></span>` : ''}
        <span class="nf-card-footer"><span>◷ ${safe(recipe.cooking_time || '')}</span><b>Xem chi tiết →</b></span></span>
      </button>`).join('');
  }

  function renderDetail(recipe) {
    const ingredients = (recipe.ingredients || []).map(item => `<div class="nf-ingredient"><span class="nf-ingredient-name"><span class="nf-ingredient-dot" aria-hidden="true"></span>${safe(item.name)}</span><b>${safe(item.amount)} ${safe(item.unit || '')}</b></div>`).join('');
    const steps = (recipe.steps || []).map((step, i) => `<div class="nf-step"><span class="nf-step-number">${i + 1}</span><span>${safe(step)}</span></div>`).join('');
    const avoid = (recipe.avoid || []).map(safe).join('<br>');
    el('nf-detail-content').innerHTML = `<div class="nf-detail-grid">
      <div class="nf-detail-visual"><div class="nf-art">${recipeImage(recipe)}${recipe.imported ? `<span class="nf-art-note">${imageLabel(recipe)}</span>` : ''}</div><p class="nf-detail-caption">◷ ${safe(recipe.cooking_time || '')} · ${state.type === 'drink' ? 'Nước uống' : 'Thức ăn'}</p></div>
      <article class="nf-detail-copy"><p class="nf-overline">${state.type === 'drink' ? 'NƯỚC UỐNG' : 'THỨC ĂN'}</p><h2>${safe(recipe.display_title || recipe.title)}</h2><p class="nf-subtitle">${safe(recipe.subtitle || '')}</p>${recipeCredit(recipe)}
      ${recipe.recommendation_reason ? `<div class="nf-recommendation-box"><div class="nf-recommendation-head"><span class="nf-recommendation-badge"><svg viewBox="0 0 20 20" fill="currentColor" width="13" height="13" aria-hidden="true"><path fill-rule="evenodd" d="M6.267 3.455a3.066 3.066 0 001.745-.723 3.066 3.066 0 013.976 0 3.066 3.066 0 001.745.723 3.066 3.066 0 012.812 2.812c.051.643.304 1.254.723 1.745a3.066 3.066 0 010 3.976 3.066 3.066 0 00-.723 1.745 3.066 3.066 0 01-2.812 2.812 3.066 3.066 0 00-1.745.723 3.066 3.066 0 01-3.976 0 3.066 3.066 0 00-1.745-.723 3.066 3.066 0 01-2.812-2.812 3.066 3.066 0 00-.723-1.745 3.066 3.066 0 010-3.976 3.066 3.066 0 00.723-1.745 3.066 3.066 0 012.812-2.812zm7.44 5.252a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/></svg> Vì sao được gợi ý?</span></div><p class="nf-recommendation-desc">${safe(recipe.recommendation_reason)}</p>${recipe.ai_caution ? `<p class="nf-ai-caution">${safe(recipe.ai_caution)}</p>` : ''}${sourceLinks(recipe.source_ids || []) ? `<p class="nf-source-links">Hướng dẫn tham khảo: ${sourceLinks(recipe.source_ids || [])}</p>` : ''}</div>` : ''}
      <h3>Công dụng / Điểm nổi bật</h3><p class="nf-benefit">${safe(recipe.benefit || 'Thông tin dinh dưỡng đang được cập nhật.')}</p>
      <h3>Nguyên liệu · ${recipe.imported ? (recipe.servings ? 'Khẩu phần theo nguồn: ' + safe(recipe.servings) : 'Theo công thức gốc') : '1 khẩu phần'}</h3><div class="nf-ingredients">${ingredients}</div>
      <h3>Cách chế biến</h3><div class="nf-steps">${steps}</div>
      <aside class="nf-avoid"><strong>LƯU Ý CỦA CÔNG THỨC</strong>${avoid || 'Chọn thực phẩm phù hợp với tình trạng và dị ứng của bạn.'}</aside>
      <section class="nf-limit-panel nf-limit-compact">${avoidanceMarkup(true)}</section></article></div>`;
  }

  async function chooseType(type, append = false) {
    if (state.request) state.request.abort();
    const controller = new AbortController();
    state.request = controller;
    state.type = type;
    const previous = append ? state.recipes.slice() : [];
    if (!append) state.recipes = [];
    el('nf-results-title').textContent = type === 'drink' ? 'Các thức uống để tham khảo' : 'Các món ăn để tham khảo';
    if (!append) el('nf-cards').innerHTML = '';
    el('nf-load-more').disabled = true;
    if (!append) el('nf-load-more').hidden = true;
    el('nf-notice').hidden = true;
    el('nf-selection-info').hidden = true;
    el('nf-selection-info').open = false;
    el('nf-sources').hidden = true;
    el('nf-clarification').hidden = true;
    el('nf-avoidance').hidden = true;
    el('nf-avoidance-jump').hidden = true;
    el('nf-catalog-stats').hidden = true;
    el('nf-status').textContent = 'Đang tìm gợi ý cho bạn…';
    if (!append) show('results');
    try {
      const response = await fetch('/api/nutrition/options', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ condition: state.query, recipe_type: type, exclude_recipe_ids: previous.map(recipe => recipe.id) }), signal: controller.signal });
      const body = await response.json();
      if (!response.ok || !body.success || !Array.isArray(body.data?.recipes)) throw new Error(body.error || 'Không thể tải gợi ý.');
      if (state.request !== controller) return;
      const incoming = body.data.recipes.filter(recipe => !previous.some(old => old.id === recipe.id));
      state.recipes = previous.concat(incoming);
      el('nf-load-more').hidden = !body.data.has_more;
      state.sources = Array.isArray(body.data.sources) ? body.data.sources : [];
      state.avoidance = Array.isArray(body.data.avoidance) ? body.data.avoidance : [];
      state.avoidanceNote = body.data.avoidance_note || 'Chưa có danh sách kiêng riêng cho mô tả này.';
      const stats = body.data.catalog;
      el('nf-catalog-stats').textContent = stats ? `${stats.cuisine === 'VN' ? 'Kho món Việt' : 'Kho dữ liệu'}${stats.source ? ' · ' + stats.source : ''}: ${stats.total} công thức · ${body.data.catalog_type_count} ${type === 'drink' ? 'nước uống' : 'món ăn'} · ${body.data.eligible_count} qua bộ lọc · ${body.data.considered_count} ứng viên gửi Gemini` : '';
      el('nf-catalog-stats').hidden = !stats;
      el('nf-avoidance').innerHTML = avoidanceMarkup();
      el('nf-avoidance').hidden = false;
      el('nf-avoidance-jump').hidden = false;
      const notice = el('nf-notice');
      notice.textContent = (append && incoming.length ? `Đã thêm ${incoming.length} gợi ý mới. ` : '') + (body.data.notice || '');
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
      el('nf-load-more').disabled = false;
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
      el('nf-load-more').addEventListener('click', () => chooseType(state.type, true));
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
