/**
 * PressureChart — Chart.js line chart for pressure history.
 *
 * Shows pressure over time with mode-colored zone backgrounds
 * and a baseline overlay.
 */

import { html } from 'htm/preact';
import { useEffect, useRef } from 'preact/hooks';

let Chart = null;
let chartLoaded = false;

async function ensureChartJs() {
  if (chartLoaded) return;
  const mod = await import('chart.js/auto');
  Chart = mod.default || mod.Chart;
  chartLoaded = true;
}

function formatTime(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function PressureChart({ history = [], baselines = null }) {
  const canvasRef = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    if (!history.length) return;

    let cancelled = false;

    (async () => {
      await ensureChartJs();
      if (cancelled || !canvasRef.current) return;

      const labels = history.map(h => formatTime(h.timestamp));
      const pressureData = history.map(h => h.pressure ?? 0);

      const datasets = [
        {
          label: 'Pressure',
          data: pressureData,
          borderColor: '#f43f5e',
          backgroundColor: 'rgba(244, 63, 94, 0.08)',
          borderWidth: 2,
          fill: true,
          tension: 0.35,
          pointRadius: 0,
          pointHoverRadius: 4,
          pointHoverBackgroundColor: '#f43f5e',
        },
      ];

      // Baseline line if available
      if (baselines && baselines.uncertainty !== undefined) {
        datasets.push({
          label: 'Baseline',
          data: Array(pressureData.length).fill(baselines.uncertainty),
          borderColor: 'rgba(161, 161, 170, 0.3)',
          borderWidth: 1,
          borderDash: [4, 4],
          pointRadius: 0,
          fill: false,
        });
      }

      const config = {
        type: 'line',
        data: { labels, datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          interaction: {
            mode: 'index',
            intersect: false,
          },
          plugins: {
            legend: { display: false },
            tooltip: {
              backgroundColor: '#18181b',
              titleColor: '#fafafa',
              bodyColor: '#a1a1aa',
              borderColor: '#27272a',
              borderWidth: 1,
              padding: 10,
              cornerRadius: 8,
              titleFont: { family: "'JetBrains Mono', monospace", size: 11 },
              bodyFont: { family: "'JetBrains Mono', monospace", size: 11 },
              callbacks: {
                label: (ctx) => {
                  const val = ctx.parsed.y;
                  return `${ctx.dataset.label}: ${(val * 100).toFixed(1)}%`;
                },
              },
            },
          },
          scales: {
            x: {
              grid: { color: 'rgba(39, 39, 42, 0.5)', drawBorder: false },
              ticks: {
                color: '#52525b',
                font: { family: "'JetBrains Mono', monospace", size: 10 },
                maxTicksLimit: 10,
              },
            },
            y: {
              min: 0,
              max: 1,
              grid: { color: 'rgba(39, 39, 42, 0.5)', drawBorder: false },
              ticks: {
                color: '#52525b',
                font: { family: "'JetBrains Mono', monospace", size: 10 },
                callback: (v) => `${Math.round(v * 100)}%`,
                stepSize: 0.25,
              },
            },
          },
          animation: {
            duration: 400,
            easing: 'easeOutQuart',
          },
        },
        plugins: [
          {
            id: 'modeZones',
            beforeDraw(chart) {
              const { ctx, chartArea: { left, right, top, bottom }, scales: { y } } = chart;
              const zones = [
                { min: 0, max: 0.25, color: 'rgba(34, 197, 94, 0.04)' },
                { min: 0.25, max: 0.5, color: 'rgba(234, 179, 8, 0.04)' },
                { min: 0.5, max: 0.75, color: 'rgba(249, 115, 22, 0.04)' },
                { min: 0.75, max: 1, color: 'rgba(239, 68, 68, 0.04)' },
              ];
              for (const z of zones) {
                const yTop = y.getPixelForValue(z.max);
                const yBot = y.getPixelForValue(z.min);
                ctx.fillStyle = z.color;
                ctx.fillRect(left, yTop, right - left, yBot - yTop);
              }
            },
          },
        ],
      };

      if (chartRef.current) {
        chartRef.current.destroy();
      }
      chartRef.current = new Chart(canvasRef.current, config);
    })();

    return () => {
      cancelled = true;
      if (chartRef.current) {
        chartRef.current.destroy();
        chartRef.current = null;
      }
    };
  }, [history, baselines]);

  if (!history.length) {
    return html`
      <div class="empty-state" style="padding:32px">
        <div class="empty-state-title">No pressure data yet</div>
        <div class="empty-state-text">Pressure history will appear as actions are recorded.</div>
      </div>
    `;
  }

  return html`
    <div class="chart-container">
      <canvas ref=${canvasRef}></canvas>
    </div>
  `;
}

export default PressureChart;
