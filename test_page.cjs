const {chromium} = require('playwright');
const path = require('path');
const {pathToFileURL} = require('url');
(async () => {
  const browser = await chromium.launch({executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH || undefined, headless: true});
  for (const width of [1440, 390]) {
    const page = await browser.newPage({viewport: {width, height: 850}, acceptDownloads: true});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(pathToFileURL(path.resolve('index.html')).href);
    if (await page.locator('#rows tr').count() !== 100) throw Error('Wrong initial count');
    await page.locator('#search').fill('Slack');
    if (await page.locator('#rows tr').count() !== 1) throw Error('Search failed');
    await page.locator('#search').fill('');
    await page.locator('#category').selectOption({label: 'CRM and Sales'});
    if (await page.locator('#rows tr').count() !== 10) throw Error('Category filter failed');
    await page.locator('#category').selectOption('');
    const first = await page.locator('#rows tr').first().innerText();
    await page.locator('#sort').click();
    if (first === await page.locator('#rows tr').first().innerText()) throw Error('Sort failed');
    const [download] = await Promise.all([page.waitForEvent('download'), page.locator('#json').click()]);
    if (download.suggestedFilename() !== 'checked-dataset-v4.json') throw Error('Export failed');
    const [csv] = await Promise.all([page.waitForEvent('download'), page.locator('#csv').click()]);
    if (csv.suggestedFilename() !== 'checked-dataset-v4.csv') throw Error('CSV export failed');
    await page.locator('#search').focus();
    await page.keyboard.type('Slack');
    if (await page.locator('#rows tr').count() !== 1) throw Error('Keyboard search failed');
    await page.locator('#search').fill('');
    await page.locator('#rows tr').first().locator('summary').focus();
    await page.keyboard.press('Enter');
    if (!(await page.locator('#rows tr').first().locator('details').evaluate(el => el.open))) throw Error('Keyboard details failed');
    if (errors.length) throw Error(errors.join('\n'));
    await page.screenshot({path: `page-${width}.png`, fullPage: false});
    console.log(`PASS ${width}px: 100 rows, search, category, sort, JSON/CSV export, keyboard details, no script errors`);
    await page.close();
  }
  await browser.close();
})().catch(error => { console.error(error); process.exitCode = 1; });
