/**
 * SOMA Dashboard — Main Application
 *
 * Preact + HTM + preact-router SPA.
 * No build step, no bundler, pure ES modules via import maps.
 */

import { h, render } from 'preact';
import { useState, useEffect, useCallback } from 'preact/hooks';
import { html } from 'htm/preact';
import Router from 'preact-router';

import store from './store.js';
import { connect } from './ws.js';

// Pages
import OverviewPage from './pages/OverviewPage.js';
import AgentPage from './pages/AgentPage.js';
import SessionPage from './pages/SessionPage.js';
import SettingsPage from './pages/SettingsPage.js';

/** Inline SVG for SOMA logo */
function SomaLogo() {
  return html`
    <svg viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
      <circle cx="16" cy="16" r="14" fill="var(--accent)"/>
      <circle cx="16" cy="16" r="8" fill="var(--bg)" opacity="0.4"/>
      <circle cx="16" cy="16" r="3" fill="var(--accent)"/>
    </svg>
  `;
}

/** Navigation bar */
function Nav({ currentPath, wsConnected }) {
  const isActive = (path) => {
    if (path === '/' && currentPath === '/') return true;
    if (path !== '/' && currentPath.startsWith(path)) return true;
    return false;
  };

  return html`
    <nav class="nav" role="navigation" aria-label="Main navigation">
      <a href="/" class="nav-brand" aria-label="SOMA Dashboard home">
        <${SomaLogo} />
        <span>SOMA</span>
      </a>

      <ul class="nav-links" role="menubar">
        <li role="none">
          <a href="/" class="nav-link ${isActive('/') && !isActive('/agents') && !isActive('/sessions') && !isActive('/settings') ? 'active' : ''}" role="menuitem">
            Overview
          </a>
        </li>
        <li role="none">
          <a href="/sessions" class="nav-link ${isActive('/sessions') ? 'active' : ''}" role="menuitem">
            Sessions
          </a>
        </li>
        <li role="none">
          <a href="/settings" class="nav-link ${isActive('/settings') ? 'active' : ''}" role="menuitem">
            Settings
          </a>
        </li>
      </ul>

      <div class="nav-spacer"></div>

      <div class="nav-status" aria-live="polite">
        <span class="status-dot ${wsConnected ? 'connected' : 'reconnecting'}"
              role="status"
              aria-label=${wsConnected ? 'Connected' : 'Reconnecting'}></span>
        <span>${wsConnected ? 'live' : 'reconnecting'}</span>
      </div>
    </nav>
  `;
}

/** Reconnect banner shown when WS is disconnected */
function ReconnectBanner({ visible }) {
  if (!visible) return null;
  return html`
    <div class="reconnect-banner" role="alert">
      <div class="spinner"></div>
      Connection lost. Reconnecting...
    </div>
  `;
}

/** Main App component */
function App() {
  const [currentPath, setCurrentPath] = useState(location.pathname);
  const [wsConnected, setWsConnected] = useState(false);

  useEffect(() => {
    // Start WebSocket connection
    connect();

    // Listen to store for WS status
    const unsub = store.subscribe((s) => {
      setWsConnected(s.wsConnected);
    });

    return unsub;
  }, []);

  const handleRoute = useCallback((e) => {
    setCurrentPath(e.url);
  }, []);

  return html`
    <${Nav} currentPath=${currentPath} wsConnected=${wsConnected} />
    <${ReconnectBanner} visible=${!wsConnected} />

    <main id="main-content" role="main">
      <${Router} onChange=${handleRoute}>
        <${OverviewPage} path="/" />
        <${AgentPage} path="/agents/:id" />
        <${SessionPage} path="/sessions/:id" />
        <${SessionPage} path="/sessions" />
        <${SettingsPage} path="/settings" />
        <${OverviewPage} default />
      </${Router}>
    </main>
  `;
}

// Mount
render(html`<${App} />`, document.getElementById('app'));
