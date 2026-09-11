/* Browser regression checks with intercepted APIs; no external API calls. */
const assert = require('node:assert/strict');
const { chromium } = require('playwright');

async function main() {
  const browser = await chromium.launch({ headless: true,
    ...(process.env.BROWSER_EXECUTABLE_PATH ? { executablePath: process.env.BROWSER_EXECUTABLE_PATH } : {}),
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    const timestamp = new Date().toISOString();
    const unsafeText = '<img src=x onerror="window.__unsafe=true">';
    const draft = [{ round: 1, keyword: '测试检索', text: '已保存的阶段性草稿' }];
    const sources = [{ url: 'javascript:window.__unsafe=true', title: unsafeText, snippet: unsafeText, accessed_at: '2026-09-08', site_name: '测试资料' }];
    const processRecord = { plan: ['测试检索'], search_queries: ['测试检索'], reviewed_urls: [sources[0].url], iterations: 1, steps: [{ type: 'plan', round: 0, detail: { keywords: ['测试检索'] } }] };
    const base = { research_id: 'ui-test', topic: '浏览器测试', status: 'running', created_at: timestamp, updated_at: timestamp, report: null, report_html: '', sources, draft, process: processRecord, confidence: null, error: null };
    const completed = { ...base, research_id: 'ui-completed', topic: '已完成的测试', status: 'completed', report: { title: unsafeText, summary: '验证文字按原样展示', sections: [{ heading: '正文', body: unsafeText, conclusions: [] }], key_conclusions: [{ text: '仅供测试的模型推断', sources: [], is_model_inference: true }], open_questions: [] }, report_html: '<!DOCTYPE html><html><body>安全预览<script>parent.__unsafe=true</script></body></html>', confidence: { overall: 'low', info_cutoff: '2026-09-08', notes: ['测试置信度说明'] } };
    let records = [];
    let posts = 0;
    let failNext = false;
    let releaseSlow;
    let slowRequested;
    const slowStarted = new Promise(resolve => { slowRequested = resolve; });
    const slowGate = new Promise(resolve => { releaseSlow = resolve; });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/api/research**', async route => {
      const request = route.request();
      const url = new URL(request.url());
      if (request.method() === 'POST') {
        posts++;
        records = [{ ...base }];
        return route.fulfill({ status: 202, json: { research_id: base.research_id, status: 'pending' } });
      }
      if (url.pathname === '/api/research') return route.fulfill({ json: records });
      if (failNext) { failNext = false; return route.abort('failed'); }
      const id = url.pathname.split('/').pop();
      if (id === 'ui-slow') { slowRequested(); await slowGate; }
      const record = records.find(item => item.research_id === id);
      return route.fulfill(record ? { json: record } : { status: 404, json: { detail: '研究记录不存在。' } });
    });
    await page.goto(process.env.E2E_BASE_URL || 'http://127.0.0.1:8000', { waitUntil: 'networkidle' });
    await page.locator('#topic').fill('   ');
    await page.getByRole('button', { name: '开始研究', exact: true }).click();
    assert.equal(posts, 0);
    assert.equal(await page.locator('#topic').evaluate(element => element.checkValidity()), false);
    await page.locator('#topic').fill('浏览器测试');
    await page.getByRole('button', { name: '开始研究', exact: true }).click();
    await page.locator('#status').filter({ hasText: '研究进行中' }).waitFor();
    assert.equal(posts, 1);
    assert.ok((await page.locator('#panel').innerText()).includes(draft[0].text));
    records[0] = { ...records[0], status: 'failed', error: '测试服务暂不可用' };
    await page.locator('#status').filter({ hasText: '研究未完成' }).waitFor({ timeout: 10000 });
    assert.ok((await page.locator('#notice').innerText()).includes('测试服务暂不可用'));
    assert.ok((await page.locator('#panel').innerText()).includes(draft[0].text));
    await page.getByRole('tab', { name: '参考来源', exact: false }).click();
    assert.equal(await page.locator('#panel img, #panel script, #panel a[href^="javascript:"]').count(), 0);
    assert.ok((await page.locator('#panel').innerText()).includes(unsafeText));
    const slow = { ...base, research_id: 'ui-slow', topic: '延迟响应测试' };
    records = [completed, slow];
    await page.getByRole('button', { name: '开启新研究', exact: false }).click();
    await page.getByRole('button', { name: '已完成的测试，研究已完成', exact: true }).waitFor();
    await page.getByRole('button', { name: '延迟响应测试，研究进行中', exact: true }).click();
    await slowStarted;
    await page.getByRole('button', { name: '已完成的测试，研究已完成', exact: true }).click();
    await page.locator('#status').filter({ hasText: '研究已完成' }).waitFor();
    releaseSlow();
    await page.waitForLoadState('networkidle');
    assert.equal(new URL(page.url()).searchParams.get('research'), completed.research_id);
    assert.equal(await page.locator('#status').innerText(), '研究已完成');
    assert.ok((await page.locator('#panel').innerText()).includes('模型推断'));
    assert.equal(await page.locator('#panel img, #panel script').count(), 0);
    await page.getByRole('button', { name: '查看排版预览' }).click();
    await page.frameLocator('iframe').getByText('安全预览').waitFor();
    assert.equal(await page.evaluate(() => window.__unsafe), undefined);
    await page.getByRole('button', { name: '收起排版预览' }).click();
    failNext = true;
    await page.getByRole('button', { name: '已完成的测试，研究已完成', exact: true }).click();
    await page.locator('#notice').filter({ hasText: '读取研究失败' }).waitFor();
    await page.getByRole('button', { name: '重试连接' }).click();
    await page.locator('#status').filter({ hasText: '研究已完成' }).waitFor();
    assert.equal(await page.locator('#notice').isVisible(), false);
    await page.getByRole('tab', { name: '研究报告', exact: true }).focus();
    await page.keyboard.press('End');
    assert.equal(await page.locator('#tab-confidence').getAttribute('aria-selected'), 'true');
    await page.setViewportSize({ width: 360, height: 780 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ passed: true, external_requests: 0, checks: ['whitespace validation', 'pending submission', 'running draft', 'failed preserves draft', 'unsafe text and URL', 'HTML sandbox', 'stale response isolation', 'network retry', 'keyboard tabs', '360px layout'] }));
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error.stack); process.exitCode = 1; });
