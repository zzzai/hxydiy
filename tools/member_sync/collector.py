"""Read only normal member-query UI; never use private APIs, cookies, storage or traces."""
from datetime import datetime, timezone
import re
import time
from urllib.parse import urlsplit
from contracts import SCOPE, SHOP, Stop, BAD_STATE, CARD_NAMES, require, source_key

HOST = "gray.aizhb.net"
CDP_ENDPOINT = "http://127.0.0.1:9333"
SEARCH = "请输入顾客姓名或手机号或卡号进行搜索"
FIELDS = {"手机号": "masked_phone", "门店": "store_name", "卡号": "card_number",
          "卡名称": "card_name", "卡类型": "source_card_type", "卡内余额": "balance_yuan",
          "开卡日期": "opened_at_date", "到期日期": "expires_at_date",
          "允许跨店消费": "allow_cross_store_text"}
BODY = ".el-table__body-wrapper table.el-table__body tbody tr"


class Collector:
    def __init__(self, page, known):
        self.page, self.known = page, known
        self.deadline = time.monotonic() + 1200

    def frame(self):
        require(time.monotonic() < self.deadline, "collection_deadline")
        require(urlsplit(self.page.url).hostname == HOST, "source_login_required")
        require(self.page.get_by_text(re.compile(r"荷小悦\s*[（(]1581452[)）]")).count() == 1,
                "tenant_not_verified")
        frames = [f for f in self.page.frames if urlsplit(f.url).hostname == HOST
                  and "/customerRelation/index.html" in f.url and "card-search" in f.url]
        require(len(frames) == 1, "query_page_required")
        f = frames[0]
        require(f.get_by_placeholder(SEARCH).input_value() == "", "search_filter_present")
        names = f.locator(".shop-selector__item").all_text_contents()
        require([s.strip() for s in names] == [SHOP], "shop_filter_not_verified")
        require(f.locator('input[type="checkbox"][value="1581453"]').is_checked(),
                "shop_id_not_verified")
        require(f.locator(".el-pagination__sizes input").input_value() == "15条/页",
                "page_size_changed")
        require(f.locator(".ant-drawer:visible,.ant-modal-wrap:visible").count() == 0,
                "unexpected_open_dialog")
        return f

    def unique_visible(self, selector):
        matches = []
        for f in self.page.frames:
            if urlsplit(f.url).hostname != HOST:
                continue
            for locator in f.locator(selector).all():
                if locator.is_visible():
                    matches.append(locator)
        require(len(matches) == 1, "detail_layout_changed")
        return matches[0]

    def wait_page(self, f, number, previous=None):
        end = time.monotonic() + 25
        while time.monotonic() < end:
            require(time.monotonic() < self.deadline, "collection_deadline")
            if (f.locator(".el-pager .active").inner_text().strip() == str(number)
                    and f.locator(".el-loading-mask:visible").count() == 0):
                rows = self.read_rows(f)
                if rows and (previous is None or rows[0]["card_number"] != previous):
                    return rows
            time.sleep(0.25)
        raise Stop("page_not_stable")

    def total(self, f):
        value = f.locator(".table_tips_item").filter(has_text="总卡数").locator(
            ".table_tips_item-value").inner_text().strip()
        require(re.fullmatch(r"\d+", value) is not None, "source_total_missing")
        return int(value)

    def read_rows(self, f):
        headers = [h.strip() for h in f.locator(
            ".el-table__header-wrapper table.el-table__header").first.locator("th").all_text_contents()]
        require(all(headers.count(name) == 1 for name in FIELDS), "table_schema_changed")
        indices = {key: headers.index(label) for label, key in FIELDS.items()}
        require(headers.count("备注") == 1, "source_state_column_missing")
        indices["state_text"] = headers.index("备注")
        # Read only the minimal needed cells, not names, birthdays, staff or consumption.
        result = f.locator(BODY).evaluate_all("""(rows, indices) => rows.map(row => {
          const cells = [...row.querySelectorAll('td')];
          return Object.fromEntries(Object.entries(indices).map(
            ([key, index]) => [key, cells[index]?.innerText ?? null]));
        })""", indices)
        for row in result:
            require(all(type(v) is str for v in row.values()), "table_cell_missing")
            row["state_text"] = "|".join(BAD_STATE.findall(row["state_text"]))
            for key in row.keys() - {"card_number"}:
                row[key] = row[key].strip()
        return result

    def detail(self, f, row_number, row):
        # The fixed-left customer link must be unique for this exact business-card row.
        fixed = f.locator(".el-table__fixed .el-table__fixed-body-wrapper tbody tr").nth(row_number)
        links = fixed.locator("td").nth(1).locator("a")
        require(links.count() == 1 and links.is_visible(), "customer_link_ambiguous")
        links.click()
        try:
            end = time.monotonic() + 25
            cards = []
            while time.monotonic() < end:
                cards = []
                for doc in self.page.frames:
                    if urlsplit(doc.url).hostname != HOST:
                        continue
                    for card in doc.locator(".member-card-box-item-content").all():
                        raw = card.locator(".content-body-info-item").filter(
                            has_text="卡号：").locator(".is_edit")
                        if card.is_visible() and raw.count() == 1 and raw.inner_text() == row["card_number"]:
                            cards.append(card)
                if len(cards) == 1:
                    break
                time.sleep(0.25)
            require(len(cards) == 1, "ownership_card_not_found")
            card = cards[0]
            title = card.locator(".content-title").inner_text().strip()
            expiry = card.locator(".content-body-info-item").filter(
                has_text="有效期至：").locator(".is_edit").inner_text().strip()
            opened_text = card.locator(".content-body-tips span").first.inner_text()
            opened = re.fullmatch(r"开卡于(\d{4}-\d{2}-\d{2})日", opened_text.strip())
            require(opened is not None, "detail_open_date_missing")
            balance_text = card.locator(".content-center-item").filter(
                has_text=re.compile(r"^余额:")).inner_text()
            balance = re.fullmatch(r"余额:\s*￥(\d+(?:\.\d{1,2})?)", balance_text.strip())
            require(balance is not None, "detail_balance_missing")
            state_text = "|".join(BAD_STATE.findall(card.inner_text()))
            label = self.unique_visible(".base-box-item:has(.base-label:text-is('手机号：'))")
            require(label.locator(".base-value").inner_text().strip() == row["masked_phone"],
                    "detail_masked_phone_mismatch")
            label.locator(".base-box-icon").click()
            modal = self.unique_visible('[role="dialog"]:has-text("修改会员手机号")')
            try:
                phone = modal.get_by_placeholder("请输入", exact=True).input_value()
            finally:
                # Never fill or click the confirmation button.
                modal.get_by_role("button", name="取 消", exact=True).click()
            return {"card_number": row["card_number"], "card_name": title, "store_name": SHOP,
                    "phone": phone, "opened_at_date": opened[1], "expiry_text": expiry,
                    "balance_yuan": balance[1], "state_text": state_text}
        finally:
            self.unique_visible(".ant-drawer-close").click()

    def scan(self):
        f = self.frame()
        f.get_by_role("button", name="查询", exact=True).click()
        self.page.wait_for_load_state("networkidle", timeout=15000)
        if f.locator(".el-pager .active").inner_text().strip() != "1":
            f.locator(".el-pager li.number").filter(has_text=re.compile("^1$")).click()
        rows = self.wait_page(f, 1)
        total = self.total(f)
        require(0 < total <= 10000, "invalid_source_total")
        pages, details = [], {}
        for number in range(1, (total + 14) // 15 + 1):
            self.frame()
            require(self.total(f) == total, "source_total_changed")
            for i, row in enumerate(rows):
                require(row["store_name"] == SHOP and row["allow_cross_store_text"] == "否",
                        "source_store_conflict")
                require(not BAD_STATE.search(row["state_text"]), "source_adverse_state")
                key = source_key(row["card_number"])
                if key not in self.known:
                    require(row["card_name"] in CARD_NAMES
                            and row["source_card_type"] == "储值消费卡", "unsupported_candidate_card")
                    details[key] = self.detail(f, i, row)
            def protection_view(items):
                return [r if source_key(r["card_number"]) not in self.known else
                        {key: r[key] for key in ("card_number", "store_name", "state_text",
                                                "allow_cross_store_text")} for r in items]
            require(protection_view(self.read_rows(f)) == protection_view(rows),
                    "page_changed_during_details")
            pages.append({"number": number, "total": total, "rows": rows})
            next_button = f.locator(".el-pagination .btn-next")
            if number == (total + 14) // 15:
                require(next_button.is_disabled(), "last_page_not_proven")
            else:
                require(next_button.is_enabled(), "pagination_ended_early")
                previous = rows[0]["card_number"]
                next_button.click()
                rows = self.wait_page(f, number + 1, previous)
        return {"scope": SCOPE, "shop_name": SHOP, "search_text": "", "total": total,
                "pages": pages, "details": details}

    def collect(self):
        return [self.scan(), self.scan()]


def collect(known):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        # A pre-authorized dedicated browser must already be running. No auto launch/login.
        try:
            browser = pw.chromium.connect_over_cdp(CDP_ENDPOINT, timeout=5000)
        except Exception:
            raise Stop("source_browser_unavailable") from None
        pages = [page for context in browser.contexts for page in context.pages]
        require(all(urlsplit(p.url).hostname == HOST or p.url == "about:blank"
                    for p in pages), "dedicated_browser_only")
        sources = [p for p in pages if urlsplit(p.url).hostname == HOST]
        require(len(sources) == 1, "single_source_tab_required")
        page = sources[0]
        page.set_default_timeout(15000)
        # The client disconnects on exit; never close Chrome or export browser state.
        return Collector(page, known).collect()
