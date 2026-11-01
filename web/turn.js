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
