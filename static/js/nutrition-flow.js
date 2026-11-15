/* Search → type → options → recipe. The API supplies complete recipes. */
(() => {
  const state = { query: '', type: '', stage: 'search', activeRecipe: null, lastData: null, lastAddedCount: 0, recipes: [], sources: [], avoidance: [], avoidanceNote: '', request: null };
  const el = id => document.getElementById(id);
  const safe = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const _isEn = () => typeof currentLang !== 'undefined' && currentLang === 'en';
  const _t = (vi, en) => (_isEn() ? en : vi);

  // ponytail: translates standardized backend recipe metadata/notices in EN mode without altering canonical Vietnamese recipe ingredients or backend API contracts.
  const _SUBTITLE_EN = {
    'Công thức tiếng Việt · ViFoodRec': 'Vietnamese Recipe · ViFoodRec',
    'Món Việt chọn lọc · công thức tiếng Việt': 'Selected Vietnamese Dish · Vietnamese Recipe',
    'Công thức Wikibooks · bản gốc tiếng Anh': 'Wikibooks Cookbook · Original English Recipe',
    'Món mềm, dễ chuẩn bị': 'Soft texture, easy to prepare',
    'Bí đỏ nấu mềm, vị nhẹ': 'Soft-cooked pumpkin, mild flavor',
    'Cháo nấu nhừ, đơn giản': 'Well-cooked rice porridge, simple',
    'Bữa ăn nhẹ giàu đạm': 'Light, protein-rich dish',
    'Khoai hấp mềm, vị ngọt tự nhiên': 'Steamed sweet potato, naturally sweet',
    'Cháo nấu nhừ với thịt gà': 'Soft rice congee with shredded chicken',
    'Đậu hũ và bí đỏ hấp mềm': 'Soft steamed silken tofu and pumpkin',
    'Một ly nước đơn giản': 'A simple glass of warm water',
    'Sữa làm ấm nhẹ': 'Gently warmed milk',
    'Vị yến mạch nhẹ': 'Mild unsweetened oat drink',
    'Nước lọc có hương nhẹ': 'Lightly infused cucumber water',
    'Sữa đậu nành không đường': 'Unsweetened warm soy milk',
    'Nước nấu cùng lê, vị dịu': 'Gently simmered pear water',
    'Nước lúa mạch nấu nhạt': 'Mildly brewed barley water'
  };
  const _AVOID_TITLE_EN = {
    'Rượu, bia và đồ uống có cồn': 'Alcoholic beverages (beer, wine, spirits)',
    'Món cay, mặn hoặc chua': 'Spicy, salty, or acidic foods',
    'Món cứng, giòn hoặc thô ráp': 'Hard, crunchy, or rough-textured foods',
    'Đồ ăn, thức uống quá nóng': 'Very hot foods and beverages',
    'Cà phê, trà và đồ uống chứa caffeine': 'Coffee, tea, and caffeinated drinks',
    'Rượu, bia gần giờ ngủ': 'Alcohol close to bedtime',
    'Bữa ăn lớn muộn vào buổi tối': 'Large meals late at night',
    'Món cay, chua hoặc nhiều chất béo': 'Spicy, acidic, or high-fat foods',
    'Cà phê/caffeine, rượu và chocolate': 'Coffee/caffeine, alcohol, and chocolate',
    'Bạc hà và món có bạc hà': 'Peppermint and mint-flavored items',
    'Hải sản (hàu, sò, nghêu, tôm, cua, mực, cá biển giàu purin)': 'High-purine seafood (shellfish, shrimp, crab, squid, marine fish)',
    'Nội tạng động vật và thịt đỏ / giò heo': 'Organ meats, red meat, and pork trotters',
    'Măng tươi và măng chua': 'Fresh and pickled bamboo shoots',
    'Đường tinh luyện, mật ong, sữa đặc có đường': 'Refined sugar, honey, and sweetened condensed milk',
    'Nước ngọt, chè ngọt, bánh kẹo ngọt': 'Sugary soft drinks, sweet desserts, and pastries',
    'Mắm đậm đặc, dưa muối, cà muối': 'Fermented fish sauces and pickled vegetables',
    'Thực phẩm chế biến sẵn (xúc xích, thịt nguội, đồ hộp)': 'Processed meats and canned foods (sausages, cold cuts)',
    'Món cay nóng (ớt, tiêu nồng)': 'Hot and spicy foods (chili, black pepper)',
    'Món chua gắt (chanh, giấm, me chua, xoài chua)': 'Strongly acidic foods (lime, vinegar, tamarind, sour mango)',
    'Đồ chiên rán nhiều dầu mỡ, rượu bia, cà phê': 'Deep-fried greasy foods, alcohol, and coffee',
    'Thực phẩm chứa gluten và yến mạch chưa xác minh': 'Gluten-containing foods and uncertified oats',
    'Thực phẩm chứa trứng': 'Foods containing egg',
    'Thực phẩm chứa sữa động vật': 'Foods containing dairy milk',
    'Thực phẩm chứa đậu nành': 'Foods containing soy'
  };
  const _AVOID_REASON_EN = {
    'Nên tránh khi sốt vì có thể làm tình trạng mất nước nặng hơn.': 'Avoid during fever as alcohol can worsen dehydration.',
    'Có thể gây xót và kích ứng vùng loét miệng; hạn chế nếu gây khó chịu.': 'May sting and irritate mouth ulcers; limit if uncomfortable.',
    'Có thể cọ xát vùng miệng đang đau; ưu tiên kết cấu mềm hơn.': 'May scrape sore oral tissue; prefer softer textures.',
    'Có thể kích ứng vùng miệng đang tổn thương; để nguội đến nhiệt độ dễ chịu.': 'Can irritate oral mucosa; let cool to a comfortable temperature.',
    'NHS khuyên tránh trà, cà phê ít nhất 6 giờ trước khi ngủ.': 'NHS guidance advises avoiding tea and coffee for at least 6 hours before bedtime.',
    'NHS khuyên tránh đồ uống có cồn ít nhất 6 giờ trước khi ngủ.': 'NHS guidance advises avoiding alcohol for at least 6 hours before bedtime.',
    'Không ăn một bữa lớn sát giờ đi ngủ.': 'Avoid eating a heavy meal right before going to bed.',
    'Có thể kích hoạt triệu chứng ở một số người; hạn chế khi xác định là yếu tố gây khó chịu của bạn.': 'May trigger reflux symptoms in some individuals; limit if it worsens your discomfort.',
    'Đây là các yếu tố có thể gây triệu chứng ở một số người bị trào ngược, không phải ai cũng cần kiêng giống nhau.': 'Potential reflux triggers for some individuals; tolerance varies from person to person.',
    'Có thể là yếu tố kích thích trào ngược ở một số người; đối chiếu với triệu chứng cá nhân.': 'Can relax the lower esophageal sphincter and trigger reflux in some people.',
    'Hàm lượng purin rất cao, dễ chuyển hóa thành acid uric và kích hoạt cơn gút cấp.': 'Very high in purines, which metabolize into uric acid and can trigger acute gout flares.',
    'Gan, cật, tim, lòng, thịt bò, giò heo chứa nhiều purin và chất béo bão hòa.': 'Organ meats, beef, and pork trotters are high in purines and saturated fats.',
    'Có thể làm tăng kết tinh acid uric tại khớp; theo hướng dẫn dinh dưỡng cần kiêng khi bị gút.': 'Associated with worsened uric acid flare-ups in local gout dietary guidance.',
    'Ức chế bài tiết acid uric qua thận và thúc đẩy tổng hợp acid uric.': 'Impairs renal uric acid excretion and increases purine synthesis.',
    'Làm tăng đột ngột chỉ số đường huyết sau ăn.': 'Causes rapid postprandial blood glucose spikes.',
    'Chứa nhiều đường tự do không có lợi cho kiểm soát đường huyết.': 'High in free sugars that impair glycemic control.',
    'Chứa hàm lượng muối/natri rất cao, gây giữ nước và tăng huyết áp.': 'Very high in sodium, promoting fluid retention and elevated blood pressure.',
    'Nhiều muối natri và chất bảo quản; cần hạn chế khi bị tăng huyết áp.': 'High in sodium and preservatives; limit when managing hypertension.',
    'Gây kích ứng trực tiếp niêm mạc dạ dày và tăng cảm giác đau rát.': 'Directly irritates gastric mucosa and worsens epigastric burning.',
    'Làm tăng độ acid trong dạ dày, gây xót và làm chậm lành vết loét.': 'Increases gastric acidity and may irritate mucosal erosions.',
    'Làm chậm tiêu hóa, kích thích tăng tiết acid dịch vị.': 'Slows gastric emptying and stimulates excess acid secretion.',
    'Bạn đã yêu cầu tránh gluten. Lúa mạch chứa gluten; yến mạch trong kho chưa được xác minh không nhiễm gluten.': 'You requested gluten avoidance. Barley contains gluten, and catalog oats are not certified gluten-free.',
    'Bạn đã nêu cần tránh thành phần này. Kiểm tra nhãn và nguy cơ nhiễm chéo khi chế biến.': 'You asked to avoid this allergen. Always check food labels and cross-contamination risks.'
  };
  function _trTime(val) {
    const s = String(val || '').trim();
    if (!_isEn() || !s) return s;
    if (s === 'Xem cách làm') return 'See steps';
    return s.replace(/(\d+)\s*phút/gi, '$1 min').replace(/(\d+)\s*(?:giờ|tiếng)/gi, '$1 hr');
  }
  function _trSubtitle(val) {
    const s = String(val || '').trim();
    return (_isEn() && _SUBTITLE_EN[s]) ? _SUBTITLE_EN[s] : s;
  }
  function _trBenefit(val) {
    const s = String(val || '').trim();
    if (!_isEn() || !s) return s;
    if (s === 'Công thức nấu ăn tham khảo; chưa được xác minh công dụng hoặc mức độ phù hợp với bệnh cho từng món.') {
      return 'Reference culinary recipe; clinical benefits or suitability for specific conditions have not been individually verified.';
    }
    return s;
  }
  function _trRecipeNote(val) {
    const s = String(val || '').trim();
    if (!_isEn() || !s) return s;
    const map = {
      'Đối chiếu nguyên liệu, dị ứng và hướng dẫn ăn uống cá nhân trước khi dùng.': 'Check ingredients, food allergies, and your personal dietary guidance before consuming.',
      'Hạn chế đồ cay, chua hoặc quá nóng nếu gây rát miệng.': 'Limit spicy, acidic, or very hot items if they irritate your mouth.',
      'Hạn chế cà phê, trà đặc và đồ uống chứa caffeine gần giờ ngủ.': 'Avoid coffee, strong tea, and caffeinated drinks close to bedtime.'
    };
    return map[s] || s;
  }
  function _trNotice(data) {
    const raw = String(data?.notice || '').trim();
    if (!_isEn() || !raw) return raw;
    if (raw.startsWith('Gemini chưa trả được gợi ý hợp lệ.')) {
      return 'AI ranking is temporarily unavailable. Showing safety-filtered reference recipes from the Python rule engine.';
    }
    const aiMatch = raw.match(/^Gemini đã chọn (\d+) công thức từ (\d+) ứng viên liên quan trong (\d+) công thức qua bộ lọc\./);
    if (aiMatch) {
      const extra = raw.includes('Chưa có bộ quy tắc riêng') ? ' No condition-specific rule set matched your input.' : '';
      return `Gemini selected ${aiMatch[1]} recipe(s) from ${aiMatch[2]} relevant candidates out of ${aiMatch[3]} safety-filtered recipes. For nutritional reference only, not a therapeutic diet.${extra}`;
    }
    if (raw.startsWith('Bạn vẫn có thể xem các công thức tham khảo bên dưới.')) {
      return 'You can browse general safety-filtered options below. Add allergy or dietary details for personalized AI ranking.';
    }
    if (raw === 'Bạn đã xem hết các công thức qua bộ lọc hiện tại.') return 'You have viewed all recipes matching the current safety filter.';
    if (raw.startsWith('Không có món trong kho hiện tại vượt qua bộ lọc')) return 'No catalog recipes passed the ingredient safety filter; the system never invents unverified dishes.';
    if (raw.startsWith('Để bảo đảm an toàn lâm sàng')) return 'For clinical safety, automated meal suggestions are disabled for medical conditions requiring physician-prescribed therapeutic diets.';
    if (raw === 'Cần thêm thông tin trước khi gợi ý món.') return 'More details are needed before suggesting recipes.';
    return raw;
  }
  function _trQuestion(val) {
    const s = String(val || '').trim();
    if (!_isEn() || !s) return s;
    if (s.startsWith('Bạn có dị ứng thực phẩm')) return 'Do you have any food allergies or dietary restrictions to factor into your suggestions?';
    if (s.startsWith('Chưa có công thức đáp ứng')) return 'No recipes matched all of your restrictions. Could you share ingredients you can safely eat?';
    const unmapped = s.match(/^Tình trạng '(.+)' là bệnh lý cần chế độ dinh dưỡng lâm sàng chuyên biệt/);
    if (unmapped) return `'${unmapped[1]}' requires a physician-directed clinical diet. Automated recipe suggestions are paused to prevent dietary interactions.`;
    return s;
  }
  function _trSelectionExplanation(data) {
    if (!_isEn()) return data?.selection_explanation || '';
    if (data?.provider_status === 'clinical_safeguard_refusal') {
      return 'MediMind Clinical Safety Guardrail: automated menus are not generated for conditions without verified dietary rules.';
    }
    const total = data?.catalog?.total || '';
    const src = data?.catalog?.source || 'the local catalog';
    return `Python rule filters check declared ingredients and cited clinical guidance first. Gemini only selects and explains pre-filtered recipes without altering ingredients or steps.${total ? ` The catalog currently holds ${total} recipes from ${src}.` : ''} Ingredient tags are scanned automatically and do not constitute clinical certification.`;
  }
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
    if (artwork(recipe).includes('.svg') || artwork(recipe) === fallbackArtwork(recipe)) return _t('Minh họa nhóm món', 'Category illustration');
    if (recipe.image_match_method === 'approximate_title_match') return _t('Ảnh tham khảo · cần kiểm tra', 'Reference image · verify');
    return ['exact_normalized_title', 'reference_title_match'].includes(recipe.image_match_method)
      ? _t('Ảnh tham khảo cùng tên món', 'Reference dish photo')
      : _t('Ảnh từ nguồn dữ liệu', 'Dataset source photo');
  }
  function recipeImage(recipe) {
    const src = artwork(recipe), fallback = fallbackArtwork(recipe);
    const fallbackNote = _t('Minh họa nhóm món', 'Category illustration');
    return `<img class="nf-food-image" src="${safe(src)}" data-fallback="${safe(fallback)}" alt="${safe(recipe.title)}" width="640" height="440" loading="lazy" decoding="async" onerror="this.onerror=null;this.src=this.dataset.fallback;const note=this.parentElement.querySelector('.nf-art-note');if(note)note.textContent='${fallbackNote}'">`;
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
      const titleText = (_isEn() && _AVOID_TITLE_EN[item.title]) ? _AVOID_TITLE_EN[item.title] : item.title;
      const reasonText = (_isEn() && _AVOID_REASON_EN[item.reason]) ? _AVOID_REASON_EN[item.reason] : item.reason;
      return `<article class="nf-limit-item"><span class="nf-limit-level">${item.level === 'avoid' ? _t('Cần tránh', 'Avoid') : _t('Nên hạn chế', 'Limit')}</span><strong>${safe(titleText)}</strong><p>${safe(reasonText)}</p>${source ? `<div class="nf-source-links">${_t('Nguồn:', 'Source:')} ${source}</div>` : ''}</article>`;
    }).join('');
    let noteText = state.avoidanceNote || '';
    if (_isEn()) {
      if (!noteText || noteText === 'Chưa có danh sách kiêng riêng cho mô tả này.' || noteText.startsWith('Chưa có danh sách thực phẩm cần kiêng riêng')) {
        noteText = 'No condition-specific avoidance list for this description. The system does not invent unverified dietary restrictions.';
      } else if (noteText.startsWith('Các mục dưới đây là lưu ý có nguồn')) {
        noteText = 'Evidence-based precautions or ingredients you asked to avoid; not an absolute restriction list for everyone.';
      }
    } else if (!noteText) {
      noteText = 'Chưa có danh sách kiêng riêng cho mô tả này.';
    }
    return `<${heading} class="nf-limit-title">${_t('Nên hạn chế / cần tránh', 'Foods to Limit or Avoid')}</${heading}><p class="nf-limit-note">${safe(noteText)}</p>${items ? `<div class="nf-limit-items">${items}</div>` : ''}`;
  }

  function show(stage) {
    state.stage = stage;
    ['search', 'type', 'results', 'detail'].forEach(name => { el('nf-' + name).hidden = name !== stage; });
    const label = state.query ? state.query.charAt(0).toLocaleUpperCase(_isEn() ? 'en-US' : 'vi-VN') + state.query.slice(1) : '';
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
    const provider = recipe.source_provider || _t('Nguồn công thức', 'Recipe source');
    const sourceUrl = recipeSourceUrl(recipe.revision_url || recipe.source_url);
    const datasetUrl = recipeSourceUrl(recipe.dataset_url);
    const imageSource = recipeSourceUrl(recipe.image_source_page);
    const sourceLabel = sourceUrl.startsWith('https://github.com/') ? _t('Kho dữ liệu nghiên cứu', 'Research dataset') : recipe.source_title || recipe.title;
    const source = sourceUrl ? `<a href="${safe(sourceUrl)}" target="_blank" rel="noopener noreferrer">${safe(sourceLabel)}</a>` : safe(recipe.source_title || recipe.title);
    const attribution = recipe.source_attribution || recipe.attribution || (provider === 'Wikibooks Cookbook' ? 'Wikibooks contributors' : provider === 'ViFoodRec' ? _t('Nhóm tác giả ViFoodRec', 'ViFoodRec authors') : '');
    const license = recipe.license === 'CC-BY-SA-4.0' || recipe.license === 'CC BY-SA 4.0'
      ? _t('Giấy phép <a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" rel="noopener noreferrer">CC BY-SA 4.0</a>.', 'License: <a href="https://creativecommons.org/licenses/by-sa/4.0/" target="_blank" rel="noopener noreferrer">CC BY-SA 4.0</a>.')
      : _t('Kho dữ liệu chưa công bố giấy phép tái sử dụng.', 'Dataset reuse license not specified.');
    const language = recipe.language === 'vi'
      ? _t('Nguyên liệu và cách làm theo bản tiếng Việt của nguồn dữ liệu.', 'Ingredients and steps follow the Vietnamese source dataset.')
      : _t(
        `Nguyên liệu và cách làm giữ bản gốc tiếng Anh.${recipe.display_title && recipe.display_title !== recipe.title ? ' Tên món được dịch tự động.' : ''}`,
        `Ingredients and steps are preserved from the original English source.${recipe.display_title && recipe.display_title !== recipe.title ? ' Dish title includes an automated translation.' : ''}`
      );
    return `<div class="nf-recipe-credit">${_t('Nguồn:', 'Source:')} ${safe(provider)} · ${source}<br>${safe(attribution)}${datasetUrl && datasetUrl !== sourceUrl ? ` · <a href="${safe(datasetUrl)}" target="_blank" rel="noopener noreferrer">${_t('Kho dữ liệu', 'Dataset')}</a>` : ''}${imageSource ? `<br>${_t('Ảnh tham khảo cùng tên món:', 'Reference photo:')} <a href="${safe(imageSource)}" target="_blank" rel="noopener noreferrer">${safe(new URL(imageSource).hostname)}</a>` : ''}<br>${license} ${language}<br>${_t('Nhãn nguyên liệu được quét tự động; chưa được xác minh y khoa cho từng món.', 'Ingredient tags are scanned automatically and are not individually verified by a clinician.')}</div>`;
  }

  function renderCards() {
    const tag = state.type === 'drink' ? _t('NƯỚC UỐNG', 'DRINK') : _t('THỨC ĂN', 'FOOD');
    const titleFor = r => (_isEn() && r.language === 'en' && r.title) ? r.title : (r.display_title || r.title);
    el('nf-cards').innerHTML = state.recipes.map((recipe, index) => `
      <button type="button" class="nf-card" data-nf-recipe="${index}">
        <span class="nf-art">${recipeImage(recipe)}<span class="nf-art-tag">${tag}</span>${recipe.imported ? `<span class="nf-art-note">${imageLabel(recipe)}</span>` : ''}</span>
        <span class="nf-card-content"><strong>${safe(titleFor(recipe))}</strong><p>${safe(_trSubtitle(recipe.subtitle || ''))}</p>
        ${recipe.imported ? `<span class="nf-import-label">${_t('Nguồn:', 'Source:')} ${safe(recipe.source_provider || _t('Nguồn công thức', 'Recipe source'))}</span>` : ''}
        ${recipe.recommendation_reason ? `<span class="nf-reason"><span class="nf-reason-header"><svg viewBox="0 0 20 20" fill="currentColor" width="12" height="12" aria-hidden="true"><path d="M11 3a1 1 0 10-2 0v1a1 1 0 102 0V3zM15.657 5.757a1 1 0 00-1.414-1.414l-.707.707a1 1 0 001.414 1.414l.707-.707zM18 10a1 1 0 01-1 1h-1a1 1 0 110-2h1a1 1 0 011 1zM5.05 6.464A1 1 0 106.464 5.05l-.707-.707a1 1 0 00-1.414 1.414l.707.707zM5 10a1 1 0 01-1 1H3a1 1 0 110-2h1a1 1 0 011 1zM8 16v-1h4v1a2 2 0 11-4 0zM12 14H8a4 4 0 01-.8-7.92 4.002 4.002 0 017.6 0A4 4 0 0112 14z"/></svg> ${_t('Vì sao gợi ý?', 'Why suggested?')}</span><span class="nf-reason-text">${safe(recipe.recommendation_reason)}</span></span>` : ''}
        <span class="nf-card-footer"><span>◷ ${safe(_trTime(recipe.cooking_time || ''))}</span><b>${_t('Xem chi tiết →', 'View recipe →')}</b></span></span>
      </button>`).join('');
  }

  function renderDetail(recipe) {
    state.activeRecipe = recipe;
    const displayTitle = (_isEn() && recipe.language === 'en' && recipe.title) ? recipe.title : (recipe.display_title || recipe.title);
    const ingredients = (recipe.ingredients || []).map(item => `<div class="nf-ingredient"><span class="nf-ingredient-name"><span class="nf-ingredient-dot" aria-hidden="true"></span>${safe(item.name)}</span><b>${safe(item.amount)} ${safe(item.unit || '')}</b></div>`).join('');
    const steps = (recipe.steps || []).map((step, i) => `<div class="nf-step"><span class="nf-step-number">${i + 1}</span><span>${safe(step)}</span></div>`).join('');
    const avoid = (recipe.avoid || []).map(x => safe(_trRecipeNote(x))).join('<br>');
    const servingMeta = recipe.imported
      ? (recipe.servings ? _t('Khẩu phần theo nguồn: ', 'Source servings: ') + safe(recipe.servings) : _t('Theo công thức gốc', 'Original recipe scale'))
      : _t('1 khẩu phần', '1 serving');
    el('nf-detail-content').innerHTML = `<div class="nf-detail-grid">
      <div class="nf-detail-visual"><div class="nf-art">${recipeImage(recipe)}${recipe.imported ? `<span class="nf-art-note">${imageLabel(recipe)}</span>` : ''}</div><p class="nf-detail-caption">◷ ${safe(_trTime(recipe.cooking_time || ''))} · ${state.type === 'drink' ? _t('Nước uống', 'Drink') : _t('Thức ăn', 'Food')}</p></div>
      <article class="nf-detail-copy"><p class="nf-overline">${state.type === 'drink' ? _t('NƯỚC UỐNG', 'DRINK') : _t('THỨC ĂN', 'FOOD')}</p><h2>${safe(displayTitle)}</h2><p class="nf-subtitle">${safe(_trSubtitle(recipe.subtitle || ''))}</p>${recipeCredit(recipe)}
      ${recipe.recommendation_reason ? `<div class="nf-recommendation-box"><div class="nf-recommendation-head"><span class="nf-recommendation-badge"><svg viewBox="0 0 20 20" fill="currentColor" width="13" height="13" aria-hidden="true"><path fill-rule="evenodd" d="M6.267 3.455a3.066 3.066 0 001.745-.723 3.066 3.066 0 013.976 0 3.066 3.066 0 001.745.723 3.066 3.066 0 012.812 2.812c.051.643.304 1.254.723 1.745a3.066 3.066 0 010 3.976 3.066 3.066 0 00-.723 1.745 3.066 3.066 0 01-2.812 2.812 3.066 3.066 0 00-1.745.723 3.066 3.066 0 01-3.976 0 3.066 3.066 0 00-1.745-.723 3.066 3.066 0 01-2.812-2.812 3.066 3.066 0 00-.723-1.745 3.066 3.066 0 010-3.976 3.066 3.066 0 00.723-1.745 3.066 3.066 0 012.812-2.812zm7.44 5.252a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/></svg> ${_t('Vì sao được gợi ý?', 'Why is this suggested?')}</span></div><p class="nf-recommendation-desc">${safe(recipe.recommendation_reason)}</p>${recipe.ai_caution ? `<p class="nf-ai-caution">${safe(recipe.ai_caution)}</p>` : ''}${sourceLinks(recipe.source_ids || []) ? `<p class="nf-source-links">${_t('Hướng dẫn tham khảo:', 'Reference guidelines:')} ${sourceLinks(recipe.source_ids || [])}</p>` : ''}</div>` : ''}
      <h3>${_t('Công dụng / Điểm nổi bật', 'Key Benefits')}</h3><p class="nf-benefit">${safe(_trBenefit(recipe.benefit) || _t('Thông tin dinh dưỡng đang được cập nhật.', 'Nutritional details are being updated.'))}</p>
      <h3>${_t('Nguyên liệu', 'Ingredients')} · ${servingMeta}</h3><div class="nf-ingredients">${ingredients}</div>
      <h3>${_t('Cách chế biến', 'Preparation Steps')}</h3><div class="nf-steps">${steps}</div>
      <aside class="nf-avoid"><strong>${_t('LƯU Ý CỦA CÔNG THỨC', 'RECIPE NOTES')}</strong>${avoid || _t('Chọn thực phẩm phù hợp với tình trạng và dị ứng của bạn.', 'Choose ingredients suited to your health status and allergies.')}</aside>
      <section class="nf-limit-panel nf-limit-compact">${avoidanceMarkup(true)}</section></article></div>`;
  }

  function applyResultsCopy() {
    if (!el('nf-results-title')) return;
    el('nf-results-title').textContent = state.type === 'drink'
      ? _t('Các thức uống để tham khảo', 'Suggested Drinks')
      : _t('Các món ăn để tham khảo', 'Suggested Dishes');
    const data = state.lastData;
    if (!data) return;
    const stats = data.catalog;
    const srcLabel = stats?.source === 'Danh mục mẫu' ? _t('Danh mục mẫu', 'Sample Catalog') : (stats?.source || '');
    el('nf-catalog-stats').textContent = stats
      ? (_isEn()
        ? `${stats.cuisine === 'VN' ? 'Vietnamese Catalog' : 'Recipe Catalog'}${srcLabel ? ' · ' + srcLabel : ''}: ${stats.total} recipes · ${data.catalog_type_count} ${state.type === 'drink' ? 'drinks' : 'dishes'} · ${data.eligible_count} passed safety filter · ${data.considered_count} candidates evaluated`
        : `${stats.cuisine === 'VN' ? 'Kho món Việt' : 'Kho dữ liệu'}${srcLabel ? ' · ' + srcLabel : ''}: ${stats.total} công thức · ${data.catalog_type_count} ${state.type === 'drink' ? 'nước uống' : 'món ăn'} · ${data.eligible_count} qua bộ lọc · ${data.considered_count} ứng viên gửi Gemini`)
      : '';
    el('nf-avoidance').innerHTML = avoidanceMarkup();
    const notice = el('nf-notice');
    const addedPrefix = state.lastAddedCount
      ? (_isEn() ? `Added ${state.lastAddedCount} more suggestion${state.lastAddedCount > 1 ? 's' : ''}. ` : `Đã thêm ${state.lastAddedCount} gợi ý mới. `)
      : '';
    notice.textContent = addedPrefix + _trNotice(data);
    if (el('nf-question')) el('nf-question').textContent = _trQuestion(data.clarification_question || '');
    const limitations = _isEn()
      ? (Array.isArray(data.limitations) && data.limitations.length ? 'Only declared ingredients and rule tags are checked; caloric needs, comorbidities, medications, age, and cross-contamination are not evaluated.' : '')
      : (Array.isArray(data.limitations) ? data.limitations.join(' ') : '');
    const excluded = (!_isEn() && Array.isArray(data.excluded)) ? data.excluded.map(item => `${item.title}: ${item.reason}`).join(' ') : '';
    const excludedEn = (_isEn() && Array.isArray(data.excluded) && data.excluded.length) ? `Excluded ${data.excluded.length} item(s) before ranking via ingredient safety rules.` : '';
    el('nf-selection-copy').textContent = [
      _trSelectionExplanation(data) || _t('Danh sách tham khảo chung, chưa xác nhận mức độ phù hợp theo tình trạng của bạn.', 'General reference suggestions; suitability for your specific clinical condition has not been verified.'),
      limitations,
      excluded ? `Món đã loại trước khi gọi Gemini: ${excluded}` : excludedEn
    ].filter(Boolean).join(' ');
    const sources = sourceLinks(state.sources.map((_, id) => id));
    el('nf-sources').innerHTML = sources ? `${_t('Hướng dẫn được cung cấp cho bộ gợi ý:', 'Reference guidelines for this suggestion set:')} ${sources}` : '';
    el('nf-edit-query').textContent = state.recipes.length
      ? _t('Bổ sung để gợi ý sát hơn →', 'Refine description →')
      : _t('Bổ sung mô tả →', 'Add more details →');
    el('nf-status').textContent = state.recipes.length || data.needs_clarification
      ? ''
      : _t('Chưa có món phù hợp. Hãy thử tìm kiếm khác.', 'No matching recipes found. Please try a different query.');
    renderCards();
  }

  async function chooseType(type, append = false) {
    if (state.request) state.request.abort();
    const controller = new AbortController();
    state.request = controller;
    state.type = type;
    const previous = append ? state.recipes.slice() : [];
    if (!append) { state.recipes = []; state.lastData = null; state.lastAddedCount = 0; }
    el('nf-results-title').textContent = type === 'drink'
      ? _t('Các thức uống để tham khảo', 'Suggested Drinks')
      : _t('Các món ăn để tham khảo', 'Suggested Dishes');
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
    el('nf-status').textContent = _t('Đang tìm gợi ý cho bạn…', 'Finding suggestions for you…');
    if (!append) show('results');
    try {
      const response = await fetch('/api/nutrition/options', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ condition: state.query, recipe_type: type, exclude_recipe_ids: previous.map(recipe => recipe.id) }), signal: controller.signal });
      const body = await response.json();
      if (!response.ok || !body.success || !Array.isArray(body.data?.recipes)) throw new Error(body.error || _t('Không thể tải gợi ý.', 'Unable to load suggestions.'));
      if (state.request !== controller) return;
      const incoming = body.data.recipes.filter(recipe => !previous.some(old => old.id === recipe.id));
      state.recipes = previous.concat(incoming);
      state.lastData = body.data;
      state.lastAddedCount = append ? incoming.length : 0;
      el('nf-load-more').hidden = !body.data.has_more;
      state.sources = Array.isArray(body.data.sources) ? body.data.sources : [];
      state.avoidance = Array.isArray(body.data.avoidance) ? body.data.avoidance : [];
      state.avoidanceNote = body.data.avoidance_note || '';
      el('nf-catalog-stats').hidden = !body.data.catalog;
      el('nf-avoidance').hidden = false;
      el('nf-avoidance-jump').hidden = false;
      el('nf-notice').hidden = !body.data.notice;
      el('nf-selection-info').hidden = false;
      el('nf-notice').dataset.mode = body.data.provider_status === 'ai_ranked' ? 'ai' : 'general';
      el('nf-clarification').hidden = !body.data.needs_clarification;
      el('nf-question').textContent = body.data.clarification_question || '';
      applyResultsCopy();
      el('nf-sources').hidden = !el('nf-sources').innerHTML;
    } catch (error) {
      if (error.name !== 'AbortError') el('nf-status').textContent = _t('Không tải được gợi ý. Hãy quay lại và thử lại.', 'Unable to load suggestions. Please go back and try again.');
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
      window.addEventListener('medimind:langchange', () => {
        if (!el('nf-search')) return;
        if (state.lastData) applyResultsCopy();
        if (state.stage === 'detail' && state.activeRecipe) renderDetail(state.activeRecipe);
      });
    }
    show('search');
  };
})();
