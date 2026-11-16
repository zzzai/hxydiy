"""Normal source query controls over the private browser pipe; no desktop input or credentials."""
from datetime import datetime, timezone
from pathlib import Path
import re
import time
from urllib.parse import urlsplit

from contracts import require,SHOP
from collector import Collector
from financial_collector import FinancialCollector,activate
from ledger_collector import collect_ledger
from payment_collector import collect_payments
from finance_schedule import query_dates,verify_evidence
from runner import save


def wait(page,predicate,code,seconds=90):
    deadline=time.monotonic()+seconds
    while time.monotonic()<deadline:
        require(not page.is_closed(),'finance_browser_closed')
        require(urlsplit(page.url).hostname=='gray.aizhb.net' and '/login' not in page.url,'finance_login_required')
        if predicate():return
        page.wait_for_timeout(250)
    require(False,code)


def navigate(page,section,menu):
    require(urlsplit(page.url).hostname=='gray.aizhb.net' and '/login' not in page.url,'finance_login_required')
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
    require(page.get_by_text(re.compile(r'荷小悦\s*[（(]1581452[)）]')).count()==1,'tenant_not_verified')
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


def set_dates(page,dates):
    require(len(dates)==2,'finance_date_range_invalid')
    page.get_by_placeholder('开始时间',exact=True).click()
    for value in dates:
        target=datetime.fromisoformat(value)
        header=page.locator('.calendar_header__center')
        require(header.count()==1,'finance_calendar_ambiguous')
        match=re.fullmatch(r'\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*',header.inner_text())
        require(match is not None,'finance_calendar_schema_changed')
        months=(target.year-int(match[1]))*12+target.month-int(match[2])
        require(abs(months)<=120,'finance_calendar_range_exceeded')
        for _ in range(abs(months)):
            activate(page.locator('.next_icon' if months>0 else '.prev_icon'))
        days=page.locator('.calendar_date:not(.calendar_date--grey)').filter(has_text=re.compile('^\s*'+str(target.day)+'\s*$'))
        activate(days)
    times=page.locator('.time-input');require(times.count()==2,'finance_calendar_time_ambiguous')
    for position,value in enumerate(dates):
        times.nth(position).fill(value[11:16]);times.nth(position).press('Tab')
    buttons=page.locator('.picker-footer button');require(buttons.count()==2,'finance_calendar_footer_changed')
    activate(buttons.nth(1))
    require(page.locator('.range-input').evaluate_all('es=>es.map(e=>e.value)')==dates,'finance_date_selection_mismatch')
    activate(page.get_by_role('button',name=re.compile('^查\s*询$')))
    page.wait_for_timeout(1500)
    wait(page,lambda:page.locator('.ant-pagination-item-active').count()==1 and
         page.locator('.ant-pagination-item-active').inner_text().strip()=='1','finance_query_not_ready')


def collect_finance(page,source):
    source=Path(source)
    member_query(page)
    one=FinancialCollector(page,lambda value:save(source/'collection-pass1.json',value)).collect_financial()
    two=FinancialCollector(page,lambda value:save(source/'collection-pass2.json',value)).collect_financial()
    targets={row['bill_no'] for history in two['histories'].values() for p in history['pages'] for row in p['rows']}
    dates=query_dates(two['histories'])
    navigate(page,'流水','营业流水')
    wait(page,lambda:page.locator('.range-input').count()==2 and page.locator('.ant-pagination-total-text').count()==1,'finance_ledger_not_ready')
    require(page.locator('.ant-pagination .ant-select-selection-item').inner_text()=='10 条/页','finance_ledger_size_changed')
    set_dates(page,dates)
    collect_ledger(page,targets,lambda value:save(source/'ledger-pass1.json',value))
    navigate(page,'流水','收款流水')
    wait(page,lambda:page.locator('.range-input').count()==2 and page.locator('.ant-pagination-total-text').count()==1,'finance_payments_not_ready')
    set_dates(page,dates)
    collect_payments(page,targets,lambda value:save(source/'payments-pass1.json',value))
    member_query(page)
    verify_evidence(source)
