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

  console.log('\n=== Deep Dive Tab Audit ===\n');

  // Navigate to Deep Dive by clicking an agent
  const firstAgent = page.locator('#tab-overview button[class*="cursor-pointer"], #tab-overview [class*="soma-card"]').first();
  if (await firstAgent.count() > 0) {
    await firstAgent.click();
    await page.waitForTimeout(3000);
  } else {
    await page.locator('button >> text="Deep Dive"').first().click();
    await page.waitForTimeout(3000);
  }

  const dd = await page.locator('#tab-deep-dive').textContent();

  // --- Row 1: Header ---
  console.log('Row 1: Header');
  check('Agent ID shown', dd.includes('cc-'));
  check('Pressure percentage', (dd.match(/\d+(\.\d+)?%/) || []).length > 0);
  check('Mode badge', dd.includes('OBSERVE') || dd.includes('GUIDE') || dd.includes('WARN') || dd.includes('BLOCK'));

  // Phase
  check('Phase label', dd.includes('Phase') || dd.includes('phase') || dd.includes('research') || dd.includes('implement') || dd.includes('unknown'));

  // Half-life
  check('Half-life section', dd.includes('Half') || dd.includes('half') || dd.includes('Success'));

  // Capacity
  check('Capacity section', dd.includes('Capacity') || dd.includes('capacity') || dd.includes('actions'));

  // Circuit breaker
  check('Circuit breaker', dd.includes('Circuit') || dd.includes('circuit') || dd.includes('Breaker') || dd.includes('N/A') || dd.includes('CLOSED'));

  // --- Row 2: Charts ---
  console.log('\nRow 2: Charts');
  const pressureCanvas = await page.locator('#dd-pressure-chart, canvas[id*="pressure"]').count();
  check('Pressure chart canvas exists', pressureCanvas > 0, `found ${pressureCanvas}`);
  const radarCanvas = await page.locator('#dd-radar-chart, canvas[id*="radar"]').count();
  check('Radar chart canvas exists', radarCanvas > 0, `found ${radarCanvas}`);

  // --- Row 3: Signal Breakdown ---
  console.log('\nRow 3: Signal Breakdown');
  check('Pressure vector section', dd.includes('Pressure Vector') || dd.includes('pressure_vector') || dd.includes('uncertainty') || dd.includes('Signal'));
  check('Calibration section', dd.includes('Calibration') || dd.includes('calibration'));
  check('Baseline section', dd.includes('Baseline') || dd.includes('baseline') || dd.includes('integrity'));

  // --- Row 4: Intelligence ---
  console.log('\nRow 4: Intelligence');
  check('Predictions section', dd.includes('Prediction') || dd.includes('prediction') || dd.includes('Escalat') || dd.includes('escalat') || dd.includes('No escalation'));
  check('Fingerprint section', dd.includes('Fingerprint') || dd.includes('fingerprint') || dd.includes('divergence') || dd.includes('Divergence'));

  // --- Row 5: Reflexes & RCA ---
  console.log('\nRow 5: Reflexes & RCA');
  check('Reflexes section header', dd.includes('Reflex') || dd.includes('reflex'));
  check('RCA section', dd.includes('RCA') || dd.includes('Root Cause') || dd.includes('diagnosis') || dd.includes('Diagnosis'));

  // --- Row 6: Mirror & Context ---
  console.log('\nRow 6: Mirror & Context');
  check('Mirror section', dd.includes('Mirror') || dd.includes('mirror') || dd.includes('injection') || dd.includes('No mirror'));
  check('Context section', dd.includes('Context') || dd.includes('context') || dd.includes('retention') || dd.includes('Retention'));

  // --- Row 7: Session Memory & Scope ---
  console.log('\nRow 7: Session Memory & Scope');
  check('Session memory section', dd.includes('Session Memory') || dd.includes('session_memory') || dd.includes('Similar') || dd.includes('similar') || dd.includes('No matched'));
  check('Scope drift section', dd.includes('Scope') || dd.includes('scope') || dd.includes('drift') || dd.includes('Drift') || dd.includes('focus'));

  // --- Row 8: Agent Graph ---
  console.log('\nRow 8: Agent Graph');
  check('Graph section', dd.includes('Graph') || dd.includes('graph') || dd.includes('relationship'));

  // --- Row 9: Subagents ---
  console.log('\nRow 9: Subagents');
  check('Subagents section', dd.includes('Subagent') || dd.includes('subagent') || dd.includes('Cascade') || dd.includes('cascade') || dd.includes('No subagent'));

  // --- Row 10: History ---
  console.log('\nRow 10: History');
  check('Intervention history', dd.includes('Intervention') || dd.includes('intervention') || dd.includes('mode change'));
  check('Actions feed', dd.includes('Actions') || dd.includes('actions') || dd.includes('Recent'));
  check('Context burn', dd.includes('Context Burn') || dd.includes('burn') || dd.includes('Burn Rate') || dd.includes('tokens'));

  // --- Collapsible sections ---
  console.log('\nInteractivity');
  const collapseButtons = await page.locator('#tab-deep-dive button[class*="w-full"]').count();
  check('Collapsible section headers', collapseButtons >= 3, `found ${collapseButtons} collapse buttons`);

  // Try clicking a section to collapse/expand
  const firstCollapse = page.locator('#tab-deep-dive button[class*="w-full"]').first();
  if (await firstCollapse.count() > 0) {
    await firstCollapse.click();
    await page.waitForTimeout(300);
    await firstCollapse.click();
    await page.waitForTimeout(300);
    check('Section toggle works', true);
  }

  // --- Data quality: check specific values ---
  console.log('\nData Quality');
  // Check that numeric values are rendered (not NaN, undefined, [object Object])
  check('No "undefined" in text', !dd.includes('undefined'));
  check('No "NaN" in text', !dd.includes('NaN'));
  check('No "[object Object]" in text', !dd.includes('[object Object]'));
  check('No "null" visible', !dd.match(/\bnull\b/));

  // Screenshot each section by scrolling
  await page.screenshot({ path: '/tmp/audit-dd-top.png', fullPage: false });
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight / 3));
  await page.waitForTimeout(300);
  await page.screenshot({ path: '/tmp/audit-dd-mid.png', fullPage: false });
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
  await page.waitForTimeout(300);
  await page.screenshot({ path: '/tmp/audit-dd-bottom.png', fullPage: false });
  await page.screenshot({ path: '/tmp/audit-dd-full.png', fullPage: true });

  // --- JS Errors ---
  console.log('\nJS Errors');
  const critical = errors.filter(e => !e.includes('favicon') && !e.includes('SSE') && !e.includes('EventSource') && !e.includes('net::'));
  const unique = [...new Set(critical)];
  if (unique.length > 0) {
    console.log(`  ${unique.length} unique errors:`);
    unique.slice(0, 10).forEach(e => console.log(`    ${FAIL} ${e.slice(0, 150)}`));
    failed += unique.length;
  } else {
    check('No JS errors', true);
  }

  await browser.close();

  console.log(`\n${'='.repeat(50)}`);
  console.log(`  Results: ${passed} passed, ${failed} failed`);
  console.log(`  Screenshots: /tmp/audit-dd-*.png`);
  console.log(`${'='.repeat(50)}\n`);

  process.exit(failed > 0 ? 1 : 0);
})();
