/* ============================================================
   SOMA Dashboard v2 — Chart.js Lifecycle Management
   ============================================================ */

window.SOMA = window.SOMA || {};

SOMA.charts = (() => {
  // Shared dark theme defaults
  const GRID_COLOR = '#1e1e1e';
  const TEXT_COLOR = '#666';
  const PINK = '#ff2d78';
  const PINK_LIGHT = '#ff6ba6';
  const SUCCESS = '#00ff88';
  const WARNING = '#ffaa00';
  const ERROR = '#ff4444';

  const BASE_OPTIONS = {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    plugins: {
      legend: { display: false },
    },
  };

  const SCALE_DEFAULTS = {
    grid: { color: GRID_COLOR },
    ticks: { color: TEXT_COLOR, font: { size: 10 } },
    border: { color: GRID_COLOR },
  };

  // ---------------------------------------------------------
  // Pressure Timeline Chart
  // ---------------------------------------------------------
  function createPressureChart(canvasId, trajectoryData, thresholds) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;

    const ctx = canvas.getContext('2d');
    const labels = (trajectoryData || []).map((_, i) => i);
    const values = (trajectoryData || []).map(d => typeof d === 'number' ? d : d.pressure || 0);
    const t = thresholds || { guide: 0.4, warn: 0.6, block: 0.8 };

    const datasets = [
      {
        label: 'Pressure',
        data: values,
        borderColor: PINK,
        backgroundColor: 'rgba(255, 45, 120, 0.1)',
        fill: true,
        tension: 0.3,
        pointRadius: 0,
        borderWidth: 2,
      },
      {
        label: 'Guide',
        data: Array(labels.length).fill(t.guide),
        borderColor: SUCCESS,
        borderWidth: 1,
        borderDash: [4, 4],
        pointRadius: 0,
        fill: false,
      },
      {
        label: 'Warn',
        data: Array(labels.length).fill(t.warn),
        borderColor: WARNING,
        borderWidth: 1,
        borderDash: [4, 4],
        pointRadius: 0,
        fill: false,
      },
      {
        label: 'Block',
        data: Array(labels.length).fill(t.block),
        borderColor: ERROR,
        borderWidth: 1,
        borderDash: [4, 4],
        pointRadius: 0,
        fill: false,
      },
    ];

    return new Chart(ctx, {
      type: 'line',
      data: { labels, datasets },
      options: {
        ...BASE_OPTIONS,
        scales: {
          x: { ...SCALE_DEFAULTS, display: false },
          y: { ...SCALE_DEFAULTS, min: 0, max: 1 },
        },
        plugins: {
          ...BASE_OPTIONS.plugins,
          tooltip: {
            backgroundColor: '#111',
            titleColor: '#ccc',
            bodyColor: '#999',
            borderColor: '#1e1e1e',
            borderWidth: 1,
          },
        },
      },
    });
  }

  // ---------------------------------------------------------
  // Radar Chart (6-axis vitals)
  // ---------------------------------------------------------
  function createRadarChart(canvasId, vitalsData, baselineData) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;

    const ctx = canvas.getContext('2d');
    const axisLabels = ['Uncertainty', 'Drift', 'Error Rate', 'Cost', 'Coherence', 'Context'];

    // Accept object {uncertainty, drift, ...} or array [v1, v2, ...]
    const keys = ['uncertainty', 'drift', 'error_rate', 'cost', 'coherence', 'context'];
    const toArr = (d) => Array.isArray(d) ? d : keys.map(k => d[k] || 0);
    const current = toArr(vitalsData || {});
    const baseline = toArr(baselineData || {});

    return new Chart(ctx, {
      type: 'radar',
      data: {
        labels: axisLabels,
        datasets: [
          {
            label: 'Current',
            data: current,
            borderColor: PINK,
            backgroundColor: 'rgba(255, 45, 120, 0.15)',
            borderWidth: 2,
            pointRadius: 3,
            pointBackgroundColor: PINK,
          },
          {
            label: 'Baseline',
            data: baseline,
            borderColor: '#444',
            backgroundColor: 'rgba(68, 68, 68, 0.1)',
            borderWidth: 1,
            borderDash: [3, 3],
            pointRadius: 2,
            pointBackgroundColor: '#444',
          },
        ],
      },
      options: {
        ...BASE_OPTIONS,
        plugins: {
          ...BASE_OPTIONS.plugins,
          legend: { display: true, labels: { color: TEXT_COLOR, font: { size: 10 } } },
        },
        scales: {
          r: {
            grid: { color: GRID_COLOR },
            angleLines: { color: GRID_COLOR },
            pointLabels: { color: TEXT_COLOR, font: { size: 10 } },
            ticks: { display: false },
            suggestedMin: 0,
            suggestedMax: 1,
          },
        },
      },
    });
  }

  // ---------------------------------------------------------
  // Sparkline (tiny inline chart)
  // ---------------------------------------------------------
  function createSparkline(canvasId, data) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;

    const ctx = canvas.getContext('2d');
    const values = (data || []).slice(-30);
    const lastVal = values[values.length - 1] || 0;

    let color = SUCCESS;
    if (lastVal >= 0.8) color = ERROR;
    else if (lastVal >= 0.6) color = WARNING;
    else if (lastVal >= 0.4) color = WARNING;

    return new Chart(ctx, {
      type: 'line',
      data: {
        labels: values.map((_, i) => i),
        datasets: [{
          data: values,
          borderColor: color,
          borderWidth: 1.5,
          pointRadius: 0,
          fill: false,
          tension: 0.3,
        }],
      },
      options: {
        ...BASE_OPTIONS,
        scales: {
          x: { display: false },
          y: { display: false, min: 0, max: 1 },
        },
        plugins: { legend: { display: false }, tooltip: { enabled: false } },
      },
    });
  }

  // ---------------------------------------------------------
  // Heatmap (24h activity)
  // ---------------------------------------------------------
  function createHeatmap(canvasId, data) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;

    const ctx = canvas.getContext('2d');
    const hours = (data || []).map(d => d.hour != null ? d.hour + 'h' : '');
    const counts = (data || []).map(d => d.count || 0);
    const max = Math.max(1, ...counts);

    return new Chart(ctx, {
      type: 'bar',
      data: {
        labels: hours,
        datasets: [{
          data: counts,
          backgroundColor: counts.map(c => {
            const intensity = c / max;
            return 'rgba(255, 45, 120, ' + (0.1 + intensity * 0.7) + ')';
          }),
          borderWidth: 0,
          borderRadius: 2,
        }],
      },
      options: {
        ...BASE_OPTIONS,
        scales: {
          x: { ...SCALE_DEFAULTS, ticks: { ...SCALE_DEFAULTS.ticks, maxRotation: 0, font: { size: 8 } } },
          y: { ...SCALE_DEFAULTS, display: false },
        },
      },
    });
  }

  // ---------------------------------------------------------
  // Horizontal Bar Chart
  // ---------------------------------------------------------
  function createBarChart(canvasId, labels, values) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;

    const ctx = canvas.getContext('2d');

    return new Chart(ctx, {
      type: 'bar',
      data: {
        labels: labels || [],
        datasets: [{
          data: values || [],
          backgroundColor: PINK,
          borderWidth: 0,
          borderRadius: 3,
        }],
      },
      options: {
        ...BASE_OPTIONS,
        indexAxis: 'y',
        scales: {
          x: { ...SCALE_DEFAULTS },
          y: { ...SCALE_DEFAULTS, ticks: { ...SCALE_DEFAULTS.ticks, font: { size: 10 } } },
        },
      },
    });
  }

  // ---------------------------------------------------------
  // Trend Chart (multi-session line)
  // ---------------------------------------------------------
  function createTrendChart(canvasId, sessionsData) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return null;

    const ctx = canvas.getContext('2d');
    const sessions = sessionsData || [];
    const labels = sessions.map((_, i) => 'S' + (i + 1));

    const datasets = [];
    if (sessions.length > 0 && sessions[0].avg_pressure != null) {
      datasets.push({
        label: 'Avg Pressure',
        data: sessions.map(s => s.avg_pressure || 0),
        borderColor: PINK,
        borderWidth: 2,
        pointRadius: 3,
        pointBackgroundColor: PINK,
        fill: false,
        tension: 0.3,
      });
    }
    if (sessions.length > 0 && sessions[0].error_count != null) {
      datasets.push({
        label: 'Errors',
        data: sessions.map(s => s.error_count || 0),
        borderColor: ERROR,
        borderWidth: 2,
        pointRadius: 3,
        pointBackgroundColor: ERROR,
        fill: false,
        tension: 0.3,
      });
    }

    return new Chart(ctx, {
      type: 'line',
      data: { labels, datasets },
      options: {
        ...BASE_OPTIONS,
        plugins: {
          ...BASE_OPTIONS.plugins,
          legend: { display: true, labels: { color: TEXT_COLOR, font: { size: 10 } } },
        },
        scales: {
          x: { ...SCALE_DEFAULTS },
          y: { ...SCALE_DEFAULTS, beginAtZero: true },
        },
      },
    });
  }

  // ---------------------------------------------------------
  // Lifecycle helpers
  // ---------------------------------------------------------
  function destroyChart(chart) {
    if (chart && typeof chart.destroy === 'function') {
      try { chart.destroy(); } catch (_) {}
    }
    return null;
  }

  function updateChart(chart, newData) {
    if (!chart) return;
    try {
      if (Array.isArray(newData)) {
        chart.data.datasets[0].data = newData;
      } else if (newData && newData.datasets) {
        chart.data = newData;
      }
      chart.update('none'); // no animation
    } catch (_) {}
  }

  // ---------------------------------------------------------
  // Public API
  // ---------------------------------------------------------
  return {
    createPressureChart,
    createRadarChart,
    createSparkline,
    createHeatmap,
    createBarChart,
    createTrendChart,
    destroyChart,
    updateChart,
  };
})();
