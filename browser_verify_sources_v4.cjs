const fs = require('fs');
const { chromium } = require('playwright');

const input = process.argv[2] || 'source_quote_review_needed_final_v4.json';
const output = process.argv[3] || 'data/browser_source_checks_v4.json';
const queue = JSON.parse(fs.readFileSync(input, 'utf8')).results;

function normalize(text) {
  return String(text || '')
    .normalize('NFKC')
    .replace(/[’‘]/g, "'")
    .replace(/[“”]/g, '"')
    .replace(/[–—]/g, '-')
    .replace(/\u2011/g, '-')
    .replace(/!?\[([^\]]+)\]\([^)]*\)/g, '$1')
    .replace(/\s+/g, ' ')
    .trim();
}

function tokens(text) {
  return (normalize(text).toLowerCase().match(/[\p{L}\p{N}]+/gu) || []);
}

function containsTokens(pageTokens, quoteTokens) {
  if (!quoteTokens.length || quoteTokens.length > pageTokens.length) return false;
  outer: for (let i = 0; i <= pageTokens.length - quoteTokens.length; i += 1) {
    for (let j = 0; j < quoteTokens.length; j += 1) {
      if (pageTokens[i + j] !== quoteTokens[j]) continue outer;
    }
    return true;
  }
  return false;
}

async function verify(browser, item) {
  const page = await browser.newPage({ userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36' });
  const result = { url: item.url, uses: [] };
  try {
    const response = await page.goto(item.url, { waitUntil: 'domcontentloaded', timeout: 45000 });
    await page.waitForTimeout(1800);
    result.status = response ? response.status() : null;
    result.final_url = page.url();
    result.title = await page.title();
    const text = normalize(await page.locator('body').innerText());
    const pageTokens = tokens(text);
    for (const use of item.uses) {
      const quote = normalize(use.quote);
      const quoteTokens = tokens(quote);
      const exact = Boolean(quote && text.includes(quote));
      const tokenExact = containsTokens(pageTokens, quoteTokens);
      const first = quoteTokens.slice(0, 6).join(' ');
      const index = first ? text.toLowerCase().indexOf(first) : -1;
      result.uses.push({ ...use, quote_exact: exact, quote_token_exact: tokenExact,
        excerpt: index >= 0 ? text.slice(Math.max(0, index - 120), index + Math.max(500, quote.length + 120)) : '' });
    }
  } catch (error) {
    result.error = String(error);
    result.uses = item.uses.map(use => ({ ...use, quote_exact: false, quote_token_exact: false }));
  } finally {
    await page.close();
  }
  return result;
}

(async () => {
  const executablePath = [
    'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
  ].find(path => fs.existsSync(path));
  const browser = await chromium.launch({ headless: true, executablePath });
  const results = [];
  let cursor = 0;
  async function worker() {
    while (cursor < queue.length) {
      const item = queue[cursor];
      cursor += 1;
      const result = await verify(browser, item);
      results.push(result);
      const matched = result.uses.filter(use => use.quote_exact || use.quote_token_exact).length;
      console.log(`${matched}/${result.uses.length} ${result.status || 'error'} ${item.url}`);
    }
  }
  await Promise.all(Array.from({ length: 4 }, worker));
  await browser.close();
  results.sort((a, b) => queue.findIndex(item => item.url === a.url) - queue.findIndex(item => item.url === b.url));
  fs.writeFileSync(output, JSON.stringify({ checked_at: '2026-11-24', method: 'Headless Chromium rendered body innerText; no raw HTML or credentials.', results }, null, 2));
  const uses = results.flatMap(result => result.uses);
  const matched = uses.filter(use => use.quote_exact || use.quote_token_exact).length;
  console.log(`Matched ${matched}/${uses.length} uses across ${results.length} URLs`);
})().catch(error => { console.error(error); process.exit(1); });
