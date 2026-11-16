"""Credential confinement and one-attempt login contracts use synthetic values only."""
import json
import os
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from contracts import Stop
from source_credentials import Credentials, encode_credentials, decode_credentials, protect, unprotect
from source_login import allowed_login_url, ensure_login

URL='https://gray.aizhb.net/shair/components/shair-web/base-system/index.html#/login'

@pytest.mark.parametrize('url',[URL,URL+'?redirect=home'])
def test_login_allowlist(url):assert allowed_login_url(url)

@pytest.mark.parametrize('url',['http://gray.aizhb.net/shair/components/shair-web/base-system/index.html#/login',
    'https://gray.aizhb.net.evil.invalid/shair/components/shair-web/base-system/index.html#/login',
    'https://gray.aizhb.net/other#/login','https://gray.aizhb.net:444/shair/components/shair-web/base-system/index.html#/login',
    'https://name:pass@gray.aizhb.net/shair/components/shair-web/base-system/index.html#/login'])
def test_wrong_url_cannot_read_credentials(tmp_path,url):
    class Page:pass
    page=Page();page.url=url
    def forbidden(*a):raise AssertionError('credential read must not happen')
    with pytest.raises(Stop):ensure_login(page,tmp_path,load=forbidden)


def test_secret_representation_and_round_trip():
    c=Credentials('test account',' synthetic secret \" ')
    assert 'synthetic secret' not in repr(c) and 'test account' not in repr(c)
    restored=decode_credentials(encode_credentials(c))
    assert restored.account==c.account and restored.password==c.password
    invalid=json.loads(encode_credentials(c));invalid['origin']='https://other.invalid'
    with pytest.raises(Stop):decode_credentials(json.dumps(invalid).encode())


@pytest.mark.skipif(os.name!='nt',reason='Windows CurrentUser DPAPI')
def test_dpapi_round_trip_and_tamper():
    raw=encode_credentials(Credentials('synthetic','synthetic-password-only'))
    encrypted=protect(raw)
    assert b'synthetic' not in encrypted and unprotect(encrypted)==raw
    with pytest.raises(Stop):unprotect(encrypted[:-12]+b'corrupt-data')


@pytest.fixture
def login_page():
    if os.environ.get('HXY_LOGIN_BROWSER_TESTS')!='1':pytest.skip('isolated browser suite requires explicit flag')
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        browser=pw.chromium.launch(channel='chrome',headless=True)
        context=browser.new_context()
        html="""<form onsubmit="event.preventDefault(); document.getElementById('sent').value=String(Number(document.getElementById('sent').value)+1); if(window.mode==='success'){location.hash='/main';document.getElementById('tenant').innerText='荷小悦（1581452）';}">
        <input placeholder="账户" type="text"><input placeholder="密码" type="password"><button type="submit">登 录</button></form>
        <output id="sent">0</output><p id="tenant"></p><p id="challenge"></p><script>window.mode='success'</script>"""
        context.route('**/*',lambda route:route.fulfill(status=200,content_type='text/html; charset=utf-8',body=html))
        page=context.new_page();page.goto(URL)
        yield page
        browser.close()


def test_background_login_success_and_no_second_secret_read(login_page,tmp_path):
    page=login_page;loaded=[]
    def load(_):loaded.append(True);return Credentials('synthetic-user','synthetic-pass')
    ensure_login(page,tmp_path,load=load,timeout_seconds=1)
    assert page.locator('#sent').inner_text()=='1'
    ensure_login(page,tmp_path,load=load,timeout_seconds=1)
    assert loaded==[True]
    state=json.loads((tmp_path/'login-state.json').read_bytes())
    assert state['status']=='authenticated' and 'synthetic' not in json.dumps(state)


def test_wrong_password_stops_and_never_retries(login_page,tmp_path):
    page=login_page;page.evaluate("window.mode='failure'")
    load=lambda _:Credentials('synthetic-user','synthetic-pass')
    with pytest.raises(Stop,match='source_login_failed'):ensure_login(page,tmp_path,load=load,timeout_seconds=.1)
    assert page.locator('#sent').inner_text()=='1'
    with pytest.raises(Stop,match='source_login_latched'):ensure_login(page,tmp_path,load=load,timeout_seconds=.1)
    assert page.locator('#sent').inner_text()=='1'
    assert page.get_by_placeholder('密码',exact=True).input_value()==''
    assert 'synthetic' not in (tmp_path/'login-state.json').read_text()


def test_visible_challenge_prevents_password_access(login_page,tmp_path):
    page=login_page;page.locator('#challenge').evaluate("e=>e.innerText='请输入验证码'")
    def forbidden(_):raise AssertionError('challenge must not load credentials')
    with pytest.raises(Stop,match='source_login_challenge_required'):ensure_login(page,tmp_path,load=forbidden)
    assert page.locator('#sent').inner_text()=='0'


def test_debug_logging_blocks_secret_read(login_page,tmp_path,monkeypatch):
    monkeypatch.setenv('DEBUG','pw:api')
    def forbidden(_):raise AssertionError('debug must not load credentials')
    with pytest.raises(Stop,match='source_login_debug_logging_enabled'):ensure_login(login_page,tmp_path,load=forbidden)
