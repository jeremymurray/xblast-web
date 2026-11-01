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
 * This file intentionally has no dependencies beyond the vendored Trystero
 * packages and no build step: it is loaded as a plain ES module.
 */
import { getRelaySockets, joinRoom, selfId } from '@trystero-p2p/nostr';

const APP_ID = 'xblast-tnt-web-v1';
const ROOM_PREFIX = 'xblast-tnt-';

const CTL_LABEL = 'xb.ctl';
const ACT_LABEL = 'xb.act';
const CTL_ID = 42;
const ACT_ID = 43;

const ROLE_HOST = 1;
const ROLE_CLIENT = 2;
const HELLO_VERSION = 1;

const CTL_HELLO = 1;
const CTL_DATA = 2;
const CTL_EOF = 3;
const CTL_CLOSE = 4;

const PORT = 16168;
const CTL_BUFFER_LIMIT = 512 * 1024;
const DEFAULT_CONNECT_TIMEOUT_MS = 20000;

const config = {
  connectTimeoutMs: DEFAULT_CONNECT_TIMEOUT_MS,
};

/* The single active page session; rooms are page-owned, not fd-owned. */
let session = null;

function localRoleOf(role) {
  return role === 'client' ? ROLE_CLIENT : ROLE_HOST;
}

function newSession(role, room) {
  return {
    role,
    room,
    localRole: localRoleOf(role),
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
    recheck: null,
    stats: { ctlTx: 0, ctlRx: 0, actTx: 0, actRx: 0 },
  };
}

function configure(opts) {
  if (!opts || typeof opts !== 'object') return;
  if (Number.isFinite(opts.connectTimeoutMs) && opts.connectTimeoutMs > 0) {
    config.connectTimeoutMs = opts.connectTimeoutMs;
  }
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
  return Boolean(peer) && !peer.closed && !peer.invalid && peer.helloOk;
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

function sendHello(s, peer) {
  if (!peer || peer.closed || peer.invalid) return false;
  return ctlSend(s, peer, new Uint8Array([CTL_HELLO, HELLO_VERSION, s.localRole]));
}

function handleHello(s, peer, bytes) {
  const version = bytes[1];
  const remoteRole = bytes[2];
  const validRole = remoteRole === ROLE_HOST || remoteRole === ROLE_CLIENT;
  if (version !== HELLO_VERSION || !validRole || remoteRole === s.localRole) {
    // Another host/client in the same room is ignored; its channels are not
    // used for engine traffic.
    peer.invalid = true;
    clearHelloTimers(peer);
    return;
  }
  const firstValid = !peer.helloOk;
  peer.version = version;
  peer.remoteRole = remoteRole;
  peer.helloOk = true;
  clearHelloTimers(peer);
  // A valid peer makes an older handshake failure stale.
  s.lastError = null;
  s.joinErrorPeer = null;
  if (firstValid) {
    // The peer's channel may have existed before ours did, so its first hello
    // can be lost. Echo ours once we know both channels are live.
    sendHello(s, peer);
  }
  if (s.role === 'host' && remoteRole === ROLE_CLIENT) {
    if (!peer.accepted && !s.pending.includes(peer.id)) s.pending.push(peer.id);
  } else if (s.role === 'client' && remoteRole === ROLE_HOST) {
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
    version: 0,
    remoteRole: 0,
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
}

function enter(role, room) {
  leave();
  const s = newSession(role === 'client' ? 'client' : 'host', room || '');
  session = s;
  try {
    const roomObj = joinRoom(
      { appId: APP_ID },
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
  if (!s || s.role !== 'host') return false;
  const f = ensureFd(s, fd, 'stream');
  f.listening = true;
  f.role = 'listen';
  s.listenFd = fd;
  s.engineListening = true;
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
  let peer = f.peer;
  if (!peer) {
    peer = findHostPeer(s);
    if (peer) {
      f.peer = peer;
      f.peerId = peer.id;
    }
  }
  if (peer && peer.helloOk && peer.remoteRole === ROLE_HOST && peer.ctlOpen && !peer.closed) {
    return 1;
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
  if (!s || s.role !== 'host') return null;
  const lf = s.fds.get(listenFd);
  if (!lf || !lf.listening) return null;
  while (s.pending.length) {
    const id = s.pending.shift();
    const peer = s.peers.get(id);
    if (!peer || peer.closed || !peer.helloOk || peer.invalid ||
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
  return {
    role: s ? s.role : null,
    room: s ? s.room : null,
    state: s ? s.state : 'idle',
    peers: s ? activePeers(s).length : 0,
    selfId,
    error: s ? s.error : null,
    lastError: s ? s.lastError : null,
    connectError: s ? s.connectError : null,
    connectTimedOut: s ? s.connectTimedOut : false,
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
};

globalThis.XBNet = XBNet;
globalThis.__xbnet = XBNet;

export default XBNet;
