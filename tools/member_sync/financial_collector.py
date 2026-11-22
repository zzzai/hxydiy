"""Read source member finance through normal DOM controls, without OS input.

The output is private, read-only evidence. It is not an approved import packet.
No cookies, browser storage, network payloads, photos or staff details are read.
"""
from datetime import datetime, timezone
import re
import time

from collector import Collector, BODY, HOST
from contracts import SCOPE, SHOP, BAD_STATE, CARD_NAMES, require, source_key
from financial_contracts import amount, check_pages

HISTORY_HEADERS = ["单号", "消费时间", "消费信息", "消费金额", "消费门店", "备注"]


def utc():
    return datetime.now(timezone.utc).isoformat()


def activate(locator):
    require(locator.count() == 1 and locator.is_enabled(), "finance_control_ambiguous")
    # Dispatch only to observed query/navigation controls; never use OS mouse or focus.
    locator.dispatch_event("click")


def wait_source_change(page,predicate,previous,timeout=20000):
    # Background/minimized pages can pause animation frames; keep the same readiness and timeout.
    return page.wait_for_function(predicate,arg=previous,timeout=timeout,polling=200)


def wait_finance_page(page,number,previous=None,timeout=20000):
    # A changed/temporarily empty table does not prove that the requested page is ready.
    return wait_source_change(page,r"""args=>{
      const active=document.querySelectorAll('.ant-pagination-item-active');
      if(active.length!==1 || active[0].textContent.trim()!==String(args.number))return false;
      const next=document.querySelectorAll('.ant-pagination-next');
      const totals=document.querySelectorAll('.ant-pagination-total-text');
      if(next.length!==1 || totals.length!==1)return false;
      const total=/^共计\s*(\d+)\s*条$/.exec(totals[0].textContent.trim());
      if(!total)return false;
      if([...document.querySelectorAll('.ant-spin-spinning')].some(e=>e.getClientRects().length && getComputedStyle(e).visibility!=='hidden'))return false;
      const rows=[...document.querySelectorAll('table.vxe-table--body tbody tr')];
      const keys=rows.map(e=>e.getAttribute('rowid')).join('|');
      if(Number(total[1])===0)
        return args.number===1 && rows.length===0 && next[0].classList.contains('ant-pagination-disabled');
      if(!rows.length || rows.some(e=>!e.hasAttribute('rowid')))return false;
      if(args.previous==null)return true;
      if(typeof args.previous==='string')return keys!==args.previous;
      return args.previous.hasNewBusinessId();
    }""",previous={'number':number,'previous':previous},timeout=timeout)


def advance_finance_page(page,number,identity_cell):
    # Virtual tables may reuse rowid values on successive pages. Keep IDs inside this page only.
    proof=page.evaluate_handle("""selector=>{
      const read=()=>new Set(Array.from(document.querySelectorAll('table.vxe-table--body tbody tr[rowid]'))
        .map(row=>row.querySelector(selector)?.textContent.trim()).filter(Boolean));
      const before=read();
      return {hasRows:before.size>0,hasNewBusinessId:()=>[...read()].some(value=>!before.has(value))};
    }""",identity_cell)
    try:
        require(proof.evaluate('state=>state.hasRows'),'finance_page_business_id_missing')
        activate(page.locator('.ant-pagination-next button'))
        wait_finance_page(page,number,proof)
    finally:
        proof.dispose()


class FinancialCollector(Collector):
    def __init__(self, page, checkpoint):
        super().__init__(page, set())
        self.deadline = time.monotonic() + 7200
        self.checkpoint = checkpoint
        self.page.set_default_timeout(12000)

    def wait_until(self, predicate, code):
        end = time.monotonic() + 30
        while time.monotonic() < min(end, self.deadline):
            if predicate():
                return
            self.page.wait_for_timeout(200)
        require(False, code)

    def member(self, f, position, row, collect_history):
        link = f.locator(".el-table__fixed .el-table__fixed-body-wrapper tbody tr").nth(position).locator("td").nth(1).locator("a")
        activate(link)
        self.wait_until(lambda: self.page.locator(".member-card-box-item-content:visible").count() > 0,
                        "finance_member_not_loaded")
        drawer = self.page.locator(".ant-drawer:visible")
        require(drawer.count() == 1, "finance_member_drawer_ambiguous")
        try:
            cards = [card for card in drawer.locator(".member-card-box-item-content").all()
                     if card.locator(".content-body-info-item").filter(has_text="卡号：").locator(".is_edit").inner_text() == row["card_number"]]
            require(len(cards) == 1, "finance_card_owner_unproven")
            card = cards[0]
            require(card.locator(".content-title").inner_text().strip() == row["card_name"], "finance_card_name_conflict")
            require(not BAD_STATE.search(card.inner_text()), "finance_card_adverse_state")
            facts = card.locator(".content-center-item").all_text_contents()
            balances = [text for text in facts if text.startswith("余额:")]
            bonuses = [text for text in facts if text.startswith("赠金:")]
            require(len(balances) == len(bonuses) == 1, "finance_balance_schema_changed")
            label = drawer.locator(".base-box-item:has(.base-label:text-is('手机号：'))")
            require(label.count() == 1 and label.locator(".base-value").inner_text().strip() == row["masked_phone"],
                    "finance_phone_mask_conflict")
            activate(label.locator(".base-box-icon"))
            modal = self.unique_visible('[role="dialog"]:has-text("修改会员手机号")')
            try:
                phone = modal.get_by_placeholder("请输入", exact=True).input_value()
                require(re.fullmatch(r"1[3-9]\d{9}", phone) is not None, "finance_phone_not_complete")
                require(phone[:3] + "****" + phone[-4:] == row["masked_phone"], "finance_phone_mask_conflict")
            finally:
                activate(modal.get_by_role("button", name="取 消", exact=True))
            balance = {"card_number": row["card_number"], "phone": phone, "card_name": row["card_name"],
                       "store_name": SHOP, "observed_at": utc(), "source_balance_cents": amount(balances[0], "余额:"),
                       "source_bonus_cents": amount(bonuses[0], "赠金:"),
                       "list_balance_cents": amount("￥" + row["balance_yuan"].removeprefix("￥").removeprefix("¥")),
                       "principal_cents": None, "total_cents": None,
                       "balance_semantics": "source_labels_pending_reconciliation"}
            require(balance["list_balance_cents"] == balance["source_balance_cents"], "finance_balance_list_detail_conflict")
            history = self.history(drawer) if collect_history(phone) else None
            return balance, history
        finally:
            # Close only our exact member drawer after any child bill is closed.
            require(self.page.locator(".ant-drawer:visible").count() == 1, "finance_child_drawer_left_open")
            activate(drawer.locator(".ant-drawer-close"))

    def bill_detail(self, row_locator, bill_no):
        activate(row_locator.locator(".bill-no"))
        self.wait_until(lambda: self.page.locator(".ant-drawer:visible").count() == 2,
                        "finance_bill_not_loaded")
        bill = self.page.locator(".ant-drawer:visible").last
        try:
            self.wait_until(lambda: bill.locator(".left_title").count() == 1 and
                            bill.locator(".left_title").inner_text().strip() == "单据详情-" + bill_no and
                            bill.locator(".price_detail_item").count() > 0, "finance_bill_identity_unproven")
            return {"bill_no": bill_no, "observed_title": bill.locator(".left_title").inner_text().strip(),
                    "scope_and_time": bill.locator(".left_info_list_item").evaluate_all(
                        "(es)=>es.filter(e=>/^(结账时间|消费门店|顾客门店|客流)[：:]/.test(e.innerText)).map(e=>e.innerText)"),
                    "financial_summary": bill.locator(".price_detail_item,.pay_detail_item").all_text_contents(),
                    "refund_status": "unknown", "source_current_status": "unknown"}
        finally:
            activate(bill.locator(".ant-drawer-close"))

    def history(self, drawer):
        activate(drawer.get_by_text("消费记录", exact=True))
        self.wait_until(lambda: drawer.get_by_role("button", name="开始查询", exact=True).count() == 1,
                        "finance_history_query_missing")
        require(drawer.get_by_placeholder("开始时间", exact=True).input_value() == "" and
                drawer.get_by_placeholder("结束时间", exact=True).input_value() == "", "finance_history_date_filter_present")
        activate(drawer.get_by_role("button", name="开始查询", exact=True))
        self.wait_until(lambda: drawer.locator(".ant-pagination-total-text").count() == 1,
                        "finance_history_total_unproven")
        total_text = drawer.locator(".ant-pagination-total-text").inner_text()
        match = re.fullmatch(r"共计\s*(\d+)\s*条", total_text.strip())
        require(match is not None, "finance_history_total_invalid")
        total = int(match[1])
        require(total <= 5000, "finance_history_limit")
        require(drawer.locator("table.vxe-table--header th").all_text_contents() == HISTORY_HEADERS,
                "finance_history_schema_changed")
        pages = []
        for number in range(1, max(1, (total + 9) // 10) + 1):
            self.wait_until(lambda: drawer.locator(".ant-pagination-item-active").inner_text().strip() == str(number),
                            "finance_history_page_not_stable")
            table_rows = drawer.locator("table.vxe-table--body tbody tr")
            self.wait_until(lambda: table_rows.count() == min(10, max(0, total - (number - 1) * 10)),
                            "finance_history_rows_not_stable")
            result = []
            for position in range(table_rows.count()):
                line = table_rows.nth(position)
                expand = line.locator(".consume-expanded")
                if expand.count() == 1:
                    activate(expand)
                value = line.evaluate("""r=>{const td=r.querySelectorAll('td');return {
                  bill_no:td[0].innerText,time:td[1].innerText,payment:td[3].innerText,shop:td[4].innerText,
                  items:[...td[2].querySelectorAll('.consume-info-item')].filter(e=>e.getClientRects().length).map(e=>({
                    type:e.querySelector('.service-type')?.innerText,name:e.querySelector('.service-name')?.innerText,
                    quantity:e.querySelector('.consume-info-item-center')?.innerText,
                    settled:e.querySelector('.selling-price')?.innerText,original:e.querySelector('.original-price')?.innerText}))}}""")
                require(value["shop"] == SHOP, "finance_bill_store_conflict")
                value["detail"] = self.bill_detail(line, value["bill_no"])
                result.append(value)
            last = "ant-pagination-disabled" in drawer.locator(".ant-pagination-next").get_attribute("class")
            pages.append({"number": number, "rows": result, "last": last})
            require(drawer.locator(".ant-pagination-total-text").inner_text() == total_text, "finance_history_total_changed")
            if number < max(1, (total + 9) // 10):
                require(not last, "finance_history_ended_early")
                previous = table_rows.locator(".bill-no").all_text_contents()
                activate(drawer.locator(".ant-pagination-next button"))
                self.wait_until(lambda: table_rows.locator(".bill-no").all_text_contents() != previous and
                                drawer.locator(".vxe-loading:visible,.ant-spin-spinning:visible").count() == 0,
                                "finance_history_page_data_not_changed")
        check_pages(pages, total, 10)
        return {"total": total, "pages": pages, "observed_at": utc(),
                "query_range": None, "coverage_complete": False,
                "coverage_gaps": ["unbounded_source_date_range", "refund_evidence_pending", "source_current_version_pending"]}

    def collect_financial(self):
        f = self.frame()
        activate(f.get_by_role("button", name="查询", exact=True))
        self.page.wait_for_timeout(1500)
        self.wait_until(lambda: f.locator(".el-loading-mask:visible").count() == 0, "finance_card_query_loading")
        if f.locator(".el-pager .active").inner_text().strip() != "1":
            activate(f.locator(".el-pager li.number").filter(has_text=re.compile("^1$")))
        rows = self.wait_page(f, 1)
        total = self.total(f)
        require(0 < total <= 10000, "finance_card_total_invalid")
        result = {"schema": "source-member-finance-observation@1", "scope": SCOPE, "started_at": utc(),
                  "status": "collecting", "business_writes": 0, "cards": [], "histories": {}, "card_pages": []}
        seen = set()
        for number in range(1, (total + 14) // 15 + 1):
            self.frame()
            require(self.total(f) == total, "finance_card_total_changed")
            for position, row in enumerate(rows):
                require(row["store_name"] == SHOP and row["allow_cross_store_text"] == "否" and not row["state_text"],
                        "finance_card_scope_conflict")
                require(row["card_name"] in CARD_NAMES, "finance_card_type_unsupported")
                key = source_key(row["card_number"])
                require(key not in seen, "finance_duplicate_card")
                balance, history = self.member(f, position, row, lambda phone: phone not in result["histories"])
                seen.add(key)
                result["cards"].append(balance)
                if history is not None:
                    result["histories"][balance["phone"]] = history
                self.checkpoint(result)
            require(self.read_rows(f) == rows, "finance_card_page_changed")
            next_button = f.locator(".el-pagination .btn-next")
            last = next_button.is_disabled()
            result["card_pages"].append({"number": number, "rows": [row["card_number"] for row in rows], "last": last})
            if number < (total + 14) // 15:
                require(not last, "finance_card_pages_incomplete")
                previous = rows[0]["card_number"]
                activate(next_button)
                rows = self.wait_page(f, number + 1, previous)
        check_pages(result["card_pages"], total, 15)
        result.update(status="collected_unverified", observed_at=utc(), total_cards=total)
        self.checkpoint(result)
        return result
