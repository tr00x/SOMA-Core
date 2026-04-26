/**
 * RoiPage — "Is SOMA worth it?" single-page answer.
 *
 * v2026.5.6 (P1.3): A/B validation verdict becomes the primary pattern
 * metric. Cards show status badge (collecting N/30 / validated /
 * refuted / inconclusive), mean Δp, and p-value up front; the legacy
 * helped% stays available under an expand toggle so returning users
 * can still find the metric they remember. A reset banner at the top
 * warns when ~/.soma/ab_reset.log indicates the window is freshly
 * cleared and cards may still be thin.
 */

import { html } from 'htm/preact';
import { useEffect, useState, useRef } from 'preact/hooks';
import api from '../api.js';

const POLL_MS = 5000;

/** Big number with label */
function Metric({ value, label, sublabel, accent }) {
  const color = accent ? 'var(--accent)' : 'var(--text)';
  return html`
    <div class="roi-metric">
      <div class="roi-metric-value" style="color: ${color}">${value}</div>
      <div class="roi-metric-label">${label}</div>
      ${sublabel && html`<div class="roi-metric-sub">${sublabel}</div>`}
    </div>
  `;
}

/** Circular health gauge */
function HealthGauge({ score }) {
  const r = 54;
  const circ = 2 * Math.PI * r;
  const offset = circ - (score / 100) * circ;
  const color = score >= 80 ? 'var(--success)' : score >= 50 ? 'var(--warning)' : 'var(--error)';

  return html`
    <div class="roi-gauge">
      <svg viewBox="0 0 128 128" width="160" height="160">
        <circle cx="64" cy="64" r="${r}" fill="none" stroke="var(--surface)" stroke-width="10" />
        <circle cx="64" cy="64" r="${r}" fill="none" stroke="${color}" stroke-width="10"
          stroke-dasharray="${circ}" stroke-dashoffset="${offset}"
          stroke-linecap="round" transform="rotate(-90 64 64)"
          style="transition: stroke-dashoffset 0.6s ease" />
      </svg>
      <div class="roi-gauge-text">
        <span class="roi-gauge-number" style="color: ${color}">${score}</span>
        <span class="roi-gauge-label">health</span>
      </div>
    </div>
  `;
}

const _STATUS_META = {
  validated:    { color: 'var(--success)', label: 'validated' },
  refuted:      { color: 'var(--error)',   label: 'refuted' },
  inconclusive: { color: 'var(--warning)', label: 'inconclusive' },
  collecting:   { color: 'var(--muted, #888)', label: 'collecting' },
};

/** Render p-value with a sensible lower bound so "0.0000" doesn't lie. */
function _fmtP(p) {
  if (p === null || p === undefined) return '—';
  if (p < 0.0001) return '< 0.0001';
  return p.toFixed(4);
}

/** Signed Δp with 3 decimals and leading sign so sign is unmistakable. */
function _fmtDelta(d) {
  if (d === null || d === undefined) return '—';
  const sign = d > 0 ? '+' : d < 0 ? '' : '±';
  return `${sign}${d.toFixed(3)}`;
}

/** Single pattern card with expandable legacy-helped details. */
function PatternCard({ card }) {
  const [expanded, setExpanded] = useState(false);
  const status = _STATUS_META[card.status] || _STATUS_META.collecting;

  const progress =
    card.status === 'collecting'
      ? `${Math.min(card.fires_treatment, card.min_pairs)}/${card.min_pairs} · ${Math.min(card.fires_control, card.min_pairs)}/${card.min_pairs}`
      : `${card.fires_treatment}T / ${card.fires_control}C`;

  const legacy = card.legacy_helped || { fires: 0, helped: 0, helped_rate: 0 };
  const legacyRate = `${(legacy.helped_rate * 100).toFixed(0)}%`;

  // v2026.6.0: three orthogonal helped definitions. Each is null
  // until n_multi rows have accumulated; render "—" so the UI doesn't
  // claim a 0% rate when there's actually no data yet.
  const multi = card.multi_helped || {};
  const multiPct = (rate) =>
    rate === null || rate === undefined ? '—' : `${(rate * 100).toFixed(0)}%`;

  return html`
    <article class="roi-pattern-card">
      <header class="roi-pattern-card-header">
        <h3 class="roi-pattern-name">${card.pattern}</h3>
        <span class="roi-pattern-badge" style="background: ${status.color}">
          ${status.label}
        </span>
      </header>
      <div class="roi-pattern-grid">
        <div class="roi-pattern-stat">
          <span class="roi-pattern-stat-label">Δp (treat − ctrl)</span>
          <span class="roi-pattern-stat-value" style="color: ${card.delta_difference > 0 ? 'var(--success)' : card.delta_difference < 0 ? 'var(--error)' : 'var(--text)'}">
            ${_fmtDelta(card.delta_difference)}
          </span>
        </div>
        <div class="roi-pattern-stat">
          <span class="roi-pattern-stat-label">p-value</span>
          <span class="roi-pattern-stat-value">${_fmtP(card.p_value)}</span>
        </div>
        <div class="roi-pattern-stat">
          <span class="roi-pattern-stat-label">pairs</span>
          <span class="roi-pattern-stat-value">${progress}</span>
        </div>
      </div>
      ${multi.n_multi > 0 && html`
        <div class="roi-pattern-multi" title="Three orthogonal helped definitions — n=${multi.n_multi}">
          <span class="roi-pattern-multi-cell">Δp ${multiPct(multi.rate_pressure_drop)}</span>
          <span class="roi-pattern-multi-cell">tool-switch ${multiPct(multi.rate_tool_switch)}</span>
          <span class="roi-pattern-multi-cell">err-resolved ${multiPct(multi.rate_error_resolved)}</span>
        </div>
      `}
      <button
        type="button"
        class="roi-pattern-expand"
        onClick=${() => setExpanded(!expanded)}
      >
        ${expanded ? '− hide helped%' : '+ show helped% (legacy)'}
      </button>
      ${expanded && html`
        <div class="roi-pattern-legacy">
          <div class="roi-pattern-legacy-row">
            <span>helped rate</span>
            <span>${legacyRate}</span>
          </div>
          <div class="roi-pattern-legacy-row">
            <span>fires / helped</span>
            <span>${legacy.fires} / ${legacy.helped}</span>
          </div>
          <p class="roi-pattern-legacy-note">
            Legacy heuristic: unpaired, self-selection bias. Kept for
            continuity. Trust the verdict above.
          </p>
        </div>
      `}
    </article>
  `;
}

/** Reset banner — shown when ab_reset.log has a recent entry. */
function ResetBanner({ info }) {
  if (!info) return null;
  const ts = info.ts ? new Date(info.ts * 1000).toISOString().slice(0, 19).replace('T', ' ') : 'unknown';
  return html`
    <div class="roi-reset-banner" role="status">
      <strong>A/B data reset on ${ts} UTC.</strong>
      ${info.reason && html` ${info.reason}. `}
      ${info.archived_rows !== undefined && html` ${info.archived_rows} prior rows archived. `}
      New pairs are still accumulating — expect "collecting" verdicts until 30 clean pairs per arm.
    </div>
  `;
}

export function RoiPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const timerRef = useRef(null);

  async function load() {
    try {
      const d = await api.roi();
      setData(d);
    } catch (e) {
      console.error('[roi] fetch failed:', e);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    timerRef.current = setInterval(load, POLL_MS);
    return () => clearInterval(timerRef.current);
  }, []);

  if (loading) {
    return html`<div class="page roi-page"><div class="roi-loading">Loading ROI data...</div></div>`;
  }
  if (!data) {
    return html`<div class="page roi-page"><div class="roi-empty">No data available. Start using SOMA to see ROI metrics.</div></div>`;
  }

  const {
    guidance_effectiveness: ge,
    tokens_saved_estimate: ts,
    session_health: sh,
    cascades_broken: cb,
    pattern_ab_status: pab,
    ab_reset_info: reset,
  } = data;

  const tokensSaved = ts.estimated_tokens_saved;
  const tokenStr = tokensSaved >= 1000 ? `${(tokensSaved / 1000).toFixed(1)}K` : `${tokensSaved}`;
  const effectivenessStr = `${(ge.effectiveness_rate * 100).toFixed(0)}%`;
  const healthScore = sh.score;
  const cards = pab || [];

  return html`
    <div class="page roi-page">
      <header class="roi-header">
        <h1>Is SOMA worth it?</h1>
        <p class="roi-subtitle">Real-time return on investment from behavioral monitoring</p>
      </header>

      <${ResetBanner} info=${reset} />

      <div class="roi-hero">
        <${HealthGauge} score=${healthScore} />
        <div class="roi-hero-metrics">
          <${Metric} value=${cb.total} label="cascades broken" sublabel="error chains stopped early" accent />
          <${Metric} value=${effectivenessStr} label="guidance precision" sublabel="${ge.helped}/${ge.total} interventions helped" />
          <${Metric} value=${ge.helped} label="interventions helped" sublabel="followthrough confirmed" />
        </div>
      </div>

      <aside class="roi-estimate-note" title=${ts.methodology}>
        <span class="roi-estimate-label">rough estimate (unverified):</span>
        <span class="roi-estimate-value">~${tokenStr} tokens saved</span>
        <span class="roi-estimate-disclaimer">
          synthetic multiplier (helped × 3 × 800), not measured
        </span>
      </aside>

      ${sh.components && Object.keys(sh.components).length > 0 && html`
        <section class="roi-section">
          <h2>Health Breakdown</h2>
          <div class="roi-health-grid">
            ${Object.entries(sh.components).map(([key, val]) => html`
              <div class="roi-health-item">
                <span class="roi-health-key">${key.replace('_', ' ')}</span>
                <span class="roi-health-val" style="color: ${val > 0.1 ? 'var(--warning)' : 'var(--success)'}">${(val * 100).toFixed(1)}%</span>
              </div>
            `)}
          </div>
        </section>
      `}

      <section class="roi-section">
        <h2>Pattern Verdicts</h2>
        <p class="roi-section-desc">
          A/B-controlled evaluation — each pattern fires for a randomized half of
          eligible moments so treatment Δp can be tested against control Δp.
          Validated = significant drop; refuted = reliably wrong direction.
        </p>
        ${cards.length === 0
          ? html`<div class="roi-empty">No A/B data yet. Use SOMA and check back.</div>`
          : html`
            <div class="roi-pattern-grid-outer">
              ${cards.map(c => html`<${PatternCard} card=${c} />`)}
            </div>
          `
        }
      </section>
    </div>
  `;
}

export default RoiPage;
