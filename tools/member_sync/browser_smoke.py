"""Isolated DOM integration check. Every network request is fulfilled or rejected locally."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collector import Collector, HOST
from contracts import SCOPE, source_key, verify, Stop
from playwright.sync_api import sync_playwright

TOP = """<html><body><span>荷小悦 (1581452)</span>
<iframe src="https://gray.aizhb.net/shair/components/customerRelation/index.html#/card-search"></iframe>
</body></html>"""
FRAME = r"""<html><body>
<div class="shop-selector-input">紫薇壹号店 </div>
<div hidden><label class="dialog-selector__item"><input type="checkbox" value="1582031">
<div class="shop-selector__item">华富世家店</div></label>
<label class="dialog-selector__item"><input type="checkbox" value="1581453" checked>
<div class="shop-selector__item">紫薇壹号店</div></label></div>
<input placeholder="请输入顾客姓名或手机号或卡号进行搜索" value="">
<button onclick="render(1)">查询</button>
<dl class="table_tips_item"><dt>总卡数</dt><dd class="table_tips_item-value">16</dd></dl>
<div class="el-table__header-wrapper"><table class="el-table__header"><thead id="head"></thead></table></div>
<div class="el-table__body-wrapper"><table class="el-table__body"><tbody id="body"></tbody></table></div>
<div class="el-table__fixed"><div class="el-table__fixed-body-wrapper"><table><tbody id="fixed"></tbody></table></div></div>
<div class="el-pagination"><button class="btn-prev" onclick="render(1)">prev</button>
<ul class="el-pager"><li class="number active" onclick="render(1)">1</li>
<li class="number" onclick="render(2)">2</li></ul>
<button class="btn-next" onclick="render(2)">next</button>
<span class="el-pagination__sizes"><input value="15条/页"></span></div>
<div id="detail"></div><div id="phone"></div>
<script>
window.confirmWrites=0;
const headers=['','会员姓名','手机号','门店','卡号','卡名称','卡类型','卡内余额','开卡日期','到期日期','允许跨店消费','备注'];
document.querySelector('#head').innerHTML='<tr>'+headers.map(x=>'<th>'+x+'</th>').join('')+'</tr>';
function row(i) {
 const card = 'TEST'+String(i).padStart(4,'0');
 return ['', 'Test member','139****0000','紫薇壹号店',card,'荷小悦年度权益会员卡','储值消费卡','0.00','2026-11-01','2027-11-01','否',''];
}
function render(n){
 let items = n===1?Array.from({length:15},(_,i)=>i):[15];
 document.querySelector('#body').innerHTML=items.map(i=>'<tr>'+row(i).map(x=>'<td>'+x+'</td>').join('')+'</tr>').join('');
 document.querySelector('#fixed').innerHTML=items.map(i=>'<tr><td></td><td><a href="javascript:;" onclick="detail('+i+')">Test member</a></td></tr>').join('');
 document.querySelectorAll('.el-pager li').forEach((x,i)=>x.className='number'+(i+1===n?' active':''));
 document.querySelector('.btn-prev').disabled=n===1;
 document.querySelector('.btn-next').disabled=n===2;
}
function detail(i){
 const r=row(i);
 document.querySelector('#detail').innerHTML='<div class="ant-drawer"><button class="ant-drawer-close" onclick="document.querySelector(\'#detail\').innerHTML=\'\'">Close</button>'+
 '<div class="base-box-item"><div class="base-label">手机号：</div><div class="base-value">139****0000</div><button class="base-box-icon" onclick="phone()">Edit</button></div>'+
 '<div class="member-card-box-item-content"><div class="content-title">'+r[5]+'</div>'+
 '<div class="content-center-item">余额:<span>￥0.00</span></div>'+
 '<div class="content-body-info-item">卡号：<span class="is_edit">'+r[4]+'</span></div>'+
 '<div class="content-body-info-item">有效期至：<span class="is_edit">2027-11-01</span></div>'+
 '<div class="content-body-tips"><span>开卡于2026-11-01日</span></div></div></div>';
}
function phone(){
 document.querySelector('#phone').innerHTML='<div role="dialog" class="ant-modal-wrap">修改会员手机号<input placeholder="请输入" value="13900000000">'+
 '<button onclick="document.querySelector(\'#phone\').innerHTML=\'\'">取 消</button><button onclick="window.confirmWrites++">确 定</button></div>';
}
render(1);
</script></body></html>"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--chromium", required=True)
    args = parser.parse_args()
    requested, rejected = [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=args.chromium, headless=True)
        context = browser.new_context()
        def route(request):
            url = request.request.url
            requested.append(url)
            if url == "https://" + HOST + "/shair/components/shair-web/base-system/index.html":
                request.fulfill(status=200, body=TOP, content_type="text/html; charset=utf-8")
            elif "/customerRelation/index.html" in url and url.startswith("https://" + HOST + "/"):
                request.fulfill(status=200, body=FRAME, content_type="text/html; charset=utf-8")
            else:
                rejected.append(url)
                request.abort()
        context.route("**/*", route)
        page = context.new_page()
        page.goto("https://" + HOST + "/shair/components/shair-web/base-system/index.html#/main/iframe?url=/shair/components/customerRelation/index.html%23/card-search")
        frame = page.frames[1]
        frame.wait_for_selector("#body tr")
        known = {source_key("TEST" + str(i).zfill(4)) for i in range(15)}
        collector = Collector(page, known)
        scans = collector.collect()
        index = {"scope": SCOPE, "observed_at_utc": datetime.now(timezone.utc).isoformat(),
                 "source_keys": sorted(known), "source_cards": 15, "business_writes": 0}
        result = verify(index, scans)
        assert result["source_cards"] == 16 and result["new_cards"] == 1
        assert frame.evaluate("window.confirmWrites") == 0
        assert frame.locator(".ant-modal-wrap:visible,.ant-drawer:visible").count() == 0
        assert len(scans) == 2 and all([len(p["rows"]) for p in s["pages"]] == [15,1] for s in scans)
        # A wrong tenant fails before another card is read.
        page.locator("span").first.evaluate("(el)=>el.textContent='Other tenant (1)'")
        try:
            collector.scan()
            raise AssertionError("wrong_tenant_not_blocked")
        except Stop as exc:
            assert str(exc) == "tenant_not_verified"
        context.close()
        browser.close()
    assert not rejected and len(requested) == 2
    print(json.dumps({"status":"synthetic_browser_passed", "two_passes":True,
                      "page_sizes":[15,1], "new_cards":1, "confirm_clicks":0,
                      "external_requests":0, "real_source_verified":False, "business_writes":0}))


if __name__ == "__main__":
    main()
