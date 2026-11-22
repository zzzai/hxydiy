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
        html="""<form onsubmit="event.preventDefault(); document.getElementById('sent').value=String(Number(document.getElementById('sent').value)+1); if(window.mode==='success'||(window.mode==='blur_required'&&window.passwordCommitted)){location.hash='/main';document.getElementById('tenant').innerText='荷小悦（1581452）';}">
        <input placeholder="账户" type="text"><input placeholder="密码" type="password"><button type="submit">登 录</button></form>
        <output id="sent">0</output><p id="tenant"></p><p id="challenge"></p><script>window.mode='success'</script>"""
        context.route('**/*',lambda route:route.fulfill(status=200,content_type='text/html; charset=utf-8',body=html))
        page=context.new_page();page.goto(URL)
        yield page
        browser.close()


def test_background_login_success_and_no_second_secret_read(login_page,tmp_path):
    page=login_page;loaded=[]
    def load(_):loaded.append(True);return Credentials('synthetic-user','synthetic-pass')
    ensure_login(page,tmp_path,load=load,timeout_seconds=3)
    assert page.locator('#sent').inner_text()=='1'
    ensure_login(page,tmp_path,load=load,timeout_seconds=3)
    assert loaded==[True]
    state=json.loads((tmp_path/'login-state.json').read_bytes())
    assert state['status']=='authenticated' and 'synthetic' not in json.dumps(state)


def test_wrong_password_stops_and_never_retries(login_page,tmp_path):
    page=login_page;page.evaluate("window.mode='failure'")
    load=lambda _:Credentials('synthetic-user','synthetic-pass')
    with pytest.raises(Stop,match='source_login_tenant_unproven'):ensure_login(page,tmp_path,load=load,timeout_seconds=.1)
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


def test_login_completes_password_change_before_submit(login_page,tmp_path):
    page=login_page
    page.evaluate("window.mode='blur_required';document.querySelector('input[type=password]').addEventListener('change',()=>window.passwordCommitted=true)")
    ensure_login(page,tmp_path,load=lambda _:Credentials('synthetic-user','synthetic-pass'),timeout_seconds=.5)
    assert page.locator('#sent').inner_text()=='1'


def test_source_error_is_redacted_and_latched(login_page,tmp_path):
    page=login_page;page.evaluate("window.mode='failure';document.querySelector('button').addEventListener('click',()=>document.getElementById('tenant').innerText='账号或密码错误')")
    with pytest.raises(Stop,match='source_login_credentials_rejected'):
        ensure_login(page,tmp_path,load=lambda _:Credentials('synthetic-user','synthetic-pass'),timeout_seconds=.5)
    assert json.loads((tmp_path/'login-state.json').read_bytes())['stage']=='verify_tenant'


def test_account_picker_selects_only_verified_tenant(login_page):
    from source_login import select_account
    page=login_page
    page.evaluate('(html)=>document.body.innerHTML=html', "<div role='dialog'><div class='ant-modal-title'>选择要登录的账号</div><div class='account_selecter_item' onclick='window.selected=1'><div class='shopname'><div class='name'>荷小悦</div></div><div class='info'><div class='name'>紫薇壹号店</div></div></div><div class='account_selecter_item' onclick='window.selected=2'><div class='shopname'><div class='name'>荷小悦</div></div><div class='info'><div class='name'>荷小悦</div></div></div></div>")
    assert select_account(page)
    assert page.evaluate('window.selected')==2
    page.locator('.account_selecter_item').last.evaluate('(e)=>e.parentElement.append(e.cloneNode(true))')
    with pytest.raises(Stop,match='source_login_account_choice_ambiguous'):select_account(page)


def test_pending_account_selection_resumes_without_password(login_page,tmp_path):
    import runner
    page=login_page
    html="<div role='dialog'><div class='ant-modal-title'>选择要登录的账号</div><div class='account_selecter_item'><div class='shopname'><div class='name'>荷小悦</div></div><div class='info'><div class='name'>荷小悦</div></div></div></div><p id='tenant'></p>"
    page.evaluate('(html)=>document.body.innerHTML=html',html)
    page.evaluate("() => {document.querySelector('.account_selecter_item').onclick=()=>{document.querySelector('[role=dialog]').remove();location.hash='/main';document.querySelector('#tenant').innerText='荷小悦（1581452）'}}")
    runner.save(tmp_path/'login-state.json',{'blocked':True,'status':'attempting'})
    def forbidden(_):raise AssertionError('must finish picker without resubmitting credentials')
    ensure_login(page,tmp_path,load=forbidden,timeout_seconds=3)
    assert json.loads((tmp_path/'login-state.json').read_bytes())['status']=='authenticated'

def test_authenticated_shell_waits_for_visible_tenant_without_credentials(login_page,tmp_path):
    page=login_page
    page.evaluate("""() => {
      location.hash='/main/iframe';
      document.body.innerHTML='<p hidden>荷小悦（1581452）</p><span id="identity"></span>';
      setTimeout(()=>document.getElementById('identity').textContent='荷小悦 （ 1581452 ）',150);
    }""")
    import runner
    runner.save(tmp_path/'login-state.json',{'status':'blocked','blocked':True})
    def forbidden(_):raise AssertionError('authenticated page must not load credentials')
    ensure_login(page,tmp_path,load=forbidden,timeout_seconds=3)
    assert page.locator('#identity').inner_text()=='荷小悦 （ 1581452 ）'
    assert json.loads((tmp_path/'login-state.json').read_bytes())['blocked'] is False


@pytest.mark.parametrize('route,label',[('/main','荷小悦（1581453）'),('/main','其他荷小悦（1581452）'),
    ('/other','荷小悦（1581452）')])
def test_unproven_tenant_keeps_lock(login_page,tmp_path,route,label):
    import runner
    runner.save(tmp_path/'login-state.json',{'status':'blocked','blocked':True})
    login_page.evaluate("""([route,label])=>{location.hash=route; document.body.innerHTML='<p></p>';
      document.querySelector('p').textContent=label}""",[route,label])
    def forbidden(_):raise AssertionError('unproven scope must not load credentials')
    with pytest.raises(Stop):ensure_login(login_page,tmp_path,load=forbidden,timeout_seconds=.3)
    assert json.loads((tmp_path/'login-state.json').read_bytes())['blocked'] is True


def test_pending_picker_loads_unique_visible_account_then_waits_for_scope(login_page,tmp_path):
    import runner
    page=login_page
    page.evaluate("""() => {
      window.picks=0;
      document.body.innerHTML='<div role="dialog"><h2>选择要登录的账号</h2></div>';
      const dialog=document.querySelector('[role=dialog]');
      const row='<div class="account_selecter_item"><div class="info"><b class="name">荷小悦</b></div><div class="shopname"><b class="name">荷小悦</b></div></div>';
      setTimeout(()=>{ dialog.innerHTML+=row+row;dialog.querySelector('div').hidden=true;
        dialog.lastElementChild.onclick=()=>{window.picks++;dialog.remove();location.hash='/main';
          setTimeout(()=>document.body.innerHTML='<p>荷小悦（1581452）</p>',100);};
      },120);
    }""")
    runner.save(tmp_path/'login-state.json',{'status':'attempting','blocked':True})
    def forbidden(_):raise AssertionError('open picker must never resubmit credentials')
    ensure_login(page,tmp_path,load=forbidden,timeout_seconds=3)
    assert page.evaluate('window.picks')==1
    assert json.loads((tmp_path/'login-state.json').read_bytes())['blocked'] is False


def test_challenge_takes_precedence_over_open_account_picker(login_page,tmp_path):
    page=login_page
    page.evaluate("""()=>{document.body.innerHTML='<div role="dialog">选择要登录的账号<div class="account_selecter_item"><div class="info"><b class="name">荷小悦</b></div><div class="shopname"><b class="name">荷小悦</b></div></div></div><p>安全验证</p>';
      document.querySelector('.account_selecter_item').onclick=()=>window.picked=true;}""")
    def forbidden(_):raise AssertionError('challenge must not load credentials')
    with pytest.raises(Stop,match='source_login_challenge_required'):
        ensure_login(page,tmp_path,load=forbidden,timeout_seconds=.3)
    assert not page.evaluate('Boolean(window.picked)')


def test_initial_route_can_resolve_to_login_before_the_only_submission(login_page,tmp_path):
    page=login_page
    page.evaluate("""()=>{history.replaceState(null,'',location.pathname);setTimeout(()=>location.hash='/login',150)}""")
    loads=[]
    def load(_):
        loads.append(True)
        return Credentials('synthetic-user','synthetic-pass')
    ensure_login(page,tmp_path,load=load,timeout_seconds=3)
    assert loads==[True] and page.locator('#sent').inner_text()=='1'


def test_tenant_marker_in_an_unclosed_picker_cannot_unlock_login(login_page,tmp_path):
    import runner
    page=login_page
    page.evaluate("""()=>{location.hash='/main';
      document.body.innerHTML='<div role="dialog"><h2>选择要登录的账号</h2><p>荷小悦（1581452）</p></div>'}""")
    runner.save(tmp_path/'login-state.json',{'status':'blocked','blocked':True})
    def forbidden(_):raise AssertionError('ambiguous source scope must not load credentials')
    with pytest.raises(Stop,match='source_login_tenant_unproven'):
        ensure_login(page,tmp_path,load=forbidden,timeout_seconds=.3)
    assert json.loads((tmp_path/'login-state.json').read_bytes())['blocked'] is True
