"""Fill only the verified source login form, once, using local encrypted credentials."""
import json
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
from contracts import Stop,require
from runner import save,utc
from source_credentials import load_credentials

PATH='/shair/components/shair-web/base-system/index.html'
TENANT=re.compile(r'荷小悦\s*[（(]1581452[)）]')


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


def ensure_login(page,root,load=load_credentials,timeout_seconds=45):
    root=Path(root);require(trusted_page(page.url),'source_login_origin_rejected')
    if not allowed_login_url(page.url):
        require(page.get_by_text(TENANT).count()==1,'source_login_tenant_unproven')
        return {'status':'already_authenticated'}
    state_path=root/'login-state.json'
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
    try:
        require(allowed_login_url(page.url),'source_login_origin_rejected')
        account.fill(credentials.account)
        require(allowed_login_url(page.url),'source_login_origin_rejected')
        password.fill(credentials.password)
        require(allowed_login_url(page.url) and not challenge(page),'source_login_challenge_required')
        button.dispatch_event('click')
        credentials=None
        deadline=time.monotonic()+timeout_seconds
        while time.monotonic()<deadline:
            require(trusted_page(page.url),'source_login_origin_rejected')
            if not allowed_login_url(page.url) and page.get_by_text(TENANT).count()==1:
                save(state_path,{'status':'authenticated','blocked':False,'updated_at':utc()})
                return {'status':'authenticated'}
            require(not challenge(page),'source_login_challenge_required')
            page.wait_for_timeout(200)
        raise Stop('source_login_failed')
    except Exception as exc:
        credentials=None
        code=str(exc) if isinstance(exc,Stop) else 'source_login_failed'
        save(state_path,{'status':'blocked','blocked':True,'code':code,'updated_at':utc()})
        # Never propagate Playwright call logs, which can include fill arguments.
        try:
            if allowed_login_url(page.url):account.fill('');password.fill('')
        except Exception:pass
        raise Stop(code) from None
