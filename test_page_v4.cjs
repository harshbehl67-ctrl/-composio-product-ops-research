const {chromium} = require('playwright');
const fs = require('fs');
const path = require('path');
const {pathToFileURL} = require('url');

const forbiddenKeys = new Set(['first_pass', 'provisional_pass12', 'composio_auth_config', 'raw_pass', 'pass12', 'pages', 'page_text', 'raw_text', 'response', 'search_response']);
function assertNoRawKeys(value, location = 'root') {
  if (Array.isArray(value)) return value.forEach((item, index) => assertNoRawKeys(item, `${location}[${index}]`));
  if (!value || typeof value !== 'object') return;
  for (const [key, item] of Object.entries(value)) {
    if (forbiddenKeys.has(key) || key.startsWith('raw_')) throw Error(`Raw research leaked at ${location}.${key}`);
    assertNoRawKeys(item, `${location}.${key}`);
  }
}
function parseCsv(text) {
  const rows = [];
  let row = [], field = '', quoted = false;
  for (let index = 0; index < text.length; index++) {
    const char = text[index];
    if (quoted) {
      if (char === '"' && text[index + 1] === '"') { field += '"'; index++; }
      else if (char === '"') quoted = false;
      else field += char;
    } else if (char === '"') quoted = true;
    else if (char === ',') { row.push(field); field = ''; }
    else if (char === '\n') { row.push(field); rows.push(row); row = []; field = ''; }
    else if (char !== '\r') field += char;
  }
  if (field || row.length) { row.push(field); rows.push(row); }
  return rows;
}

let browser;
(async () => {
  try {
    browser = await chromium.launch({executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH || undefined, headless: true});
    for (const width of [1440, 390]) {
    const page = await browser.newPage({viewport: {width, height: 900}, acceptDownloads: true});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(process.env.CASE_URL || pathToFileURL(path.resolve('index.html')).href);
    await page.locator('#rows tr').first().waitFor();
    const pageCopy = await page.locator('body').innerText();
    if (!pageCopy.includes('python run_pipeline.py --mode live --app "Google Ads"')) throw Error('Combined live pipeline command is missing');
    if (!pageCopy.includes('run_one.py only revalidates a saved checked record')) throw Error('run_one boundary is missing');
    if (pageCopy.includes('context-aware extraction → independent review')) throw Error('Unsupported independent-review claim remains');
    if (!pageCopy.includes('rows await a separate human decision')) throw Error('Pending gold adjudications are not disclosed');
    if (!pageCopy.includes('For the four judgment fields, answered / rows with gold_status="found"')) throw Error('Four-field scoreable rubric is missing from page');
    if (await page.locator('#rows tr').count() !== 100) throw Error('Wrong initial count');
    if (await page.locator('#rows .purpose').count() !== 100) throw Error('App purpose missing');
    if (await page.locator('#rows td p').count() !== 0) throw Error('Paragraph found in app table cell');
    const firstDataRow = await page.locator('#rows tr').first();
    if (await firstDataRow.locator('td .chip').count() < 2) throw Error('Normalized auth/MCP chips missing');
    if (!['Hosted actions', 'Docs / read-only', 'Local', 'Beta / EAP', 'Prelaunch', 'None documented', 'Unresolved'].includes(
      await firstDataRow.locator('td').nth(7).locator('.chip').first().innerText()
    )) throw Error('MCP tier is not normalized');
    const viewport = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, inner: window.innerWidth }));
    if (viewport.scroll > viewport.inner + 1) throw Error(`Page overflows horizontally at ${width}px`);
    await page.screenshot({path: `page-v4-top-${width}.png`, fullPage: false});
    await page.locator('#search').fill('Slack');
    const searchCount = await page.locator('#rows tr').count();
    if (searchCount === 0 || searchCount === 100) throw Error('Search failed');
    const searchRows = await page.locator('#rows tr').allInnerTexts();
    if (!searchRows.every(text => text.toLowerCase().includes('slack'))) throw Error('Search returned unrelated rows');
    await page.locator('#search').fill('');
    await page.locator('#search').fill('Google Ads');
    const googleRow = await page.locator('#rows tr').first();
    if (!(await googleRow.innerText()).includes('OAuth 2.0 service account') ||
        (await googleRow.innerText()).includes('OAuth 2.0 client credentials')) throw Error('Google Ads auth chip is mislabeled');
    if (!(await googleRow.locator('td').nth(7).innerText()).includes('Updated 2026-11-19')) throw Error('Google Ads MCP update date is missing');
    await page.locator('#search').fill('Binance');
    const binanceText = await page.locator('#rows tr').first().innerText();
    if (!binanceText.includes('signed request') || binanceText.includes('Signed JWT')) throw Error('Binance signature chip is mislabeled');
    await page.locator('#search').fill('Amazon Selling Partner');
    const amazonText = await page.locator('#rows tr').first().innerText();
    if (!amazonText.includes('OAuth 2.0') || amazonText.includes('Signed JWT')) throw Error('Amazon auth chip is mislabeled');
    await page.locator('#search').fill('');
    await page.locator('#category').selectOption({label: 'CRM and Sales'});
    if (await page.locator('#rows tr').count() !== 10) throw Error('Category filter failed');
    await page.locator('#category').selectOption('');
    if (await page.locator('#rows tr').count() !== 100) throw Error('Category reset failed');
    await page.locator('#prototype').selectOption('self_serve_free');
    const prototypeRows = await page.locator('#rows tr').count();
    if (prototypeRows === 0 || prototypeRows === 100 || !(await page.locator('#rows tr').allInnerTexts()).every(text => text.includes('Self-serve free'))) throw Error('Prototype filter failed');
    await page.locator('#prototype').selectOption('');
    await page.locator('#production').selectOption('app_review');
    const productionRows = await page.locator('#rows tr').count();
    if (productionRows === 0 || productionRows === 100 || !(await page.locator('#rows tr').allInnerTexts()).every(text => text.includes('App review'))) throw Error('Production filter failed');
    await page.locator('#production').selectOption('');
    await page.locator('#verdict').selectOption('partner_outreach');
    const verdictRows = await page.locator('#rows tr').count();
    if (verdictRows === 0 || verdictRows === 100 || !(await page.locator('#rows tr').allInnerTexts()).every(text => text.includes('Partner / sales outreach'))) throw Error('Verdict filter failed');
    await page.locator('#verdict').selectOption('');
    await page.locator('#mcp').selectOption('none');
    const mcpRows = await page.locator('#rows tr').count();
    if (mcpRows === 0 || mcpRows === 100 || !(await page.locator('#rows tr').allInnerTexts()).every(text => text.includes('None documented'))) throw Error('MCP filter failed');
    await page.locator('#mcp').selectOption('');
    await page.locator('#search').fill('zzzz-no-matching-app');
    if (await page.locator('#rows tr').count() !== 0 || !(await page.locator('#count').innerText()).startsWith('0 of 100')) throw Error('Empty search state failed');
    await page.locator('#search').fill('');
    const first = await page.locator('#rows tr').first().locator('td b').first().innerText();
    await page.locator('#sort').click();
    await page.waitForFunction(previous => document.querySelector('#rows tr td b')?.textContent !== previous, first, {timeout: 5000});
    if (first === await page.locator('#rows tr').first().locator('td b').first().innerText()) throw Error('Sort failed');
    await page.locator('#sort').click();
    await page.waitForFunction(previous => document.querySelector('#rows tr td b')?.textContent === previous, first, {timeout: 5000});
    await page.locator('#search').fill('Stripe');
    if (await page.locator('#rows tr').count() !== 1) throw Error('Export fixture filter failed');
    const [download] = await Promise.all([page.waitForEvent('download'), page.locator('#json').click()]);
    if (download.suggestedFilename() !== 'checked-dataset-v4.json') throw Error('JSON export failed');
    const exported = JSON.parse(fs.readFileSync(await download.path(), 'utf8'));
    if (exported.length !== 1 || exported[0].app !== 'Stripe') throw Error('JSON export did not honor the active filter');
    const requiredFields = ['auth', 'credential_gate', 'api_surface', 'official_mcp', 'composio_toolkit', 'verdict'];
    for (const item of exported) {
      if (!item.app || !item.category || !item.fields || requiredFields.some(field => !item.fields[field])) throw Error('JSON export schema failed');
      if (Object.keys(item.fields).some(field => !requiredFields.includes(field))) throw Error('JSON export has unexpected fields');
      if (!item.prototype_access || !item.production_access || !item.mcp_updated) throw Error('Access/MCP date fields missing');
      if (item.what_it_does.trim().split(/\s+/).length > 10) throw Error(`Purpose exceeds ten words: ${item.app}`);
    }
    assertNoRawKeys(exported, 'json');
    const [csv] = await Promise.all([page.waitForEvent('download'), page.locator('#csv').click()]);
    if (csv.suggestedFilename() !== 'checked-dataset-v4.csv') throw Error('CSV export failed');
    const csvRows = parseCsv(fs.readFileSync(await csv.path(), 'utf8'));
    if (csvRows.length !== 2 || csvRows[0].length !== 12 || csvRows.slice(1).some(row => row.length !== 12)) throw Error('CSV filtered export shape failed');
    if (csvRows.slice(1).map(row => row[0]).sort().join('\n') !== exported.map(item => item.app).sort().join('\n')) throw Error('CSV export apps differ from JSON');
    if (csvRows.slice(1).some(row => row.some(value => /^[=+\-@\t\r]/.test(value)))) throw Error('CSV export contains formula-shaped cells');
    await page.locator('#rows tr').first().locator('summary').focus();
    await page.keyboard.press('Enter');
    if (!(await page.locator('#rows tr').first().locator('details').evaluate(el => el.open))) throw Error('Keyboard details failed');
    const fieldLabels = await page.locator('#rows tr').first().locator('.rowdetails > .fielddetail').evaluateAll(nodes => nodes.slice(0, 6).map(node => node.querySelector('b')?.textContent));
    if (fieldLabels.length !== 6 || !fieldLabels.includes('Authentication:')) throw Error('Evidence does not expose six fields');
    if (await page.locator('#rows tr').first().locator('.quote').count() === 0) throw Error('Evidence quotations are not visible');
    const expandedViewport = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, inner: window.innerWidth }));
    if (expandedViewport.scroll > expandedViewport.inner + 1) throw Error(`Expanded evidence overflows horizontally at ${width}px`);
    await page.locator('#cohort').evaluate(element => { element.closest('details').open = true; });
    await page.locator('#cohort').selectOption({label: 'Random holdout'});
    if (await page.locator('#reviewrows tr').count() !== 60) throw Error('Review cohort filter failed');
    if (errors.length) throw Error(errors.join('\n'));
    await page.screenshot({path: `page-v4-${width}.png`, fullPage: false});
    console.log(`PASS ${width}px: 100 rows, prototype/production filters, purpose limit, empty search, sort, filtered JSON/CSV export, keyboard details, no horizontal overflow, 60 holdout reviews, no script errors`);
    await page.close();
  }
  } finally {
    if (browser) await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
