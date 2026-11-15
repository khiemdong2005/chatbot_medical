from html.parser import HTMLParser
from pathlib import Path

class TabParents(HTMLParser):
    void = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr','path','circle'}
    def __init__(self):
        super().__init__(); self.stack=[]; self.parents={}
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs); ident=attrs.get('id')
        if ident in {'home-tab','booking-tab','ocr-tab','doctor-tab'}:
            self.parents[ident]=self.stack[-1] if self.stack else None
        if tag not in self.void:self.stack.append((tag,ident))
    def handle_endtag(self, tag):
        if tag in self.void:return
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i][0]==tag:
                self.stack=self.stack[:i];break

def test_primary_tabs_share_main_container():
    parser=TabParents(); parser.feed(Path('templates/index.html').read_text(encoding='utf8'))
    assert set(parser.parents)=={'home-tab','booking-tab','ocr-tab','doctor-tab'}
    assert len(set(parser.parents.values()))==1
    assert parser.parents['ocr-tab'][0]=='main'


def test_auth_split_shell_structure_and_modes():
    html = Path('templates/index.html').read_text(encoding='utf8')
    js = Path('static/js/app.js').read_text(encoding='utf8')
    css = Path('static/css/style.css').read_text(encoding='utf8')
    for required_id in (
        'id="login-modal"', 'id="auth-left-hero"', 'id="auth-modal-card"',
        'id="btn-google-signin"', 'id="login-form"', 'id="register-form"',
        'id="register-confirm-password"', 'id="forgot-form"', 'id="otp-form"',
    ):
        assert required_id in html, f'Missing {required_id}'
    assert '#login-modal.auth-4exam-shell' in css
    assert 'function toggleAuthPasswordVisibility(' in js
    assert 'async function handleForgotSubmit(' in js


def test_bilingual_i18n_dictionary_integrity():
    import re
    html = Path('templates/index.html').read_text(encoding='utf8')
    js = Path('static/js/app.js').read_text(encoding='utf8')

    assert '<html lang="vi"' in html
    for marker in (
        'data-i18n="menu_profile"',
        'data-i18n="menu_settings"',
        'data-i18n="menu_logout"',
        'data-i18n-placeholder="set_ph_curr_pass"',
        'data-i18n-title="lbl_toggle_pwd"',
    ):
        assert marker in html, f'Missing {marker} in index.html'

    tr_block = js[js.index('const translations = {'):js.index('const STATIC_VI_EN_TEXT = {')]
    vi_src = tr_block[tr_block.index('vi: {') + 5:tr_block.index('en: {')]
    en_src = tr_block[tr_block.index('en: {') + 5:]

    vi_keys = re.findall(r'^\s*([a-zA-Z0-9_]+)\s*:', vi_src, re.M)
    en_keys = re.findall(r'^\s*([a-zA-Z0-9_]+)\s*:', en_src, re.M)
    assert len(vi_keys) == len(set(vi_keys)), 'Duplicate keys in translations.vi'
    assert len(en_keys) == len(set(en_keys)), 'Duplicate keys in translations.en'
    assert set(vi_keys) == set(en_keys), 'Key mismatch between translations.vi and translations.en'
    assert len(vi_keys) >= 350

    vi_diacritics = re.compile(
        r'[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ'
        r'ÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ]'
    )
    en_vals = re.findall(r'^\s*[a-zA-Z0-9_]+\s*:\s*"((?:\\"|[^"])*)"', en_src, re.M)
    leaked = [v for v in en_vals if vi_diacritics.search(v)]
    assert not leaked, f'Vietnamese diacritics leaked into translations.en: {leaked[:5]}'

    html_i18n_keys = set(re.findall(r'data-i18n(?:-(?:placeholder|title|aria))?="([^"]+)"', html))
    missing = html_i18n_keys - set(vi_keys)
    assert not missing, f'HTML data-i18n keys missing from dictionary: {missing}'


def test_pagination_theme_and_profile_dob_controls():
    html = Path('templates/index.html').read_text(encoding='utf8')
    js = Path('static/js/app.js').read_text(encoding='utf8')
    fac_css = Path('static/css/facilities.css').read_text(encoding='utf8')

    # 1. Home Discovery heading breathing room
    assert 'data-i18n="home_disc_title"' in html
    assert 'leading-[1.42]' in html

    # 2. Facilities pagination next/prev disambiguated from page 1
    assert 'onclick="changeFacilityPage(\'prev\')"' in html
    assert 'onclick="changeFacilityPage(\'next\')"' in html
    assert 'onclick="changeFacilityPage(1)"' not in html
    assert "target === 'next'" in html

    # 3. Light/Dark theme rules for pagination, clear search, and reset filter buttons
    for selector in ('#btnPrevPage', '#btnNextPage', '#btnClearHospitalSearch', '.facility-reset-btn'):
        assert selector in fac_css, f'Missing theme selector {selector} in facilities.css'

    # 4. Profile Date of Birth Day/Month/Year dropdowns (without quick calendar picker)
    for dob_id in ('id="p-birthdate"', 'id="p-dob-day"', 'id="p-dob-month"', 'id="p-dob-year"'):
        assert dob_id in html, f'Missing {dob_id} in profile form'
    assert 'id="p-dob-calendar-btn"' not in html
    assert 'id="p-dob-native"' not in html
    assert 'function syncProfileTabDobFromDropdowns()' in js


def test_facilities_leaflet_map_and_coordinates():
    import json
    html = Path('templates/index.html').read_text(encoding='utf8')
    fac_css = Path('static/css/facilities.css').read_text(encoding='utf8')
    records = json.loads(Path('data/CSKCB_Data/danh_sach_co_so_kcb_normalized.json').read_text(encoding='utf8'))

    assert len(records) == 1505
    for r in records:
        lat, lng = r.get('lat'), r.get('lng')
        assert lat is not None and lng is not None, f"Facility {r.get('id')} missing coordinates"
        assert 10.35 <= float(lat) <= 11.20 and 106.35 <= float(lng) <= 107.05, f"Out-of-bounds HCMC coords on {r.get('id')}: {lat},{lng}"
        qh = str(r.get('quan_huyen') or '')
        assert qh.startswith(('Quận', 'Huyện', 'TP')), f"Malformed quan_huyen on {r.get('id')}: {qh}"

    assert '<div id="leafletHospitalMap" class="w-full h-full"></div>' in html
    assert 'id="googleHospitalMapEmbed" class="w-full h-full hidden"' in html
    assert 'async function showFallbackMap() {\n  initLeafletMapView();\n}' in html
    assert 'function buildGoogleMapsDirectionsUrl(fac)' in html
    assert 'https://www.google.com/maps/dir/?api=1&destination=' in html
    assert "className: 'medimind-map-pin'" in html
    assert 'leafletMarkerCluster.zoomToShowLayer(m,' in html
    assert '.medimind-map-pin-dot' in fac_css
    assert '#hospitalMapPanel .facility-map-controls button' in fac_css



