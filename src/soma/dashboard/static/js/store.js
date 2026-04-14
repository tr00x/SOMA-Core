/**
 * SOMA Dashboard — Reactive Store
 *
 * Simple pub/sub state management. Components subscribe to changes
 * and re-render when state updates.
 */

const initialState = {
  agents: [],
  sessions: [],
  overview: null,
  config: {},
  budget: null,
  wsConnected: false,
  loading: true,
  error: null,
  /** Track selected agent detail data separately */
  agentDetail: null,
  agentTimeline: [],
  agentPressureHistory: [],
  agentTools: [],
  agentAudit: [],
  agentGuidance: null,
  agentQuality: null,
  agentFindings: [],
  agentBaselines: null,
  agentPredictions: null,
  agentFingerprint: null,
  agentLearning: null,
  /** Session detail */
  sessionDetail: null,
  /** Graph data */
  graph: null,
};

let state = { ...initialState };
const listeners = new Set();

export const store = {
  /** Get current state (read-only snapshot) */
  getState() {
    return state;
  },

  /** Merge partial state and notify all subscribers */
  update(partial) {
    const prev = state;
    state = { ...state, ...partial };
    for (const fn of listeners) {
      try {
        fn(state, prev);
      } catch (e) {
        console.error('[store] Listener error:', e);
      }
    }
  },

  /** Subscribe to state changes. Returns unsubscribe function. */
  subscribe(fn) {
    listeners.add(fn);
    return () => listeners.delete(fn);
  },

  /** Reset to initial state */
  reset() {
    state = { ...initialState };
    for (const fn of listeners) {
      try {
        fn(state, initialState);
      } catch (_) {}
    }
  },
};

export default store;
