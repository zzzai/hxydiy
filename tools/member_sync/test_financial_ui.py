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
    with pytest.raises(TimeoutError):wait_finance_page(page,2,timeout=200)

def test_ledger_accepts_ready_store_query_before_pagination_exists(login_page):
    from financial_ui import wait_query_controls
    page=login_page
    page.evaluate("""()=>{location.hash='/main/bill-record';
      document.body.innerHTML='<p>紫薇壹号店（1581453）</p><input class="range-input" placeholder="开始时间"><input class="range-input"><input placeholder="单号/手机号/卡号"><button>查 询</button><table class="vxe-table--body"></table>'}""")
    wait_query_controls(page,'ledger',seconds=1)
    assert page.locator('.ant-pagination-total-text').count()==0
    page.locator('p').evaluate("e=>e.textContent='紫薇壹号店（1581454）'")
    with pytest.raises(Stop,match='finance_ledger_not_ready'):wait_query_controls(page,'ledger',seconds=.2)
    page.locator('p').evaluate("e=>e.textContent='紫薇壹号店（1581453）'")
    page.evaluate("location.hash='/main/other'")
    with pytest.raises(Stop,match='finance_ledger_not_ready'):wait_query_controls(page,'ledger',seconds=.2)


def test_first_finance_page_requires_unambiguous_total_and_terminal_empty(login_page):
    from financial_collector import wait_finance_page
    from playwright.sync_api import TimeoutError
    page=login_page
    page.evaluate("""()=>document.body.innerHTML='<div class="ant-pagination-item-active">1</div><div class="ant-pagination-next ant-pagination-disabled"></div><table class="vxe-table--body"><tbody><tr rowid="a"><td>synthetic</td></tr></tbody></table>'""")
    with pytest.raises(TimeoutError):wait_finance_page(page,1,timeout=200)
    page.evaluate("""()=>{document.querySelector('tbody').innerHTML='';document.body.insertAdjacentHTML('beforeend','<span class="ant-pagination-total-text">共计 0 条</span>')}""")
    wait_finance_page(page,1,timeout=500)
    page.evaluate("document.querySelector('.ant-pagination-next').classList.remove('ant-pagination-disabled')")
    with pytest.raises(TimeoutError):wait_finance_page(page,1,timeout=200)


def test_date_query_requires_results_for_new_dates_even_when_page_one_is_already_visible(login_page):
    from financial_ui import submit_date_query
    from playwright.sync_api import TimeoutError
    page=login_page
    page.evaluate("""()=>{document.body.innerHTML='<button>查 询</button><div class="ant-pagination-item-active">1</div><div class="ant-pagination-next ant-pagination-disabled"></div><div class="ant-pagination-total-text">共计 1 条</div><table class="vxe-table--body"><tbody><tr rowid="before"><td>synthetic</td></tr></tbody></table><aside></aside>';
      document.querySelector('button').onclick=()=>{document.querySelector('aside').textContent='menu updated'};}""")
    with pytest.raises(TimeoutError):submit_date_query(page,timeout=220)
    page.evaluate("""()=>{document.querySelector('button').onclick=()=>{
      setTimeout(()=>{document.querySelector('tbody').innerHTML='<tr rowid="after"><td>synthetic</td></tr>'},100);
    }}""")
    submit_date_query(page,timeout=1500)
    assert page.locator('tbody tr').get_attribute('rowid')=='after'


def test_payment_query_uses_its_own_filters_without_default_rows(login_page):
    from financial_ui import wait_query_controls
    page=login_page
    page.evaluate("""()=>{location.hash='/main/payments';
      document.body.innerHTML='<p>紫薇壹号店（1581453）</p><input class="range-input" placeholder="开始时间"><input class="range-input"><button>查询</button><span class="ant-select-selection-item">全部支付方式</span><span class="ant-select-selection-item">全部支付状态</span>'}""")
    wait_query_controls(page,'payments',seconds=1)
    page.locator('.ant-select-selection-item').last.evaluate("e=>e.textContent='other'")
    with pytest.raises(Stop,match='finance_payments_not_ready'):wait_query_controls(page,'payments',seconds=.2)


def test_ledger_scans_each_bill_page_when_table_reuses_row_slots(login_page):
    from contracts import SHOP
    from ledger_collector import FIELDS,collect_ledger
    page=login_page
    page.evaluate("""([fields,store])=>{
      location.hash='/main/bill-record';
      document.body.innerHTML='<p>紫薇壹号店（1581453）</p><input placeholder="单号/手机号/卡号"><input type="radio" value="ALL" checked><div class="ant-pagination"><span class="ant-select-selection-item">10 条/页</span><span class="ant-pagination-item-active">1</span><span class="ant-pagination-total-text">共计 23 条</span><span class="ant-pagination-next"><button>下一页</button></span></div><table class="vxe-table--header"><thead><tr></tr></thead></table><table class="vxe-table--body"><tbody></tbody></table><div class="vxe-table--scroll-y-handle"></div>';
      document.querySelector('thead tr').innerHTML=fields.map((v,i)=>'<th class="col_'+i+'">'+v+'</th>').join('');
      const body=document.querySelector('tbody'), next=document.querySelector('.ant-pagination-next');
      function render(number) {
        body.innerHTML=Array.from({length:Math.min(10,23-(number-1)*10)},(_,slot)=>{
          const idx=(number-1)*10+slot;
          return '<tr rowid="slot'+slot+'">'+fields.map((v,i)=>'<td class="col_'+i+'">'+
            (v==='单号'?'SYN-'+idx:v==='消费门店'?store:'synthetic')+'</td>').join('')+'</tr>';}).join('');
        next.classList.toggle('ant-pagination-disabled',number===3);
      }
      render(1);
      next.querySelector('button').onclick=()=>{
        const active=document.querySelector('.ant-pagination-item-active');
        const number=Number(active.textContent)+1; active.textContent=String(number);
        setTimeout(()=>render(number),120);
      };
    }""",[FIELDS,SHOP])
    targets={'SYN-0','SYN-15','SYN-22'}
    result=collect_ledger(page,targets,lambda _:None)
    assert [p['source_rows'] for p in result['pages']]==[10,10,3]
    assert [p['last'] for p in result['pages']]==[False,False,True]
    assert [r['单号'] for p in result['pages'] for r in p['rows']]==['SYN-0','SYN-15','SYN-22']
