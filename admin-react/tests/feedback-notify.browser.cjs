const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const origin = process.env.PREVIEW_ORIGIN || 'http://127.0.0.1:4220';
const out = process.env.EVIDENCE_DIR;
const report = {passed:false,cases:[],unexpectedRequests:[],pageErrors:[],productionWrites:0,synthetic:true};
(async()=>{
  await fs.mkdir(out,{recursive:true});
  const browser=await chromium.launch({channel:"chrome",headless:true,args:['--js-flags=--max-old-space-size=192','--disable-background-networking']});
  try {
    const context=await browser.newContext({viewport:{width:375,height:812},serviceWorkers:'block'});
    await context.route('**/*',route=>{
      const u=new URL(route.request().url());
      if(u.origin!==origin || u.pathname.startsWith('/api/')){report.unexpectedRequests.push(u.origin+u.pathname);return route.abort();}
      return route.continue();
    });
    const page=await context.newPage();
    page.setDefaultTimeout(20000);
    page.on('pageerror',e=>report.pageErrors.push(e.message));
    async function open(query=''){await page.goto(origin+'/technician/store?'+query);}
    await open('review=visit_feedback%3A7');
    await page.getByRole('dialog').waitFor();
    assert.equal(await page.getByRole('dialog').getByText('到店扫码评价',{exact:true}).count(),1);
    assert.equal(await page.locator('.manager-review-card').count(),2);
    report.cases.push('QR deep link opens correct review while same-ID service review remains distinct');
    await page.getByRole('textbox').fill('合成跟进：已核实并处理');
    await page.getByRole('button',{name:'保存跟进',exact:true}).evaluate(b=>{b.click();b.click();});
    await page.waitForFunction(()=>document.querySelector('.ant-drawer-footer button.ant-btn-primary')?.disabled===true);
    assert.equal(await page.evaluate(()=>window.reviewStats.saves),1,'Repeated click must save once');
    await page.getByRole('button',{name:'关闭详情',exact:true}).click();
    await page.getByRole('dialog').waitFor({state:'hidden'});
    await page.locator('.manager-review-card').filter({hasText:'合成扫码反馈'}).click();
    assert.equal(await page.getByRole('textbox').inputValue(),'合成跟进：已核实并处理');
    report.cases.push('Follow-up saves once and reads back without changing original feedback');
    await page.screenshot({path:path.join(out,'qr-review-followup.png')});
    await open('review=service_review%3A7');
    await page.getByRole('dialog').getByText('服务评价',{exact:true}).waitFor();
    assert.equal(await page.getByRole('textbox').inputValue(),'');
    report.cases.push('Service deep link does not open same-ID QR review');
    await open('review=visit_feedback%3A7&mode=save-failure');
    await page.getByRole('dialog').waitFor();
    await page.getByRole('textbox').fill('合成失败后保留输入');
    await page.getByRole('button',{name:'保存跟进',exact:true}).click();
    await page.getByText('跟进保存失败，请重试',{exact:true}).waitFor();
    assert.equal(await page.getByRole('textbox').inputValue(),'合成失败后保留输入');
    await page.getByRole('button',{name:'保存跟进',exact:true}).click();
    await page.getByText('跟进保存失败，请重试',{exact:true}).waitFor({state:'hidden'});
    assert.equal(await page.evaluate(()=>window.reviewStats.saves),2);
    report.cases.push('Save failure preserves draft and explicit retry succeeds');
    await open('review=visit_feedback%3A7&mode=forbidden');
    await page.getByText('评价链接已失效或无权查看，已返回评价列表。',{exact:true}).waitFor();
    assert.equal(await page.getByRole('dialog').count(),0);
    report.cases.push('Unavailable or forbidden deep link stays in scoped list');
    await page.getByRole('button',{name:'待处理',exact:true}).click();
    await page.getByText('低分评价待跟进',{exact:true}).waitFor();
    assert.equal(await page.locator('button.manager-review-task-row').count(),2);
    assert.ok(await page.evaluate(()=>window.reviewStats.listParams.some(p=>p.low_rating_only===true && !p.feedback_type)));
    report.cases.push('Low-rating tasks request both sources with server-side rating filter');
    assert.equal(await page.evaluate(()=>window.reviewStats.unexpected),0);
    assert.deepEqual(report.pageErrors,[]);
    assert.deepEqual(report.unexpectedRequests,[]);
    report.passed=true;
  } catch(error){report.error=String(error);process.exitCode=1;}
  finally {await browser.close();await fs.writeFile(path.join(out,'browser-result.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));}
})();
