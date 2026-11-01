/*
 * TURN configuration for the browser build.
 *
 * This module has no dependencies and no side effects; web/net.js imports
 * normalizeTurnConfig, and web/index.html imports the loaders and the
 * player-override helpers.
 */

const TURN_URL = /^(turns?):(\[[0-9a-fA-F:]+\]|[A-Za-z0-9._-]+)(?::(\d{1,5}))?(?:\?([A-Za-z0-9=&%._-]+))?$/;
const MAX_FIELD = 512;
const MAX_URL = 2048;

export const PLAYER_STORAGE_KEY = 'xb:turn';

export function parseTurnUrl(value) {
  if (typeof value !== 'string') return null;
  const text = value.trim();
  if (!text || text.length > MAX_URL) return null;
  const match = TURN_URL.exec(text);
  if (!match) return null;
  const port = match[3] ? Number(match[3]) : null;
  if (port !== null && (port < 1 || port > 65535)) return null;
  return text;
}

export function normalizeTurnConfig(value) {
  if (!Array.isArray(value)) return [];
  const out = [];
  for (const entry of value) {
    if (!entry || typeof entry !== 'object') continue;
    const rawUrls = Array.isArray(entry.urls) ? entry.urls : [entry.urls];
    if (!rawUrls.length) continue;
    const urls = rawUrls.map(parseTurnUrl);
    if (urls.some((url) => !url)) continue;
    if (typeof entry.username !== 'string' || !entry.username ||
        entry.username.length > MAX_FIELD) continue;
    if (typeof entry.credential !== 'string' || !entry.credential ||
        entry.credential.length > MAX_FIELD) continue;
    out.push({
      urls: Array.isArray(entry.urls) ? urls : urls[0],
      username: entry.username,
      credential: entry.credential,
    });
  }
  return out;
}

function isLocalHost(hostname) {
  return hostname === 'localhost' || hostname === '127.0.0.1' ||
    hostname === '::1' || hostname === '[::1]';
}

function parseCredentialUrl(value, baseUrl) {
  if (typeof value !== 'string') return null;
  const text = value.trim();
  if (!text || text.length > MAX_URL) return null;
  let url;
  try {
    url = new URL(text, baseUrl);
  } catch (e) {
    return null;
  }
  if (url.username || url.password || url.hash) return null;
  if (url.protocol !== 'https:' && !(url.protocol === 'http:' && isLocalHost(url.hostname))) {
    return null;
  }
  return url.href;
}

export function parseTurnFile(data, opts = {}) {
  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    return { turnConfig: [], credentialsUrl: null, warning: 'TURN configuration is not an object.' };
  }
  const turnConfig = normalizeTurnConfig(data.turnConfig);
  let warning = null;
  if (data.turnConfig !== undefined && turnConfig.length === 0) {
    warning = 'TURN configuration has no valid entries.';
  }
  let credentialsUrl = null;
  if (data.credentialsUrl !== undefined) {
    const baseUrl = opts.baseUrl ||
      (typeof location !== 'undefined' ? location.href : 'https://localhost/');
    credentialsUrl = parseCredentialUrl(data.credentialsUrl, baseUrl);
    if (!credentialsUrl) warning = 'TURN credentials URL is invalid.';
  }
  return { turnConfig, credentialsUrl, warning };
}

export function parseCredentialResponse(data) {
  if (Array.isArray(data)) {
    return { turnConfig: normalizeTurnConfig(data), warning: null };
  }
  if (!data || typeof data !== 'object') {
    return { turnConfig: [], warning: 'TURN credential response is not an object.' };
  }
  if (Array.isArray(data.turnConfig)) {
    return { turnConfig: normalizeTurnConfig(data.turnConfig), warning: null };
  }
  const turnConfig = normalizeTurnConfig([data]);
  if (turnConfig.length) return { turnConfig, warning: null };
  return { turnConfig: [], warning: 'TURN credential response has no valid entries.' };
}

async function fetchJson(url, fetchImpl, init, timeoutMs) {
  const controller = typeof AbortController === 'function' ? new AbortController() : null;
  const timer = controller ? setTimeout(() => controller.abort(), timeoutMs) : null;
  try {
    const response = await fetchImpl(url, {
      ...init,
      signal: controller ? controller.signal : undefined,
    });
    if (!response || !response.ok) {
      throw new Error(`HTTP ${response ? response.status : 'ERR'}`);
    }
    return await response.json();
  } finally {
    if (timer) clearTimeout(timer);
  }
}

export async function loadTurnFile(opts = {}) {
  const fetchImpl = opts.fetchImpl || (typeof fetch === 'function' ? fetch : null);
  const url = opts.url || './turn.json';
  const timeoutMs = Number.isFinite(opts.timeoutMs) ? opts.timeoutMs : 3000;
  if (!fetchImpl) {
    return { turnConfig: [], credentialsUrl: null, warning: 'fetch is unavailable.' };
  }
  try {
    const data = await fetchJson(url, fetchImpl, { cache: 'no-cache' }, timeoutMs);
    return parseTurnFile(data);
  } catch (e) {
    return {
      turnConfig: [],
      credentialsUrl: null,
      warning: `TURN configuration unavailable: ${e && e.message ? e.message : e}`,
    };
  }
}

export async function fetchCredentials(url, opts = {}) {
  const fetchImpl = opts.fetchImpl || (typeof fetch === 'function' ? fetch : null);
  const timeoutMs = Number.isFinite(opts.timeoutMs) ? opts.timeoutMs : 3000;
  if (!fetchImpl) {
    return { turnConfig: [], warning: 'fetch is unavailable.' };
  }
  try {
    const data = await fetchJson(url, fetchImpl, {
      cache: 'no-store',
      mode: 'cors',
      credentials: 'omit',
      headers: { Accept: 'application/json' },
    }, timeoutMs);
    return parseCredentialResponse(data);
  } catch (e) {
    return {
      turnConfig: [],
      warning: `TURN credentials unavailable: ${e && e.message ? e.message : e}`,
    };
  }
}

export async function resolveTurnConfig(opts = {}) {
  const player = normalizeTurnConfig(opts.playerOverride);
  if (player.length) {
    return { turnConfig: player, source: 'player', warning: null };
  }
  const file = opts.file || null;
  const staticConfig = normalizeTurnConfig(file && file.turnConfig);
  let warning = file && file.warning ? file.warning : null;
  if (file && file.credentialsUrl) {
    const endpoint = await fetchCredentials(file.credentialsUrl, opts);
    if (endpoint.turnConfig.length) {
      return { turnConfig: endpoint.turnConfig, source: 'endpoint', warning: null };
    }
    if (endpoint.warning) warning = endpoint.warning;
  }
  if (staticConfig.length) {
    return { turnConfig: staticConfig, source: 'file', warning };
  }
  return { turnConfig: [], source: null, warning };
}

const OVERRIDE_ERROR = 'Enter a turn: or turns: URL, username and credential.';

export function parsePlayerOverride(value) {
  if (!value || typeof value !== 'object') {
    return { turnConfig: [], error: OVERRIDE_ERROR };
  }
  let urls = value.urls;
  if (typeof urls === 'string') {
    urls = urls.split(/[\s,]+/).filter(Boolean);
  } else if (!Array.isArray(urls)) {
    urls = [];
  }
  urls = urls.map((url) => String(url).trim()).filter(Boolean);
  const username = typeof value.username === 'string' ? value.username.trim() : '';
  const credential = typeof value.credential === 'string' ? value.credential.trim() : '';
  const turnConfig = normalizeTurnConfig([{ urls, username, credential }]);
  if (!turnConfig.length) {
    return { turnConfig: [], error: OVERRIDE_ERROR };
  }
  return { turnConfig, error: null };
}

export function readPlayerOverride(storage = globalThis.sessionStorage) {
  try {
    const raw = storage.getItem(PLAYER_STORAGE_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    if (!data || typeof data !== 'object') return null;
    return {
      urls: Array.isArray(data.urls) ? data.urls.slice() : String(data.urls || ''),
      username: typeof data.username === 'string' ? data.username : '',
      credential: typeof data.credential === 'string' ? data.credential : '',
    };
  } catch (e) {
    return null;
  }
}

export function writePlayerOverride(storage, value) {
  if (!storage || !value) return false;
  try {
    storage.setItem(PLAYER_STORAGE_KEY, JSON.stringify({
      urls: Array.isArray(value.urls) ? value.urls.slice() : String(value.urls || ''),
      username: typeof value.username === 'string' ? value.username : '',
      credential: typeof value.credential === 'string' ? value.credential : '',
    }));
    return true;
  } catch (e) {
    return false;
  }
}

export function clearPlayerOverride(storage = globalThis.sessionStorage) {
  try {
    storage.removeItem(PLAYER_STORAGE_KEY);
  } catch (e) {
    // private mode or no storage
  }
}
