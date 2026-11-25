/* Search → type → options → recipe. The API supplies complete recipes. */
(() => {
  const state = { query: '', type: '', stage: 'search', activeRecipe: null, lastData: null, lastAddedCount: 0, recipes: [], sources: [], avoidance: [], avoidanceNote: '', request: null, viewMode: 'full_meal' };
  const el = id => document.getElementById(id);
  const safe = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const _isEn = () => typeof currentLang !== 'undefined' && currentLang === 'en';
  const _t = (vi, en) => (_isEn() ? en : vi);
  const kcal = value => {
    if (value === null || value === undefined || value === '') return '';
    const number = Number(value);
    return Number.isFinite(number) && number >= 0
      ? `${Math.round(number).toLocaleString(_isEn() ? 'en-US' : 'vi-VN')} kcal` : '';
  };

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
    'Nội tạng động vật': 'Organ meats',
    'Thịt đỏ và hải sản giàu purin': 'Red meat and high-purine seafood',
    'Rượu, bia': 'Alcohol and beer',
    'Đường tinh luyện, mật ong, sữa đặc có đường': 'Refined sugar, honey, and sweetened condensed milk',
    'Nước ngọt, chè ngọt, bánh kẹo ngọt': 'Sugary soft drinks, sweet desserts, and pastries',
    'Mắm đậm đặc, dưa muối, cà muối': 'Fermented fish sauces and pickled vegetables',
    'Thực phẩm chế biến sẵn (xúc xích, thịt nguội, đồ hộp)': 'Processed meats and canned foods (sausages, cold cuts)',
    'Món cay nóng (ớt, tiêu nồng)': 'Hot and spicy foods (chili, black pepper)',
    'Món chua gắt (chanh, giấm, me chua, xoài chua)': 'Strongly acidic foods (lime, vinegar, tamarind, sour mango)',
    'Đồ chiên rán nhiều dầu mỡ, rượu bia, cà phê': 'Deep-fried greasy foods, alcohol, and coffee',
    'Đồ ăn, thức uống nhiều đường thêm': 'Foods and drinks high in added sugar',
    'Món nhiều chất béo bão hòa': 'Foods high in saturated fat',
    'Thực phẩm chứa gluten và yến mạch chưa xác minh': 'Gluten-containing foods and uncertified oats',
    'Thực phẩm chứa trứng': 'Foods containing egg',
    'Thực phẩm chứa sữa động vật': 'Foods containing dairy milk',
    'Thực phẩm chứa đậu nành': 'Foods containing soy',
    'Thực phẩm chứa tôm/tép': 'Foods containing shrimp',
    'Thực phẩm chứa cua/ghẹ': 'Foods containing crab',
    'Thực phẩm chứa hải sản có vỏ': 'Foods containing shellfish',
    'Thực phẩm chứa hải sản': 'Foods containing seafood',
    'Thực phẩm chứa cá': 'Foods containing fish',
    'Thực phẩm chứa đậu phộng/lạc': 'Foods containing peanuts',
    'Thực phẩm chứa hạt cây': 'Foods containing tree nuts',
    'Thực phẩm chứa mè/vừng': 'Foods containing sesame'
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
    'Gan, cật và tim là nhóm rất giàu purin.': 'Liver, kidney and heart are very high in purines.',
    'Hạn chế khẩu phần và tần suất theo hướng dẫn cá nhân.': 'Limit portion size and frequency according to individual guidance.',
    'Hạn chế, đặc biệt trong giai đoạn gút chưa được kiểm soát.': 'Limit alcohol, especially when gout is not well controlled.',
    'Hạn chế đường thêm và xét tổng carbohydrate theo khẩu phần.': 'Limit added sugars and consider total carbohydrates in the portion.',
    'Thường có nhiều đường tự do; hạn chế theo kế hoạch ăn uống cá nhân.': 'Often high in free sugars; limit according to an individual eating plan.',
    'Chứa hàm lượng muối/natri rất cao, gây giữ nước và tăng huyết áp.': 'Very high in sodium, promoting fluid retention and elevated blood pressure.',
    'Nhiều muối natri và chất bảo quản; cần hạn chế khi bị tăng huyết áp.': 'High in sodium and preservatives; limit when managing hypertension.',
    'Gây kích ứng trực tiếp niêm mạc dạ dày và tăng cảm giác đau rát.': 'Directly irritates gastric mucosa and worsens epigastric burning.',
    'Làm tăng độ acid trong dạ dày, gây xót và làm chậm lành vết loét.': 'Increases gastric acidity and may irritate mucosal erosions.',
    'Làm chậm tiêu hóa, kích thích tăng tiết acid dịch vị.': 'Slows gastric emptying and stimulates excess acid secretion.',
    'Bạn đã yêu cầu tránh gluten. Lúa mạch chứa gluten; yến mạch trong kho chưa được xác minh không nhiễm gluten.': 'You requested gluten avoidance. Barley contains gluten, and catalog oats are not certified gluten-free.',
    'Bạn đã nêu cần tránh thành phần này. Kiểm tra nhãn và nguy cơ nhiễm chéo khi chế biến.': 'You asked to avoid this allergen. Always check food labels and cross-contamination risks.',
    'NIDDK khuyên giảm rượu vì rượu có thể làm tổn thương gan thêm.': 'NIDDK advises minimizing alcohol because it can further harm the liver.',
    'NIDDK khuyên hạn chế đường đơn, nhất là đồ uống ngọt; xem thành phần và khẩu phần thực tế.': 'NIDDK advises limiting simple sugars, especially sweetened drinks; check ingredients and actual portions.',
    'Ưu tiên thay chất béo bão hòa bằng chất béo chưa bão hòa theo hướng dẫn NIDDK; chưa có định lượng chất béo cho từng công thức.': 'NIDDK advises replacing saturated fat with unsaturated fat; fat amounts have not been measured for individual recipes.'
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
  function _recipeEn(recipe) { return _isEn() ? recipe?.translations?.en : null; }
  function _recipeTitle(recipe) {
    return _recipeEn(recipe)?.title || ((_isEn() && recipe.language === 'en' && recipe.title) ? recipe.title : (recipe.display_title || recipe.title));
  }
  function _recipeSubtitle(recipe) { return _recipeEn(recipe)?.subtitle || _trSubtitle(recipe.subtitle || ''); }
  function _recipeBenefit(recipe) { return _recipeEn(recipe)?.benefit || _trBenefit(recipe.benefit); }
  function _recipeReason(recipe) {
    if (_recipeEn(recipe)) return 'A reference recipe screened against listed ingredients and recognized allergies; suitability for your portions and other conditions has not been confirmed.';
    return recipe.recommendation_reason || '';
  }
  function _trNotice(data) {
    const raw = String(data?.notice || '').trim();
    if (String(data?.provider_status || '').startsWith('fallback_')) {
      return _t(
        'AI tạm thời chưa thể xếp hạng món ăn. Hệ thống đang hiển thị các gợi ý tham khảo đã được lọc theo yêu cầu của bạn.',
        'AI ranking is temporarily unavailable. Showing reference recipes screened against your stated requirements.'
      );
    }
    if (!_isEn() || !raw) return raw;
    if (data?.provider_status === 'ai_clarification_with_options') {
      return 'You can browse screened reference recipes below. Add more dietary details for personalized AI ranking; these options are not AI ranked.';
    }
    if (raw.startsWith('Bạn vẫn có thể xem các công thức tham khảo bên dưới.')) {
      return 'You can browse general safety-filtered options below. Add allergy or dietary details for personalized AI ranking.';
    }
    if (data?.provider_status === 'guided_catalog') {
      return 'These reference recipes have clear ingredient lists and were screened against recognized allergies. NIDDK guidance covers nonalcoholic fatty liver disease; each dish still needs review for your cause, disease stage, and portion needs.';
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
    if (data?.provider_status === 'guided_catalog') {
      return 'MediMind checks fixed ingredient lists against declared allergies and cited general dietary principles. These recipes have not undergone clinical nutrition verification; review seasoning, portions, and other conditions before use.';
    }
    if (data?.provider_status === 'clinical_safeguard_refusal') {
      return 'MediMind Clinical Safety Guardrail: automated menus are not generated for conditions without verified dietary rules.';
    }
    const total = data?.catalog?.total || '';
    const src = data?.catalog?.source || 'the local catalog';
    const aiExplanation = data?.provider_status === 'ai_ranked'
      ? ' AI selected and explained only pre-filtered recipes without altering ingredients or steps.'
      : ' The displayed recipes have not been ranked by AI.';
    return `Python rule filters check declared ingredients and cited clinical guidance first.${aiExplanation}${total ? ` The catalog currently holds ${total} recipes from ${src}.` : ''} Ingredient tags are scanned automatically and do not constitute clinical certification.`;
  }
  const artworkIds = new Set(['oat_porridge', 'pumpkin_soup', 'rice_carrot', 'soft_egg', 'sweet_potato', 'chicken_congee', 'tofu_pumpkin', 'warm_water', 'warm_milk', 'oat_drink', 'cucumber_water', 'warm_soy', 'pear_water', 'barley_water', 'bread', 'white_rice', 'rice_noodles']);
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
    if (/bánh mì|bread|sandwich|toast|baguette/.test(text)) return 'bread';
    if (/cơm trắng|cơm dẻo|gạo tẻ|bát cơm|cơm nóng|gạo lứt/.test(text)) return 'white_rice';
    if (/bún|phở|bánh phở|hủ tiếu|mì|miến|noodle/.test(text)) return 'rice_noodles';
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
    const img = recipe?.image_link || recipe?.source_image_url;
    if (img && (img.startsWith('/static/') || img.startsWith('http'))) {
      return img;
    }
    return fallbackArtwork(recipe);
  }
  function fallbackArtwork(recipe) { return `/static/images/nutrition/${matchArtwork(recipe)}.svg?v=2`; }
  function recipeImage(recipe) {
    const src = artwork(recipe), fallback = fallbackArtwork(recipe);
    return `<img class="nf-food-image" src="${safe(src)}" data-fallback="${safe(fallback)}" alt="${safe(_recipeTitle(recipe))}" width="640" height="440" loading="lazy" decoding="async" onerror="this.onerror=null;this.src=this.dataset.fallback">`;
  }
  let initialized = false;

  function sourceLinks() {
    const seen = new Set();
    return state.sources.concat(state.avoidance.map(item => ({ source_url: item.source_url, source_title: item.source_title }))).filter(Boolean).map(source => {
      try {
        const url = new URL(source.source_url);
        if (url.protocol !== 'https:' || seen.has(url.href)) return '';
        seen.add(url.href);
        return `<a href="${safe(url.href)}" target="_blank" rel="noopener noreferrer">${safe(source.source_title)}</a>`;
      } catch (_) { return ''; }
    }).filter(Boolean).join(' · ');
  }

  function avoidanceMarkup() {
    const items = state.avoidance.map(item => {
      const titleText = (_isEn() && _AVOID_TITLE_EN[item.title]) ? _AVOID_TITLE_EN[item.title] : item.title;
      const reasonText = (_isEn() && _AVOID_REASON_EN[item.reason]) ? _AVOID_REASON_EN[item.reason] : item.reason;
      return `<article class="nf-limit-item"><span class="nf-limit-level">${item.level === 'avoid' ? _t('Cần tránh', 'Avoid') : _t('Nên hạn chế', 'Limit')}</span><strong>${safe(titleText)}</strong><p>${safe(reasonText)}</p></article>`;
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
    return `<p class="nf-limit-note">${safe(noteText)}</p>${items ? `<div class="nf-limit-items">${items}</div>` : ''}`;
  }

  const _NF_SESSION_KEY = 'medimind_nutrition_session_v1';

  function _readNutritionSession() {
    try {
      const raw = sessionStorage.getItem(_NF_SESSION_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch (_) {
      return {};
    }
  }

  function _saveNutritionSession(patch) {
    try {
      const prev = _readNutritionSession();
      const next = { ...prev, ...patch };
      sessionStorage.setItem(_NF_SESSION_KEY, JSON.stringify(next));
    } catch (_) { /* Ignore storage quota errors. */ }
  }

  function show(stage) {
    state.stage = stage;
    ['search', 'type', 'results', 'detail'].forEach(name => { el('nf-' + name).hidden = name !== stage; });
    el('nf-evidence').hidden = !state.lastData || (stage !== 'results' && stage !== 'detail');
    if (stage === 'results') { el('nf-recipe-source').innerHTML = ''; el('nf-recipe-source').hidden = true; }
    const label = state.query ? state.query.charAt(0).toLocaleUpperCase(_isEn() ? 'en-US' : 'vi-VN') + state.query.slice(1) : '';
    document.querySelectorAll('#doctor-tab .nf-query-label').forEach(node => { node.textContent = label; });
    if (stage === 'search' || stage === 'results' || stage === 'detail') {
      _saveNutritionSession({
        stage,
        query: state.query || '',
        activeRecipe: stage === 'detail' ? (state.activeRecipe || null) : null
      });
    }
    if (window.scrollY > 200) {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
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

  function _trMealRoleTag(r) {
    if (state.type === 'drink') return _t('NƯỚC UỐNG', 'DRINK');
    const meal = r.meal_time || 'dinner';
    const role = r.dish_role || 'main';
    const mealMapVi = { breakfast: '☀️ Bữa sáng', lunch: '🍱 Bữa trưa', dinner: '🌙 Bữa tối', snack: '🍵 Bữa phụ' };
    const mealMapEn = { breakfast: '☀️ Breakfast', lunch: '🍱 Lunch', dinner: '🌙 Dinner', snack: '🍵 Snack' };
    const roleMapEn = { main: 'Main Dish', soup: 'Soup', side: 'Side/Veg', staple: 'One-Dish Meal', drink: 'Drink/Dessert' };
    const mStr = _isEn() ? (mealMapEn[meal] || meal) : (mealMapVi[meal] || r.meal_label || meal);
    const rStr = _isEn() ? (roleMapEn[role] || role) : (r.dish_role_label || role);
    return `${mStr} · ${rStr}`;
  }

  function renderContext(data) {
    const profile = data.profile_context || {};
    const allergies = Array.isArray(profile.allergies) ? profile.allergies : [];
    const allergyEn = { 'trứng': 'egg', 'sữa động vật': 'milk', 'đậu nành': 'soy', 'gluten': 'gluten',
      'tôm/tép': 'shrimp', 'cua/ghẹ': 'crab', 'hải sản có vỏ': 'shellfish', 'hải sản': 'seafood',
      'cá': 'fish', 'đậu phộng/lạc': 'peanuts', 'hạt cây': 'tree nuts', 'mè/vừng': 'sesame' };
    const allergyText = (_isEn() ? allergies.map(value => allergyEn[value] || value) : allergies).join(', ');
    const preferences = Array.isArray(data.query_preferences) ? data.query_preferences : [];
    const preferenceEn = { 'Ít/không thêm đường': 'Less/no added sugar', 'Không cay': 'Mild food',
      'Ít dầu mỡ': 'Less oil', 'Ít muối': 'Less salt' };
    const bmiCategoryEn = { 'Thiếu cân': 'Underweight', 'Trong khoảng tham chiếu': 'Reference range',
      'Thừa cân': 'Overweight', 'Béo phì': 'Obesity' };
    const metrics = [
      profile.height_cm ? { icon: '↟', value: `${profile.height_cm} cm` } : null,
      profile.weight_kg ? { icon: '▣', value: `${profile.weight_kg} kg` } : null,
      profile.bmi ? { icon: '▥', value: `BMI ${profile.bmi}` } : null
    ].filter(Boolean);
    const profileTitle = profile.allergy_needs_review
      ? _t('Cần làm rõ dị ứng trong hồ sơ', 'Please clarify your profile allergy')
      : profile.used ? _t('Đã áp dụng hồ sơ của bạn', 'Your profile is applied')
        : _t('Gợi ý theo mô tả bạn nhập', 'Suggestions from your search');
    const allergySummary = profile.allergy_needs_review
      ? _t('Tên dị ứng chưa được nhận diện; hệ thống chưa tự gợi ý món.', 'Unrecognized allergy; automatic suggestions are paused.')
      : allergies.length ? `${_t('Dị ứng đã khai báo:', 'Declared allergies:')} ${allergyText} · ${_t('đã loại món chứa hải sản', 'seafood recipes excluded')}`
        : _t('Chưa khai báo dị ứng thực phẩm (chưa xác minh nếu có dị ứng riêng)', 'No food allergies declared (not verified for personal allergies)');
    const allergyVerificationHtml = profile.allergy_verification_note
      ? `<div class="nf-allergy-safe-notice">🛡️ <b>${_t('Lưu ý dị ứng:', 'Allergy safety note:')}</b> ${safe(profile.allergy_verification_note)}</div>`
      : '';
    el('nf-context').innerHTML = `<div class="nf-context-main${metrics.length ? '' : ' nf-context-main--no-metrics'}">${metrics.length ? `<div class="nf-context-metrics">${metrics.map(item => `<span class="nf-context-metric"><span aria-hidden="true">${item.icon}</span><b>${safe(item.value)}</b></span>`).join('')}</div>` : ''}<div class="nf-context-copy"><span class="nf-context-symbol" aria-hidden="true">☷</span><div><strong>${safe(profileTitle)}</strong><p>${profile.bmi_category ? `${safe(_isEn() ? bmiCategoryEn[profile.bmi_category] || profile.bmi_category : profile.bmi_category)} · ` : ''}${safe(allergySummary)}</p></div></div><button type="button" class="nf-profile-link">${_t('Sửa hồ sơ →', 'Edit profile →')}</button></div>${preferences.length ? `<div class="nf-preferences">${preferences.map(value => `<span class="nf-preference-chip">${safe(_isEn() ? preferenceEn[value] || value : value)}</span>`).join('')}</div>` : ''}${allergyVerificationHtml}`;
    el('nf-context').hidden = false;
  }

  function mealCombos() {
    const data = state.lastData;
    const usable = combo => Array.isArray(combo?.dishes)
      && combo.dishes.length >= 2
      && combo.dishes.every(dish => dish?.recipe && typeof dish.recipe === 'object');
    const combos = Array.isArray(data?.meal_combos) ? data.meal_combos.filter(usable) : [];
    if (combos.length) return combos;
    return usable(data?.full_meal_set) ? [data.full_meal_set] : [];
  }

  function renderFullMeal() {
    const wrap = el('nf-full-meal-wrap');
    if (!wrap) return;
    const combos = mealCombos();
    if (!combos.length || state.type === 'drink') {
      wrap.innerHTML = '';
      wrap.hidden = true;
      return;
    }

    const activeIdx = state.activeComboIndex || 0;
    const currentCombo = combos[activeIdx] || combos[0];

    let comboBarMarkup = '';
    if (combos.length > 1) {
      comboBarMarkup = `
        <div class="nf-combo-bar" role="tablist" aria-label="${_t('Chọn combo mâm cơm', 'Select meal combo')}">
          ${combos.map((c, i) => {
            const isActive = i === activeIdx;
            const emoji = i === 0 ? '🍱' : i === 1 ? '🍲' : i === 2 ? '🥗' : i === 3 ? '🥘' : i === 4 ? '🍜' : '🍛';
            return `
              <button type="button" class="nf-combo-tab ${isActive ? 'active' : ''}" data-nf-combo="${i}" role="tab" aria-selected="${isActive}">
                <span class="nf-combo-tab-icon">${emoji}</span>
                <span class="nf-combo-tab-text">
                  <strong class="nf-combo-tab-title">${safe(c.name || `Combo ${i + 1}`)}</strong>
                </span>
              </button>
            `;
          }).join('')}
          <button type="button" class="nf-combo-tab nf-combo-refresh-tab" id="nf-btn-refresh-combos" title="${_t('Đổi mâm cơm khác từ kho ứng viên hợp lệ', 'Refresh meal suggestions')}">
            <span class="nf-combo-tab-icon">🔄</span>
            <span class="nf-combo-tab-text">
              <strong class="nf-combo-tab-title">${_t('Đổi món khác', 'Refresh')}</strong>
              <span class="nf-combo-tab-badge">${_t('Làm mới', 'New options')}</span>
            </span>
          </button>
        </div>
      `;
    }

    const dishesMarkup = currentCombo.dishes.map((item, index) => {
      const r = item.recipe;
      const roleTag = _isEn()
        ? (item.role === 'staple' ? 'Staple' : item.role === 'main' ? 'Main dish' : item.role === 'soup' ? 'Soup' : 'Vegetable / side')
        : (item.role_label || (item.role === 'staple' ? 'Tinh bột chủ lực' : 'Món ăn trong bữa'));
      const titleFor = _recipeTitle(r);
      return `
        <article class="nf-meal-dish-card" data-nf-meal-dish="${index}" role="button" tabindex="0" aria-label="${safe(_t('Xem công thức', 'View recipe'))}: ${safe(titleFor)}">
          <div class="nf-meal-dish-art">
            ${recipeImage(r)}
            <span class="nf-meal-dish-role">${safe(roleTag)}</span>
          </div>
          <div class="nf-meal-dish-body">
            <div class="nf-dish-heading"><strong>${safe(titleFor)}</strong>${kcal(r.calories) ? `<span class="nf-kcal">${kcal(r.calories)}</span>` : ''}</div>
            ${r.imported ? '' : `<p class="nf-meal-dish-sub">${safe(_recipeSubtitle(r))}</p>`}
            ${r.key_nutrients ? `<div class="nf-nutrients-badge"><span class="nf-badge-icon">🧬</span> <b>${_t('Dưỡng chất:', 'Nutrients:')}</b> ${safe(r.key_nutrients)}</div>` : ''}
            ${r.recommendation_reason ? `<div class="nf-reason-compact"><span class="nf-reason-header"><svg viewBox="0 0 20 20" fill="currentColor" width="11" height="11"><path d="M11 3a1 1 0 10-2 0v1a1 1 0 102 0V3zM15.657 5.757a1 1 0 00-1.414-1.414l-.707.707a1 1 0 001.414 1.414l.707-.707zM18 10a1 1 0 01-1 1h-1a1 1 0 110-2h1a1 1 0 011 1zM5.05 6.464A1 1 0 106.464 5.05l-.707-.707a1 1 0 001.414 1.414l.707.707zM5 10a1 1 0 01-1 1H3a1 1 0 110-2h1a1 1 0 011 1zM8 16v-1h4v1a2 2 0 11-4 0zM12 14H8a4 4 0 01-.8-7.92 4.002 4.002 0 017.6 0A4 4 0 0112 14z"/></svg> ${_t('Vì sao được gợi ý?', 'Why suggested?')}</span><p>${safe(_recipeReason(r))}</p></div>` : ''}
            <div class="nf-meal-dish-footer">
              <span>◷ ${safe(_trTime(r.cooking_time || ''))}</span>
              <b>${_t('Xem công thức →', 'View recipe →')}</b>
            </div>
          </div>
        </article>`;
    }).join('');

    const mealLabel = _isEn()
      ? (currentCombo.meal_time === 'breakfast' ? 'Breakfast' : currentCombo.meal_time === 'lunch' ? 'Lunch' : 'Dinner')
      : (currentCombo.meal_label || 'Bữa tối');

    const titleText = _isEn()
      ? (currentCombo.name ? `${currentCombo.name}: One meal suggestion` : 'One meal suggestion')
      : (currentCombo.title || 'Mâm cơm đủ món cân bằng');

    const staple = currentCombo.dishes.find(dish => dish.role === 'staple');
    const stapleLabel = staple ? _t('Tinh bột trong mâm:', 'Staple in the meal:') : _t('Tinh bột ăn kèm:', 'Accompanying staple:');
    const stapleValue = staple ? _recipeTitle(staple.recipe) : (_isEn()
      ? 'Choose a staple you can eat for your portion; it is not included in the kcal shown.'
      : currentCombo.staple_text || 'Chọn loại tinh bột bạn dùng được theo khẩu phần cá nhân.');

    const rationaleText = _isEn()
      ? 'The dishes were combined from recipes that passed the declared ingredient filters. Review portions and seasoning before use.'
      : currentCombo.rationale;
    const calorieValues = currentCombo.dishes.map(dish => dish.recipe.calories)
      .filter(value => Number.isFinite(value) && value >= 0);
    const mealKcal = kcal(currentCombo.total_calories
      ?? (calorieValues.length ? calorieValues.reduce((sum, value) => sum + value, 0) : null));
    const coveredDishes = currentCombo.calorie_covered_dishes ?? calorieValues.length;
    const coverage = `${coveredDishes}/${currentCombo.dishes.length}`;

    wrap.innerHTML = `
      ${comboBarMarkup}
      <div class="nf-meal-hero">
        <div class="nf-meal-hero-badge">
          <span>🍱 ${_t(currentCombo.name ? `${currentCombo.name.toUpperCase()} · BỮA ĂN ĐẦY ĐỦ` : 'MÂM CƠM GỢI Ý CHO 1 BỮA', 'ONE MEAL SUGGESTION')}</span>
          <span class="nf-meal-time-tag">${safe(mealLabel)}</span>
        </div>
        <h2 class="nf-meal-hero-title">${safe(titleText)}</h2>
        ${mealKcal ? `<div class="nf-meal-energy">
          <div class="nf-meal-energy-total">
            <span class="nf-meal-energy-icon" aria-hidden="true">🔥</span>
            <div>
              <span>${_t(`Năng lượng theo công thức · ${coverage} món`, `Recipe energy estimate · ${coverage} dishes`)}</span>
              <strong>${mealKcal}</strong>
            </div>
          </div>
        </div>` : `<p class="nf-subtitle">${_t('Các công thức trong mâm chưa có số liệu kcal.', 'No kcal data is available for these recipes.')}</p>`}
        <div class="nf-meal-hero-rationale">
          <div class="nf-rationale-head">
            <svg viewBox="0 0 20 20" fill="currentColor" width="14" height="14" aria-hidden="true"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"/></svg>
            <strong>${_t('Vì sao chọn các món này?', 'Why these dishes?')}</strong>
          </div>
          <p>${safe(rationaleText)}</p>
        </div>
        <div class="nf-meal-staple">
          <span class="nf-staple-icon">🍚</span>
          <span><b>${safe(stapleLabel)}</b> ${safe(stapleValue)}</span>
        </div>
      </div>
      <div class="nf-meal-dishes-grid">
        ${dishesMarkup}
      </div>
      <div class="nf-switch-banner">
        <button type="button" class="nf-switch-btn" id="nf-btn-switch-singles">
          <span>🍲 ${_t('Xem món lẻ đại diện (Phở, bún, mì, miến, hủ tiếu, cháo...)', 'Browse representative one-dish meals (Phở, noodles, congee...)')}</span>
          <span class="nf-arrow">→</span>
        </button>
      </div>`;
  }

  function updateViewModeUI() {
    const switcher = el('nf-mode-switcher');
    const fullMealWrap = el('nf-full-meal-wrap');
    const cards = el('nf-cards');
    const loadMore = el('nf-load-more');

    // Chế độ Nước uống: tuyệt đối ẩn bộ chuyển đổi mâm cơm và bộ lọc bữa ăn
    if (state.type === 'drink') {
      state.viewMode = 'single_dishes';
      if (switcher) switcher.hidden = true;
      if (fullMealWrap) { fullMealWrap.hidden = true; fullMealWrap.innerHTML = ''; }
      if (cards) cards.hidden = false;
      if (loadMore) loadMore.hidden = !state.lastData?.has_more;
      return;
    }

    const hasFullMeal = state.type === 'food' && mealCombos().length > 0;
    if (!hasFullMeal && state.viewMode === 'full_meal') {
      state.viewMode = 'single_dishes';
    }

    if (switcher) switcher.hidden = !hasFullMeal;
    if (switcher) {
      switcher.querySelectorAll('.nf-mode-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.nfView === state.viewMode);
      });
    }

    if (hasFullMeal && state.viewMode === 'full_meal') {
      if (fullMealWrap) fullMealWrap.hidden = false;
      if (cards) cards.hidden = true;
      if (loadMore) loadMore.hidden = true;
    } else {
      if (fullMealWrap) fullMealWrap.hidden = true;
      if (cards) cards.hidden = false;
      if (loadMore) loadMore.hidden = !state.lastData?.has_more;
    }

  }

  function renderCards() {
    el('nf-cards').innerHTML = state.recipes.map((recipe, index) => {
      const tagText = _trMealRoleTag(recipe);
      return `
      <button type="button" class="nf-card" data-nf-recipe="${index}">
        <span class="nf-art">${recipeImage(recipe)}<span class="nf-art-tag">${safe(tagText)}</span></span>
        <span class="nf-card-content">
          <strong>${safe(_recipeTitle(recipe))}</strong>
          ${recipe.imported ? '' : `<p>${safe(_recipeSubtitle(recipe))}</p>`}
          ${kcal(recipe.calories) ? `<span class="nf-kcal">${kcal(recipe.calories)} · ${_t('ước tính theo nguồn', 'source estimate')}</span>` : ''}
          ${recipe.key_nutrients ? `<span class="nf-nutrients-badge"><span class="nf-badge-icon">🧬</span> <b>${_t('Dưỡng chất:', 'Nutrients:')}</b> ${safe(recipe.key_nutrients)}</span>` : ''}
          ${recipe.recommendation_reason ? `<span class="nf-reason"><span class="nf-reason-header">${_t('Vì sao chọn món này', 'Why this dish')}</span><span class="nf-reason-text">${safe(_recipeReason(recipe))}</span></span>` : ''}
          <span class="nf-card-footer"><span>◷ ${safe(_trTime(recipe.cooking_time || ''))}</span><b>${_t('Xem chi tiết →', 'View recipe →')}</b></span>
        </span>
      </button>`;
    }).join('');
  }

  function _getSavedRecipeIds() {
    try {
      const raw = localStorage.getItem('medimind_saved_recipes');
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? new Set(parsed.map(String)) : new Set();
    } catch (_) {
      return new Set();
    }
  }

  function _toggleSavedRecipe(recipeId) {
    if (!recipeId) return false;
    const saved = _getSavedRecipeIds();
    const id = String(recipeId);
    const nextState = !saved.has(id);
    if (nextState) saved.add(id);
    else saved.delete(id);
    try {
      localStorage.setItem('medimind_saved_recipes', JSON.stringify(Array.from(saved)));
    } catch (_) { /* Ignore storage quota errors. */ }
    return nextState;
  }

  function _formatMacroGrams(value) {
    if (value === null || value === undefined || value === '') return '—';
    const n = Number(value);
    if (!Number.isFinite(n) || n < 0) return '—';
    const rounded = n < 20 ? n.toFixed(1) : String(Math.round(n));
    return `${rounded} g`;
  }

  function renderDetail(recipe) {
    state.activeRecipe = recipe;
    const translation = _recipeEn(recipe);
    const displayTitle = _recipeTitle(recipe);
    const cleanIngredients = (recipe.ingredients || []).filter(item => {
      const name = String(item?.name || '').trim();
      return name && name.toUpperCase() !== 'N/A';
    });
    const ingredients = cleanIngredients.map((item, i) => {
      const name = safe(translation?.ingredients?.[i] || item.name);
      const qty = [item.amount, item.unit].map(v => String(v || '').trim()).filter(Boolean).join(' ');
      return `<div class="nf-ingredient"><span class="nf-ingredient-name"><span class="nf-ingredient-dot" aria-hidden="true"></span><span>${name}</span></span>${qty ? `<b>${safe(qty)}</b>` : ''}</div>`;
    }).join('');
    const steps = (translation?.steps || recipe.steps || [])
      .map(s => String(s || '').trim())
      .filter(s => s && s.toUpperCase() !== 'N/A')
      .map((step, i) => `<div class="nf-step"><span class="nf-step-number">${i + 1}</span><span>${safe(step)}</span></div>`)
      .join('');
    const avoid = (translation?.avoid || recipe.avoid || [])
      .map(x => safe(_trRecipeNote(x)))
      .filter(Boolean)
      .join('<br>');

    const servingLabel = recipe.servings
      ? safe(recipe.servings)
      : _t('1 người', '1 serving');
    const rawTag = _trMealRoleTag(recipe);
    const cleanTag = rawTag.replace(/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/gu, '').trim() || rawTag;
    const timeLabel = _trTime(recipe.cooking_time || '') || _t('Xem cách làm', 'See steps');

    const rawCal = recipe.calories ?? recipe.per_person_calories;
    const calNum = (rawCal !== null && rawCal !== undefined && rawCal !== '' && Number.isFinite(Number(rawCal)) && Number(rawCal) >= 0)
      ? Math.round(Number(rawCal))
      : null;
    const calDisplay = calNum !== null ? `${calNum.toLocaleString(_isEn() ? 'en-US' : 'vi-VN')} kcal` : '—';
    const proDisplay = _formatMacroGrams(recipe.protein);
    const fatDisplay = _formatMacroGrams(recipe.fat);
    let rawCarb = recipe.carbs ?? recipe.carb ?? recipe.carbohydrate;
    const hasPro = recipe.protein !== null && recipe.protein !== undefined && recipe.protein !== '' && Number.isFinite(Number(recipe.protein));
    const hasFat = recipe.fat !== null && recipe.fat !== undefined && recipe.fat !== '' && Number.isFinite(Number(recipe.fat));
    if ((rawCarb === null || rawCarb === undefined || rawCarb === '') && calNum !== null && hasPro && hasFat) {
      rawCarb = Math.max(0, Math.round((calNum - (Number(recipe.protein) * 4) - (Number(recipe.fat) * 9)) / 4));
    }
    const carbDisplay = _formatMacroGrams(rawCarb);

    const recipeKey = recipe.id || displayTitle;
    const isSaved = _getSavedRecipeIds().has(String(recipeKey));

    const iconForkKnife = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="15" height="15" aria-hidden="true"><path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2"/><path d="M7 2v20"/><path d="M21 15V2v0a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7"/></svg>';
    const iconClock = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="15" height="15" aria-hidden="true"><circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15.5 14"/></svg>';
    const iconUsers = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="15" height="15" aria-hidden="true"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>';
    const iconFlame = '<svg viewBox="0 0 24 24" fill="currentColor" width="17" height="17" aria-hidden="true"><path d="M12.5 2.2c.3 2.4-.5 4.2-2 5.6-1.4 1.3-2.3 2.8-2.3 4.5 0 1.3.7 2.5 1.8 3.2-.4-.8-.3-1.8.4-2.6.6-.7 1.3-1.2 1.6-2.2 1.4 1.1 2.2 2.4 2.2 3.9 0 .9-.3 1.7-.9 2.3 1.6-.7 2.7-2.4 2.7-4.5 0-3.2-1.8-6.4-3.5-10.2ZM12 22a7 7 0 0 1-7-7c0-2.6 1.2-5 3.3-7.1.3 1.4 1 2.4 2 3.3-.2-1.9.4-4.1 2.4-6.3.3 2.1 1.6 3.7 2.9 5.3 1.1 1.4 1.9 2.9 1.9 4.8A7 7 0 0 1 12 22Z"/></svg>';
    const iconArm = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="18" height="18" aria-hidden="true"><path d="M15 9.5c1.5-1.5 4-1 4.5 1.2.4 1.9-.6 4.8-3 6.3-2.2 1.4-5.5 2-8.5 2-2.2 0-4-1.6-4-3.8 0-1.6.9-3.2 2.2-4.7L8.5 7l2.5 1.2-.8 2.4c1.4-.9 3.4-.9 4.8-1.1Z"/><path d="M10.2 10.6c1.5-.3 2.8.2 3.5 1.1"/></svg>';
    const iconDrop = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="18" height="18" aria-hidden="true"><path d="M12 2.69l5.66 5.66a8 8 0 1 1-11.31 0z"/></svg>';
    const iconWheat = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="18" height="18" aria-hidden="true"><path d="M2 22 16 8"/><path d="M3.47 12.53 5 11l1.53 1.53a3.5 3.5 0 0 1 0 4.94L5 19l-1.53-1.53a3.5 3.5 0 0 1 0-4.94Z"/><path d="M7.47 8.53 9 7l1.53 1.53a3.5 3.5 0 0 1 0 4.94L9 15l-1.53-1.53a3.5 3.5 0 0 1 0-4.94Z"/><path d="M11.47 4.53 13 3l1.53 1.53a3.5 3.5 0 0 1 0 4.94L13 11l-1.53-1.53a3.5 3.5 0 0 1 0-4.94Z"/><path d="M20 2h2v2a4 4 0 0 1-4 4h-2V6a4 4 0 0 1 4-4Z"/></svg>';
    const iconBasket = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" width="17" height="17" aria-hidden="true"><path d="m5 11 4-7"/><path d="m19 11-4-7"/><path d="M2 11h20"/><path d="m3.5 11 1.6 7.4a2 2 0 0 0 2 1.6h9.8c.9 0 1.8-.7 2-1.6l1.7-7.4"/><path d="m9 11 1 9"/><path d="M4.5 15.5h15"/><path d="m15 11-1 9"/></svg>';
    const iconBookmark = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="18" height="18" aria-hidden="true"><path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/></svg>';
    const iconInfo = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="20" height="20" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>';

    const defaultNote = safe(_t('Kiểm tra nguyên liệu, dị ứng, gia vị và khẩu phần theo hướng dẫn ăn uống cá nhân.', 'Check ingredients, allergies, seasoning, and portions according to personal dietary guidance.'));

    el('nf-detail-content').innerHTML = `<div class="nf-detail-grid">
      <div class="nf-detail-left">
        <div class="nf-detail-visual">
          <div class="nf-art nf-detail-photo-wrap">
            ${recipeImage(recipe)}
            <button type="button" class="nf-bookmark-btn ${isSaved ? 'is-saved' : ''}" data-nf-bookmark="${safe(recipeKey)}" aria-pressed="${isSaved ? 'true' : 'false'}" title="${_t('Lưu công thức', 'Save recipe')}" aria-label="${_t('Lưu công thức', 'Save recipe')}">${iconBookmark}</button>
          </div>
          <div class="nf-detail-meta-bar">
            <span class="nf-detail-meta-item">${iconClock}<span>${safe(timeLabel)}</span></span>
            <span class="nf-detail-meta-item">${iconForkKnife}<span>${safe(cleanTag)}</span></span>
            <span class="nf-detail-meta-item">${iconUsers}<span>${servingLabel}</span></span>
          </div>
        </div>
        <div class="nf-nutrition-card">
          <div class="nf-nutrition-head"><strong>${_t('Giá trị dinh dưỡng', 'Nutrition facts')}</strong> <span>(${_t('ước tính / khẩu phần', 'est. / serving')})</span></div>
          <div class="nf-nutrition-grid">
            <div class="nf-nutri-tile is-kcal">
              <span class="nf-nutri-icon nf-nutri-icon-amber">${iconFlame}</span>
              <b>${safe(calDisplay)}</b>
              <span>${_t('Năng lượng', 'Calories')}</span>
            </div>
            <div class="nf-nutri-tile">
              <span class="nf-nutri-icon">${iconArm}</span>
              <b>${safe(proDisplay)}</b>
              <span>Protein</span>
            </div>
            <div class="nf-nutri-tile">
              <span class="nf-nutri-icon">${iconDrop}</span>
              <b>${safe(fatDisplay)}</b>
              <span>${_t('Chất béo', 'Fat')}</span>
            </div>
            <div class="nf-nutri-tile">
              <span class="nf-nutri-icon">${iconWheat}</span>
              <b>${safe(carbDisplay)}</b>
              <span>Carb</span>
            </div>
          </div>
        </div>
      </div>
      <article class="nf-detail-copy">
        <div class="nf-detail-role-pill">${iconForkKnife}<span>${safe(cleanTag)}</span></div>
        <h2>${safe(displayTitle)}</h2>
        <p class="nf-subtitle nf-detail-subtitle">${safe(_recipeSubtitle(recipe))}</p>
        ${calNum !== null ? `<div class="nf-detail-kcal-pill">${iconFlame}<span>${calNum.toLocaleString(_isEn() ? 'en-US' : 'vi-VN')} kcal / ${_t('khẩu phần', 'serving')}</span></div>` : ''}
        ${recipe.key_nutrients ? `<div class="nf-nutrients-badge" style="margin: 14px 0;"><span class="nf-badge-icon">🧬</span> <b>${_t('Dưỡng chất then chốt:', 'Key nutrients:')}</b> ${safe(recipe.key_nutrients)}</div>` : ''}
        ${recipe.recommendation_reason ? `<div class="nf-recommendation-box"><strong>${_t('Vì sao chọn món này?', 'Why this dish?')}</strong><p class="nf-recommendation-desc">${safe(_recipeReason(recipe))}</p>${recipe.ai_caution ? `<p class="nf-ai-caution">${safe(recipe.ai_caution)}</p>` : ''}</div>` : ''}
        <h3 class="nf-detail-sec-head">${iconBasket}<span>${_t('Nguyên liệu', 'Ingredients')} (${servingLabel})</span></h3>
        <div class="nf-ingredients">${ingredients || `<div class="nf-ingredient"><span class="nf-ingredient-name"><span class="nf-ingredient-dot" aria-hidden="true"></span><span>${safe(displayTitle)}</span></span></div>`}</div>
        <h3 class="nf-detail-sec-head">${iconBasket}<span>${_t('Cách chế biến', 'Preparation Steps')}</span></h3>
        <div class="nf-steps-panel"><div class="nf-steps">${steps}</div></div>
        <aside class="nf-avoid nf-avoid-callout"><span class="nf-avoid-icon" aria-hidden="true">${iconInfo}</span><div><strong>${_t('Lưu ý công thức', 'Recipe note')}</strong><p>${avoid || defaultNote}</p></div></aside>
      </article>
    </div>`;
    el('nf-recipe-source').innerHTML = recipeCredit(recipe);
    el('nf-recipe-source').hidden = !el('nf-recipe-source').innerHTML;
  }

  function applyResultsCopy() {
    if (!el('nf-results-title')) return;
    el('nf-results-title').textContent = state.type === 'drink'
      ? _t('Gợi ý thức uống', 'Suggested drinks')
      : _t('Gợi ý món ăn', 'Suggested dishes');
    const data = state.lastData;
    if (!data) return;
    renderContext(data);

    // Render khối ưu tiên lâm sàng: Bù nước & Điện giải
    const hydAlert = el('nf-hydration-alert');
    if (hydAlert) {
      if (data.hydration_priority && data.hydration_priority.active) {
        const hyd = data.hydration_priority;
        hydAlert.innerHTML = `
          <div class="nf-hydration-card">
            <div class="nf-hydration-head">
              <span class="nf-hydration-pill">${safe(hyd.badge || '💧 ƯU TIÊN Y KHOA: BÙ NƯỚC & ĐIỆN GIẢI')}</span>
              ${hyd.source_url ? `<a href="${safe(hyd.source_url)}" target="_blank" rel="noopener noreferrer" class="nf-hydration-src">${safe(hyd.source_title || 'NIDDK / NHS')} ↗</a>` : ''}
            </div>
            <h3 class="nf-hydration-title">${safe(hyd.title || 'Ưu tiên bù nước và điện giải trước khi chọn món ăn')}</h3>
            <p class="nf-hydration-lead">${safe(hyd.lead || '')}</p>
            <ul class="nf-hydration-list">
              ${(hyd.guidelines || []).map(g => `<li><span class="nf-check-icon">✓</span><span>${safe(g)}</span></li>`).join('')}
            </ul>
            ${hyd.red_flags ? `
              <div class="nf-hydration-warning">
                <span class="nf-warn-icon">⚠️</span>
                <div>
                  <strong>${_t('Dấu hiệu nguy hiểm cần đến bệnh viện ngay:', 'Emergency warning signs:')}</strong>
                  <p>${safe(hyd.red_flags)}</p>
                </div>
              </div>
            ` : ''}
          </div>
        `;
        hydAlert.hidden = false;
      } else {
        hydAlert.innerHTML = '';
        hydAlert.hidden = true;
      }
    }
    const stats = data.catalog;
    const srcLabel = stats?.source === 'Danh mục mẫu' ? _t('Danh mục mẫu', 'Sample Catalog') : (stats?.source || '');
    el('nf-catalog-stats').textContent = stats
      ? (_isEn()
        ? `${stats.cuisine === 'VN' ? 'Vietnamese Catalog' : 'Recipe Catalog'}${srcLabel ? ' · ' + srcLabel : ''}: ${stats.total} recipes · ${data.catalog_type_count} ${state.type === 'drink' ? 'drinks' : 'dishes'} · ${data.eligible_count} passed ingredient rules · ${data.considered_count} candidates considered`
        : `${stats.cuisine === 'VN' ? 'Kho món Việt' : 'Kho dữ liệu'}${srcLabel ? ' · ' + srcLabel : ''}: ${stats.total} công thức · ${data.catalog_type_count} ${state.type === 'drink' ? 'nước uống' : 'món ăn'} · ${data.eligible_count} qua bộ lọc nguyên liệu · ${data.considered_count} ứng viên được xem xét`)
      : '';
    el('nf-avoidance-content').innerHTML = avoidanceMarkup();
    el('nf-avoidance').querySelector('summary').textContent = _t('Nên hạn chế / cần tránh', 'Foods to limit or avoid');
    const notice = el('nf-notice');
    const addedPrefix = state.lastAddedCount
      ? (_isEn() ? `Added ${state.lastAddedCount} more suggestion${state.lastAddedCount > 1 ? 's' : ''}. ` : `Đã thêm ${state.lastAddedCount} gợi ý mới. `)
      : '';
    notice.textContent = (addedPrefix + (data.provider_status === 'ai_ranked' ? '' : _trNotice(data))).trim();
    notice.hidden = !notice.textContent;
    if (el('nf-question')) el('nf-question').textContent = _trQuestion(data.clarification_question || '');
    const limitations = _isEn()
      ? (Array.isArray(data.limitations) && data.limitations.length ? 'Source data and ingredient tags may be incomplete; check portions, preparation and cross-contact.' : '')
      : (Array.isArray(data.limitations) ? data.limitations.join(' ') : '');
    const excluded = (!_isEn() && data.excluded_count) ? `${data.excluded_count} món đã loại trước khi xếp hạng.` : '';
    const excludedEn = (_isEn() && Array.isArray(data.excluded) && data.excluded.length) ? `Excluded ${data.excluded.length} item(s) before ranking via ingredient safety rules.` : '';
    el('nf-selection-copy').textContent = [
      _trSelectionExplanation(data) || _t('Danh sách tham khảo chung, chưa xác nhận mức độ phù hợp theo tình trạng của bạn.', 'General reference suggestions; suitability for your specific clinical condition has not been verified.'),
      limitations,
      excluded || excludedEn,
      _t('Kcal được ước tính theo công thức gốc, chưa quy đổi theo suất ăn.', 'Kcal are estimates from the source recipes before conversion to individual servings.'),
      data.profile_context?.bmi ? _t('BMI ở người lớn chỉ là chỉ số tham khảo, không tự quyết định mục tiêu kcal.', 'Adult BMI is only a reference and does not set a kcal target.') : ''
    ].filter(Boolean).join(' ');
    const sources = sourceLinks();
    el('nf-sources').innerHTML = sources ? `${_t('Hướng dẫn được cung cấp cho bộ gợi ý:', 'Reference guidelines for this suggestion set:')} ${sources}` : '';
    el('nf-edit-query').textContent = state.recipes.length
      ? _t('Bổ sung để gợi ý sát hơn →', 'Refine description →')
      : _t('Bổ sung mô tả →', 'Add more details →');
    el('nf-status').textContent = state.recipes.length || data.needs_clarification
      ? ''
      : _t('Chưa có món phù hợp. Hãy thử tìm kiếm khác.', 'No matching recipes found. Please try a different query.');
    el('nf-evidence').querySelector('summary').textContent = _t('Nguồn & lưu ý dữ liệu', 'Sources & data notes');
    el('nf-evidence').hidden = false;

    // Render mâm cơm 1 bữa ăn đủ món
    renderFullMeal();
    updateViewModeUI();
    renderCards();
  }

  async function chooseType(type, append = false, refresh = false) {
    if (state.request) state.request.abort();
    const controller = new AbortController();
    state.request = controller;
    state.type = type;
    if (el('nf-results')) el('nf-results').dataset.type = type;
    const previous = append ? state.recipes.slice() : [];
    const excludeIds = append
      ? previous.map(recipe => recipe.id)
      : (refresh && state.seenComboRecipeIds ? Array.from(state.seenComboRecipeIds) : []);
    if (!append) {
      state.recipes = [];
      state.lastData = null;
      state.lastAddedCount = 0;
      state.activeComboIndex = 0;
      state.viewMode = type === 'drink' ? 'single_dishes' : 'full_meal';
    }
    el('nf-results-title').textContent = type === 'drink'
      ? _t('Gợi ý thức uống', 'Suggested drinks')
      : _t('Gợi ý món ăn', 'Suggested dishes');
    if (!append) el('nf-cards').innerHTML = '';
    el('nf-load-more').disabled = true;
    if (!append) el('nf-load-more').hidden = true;
    el('nf-notice').hidden = true;
    el('nf-context').hidden = true;
    if (el('nf-hydration-alert')) { el('nf-hydration-alert').hidden = true; el('nf-hydration-alert').innerHTML = ''; }
    el('nf-evidence').hidden = true;
    el('nf-evidence').open = false;
    el('nf-sources').hidden = true;
    el('nf-clarification').hidden = true;
    el('nf-avoidance').hidden = true;
    el('nf-avoidance').open = false;
    el('nf-catalog-stats').hidden = true;
    if (el('nf-mode-switcher')) el('nf-mode-switcher').hidden = true;
    if (el('nf-full-meal-wrap')) { el('nf-full-meal-wrap').hidden = true; el('nf-full-meal-wrap').innerHTML = ''; }
    const retryButton = el('nf-retry');
    retryButton.hidden = true;
    retryButton.onclick = null;
    el('nf-status').textContent = _t('Đang tìm gợi ý cho bạn…', 'Finding suggestions for you…');
    if (!append) show('results');
    let failureMessage = _t('Mất kết nối khi tải gợi ý món.', 'The connection was interrupted while loading recipes.');
    try {
      const response = await fetch('/api/nutrition/options', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ condition: state.query, recipe_type: type, exclude_recipe_ids: excludeIds }), signal: controller.signal });
      failureMessage = _t('Máy chủ chưa trả được gợi ý món.', 'The server could not return recipe suggestions.');
      if (!response.ok) throw new Error(`Nutrition options returned HTTP ${response.status}`);
      const body = await response.json();
      if (!body.success || !Array.isArray(body.data?.recipes)) throw new Error('Invalid nutrition options response');
      if (state.request !== controller) return;
      failureMessage = _t('Đã nhận gợi ý nhưng chưa hiển thị được.', 'Recipes were received but could not be displayed.');
      const incoming = body.data.recipes.filter(recipe => !previous.some(old => old.id === recipe.id));
      state.recipes = previous.concat(incoming);
      state.lastData = body.data;
      if (Array.isArray(body.data?.meal_combos)) {
        if (!state.seenComboRecipeIds) state.seenComboRecipeIds = new Set();
        body.data.meal_combos.forEach(c => {
          (c.dishes || []).forEach(d => {
            if (d.recipe?.id) state.seenComboRecipeIds.add(d.recipe.id);
          });
        });
      }
      state.lastAddedCount = append ? incoming.length : 0;
      el('nf-load-more').hidden = !body.data.has_more;
      state.sources = Array.isArray(body.data.sources) ? body.data.sources : [];
      state.avoidance = Array.isArray(body.data.avoidance) ? body.data.avoidance : [];
      state.avoidanceNote = body.data.avoidance_note || '';
      el('nf-catalog-stats').hidden = !body.data.catalog;
      el('nf-avoidance').hidden = !state.avoidance.length && !state.avoidanceNote;
      el('nf-clarification').hidden = !body.data.needs_clarification;
      el('nf-question').textContent = body.data.clarification_question || '';
      applyResultsCopy();
      el('nf-sources').hidden = !el('nf-sources').innerHTML;
    } catch (error) {
      if (state.request !== controller || error.name === 'AbortError') return;
      el('nf-status').textContent = failureMessage;
      retryButton.textContent = _t('Thử lại', 'Try again');
      retryButton.onclick = () => chooseType(type, append, refresh);
      retryButton.hidden = false;
    } finally {
      if (state.request === controller) {
        el('nf-load-more').disabled = false;
        state.request = null;
      }
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
        state.seenComboRecipeIds = new Set();
        show('type');
      });
      // Luồng khảo sát mới: bấm nút bắt đầu -> mở khảo sát -> lưu & áp dụng -> AI lọc món ra bữa ăn
      const surveyModal = el('nf-survey-modal');
      const startSurveyBtn = el('nf-start-survey-btn');
      const reviewSurveyBtn = el('nf-review-survey-btn');
      const closeSurveyModal = () => {
        if (!surveyModal) return;
        surveyModal.classList.add('hidden');
        surveyModal.classList.remove('flex');
        if (el('nf-search')) el('nf-search').classList.remove('invisible');
      };
      const openSurveyModal = async () => {
        if (!surveyModal) return;
        if (el('nf-search')) el('nf-search').classList.add('invisible');
        surveyModal.classList.remove('hidden');
        surveyModal.classList.add('flex');
        // Tự động điền sẵn dị ứng từ Profile ban đầu của user nếu có
        const avoidInput = el('nf-sv-avoid');
        if (avoidInput && !avoidInput.value.trim()) {
          const cachedAllergies = window.currentUser?.allergies || window.currentUserData?.allergies;
          if (cachedAllergies) {
            avoidInput.value = Array.isArray(cachedAllergies) ? cachedAllergies.join(', ') : String(cachedAllergies);
          } else {
            try {
              const res = await fetch('/api/auth/me');
              if (res.ok) {
                const me = await res.json();
                const al = me?.user?.allergies || me?.allergies;
                if (al) avoidInput.value = Array.isArray(al) ? al.join(', ') : String(al);
              }
            } catch (_) {}
          }
        }
      };
      if (startSurveyBtn && surveyModal) {
        startSurveyBtn.addEventListener('click', openSurveyModal);
      }
      if (reviewSurveyBtn && surveyModal) {
        reviewSurveyBtn.addEventListener('click', openSurveyModal);
      }
      if (el('nf-survey-close-btn')) el('nf-survey-close-btn').addEventListener('click', closeSurveyModal);
      if (el('nf-survey-cancel-btn')) el('nf-survey-cancel-btn').addEventListener('click', closeSurveyModal);
      // Tự động bỏ chọn "Không có" khi chọn bệnh nền, và ngược lại
      const condCheckboxes = Array.from(document.querySelectorAll('input[name="nf-sv-cond"]'));
      condCheckboxes.forEach(cb => {
        cb.addEventListener('change', () => {
          if (cb.value === 'Không có' && cb.checked) {
            condCheckboxes.forEach(other => { if (other !== cb) other.checked = false; });
          } else if (cb.value !== 'Không có' && cb.checked) {
            condCheckboxes.forEach(other => { if (other.value === 'Không có') other.checked = false; });
          }
        });
      });
      function _renderMealPlanView(data, mainTab = 'food', foodSubTab = 'single') {
        const plan = data?.daily_plan;
        if (!plan) return;
        const cardsEl = el('nf-cards');
        const ctxEl = el('nf-context');
        const emptyEl = el('nf-empty');
        const loadMoreEl = el('nf-load-more');
        if (emptyEl) emptyEl.hidden = true;
        if (loadMoreEl) loadMoreEl.hidden = true;
        document.querySelectorAll('.nf-query-label').forEach(n => { n.textContent = state.query; });

        const warnHtml = plan.calorie_warning
          ? `<div class="mt-2 rounded-xl border border-amber-400/40 bg-amber-500/15 px-3 py-2 text-xs text-amber-200">⚠️ ${plan.calorie_warning}</div>`
          : '';
        const aiNoteHtml = data.ai_rationale
          ? `<div class="mt-2 text-xs text-sky-200/90">✨ ${data.ai_rationale}</div>`
          : '';
        if (ctxEl) {
          ctxEl.hidden = false;
          ctxEl.innerHTML = `
            <div class="rounded-2xl border border-white/15 bg-slate-900/60 p-4 text-sm text-slate-100">
              <div class="flex flex-wrap items-center justify-between gap-2">
                <div><strong>Chỉ số năng lượng:</strong> BMR <strong>${plan.bmr} kcal</strong> · TDEE <strong>${plan.tdee} kcal</strong></div>
                <div class="text-emerald-300 font-semibold">Mục tiêu: ${plan.target_calories} kcal/ngày (Thực tế: ${plan.total_calories} kcal)</div>
              </div>
              ${aiNoteHtml}
              ${warnHtml}
            </div>`;
        }

        state.recipes = [];
        const regRecipe = (r) => {
          if (!r) return -1;
          const idx = state.recipes.length;
          state.recipes.push(r);
          return idx;
        };
        const imgTag = (r, altText) => {
          const src = r?.image_link || r?.source_image_url || '';
          return src
            ? `<img src="${src}" alt="${altText || ''}" class="w-16 h-16 sm:w-20 sm:h-20 rounded-xl object-cover shrink-0 border border-white/10 bg-slate-800" loading="lazy">`
            : `<div class="w-16 h-16 sm:w-20 sm:h-20 rounded-xl shrink-0 bg-slate-800/80 border border-white/10 flex items-center justify-center text-2xl">🍽️</div>`;
        };

        // 1. HTML Món lẻ theo bữa
        const singleMealsHtml = (plan.meals || []).map(meal => {
          const itemsHtml = (meal.items || []).map(item => {
            const idx = regRecipe(item.recipe);
            return `
              <button type="button" data-nf-recipe="${idx}" class="w-full text-left rounded-xl border border-white/15 bg-slate-900/70 hover:bg-slate-800/90 p-3 transition flex items-center gap-3.5">
                ${imgTag(item.recipe, item.name)}
                <div class="flex-1 min-w-0">
                  <div class="font-semibold text-white text-base truncate">${item.name || 'Món ăn'}</div>
                  <div class="text-xs text-slate-300 mt-1">Khẩu phần: ${item.portion || '1 phần'} · Bấm để xem công thức</div>
                </div>
                <div class="shrink-0 rounded-lg bg-emerald-500/20 border border-emerald-400/30 px-3 py-1.5 text-xs font-bold text-emerald-300">${item.calories} kcal</div>
              </button>`;
          }).join('');
          return `
            <div class="rounded-2xl border border-white/15 bg-slate-900/40 p-4 space-y-3">
              <div class="flex items-center justify-between">
                <h3 class="text-base font-bold text-sky-300">${meal.meal_name}</h3>
                <span class="text-xs text-slate-300">Mục tiêu: ${meal.target_calories} kcal · Thực tế: <strong>${meal.calories} kcal</strong></span>
              </div>
              ${itemsHtml || '<div class="text-xs text-slate-400">Chưa có món phù hợp trong tập đã lọc.</div>'}
            </div>`;
        }).join('');

        // 2. HTML Combo (Mâm cơm đủ món: cơm, canh, món mặn/xào)
        const combos = data.food_combos || [];
        const combosHtml = combos.length ? combos.map((combo, cIdx) => {
          const dishes = combo.dishes || combo.items || [];
          const dishesHtml = dishes.map(d => {
            const recipeObj = d.recipe || d;
            const idx = d.recipe === null ? -1 : regRecipe(recipeObj);
            const attr = idx >= 0 ? `data-nf-recipe="${idx}"` : '';
            return `
              <button type="button" ${attr} class="w-full text-left rounded-xl border border-white/10 bg-slate-900/60 hover:bg-slate-800/90 p-2.5 transition flex items-center gap-3">
                ${imgTag(d, d.title || d.name)}
                <div class="flex-1 min-w-0">
                  <div class="font-medium text-white text-sm truncate">${d.title || d.name || 'Món ăn'}</div>
                  <div class="text-xs text-slate-400">${d.dish_role_label || d.meal_label || 'Món trong mâm'}${d.servings_note ? ' · ' + d.servings_note : ''}</div>
                </div>
                <div class="text-xs font-semibold text-emerald-300 shrink-0">${d.calories || 0} kcal</div>
              </button>`;
          }).join('');
          return `
            <div class="rounded-2xl border border-white/15 bg-slate-900/40 p-4 space-y-3">
              <div class="flex items-center justify-between gap-2">
                <h3 class="text-base font-bold text-amber-300">${combo.title || `Mâm cơm gợi ý #${cIdx + 1}`}</h3>
                <span class="text-xs font-semibold text-emerald-300 shrink-0">${combo.total_calories || ''} kcal</span>
              </div>
              ${combo.note ? `<div class="text-xs text-slate-400">${combo.note}</div>` : ''}
              <div class="grid grid-cols-1 gap-2">${dishesHtml}</div>
            </div>`;
        }).join('') : '<div class="rounded-2xl border border-white/10 bg-slate-900/40 p-6 text-center text-sm text-slate-300">Chưa ghép được mâm cơm combo phù hợp cho điều kiện này, bạn xem tab Món lẻ bên cạnh nhé.</div>';

        // 3. HTML Nước uống
        const drinks = data.drinks || [];
        const drinksHtml = drinks.length ? drinks.map(dr => {
          const idx = regRecipe(dr);
          const dCal = dr.per_person_calories || dr.calories || 0;
          return `
            <button type="button" data-nf-recipe="${idx}" class="w-full text-left rounded-xl border border-white/15 bg-slate-900/70 hover:bg-slate-800/90 p-3 transition flex items-center gap-3.5">
              ${imgTag(dr, dr.title || dr.name)}
              <div class="flex-1 min-w-0">
                <div class="font-semibold text-white text-base truncate">${dr.title || dr.name || 'Thức uống'}</div>
                <div class="text-xs text-slate-300 mt-1">${dr.cooking_time || 'Pha chế nhanh'} · ${dr.servings || '1 ly'} · Bấm để xem cách làm</div>
              </div>
              <div class="shrink-0 rounded-lg bg-sky-500/20 border border-sky-400/30 px-3 py-1.5 text-xs font-bold text-sky-300">${dCal} kcal</div>
            </button>`;
        }).join('') : '<div class="rounded-2xl border border-white/10 bg-slate-900/40 p-6 text-center text-sm text-slate-300">Chưa có thức uống phù hợp với điều kiện lọc hiện tại.</div>';

        if (cardsEl) {
          const iconUtensils = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" width="16" height="16" aria-hidden="true"><path d="M3 2v7c0 1.1.9 2 2 2h4a2 2 0 0 0 2-2V2"/><path d="M7 2v20"/><path d="M21 15V2a5 5 0 0 0-5 5v6c0 1.1.9 2 2 2h3Zm0 0v7"/></svg>';
          const iconCup = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" width="16" height="16" aria-hidden="true"><path d="M6 8h12l-1.2 11a2 2 0 0 1-2 1.8H9.2a2 2 0 0 1-2-1.8L6 8Z"/><path d="M5 8h14"/><path d="M12 8V4l3-1"/></svg>';
          const iconSoupBowl = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" width="16" height="16" aria-hidden="true"><path d="M4 12h16a8 8 0 0 1-16 0Z"/><path d="M9 5v2"/><path d="M12 4v3"/><path d="M15 5v2"/><path d="M8 20h8"/></svg>';
          const iconRiceBowl = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" width="16" height="16" aria-hidden="true"><path d="M4 12h16a8 8 0 0 1-16 0Z"/><path d="M6 12a6 6 0 0 1 12 0"/><path d="M9 20h6"/></svg>';
          const iconGrid = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" width="16" height="16" aria-hidden="true"><rect x="4" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="4" width="6.5" height="6.5" rx="1.5"/><rect x="4" y="13.5" width="6.5" height="6.5" rx="1.5"/><rect x="13.5" y="13.5" width="6.5" height="6.5" rx="1.5"/></svg>';

          const tabActiveCls = 'px-5 py-2.5 rounded-full text-sm font-semibold inline-flex items-center gap-2 bg-sky-500 text-white border border-sky-400/60 shadow-[0_6px_18px_rgba(14,165,233,0.35)] cursor-pointer transition';
          const tabIdleCls = 'px-5 py-2.5 rounded-full text-sm font-semibold inline-flex items-center gap-2 bg-[#122644]/90 text-slate-100 border border-white/15 hover:bg-slate-800/90 cursor-pointer transition';
          const subActiveCls = 'px-5 py-2.5 rounded-full text-sm font-semibold inline-flex items-center gap-2 bg-teal-600/35 text-teal-100 border border-teal-400/65 shadow-sm cursor-pointer transition';
          const subIdleCls = 'px-5 py-2.5 rounded-full text-sm font-semibold inline-flex items-center gap-2 bg-[#122644]/90 text-slate-100 border border-white/15 hover:bg-slate-800/90 cursor-pointer transition';
          const shuffleCls = 'px-5 py-2.5 rounded-full text-sm font-semibold inline-flex items-center gap-2 bg-amber-600/25 text-amber-100 border border-amber-400/60 hover:bg-amber-500/35 cursor-pointer transition';

          const isDrink = mainTab === 'drink';
          const isCombo = foodSubTab === 'combo';

          cardsEl.innerHTML = `
            <div class="col-span-full space-y-4">
              <div class="flex flex-wrap items-center gap-3 border-b border-white/10 pb-3.5">
                <button type="button" id="nf-tab-food" class="${!isDrink ? tabActiveCls : tabIdleCls}">${iconUtensils}<span>Thức ăn</span></button>
                <button type="button" id="nf-tab-drink" class="${isDrink ? tabActiveCls : tabIdleCls}">${iconCup}<span>Nước uống (${drinks.length})</span></button>
                <div id="nf-food-subtabs" class="${isDrink ? 'hidden ' : ''}flex flex-wrap items-center gap-3">
                  <button type="button" id="nf-sub-single" class="${!isCombo ? subActiveCls : subIdleCls}">${iconSoupBowl}<span>Món lẻ theo bữa</span></button>
                  <button type="button" id="nf-sub-combo" class="${isCombo ? subActiveCls : subIdleCls}">${iconRiceBowl}<span>Combo mâm cơm (${combos.length})</span></button>
                </div>
                <button type="button" id="nf-shuffle-menu-btn" class="${shuffleCls}">${iconGrid}<span>Đổi thực đơn khác</span></button>
              </div>
              <div id="nf-panel-food-single" class="${(isDrink || isCombo) ? 'hidden ' : ''}grid grid-cols-1 md:grid-cols-2 gap-4">${singleMealsHtml}</div>
              <div id="nf-panel-food-combo" class="${(isDrink || !isCombo) ? 'hidden ' : ''}grid grid-cols-1 md:grid-cols-2 gap-4">${combosHtml}</div>
              <div id="nf-panel-drink" class="${!isDrink ? 'hidden ' : ''}grid grid-cols-1 md:grid-cols-2 gap-4">${drinksHtml}</div>
            </div>`;

          const tabFood = el('nf-tab-food');
          const tabDrink = el('nf-tab-drink');
          const subTabs = el('nf-food-subtabs');
          const subSingle = el('nf-sub-single');
          const subCombo = el('nf-sub-combo');
          const shuffleBtn = el('nf-shuffle-menu-btn');
          const pSingle = el('nf-panel-food-single');
          const pCombo = el('nf-panel-food-combo');
          const pDrink = el('nf-panel-drink');

          if (shuffleBtn && el('nf-survey-form')) {
            shuffleBtn.addEventListener('click', () => {
              el('nf-survey-form').dispatchEvent(new Event('submit', { cancelable: true }));
            });
          }

          tabFood.addEventListener('click', () => {
            tabFood.className = tabActiveCls;
            tabDrink.className = tabIdleCls;
            subSingle.className = subActiveCls;
            subCombo.className = subIdleCls;
            subTabs.classList.remove('hidden');
            pDrink.classList.add('hidden');
            pSingle.classList.remove('hidden');
            pCombo.classList.add('hidden');
            _saveNutritionSession({ mainTab: 'food', foodSubTab: 'single' });
          });
          tabDrink.addEventListener('click', () => {
            tabDrink.className = tabActiveCls;
            tabFood.className = tabIdleCls;
            subTabs.classList.add('hidden');
            pSingle.classList.add('hidden');
            pCombo.classList.add('hidden');
            pDrink.classList.remove('hidden');
            _saveNutritionSession({ mainTab: 'drink' });
          });
          subSingle.addEventListener('click', () => {
            subSingle.className = subActiveCls;
            subCombo.className = subIdleCls;
            pSingle.classList.remove('hidden');
            pCombo.classList.add('hidden');
            _saveNutritionSession({ mainTab: 'food', foodSubTab: 'single' });
          });
          subCombo.addEventListener('click', () => {
            subCombo.className = subActiveCls;
            subSingle.className = subIdleCls;
            pCombo.classList.remove('hidden');
            pSingle.classList.add('hidden');
            _saveNutritionSession({ mainTab: 'food', foodSubTab: 'combo' });
          });
        }
      }

      if (el('nf-survey-form')) {
        el('nf-survey-form').addEventListener('submit', async event => {
          event.preventDefault();
          const height = Number(el('nf-sv-height')?.value || 165);
          const weight = Number(el('nf-sv-weight')?.value || 60);
          const age = Number(el('nf-sv-age')?.value || 25);
          const gender = el('nf-sv-gender')?.value || 'Nam';
          const activity_level = el('nf-sv-activity')?.value || 'Vận động vừa';
          const goal = el('nf-sv-goal')?.value || '';
          const mealsText = el('nf-sv-meals')?.value || '3';
          const meals_per_day = mealsText.includes('4') ? 4 : (mealsText.includes('2') ? 2 : 3);
          const target_calories = null;
          const allergies = (el('nf-sv-avoid')?.value || '').trim();
          const condMap = {
            'Gout / Acid uric cao': 'Gout',
            'Tăng huyết áp': 'Tăng huyết áp',
            'Đái tháo đường': 'Đái tháo đường',
            'Gan nhiễm mỡ': 'Gan nhiễm mỡ',
            'Dạ dày / Trào ngược': 'Dạ dày',
            'Rối loạn mỡ máu': 'Rối loạn mỡ máu',
          };
          const checkedCondValues = Array.from(document.querySelectorAll('input[name="nf-sv-cond"]:checked')).map(cb => cb.value);
          const medical_conditions = checkedCondValues
            .map(val => condMap[val] || val)
            .filter(Boolean);
          const customCond = (el('nf-sv-cond-custom')?.value || '').trim();
          if (customCond) medical_conditions.push(customCond);

          const payload = {
            user_metrics: { height, weight, age, gender, activity_level, goal },
            medical_conditions,
            allergies,
            preferences: { meals_per_day, target_calories },
          };

          const labelParts = [];
          const activeConds = medical_conditions.filter(c => c !== 'Không có');
          if (activeConds.length) labelParts.push(activeConds.join(', '));
          if (target_calories) labelParts.push(`${target_calories} kcal/ngày`);
          if (allergies) labelParts.push(`tránh: ${allergies}`);
          state.query = labelParts.join(' · ') || `${meals_per_day} bữa cân bằng`;
          closeSurveyModal();

          show('results');
          const cardsEl = el('nf-cards');
          const ctxEl = el('nf-context');
          const emptyEl = el('nf-empty');
          const loadMoreEl = el('nf-load-more');
          if (emptyEl) emptyEl.hidden = true;
          if (loadMoreEl) loadMoreEl.hidden = true;
          if (ctxEl) {
            ctxEl.hidden = false;
            ctxEl.innerHTML = '<div class="p-4 text-sm text-sky-200">Đang tính BMR/TDEE và lọc thực đơn từ ViFoodRec...</div>';
          }
          if (cardsEl) cardsEl.innerHTML = '';
          document.querySelectorAll('.nf-query-label').forEach(n => { n.textContent = state.query; });

          try {
            const resp = await fetch('/api/nutrition/meal-plan', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(payload),
            });
            const data = await resp.json();
            if (data?.status === 'clarification_needed') {
              if (ctxEl) {
                ctxEl.hidden = false;
                ctxEl.innerHTML = `<div class="rounded-2xl border border-amber-400/40 bg-amber-500/15 p-4 text-sm text-amber-200">⚠️ ${data.message || 'Cần tư vấn chuyên biệt từ bác sĩ.'}</div>`;
              }
              return;
            }
            const plan = data?.daily_plan;
            if (!resp.ok || !plan) {
              if (ctxEl) {
                ctxEl.hidden = false;
                ctxEl.innerHTML = '<div class="p-4 text-sm text-rose-300">Không thể tạo thực đơn lúc này. Vui lòng thử lại.</div>';
              }
              return;
            }

            _saveNutritionSession({
              stage: 'results',
              query: state.query,
              mainTab: 'food',
              foodSubTab: 'single',
              activeRecipe: null,
              mealPlanData: data,
              surveyFields: {
                height, weight, age, gender, activity_level, goal, mealsText, allergies,
                checkedCondValues, customCond
              }
            });
            _renderMealPlanView(data, 'food', 'single');
          } catch (err) {
            if (ctxEl) ctxEl.innerHTML = '<div class="p-4 text-sm text-rose-300">Lỗi kết nối máy chủ khi tạo thực đơn.</div>';
          }
        });
      }
      el('nf-edit-query').addEventListener('click', () => { show('search'); el('nf-query').focus(); });
      el('nf-context').addEventListener('click', event => {
        if (event.target.closest('.nf-profile-link') && typeof switchTab === 'function') switchTab('profile-tab');
      });
      el('nf-load-more').addEventListener('click', () => chooseType(state.type, true));
      document.querySelectorAll('[data-nf-type]').forEach(button => button.addEventListener('click', () => chooseType(button.dataset.nfType)));
      document.querySelectorAll('[data-nf-back]').forEach(button => button.addEventListener('click', () => {
        if (state.request) { state.request.abort(); state.request = null; }
        show(button.dataset.nfBack);
      }));
      if (el('nf-detail-content')) {
        el('nf-detail-content').addEventListener('click', event => {
          const bm = event.target.closest('[data-nf-bookmark]');
          if (!bm) return;
          const savedNow = _toggleSavedRecipe(bm.dataset.nfBookmark);
          bm.classList.toggle('is-saved', savedNow);
          bm.setAttribute('aria-pressed', savedNow ? 'true' : 'false');
        });
      }
      el('nf-cards').addEventListener('click', event => {
        const button = event.target.closest('[data-nf-recipe]');
        const recipe = button && state.recipes[Number(button.dataset.nfRecipe)];
        if (!recipe) return;
        renderDetail(recipe);
        show('detail');
      });

      // Chuyển đổi giữa Thực đơn đủ món vs Món đơn lẻ
      document.querySelectorAll('[data-nf-view]').forEach(btn => {
        btn.addEventListener('click', () => {
          const target = btn.dataset.nfView;
          const hasFullMeal = state.type === 'food' && mealCombos().length > 0;
          if (target === 'full_meal' && !hasFullMeal) return;
          state.viewMode = target;
          updateViewModeUI();
          renderCards();
        });
      });

      // Nhấn vào món ăn hoặc nút chuyển sang xem món lẻ trong mâm cơm 1 bữa đủ món
      if (el('nf-full-meal-wrap')) {
        el('nf-full-meal-wrap').addEventListener('keydown', event => {
          if ((event.key === 'Enter' || event.key === ' ') && event.target.matches('[data-nf-meal-dish]')) {
            event.preventDefault(); event.target.click();
          }
        });
        el('nf-full-meal-wrap').addEventListener('click', event => {
          const comboBtn = event.target.closest('[data-nf-combo]');
          if (comboBtn) {
            const idx = Number(comboBtn.dataset.nfCombo);
            if (mealCombos()[idx]) {
              state.activeComboIndex = idx;
              renderFullMeal();
            }
            return;
          }
          const refreshBtn = event.target.closest('#nf-btn-refresh-combos');
          if (refreshBtn) {
            chooseType(state.type, false, true);
            return;
          }
          const switchBtn = event.target.closest('#nf-btn-switch-singles');
          if (switchBtn) {
            state.viewMode = 'single_dishes';
            updateViewModeUI();
            renderCards();
            if (el('nf-mode-switcher')) {
              el('nf-mode-switcher').scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
            return;
          }
          const card = event.target.closest('[data-nf-meal-dish]');
          const dishIndex = card && card.dataset.nfMealDish;
          const combos = mealCombos();
          const activeCombo = combos[state.activeComboIndex || 0] || combos[0];
          const recipe = dishIndex !== undefined && activeCombo?.dishes?.[Number(dishIndex)]?.recipe;
          if (!recipe) return;
          renderDetail(recipe);
          show('detail');
        });
      }

      window.addEventListener('medimind:langchange', () => {
        if (!el('nf-search')) return;
        if (state.lastData) applyResultsCopy();
        if (state.stage === 'detail' && state.activeRecipe) renderDetail(state.activeRecipe);
      });

      // Khôi phục đúng màn đang xem (results / detail / search) khi F5 reload trang
      const saved = _readNutritionSession();
      const fields = saved.surveyFields;
      if (fields && el('nf-survey-form')) {
        if (el('nf-sv-height') && fields.height) el('nf-sv-height').value = fields.height;
        if (el('nf-sv-weight') && fields.weight) el('nf-sv-weight').value = fields.weight;
        if (el('nf-sv-age') && fields.age) el('nf-sv-age').value = fields.age;
        if (el('nf-sv-gender') && fields.gender) el('nf-sv-gender').value = fields.gender;
        if (el('nf-sv-activity') && fields.activity_level) el('nf-sv-activity').value = fields.activity_level;
        if (el('nf-sv-goal') && fields.goal !== undefined) el('nf-sv-goal').value = fields.goal;
        if (el('nf-sv-meals') && fields.mealsText) el('nf-sv-meals').value = fields.mealsText;
        if (el('nf-sv-avoid') && fields.allergies !== undefined) el('nf-sv-avoid').value = fields.allergies;
        if (el('nf-sv-cond-custom') && fields.customCond !== undefined) el('nf-sv-cond-custom').value = fields.customCond;
        if (Array.isArray(fields.checkedCondValues)) {
          const picked = new Set(fields.checkedCondValues);
          document.querySelectorAll('input[name="nf-sv-cond"]').forEach(cb => {
            cb.checked = picked.has(cb.value);
          });
        }
      }
      if (saved.mealPlanData?.daily_plan && (saved.stage === 'results' || saved.stage === 'detail')) {
        state.query = saved.query || '';
        _renderMealPlanView(saved.mealPlanData, saved.mainTab || 'food', saved.foodSubTab || 'single');
        if (saved.stage === 'detail' && saved.activeRecipe) {
          renderDetail(saved.activeRecipe);
          show('detail');
        } else {
          show('results');
        }
      } else {
        show('search');
      }
    }
  };
})();
