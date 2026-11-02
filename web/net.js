/*
 * XBlast TNT web transport: one Trystero room per page plus two negotiated
 * WebRTC DataChannels per peer.
 *
 * The HTML lobby owns the room (`enter`/`leave`). The engine's socket shim
 * only attaches synthetic file descriptors (`open`/`listen`/`connect`).
 * All stream bytes ride the reliable ordered `xb.ctl` channel, framed as
 * [type, ...payload]; datagrams ride the unreliable unordered `xb.act`
 * channel as raw bytes.
 *
 * This file has no build step: it is loaded as a plain ES module. It imports
 * the vendored Trystero packages and the dependency-free ./turn.js validator.
 */
import { getRelaySockets, joinRoom, selfId } from '@trystero-p2p/nostr';
import { normalizeTurnConfig } from './turn.js';

const APP_ID = 'xblast-tnt-web-v1';
const ROOM_PREFIX = 'xblast-tnt-';

const CTL_LABEL = 'xb.ctl';
const ACT_LABEL = 'xb.act';
const CTL_ID = 42;
const ACT_ID = 43;

const ROLE_HOST = 1;
const ROLE_CLIENT = 2;
const HELLO_VERSION = 2;

const CTL_HELLO = 1;
const CTL_DATA = 2;
const CTL_EOF = 3;
const CTL_CLOSE = 4;
const CTL_STATUS = 5;
const CTL_REJECT = 6;
const CTL_CLAIM = 7;
const CTL_HOST_LEAVING = 8;

const REJECT_FULL = 1;

/* The room is joined before the engine loads, so capacity comes from the
 * generated build-info.js. The fallback is the six-player build. */
const BUILD = globalThis.XB_BUILD || {};
const MAX_PLAYERS = Number.isInteger(BUILD.maxPlayers) && BUILD.maxPlayers > 1
  ? BUILD.maxPlayers
  : 6;
const MAX_CLIENTS = MAX_PLAYERS - 1;
const ROOM_FULL_MESSAGE = `The room is full (${MAX_PLAYERS} players).`;

const STAGE_SETUP = 0;
const STAGE_LISTENING = 1;
const STAGE_MATCH = 2;
const STAGE_IDLE = 3;

const CLIENT_ID_KEY = 'xb:clientId';
const CLIENT_ID_LEN = 16;
const PORT = 16168;
const CTL_BUFFER_LIMIT = 512 * 1024;
const DEFAULT_CONNECT_TIMEOUT_MS = 20000;

const DEFAULT_CLAIM_WINDOW_MS = 500;
const DEFAULT_CLAIM_SETTLE_MS = 500;
const DEFAULT_HOST_READY_TIMEOUT_MS = 30000;

const TURN_SOURCES = new Set(['file', 'endpoint', 'player']);

const config = {
  connectTimeoutMs: DEFAULT_CONNECT_TIMEOUT_MS,
  relayUrls: [],
  turnConfig: [],
  turnSource: null,
  takeover: {
    claimWindowMs: DEFAULT_CLAIM_WINDOW_MS,
    claimSettleMs: DEFAULT_CLAIM_SETTLE_MS,
    hostReadyTimeoutMs: DEFAULT_HOST_READY_TIMEOUT_MS,
  },
};

/* The single active page session; rooms are page-owned, not fd-owned. */
let session = null;

function localRoleOf(role) {
  return role === 'client' ? ROLE_CLIENT : ROLE_HOST;
}

function makeClientId() {
  const bytes = crypto.getRandomValues(new Uint8Array(CLIENT_ID_LEN));
  return Array.from(bytes, (x) => x.toString(16).padStart(2, '0')).join('');
}

/* A tab keeps its id across reloads so a refreshed page can replace the peer
 * the host still has. Private mode may deny storage; a per-page id still
 * works, it just cannot replace the old peer after a refresh. */
function loadClientId() {
  try {
    let id = sessionStorage.getItem(CLIENT_ID_KEY);
    if (!id || !/^[0-9a-f]{32}$/.test(id)) {
      id = makeClientId();
      sessionStorage.setItem(CLIENT_ID_KEY, id);
    }
    return id;
  } catch (e) {
    return makeClientId();
  }
}

function clientIdBytes(hex) {
  const out = new Uint8Array(CLIENT_ID_LEN);
  for (let i = 0; i < CLIENT_ID_LEN; i++) {
    out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  }
  return out;
}

function bytesToClientId(bytes) {
  return Array.from(bytes, (x) => x.toString(16).padStart(2, '0')).join('');
}

function newSession(role, room) {
  return {
    role,
    room,
    localRole: localRoleOf(role),
    clientId: loadClientId(),
    hostStage: role === 'host' ? STAGE_SETUP : 0,
    hostVisible: true,
    hostLost: false,
    hostLostStage: 0,
    newHostId: null,
    newHostStage: 0,
    everSawHost: false,
    hostReadyTimer: null,
    stepDown: false,
    steppedDownBy: null,
    claim: null,
    takeover: null,
    hostWaitFailed: false,
    roomObj: null,
    peers: new Map(),      // peerId -> peer record
    pending: [],           // host: clients with a valid hello, not yet accepted
    fds: new Map(),        // synthetic fd -> fd record
    listenFd: null,
    connectFd: null,
    activeConnectFd: null,
    engineListening: false,
    state: 'joining',
    error: null,            // fatal: the room itself could not be joined
    lastError: null,        // last per-peer/connect error, for display only
    joinErrorPeer: null,
    connectError: null,     // reason the active connect failed or timed out
    connectTimedOut: false,
    rejectReason: null,     // session-wide: the host refused this guest
    recheck: null,
    stats: { ctlTx: 0, ctlRx: 0, actTx: 0, actRx: 0 },
  };
}

function configure(opts) {
  if (!opts || typeof opts !== 'object') return;
  if (Array.isArray(opts.relayUrls)) {
    config.relayUrls = opts.relayUrls.filter(
      (url) => typeof url === 'string' && /^wss?:\/\//i.test(url));
  }
  if (Number.isFinite(opts.connectTimeoutMs) && opts.connectTimeoutMs > 0) {
    config.connectTimeoutMs = opts.connectTimeoutMs;
  }
  if ('turnConfig' in opts) {
    config.turnConfig = normalizeTurnConfig(opts.turnConfig);
    config.turnSource = null;
  }
  if ('turnSource' in opts) {
    config.turnSource = config.turnConfig.length && TURN_SOURCES.has(opts.turnSource)
      ? opts.turnSource
      : null;
  }
  if (!config.turnConfig.length) config.turnSource = null;
}

function ensureFd(s, fd, kind) {
  let f = s.fds.get(fd);
  if (!f) {
    f = {
      fd,
      kind: kind || 'stream',
      role: null,          // 'connect' | 'accept' | null
      peer: null,
      peerId: '',
      listening: false,
      writeClosed: false,
      connectStarted: 0,
      cancelled: false,
    };
    s.fds.set(fd, f);
  } else if (kind) {
    f.kind = kind;
  }
  return f;
}

function removePending(s, peer) {
  if (!s.pending.length) return;
  s.pending = s.pending.filter((id) => id !== peer.id);
}

/* Closed, wrong-role/duplicate and not-yet-helloed peers stay in the map so
 * bound fds can still observe eof; only a usable game link counts as a
 * connected peer. This also stops clients counting each other's ignored
 * channel in the lobby chip. */
function isActivePeer(peer) {
  return Boolean(peer) && !peer.closed && !peer.invalid && !peer.rejected && peer.helloOk;
}

/* Distinct client ids that hold (or are queued for) a player slot. A peer that
 * is rejected never counts, so a repeated hello cannot inflate the room. */
function clientCount(s, exceptPeer) {
  let count = 0;
  if (!s) return count;
  for (const peer of s.peers.values()) {
    if (peer === exceptPeer) continue;
    if (!isActivePeer(peer) || peer.remoteRole !== ROLE_CLIENT) continue;
    if (peer.accepted || s.pending.includes(peer.id)) count++;
  }
  return count;
}

/* The room is at its build cap: tell the guest why and keep it out. */
function rejectClient(s, peer) {
  if (!ctlSend(s, peer, new Uint8Array([CTL_REJECT, REJECT_FULL]))) {
    console.warn('xbnet: could not send the room-full reject to', peer.id);
  }
  peer.rejected = true;
  removePending(s, peer);
}

function activePeers(s) {
  const out = [];
  if (!s) return out;
  for (const peer of s.peers.values()) {
    if (isActivePeer(peer)) out.push(peer);
  }
  return out;
}

function ctlSend(s, peer, bytes) {
  if (!peer.ctl || peer.ctl.readyState !== 'open') return false;
  try {
    peer.ctl.send(bytes);
    s.stats.ctlTx += bytes.length;
    return true;
  } catch (e) {
    console.warn('xbnet: ctl send failed', e);
    return false;
  }
}

function findHostPeer(s) {
  if (s.newHostId) {
    const preferred = s.peers.get(s.newHostId);
    if (isActivePeer(preferred) && preferred.helloOk && preferred.remoteRole === ROLE_HOST) {
      return preferred;
    }
  }
  for (const peer of s.peers.values()) {
    if (isActivePeer(peer) && peer.helloOk && peer.remoteRole === ROLE_HOST) return peer;
  }
  return null;
}

function bindConnectFds(s, peer) {
  for (const f of s.fds.values()) {
    if (f.kind === 'stream' && f.role === 'connect' && !f.peer) {
      f.peer = peer;
      f.peerId = peer.id;
    }
  }
}

function clearHelloTimers(peer) {
  if (!peer.helloTimers) return;
  for (const timer of peer.helloTimers) clearTimeout(timer);
  peer.helloTimers = null;
}

function setHostStage(s, stage) {
  if (!s || s.role !== 'host' || s.hostStage === stage) return;
  s.hostStage = stage;
  sendStatus(s);
}

function sendStatus(s) {
  if (!s || s.role !== 'host' || session !== s) return;
  const frame = new Uint8Array([CTL_STATUS, s.hostStage, s.hostVisible ? 1 : 0]);
  for (const peer of activePeers(s)) {
    if (peer.remoteRole === ROLE_CLIENT && peer.ctlOpen && !peer.closed) {
      ctlSend(s, peer, frame);
    }
  }
}

function sendHostLeaving(s) {
  if (!s || s.role !== 'host') return;
  const frame = new Uint8Array([CTL_HOST_LEAVING, s.hostStage]);
  for (const peer of activePeers(s)) {
    // Only this host's accepted clients. In a two-host room the other host's
    // guests are peers here too, but their real host is still alive.
    if (peer.accepted && peer.remoteRole === ROLE_CLIENT &&
        peer.ctlOpen && !peer.closed) {
      ctlSend(s, peer, frame);
    }
  }
}

function broadcastHello(s) {
  for (const peer of s.peers.values()) {
    if (peer.helloOk && !peer.closed && !peer.invalid) sendHello(s, peer);
  }
}

function noteHostLost(s, peer) {
  if (!s || s.role !== 'client' || !peer || peer.remoteRole !== ROLE_HOST) return;
  if (!s.everSawHost) return;
  const other = findHostPeer(s);
  if (other && other.id !== peer.id) {
    // The host we were following stepped down; another host is still here.
    s.newHostId = other.id;
    s.newHostStage = other.hostStage;
    s.hostLost = false;
    clearClaimTimers(s);
    s.claim = null;
    s.takeover = null;
    s.hostWaitFailed = false;
    return;
  }
  if (other) return;
  s.hostLost = true;
  s.hostLostStage = peer.hostStage || 0;
  s.newHostId = null;
  s.newHostStage = 0;
  clearTimeout(s.hostReadyTimer);
  s.hostReadyTimer = null;
  if (s.claim && (s.claim.state === 'want' || s.claim.state === 'won')) {
    // Keep an in-flight claim: a late peer-leave for the old host must not
    // cancel the takeover the user just started.
    return;
  }
  clearClaimTimers(s);
  s.claim = null;
  s.takeover = null;
  s.hostWaitFailed = false;
}

function claimFrame(state, clientId) {
  const frame = new Uint8Array(4 + CLIENT_ID_LEN);
  frame[0] = CTL_CLAIM;
  frame[1] = state;
  frame[2] = CLIENT_ID_LEN;
  frame.set(clientIdBytes(clientId), 3);
  return frame;
}

function broadcastCtl(s, bytes) {
  for (const peer of s.peers.values()) {
    if (peer.ctl && peer.ctl.readyState === 'open' && !peer.closed) {
      ctlSend(s, peer, bytes);
    }
  }
}

function clearClaimTimers(s) {
  if (!s) return;
  if (s.claim) clearTimeout(s.claim.timer);
  clearTimeout(s.hostReadyTimer);
  s.hostReadyTimer = null;
  if (s.claim) s.claim.timer = null;
}

function startHostReadyTimer(s) {
  if (!s) return;
  clearTimeout(s.hostReadyTimer);
  s.hostReadyTimer = setTimeout(() => {
    if (session !== s) return;
    if (s.newHostId && s.newHostStage >= STAGE_LISTENING) return;
    s.hostWaitFailed = true;
    if (s.claim) {
      s.claim.state = 'failed';
      s.claim.winner = null;
      s.claim.self = false;
    }
    s.takeover = null;
  }, config.takeover.hostReadyTimeoutMs);
}

function noteHostReady(s, peer) {
  if (!s) return;
  if (peer && s.newHostId && peer.id !== s.newHostId) return;
  clearTimeout(s.hostReadyTimer);
  s.hostReadyTimer = null;
  s.hostWaitFailed = false;
}

function finishClaimWindow(s) {
  if (!s || !s.claim || s.claim.state !== 'want') return;
  s.claim.timer = null;
  const entries = Array.from(s.claim.entries.keys()).sort();
  const winner = entries[0] || s.clientId;
  s.claim.winner = winner;
  s.claim.self = winner === s.clientId;
  s.claim.state = 'won';
  if (s.claim.self) {
    broadcastCtl(s, claimFrame(2, s.clientId));
    startHostReadyTimer(s);
    setTimeout(() => {
      if (session === s && s.claim && s.claim.state === 'won' && s.claim.self) {
        s.takeover = 'host';
      }
    }, config.takeover.claimSettleMs);
  } else {
    s.takeover = 'join';
    startHostReadyTimer(s);
  }
}

function handleClaim(s, bytes) {
  if (!s || s.role !== 'client') return;
  if (findHostPeer(s) && !s.hostWaitFailed && !s.claim) return;
  if (!bytes || bytes.length < 4 + CLIENT_ID_LEN) return;
  if (bytes[2] !== CLIENT_ID_LEN) return;
  const state = bytes[1];
  const id = bytesToClientId(bytes.subarray(3, 3 + CLIENT_ID_LEN));
  if (state === 1) {
    if (!s.claim) return;
    s.claim.entries.set(id, Date.now());
    if (s.claim.state === 'won' && id < s.claim.winner) {
      s.claim.winner = id;
      s.claim.self = id === s.clientId;
      s.takeover = s.claim.self ? 'host' : 'join';
      if (s.claim.self) {
        broadcastCtl(s, claimFrame(2, s.clientId));
        startHostReadyTimer(s);
      }
    }
    return;
  }
  if (state === 2) {
    if (!s.claim) {
      s.claim = {
        state: 'won', winner: id, self: false, entries: new Map(), timer: null,
      };
    } else if (!s.claim.winner || id < s.claim.winner) {
      s.claim.winner = id;
    } else if (s.claim.winner !== id) {
      return;
    }
    s.claim.self = s.claim.winner === s.clientId;
    s.claim.state = 'won';
    clearTimeout(s.claim.timer);
    s.claim.timer = null;
    s.takeover = s.claim.self ? 'host' : 'join';
    startHostReadyTimer(s);
    return;
  }
  if (state === 3 && s.claim) {
    s.claim.entries.delete(id);
    if (s.claim.winner === id) {
      s.claim.winner = null;
      s.claim.self = false;
      s.takeover = null;
      s.claim.state = s.claim.timer ? 'want' : 'failed';
    }
  }
}

function claimHost() {
  const s = session;
  if (!s || s.role !== 'client') return false;
  const host = findHostPeer(s);
  // A host in setup after a failed takeover may be superseded; a listening
  // host is authoritative and must not be claimed.
  if (host && !(s.hostWaitFailed && host.hostStage === STAGE_SETUP)) return false;
  if (!s.hostLost && !s.hostWaitFailed) return false;
  if (s.claim && (s.claim.winner || s.claim.timer)) return false;
  if (s.claim) clearClaimTimers(s);
  s.hostWaitFailed = false;
  s.claim = {
    state: 'want',
    winner: null,
    self: true,
    entries: new Map([[s.clientId, Date.now()]]),
    timer: null,
  };
  broadcastCtl(s, claimFrame(1, s.clientId));
  s.claim.timer = setTimeout(() => finishClaimWindow(s), config.takeover.claimWindowMs);
  return true;
}

function cancelClaim() {
  const s = session;
  if (!s || !s.claim) return false;
  broadcastCtl(s, claimFrame(3, s.clientId));
  clearClaimTimers(s);
  s.claim = null;
  s.takeover = null;
  s.hostWaitFailed = false;
  return true;
}

function setTakeoverTimings(opts) {
  if (!opts || typeof opts !== 'object') return;
  for (const key of ['claimWindowMs', 'claimSettleMs', 'hostReadyTimeoutMs']) {
    if (Number.isFinite(opts[key]) && opts[key] > 0) config.takeover[key] = opts[key];
  }
}

/* The engine closes the listen socket at match start and on cancel. Accepted
 * peers staying open means a match; no accepted peers means idle. */
function closeListenStage(s) {
  if (!s || s.role !== 'host') return;
  const acceptedAlive = activePeers(s).some((peer) => peer.accepted && !peer.closed);
  setHostStage(s, acceptedAlive ? STAGE_MATCH : STAGE_IDLE);
}

function refreshHostStage(s) {
  if (!s || s.role !== 'host' || s.engineListening) return;
  if (s.hostStage !== STAGE_MATCH) return;
  const acceptedAlive = activePeers(s).some((peer) => peer.accepted && !peer.closed);
  if (!acceptedAlive) setHostStage(s, STAGE_IDLE);
}

/* A refreshed guest keeps its tab id; close the old peer so the engine frees
 * the stale client slot and the new peer can be accepted. */
function replaceClientPeer(s, peer, clientId) {
  if (!s || s.role !== 'host' || !clientId) return;
  for (const other of s.peers.values()) {
    if (other === peer || other.clientId !== clientId || other.closed) continue;
    closePeerChannels(s, other, true);
    removePending(s, other);
    other.replacedBy = peer.id;
  }
}

function sendHello(s, peer) {
  if (!peer || peer.closed || peer.invalid) return false;
  const frame = new Uint8Array(5 + CLIENT_ID_LEN);
  frame[0] = CTL_HELLO;
  frame[1] = HELLO_VERSION;
  frame[2] = s.localRole;
  frame[3] = CLIENT_ID_LEN;
  frame.set(clientIdBytes(s.clientId), 4);
  frame[4 + CLIENT_ID_LEN] = s.role === 'host' ? s.hostStage : 0;
  return ctlSend(s, peer, frame);
}

function handleHello(s, peer, bytes) {
  // A peer that was refused stays out until it leaves; repeated hellos are
  // retransmits, not a new request.
  if (peer.rejected) return;
  const version = bytes[1];
  const remoteRole = bytes[2];
  const idLen = bytes[3];
  const validRole = remoteRole === ROLE_HOST || remoteRole === ROLE_CLIENT;
  if (s.role === 'host' && remoteRole === ROLE_HOST &&
      version === HELLO_VERSION && idLen === CLIENT_ID_LEN &&
      bytes.length >= 4 + idLen + 1) {
    const remoteClientId = bytesToClientId(bytes.subarray(4, 4 + idLen));
    const remoteWins = remoteClientId < s.clientId ||
      (remoteClientId === s.clientId && peer.id < selfId);
    peer.invalid = true;
    clearHelloTimers(peer);
    if (remoteWins) {
      s.stepDown = true;
      s.steppedDownBy = remoteClientId;
      s.hostStage = STAGE_IDLE;
      s.engineListening = false;
      sendHostLeaving(s);
      for (const other of s.peers.values()) {
        if (other !== peer) closePeerChannels(s, other, true);
      }
    } else {
      broadcastHello(s);
    }
    return;
  }
  if (version !== HELLO_VERSION || !validRole || remoteRole === s.localRole ||
      idLen !== CLIENT_ID_LEN || bytes.length < 4 + idLen + 1) {
    // Another host/client in the same room or a stale build is ignored; its
    // channels are not used for engine traffic.
    peer.invalid = true;
    clearHelloTimers(peer);
    return;
  }
  const remoteClientId = bytesToClientId(bytes.subarray(4, 4 + idLen));
  const remoteStage = bytes[4 + idLen];
  const firstValid = !peer.helloOk;
  peer.version = version;
  peer.remoteRole = remoteRole;
  peer.clientId = remoteClientId;
  peer.hostStage = remoteRole === ROLE_HOST ? remoteStage : 0;
  peer.helloOk = true;
  clearHelloTimers(peer);
  if (peer.accepted) {
    // An accepted peer only retransmits its hello; re-running admission would
    // let a lost echo plus a match start evict a guest that is playing.
    return;
  }
  // A valid peer makes an older handshake failure stale.
  s.lastError = null;
  s.joinErrorPeer = null;
  if (firstValid) {
    // The peer's channel may have existed before ours did, so its first hello
    // can be lost. Echo ours first: a guest must read the stage before any
    // reject frame that follows on the same ordered channel.
    sendHello(s, peer);
    // A joiner needs the current visibility too, not just the stage.
    if (s.role === 'host') sendStatus(s);
  }
  if (s.role === 'host' && remoteRole === ROLE_CLIENT) {
    replaceClientPeer(s, peer, remoteClientId);
    if (s.hostStage === STAGE_MATCH || s.hostStage === STAGE_IDLE) {
      // Not accepting: the hello's stage already tells the guest why, so no
      // reject frame, and the peer must not look connected or get a slot.
      peer.rejected = true;
      removePending(s, peer);
    } else if (clientCount(s, peer) >= MAX_CLIENTS) {
      rejectClient(s, peer);
    } else if (!peer.accepted && !s.pending.includes(peer.id)) {
      s.pending.push(peer.id);
    }
  } else if (s.role === 'client' && remoteRole === ROLE_HOST) {
    const wasLost = s.hostLost || s.hostWaitFailed;
    s.newHostId = peer.id;
    s.newHostStage = remoteStage;
    s.everSawHost = true;
    s.hostLost = false;
    if (s.claim && s.claim.self && s.claim.state === 'won') {
      // Another host appeared before this client reloaded. Stand down.
      clearClaimTimers(s);
      s.claim = null;
      s.takeover = null;
    }
    if (remoteStage >= STAGE_LISTENING) noteHostReady(s, peer);
    else if (wasLost) startHostReadyTimer(s);
    bindConnectFds(s, peer);
  }
}

function handleCtlMessage(s, peer, data) {
  let bytes;
  if (data instanceof ArrayBuffer) bytes = new Uint8Array(data);
  else if (ArrayBuffer.isView(data)) bytes = new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
  else return;
  if (!bytes.length) return;
  s.stats.ctlRx += bytes.length;

  switch (bytes[0]) {
    case CTL_HELLO:
      handleHello(s, peer, bytes);
      break;
    case CTL_DATA: {
      if (peer.helloOk && !peer.invalid && bytes.length > 1) {
        // An empty payload is not EOF: the C shim reserves 0 for end of
        // file, so a zero-length frame would look like a half-close.
        peer.ctlQueue.push(bytes.slice(1));
      }
      break;
    }
    case CTL_EOF:
      peer.eof = true;
      break;
    case CTL_CLOSE:
      peer.eof = true;
      peer.closed = true;
      peer.ctlOpen = false;
      clearHelloTimers(peer);
      removePending(s, peer);
      refreshHostStage(s);
      break;
    case CTL_STATUS:
      if (peer.remoteRole === ROLE_HOST && bytes.length >= 2) {
        peer.hostStage = bytes[1];
        peer.hostVisible = bytes.length >= 3 ? bytes[2] === 1 : true;
        if (s.role === 'client' && peer.id === s.newHostId) {
          s.newHostStage = peer.hostStage;
          if (peer.hostStage === STAGE_LISTENING) noteHostReady(s, peer);
        }
      }
      break;
    case CTL_HOST_LEAVING:
      if (peer.remoteRole === ROLE_HOST && bytes.length >= 2 &&
          (!s.newHostId || peer.id === s.newHostId)) {
        s.hostLost = true;
        s.hostLostStage = bytes[1];
        s.newHostId = null;
        s.newHostStage = 0;
      }
      break;
    case CTL_CLAIM:
      if (s.role === 'client') handleClaim(s, bytes);
      break;
    case CTL_REJECT:
      /* Only the host refuses; the hello precedes it on the same ordered
       * channel, so remoteRole is known by the time this arrives. */
      if (peer.remoteRole === ROLE_HOST && bytes.length >= 2 && bytes[1] === REJECT_FULL) {
        peer.rejected = true;
        /* Session-wide: the reject usually lands while the engine is still
         * loading, before the player presses Connect. */
        s.rejectReason = ROOM_FULL_MESSAGE;
        s.connectError = ROOM_FULL_MESSAGE;
        s.lastError = s.connectError;
        // Closing the stream makes the engine leave the wait screen instead of
        // waiting for config that will never come.
        closePeerChannels(s, peer, true);
      }
      break;
    default:
      break;
  }
}

function handleActMessage(s, peer, data) {
  let bytes;
  if (data instanceof ArrayBuffer) bytes = new Uint8Array(data);
  else if (ArrayBuffer.isView(data)) bytes = new Uint8Array(data.buffer, data.byteOffset, data.byteLength);
  else return;
  // Queue even before the hello is processed: xb.act is a separate channel
  // (unordered, unreliable) and a datagram can be delivered while hello is
  // still in flight.
  peer.actQueue.push(bytes.slice());
  s.stats.actRx += bytes.length;
}

function setupPeer(s, peerId, pc) {
  if (!pc) return false;
  const existing = s.peers.get(peerId);
  if (existing) return true;

  let ctl;
  let act;
  try {
    ctl = pc.createDataChannel(CTL_LABEL, { negotiated: true, id: CTL_ID, ordered: true });
    act = pc.createDataChannel(ACT_LABEL, {
      negotiated: true,
      id: ACT_ID,
      ordered: false,
      maxRetransmits: 0,
    });
  } catch (e) {
    console.warn('xbnet: could not create channels for', peerId, e);
    return false;
  }

  const peer = {
    id: peerId,
    pc,
    ctl,
    act,
    ctlOpen: false,
    actOpen: false,
    helloOk: false,
    invalid: false,
    rejected: false,
    version: 0,
    remoteRole: 0,
    clientId: null,
    hostStage: 0,
    hostVisible: true,
    ctlQueue: [],
    actQueue: [],
    eof: false,
    closed: false,
    accepted: false,
  };
  s.peers.set(peerId, peer);

  ctl.binaryType = 'arraybuffer';
  act.binaryType = 'arraybuffer';
  ctl.bufferedAmountLowThreshold = 65535;

  ctl.onopen = () => {
    if (peer.closed) return;
    peer.ctlOpen = true;
    sendHello(s, peer);
    // Negotiated channels have no DCEP open handshake: if this side opens
    // first, the first hello can arrive before the remote has a local channel
    // to receive it. Retry briefly until a valid hello is seen.
    peer.helloTimers = [250, 750, 1500].map((delay) => setTimeout(() => {
      if (!peer.helloOk && !peer.closed) sendHello(s, peer);
    }, delay));
  };
  ctl.onmessage = (event) => handleCtlMessage(s, peer, event.data);
  ctl.onclose = () => {
    peer.ctlOpen = false;
    peer.eof = true;
    peer.closed = true;
    clearHelloTimers(peer);
    removePending(s, peer);
    refreshHostStage(s);
    noteHostLost(s, peer);
  };
  ctl.onerror = (event) => {
    console.warn('xbnet: ctl channel error for', peerId, event);
  };

  act.onopen = () => {
    if (peer.closed) return;
    peer.actOpen = true;
  };
  act.onmessage = (event) => handleActMessage(s, peer, event.data);
  act.onclose = () => {
    peer.actOpen = false;
  };
  act.onerror = (event) => {
    console.warn('xbnet: act channel error for', peerId, event);
  };

  return true;
}

function setupPeerFromRoom(s, peerId) {
  if (!s.roomObj) return;
  let peers;
  try {
    peers = s.roomObj.getPeers();
  } catch (e) {
    return;
  }
  if (peers && peers[peerId]) setupPeer(s, peerId, peers[peerId]);
}

function attachExistingPeers(s) {
  if (!s.roomObj) return;
  let peers;
  try {
    peers = s.roomObj.getPeers();
  } catch (e) {
    return;
  }
  for (const id of Object.keys(peers || {})) setupPeer(s, id, peers[id]);
}

function handlePeerLeave(s, peerId) {
  const peer = s.peers.get(peerId);
  if (!peer) return;
  if (s.joinErrorPeer === peerId) {
    s.lastError = null;
    s.joinErrorPeer = null;
  }
  clearHelloTimers(peer);
  peer.closed = true;
  peer.eof = true;
  peer.ctlOpen = false;
  peer.actOpen = false;
  removePending(s, peer);
  // Fds keep a direct peer reference, so bound sockets still observe eof.
  s.peers.delete(peerId);
  refreshHostStage(s);
  noteHostLost(s, peer);
}

function enter(role, room) {
  leave();
  const s = newSession(role === 'client' ? 'client' : 'host', room || '');
  session = s;
  try {
    const roomConfig = { appId: APP_ID };
    if (config.relayUrls.length) {
      roomConfig.relayConfig = { urls: config.relayUrls, redundancy: 1 };
    }
    if (config.turnConfig.length) roomConfig.turnConfig = config.turnConfig;
    const roomObj = joinRoom(
      roomConfig,
      ROOM_PREFIX + s.room,
      {
        onJoinError: (err) => {
          if (session !== s) return;
          const text = err && err.error ? String(err.error) : String(err);
          const peerId = err && err.peerId ? String(err.peerId) : '';
          // Trystero reports handshake/SDP failures per peer. One stale or
          // unreachable peer must not poison the session: keep the message
          // for display and keep waiting for the actual host.
          if (s.role === 'client' && peerId) {
            const host = findHostPeer(s);
            if (host && peerId !== host.id) return;
          }
          s.lastError = text;
          s.joinErrorPeer = peerId;
        },
      },
    );
    s.roomObj = roomObj;
    s.state = 'joined';
    roomObj.onPeerJoin = (id) => {
      if (session === s) setupPeerFromRoom(s, id);
    };
    roomObj.onPeerLeave = (id) => {
      if (session === s) handlePeerLeave(s, id);
    };
    attachExistingPeers(s);
    // onPeerJoin already replays existing peers, but a second sweep covers
    // peers that finish Trystero's handshake while joinRoom() is returning.
    s.recheck = setTimeout(() => {
      s.recheck = null;
      if (session === s) attachExistingPeers(s);
    }, 500);
  } catch (e) {
    s.error = e && e.message ? e.message : String(e);
    s.state = 'error';
    console.warn('xbnet: joinRoom failed', e);
  }
}

function leave() {
  const s = session;
  if (!s) return;
  sendHostLeaving(s);
  clearClaimTimers(s);
  session = null;
  if (s.recheck) {
    clearTimeout(s.recheck);
    s.recheck = null;
  }
  for (const peer of s.peers.values()) closePeerChannels(s, peer, true);
  s.peers.clear();
  s.pending.length = 0;
  s.fds.clear();
  s.state = 'left';
  const roomObj = s.roomObj;
  s.roomObj = null;
  if (roomObj) {
    try {
      Promise.resolve(roomObj.leave()).catch(() => {});
    } catch (e) {
      // already left
    }
  }
}

function open(fd, kind) {
  const s = session;
  if (!s) return;
  const k = kind === 'dgram' ? 'dgram' : 'stream';
  s.fds.set(fd, {
    fd,
    kind: k,
    role: null,
    peer: null,
    peerId: '',
    listening: false,
    writeClosed: false,
    connectStarted: 0,
    cancelled: false,
  });
}

function listen(fd, room) {
  if (!session) {
    if (!room) return false;
    enter('host', room);
  }
  const s = session;
  if (!s || s.role !== 'host' || s.stepDown) return false;
  const f = ensureFd(s, fd, 'stream');
  f.listening = true;
  f.role = 'listen';
  s.listenFd = fd;
  s.engineListening = true;
  setHostStage(s, STAGE_LISTENING);
  return true;
}

function connect(fd, room) {
  if (!session) {
    if (!room) return;
    enter('client', room);
  }
  const s = session;
  if (!s || s.role !== 'client') return;
  // A new attempt starts clean: a stale per-peer error or a previous timeout
  // must not make Connect fail immediately.
  s.error = null;
  s.lastError = null;
  s.joinErrorPeer = null;
  s.connectError = null;
  s.connectTimedOut = false;
  const f = ensureFd(s, fd, 'stream');
  f.kind = 'stream';
  f.role = 'connect';
  f.connectStarted = Date.now();
  f.cancelled = false;
  s.connectFd = fd;
  s.activeConnectFd = fd;
  const host = findHostPeer(s);
  if (host) {
    f.peer = host;
    f.peerId = host.id;
  }
}

function connectState(fd) {
  const s = session;
  if (!s) return -1;
  const f = s.fds.get(fd);
  // A missing fd is a failure, not "still connecting": the engine menu must
  // not spin forever if the session/fd bookkeeping regresses.
  if (!f || f.kind !== 'stream') return -1;
  if (f.cancelled) {
    s.connectError = s.connectError || 'Connect cancelled.';
    return -1;
  }
  if (s.error) return -1;
  /* The host refused this guest. The frame usually arrives before the engine
   * calls connect(), so the reason outlives the peer's channels. */
  if (s.rejectReason) {
    s.connectError = s.rejectReason;
    s.lastError = s.connectError;
    return -1;
  }
  let peer = f.peer;
  if (!peer) {
    peer = findHostPeer(s);
    if (peer) {
      f.peer = peer;
      f.peerId = peer.id;
    }
  }
  if (peer && peer.helloOk && peer.remoteRole === ROLE_HOST) {
    if (peer.hostStage === STAGE_MATCH) {
      s.connectError = 'The host is already in a match.';
      s.lastError = s.connectError;
      return -1;
    }
    if (peer.hostStage === STAGE_IDLE) {
      s.connectError = 'The host is not accepting players.';
      s.lastError = s.connectError;
      return -1;
    }
    if (peer.rejected) {
      s.connectError = ROOM_FULL_MESSAGE;
      s.lastError = s.connectError;
      return -1;
    }
    if (peer.ctlOpen && !peer.closed) return 1;
  }
  if (f.connectStarted && Date.now() - f.connectStarted > config.connectTimeoutMs) {
    s.connectTimedOut = true;
    s.connectError = `Timed out connecting to room ${s.room}.`;
    s.lastError = s.connectError;
    return -1;
  }
  return 0;
}

function cancelConnect(fd) {
  const s = session;
  if (!s) return;
  const target = fd === undefined || fd === null
    ? (s.activeConnectFd !== null ? s.activeConnectFd : s.connectFd)
    : fd;
  if (target === null || target === undefined) return;
  const f = s.fds.get(target);
  if (f) {
    f.cancelled = true;
    s.connectError = 'Connect cancelled.';
    s.connectTimedOut = false;
    s.lastError = s.connectError;
  }
}

function accept(listenFd, newFd) {
  const s = session;
  if (!s || s.role !== 'host' || s.stepDown) return null;
  const lf = s.fds.get(listenFd);
  if (!lf || !lf.listening) return null;
  while (s.pending.length) {
    const id = s.pending.shift();
    const peer = s.peers.get(id);
    if (!peer || peer.closed || !peer.helloOk || peer.invalid || peer.rejected ||
        peer.remoteRole !== ROLE_CLIENT || peer.accepted) {
      continue;
    }
    peer.accepted = true;
    const f = ensureFd(s, newFd, 'stream');
    f.kind = 'stream';
    f.role = 'accept';
    f.peer = peer;
    f.peerId = id;
    return id;
  }
  return null;
}

function attachPeer(fd, peerName) {
  const s = session;
  if (!s) return false;
  const peer = s.peers.get(peerName);
  if (!peer || peer.closed || !peer.helloOk) return false;
  const f = ensureFd(s, fd, 'dgram');
  f.kind = 'dgram';
  f.peer = peer;
  f.peerId = peerName;
  return true;
}

function send(fd, bytes) {
  const s = session;
  if (!s) return -2;
  const f = s.fds.get(fd);
  if (!f) return -2;
  const peer = f.peer;
  if (!peer) return -1;
  if (peer.closed) return -2;

  let data;
  try {
    data = bytes instanceof Uint8Array ? bytes.slice() : new Uint8Array(bytes);
  } catch (e) {
    return -2;
  }

  if (f.kind === 'dgram') {
    if (!peer.actOpen || peer.closed || !peer.act || peer.act.readyState !== 'open') return -1;
    try {
      peer.act.send(data);
      s.stats.actTx += data.length;
      return data.length;
    } catch (e) {
      return -2;
    }
  }

  if (f.writeClosed) return -2;
  if (!peer.ctlOpen || peer.closed || !peer.ctl || peer.ctl.readyState !== 'open') return -1;
  if (peer.ctl.bufferedAmount > CTL_BUFFER_LIMIT) return -1;

  const frame = new Uint8Array(data.length + 1);
  frame[0] = CTL_DATA;
  frame.set(data, 1);
  try {
    peer.ctl.send(frame);
    s.stats.ctlTx += frame.length;
    return data.length;
  } catch (e) {
    return -2;
  }
}

function recv(fd, max) {
  const s = session;
  if (!s) return { kind: 'block' };
  const f = s.fds.get(fd);
  if (!f) return { kind: 'block' };
  const limit = Math.max(0, Math.floor(max));
  const peer = f.peer;
  if (limit === 0) return { kind: 'block' };

  if (f.kind === 'dgram') {
    if (!peer || !peer.actQueue.length) return { kind: 'block' };
    const message = peer.actQueue.shift();
    return { kind: 'data', data: message.length > limit ? message.slice(0, limit) : message };
  }

  if (peer && peer.ctlQueue.length) {
    let total = 0;
    for (const chunk of peer.ctlQueue) {
      if (total >= limit) break;
      total += chunk.length;
    }
    const out = new Uint8Array(Math.min(total, limit));
    let offset = 0;
    while (peer.ctlQueue.length && offset < limit) {
      const chunk = peer.ctlQueue[0];
      const take = Math.min(chunk.length, limit - offset);
      out.set(chunk.subarray(0, take), offset);
      offset += take;
      if (take === chunk.length) peer.ctlQueue.shift();
      else peer.ctlQueue[0] = chunk.subarray(take);
    }
    // Empty chunks are dropped on receipt, but never surface a zero-length
    // read: the C shim treats 0 as end of file.
    if (!out.length) return { kind: 'block' };
    return { kind: 'data', data: out };
  }

  if (peer && (peer.eof || peer.closed)) return { kind: 'eof' };
  return { kind: 'block' };
}

function readable(fd) {
  const s = session;
  if (!s) return false;
  const f = s.fds.get(fd);
  if (!f) return false;
  if (f.listening) return s.pending.length > 0;
  const peer = f.peer;
  if (!peer) return false;
  if (f.kind === 'dgram') return peer.actQueue.length > 0;
  return peer.ctlQueue.length > 0 || peer.eof || peer.closed;
}

function writable(fd) {
  const s = session;
  if (!s) return false;
  const f = s.fds.get(fd);
  if (!f || f.listening) return false;
  const peer = f.peer;
  if (!peer || peer.closed) return false;
  if (f.kind === 'dgram') return peer.actOpen && !!peer.act && peer.act.readyState === 'open';
  if (f.writeClosed || !peer.ctlOpen || !peer.ctl || peer.ctl.readyState !== 'open') return false;
  return peer.ctl.bufferedAmount <= CTL_BUFFER_LIMIT;
}

function shutdownWrite(fd) {
  const s = session;
  if (!s) return;
  const f = s.fds.get(fd);
  if (!f || f.kind !== 'stream') return;
  f.writeClosed = true;
  const peer = f.peer;
  if (!peer || peer.closed || !peer.ctlOpen) return;
  ctlSend(s, peer, new Uint8Array([CTL_EOF]));
}

function closePeerChannels(s, peer, sendClose) {
  if (!peer) return;
  clearHelloTimers(peer);
  const wasClosed = peer.closed;
  peer.closed = true;
  peer.eof = true;
  peer.ctlOpen = false;
  peer.actOpen = false;
  removePending(s, peer);
  if (wasClosed) return;
  if (sendClose && peer.ctl && peer.ctl.readyState === 'open') {
    try {
      peer.ctl.send(new Uint8Array([CTL_CLOSE]));
      s.stats.ctlTx += 1;
    } catch (e) {
      // The channel may close underneath us; the remote still sees onclose.
    }
  }
  try {
    if (peer.ctl) peer.ctl.close();
  } catch (e) {
    // already closed
  }
  try {
    if (peer.act) peer.act.close();
  } catch (e) {
    // already closed
  }
  refreshHostStage(s);
}

function close(fd) {
  const s = session;
  if (!s) return;
  const f = s.fds.get(fd);
  if (!f) return;
  s.fds.delete(fd);

  if (s.listenFd === fd) {
    // Stop accepting. Never accepted peers are dropped; accepted peers and
    // the room itself stay alive (Server_StopListen at match start).
    s.listenFd = null;
    s.engineListening = false;
    const pending = s.pending;
    s.pending = [];
    for (const id of pending) {
      const peer = s.peers.get(id);
      if (peer && !peer.accepted) closePeerChannels(s, peer, true);
    }
    closeListenStage(s);
    return;
  }

  if (s.connectFd === fd) s.connectFd = null;
  if (s.activeConnectFd === fd) s.activeConnectFd = null;

  if (f.kind === 'dgram') {
    // Unbind only; channels are shared with the session's other fds.
    f.peer = null;
    f.peerId = '';
    return;
  }

  if (f.kind === 'stream' && f.peer) {
    // Guest closing its stream, or the host closing one accepted stream:
    // close only that peer's channels, never the room or other peers.
    closePeerChannels(s, f.peer, true);
  }
}

function localName(fd) {
  return selfId;
}

function remoteName(fd) {
  const s = session;
  if (!s) return '';
  const f = s.fds.get(fd);
  return f && f.peer ? f.peer.id : (f ? f.peerId : '');
}

function localPort(fd) {
  return PORT;
}

function remotePort(fd) {
  return PORT;
}

function relayReady() {
  try {
    const sockets = getRelaySockets();
    return Object.values(sockets || {}).some((socket) => socket && socket.readyState === 1);
  } catch (e) {
    return false;
  }
}

function status() {
  const s = session;
  const hostPeer = s ? findHostPeer(s) : null;
  return {
    role: s ? s.role : null,
    room: s ? s.room : null,
    state: s ? s.state : 'idle',
    peers: s ? activePeers(s).length : 0,
    selfId,
    clientId: s ? s.clientId : null,
    /* The host's own stage, or the stage its hello told a guest. */
    hostStage: s ? (s.role === 'host' ? s.hostStage : (hostPeer ? hostPeer.hostStage : 0)) : null,
    hostVisible: s ? (s.role === 'host' ? s.hostVisible : (hostPeer ? hostPeer.hostVisible : true)) : null,
    hostLost: s ? s.hostLost : false,
    hostLostStage: s ? s.hostLostStage : 0,
    newHostId: s ? s.newHostId : null,
    newHostStage: s ? s.newHostStage : 0,
    stepDown: s ? s.stepDown : false,
    steppedDownBy: s ? s.steppedDownBy : null,
    claim: s && s.claim
      ? { state: s.claim.state, winner: s.claim.winner, self: s.claim.self }
      : { state: 'idle', winner: null, self: false },
    takeover: s ? s.takeover : null,
    hostWaitFailed: s ? s.hostWaitFailed : false,
    error: s ? s.error : null,
    lastError: s ? s.lastError : null,
    connectError: s ? s.connectError : null,
    connectTimedOut: s ? s.connectTimedOut : false,
    maxClients: MAX_CLIENTS,
    full: Boolean(s && s.role === 'host' && clientCount(s, null) >= MAX_CLIENTS),
    turnConfigured: config.turnConfig.length > 0,
    turnServers: config.turnConfig.length,
    turnSource: config.turnConfig.length ? config.turnSource : null,
    relayReady: relayReady(),
    listening: s ? Boolean(s.engineListening) : false,
  };
}

function peerIds() {
  const s = session;
  return s ? activePeers(s).map((peer) => peer.id) : [];
}

function stats() {
  const s = session;
  let ctlOpen = false;
  let actOpen = false;
  const peers = activePeers(s);
  for (const peer of peers) {
    if (peer.ctlOpen) ctlOpen = true;
    if (peer.actOpen) actOpen = true;
  }
  return {
    peers: peers.length,
    ctlTx: s ? s.stats.ctlTx : 0,
    ctlRx: s ? s.stats.ctlRx : 0,
    actTx: s ? s.stats.actTx : 0,
    actRx: s ? s.stats.actRx : 0,
    ctlOpen,
    actOpen,
  };
}

function engineListening() {
  if (session) session.engineListening = true;
}

/* Test hook: every room peer, including same-role clients that are invalid for
 * engine traffic. */
function peerCount() {
  return session ? session.peers.size : 0;
}

function setHostVisible(value) {
  const s = session;
  if (!s) return false;
  s.hostVisible = Boolean(value);
  if (s.role === 'host') sendStatus(s);
  return true;
}

if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    const s = session;
    if (!s || s.role !== 'host') return;
    const visible = document.visibilityState !== 'hidden';
    if (s.hostVisible === visible) return;
    s.hostVisible = visible;
    sendStatus(s);
  });
}

/* Test hook: retransmit our hello to one peer, as the retry timers do. Used to
 * prove a retransmit cannot change an accepted peer's slot. */
function resendHello(peerId) {
  const s = session;
  if (!s) return false;
  const peer = s.peers.get(peerId);
  if (!peer || peer.closed) return false;
  return sendHello(s, peer);
}

const XBNet = {
  configure,
  enter,
  leave,
  open,
  listen,
  connect,
  connectState,
  cancelConnect,
  accept,
  attachPeer,
  send,
  recv,
  readable,
  writable,
  shutdownWrite,
  close,
  localName,
  remoteName,
  localPort,
  remotePort,
  status,
  peerIds,
  stats,
  engineListening,
  __peerCount: peerCount,
  claimHost,
  cancelClaim,
  __setTakeoverTimings: setTakeoverTimings,
  __setHostVisible: setHostVisible,
  __resendHello: resendHello,
};

globalThis.XBNet = XBNet;
globalThis.__xbnet = XBNet;

export default XBNet;
