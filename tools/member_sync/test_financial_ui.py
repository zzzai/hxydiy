"""Normal query navigation only selects the scoped source store."""
import pytest
from contracts import Stop
from test_source_login import login_page
from financial_ui import select_store_dialog


def test_initial_store_picker_requires_id_and_name(login_page):
    page=login_page
    html="<p>荷小悦（1581452）</p><div role='dialog'><div class='custom-modal__header'>门店选择</div><div class='group-list__item' title='1581454 荷小悦' onclick='window.selected=2'><div class='store-name'>华富世家店</div></div><div class='group-list__item' title='1581453 荷小悦' onclick='window.selected=1;this.parentElement.remove()'><div class='store-name'>紫薇壹号店</div></div></div>"
    page.evaluate('(html)=>document.body.innerHTML=html',html)
    assert select_store_dialog(page) is True
    assert page.evaluate('window.selected')==1
    assert select_store_dialog(page) is False
    page.evaluate('(html)=>document.body.innerHTML=html',html.replace('1581453','1581499'))
    with pytest.raises(Stop,match='finance_initial_store_choice_ambiguous'):select_store_dialog(page)
    page.evaluate('(html)=>document.body.innerHTML=html',html.replace('紫薇壹号店','other store'))
    with pytest.raises(Stop,match='finance_initial_store_choice_ambiguous'):select_store_dialog(page)


def test_background_wait_survives_paused_render_frames(login_page):
    from financial_collector import wait_source_change
    page=login_page
    page.evaluate("() => { window.requestAnimationFrame=()=>0; window.queryReady=false; setTimeout(()=>{window.queryReady=true},100); }")
    wait_source_change(page,'()=>window.queryReady',None,timeout=700)
    assert page.evaluate('window.queryReady') is True
    from playwright.sync_api import TimeoutError
    with pytest.raises(TimeoutError):wait_source_change(page,'()=>false',None,timeout=100)


def test_failure_state_excludes_url_secrets_and_page_content(login_page):
    from finance_schedule import collection_failure_state
    page=login_page
    page.evaluate("() => { history.replaceState(null,'','#/login?token=synthetic-secret'); document.body.innerHTML='<input placeholder=账户><p>synthetic-customer</p>'; }")
    result=collection_failure_state(page)
    assert result['expected_host'] and result['login_route'] and result['login_form']
    assert result['active_page_count']==0
    assert 'synthetic' not in str(result)


def test_finance_page_wait_requires_completed_target_page(login_page):
    from financial_collector import wait_finance_page
    from playwright.sync_api import TimeoutError
    page=login_page
    page.evaluate("""()=>document.body.innerHTML='<div class="ant-pagination-item-active">2</div><div class="ant-pagination-next"></div><div class="ant-pagination-total-text">共计 10 条</div><div class="ant-spin-spinning">Loading</div><table class="vxe-table--body"><tbody><tr rowid="new"><td>row</td></tr></tbody></table>'""")
    with pytest.raises(TimeoutError):wait_finance_page(page,2,'old',timeout=100)
    page.evaluate("()=>document.querySelector('.ant-spin-spinning').remove()")
    with pytest.raises(TimeoutError):wait_finance_page(page,3,'old',timeout=100)
    with pytest.raises(TimeoutError):wait_finance_page(page,2,'new',timeout=100)
    page.evaluate("()=>document.querySelector('tbody').innerHTML=''")
    with pytest.raises(TimeoutError):wait_finance_page(page,2,'old',timeout=100)
    page.evaluate("()=>setTimeout(()=>document.querySelector('tbody').innerHTML='<tr rowid=ready><td>row</td></tr>',50)")
    wait_finance_page(page,2,'old',timeout=1000)
    page.evaluate("()=>{document.querySelector('tbody').innerHTML='';document.querySelector('.ant-pagination-total-text').textContent='共计 0 条'}")
    wait_finance_page(page,2,timeout=1000)
