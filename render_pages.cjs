// Render JavaScript-only docs pages with headless Chromium.
// Usage: node render_pages.cjs <queue.json> <out.json>
// queue.json: [{ "id": "R001", "url": "https://..." }, ...]
// out.json:   { "R001": { "status": 200, "title": "...", "text": "...", "method": "playwright" }, ... }
const fs = require('fs');
const { chromium } = require('playwright');

const input = process.argv[2];
const output = process.argv[3];
const items = JSON.parse(fs.readFileSync(input, 'utf8'));

(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.PLAYWRIGHT_EXECUTABLE_PATH || undefined,
  });
  const out = {};
  let cursor = 0;
  async function worker() {
    while (cursor < items.length) {
      const item = items[cursor];
      cursor += 1;
      const page = await browser.newPage({
        userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36',
      });
      try {
        const response = await page.goto(item.url, { waitUntil: 'domcontentloaded', timeout: 45000 });
        await page.waitForTimeout(1800);
        out[item.id] = {
          status: response ? response.status() : null,
          title: await page.title(),
          text: await page.locator('body').innerText(),
          final_url: page.url(),
          method: 'playwright',
        };
      } catch (error) {
        out[item.id] = { error: String(error).slice(0, 200), method: 'playwright' };
      } finally {
        await page.close();
      }
    }
  }
  await Promise.all(Array.from({ length: 4 }, worker));
  await browser.close();
  fs.writeFileSync(output, JSON.stringify(out, null, 2));
})().catch((error) => { console.error(error); process.exit(1); });
