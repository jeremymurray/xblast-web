/* WebRTC implementation of the engine's socket.h seam. */
#include "xblast.h"
#include "socket.h"
#include "sdl_socket.h"
#include "net_web.h"

#include <emscripten.h>
#include <limits.h>

#define XB_WEB_PORT 16168
#define XB_CONNECT_SLICE_MS 50
#define XB_SELECT_SLICE_MS 5

struct _xb_socket
{
	int fd;
	int family;
	int type;
	XBBool bound;
	XBBool connected;
	XBBool open;
	XBBool readReg;
	XBBool writeReg;
	char host[128];
	unsigned short port;
	char localName[128];
	char remoteName[128];
	struct _xb_socket *next;
};

static XBSocket *sockets = NULL;
static int nextFd = 1000;

EM_JS(int, xbnet_open, (int fd, int dgram), {
	const net = globalThis.XBNet;
	if (!net) return 0;
	net.open(fd, dgram ? 'dgram' : 'stream');
	return 1;
});

EM_JS(int, xbnet_listen, (int fd, const char *room), {
	const net = globalThis.XBNet;
	if (!net) return 0;
	return net.listen(fd, UTF8ToString(room)) ? 1 : 0;
});

EM_JS(void, xbnet_engine_listening, (void), {
	if (globalThis.XBNet) globalThis.XBNet.engineListening();
});

EM_JS(int, xbnet_accept, (int listenFd, int newFd, char *peer, int peerSize), {
	const net = globalThis.XBNet;
	if (!net) return 0;
	const id = net.accept(listenFd, newFd);
	if (!id) return 0;
	stringToUTF8(id, peer, peerSize);
	return 1;
});

EM_JS(int, xbnet_connect, (int fd, const char *room), {
	const net = globalThis.XBNet;
	if (!net) return 0;
	net.connect(fd, UTF8ToString(room));
	const status = net.status();
	return status.role === 'client' ? 1 : 0;
});

EM_JS(int, xbnet_connect_state, (int fd), {
	return globalThis.XBNet ? globalThis.XBNet.connectState(fd) : -1;
});

EM_JS(int, xbnet_attach_peer, (int fd, const char *peer), {
	return globalThis.XBNet && globalThis.XBNet.attachPeer(fd, UTF8ToString(peer)) ? 1 : 0;
});

EM_JS(int, xbnet_send, (int fd, const void *buffer, int len), {
	return globalThis.XBNet ? globalThis.XBNet.send(fd, HEAPU8.subarray(buffer, buffer + len)) : -2;
});

EM_JS(int, xbnet_recv, (int fd, void *buffer, int max), {
	const net = globalThis.XBNet;
	if (!net) return -2;
	const result = net.recv(fd, max);
	if (!result) return -2;
	if (result.kind === 'eof') return 0;
	if (result.kind === 'block') return -1;
	if (result.kind !== 'data') return -2;
	HEAPU8.set(result.data, buffer);
	return result.data.length;
});

EM_JS(int, xbnet_readable, (int fd), {
	return globalThis.XBNet && globalThis.XBNet.readable(fd) ? 1 : 0;
});

EM_JS(int, xbnet_writable, (int fd), {
	return globalThis.XBNet && globalThis.XBNet.writable(fd) ? 1 : 0;
});

EM_JS(void, xbnet_shutdown_write, (int fd), {
	if (globalThis.XBNet) globalThis.XBNet.shutdownWrite(fd);
});

EM_JS(void, xbnet_close, (int fd), {
	if (globalThis.XBNet) globalThis.XBNet.close(fd);
});

EM_JS(int, xbnet_name, (int fd, int peer, char *name, int nameSize), {
	const net = globalThis.XBNet;
	if (!net) return 0;
	const value = peer ? net.remoteName(fd) : net.localName(fd);
	if (!value) return 0;
	stringToUTF8(value, name, nameSize);
	return 1;
});

EM_JS(void, xbnet_leave, (void), {
	if (globalThis.XBNet) globalThis.XBNet.leave();
});

EM_JS(int, xb_web_mode, (void), {
	const config = globalThis.xbConfig;
	if (config && config.mode === 'host') return 1;
	if (config && config.mode === 'client') return 2;
	return 0;
});

EM_JS(void, xb_web_room_code, (char *room, int roomSize), {
	const config = globalThis.xbConfig;
	const value = config && config.room !== undefined ? config.room : "";
	const code = String(value).trim().toLowerCase().slice(0, 32);
	stringToUTF8(code, room, roomSize);
});

EM_JS(void, xb_web_clear_intent, (void), {
	globalThis.xbConfig = globalThis.xbConfig || {};
	globalThis.xbConfig.mode = 'solo';
});

EM_JS(void, xb_web_reload_lobby, (void), {
	if (globalThis.XBNet) globalThis.XBNet.leave();
	location.reload();
});

static XBSocket *
FindFd (int fd)
{
	XBSocket *sock;
	for (sock = sockets; sock != NULL; sock = sock->next) {
		if (sock->open && sock->fd == fd) {
			return sock;
		}
	}
	return NULL;
}

static void
CacheNames (XBSocket *sock)
{
	xbnet_name (sock->fd, 0, sock->localName, sizeof (sock->localName));
	xbnet_name (sock->fd, 1, sock->remoteName, sizeof (sock->remoteName));
}

static const char *
RoomWithPortFallback (const char *room, unsigned short port, char *fallback, size_t fallbackSize)
{
	if (room != NULL && room[0] != '\0') {
		return room;
	}
	snprintf (fallback, fallbackSize, "%u", port ? port : XB_WEB_PORT);
	return fallback;
}

static unsigned
TimeoutMs (const struct timeval *timeout)
{
	long usec;
	if (timeout == NULL) {
		return 50;
	}
	usec = (long)timeout->tv_sec * 1000000 + timeout->tv_usec;
	if (usec <= 0) {
		return 1;
	}
	return (unsigned)((usec + 999) / 1000);
}

XBWebMode
XBWeb_Mode (void)
{
	return (XBWebMode)xb_web_mode ();
}

const char *
XBWeb_RoomCode (void)
{
	static char room[33];
	xb_web_room_code (room, sizeof (room));
	return room;
}

void
XBWeb_ClearIntent (void)
{
	xb_web_clear_intent ();
}

void
XBWeb_ReloadLobby (void)
{
	xb_web_reload_lobby ();
}

XBBool
Socket_Init (void)
{
	return XBTrue;
}

void
Socket_Finish (void)
{
	XBSocket *sock;
	for (sock = sockets; sock != NULL; sock = sock->next) {
		sock->fd = -1;
		sock->open = XBFalse;
		sock->connected = XBFalse;
		sock->readReg = XBFalse;
		sock->writeReg = XBFalse;
	}
	xbnet_leave ();
}

int
Socket_Fd (const XBSocket *sock)
{
	return sock ? sock->fd : -1;
}

int
Socket_Family (const XBSocket *sock)
{
	return sock ? sock->family : 0;
}

const char *
Socket_HostName (const XBSocket *sock, XBBool peer)
{
	const char *name;
	if (sock == NULL) {
		return NULL;
	}
	name = peer ? sock->remoteName : sock->localName;
	return name[0] ? name : NULL;
}

unsigned
Socket_HostPort (const XBSocket *sock, XBBool peer)
{
	(void)peer;
	return sock ? XB_WEB_PORT : 0;
}

XBSocket *
Socket_Alloc (int family)
{
	XBSocket *sock;
	if (family != AF_INET) {
		return NULL;
	}
	sock = calloc (1, sizeof (*sock));
	if (sock == NULL) {
		return NULL;
	}
	sock->fd = -1;
	sock->family = family;
	sock->next = sockets;
	sockets = sock;
	return sock;
}

void
Socket_Free (XBSocket *sock)
{
	XBSocket **link;
	if (sock == NULL) {
		return;
	}
	for (link = &sockets; *link != NULL; link = &(*link)->next) {
		if (*link == sock) {
			*link = sock->next;
			break;
		}
	}
	free (sock);
}

XBBool
Socket_SetAddressInet (XBSocket *sock, XBBool peer, const char *hostName, unsigned short port)
{
	(void)peer;
	if (sock == NULL) {
		return XBFalse;
	}
	if (hostName != NULL) {
		snprintf (sock->host, sizeof (sock->host), "%s", hostName);
	}
	else {
		sock->host[0] = '\0';
	}
	sock->port = port;
	return XBTrue;
}

XBBool
Socket_SetBroadcast (XBSocket *sock, XBBool enable)
{
	(void)sock;
	(void)enable;
	return XBTrue;
}

XBBool
Socket_SetReuse (XBSocket *sock)
{
	(void)sock;
	return XBTrue;
}

void
Socket_RegisterWrite (XBSocket *sock)
{
	if (sock != NULL && sock->open) {
		sock->writeReg = XBTrue;
	}
}

void
Socket_RegisterRead (XBSocket *sock)
{
	if (sock != NULL && sock->open) {
		sock->readReg = XBTrue;
	}
}

void
Socket_UnregisterWrite (XBSocket *sock)
{
	if (sock != NULL) {
		sock->writeReg = XBFalse;
	}
}

void
Socket_UnregisterRead (XBSocket *sock)
{
	if (sock != NULL) {
		sock->readReg = XBFalse;
	}
}

XBBool
Socket_Open (XBSocket *sock, int type)
{
	int fd;
	if (sock == NULL || sock->open || (type != SOCK_STREAM && type != SOCK_DGRAM)) {
		return XBFalse;
	}
	fd = nextFd++;
	if (!xbnet_open (fd, type == SOCK_DGRAM)) {
		return XBFalse;
	}
	sock->fd = fd;
	sock->type = type;
	sock->open = XBTrue;
	sock->bound = XBFalse;
	sock->connected = XBFalse;
	sock->readReg = XBFalse;
	sock->writeReg = XBFalse;
	return XBTrue;
}

XBBool
Socket_Bind (XBSocket *sock)
{
	if (sock == NULL || !sock->open) {
		return XBFalse;
	}
	sock->bound = XBTrue;
	return XBTrue;
}

XBBool
Socket_Listen (XBSocket *sock)
{
	char fallback[16];
	const char *room;
	if (sock == NULL || !sock->open || sock->type != SOCK_STREAM) {
		return XBFalse;
	}
	room = RoomWithPortFallback (XBWeb_RoomCode (), sock->port, fallback, sizeof (fallback));
	if (!xbnet_listen (sock->fd, room)) {
		return XBFalse;
	}
	xbnet_engine_listening ();
	sock->bound = XBTrue;
	return XBTrue;
}

XBBool
Socket_Accept (XBSocket *sock, const XBSocket *listenSock)
{
	int fd;
	if (sock == NULL || listenSock == NULL || sock->open || !listenSock->open ||
		listenSock->type != SOCK_STREAM) {
		return XBFalse;
	}
	fd = nextFd++;
	if (!xbnet_accept (listenSock->fd, fd, sock->remoteName, sizeof (sock->remoteName))) {
		sock->remoteName[0] = '\0';
		return XBFalse;
	}
	sock->fd = fd;
	sock->family = listenSock->family;
	sock->type = SOCK_STREAM;
	sock->bound = XBTrue;
	sock->connected = XBTrue;
	sock->open = XBTrue;
	CacheNames (sock);
	return XBTrue;
}

XBBool
Socket_Connect (XBSocket *sock)
{
	char fallback[16];
	const char *room;
	if (sock == NULL || !sock->open) {
		return XBFalse;
	}
	if (sock->type == SOCK_DGRAM) {
		if (!sock->host[0] || !xbnet_attach_peer (sock->fd, sock->host)) {
			return XBFalse;
		}
		sock->connected = XBTrue;
		CacheNames (sock);
		return XBTrue;
	}
	if (sock->type != SOCK_STREAM) {
		return XBFalse;
	}
	room = sock->host[0] ? sock->host : XBWeb_RoomCode ();
	room = RoomWithPortFallback (room, sock->port, fallback, sizeof (fallback));
	if (!xbnet_connect (sock->fd, room)) {
		return XBFalse;
	}
	for (;;) {
		int state = xbnet_connect_state (sock->fd);
		if (state == 1) {
			sock->connected = XBTrue;
			CacheNames (sock);
			return XBTrue;
		}
		if (state != 0) {
			return XBFalse;
		}
		emscripten_sleep (XB_CONNECT_SLICE_MS);
	}
}

void
Socket_Close (XBSocket *sock)
{
	if (sock == NULL || !sock->open) {
		return;
	}
	xbnet_close (sock->fd);
	sock->fd = -1;
	sock->open = XBFalse;
	sock->bound = XBFalse;
	sock->connected = XBFalse;
	sock->readReg = XBFalse;
	sock->writeReg = XBFalse;
}

void
Socket_ShutdownWrite (XBSocket *sock)
{
	if (sock != NULL && sock->open && sock->type == SOCK_STREAM) {
		xbnet_shutdown_write (sock->fd);
	}
}

int
Socket_Send (const XBSocket *sock, const void *buffer, size_t len)
{
	if (sock == NULL || !sock->open || (buffer == NULL && len != 0) || len > INT_MAX) {
		return XB_SOCKET_ERROR;
	}
	return xbnet_send (sock->fd, buffer, (int)len);
}

int
Socket_Receive (const XBSocket *sock, void *buffer, size_t len)
{
	if (sock == NULL || !sock->open || (buffer == NULL && len != 0) || len > INT_MAX) {
		return XB_SOCKET_ERROR;
	}
	return xbnet_recv (sock->fd, buffer, (int)len);
}

int
Socket_SendTo (XBSocket *sock, const void *buffer, size_t len, const char *host, unsigned short port)
{
	(void)sock;
	(void)buffer;
	(void)len;
	(void)host;
	(void)port;
	return XB_SOCKET_ERROR;
}

int
Socket_ReceiveFrom (XBSocket *sock, void *buffer, size_t len, const char **host, unsigned short *port)
{
	(void)sock;
	(void)buffer;
	(void)len;
	if (host != NULL) {
		*host = NULL;
	}
	if (port != NULL) {
		*port = 0;
	}
	return XB_SOCKET_ERROR;
}

const XBSocketInterface *
Socket_GetInterfaces (size_t *count)
{
	if (count != NULL) {
		*count = 0;
	}
	return NULL;
}

const char *
Socket_GetAutoInterface (XBSocket *sock, const char *hint)
{
	(void)sock;
	(void)hint;
	return NULL;
}

void
SelectSockets (struct timeval *timeout)
{
	XBSocket *sock;
	int count = 0;
	int *fds;
	int i;
	unsigned totalMs;
	unsigned elapsed = 0;

	for (sock = sockets; sock != NULL; sock = sock->next) {
		if (sock->open && (sock->readReg || sock->writeReg)) {
			count++;
		}
	}
	totalMs = TimeoutMs (timeout);
	if (count == 0) {
		emscripten_sleep (totalMs);
		return;
	}
	fds = malloc ((size_t)count * sizeof (*fds));
	if (fds == NULL) {
		emscripten_sleep (1);
		return;
	}
	i = 0;
	for (sock = sockets; sock != NULL; sock = sock->next) {
		if (sock->open && (sock->readReg || sock->writeReg)) {
			fds[i++] = sock->fd;
		}
	}

	for (;;) {
		int dispatched = 0;
		for (i = 0; i < count; i++) {
			int readReady;
			int writeReady;
			sock = FindFd (fds[i]);
			if (sock == NULL) {
				continue;
			}
			readReady = sock->readReg && xbnet_readable (sock->fd);
			writeReady = sock->writeReg && xbnet_writable (sock->fd);
			if (readReady) {
				CommReadable (fds[i]);
				dispatched = 1;
			}
			if (writeReady) {
				sock = FindFd (fds[i]);
				if (sock != NULL && sock->writeReg) {
					CommWriteable (fds[i]);
					dispatched = 1;
				}
			}
		}
		if (dispatched || elapsed >= totalMs) {
			break;
		}
		{
			unsigned slice = totalMs - elapsed;
			if (slice > XB_SELECT_SLICE_MS) {
				slice = XB_SELECT_SLICE_MS;
			}
			emscripten_sleep (slice);
			elapsed += slice;
		}
	}
	free (fds);
}
