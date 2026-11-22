"""Read matched bill evidence through the source virtual table and complete pages."""
import re
from datetime import datetime, timezone

from contracts import SHOP_MARKER, require, SHOP
from financial_collector import advance_finance_page,wait_finance_page

FIELDS = ["单号", "状态", "消费内容", "数量", "消费门店", "顾客门店", "原价", "优惠", "售价",
          "金额总计", "入账", "现金", "银联", "微信", "支付宝", "抖音团购", "美团点评", "商城订单",
          "卡金", "赠送金", "套餐卡金", "套餐赠金", "代金券", "优惠券", "积分", "免单", "下单时间", "结账时间", "撤单时间"]


def collect_ledger(page, target_bills, checkpoint):
    wait_finance_page(page,1)
    require(page.get_by_text(SHOP_MARKER).filter(visible=True).count() == 1, "ledger_store_unproven")
    require(page.get_by_placeholder("单号/手机号/卡号", exact=True).input_value() == "", "ledger_filter_present")
    require(page.locator('input[type=radio]:checked').evaluate_all("es=>es.map(e=>e.value)") == ["ALL"], "ledger_all_states_required")
    require(page.locator(".ant-pagination .ant-select-selection-item").inner_text() == "10 条/页", "ledger_page_size_changed")
    columns = page.locator("table.vxe-table--header th").evaluate_all("""(es,labels)=>Object.fromEntries(
      es.filter(e=>labels.includes(e.textContent.trim())).map(e=>[e.textContent.trim(),[...e.classList].find(c=>/^col_/.test(c))]))""", FIELDS)
    require(set(columns) == set(FIELDS), "ledger_schema_changed")
    total_text = page.locator(".ant-pagination-total-text").inner_text()
    total = int(re.fullmatch(r"共计\s*(\d+)\s*条", total_text.strip())[1])
    require(0 < total <= 100000, "ledger_total_invalid")
    result = {"schema":"source-ledger-observation@1", "store_name":SHOP, "shop_id":1581453,
              "query_dates":page.locator(".range-input").evaluate_all("es=>es.map(e=>e.value)"),
              "source_total":total, "page_size":10, "pages":[], "status":"collecting", "business_writes":0}
    scroller = page.locator(".vxe-table--scroll-y-handle")
    require(scroller.count() == 1, "ledger_scroll_ambiguous")
    for number in range(1, (total + 9)//10 + 1):
        require(page.locator(".ant-pagination-item-active").inner_text().strip() == str(number), "ledger_page_changed")
        require(page.locator(".ant-pagination-total-text").inner_text() == total_text, "ledger_total_changed")
        scroller.evaluate("e=>{e.scrollTop=0}")
        page.wait_for_timeout(250)
        seen, matches = set(), {}
        expected = min(10,total-(number-1)*10)
        for _ in range(1000):
            rows = page.locator("table.vxe-table--body").evaluate_all("""(tables,args)=>{
              let byRow=new Map();
              for (const table of tables) for (const row of table.querySelectorAll('tbody tr')) {
                const key=row.getAttribute('rowid'); if(!byRow.has(key))byRow.set(key,[]);
                byRow.get(key).push(row);
              }
              return [...byRow.entries()].map(([key,copies])=>{
                const bill=copies.map(r=>r.querySelector('td.'+args.columns['单号']))
                  .filter(Boolean).map(c=>(c.innerText||c.textContent||'').trim()).find(Boolean);
                if(!args.targets.includes(bill))return {key,data:null};
                const data={};
                for(const row of copies) for(const [label,column] of Object.entries(args.columns)) {
                  const cell=row.querySelector('td.'+column); if(!cell)continue;
                  const text=cell.innerText || cell.textContent || '';
                  if(text.trim() || !(label in data))data[label]=text.trim();
                }
                return {key,data};
              });
            }""", {"columns":columns, "targets":list(target_bills)})
            for row in rows:
                require(row["key"] is not None, "ledger_row_key_missing")
                seen.add(row["key"])
                if row["data"] is not None:
                    require(row["data"]["消费门店"] == SHOP, "ledger_bill_store_conflict")
                    if row["key"] in matches:
                        require(matches[row["key"]] == row["data"], "ledger_row_changed")
                    matches[row["key"]] = row["data"]
            if len(seen) == expected:
                break
            state = scroller.evaluate("e=>({top:e.scrollTop,height:e.clientHeight,total:e.scrollHeight})")
            if state["top"] + state["height"] >= state["total"] - 1:
                break
            scroller.evaluate("e=>{e.scrollTop+=Math.max(80,Math.floor(e.clientHeight/2))}")
            page.wait_for_timeout(70)
        expected = min(10,total-(number-1)*10)
        require(len(seen) == expected, "ledger_virtual_rows_incomplete")
        last = "ant-pagination-disabled" in page.locator(".ant-pagination-next").get_attribute("class")
        require(last == (number == (total+9)//10), "ledger_last_page_unproven")
        result["pages"].append({"number":number,"source_rows":len(seen),"rows":list(matches.values()),"last":last})
        checkpoint(result)
        if not last:
            advance_finance_page(page,number+1,"td."+columns["单号"])
            page.wait_for_timeout(150)
    result.update(status="collected_unverified",observed_at=datetime.now(timezone.utc).isoformat())
    checkpoint(result)
    return result
