"""Fill only the verified source login form, once, using local encrypted credentials."""
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
from contracts import TENANT_MARKER as TENANT, Stop,require
from runner import save,utc
from source_credentials import load_credentials

PATH='/shair/components/shair-web/base-system/index.html'
ACCOUNT=re.compile(r'^\s*荷小悦\s*$')


def trusted_page(url):
    try:
        p=urlsplit(url)
        return p.scheme=='https' and p.hostname=='gray.aizhb.net' and p.port in (None,443) and not p.username and not p.password and p.path==PATH
    except ValueError:return False


def allowed_login_url(url):
    return trusted_page(url) and urlsplit(url).fragment.split('?',1)[0]=='/login'


def challenge(page):
    labels=page.get_by_text(re.compile('验证码|滑块|拖动.*验证|安全验证'))
    return any(label.is_visible() for label in labels.all())



def account_dialogs(page):
    return page.get_by_role('dialog').filter(has=page.get_by_text('选择要登录的账号',exact=True))


def select_account(page,timeout_seconds=0):
    dialogs=account_dialogs(page)
    if dialogs.count()==0:return False
    require(dialogs.count()==1 and allowed_login_url(page.url),'source_login_account_choice_ambiguous')
    # The tenant account and the store account can have the same brand label.
    target=dialogs.locator('.account_selecter_item:visible').filter(
        has=page.locator('.info .name:visible').filter(has_text=ACCOUNT)).filter(
        has=page.locator('.shopname .name:visible').filter(has_text=ACCOUNT))
    deadline=time.monotonic()+timeout_seconds
    while target.count()==0 and time.monotonic()<deadline:
        require(allowed_login_url(page.url),'source_login_origin_rejected')
        require(not challenge(page),'source_login_challenge_required')
        page.wait_for_timeout(100)
    require(allowed_login_url(page.url) and dialogs.count()==1 and target.count()==1,'source_login_account_choice_ambiguous')
    require(not challenge(page),'source_login_challenge_required')
    target.click()
    return True


def wait_for_identity(page,timeout_seconds):
    deadline=time.monotonic()+timeout_seconds
    selected=False
    while True:
        require(trusted_page(page.url),'source_login_origin_rejected')
        require(not challenge(page),'source_login_challenge_required')
        route=urlsplit(page.url).fragment.partition('?')[0]
        if route=='/main' or route.startswith('/main/'):
            if not account_dialogs(page).count() and page.get_by_text(TENANT).filter(visible=True).count()==1:
                return
        elif allowed_login_url(page.url):
            errors=page.get_by_text(re.compile('(?:账号|账户).*密码.*(?:错误|不正确)|密码(?:错误|不正确)|(?:账号|账户)不存在'))
            require(not any(error.is_visible() for error in errors.all()),'source_login_credentials_rejected')
            if not selected:
                selected=select_account(page,max(0,deadline-time.monotonic()))
        else:
            require(route in ('','/'),'source_login_tenant_unproven')
        if time.monotonic()>=deadline:
            raise Stop('source_login_tenant_unproven')
        page.wait_for_timeout(100)


def initial_screen(page,timeout_seconds):
    deadline=time.monotonic()+timeout_seconds
    while time.monotonic()<deadline:
        require(trusted_page(page.url),'source_login_origin_rejected')
        route=urlsplit(page.url).fragment.partition('?')[0]
        if route=='/main' or route.startswith('/main/'):
            return 'main'
        if allowed_login_url(page.url):
            require(not challenge(page),'source_login_challenge_required')
            if account_dialogs(page).count():
                return 'picker'
            if page.get_by_placeholder('账户',exact=True).filter(visible=True).count():
                return 'form'
        else:
            require(route in ('','/'),'source_login_tenant_unproven')
        page.wait_for_timeout(100)
    raise Stop('source_login_screen_unproven')


def ensure_login(page,root,load=load_credentials,timeout_seconds=45):
    root=Path(root);require(trusted_page(page.url),'source_login_origin_rejected')
    state_path=root/'login-state.json'
    screen=initial_screen(page,timeout_seconds)
    if screen!='form':
        wait_for_identity(page,timeout_seconds)
        save(state_path,{'status':'authenticated','blocked':False,'updated_at':utc()})
        return {'status':'already_authenticated' if screen=='main' else 'authenticated'}
    state=json.loads(state_path.read_bytes()) if state_path.exists() else {}
    require(state.get('blocked') is not True,'source_login_latched')
    account=page.get_by_placeholder('账户',exact=True);password=page.get_by_placeholder('密码',exact=True)
    button=page.get_by_role('button',name=re.compile(r'^登\s*录$'))
    require(not challenge(page),'source_login_challenge_required')
    require(account.count()==password.count()==button.count()==1 and
            account.is_visible() and password.is_visible() and account.get_attribute('type')=='text' and
            password.get_attribute('type')=='password','source_login_form_changed')
    require(account.evaluate('e=>e.form!==null && e.form===document.querySelector(\'input[type="password"]\').form'),'source_login_form_changed')
    require(not os.environ.get("DEBUG") and not os.environ.get("PWDEBUG"),"source_login_debug_logging_enabled")
    credentials=load(root)
    # A durable one-attempt latch is written before filling or submitting.
    save(state_path,{'status':'attempting','blocked':True,'started_at':utc()})
    stage='fill_account'
    try:
        require(allowed_login_url(page.url),'source_login_origin_rejected')
        account.fill(credentials.account)
        stage='fill_password'
        require(allowed_login_url(page.url),'source_login_origin_rejected')
        password.fill(credentials.password)
        require(allowed_login_url(page.url) and not challenge(page),'source_login_challenge_required')
        stage='submit'
        button.click()
        stage='verify_tenant'
        credentials=None
        wait_for_identity(page,timeout_seconds)
        save(state_path,{'status':'authenticated','blocked':False,'updated_at':utc()})
        return {'status':'authenticated'}
    except Exception as exc:
        credentials=None
        code=str(exc) if isinstance(exc,Stop) else 'source_login_failed'
        save(state_path,{'status':'blocked','blocked':True,'code':code,'stage':stage,'updated_at':utc()})
        # Never propagate Playwright call logs, which can include fill arguments.
        try:
            if allowed_login_url(page.url):account.fill('');password.fill('')
        except Exception:pass
        raise Stop(code) from None
