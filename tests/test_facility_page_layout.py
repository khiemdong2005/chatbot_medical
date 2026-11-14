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
