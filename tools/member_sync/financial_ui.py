"""Normal source query controls over the private browser pipe; no desktop input or credentials."""
from datetime import datetime, timezone
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

from contracts import require,SHOP,TENANT_MARKER,SHOP_MARKER
from collector import Collector
from financial_collector import FinancialCollector,activate,wait_finance_page,wait_source_change
from ledger_collector import collect_ledger
from payment_collector import collect_payments
from finance_schedule import query_dates,verify_evidence
from runner import save
from source_login import trusted_page,allowed_login_url


def wait(page,predicate,code,seconds=90):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        require(not page.is_closed(),'finance_browser_closed')
        require(trusted_page(page.url) and not allowed_login_url(page.url),'finance_login_required')
        if predicate():return
        page.wait_for_timeout(250)
    require(False,code)


def navigate(page,section,menu):
    require(trusted_page(page.url) and not allowed_login_url(page.url),'finance_login_required')
    label=page.locator('span.label').filter(has_text=re.compile('^'+re.escape(section)+'$'))
    if label.count()!=1:label=page.get_by_text(section,exact=True)
    activate(label)
    activate(page.get_by_role('menuitem',name=menu,exact=True))


def card_frame(page):
    frames=[f for f in page.frames if urlsplit(f.url).hostname=='gray.aizhb.net' and
            urlsplit(f.url).path.endswith('/customerRelation/index.html') and urlsplit(f.url).fragment.startswith('/card-search')]
    return frames[0] if len(frames)==1 else None


def select_store_dialog(page):
    dialogs=page.get_by_role('dialog').filter(has=page.get_by_text('门店选择',exact=True))
    if dialogs.count()==0:return False
    require(dialogs.count()==1,'finance_initial_store_dialog_ambiguous')
    require(page.get_by_text(TENANT_MARKER).filter(visible=True).count()==1,'tenant_not_verified')
    target=dialogs.locator('.group-list__item[title="1581453 荷小悦"]').filter(has=page.get_by_text(SHOP,exact=True))
    require(target.count()==1,'finance_initial_store_choice_ambiguous')
    target.click()
    return True


def member_query(page):
    page.set_default_timeout(15000)
    require('/login' not in page.url,'finance_login_required')
    if card_frame(page) is None:navigate(page,'顾客','会员卡查询')
    wait(page,lambda:card_frame(page) is not None,'finance_card_page_missing')
    select_store_dialog(page)
    f=card_frame(page)
    wait(page,lambda:f.locator('.shop-selector-input').count()==1,'finance_card_filter_missing')
    if f.locator('.shop-selector-input').inner_text().strip()!=SHOP:
        f.locator('.shop-selector-input').click()
        choices=f.locator('label.dialog-selector__item')
        require(choices.locator('input[value="1581453"]').count()==1,'finance_store_choice_missing')
        for label in choices.all():
            checkbox=label.locator('input')
            require(checkbox.count()==1,'finance_store_choice_ambiguous')
            desired=checkbox.get_attribute('value')=='1581453'
            if checkbox.is_checked()!=desired:label.click()
        activate(f.get_by_role('button',name='保存',exact=True))
    # Validate the complete scope, blank search and normal page size before querying.
    f=Collector(page,set()).frame()
    activate(f.get_by_role('button',name='查询',exact=True))
    page.wait_for_timeout(1500)
    Collector(page,set()).frame()


def wait_query_controls(page,kind,seconds=90):
    require(kind in ('ledger','payments'),'finance_query_type_invalid')
    def ready():
        inputs=page.locator('.range-input:visible')
        start=page.get_by_placeholder('开始时间',exact=True).filter(visible=True)
        button=page.get_by_role('button',name=re.compile(r'^查\s*询$'))
        store=page.get_by_text(SHOP_MARKER).filter(visible=True)
        if inputs.count()!=2 or start.count()!=1 or store.count()!=1 or button.count()!=1 or not button.is_enabled():
            return False
        if kind=='ledger':
            return (urlsplit(page.url).fragment.partition('?')[0]=='/main/bill-record' and
                    page.get_by_placeholder('单号/手机号/卡号',exact=True).filter(visible=True).count()==1)
        return page.locator('.ant-select-selection-item:visible').all_text_contents()[:2]==['全部支付方式','全部支付状态']
    # A default date range may not have a paginator. Inspect results only after the query.
    wait(page,ready,'finance_'+kind+'_not_ready',seconds)


def submit_date_query(page,timeout=20000):
    # A pre-existing page one belongs to the previous date range until the source updates its results.
    watch=page.evaluate_handle("""()=> {
      const result='table.vxe-table--body tbody, .ant-pagination-total-text';
      const state={changed:false};
      const isResult=node=>node.nodeType===1 && (node.matches(result) || node.querySelector(result));
      state.observer=new MutationObserver(records=>{
        for (const m of records) {
          const element=m.target.nodeType===1 ? m.target : m.target.parentElement;
          if(element?.closest(result) || [...m.addedNodes,...m.removedNodes].some(isResult)){
            state.changed=true;break;
          }
        }
      });
      state.observer.observe(document.body,{childList:true,subtree:true,characterData:true,attributes:true,attributeFilter:['rowid']});
      return state;
    }""")
    try:
        activate(page.get_by_role('button',name=re.compile(r'^查\s*询$')))
        wait_source_change(page,'state=>state.changed',watch,timeout=timeout)
        wait_finance_page(page,1,timeout=timeout)
    finally:
        try:watch.evaluate('state=>state.observer.disconnect()')
        finally:watch.dispose()


def set_dates(page,dates):
    require(len(dates)==2,'finance_date_range_invalid')
    start=page.get_by_placeholder('开始时间',exact=True).filter(visible=True)
    require(start.count()==1,'finance_start_date_ambiguous')
    start.click()
    calendar=page.locator('.calendar:visible')
    header=calendar.locator('.calendar_header__center:visible')

    def displayed_month():
        if calendar.count()!=1 or header.count()!=1:
            return None
        match=re.fullmatch(r'\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*',header.inner_text())
        if not match or not 1<=int(match[2])<=12:
            return None
        return int(match[1])*12+int(match[2])-1

    for value in dates:
        target=datetime.fromisoformat(value)
        # The popover mounts asynchronously and can retain a hidden calendar from the previous route.
        wait(page,lambda:displayed_month() is not None,'finance_calendar_ambiguous',8)
        month=displayed_month()
        desired=target.year*12+target.month-1
        require(month is not None and abs(desired-month)<=120,'finance_calendar_range_exceeded')
        step=1 if desired>month else -1
        for expected in range(month+step,desired+step,step):
            activate(calendar.locator('.next_icon:visible' if step>0 else '.prev_icon:visible'))
            wait(page,lambda:displayed_month()==expected,'finance_calendar_month_not_changed',8)
        days=calendar.locator('.calendar_date:visible:not(.calendar_date--grey)').filter(has_text=re.compile(r'^\s*'+str(target.day)+r'\s*$'))
        activate(days)
    times=page.locator('.time-input:visible');require(times.count()==2,'finance_calendar_time_ambiguous')
    for position,value in enumerate(dates):
        times.nth(position).fill(value[11:16]);times.nth(position).press('Tab')
    buttons=page.locator('.picker-footer:visible button:visible');require(buttons.count()==2,'finance_calendar_footer_changed')
    activate(buttons.nth(1))
    inputs=page.locator('.range-input:visible')
    wait(page,lambda:inputs.evaluate_all('es=>es.map(e=>e.value)')==dates,'finance_date_selection_mismatch',8)
    submit_date_query(page)


def collect_finance(page,source):
    source=Path(source)
    member_query(page)
    one=FinancialCollector(page,lambda value:save(source/'collection-pass1.json',value)).collect_financial()
    two=FinancialCollector(page,lambda value:save(source/'collection-pass2.json',value)).collect_financial()
    targets={row['bill_no'] for history in two['histories'].values() for p in history['pages'] for row in p['rows']}
    dates=query_dates(two['histories'])
    navigate(page,'流水','营业流水')
    wait_query_controls(page,'ledger')
    set_dates(page,dates)
    collect_ledger(page,targets,lambda value:save(source/'ledger-pass1.json',value))
    navigate(page,'流水','收款流水')
    wait_query_controls(page,'payments')
    set_dates(page,dates)
    collect_payments(page,targets,lambda value:save(source/'payments-pass1.json',value))
    member_query(page)
    verify_evidence(source)
