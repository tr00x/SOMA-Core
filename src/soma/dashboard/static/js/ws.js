/**
 * SOMA Dashboard — WebSocket Client
 *
 * Connects to /ws for real-time state updates.
 * Falls back to HTTP polling on disconnect.
 */

import store from './store.js';
import api from './api.js';

let ws = null;
let reconnectTimer = null;
let pollTimer = null;
let reconnectDelay = 1000;
const MAX_RECONNECT_DELAY = 30000;

function getWsUrl() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${location.host}/ws`;
}

/** Convert agents dict {"cc-1001": {...}} to array [{agent_id: "cc-1001", ...}] */
function agentsToArray(agentsObj) {
  if (!agentsObj || Array.isArray(agentsObj)) return agentsObj || [];
  return Object.entries(agentsObj).map(([id, data]) => ({ agent_id: id, ...data }));
}

function handleMessage(event) {
  try {
    const msg = JSON.parse(event.data);
    if (msg.type === 'state_full' || msg.type === 'state_update') {
      const partial = {};
      if (msg.data.budget) partial.budget = msg.data.budget;
      // Refresh agents from REST API (has display names resolved)
      if (msg.data.agents) {
        api.agents().then(agents => store.update({ agents })).catch(() => {});
      }
      store.update(partial);
    }
  } catch (e) {
    console.error('[ws] Failed to parse message:', e);
  }
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function startPolling() {
  stopPolling();
  async function poll() {
    try {
      const [agents, overview, budget] = await Promise.all([
        api.agents(),
        api.overview(),
        api.budget(),
      ]);
      store.update({ agents, overview, budget, loading: false });
    } catch (_) {
      // Polling failure is non-fatal
    }
  }
  poll(); // immediate first poll
  pollTimer = setInterval(poll, 2000);
}

export function connect() {
  if (ws && (ws.readyState === WebSocket.CONNECTING || ws.readyState === WebSocket.OPEN)) {
    return;
  }

  try {
    ws = new WebSocket(getWsUrl());
  } catch (e) {
    console.error('[ws] Failed to create WebSocket:', e);
    store.update({ wsConnected: false });
    startPolling();
    scheduleReconnect();
    return;
  }

  ws.onopen = () => {
    console.log('[ws] Connected');
    store.update({ wsConnected: true });
    reconnectDelay = 1000;
    stopPolling();
  };

  ws.onmessage = handleMessage;

  ws.onclose = (ev) => {
    console.log('[ws] Disconnected:', ev.code, ev.reason);
    store.update({ wsConnected: false });
    ws = null;
    startPolling();
    scheduleReconnect();
  };

  ws.onerror = (err) => {
    console.error('[ws] Error:', err);
    // onclose will fire after onerror
  };
}

function scheduleReconnect() {
  if (reconnectTimer) clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(() => {
    console.log(`[ws] Reconnecting (delay: ${reconnectDelay}ms)...`);
    connect();
    reconnectDelay = Math.min(reconnectDelay * 2, MAX_RECONNECT_DELAY);
  }, reconnectDelay);
}

export function disconnect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  stopPolling();
  if (ws) {
    ws.close();
    ws = null;
  }
}

export default { connect, disconnect };
