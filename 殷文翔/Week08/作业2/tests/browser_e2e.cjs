/* Real browser acceptance. Run explicitly: this submits a paid research task. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const baseURL = process.env.E2E_BASE_URL || 'http://127.0.0.1:8000';
const output = path.resolve(__dirname, '../backend/data/verification');
const topic = '中小企业 RAG 知识库技术选型：向量检索与混合检索的适用场景及评测方法';
const existingID = process.argv[2];

async function main() {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.BROWSER_EXECUTABLE_PATH ? { executablePath: process.env.BROWSER_EXECUTABLE_PATH } : {}),
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1060 }, deviceScaleFactor: 1 });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(baseURL, { waitUntil: 'networkidle' });
    await page.getByText('每一份好研究，都始于好奇').waitFor();
    await page.screenshot({ path: path.join(output, 'desktop-empty.png'), fullPage: true });
    let researchID = existingID;
    if (!researchID) {
      await page.getByLabel('你想深入了解什么？', { exact: false }).fill(topic);
      const responsePromise = page.waitForResponse(response => response.url().endsWith('/api/research') && response.request().method() === 'POST');
      await page.getByRole('button', { name: '开始研究', exact: true }).click();
      const accepted = await responsePromise;
      assert.equal(accepted.status(), 202);
      const body = await accepted.json();
      assert.equal(body.status, 'pending');
      researchID = body.research_id;
      assert.match(researchID, /^[a-f0-9-]{36}$/);
    } else {
      await page.goto(`${baseURL}/?research=${encodeURIComponent(researchID)}`);
    }
    fs.writeFileSync(path.join(output, 'research-id.txt'), researchID);
    console.log(JSON.stringify({ submitted: true, research_id: researchID, topic }));
    const started = Date.now();
    let record;
    let previous = '';
    while (Date.now() - started < 25 * 60 * 1000) {
      const response = await page.request.get(`${baseURL}/api/research/${researchID}`);
      assert.equal(response.status(), 200);
      record = await response.json();
      const progress = JSON.stringify({ status: record.status, rounds: record.process?.iterations || 0, sources: record.sources.length, draft: record.draft.length, steps: record.process?.steps.length || 0 });
      if (progress !== previous) { console.log(progress); previous = progress; }
      if (record.status === 'completed') break;
      if (record.status === 'failed') throw new Error(`Research failed: ${record.error}`);
      await new Promise(resolve => setTimeout(resolve, 2000));
    }
    assert.equal(record.status, 'completed', 'Research must finish within 25 minutes');
    assert.equal(record.error, null);
    assert.ok(record.report.title && record.report.summary && record.report.sections.length);
    assert.ok(record.report.key_conclusions.length);
    assert.ok(record.report_html.includes('<html'));
    assert.ok(record.sources.length > 0, 'Bocha must return real sources');
    assert.ok(record.process.steps.some(step => step.type === 'judge'));
    assert.ok(record.process.search_queries.length > 0);
    assert.ok(record.confidence.overall && record.confidence.info_cutoff && record.confidence.notes.length);
    assert.deepEqual(record.report.sections.map(section => section.body), record.draft.map(block => block.text));
    const sourceURLs = new Set(record.sources.map(source => source.url));
    for (const conclusion of record.report.key_conclusions) {
      if (!conclusion.sources.length) assert.equal(conclusion.is_model_inference, true);
      for (const source of conclusion.sources) assert.ok(sourceURLs.has(source.url));
    }
    assert.deepEqual(record.process.reviewed_urls, record.sources.map(source => source.url));
    const disk = JSON.parse(fs.readFileSync(path.resolve(__dirname, `../backend/data/research/${researchID}.json`), 'utf8'));
    assert.deepEqual(disk, record);
    await page.locator('#status').filter({ hasText: '研究已完成' }).waitFor({ timeout: 15000 });
    assert.equal(await page.locator('#source-count').innerText(), String(record.sources.length));
    assert.equal(await page.locator('#round-count').innerText(), String(record.process.iterations));
    for (const [tab, file] of [['研究报告', 'report'], ['参考来源', 'sources'], ['研究过程', 'process'], ['置信度', 'confidence']]) {
      await page.getByRole('tab', { name: tab, exact: false }).click();
      const text = await page.locator('#panel').innerText();
      if (file === 'report') assert.ok(text.includes(record.report.summary));
      if (file === 'sources') assert.equal(await page.locator('.source-card').count(), record.sources.length);
      if (file === 'process') assert.equal(await page.locator('.step').count(), record.process.steps.length);
      if (file === 'confidence') assert.ok(text.includes(record.confidence.info_cutoff));
      await page.screenshot({ path: path.join(output, `desktop-${file}.png`), fullPage: true });
    }
    await page.getByRole('tab', { name: '研究报告', exact: true }).click();
    await page.getByRole('button', { name: '查看排版预览' }).click();
    const frame = page.frameLocator('iframe');
    await frame.locator('body').waitFor();
    assert.equal(await page.locator('iframe').getAttribute('sandbox'), '');
    assert.ok((await frame.locator('body').innerText()).includes(record.report.title));
    await page.getByRole('button', { name: '收起排版预览' }).click();
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: '导出 Markdown 报告' }).click();
    const download = await downloadPromise;
    await download.saveAs(path.join(output, 'research-report.md'));
    assert.ok(fs.readFileSync(path.join(output, 'research-report.md'), 'utf8').includes(record.report.title));
    await page.reload({ waitUntil: 'networkidle' });
    await page.locator('#status').filter({ hasText: '研究已完成' }).waitFor();
    assert.equal(new URL(page.url()).searchParams.get('research'), researchID);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: path.join(output, 'mobile-report.png'), fullPage: true });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), 'Mobile must not overflow horizontally');
    await page.getByRole('button', { name: '打开研究记录' }).click();
    assert.equal(await page.locator('#menu-toggle').getAttribute('aria-expanded'), 'true');
    await page.locator('.history-button.active').click();
    await page.locator('#status').filter({ hasText: '研究已完成' }).waitFor();
    assert.equal(await page.locator('#menu-toggle').getAttribute('aria-expanded'), 'false');
    assert.deepEqual(errors, []);
    const summary = {
      research_id: researchID, topic: record.topic, status: record.status,
      sources: record.sources.length, iterations: record.process.iterations,
      sections: record.report.sections.length, conclusions: record.report.key_conclusions.length,
      inference_conclusions: record.report.key_conclusions.filter(c => c.is_model_inference).length,
      confidence: record.confidence.overall, info_cutoff: record.confidence.info_cutoff,
      created_at: record.created_at, completed_at: record.updated_at,
      browser_errors: errors, checks: ['HTTP 202 + id', 'poll to completed', 'JSON equals API', 'four artifact tabs', 'traceable conclusions', 'HTML sandbox preview', 'Markdown export', 'reload restores task', 'mobile layout and history'],
    };
    fs.writeFileSync(path.join(output, 'acceptance.json'), JSON.stringify(summary, null, 2));
    console.log(JSON.stringify({ acceptance: 'passed', ...summary }));
  } finally {
    await browser.close();
  }
}

main().catch(error => { console.error(error.message); process.exitCode = 1; });
