"""Conservative text features for imported recipes, not clinical approval.

Full original ingredient strings form the fingerprint. Flags indicate textual
evidence only; absent flags do not establish nutrient amounts or allergy safety.
No external calls or model output are used here.
"""
import re
import unicodedata
from functools import lru_cache


def normalize_ingredient(value):
    text = unicodedata.normalize("NFD", str(value or "").lower().replace("_", " "))
    text = "".join(c for c in text if unicodedata.category(c) != "Mn").replace("đ", "d")
    return " ".join(text.split())


def _has(pattern, text):
    return bool(re.search(r"\b(?:" + pattern + r")\b", text))


_PLANT_MILK = r"(?:coconut|soy|soya|almond|oat|rice|cashew|hemp)\s+milk"
_MILK = r"milk|butter|buttermilk|cream|cheese|yog[hu]rt|whey|casein|ghee|paneer|curd|creme\s+fraiche|sua\s+(?:bo|tuoi)|bo\s+sua"
_EGG = r"eggs?|egg\s+(?:white|yolk)s?|albumen|trung\s+ga|mayonnaise|meringue"
_SOY = r"soy|soya|tofu|tempeh|miso|edamame|dau\s+(?:nanh|hu)|sua\s+dau\s+nanh"
_GLUTEN = r"wheat|barley|rye|semolina|couscous|bulgur|seitan|spelt|farro|bread|breadcrumbs|panko|pasta|macaroni|spaghetti|noodles|malt|lua\s+mach"
_FLOUR_TYPES_WITHOUT_GLUTEN = r"(?:rice|corn|maize|potato|tapioca|cassava|almond|coconut|chickpea|buckwheat|gluten[ -]free)\s+(?:flour|starch)"
_PACKAGED = r"stock|bouillon|broth|sauces?|mix(?:ture)?|seasoning|margarine|shortening|substitute|replacement|spread|dressing|curry\s+paste|chocolate\s+chips|processed|condensed|evaporated|flavou?ring|flavou?red|protein\s+powder"

# Vietnamese names are matched as phrases. Accent removal alone collapses
# unrelated words (sữa/sứa, bơ/bò); a bare syllable is not enough evidence.
_PLANT_MILK_VI = r"sua\s+(?:dau\s+nanh|dau\s+xanh|dau\s+do|dau\s+den|dua|hanh\s+nhan|yen\s+mach|gao|hat\s+(?:dieu|sen|oc\s+cho)|bap|ngo)"
_MILK_VI = r"sua\s+(?:tuoi|dac|bot|chua|bo|khong\s+duong|co\s+duong|tach\s+beo|nguyen\s+kem)|pho\s+mai|pho\s+mat|phomai|kem\s+(?:sua|tuoi|beo)|bo\s+(?:lat|man|sua)|váng\s+sua|vang\s+sua"
_EGG_VI = r"trung(?:\s+(?:ga|vit|cut|ngong|muoi|bac\s+thao))?|long\s+(?:do|trang)(?:\s+trung)?"
_SOY_VI = r"dau\s+(?:nanh|hu|phu)|tau\s+hu|tao\s+pho|tuong\s+(?:dau|hot|ban)|nuoc\s+tuong|xi\s+dau"
_GLUTEN_VI = r"bot\s+mi|lua\s+mi|lua\s+mach|banh\s+mi|mi\s+(?:ong|trung|soi|goi)|nui|can\s+mi"
_PACKAGED_VI = r"hat\s+nem|bot\s+nem|vien\s+sup|nuoc\s+(?:dung|cot|sot|mam|tuong)|tuong\s+(?:ot|ca|den)|sot|xuc\s+xich|gio\s+lua|cha\s+lua|thit\s+nguoi|dau\s+hao|bo\s+thuc\s+vat|bot\s+chien|gia\s+vi\s+(?:lau|hoan\s+chinh|tong\s+hop)|dong\s+goi|che\s+bien\s+san"

_VI_INGREDIENT_PHRASES = """nuoc loc|nuoc uong|nuoc soi|nuoc am|nuoc lanh|nuoc sach|nuoc khoang|nuoc|muoi|duong phen|duong trang|duong nau|duong thot not|duong|mat ong
gao te|gao nep|gao lut|gao|yen mach|lua mach|lua mi|bot mi|bot gao|bot nep|bot nang|bot bap|bot ngo|bot san day|bot san|bot rau cau|bap|ngo|tam|mien dong|bun tuoi|bun|banh pho|pho tuoi|nui|mi trung
thit ga|uc ga|dui ga|ga|thit heo|thit lon|thit nac|thit bam|thit xay|suon non|suon heo|suon lon|xuong heo|xuong lon|thit bo|thit vit|thit de|thit cuu
ca loc|ca qua|ca qua|ca ro|ca ro phi|ca chep|ca hoi|ca thu|ca basa|ca basa|ca dieu hong|ca ngu|ca bong|ca trich|ca tre|ca|tom su|tom the|tom kho|tom|cua dong|cua bien|cua|tep|muc|ngheu|ngao|so|oc|hen|hai san|sua bien|sua
trung ga|trung vit|trung cut|trung muoi|trung bac thao|trung|long do trung|long trang trung|long do|long trang
sua tuoi|sua dac|sua bot|sua chua|sua bo|sua|pho mai|pho mat|phomai|bo lat|bo man|bo sua|kem sua|kem tuoi|kem beo|vang sua
dau nanh|dau hu non|dau hu|dau phu non|dau phu|tau hu|tao pho|tuong hot|nuoc tuong|xi dau|dau xanh|dau do|dau den|dau trang|dau ngu|dau ha lan|dau co ve|dau que|dau rong|lac|dau phong|dau dua|dau oliu|dau o liu|dau an
khoai tay|khoai lang|khoai mon|khoai so|cu san|khoai mi|ca rot|cu cai trang|cu cai|cu den|cu sen|hat sen|bi do|bi ngo|bi xanh|bi dao|bau|muop huong|muop|kho qua|muop dang|du du|su su|su hao|bong cai xanh|bong cai trang|sup lo xanh|sup lo|bap cai|cai thao|cai ngot|cai xanh|cai thia|cai be|cai bo xoi|rau bina|rau ngot|rau den|rau mung toi|mong toi|rau muong|rau lang|rau ma|rau day|rau can|can tay|xa lach|rau xa lach|gia do|gia|mang tuoi|mang|mit non|dau bap
nam huong|nam dong co|nam rom|nam kim cham|nam bao ngu|nam meo|moc nhi|nam
dua leo|dua chuot|ca chua|ca tim|hanh tay|hanh tim|hanh la|hanh|toi|gung|nghe|rieng|sa|la chanh|la dua|la nep|la lot|tia to|rau ram|rau ngo|ngo ri|mui ta|mui tau|ngò rí|thi la|hung que|hung lui|bac ha|kinh gioi|rau thom|tieu den|tieu xay|tieu|que|hoi|dinh huong|ot chuong|ot|chanh|tac|quat|giam|me chua|me|sau|khe chua
dua tuoi|dua non|dua kho|dua|nuoc dua|nuoc cot dua|com dua|cu hui dua|chuoi chin|chuoi|tao|le|cam|buoi|quyt|xoai|dua hau|dua luoi|thom|dua (thom)|khom|dau tay|viet quat|nho|man|dao|mo|nhan|vai|chom chom|mang cut|sau rieng|bo|chanh day|mang cau|na|hong xiem|sapoche|kiwi|oi|thanh long
hanh nhan|hat dieu|oc cho|hat oc cho|hat chia|hat lanh|hat bi|hat huong duong|me trang|me den|vung trang|vung den|me|vung
tra xanh|tra den|tra o long|tra tui loc|tra|ca phe|ca cao|cacao|bot cacao|bot ca cao|socola|so co la|hoa cuc|hoa atiso|atiso|a ti so|hoa hong|long nhan|tao do|ky tu|hat e
nuoc mam|hat nem|bot nem|bot ngot|mi chinh|bot canh|nuoc dung|nuoc cot|nuoc sot|tuong ot|tuong ca|tuong den|sot|dau hao|banh mi|bot chien gion|bot chien xu|xuc xich|gio lua|cha lua|men no|bot no|baking soda|ruou|bia|ruou trang|ruou vang
"""
_VI_PHRASES = sorted({normalize_ingredient(s) for s in re.split(r"[|\n]", _VI_INGREDIENT_PHRASES) if s.strip()}, key=len, reverse=True)
_VI_PHRASE_PATTERN = re.compile(r"\b(?:" + "|".join(re.escape(phrase) for phrase in _VI_PHRASES) + r")\b")
_VI_DESCRIPTORS = set("""g gr gram gam kg mg ml lit l millilit muong thia canh ca phe che chen bat to ly coc
qua trai cu cay cai con mieng lat nhanh tep bo nhum it chut vua du an khau phan phan goi hop chai lon
tuoi kho chin song sach ngam rua got vo bo hat loc nac non gia khong duong co it tach beo nguyen kem
thai cat bam xay nghien nhuyen nho lon vua day mong soi hat nguyen mieng tron de rieng tuy chon
va hoac voi theo khau vi cho them khoang den tu nhu can neu thich da nau hap luoc rang chin
chung chit lot may khoa dong lanh hop huu co loai thom chin mem chia nho day leo nuong khong muoi
""".split())


def _vietnamese_ingredient_uncertainty(text):
    """Recognize whole ingredient phrases; leftover words remain unresolved."""
    if _has(_PACKAGED_VI, text):
        return True
    remainder = _VI_PHRASE_PATTERN.sub(" ", text)
    words = re.findall(r"[a-z]+", remainder)
    return any(word not in _VI_DESCRIPTORS for word in words)


def _vietnamese_ambiguous_ingredient(text):
    # Bare "bơ" can mean butter or avocado; accent folding also maps beef
    # "bò" to the same token. A known qualifier is needed to resolve it.
    remainder = re.sub(r"\b(?:thit\s+bo|qua\s+bo|trai\s+bo|bo\s+chin|bo\s+lat|bo\s+man|bo\s+sua)\b", "", text)
    return _has(r"bo", remainder)

# A deliberately bounded vocabulary. Unrecognized food/product names retain
# uncertainty instead of being interpreted as allergen-free by omission.
_FOODS = set("""water salt pepper sugar honey maple syrup agave molasses brown white black
rice potato potatoes carrot onion garlic leek shallot scallion spring chicken turkey beef pork lamb
fish salmon tuna cod trout shrimp prawn crab lobster mussel clam oyster seafood meat breast thigh
lentil lentils pea peas bean beans chickpea chickpeas kidney pinto cannellini mung split
oat oats oatmeal corn maize tapioca cassava almond almonds cashew cashews walnut walnuts peanut peanuts
hazelnut hazelnuts pecan pecans pistachio pistachios nut nuts coconut hemp flax chia sesame sunflower
pumpkin squash zucchini courgette cucumber tomato tomatoes broccoli cauliflower cabbage kale spinach
lettuce celery mushroom mushrooms aubergine eggplant beet beetroot turnip parsnip radish sweet yam
apple apples pear pears banana bananas orange oranges lemon lemons lime limes grapefruit pineapple
strawberry strawberries blueberry blueberries raspberry raspberries blackberry blackberries berry berries
peach peaches plum plums apricot apricots mango papaya melon watermelon cantaloupe grape grapes
raisin raisins date dates fig figs cherry cherries prune prunes avocado olive olives
oil vinegar juice zest peel pulp puree flour starch yeast baking soda powder cream tartar
milk butter buttermilk cheese yoghurt yogurt whey casein ghee paneer curd creme fraiche
egg eggs yolk yolks whites white albumen mayonnaise meringue
soy soya tofu tempeh miso edamame wheat barley rye semolina couscous bulgur seitan spelt farro
bread breadcrumbs panko pasta macaroni spaghetti noodles malt
coffee tea cacao cocoa chocolate chicory matcha vanilla cinnamon nutmeg clove cloves ginger turmeric
cumin coriander cilantro parsley basil oregano thyme rosemary sage dill bay laurel fennel anise
mint peppermint spearmint cardamom allspice saffron paprika chili chillies chilies chilli cayenne
jalapeno habanero mustard wasabi horseradish sriracha tabasco
gelatin gelatine agar pectin custard pudding quinoa millet sorghum buckwheat amaranth
semolina polenta arborio basmati jasmine vermicelli coriander cumin tamarind
nuoc sua bo tuoi dau nanh hu trung ga gao yen mach rau ca rot bi do khoai lang lua
""".split())
_DESCRIPTORS = set("""a an and or of with without to taste as needed optional plus more extra for
the about approximately around divided at room temperature hot warm cold cool boiling boiled
fresh freshly dried dry frozen thawed canned tinned cooked uncooked raw roasted toasted ripe
small medium large whole half quarter finely coarse coarsely ground cracked crushed chopped
diced minced sliced grated shredded peeled unpeeled seeded deseeded pitted drained rinsed
washed sifted sieved packed heaped level scant unsalted salted low sodium reduced fat nonfat
skim skimmed full lean boneless skinless skin bone breast breasts thigh thighs fillet fillets
all purpose self raising plain strong quick instant rolled steel cut cut into pieces cubes
inch inches cm mm g kg mg gram grams kilogram kilograms ounce ounces oz pound pounds lb lbs
ml litre litres liter liters l cup cups teaspoon teaspoons tablespoon tablespoons tsp tbsp
dash pinch handful bunch bunches sprig sprigs stalk stalks clove cloves can cans tin tins
packet packets slice slices sheet sheets stick sticks piece pieces head heads
organic unrefined refined pure natural clear filtered drinking tap bottled potable
fluid liquid solid solids extract essence seeds seed flour starch powder flakes flaked
thin thick smooth soft hard softening softened melting melted beaten lightly well thoroughly
food grade free dairy gluten wheat egg soy
""".split())


@lru_cache(maxsize=32768)
def _ingredient_uncertainty(text, vietnamese=False):
    uncertain = _has(_PACKAGED, text)
    if _has(r"flour", text) and not (_has(_FLOUR_TYPES_WITHOUT_GLUTEN, text)
                                            or _has(r"wheat|all[ -]purpose|plain|self[ -]raising|bread\s+flour", text)):
        uncertain = True
    words = re.findall(r"[a-z]+", text)
    unknown = [word for word in words if word not in _FOODS and word not in _DESCRIPTORS
               and not (word.endswith("s") and word[:-1] in (_FOODS | _DESCRIPTORS))]
    if vietnamese:
        # A line may contain a known English name, but an unresolved Vietnamese
        # phrase or a packaged product must never disappear from allergy checks.
        return uncertain or _has(_PACKAGED_VI, text) or _vietnamese_ambiguous_ingredient(text) or (bool(unknown) and _vietnamese_ingredient_uncertainty(text))
    return uncertain or bool(unknown)


def analyze_imported_recipe(recipe):
    """Return compatible metadata while preserving uncertainty and input data.

    ``automatic`` is always true. ``ingredients`` is an immutable normalized
    fingerprint; a caller must match it to the actual recipe before filtering.
    ``allergen_uncertain`` must be treated as unresolved for allergy requests.
    ``nutrients_unknown`` means these features cannot support nutrient thresholds.
    """
    entries = recipe.get("ingredients", [])
    texts = [normalize_ingredient(item.get("name", "")) for item in entries if isinstance(item, dict)] if isinstance(entries, list) else []
    raw_texts = [str(item.get("name", "")).lower() for item in entries if isinstance(item, dict)] if isinstance(entries, list) else []
    vietnamese = recipe.get("language") == "vi" or str(recipe.get("id", "")).startswith("vifoodrec_")
    shape_valid = bool(texts) and len(texts) == len(entries) and all(texts)
    ingredients = " ; ".join(texts)
    raw_title = str(recipe.get("title", "")).lower()
    title = normalize_ingredient(raw_title)
    categories = recipe.get("categories", [])
    categories = categories if isinstance(categories, list) else [str(categories)]
    labels = title + " ; " + " ; ".join(normalize_ingredient(c) for c in categories)
    raw_steps = " ; ".join(s.lower() for s in recipe.get("steps", []) if isinstance(s, str))
    steps = normalize_ingredient(raw_steps)
    allergens = set()
    for text, raw_text in zip(texts, raw_texts):
        # Plant milk is not automatically animal milk; its own known allergens
        # are still scanned below. Compound replacement products stay uncertain.
        milk_text = normalize_ingredient(re.sub(r"\bsứa\b", "jellyfish", raw_text))
        animal_scan = re.sub(r"\b(?:" + _PLANT_MILK + "|" + _PLANT_MILK_VI + r")\b", "", milk_text)
        raw_animal_scan = re.sub(r"sữa\s+(?:đậu\s+nành|đậu\s+xanh|đậu\s+đỏ|đậu\s+đen|dừa|hạnh\s+nhân|yến\s+mạch|gạo|hạt\s+(?:điều|sen|óc\s+chó)|bắp|ngô)", "", raw_text)
        if _has(_MILK, animal_scan) or _has(_MILK_VI, animal_scan) or (vietnamese and _has(r"sữa", raw_animal_scan)):
            allergens.add("milk")
        if _has(_EGG, text) or (vietnamese and _has(_EGG_VI, text)):
            allergens.add("egg")
        if _has(_SOY, text) or (vietnamese and _has(_SOY_VI, text)):
            allergens.add("soy")
        gluten_scan = re.sub(r"\b" + _FLOUR_TYPES_WITHOUT_GLUTEN + r"\b", "", text)
        if _has(_GLUTEN, gluten_scan) or (vietnamese and _has(_GLUTEN_VI, gluten_scan)) or (_has(r"flour", gluten_scan) and _has(r"wheat|all[ -]purpose|plain|self[ -]raising|bread\s+flour", gluten_scan)):
            allergens.add("gluten")
    unresolved = [text for text in texts if _ingredient_uncertainty(text, vietnamese)]
    gluten_uncertain = _has(r"oats?|oatmeal|yen\s+mach|nuoc\s+tuong|xi\s+dau|bot\s+chien|mi\s+soi", ingredients)
    alcohol = _has(r"wine|beer|ale|lager|stout|rum|vodka|whisk[ey]+|brandy|gin|liqueur|liquor|sherry|cognac|bourbon|sake|tequila|ethanol|champagne|ruou|bia", ingredients)
    fermented_drink = recipe.get("recipe_type") == "drink" and _has(r"ferment|fermented|fermenting|fermentation|brew|brewing|len\s+men|u\s+men", steps) and _has(r"yeast|culture|starter|men", ingredients)
    alcohol = alcohol or fermented_drink
    caffeine_scan = re.sub(r"\btra\s+(?:hoa\s+cuc|hoa\s+hong|bac\s+ha|gung|atiso|a\s+ti\s+so)\b", "", ingredients)
    caffeine = _has(r"coffee|tea|matcha|cocoa|cacao|chocolate|espresso|caffeine|yerba\s+mate|ca\s+phe|ca\s+cao|socola|so\s+co\s+la", ingredients) or (vietnamese and _has(r"tra", caffeine_scan))
    acidic = _has(r"lemon|lime|orange|grapefruit|citrus|tomato|vinegar|tamarind|pineapple|chanh|tac|quat|giam|me\s+chua|ca\s+chua|khom|cam|buoi|quyt|sau|khe\s+chua", ingredients) or (vietnamese and _has(r"me|thơm|dứa", " ; ".join(raw_texts)))
    # Bell pepper is a vegetable, not evidence that a dish is hot/spicy.
    spice_scan = re.sub(r"\bot\s+chuong\b", "", ingredients)
    spicy = _has(r"chili|chilli|chilies|chillies|cayenne|jalapeno|habanero|hot\s+pepper|sriracha|tabasco|wasabi|horseradish|ot", spice_scan)
    mint = _has(r"mint|peppermint|spearmint|bac\s+ha|hung\s+lui", ingredients)
    fried = _has(r"deep[ -]fr(?:y|ied)|shallow[ -]fr(?:y|ied)|pan[ -]fr(?:y|ied)|stir[ -]fr(?:y|ied)|fry|fried|frying|chien|xao|ran", labels + " ; " + steps)
    # Keep Vietnamese accents for texture names: cánh gà is chicken wings,
    # canh is soup; chảo is a pan while cháo is porridge.
    liquid = recipe.get("recipe_type") == "drink" or (vietnamese and _has(r"canh|súp(?!\s+lơ)", raw_title))
    raw_labels = raw_title + " ; " + " ; ".join(str(c).lower() for c in categories)
    soft = liquid or _has(r"soups?|congee|porridge|puree|pureed|mashed|custard|pudding|smoothie|jelly", labels) or (vietnamese and _has(r"cháo|súp(?!\s+lơ)|nghiền|xay\s+nhuyễn|hấp\s+mềm", raw_labels))
    if _has(r"crouton|crispy|crunchy|crisp|raw\s+carrot|gion|rau\s+song", labels + " ; " + ingredients) or fried:
        soft = False
    fat_unknown = bool(unresolved) or _has(r"oil|butter|cream|ghee|cheese|full[ -]fat|whole\s+milk|coconut|nuts?|peanuts?|almonds?|cashews?|beef|pork|lamb|chicken|turkey|dau\s+an|dau\s+dua|dau\s+oliu|dau\s+o\s+liu|mo\s+heo|mo\s+lon|nuoc\s+cot\s+dua|sua\s+tuoi|kem\s+sua|pho\s+mai|thit\s+(?:heo|lon|bo|ga)|lac|dau\s+phong|hat\s+dieu|hanh\s+nhan", ingredients)
    medicinal = _has(r"oral\s+rehydration|ors|medicin[ae]l|medicine|supplement|cough\s+syrup|tincture|detox|poison|herbal\s+remedy|remedies|thuoc|chua\s+benh|tri\s+benh|ha\s+sot|giai\s+doc|nuoc\s+bu\s+dien\s+giai", labels)
    raw_hazard = _has(r"tartare|sashimi|ceviche|raw\s+milk|unpasteuri[sz]ed|raw\s+meat|raw\s+chicken|raw\s+pork|tiet\s+canh|tai\s+chanh|thit\s+tai|ca\s+song|tom\s+song|goi\s+ca|goi\s+hai\s+san|sua\s+(?:song|chua\s+tiet\s+trung)", labels + " ; " + ingredients)
    vi_animal_scan = re.sub(r"\b(?:ca\s+rot|ca\s+chua|ca\s+tim|ca\s+phe|ca\s+cao)\b", "", ingredients)
    animal_raw = _has(r"eggs?|beef|pork|lamb|chicken|turkey|fish|salmon|tuna|shrimp|seafood", ingredients) or (vietnamese and _has(r"trung|thit|ga|vit|tom|ca|hai\s+san|muc|cua|ngheu|ngao|hen", vi_animal_scan))
    cooking_step = _has(r"cook|cooked|cooking|bake|baked|baking|boil|boiled|boiling|simmer|simmered|steam|steamed|roast|roasted|fry|fried|grill|grilled|poach|poached|microwave|heat|heated|nau|hap|luoc|ham|ninh|chien|xao|ran|nuong|om|dun|chung|rang|chao\s+chin", steps) or (vietnamese and _has(r"kho", raw_steps))
    raw_ingredients = " ; ".join(raw_texts)
    vi_oc_scan = re.sub(r"\boc\s+cho\b", "", ingredients)
    vi_mang_scan = re.sub(r"\bmang\s+cut\b", "", ingredients)
    labels_oc_scan = re.sub(r"\boc\s+cho\b", "", labels)
    labels_mang_scan = re.sub(r"\bmang\s+cut\b", "", labels)
    purine_high = alcohol or _has(
        r"oysters?|mussels?|clams?|scallops?|shrimp|prawns?|crabs?|lobsters?|squid|octopus|anchov(?:y|ies)|sardines?|herring|mackerel|tuna"
        r"|liver|kidney|heart|brain|sweetbread|organ\s+meat|beef|lamb|mutton|veal|bamboo\s+shoots?",
        ingredients
    ) or (vietnamese and (
        _has(r"hau|so|ngheu|ngao|hen|tom|cua|muc|bach\s+tuoc|ca\s+(?:trich|moi|thu|nuc|ngu|com)|hai\s+san", ingredients)
        or _has(r"oc", vi_oc_scan)
        or _has(r"gan|pheo|bao\s+tu|tiet|huyet|noi\s+tang|pha\s+lau|doi\s+heo", ingredients)
        or _has(r"qua\s+tim|tim\s+(?:heo|lon|bo|ga|vit|dong\s+vat)", ingredients)
        or _has(r"cat\s+(?:heo|lon|bo)|than\s+(?:heo|lon|bo)", ingredients) or bool(re.search(r"\bcật\b", raw_ingredients))
        or _has(r"long\s+(?:heo|lon|bo|ga|vit|non|gia)", ingredients) or bool(re.search(r"\blòng(?!\s+(?:đỏ|trắng))\b", raw_ingredients))
        or _has(r"thit\s+(?:bo|be|de|cuu|heo|lon|nac|bam|xay)|ba\s+(?:roi|chi)|suon\s+(?:heo|lon|non)|xuong\s+(?:heo|lon|ong)|gio\s+heo|mong\s+gio|chan\s+gio|gio\s+song|cha\s+lua|gio\s+lua|thit\s+nguoi|xuc\s+xich", ingredients)
        or _has(r"mang", vi_mang_scan)
    )) or (vietnamese and (
        _has(r"hau|so|ngheu|ngao|hen|tom|cua|muc|thit\s+(?:bo|heo|lon)|gio\s+heo|mong\s+gio|chan\s+gio", labels)
        or _has(r"oc", labels_oc_scan)
        or _has(r"mang", labels_mang_scan)
    ))
    sugar_high = _has(
        r"sugar|cane\s+sugar|corn\s+syrup|honey|molasses|caramel|jam|marmalade|candy|condensed\s+milk"
        r"|duong\s+(?:cat|phen|trang|nau|thot\s+not)|mat\s+ong|siro|sua\s+dac|keo|mut",
        ingredients
    ) or (vietnamese and _has(r"che\s+ngot|nuoc\s+ngot", labels))
    sodium_high = _has(
        r"mam\s+(?:tom|tep|ca|ruoc|nem)|ca\s+kho|kho\s+muc|thit\s+(?:xong\s+khoi|nguoi)|xuc\s+xich|lap\s+xuong|dua\s+muoi|dua\s+chua|ca\s+muoi|cured|bacon|ham|sausage|pickles?",
        ingredients
    )
    unsafe = not shape_valid or not steps.strip() or medicinal or raw_hazard or fermented_drink or (animal_raw and not cooking_step)
    return {
        "ingredients": frozenset(texts), "allergens": frozenset(allergens),
        "automatic": True, "allergen_uncertain": not shape_valid or bool(unresolved),
        "unresolved_ingredients": unresolved, "gluten_uncertain": gluten_uncertain,
        "soft": soft, "liquid": liquid, "caffeine": caffeine, "alcohol": alcohol,
        "acidic": acidic, "spicy": spicy, "mint": mint, "fried": fried,
        "fat_unknown": fat_unknown, "purine_high": purine_high,
        "sugar_high": sugar_high, "sodium_high": sodium_high,
        "unsafe_preparation": unsafe, "nutrients_unknown": True,
    }
