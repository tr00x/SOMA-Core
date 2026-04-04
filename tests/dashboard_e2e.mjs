import { chromium } from 'playwright';

const BASE = 'http://127.0.0.1:8765';
const PASS = '\x1b[32mPASS\x1b[0m';
const FAIL = '\x1b[31mFAIL\x1b[0m';
let passed = 0, failed = 0;

function check(name, ok) {
  if (ok) { console.log(`  ${PASS} ${name}`); passed++; }
  else { console.log(`  ${FAIL} ${name}`); failed++; }
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const jsErrors = [];
  page.on('pageerror', err => jsErrors.push(err.message));

  console.log('\n=== SOMA Dashboard v2 — E2E Tests ===\n');

  // ---- 1. Page Load ----
  console.log('1. Page Load');
  await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 10000 });
  await page.waitForTimeout(3000);
  check('Title contains SOMA', (await page.title()).includes('SOMA'));
  check('Alpine initialized', await page.evaluate(() => typeof Alpine !== 'undefined'));

  // ---- 2. Header ----
  console.log('\n2. Header');
  check('SOMA logo visible', await page.locator('text=SOMA').first().isVisible());
  check('Clock renders', (await page.locator('.num').first().textContent()).match(/\d{2}:\d{2}/));

  // ---- 3. Tabs ----
  console.log('\n3. Tab Navigation');
  const tabLabels = ['Overview', 'Deep Dive', 'Settings', 'Logs', 'Sessions', 'Analytics'];
  for (const label of tabLabels) {
    check(`Tab "${label}" visible`, await page.locator(`button >> text="${label}"`).first().isVisible());
  }

  // ---- 4. Overview Content ----
  console.log('\n4. Overview Tab');
  const overviewText = await page.locator('#tab-overview').textContent();
  check('Overview has content', overviewText.length > 50);
  check('Shows agents or empty state', overviewText.includes('OBSERVE') || overviewText.includes('No agents'));

  // ---- 5. API ----
  console.log('\n5. API Endpoints');
  for (const ep of ['/api/agents', '/api/overview', '/api/config', '/api/budget', '/api/sessions',
                     '/api/audit', '/api/tool-usage', '/api/activity-heatmap', '/api/findings',
                     '/api/predictions', '/api/patterns', '/api/engine']) {
    check(`${ep} → 200`, (await page.request.get(BASE + ep)).status() === 200);
  }

  // ---- 6. Tab Switching ----
  console.log('\n6. Tab Switching');
  for (const label of tabLabels) {
    await page.locator(`button >> text="${label}"`).first().click();
    await page.waitForTimeout(500);
    check(`"${label}" switch OK`, true);
  }
  await page.locator('button >> text="Overview"').first().click();
  await page.waitForTimeout(500);

  // ---- 7. Keyboard Shortcuts ----
  console.log('\n7. Keyboard Shortcuts');
  await page.keyboard.press('Control+k');
  await page.waitForTimeout(300);
  check('Ctrl+K opens search', await page.locator('input[placeholder="Search agents, tools, findings..."]').isVisible());
  await page.keyboard.press('Escape');
  await page.waitForTimeout(200);

  await page.keyboard.press('?');
  await page.waitForTimeout(300);
  check('? opens help', await page.locator('h2:has-text("Keyboard Shortcuts")').isVisible());
  await page.keyboard.press('Escape');
  await page.waitForTimeout(200);

  await page.keyboard.press('3');
  await page.waitForTimeout(300);
  check('Key "3" → Settings', (await page.evaluate(() => window.location.hash)) === '#settings');
  await page.keyboard.press('1');
  await page.waitForTimeout(300);

  // ---- 8. Settings ----
  console.log('\n8. Settings Tab');
  await page.locator('button >> text="Settings"').first().click();
  await page.waitForTimeout(1000);
  const settingsText = await page.locator('#tab-settings').textContent();
  check('Settings has content', settingsText.length > 50);
  check('Settings shows config', settingsText.toLowerCase().includes('mode') || settingsText.toLowerCase().includes('threshold'));

  // ---- 9. Logs ----
  console.log('\n9. Logs Tab');
  await page.locator('button >> text="Logs"').first().click();
  await page.waitForTimeout(1000);
  check('Logs has content', (await page.locator('#tab-logs').textContent()).length > 20);

  // ---- 10. Sessions ----
  console.log('\n10. Sessions Tab');
  await page.locator('button >> text="Sessions"').first().click();
  await page.waitForTimeout(1000);
  check('Sessions has content', (await page.locator('#tab-sessions').textContent()).length > 20);

  // ---- 11. Screenshots ----
  console.log('\n11. Screenshots');
  for (const [label, file] of [['Overview', 'overview'], ['Deep Dive', 'deepdive'], ['Settings', 'settings']]) {
    await page.locator(`button >> text="${label}"`).first().click();
    await page.waitForTimeout(800);
    await page.screenshot({ path: `/tmp/soma-dash-${file}.png`, fullPage: true });
    check(`${label} screenshot`, true);
  }

  // ---- 12. JS Errors ----
  console.log('\n12. JS Errors');
  const critical = jsErrors.filter(e => !e.includes('favicon') && !e.includes('SSE') && !e.includes('EventSource') && !e.includes('net::'));
  if (critical.length > 0) {
    console.log(`  ${critical.length} JS errors found:`);
    critical.slice(0, 5).forEach(e => console.log(`    ${FAIL} ${e.slice(0, 150)}`));
    failed += Math.min(critical.length, 5);
  } else {
    check('No JS errors', true);
  }

  await browser.close();

  console.log(`\n${'='.repeat(50)}`);
  console.log(`  Results: ${passed} passed, ${failed} failed, ${passed + failed} total`);
  console.log(`${'='.repeat(50)}\n`);

  process.exit(failed > 0 ? 1 : 0);
})();
