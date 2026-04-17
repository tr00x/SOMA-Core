/**
 * RoiPage — "Is SOMA worth it?" single-page answer.
 *
 * Shows: health score, tokens saved, cascades broken,
 * guidance precision, pattern hit rates chart.
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

/** Horizontal bar chart for pattern hit rates */
function PatternBars({ patterns }) {
  if (!patterns || patterns.length === 0) {
    return html`<div class="roi-empty">No guidance patterns fired yet. Use SOMA and check back.</div>`;
  }
  const maxFires = Math.max(...patterns.map(p => p.fires));

  return html`
    <div class="roi-bars">
      ${patterns.map(p => {
        const pct = maxFires > 0 ? (p.fires / maxFires) * 100 : 0;
        const followPct = (p.follow_rate * 100).toFixed(0);
        return html`
          <div class="roi-bar-row">
            <div class="roi-bar-label">${p.pattern_key}</div>
            <div class="roi-bar-track">
              <div class="roi-bar-fill" style="width: ${pct}%"></div>
              <div class="roi-bar-followed" style="width: ${pct * p.follow_rate}%"></div>
            </div>
            <div class="roi-bar-stats">
              <span class="roi-bar-count">${p.fires}</span>
              <span class="roi-bar-rate">${followPct}%</span>
            </div>
          </div>
        `;
      })}
      <div class="roi-bars-legend">
        <span><span class="roi-legend-dot fired"></span> fired</span>
        <span><span class="roi-legend-dot followed"></span> followed</span>
      </div>
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

  const { guidance_effectiveness: ge, tokens_saved_estimate: ts, session_health: sh, cascades_broken: cb, pattern_hit_rates: ph } = data;

  const tokensSaved = ts.estimated_tokens_saved;
  const tokenStr = tokensSaved >= 1000 ? `${(tokensSaved / 1000).toFixed(1)}K` : `${tokensSaved}`;
  const effectivenessStr = `${(ge.effectiveness_rate * 100).toFixed(0)}%`;
  const healthScore = sh.score;

  return html`
    <div class="page roi-page">
      <header class="roi-header">
        <h1>Is SOMA worth it?</h1>
        <p class="roi-subtitle">Real-time return on investment from behavioral monitoring</p>
      </header>

      <div class="roi-hero">
        <${HealthGauge} score=${healthScore} />
        <div class="roi-hero-metrics">
          <${Metric} value=${tokenStr} label="tokens saved" sublabel="estimated from broken cascades" accent />
          <${Metric} value=${cb.total} label="cascades broken" sublabel="error chains stopped early" />
          <${Metric} value=${effectivenessStr} label="guidance precision" sublabel="${ge.helped}/${ge.total} interventions helped" />
        </div>
      </div>

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
        <h2>Pattern Performance</h2>
        <p class="roi-section-desc">Which patterns fire most, and how often agents follow the guidance.</p>
        <${PatternBars} patterns=${ph} />
      </section>
    </div>
  `;
}

export default RoiPage;
