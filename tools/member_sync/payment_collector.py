"""Read only financial receipt fields and preserve unresolved refunds separately."""
import re
from datetime import datetime, timezone
from contracts import SHOP_MARKER, require
from financial_collector import advance_finance_page,wait_finance_page

HEADERS = ["收款交易号", "支付金额", "支付方式", "支付状态", "支付时间", "收款渠道", "收款账户", "交易模式", "关联流水", "支付备注", "退款人", "退款时间", "退款原因", "操作"]

def collect_payments(page, targets, checkpoint):
    wait_finance_page(page,1)
    require(page.get_by_text(SHOP_MARKER).filter(visible=True).count()==1,"payment_scope_unproven")
    require(page.locator('.ant-select-selection-item').all_text_contents()[:2]==["全部支付方式","全部支付状态"],"payment_filter_present")
    require(page.locator('table.vxe-table--header th').all_text_contents()==HEADERS,"payment_schema_changed")
    total_text=page.locator('.ant-pagination-total-text').inner_text()
    total=int(re.fullmatch(r"共计\s*(\d+)\s*条",total_text.strip())[1])
    result={"schema":"source-payment-observation@1","shop_id":1581453,"business_writes":0,
            "query_dates":page.locator('.range-input').evaluate_all("es=>es.map(e=>e.value)"),
            "source_total":total,"pages":[],"status":"collecting"}
    require(page.locator('.ant-pagination .ant-select-selection-item').inner_text()=="15 条/页","payment_size_changed")
    for number in range(1,max(1,(total+14)//15)+1):
        require(page.locator('.ant-pagination-item-active').inner_text().strip()==str(number),"payment_page_changed")
        require(page.locator('.ant-pagination-total-text').inner_text()==total_text,"payment_total_changed")
        rows=page.locator('table.vxe-table--body tbody tr')
        expected=min(15,max(0,total-(number-1)*15))
        require(rows.count()==expected,"payment_page_incomplete")
        facts=rows.evaluate_all("""(rs,targets)=>rs.flatMap(r=>{
          const c=r.querySelectorAll('td'); const association=c[8].innerText.trim();
          const status=c[3].innerText.trim();
          const matched=targets.some(b=>association===b || association.startsWith(b+'(')||association.startsWith(b+'（'));
          if(!matched && !status.includes('退款'))return [];
          return [{transaction:c[0].innerText.trim(),amount:c[1].innerText.trim(),method:c[2].innerText.trim(),
             status,time:c[4].innerText.trim(),association,refund_time:c[11].innerText.trim(),matched}];
        })""",list(targets))
        last='ant-pagination-disabled' in page.locator('.ant-pagination-next').get_attribute('class')
        require(last==(number==max(1,(total+14)//15)),"payment_last_page_unproven")
        result['pages'].append({'number':number,'source_rows':expected,'rows':facts,'last':last});checkpoint(result)
        if not last:
            advance_finance_page(page,number+1,"td:first-child")
            page.wait_for_timeout(200)
    result.update(status='collected_unverified',observed_at=datetime.now(timezone.utc).isoformat());checkpoint(result)
    return result
