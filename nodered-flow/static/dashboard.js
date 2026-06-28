/* global */
'use strict';

// ── State ──────────────────────────────────────────────────────────────────
let events = [];
let selectedEvent = null;

// In-memory ICAO type cache: icao -> string type (already fetched from server)
// The server now stores API data in the DB, so this just avoids redundant calls.
const icaoTypeCache = new Map();
const icaoFetching = new Set();

// ── DOM refs ───────────────────────────────────────────────────────────────
const rowsEl = document.getElementById('rows');
const qEl = document.getElementById('q');
const milEl = document.getElementById('mil');
const limitEl = document.getElementById('limit');
const decodedFilterEl = document.getElementById('decoded');
const detailOverlay = document.getElementById('detailOverlay');
const detailTitle = document.getElementById('detailTitle');
const detailSubtitle = document.getElementById('detailSubtitle');
const detailGrid = document.getElementById('detailGrid');
const detailText = document.getElementById('detailText');
const detailJson = document.getElementById('detailJson');
const libacarsStatus = document.getElementById('libacarsStatus');
const libacarsJson = document.getElementById('libacarsJson');
const decodedSummaryEl = document.getElementById('decodedSummary');
const acarsDecoderStatus = document.getElementById('acarsDecoderStatus');
const acarsDecoderJson = document.getElementById('acarsDecoderJson');
const loadAirframeApiBtn = document.getElementById('loadAirframeApi');
const airframeApiStatus = document.getElementById('airframeApiStatus');
const airframeApiJson = document.getElementById('airframeApiJson');
const fullscreenBtn = document.getElementById('fullscreenBtn');

// ── Utilities ──────────────────────────────────────────────────────────────
function esc(v) {
  return String(v ?? '').replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

function formatTime(v) {
  if (!v) return '-';
  const d = new Date(v);
  return isNaN(d) ? String(v) : d.toISOString().replace('T', ' ').slice(11, 19);
}

function formatValue(v) {
  return (v === null || v === undefined || v === '') ? '-' : String(v);
}

function eventTitle(e) {
  return e.flight || e.tail || e.airframe_icao || e.id || 'message';
}

// ── ICAO type helpers ──────────────────────────────────────────────────────
/**
 * Try to resolve the ICAO type from:
 * 1. Local in-memory cache (already fetched this session)
 * 2. event.airframes_api (already stored in the DB by the server)
 * 3. Falls back to remote fetch via /airframes/api/icao/:icao
 */
function getIcaoTypeFromEvent(e) {
  if (!e || !e.airframe_icao) return '';

  const api = e.airframes_api;

  if (api) {
    return (
      api.airframe?.icaoType ||
      api.icaoType ||
      api.aircraft_type ||
      ''
    );
  }

  const cached = icaoTypeCache.get(e.airframe_icao);
  return cached !== undefined ? cached : null;
}

/* async function fetchIcaoTypeRemote(icao) {
  if (!icao || icaoTypeCache.has(icao) || icaoFetching.has(icao)) return;
  icaoFetching.add(icao);
  try {
    const res  = await fetch(`/airframes/api/icao/${encodeURIComponent(icao)}`, { cache: 'no-store' });
    const data = await res.json();
    const type = data?.airframe?.icaoType || data?.icaoType || data?.aircraft_type || '';
    icaoTypeCache.set(icao, type);
  } catch (_) {
    icaoTypeCache.set(icao, '');
  } finally {
    icaoFetching.delete(icao);
  }
} */

/* async function resolveIcaoTypes() {
  // Find events where type is unknown and not already stored in DB
  const needed = events.filter(e => {
    if (!e.airframe_icao) return false;
    if (e.airframes_api)  return false; // server already has it
    return !icaoTypeCache.has(e.airframe_icao) && !icaoFetching.has(e.airframe_icao);
  }).map(e => e.airframe_icao);

  const unique = [...new Set(needed)];
  if (!unique.length) return;

  const BATCH = 6;
  for (let i = 0; i < unique.length; i += BATCH) {
    await Promise.all(unique.slice(i, i + BATCH).map(fetchIcaoTypeRemote));
  }
  render();
} */

function icaoTypeCell(e) {
  const icao = e?.airframe_icao;
  if (!icao) return '<td class="icao-type">-</td>';

  const stored = getIcaoTypeFromEvent(e);
  if (stored === null) {
    // Still unknown — show placeholder, will update after resolveIcaoTypes
    return `<td class="icao-type loading" data-icao="${esc(icao)}">…</td>`;
  }
  return `<td class="icao-type">${esc(stored || '-')}</td>`;
}

// ── Badges ─────────────────────────────────────────────────────────────────
function decodedBadges(e) {
  const parts = [];
  if (e.acars_decoded?.ok) parts.push('<span class="badge badge-ts" title="acars-decoder-typescript">TS</span>');
  if (e.libacars?.ok) parts.push('<span class="badge badge-la" title="libacars">LA</span>');
  return parts.join(' ');
}

function decodeSummaryFromObject(decoded) {
  if (decoded == null) return '';
  if (typeof decoded !== 'object') return String(decoded);

  const preferred = [];
  const keys = ['position', 'latitude', 'longitude', 'altitude', 'flight_level', 'ground_speed', 'track', 'message_type', 'report_type', 'flight_id', 'status'];
  keys.forEach(key => {
    if (decoded[key] !== undefined && decoded[key] !== null && decoded[key] !== '') {
      preferred.push(`${key}=${decoded[key]}`);
    }
  });

  if (preferred.length) return preferred.slice(0, 4).join(' ');

  const entries = Object.entries(decoded).filter(([, value]) => value !== null && value !== undefined).slice(0, 4);
  if (entries.length) {
    return entries.map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : v}`).join(' ');
  }

  return JSON.stringify(decoded);
}

function decodeSummary(e) {
  if (e.libacars?.ok) {
    const summary = decodeSummaryFromObject(e.libacars.decoded);
    return `[LA] ${summary}`.trim();
  }
  if (e.acars_decoded?.ok) {
    const summary = decodeSummaryFromObject(e.acars_decoded.decoded);
    return `[TS] ${summary}`.trim();
  }
  if (e.decoded) {
    const summary = decodeSummaryFromObject(e.decoded);
    return `[DECODED] ${summary}`.trim();
  }
  return 'not decoded';
}

function decodedSummaryCell(e) {
  const summary = decodeSummary(e);
  const badges = decodedBadges(e);
  return `<td class="summary-col">
    <div class="summary-body">${esc(summary)}</div>
    ${badges ? `<div class="summary-badges">${badges}</div>` : ''}
  </td>`;
}

// ── Airframes link ─────────────────────────────────────────────────────────
function icaoLink(e) {
  const icao = e.airframe_icao;
  if (!icao) return '-';
  return `<a href="https://tbgmap.airframes.io/?icao=${esc(icao)}" target="_blank" rel="noopener">${esc(icao)}</a>`;
}

// ── Detail panel ───────────────────────────────────────────────────────────
function detailField(label, value) {
  return `<div class="detail-field"><span>${esc(label)}</span><b>${esc(formatValue(value))}</b></div>`;
}

function openDetails(index) {
  const e = events[index];
  if (!e) return;
  selectedEvent = e;
  const raw = e.raw || e;

  detailTitle.textContent = eventTitle(e);
  detailSubtitle.textContent =
    `${formatValue(e.timestamp)} · ${formatValue(e.station)} · ${formatValue(e.source || e.source_type)}`;

  const icaoType = getIcaoTypeFromEvent(e) || (e.airframe_icao ? 'loading…' : '-');

  detailGrid.innerHTML = [
    detailField('id', e.id),
    detailField('timestamp', e.timestamp),
    detailField('received', e.received_at),
    detailField('station', e.station),
    detailField('country', e.country),
    detailField('flight', e.flight),
    detailField('icao', e.airframe_icao),
    detailField('icaoType', icaoType),
    detailField('tail', e.tail),
    detailField('military', e.military),
    detailField('source', e.source),
    detailField('source type', e.source_type),
    detailField('frequency', e.frequency),
    detailField('label', e.label),
    detailField('mode', e.mode),
    detailField('acars-decoder', e.acars_decoded?.ok ? 'decoded (TS)' : 'not decoded'),
    detailField('libacars', e.libacars?.ok ? 'decoded (LA)' : 'not decoded'),
    detailField('airframes API', e.airframes_api ? 'cached in DB' : 'not fetched'),
  ].join('');

  detailText.textContent = formatValue(e.text);

  acarsDecoderStatus.textContent = e.acars_decoded?.ok ? 'decoded' : 'not decoded';
  acarsDecoderJson.textContent = e.acars_decoded
    ? JSON.stringify(e.acars_decoded, null, 2)
    : 'No acars-decoder result for this message.';

  libacarsStatus.textContent = e.libacars?.ok ? 'decoded' : 'not decoded';
  libacarsJson.textContent = e.libacars
    ? JSON.stringify(e.libacars, null, 2)
    : 'No libacars decode available for this message.';

  detailJson.textContent = JSON.stringify(raw, null, 2);

  decodedSummaryEl.textContent = decodeSummary(e);

  // Airframe API section — prefer stored data
  if (e.airframes_api) {
    airframeApiStatus.textContent = 'cached in DB';
    airframeApiJson.textContent = JSON.stringify(e.airframes_api, null, 2);
    loadAirframeApiBtn.textContent = 'reload';
  } else if (e.airframe_icao) {
    airframeApiStatus.textContent = 'not loaded';
    airframeApiJson.textContent = 'Press load airframe data to query api.airframes.io.';
    loadAirframeApiBtn.textContent = 'load airframe data';
  } else {
    airframeApiStatus.textContent = 'no hex available';
    airframeApiJson.textContent = 'This message does not include an airframe hex.';
  }
  loadAirframeApiBtn.disabled = !e.airframe_icao;

  detailOverlay.classList.add('open');
  detailOverlay.removeAttribute('aria-hidden');
  document.body.style.overflow = 'hidden';
}

function closeDetails() {
  detailOverlay.classList.remove('open');
  detailOverlay.setAttribute('aria-hidden', 'true');
  document.body.style.overflow = '';
}

// ── Airframe API (on-demand from panel) ────────────────────────────────────
async function loadAirframeApi(eventData = selectedEvent) {
  const icao = eventData?.airframe_icao;
  if (!icao) return;
  airframeApiStatus.textContent = 'loading…';
  airframeApiJson.textContent = '';
  loadAirframeApiBtn.disabled = true;
  try {
    const res = await fetch(`/airframes/api/icao/${encodeURIComponent(icao)}`, { cache: 'no-store' });
    const payload = await res.json();
    if (!res.ok) throw new Error(payload.error || `${res.status} ${res.statusText}`);
    const type = payload?.airframe?.icaoType || payload?.icaoType || payload?.aircraft_type || '';
    if (type) { icaoTypeCache.set(icao, type); render(); }
    airframeApiStatus.textContent = 'loaded';
    airframeApiJson.textContent = JSON.stringify(payload, null, 2);
  } catch (err) {
    airframeApiStatus.textContent = 'error';
    airframeApiJson.textContent = String(err.message || err);
  } finally {
    loadAirframeApiBtn.disabled = false;
  }
}

// ── Render table ───────────────────────────────────────────────────────────
function keyText(e) {
  return [e.timestamp, e.airframe_icao, e.flight, e.tail, e.label, decodeSummary(e), e.text].join(' ').toLowerCase();
}

function render() {
  const q = qEl.value.trim().toLowerCase();
  const mil = milEl.value;
  const df = decodedFilterEl.value;

  const filtered = events.filter(e => {
    if (q && !keyText(e).includes(q)) return false;
    if (mil !== 'all' && String(e.military) !== mil) return false;
    if (df === 'acars' && !e.acars_decoded?.ok) return false;
    if (df === 'libacars' && !e.libacars?.ok) return false;
    if (df === 'api' && !e.airframes_api) return false;
    if (df === 'any' && !e.acars_decoded?.ok && !e.libacars?.ok) return false;
    return true;
  });

  rowsEl.innerHTML = filtered.map(e => {
    const i = events.indexOf(e);
    return `<tr class="event-row">
      <td>${esc(formatTime(e.timestamp))}</td>
      <td>${icaoLink(e)}</td>
      ${icaoTypeCell(e)}
      <td>${esc(e.flight)}</td>
      <td>${esc(e.tail)}</td>
      <td>${esc(e.label)}</td>
      <td>${esc(e.mode)}</td>
      <td>${esc(e.source || e.source_type || e.station)}</td>
      ${decodedSummaryCell(e)}
      <td class="text-col">${esc(e.text)}</td>
      <td><button class="detail-btn" type="button" data-index="${i}">details</button></td>
    </tr>
    <tr class="event-meta">
      <td colspan="11">
        <div class="meta-grid">
          <div class="meta-item"><span>station</span><b>${esc(e.station)}</b></div>
          <div class="meta-item"><span>frequency</span><b>${esc(e.frequency)}</b></div>
          <div class="meta-item"><span>country</span><b>${esc(e.country)}</b></div>
          <div class="meta-item"><span>icao type</span><b>${esc(getIcaoTypeFromEvent(e) || (e.airframe_icao ? 'loading…' : '-'))}</b></div>
          <div class="meta-item"><span>military</span><b>${esc(e.military)}</b></div>
          <div class="meta-item"><span>raw label</span><b>${esc(e.label)} / ${esc(e.mode)}</b></div>
        </div>
        <div class="row-summary">${esc(decodeSummary(e))}</div>
      </td>
    </tr>`;
  }).join('');

  const latestTime = events[0]?.timestamp;
  document.getElementById('last').textContent = latestTime ? formatTime(latestTime) : '-';
  document.getElementById('decodedCount').textContent = events.filter(e => e.acars_decoded?.ok).length;
  document.getElementById('libacarsCount').textContent = events.filter(e => e.libacars?.ok).length;
}

// ── Data load ──────────────────────────────────────────────────────────────
async function load() {
  try {
    const res = await fetch(`/airframes/events?limit=${encodeURIComponent(limitEl.value)}`, { cache: 'no-store' });
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    events = await res.json();
    document.getElementById('status').textContent = 'live';
    render();
    //resolveIcaoTypes(); // background, non-blocking
  } catch (err) {
    document.getElementById('status').textContent = 'error';
    console.error(err);
  }
}

// ── Clock ──────────────────────────────────────────────────────────────────
function tick() {
  const now = new Date();
  document.getElementById('clock').textContent =
    'UTC ' + now.toISOString().replace('T', ' ').slice(11, 19) + ' ' + now.toISOString().slice(0, 10);
}

// ── Event listeners ────────────────────────────────────────────────────────
qEl.addEventListener('input', render);
milEl.addEventListener('change', render);
decodedFilterEl.addEventListener('change', render);
limitEl.addEventListener('change', load);

rowsEl.addEventListener('click', ev => {
  const btn = ev.target.closest('[data-index]');
  if (!btn) return;
  openDetails(Number(btn.dataset.index));
});

loadAirframeApiBtn.addEventListener('click', () => loadAirframeApi());

detailOverlay.addEventListener('click', ev => {
  if (ev.target === detailOverlay) closeDetails();
});
document.addEventListener('keydown', ev => {
  if (ev.key === 'Escape') closeDetails();
});

function isFullscreenActive() {
  return !!(
    document.fullscreenElement ||
    document.webkitFullscreenElement ||
    document.mozFullScreenElement ||
    document.msFullscreenElement
  );
}

function updateFullscreenButton() {
  if (!fullscreenBtn) return;
  const active = isFullscreenActive();
  fullscreenBtn.textContent = active ? '⤢' : '⛶';
  fullscreenBtn.title = active ? 'Salir de pantalla completa' : 'Pantalla completa';
}

async function toggleFullscreen() {
  if (!fullscreenBtn) return;
  try {
    if (isFullscreenActive()) {
      if (document.exitFullscreen) await document.exitFullscreen();
      else if (document.webkitExitFullscreen) await document.webkitExitFullscreen();
      else if (document.mozCancelFullScreen) await document.mozCancelFullScreen();
      else if (document.msExitFullscreen) await document.msExitFullscreen();
    } else {
      const el = document.documentElement;
      if (el.requestFullscreen) await el.requestFullscreen();
      else if (el.webkitRequestFullscreen) await el.webkitRequestFullscreen();
      else if (el.mozRequestFullScreen) await el.mozRequestFullScreen();
      else if (el.msRequestFullscreen) await el.msRequestFullscreen();
    }
  } catch (err) {
    console.warn('Fullscreen toggle failed', err);
  }
}

document.addEventListener('fullscreenchange', updateFullscreenButton);
document.addEventListener('webkitfullscreenchange', updateFullscreenButton);
document.addEventListener('mozfullscreenchange', updateFullscreenButton);
document.addEventListener('MSFullscreenChange', updateFullscreenButton);

if (fullscreenBtn) {
  fullscreenBtn.addEventListener('click', toggleFullscreen);
  updateFullscreenButton();
}

// ── Boot ──────────────────────────────────────────────────────────────────
setInterval(load, 3000);
setInterval(tick, 1000);
tick();
load();
