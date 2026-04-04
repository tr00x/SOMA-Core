import { chromium } from 'playwright';

const BASE = 'http://127.0.0.1:7777';
const PASS = '\x1b[32mPASS\x1b[0m';
const FAIL = '\x1b[31mFAIL\x1b[0m';
let passed = 0, failed = 0;

function check(name, ok, detail) {
  if (ok) { console.log(`  ${PASS} ${name}`); passed++; }
  else { console.log(`  ${FAIL} ${name}${detail ? ' — ' + detail : ''}`); failed++; }
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', err => errors.push(err.message));

  await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 10000 });
  await page.waitForTimeout(3000);

  console.log('\n=== Tab-by-Tab Audit ===\n');

  // ============ OVERVIEW ============
  console.log('--- OVERVIEW ---');
  await page.locator('button >> text="Overview"').first().click();
  await page.waitForTimeout(2000);
  const ov = await page.locator('#tab-overview').textContent();

  // Status bar
  check('Status bar has pressure', ov.includes('P:') || ov.includes('%'));
  check('Status bar has mode', ov.includes('OBSERVE') || ov.includes('GUIDE') || ov.includes('WARN') || ov.includes('BLOCK'));
  check('Status bar has budget', ov.includes('Budget'));
  check('Status bar has agents count', ov.includes('Agents'));

  // Agent cards
  const agentCards = await page.locator('#tab-overview .soma-card, #tab-overview [class*="border-soma"]').count();
  check('Agent cards rendered', agentCards > 0, `found ${agentCards}`);

  // Pressure numbers visible
  const pressureNums = await page.locator('#tab-overview .num').count();
  check('Pressure numbers visible', pressureNums > 0, `found ${pressureNums}`);

  // Findings section
  check('Findings section exists', ov.includes('Findings') || ov.includes('findings') || ov.includes('all clear'));

  // Sidebar
  check('Budget section exists', ov.includes('Budget') || ov.includes('budget'));
  check('Top tools section exists', ov.includes('Top Tools') || ov.includes('Tools') || ov.includes('tool'));

  // Screenshot
  await page.screenshot({ path: '/tmp/audit-overview.png', fullPage: true });

  // ============ DEEP DIVE ============
  console.log('\n--- DEEP DIVE ---');
  // Click first agent to navigate
  const firstAgentBtn = page.locator('#tab-overview button[class*="soma-card"], #tab-overview [class*="cursor-pointer"]').first();
  if (await firstAgentBtn.count() > 0) {
    await firstAgentBtn.click();
    await page.waitForTimeout(2000);
  } else {
    await page.locator('button >> text="Deep Dive"').first().click();
    await page.waitForTimeout(2000);
  }
  const dd = await page.locator('#tab-deep-dive').textContent();
  check('Deep Dive has content', dd.length > 100, `${dd.length} chars`);
  check('Shows agent ID or select prompt', dd.includes('cc-') || dd.includes('Select an agent') || dd.includes('select'));

  // If agent selected, check sections
  if (dd.includes('cc-')) {
    check('Pressure section', dd.includes('%') || dd.includes('Pressure'));
    check('Vitals or radar', dd.includes('uncertainty') || dd.includes('drift') || dd.includes('Vitals') || dd.includes('Radar'));
    check('Calibration section', dd.includes('Calibration') || dd.includes('calibration'));
    check('Predictions section', dd.includes('Prediction') || dd.includes('prediction') || dd.includes('escalat'));
    check('Reflexes section', dd.includes('Reflex') || dd.includes('reflex'));
    check('RCA section', dd.includes('RCA') || dd.includes('Root Cause') || dd.includes('diagnosis'));
    check('Actions section', dd.includes('Actions') || dd.includes('action'));
  }
  await page.screenshot({ path: '/tmp/audit-deepdive.png', fullPage: true });

  // ============ SETTINGS ============
  console.log('\n--- SETTINGS ---');
  await page.locator('button >> text="Settings"').first().click();
  await page.waitForTimeout(2000);
  const st = await page.locator('#tab-settings').textContent();
  check('Settings has content', st.length > 50, `${st.length} chars`);

  // Mode selector
  check('Mode section', st.includes('Reflex') || st.includes('Advisory') || st.includes('Strict') || st.includes('mode'));

  // Sub-tabs
  const settingsBtns = await page.locator('#tab-settings button').allTextContents();
  const joined = settingsBtns.join(' ');
  check('Thresholds sub-tab', joined.includes('Thresholds') || st.includes('Threshold'));
  check('Weights sub-tab', joined.includes('Weights') || st.includes('Weight'));
  check('Budget sub-tab', joined.includes('Budget'));
  check('Hooks sub-tab', joined.includes('Hooks'));
  check('Raw TOML sub-tab', joined.includes('Raw') || joined.includes('TOML'));

  // Click Thresholds
  const threshBtn = page.locator('#tab-settings button:has-text("Thresholds")').first();
  if (await threshBtn.count() > 0) {
    await threshBtn.click();
    await page.waitForTimeout(500);
    const stAfter = await page.locator('#tab-settings').textContent();
    check('Thresholds shows sliders', stAfter.includes('Guide') || stAfter.includes('guide') || stAfter.includes('0.'));
  }
  await page.screenshot({ path: '/tmp/audit-settings.png', fullPage: true });

  // ============ LOGS ============
  console.log('\n--- LOGS ---');
  await page.locator('button >> text="Logs"').first().click();
  await page.waitForTimeout(2000);
  const logs = await page.locator('#tab-logs').textContent();
  check('Logs has content', logs.length > 100, `${logs.length} chars`);

  // Check table rendered
  const logRows = await page.locator('#tab-logs tr, #tab-logs [class*="h-9"]').count();
  check('Log rows rendered', logRows > 3, `found ${logRows} rows`);

  // Check data in rows
  check('Agent IDs in logs', logs.includes('cc-'));
  check('Tool names in logs', logs.includes('Read') || logs.includes('Edit') || logs.includes('Bash') || logs.includes('Write'));
  check('Pressure values in logs', logs.includes('%'));
  check('Mode badges in logs', logs.includes('OBSERVE') || logs.includes('GUIDE'));

  // Filters
  check('Agent filter dropdown', logs.includes('All agents') || logs.includes('agent'));
  check('Mode filter buttons', logs.includes('OBSERVE') && logs.includes('WARN') && logs.includes('BLOCK'));
  check('CSV export button', logs.includes('CSV'));

  await page.screenshot({ path: '/tmp/audit-logs.png', fullPage: true });

  // ============ SESSIONS ============
  console.log('\n--- SESSIONS ---');
  await page.locator('button >> text="Sessions"').first().click();
  await page.waitForTimeout(2000);
  const sess = await page.locator('#tab-sessions').textContent();
  check('Sessions has content', sess.length > 50, `${sess.length} chars`);
  check('Has session data or empty state', sess.includes('cc-') || sess.includes('No past sessions') || sess.includes('session'));

  await page.screenshot({ path: '/tmp/audit-sessions.png', fullPage: true });

  // ============ ANALYTICS ============
  console.log('\n--- ANALYTICS ---');
  await page.locator('button >> text="Analytics"').first().click();
  await page.waitForTimeout(2000);
  const ana = await page.locator('#tab-analytics').textContent();
  check('Analytics has content', ana.length > 50, `${ana.length} chars`);
  check('Has agent selector or data', ana.includes('agent') || ana.includes('cc-') || ana.includes('trend') || ana.includes('Not enough'));

  await page.screenshot({ path: '/tmp/audit-analytics.png', fullPage: true });

  // ============ JS ERRORS ============
  console.log('\n--- JS ERRORS ---');
  const critical = errors.filter(e => !e.includes('favicon') && !e.includes('SSE') && !e.includes('EventSource') && !e.includes('net::'));
  if (critical.length > 0) {
    console.log(`  ${critical.length} errors:`);
    [...new Set(critical)].slice(0, 8).forEach(e => console.log(`    ${FAIL} ${e.slice(0, 150)}`));
    failed += [...new Set(critical)].length;
  } else {
    check('No JS errors', true);
  }

  await browser.close();

  console.log(`\n${'='.repeat(50)}`);
  console.log(`  Results: ${passed} passed, ${failed} failed`);
  console.log(`  Screenshots: /tmp/audit-*.png`);
  console.log(`${'='.repeat(50)}\n`);

  process.exit(failed > 0 ? 1 : 0);
})();
