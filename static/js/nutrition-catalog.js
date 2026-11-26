/* Browse the bundled Mon Ngon Moi Ngay catalog without changing clinical recommendations. */
(() => {
  const $ = id => document.getElementById(id);
  const safe = value => String(value ?? '').replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[char]);
  const state = { page: 1, objective: 'all', timer: null, request: null, activeRecipe: null };
  const pageSize = 18;
  const healthTags = ['Ăn kiêng', 'Giảm khối mỡ thừa của cơ thể', 'Cân bằng dinh dưỡng', 'Ăn chay', 'Tăng năng lượng', 'Tốt cho xương', 'Tốt cho da', 'Hỗ trợ miễn dịch', 'Hỗ trợ xây dựng khối cơ xương', 'Giúp làm việc trí não hiệu quả', 'Hồi phục sau cảm'];
  const placeholder = '/static/images/nutrition/category-food.svg';
  const isEn = () => typeof currentLang !== 'undefined' && currentLang === 'en';
  const _t = (vi, en) => (isEn() ? en : vi);
  const kcalText = value => Number(value).toLocaleString(isEn() ? 'en-US' : 'vi-VN');
  const DIFFICULTY_EN = { 'dễ': 'Easy', 'trung bình': 'Medium', 'khó': 'Hard', 'rất khó': 'Very hard', 'chưa rõ': 'Unknown' };
  const trDifficulty = value => {
    const raw = String(value || '').trim();
    if (!raw) return _t('Chưa rõ', 'Unknown');
    return isEn() ? (DIFFICULTY_EN[raw.toLocaleLowerCase('vi')] || raw) : raw;
  };
  const trTime = value => {
    const raw = String(value || '').trim();
    if (!isEn()) return raw;
    return raw.replace(/\bPhút\b/gi, 'min').replace(/\bGiờ\b/gi, 'h').replace(/\bGiây\b/gi, 's');
  };
  const servingText = people => (people ? _t(`${people} người`, `${people} ${people > 1 ? 'servings' : 'serving'}`) : _t('Theo công thức', 'Per recipe'));
  let lastPage = { current: 1, pages: 0 };
  let lastCounts = null;
  const imageFor = recipe => recipe.image_ok && recipe.hinh_anh && !/no-image\.jpg(?:$|\?)/i.test(recipe.hinh_anh) ? recipe.hinh_anh : placeholder;
  const servingCount = recipe => {
    const match = String(recipe.khau_phan || '').match(/\b(\d+)\s*người\b/i);
    return match ? Math.max(1, Number(match[1])) : null;
  };
  const tagsForCard = tags => {
    const rank = tag => healthTags.some(health => health.toLocaleLowerCase('vi') === tag.toLocaleLowerCase('vi')) ? 0 : /bữa sáng|bữa trưa|bữa tối|ăn vặt/i.test(tag) ? 1 : 2;
    return [...new Set(tags || [])].sort((a, b) => rank(a) - rank(b)).slice(0, 3);
  };
  const foodHeading = line => {
    const clean = String(line).trim().replace(/^\*/, '');
    const letters = clean.replace(/[^\p{L}]/gu, '');
    return /^\*/.test(line) || /:$/.test(clean) || (letters.length > 1 && letters === letters.toLocaleUpperCase('vi'));
  };

  function setCatalogVisible(visible) {
    const ids = ['nf-search', 'nf-type', 'nf-results', 'nf-detail', 'nf-catalog', 'nf-evidence'];
    ids.forEach(id => {
      const section = $(id);
      if (section) section.hidden = visible ? id !== 'nf-catalog' : id !== 'nf-search';
    });
    $('doctor-tab')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    if (visible) loadRecipes();
  }

  function filters() {
    const kcal = $('nf-catalog-kcal')?.value || 'all';
    const ranges = { under1000: [0, 999], '1000to2500': [1000, 2500], '2500to4000': [2501, 4000], over4000: [4001, 1000000] };
    const [kcal_min, kcal_max] = ranges[kcal] || [0, 1000000];
    const params = new URLSearchParams({ page: String(state.page), per_page: String(pageSize), q: $('nf-catalog-query')?.value || '', objective: state.objective, meal: $('nf-catalog-meal')?.value || 'all', method: $('nf-catalog-method')?.value || 'all', kcal_min: String(kcal_min), kcal_max: String(kcal_max), sort: $('nf-catalog-sort')?.value || 'relevance' });
    $('nf-catalog-excludes')?.querySelectorAll('input:checked').forEach(input => params.append('exclude', input.value));
    return params;
  }

  function renderCount() {
    const count = $('nf-catalog-count');
    if (!count) return;
    if (!lastCounts) { count.textContent = lastCounts === false ? _t('Chưa tải được danh mục', 'Catalog unavailable') : _t('Đang tải…', 'Loading…'); return; }
    count.textContent = _t(
      `${kcalText(lastCounts.total)} món phù hợp · ${kcalText(lastCounts.catalogTotal)} công thức`,
      `${kcalText(lastCounts.total)} matching dishes · ${kcalText(lastCounts.catalogTotal)} recipes`
    );
  }

  async function loadRecipes() {
    if (state.request) state.request.abort();
    const controller = new AbortController();
    state.request = controller;
    $('nf-catalog-grid').innerHTML = `<div class="nf-catalog-loading">${_t('Đang tìm công thức phù hợp…', 'Finding matching recipes…')}</div>`;
    $('nf-catalog-empty').hidden = true;
    try {
      const response = await fetch(`/api/nutrition/recipe-catalog?${filters()}`, { signal: controller.signal, headers: { Accept: 'application/json' } });
      if (!response.ok) throw new Error('catalog');
      const data = await response.json();
      if (state.request !== controller) return;
      lastCounts = { total: Number(data.total || 0), catalogTotal: Number(data.catalog_total || 0) };
      renderCount();
      $('nf-catalog-grid').innerHTML = (data.items || []).map(cardMarkup).join('');
      $('nf-catalog-empty').hidden = Boolean((data.items || []).length);
      renderPages(data.page || 1, data.pages || 0);
    } catch (error) {
      if (error.name === 'AbortError') return;
      lastCounts = false;
      renderCount();
      $('nf-catalog-grid').innerHTML = `<div class="nf-catalog-loading">${_t('Không thể tải công thức. Vui lòng thử lại.', 'Unable to load recipes. Please try again.')}</div>`;
      $('nf-catalog-pages').innerHTML = '';
    } finally {
      if (state.request === controller) state.request = null;
    }
  }

  function cardMarkup(recipe) {
    const people = servingCount(recipe);
    const tags = tagsForCard(recipe.tags);
    const time = String(recipe.thoi_gian_thuc_hien || '').trim() === '0 Phút' ? _t('Linh hoạt', 'Flexible') : (trTime(recipe.thoi_gian_thuc_hien) || _t('Chưa rõ thời gian', 'Time not specified'));
    const serving = servingText(people);
    return `<article class="nf-recipe-card">
      <div class="nf-recipe-photo"><img src="${safe(imageFor(recipe))}" alt="${safe(recipe.ten_mon)}" loading="lazy" decoding="async" onerror="this.onerror=null;this.src='${placeholder}'"><span class="nf-recipe-kcal">~${kcalText(recipe.kcal || 0)} kcal<small>${_t('Tổng cả món', 'Whole dish')}</small></span></div>
      <div class="nf-recipe-card-body"><h2>${safe(recipe.ten_mon)}</h2><div class="nf-recipe-meta"><span>◷ ${safe(time)}</span><span>✳ ${safe(trDifficulty(recipe.do_kho))}</span><span>♧ ${safe(serving)}</span></div>
      ${people ? `<p class="nf-per-person">~${kcalText(Math.round(Number(recipe.kcal || 0) / people))} ${_t('kcal/người · ước tính theo khẩu phần', 'kcal/serving · portion estimate')}</p>` : ''}
      <div class="nf-recipe-tags">${tags.map(tag => `<span class="${healthTags.includes(tag) ? 'health' : ''}">${safe(tag)}</span>`).join('')}</div>
      <button class="nf-recipe-open" type="button" data-recipe-id="${safe(recipe.id)}">${_t('Xem công thức &amp; Dinh dưỡng', 'View recipe &amp; nutrition')} <span aria-hidden="true">→</span></button></div>
      <script type="application/json" class="nf-recipe-data">${JSON.stringify(recipe).replace(/</g, '\\u003c')}</script>
    </article>`;
  }

  function renderPages(current, pages) {
    lastPage = { current, pages };
    const nav = $('nf-catalog-pages');
    if (!pages || pages < 2) { nav.innerHTML = ''; return; }
    const start = Math.max(1, Math.min(current - 2, pages - 4));
    const end = Math.min(pages, start + 4);
    nav.innerHTML = `<button type="button" data-page="${current - 1}" ${current === 1 ? 'disabled' : ''}>${_t('← Trước', '← Prev')}</button>${Array.from({ length: end - start + 1 }, (_, i) => start + i).map(page => `<button type="button" data-page="${page}" class="${page === current ? 'active' : ''}" aria-current="${page === current ? 'page' : 'false'}">${page}</button>`).join('')}<button type="button" data-page="${current + 1}" ${current === pages ? 'disabled' : ''}>${_t('Tiếp →', 'Next →')}</button>`;
  }

  function detailMarkup(recipe) {
    const people = servingCount(recipe);
    const time = String(recipe.thoi_gian_thuc_hien || '').trim() === '0 Phút' ? _t('Linh hoạt', 'Flexible') : (trTime(recipe.thoi_gian_thuc_hien) || _t('Chưa rõ', 'Unknown'));
    const tags = (recipe.tags || []).map(tag => `<span class="${healthTags.includes(tag) ? 'health' : ''}">${safe(tag)}</span>`).join('');
    const ingredients = (recipe.nguyen_lieu || []).map((item, index) => foodHeading(item)
      ? `<h4 class="nf-ingredient-heading">${safe(String(item).replace(/^\*/, ''))}</h4>`
      : `<label class="nf-ingredient-check"><input type="checkbox" data-ingredient="${index}"><span>${safe(item)}</span></label>`).join('');
    const steps = (label, items) => items?.length ? `<section class="nf-detail-section"><h3>${label}</h3><ol class="nf-recipe-steps">${items.map(step => `<li>${safe(step)}</li>`).join('')}</ol></section>` : '';
    return `<div class="nf-drawer-hero"><img src="${safe(imageFor(recipe))}" alt="${safe(recipe.ten_mon)}" onerror="this.onerror=null;this.src='${placeholder}'"><div><span class="nf-overline">${_t('CÔNG THỨC MÓN VIỆT', 'VIETNAMESE RECIPE')}</span><h2 id="nf-drawer-title">${safe(recipe.ten_mon)}</h2><div class="nf-recipe-tags">${tags}</div></div></div>
      <div class="nf-drawer-stats"><div><strong>~${kcalText(recipe.kcal || 0)}</strong><span>${_t('Tổng calo cả món', 'Total dish calories')}</span></div>${people ? `<div><strong>~${kcalText(Math.round(Number(recipe.kcal || 0) / people))}</strong><span>${_t('kcal/người (ước tính)', 'kcal/serving (est.)')}</span></div>` : ''}<div><strong>${safe(time)}</strong><span>${_t('Thời gian', 'Time')}</span></div><div><strong>${safe(trDifficulty(recipe.do_kho))}</strong><span>${_t('Độ khó', 'Difficulty')}</span></div><div><strong>${safe(servingText(people))}</strong><span>${_t('Khẩu phần', 'Servings')}</span></div>${recipe.protein != null ? `<div><strong>${safe(recipe.protein)}g</strong><span>${_t('Đạm (Protein)', 'Protein')}</span></div>` : ''}${recipe.carbs != null ? `<div><strong>${safe(recipe.carbs)}g</strong><span>${_t('Tinh bột (Carbs)', 'Carbs')}</span></div>` : ''}${recipe.fat != null ? `<div><strong>${safe(recipe.fat)}g</strong><span>${_t('Chất béo (Fat)', 'Fat')}</span></div>` : ''}</div>
      <section class="nf-detail-section"><div class="nf-section-title"><h3>${_t('Nguyên liệu &amp; gia vị', 'Ingredients &amp; seasonings')}</h3><span>${_t('Chạm để đánh dấu khi chuẩn bị', 'Tap to check off while preparing')}</span></div><div class="nf-recipe-ingredients">${ingredients || `<p>${_t('Chưa có danh sách nguyên liệu.', 'No ingredient list available.')}</p>`}</div></section>
      ${steps(_t('Sơ chế', 'Preparation'), recipe.so_che)}${steps(_t('Thực hiện', 'Cooking steps'), recipe.thuc_hien)}
      <div class="nf-drawer-footer">${recipe.source_ok && recipe.url ? `<a class="nf-recipe-source-link" href="${safe(recipe.url)}" target="_blank" rel="noopener noreferrer">${_t('Mở công thức gốc ↗', 'Open original recipe ↗')}</a>` : ''}<span>${_t('Kcal và tag là số liệu tham khảo từ nguồn công thức, chưa được thẩm định lâm sàng.', 'Kcal and tags are reference values from the recipe source and have not been clinically validated.')}</span></div>`;
  }

  function normalizeMealRecipe(recipe) {
    const ingredients = Array.isArray(recipe?.nguyen_lieu) ? recipe.nguyen_lieu : (recipe?.ingredients || []);
    const ingredientLines = ingredients.map(item => {
      if (typeof item === 'string') return item;
      const name = item?.name || item?.title || '';
      const amount = [item?.amount, item?.unit].filter(Boolean).join(' ');
      return [name, amount].filter(Boolean).join(' ');
    }).filter(Boolean);
    const allSteps = Array.isArray(recipe?.steps) ? recipe.steps : [];
    const prepSteps = Array.isArray(recipe?.preparation_steps) ? recipe.preparation_steps : (recipe?.so_che || []);
    const cookingSteps = Array.isArray(recipe?.thuc_hien)
      ? recipe.thuc_hien
      : allSteps.filter(step => !/^sơ chế\s*:/i.test(String(step)));
    const image = recipe?.hinh_anh || recipe?.source_image_url || recipe?.image_link || '';
    const sourceUrl = recipe?.url || recipe?.source_url || recipe?.revision_url || '';
    let sourceOk = false;
    try {
      const parsed = new URL(sourceUrl);
      sourceOk = parsed.protocol === 'https:' && !parsed.username && !parsed.password;
    } catch (_) { /* No external source link for recipes without a valid HTTPS URL. */ }
    return {
      id: recipe?.id,
      ten_mon: recipe?.ten_mon || recipe?.display_title || recipe?.title || recipe?.name || _t('Công thức món ăn', 'Recipe'),
      hinh_anh: image,
      image_ok: Boolean(image),
      tags: recipe?.tags || recipe?.categories || [],
      kcal: recipe?.per_person_calories ?? recipe?.total_calories ?? recipe?.calories ?? recipe?.kcal ?? 0,
      protein: recipe?.protein ?? null,
      fat: recipe?.fat ?? null,
      carbs: recipe?.carbs ?? null,
      khau_phan: recipe?.servings || recipe?.khau_phan || '',
      thoi_gian_thuc_hien: recipe?.cooking_time || recipe?.thoi_gian_thuc_hien || '',
      do_kho: recipe?.difficulty || recipe?.do_kho || '',
      nguyen_lieu: ingredientLines,
      so_che: prepSteps,
      thuc_hien: cookingSteps,
      url: sourceUrl,
      source_ok: sourceOk,
    };
  }

  window.openNutritionRecipePopup = function (recipe) {
    const drawer = $('nf-recipe-drawer');
    const content = $('nf-drawer-content');
    if (!drawer || !content || !recipe) return false;
    if (drawer.parentElement !== document.body) document.body.appendChild(drawer);
    const normalized = normalizeMealRecipe(recipe);
    content.innerHTML = detailMarkup(normalized);
    state.activeRecipe = normalized;
    drawer.hidden = false;
    document.body.classList.add('nf-drawer-open');
    drawer.querySelector('.nf-drawer-panel')?.focus();
    return true;
  };

  function init() {
    if (!$('nf-catalog')) return;
    $('nf-open-catalog')?.addEventListener('click', () => {
      const profileAllergies = $('p-allergies')?.value || window.currentUser?.allergies || '';
      if (profileAllergies) {
        const normalizedProfile = String(profileAllergies).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('vi').replace(/đ/g, 'd');
        const matches = { 'Tôm': ['tom'], 'Hải sản': ['hai san', 'tom', 'cua', 'ghe', 'ca', 'muc', 'bach tuoc', 'so', 'ngheu', 'hen', 'oc', 'hau'], 'Trứng': ['trung'], 'Thịt bò': ['thit bo', 'bo'], 'Đậu phộng': ['dau phong', 'lac'], 'Phô mai / Sữa': ['pho mai', 'sua', 'bo sua', 'kem tuoi'], 'Nấm': ['nam'] };
        $('nf-catalog-excludes').querySelectorAll('input').forEach(input => {
          const words = matches[input.value] || [];
          if (words.some(word => new RegExp(`(?:^|[^a-z])${word.replace(/ /g, '\\s+')}($|[^a-z])`).test(normalizedProfile))) input.checked = true;
        });
      }
      setCatalogVisible(true);
    });
    $('nf-catalog-back')?.addEventListener('click', () => setCatalogVisible(false));
    const reload = () => { state.page = 1; loadRecipes(); };
    $('nf-catalog-query')?.addEventListener('input', () => { clearTimeout(state.timer); state.timer = setTimeout(reload, 250); });
    ['nf-catalog-meal', 'nf-catalog-method', 'nf-catalog-kcal', 'nf-catalog-sort'].forEach(id => $(id)?.addEventListener('change', reload));
    $('nf-catalog-objectives')?.addEventListener('click', event => {
      const button = event.target.closest('[data-objective]');
      if (!button) return;
      state.objective = button.dataset.objective;
      $('nf-catalog-objectives').querySelectorAll('button').forEach(item => item.classList.toggle('active', item === button));
      reload();
    });
    $('nf-catalog-excludes')?.addEventListener('change', reload);
    $('nf-catalog-reset')?.addEventListener('click', () => {
      $('nf-catalog-query').value = '';
      ['nf-catalog-meal', 'nf-catalog-method', 'nf-catalog-kcal', 'nf-catalog-sort'].forEach(id => { $(id).selectedIndex = 0; });
      $('nf-catalog-excludes').querySelectorAll('input').forEach(input => { input.checked = false; });
      state.objective = 'all';
      $('nf-catalog-objectives').querySelectorAll('button').forEach(button => button.classList.toggle('active', button.dataset.objective === 'all'));
      reload();
    });
    $('nf-catalog-pages')?.addEventListener('click', event => {
      const button = event.target.closest('[data-page]');
      if (!button || button.disabled) return;
      state.page = Number(button.dataset.page);
      loadRecipes();
      $('nf-catalog-title').scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
    $('nf-catalog-grid')?.addEventListener('click', event => {
      const button = event.target.closest('[data-recipe-id]');
      if (!button) return;
      const dataNode = button.closest('.nf-recipe-card')?.querySelector('.nf-recipe-data');
      try {
        state.activeRecipe = JSON.parse(dataNode.textContent);
        $('nf-drawer-content').innerHTML = detailMarkup(state.activeRecipe);
        $('nf-recipe-drawer').hidden = false;
        document.body.classList.add('nf-drawer-open');
        $('nf-recipe-drawer').querySelector('.nf-drawer-panel').focus();
      } catch (_) { /* Ignore malformed card data and keep the catalog usable. */ }
    });
    $('nf-recipe-drawer')?.addEventListener('click', event => {
      if (event.target.closest('[data-drawer-close]')) {
        $('nf-recipe-drawer').hidden = true;
        document.body.classList.remove('nf-drawer-open');
        state.activeRecipe = null;
      }
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' && $('nf-recipe-drawer') && !$('nf-recipe-drawer').hidden) {
        $('nf-recipe-drawer').hidden = true;
        document.body.classList.remove('nf-drawer-open');
      }
    });
    // Re-render dynamic catalog copy when the user switches VI/EN
    window.addEventListener('medimind:langchange', () => {
      renderCount();
      const catalog = $('nf-catalog');
      if (catalog && !catalog.hidden && $('nf-catalog-grid')?.children.length) loadRecipes();
      else renderPages(lastPage.current, lastPage.pages);
      const drawer = $('nf-recipe-drawer');
      if (drawer && !drawer.hidden && state.activeRecipe) $('nf-drawer-content').innerHTML = detailMarkup(state.activeRecipe);
    });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true }); else init();
})();
