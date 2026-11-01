/* Test-only socket.h harness; not linked into the shipped game. */
#include "xblast.h"
#include "socket.h"
#include "sdl_socket.h"
#include "net_web.h"

#include <emscripten.h>

#define WAIT_SLICES 2000

static int g_readyFd = -1;
static int g_readyKind = 0;

EM_JS(void, xb_test_report, (const char *msg), {
	window.__nettest = {done:true, msg: UTF8ToString(msg)};
});

void
CommReadable (int fd)
{
	g_readyFd = fd;
	g_readyKind = 1;
}

void
CommWriteable (int fd)
{
	g_readyFd = fd;
	g_readyKind = 2;
}

static int
Fail (const char *step)
{
	char msg[128];
	snprintf (msg, sizeof (msg), "fail:%s", step);
	xb_test_report (msg);
	return -1;
}

static int
ReceiveExact (XBSocket *sock, void *buffer, size_t len)
{
	size_t offset = 0;
	int waits = 0;
	while (offset < len && waits < WAIT_SLICES) {
		int got = Socket_Receive (sock, (char *)buffer + offset, len - offset);
		if (got > 0) {
			offset += (size_t)got;
			waits = 0;
		}
		else if (got == XB_SOCKET_WOULD_BLOCK) {
			emscripten_sleep (10);
			waits++;
		}
		else {
			return 0;
		}
	}
	return offset == len;
}

static int
ReceiveEof (XBSocket *sock)
{
	unsigned char byte;
	int waits;
	for (waits = 0; waits < WAIT_SLICES; waits++) {
		int got = Socket_Receive (sock, &byte, 1);
		if (got == XB_SOCKET_END_OF_FILE) {
			return 1;
		}
		if (got != XB_SOCKET_WOULD_BLOCK) {
			return 0;
		}
		emscripten_sleep (10);
	}
	return 0;
}

static int
SendStream (XBSocket *sock, const void *buffer, size_t len)
{
	size_t offset = 0;
	int waits = 0;
	while (offset < len && waits < WAIT_SLICES) {
		int sent = Socket_Send (sock, (const char *)buffer + offset, len - offset);
		if (sent > 0) {
			offset += (size_t)sent;
			waits = 0;
		}
		else if (sent == XB_SOCKET_WOULD_BLOCK) {
			emscripten_sleep (10);
			waits++;
		}
		else {
			return 0;
		}
	}
	return offset == len;
}

static XBSocket *
NewSocket (int type)
{
	XBSocket *sock = Socket_Alloc (AF_INET);
	if (sock == NULL || !Socket_Open (sock, type)) {
		return NULL;
	}
	return sock;
}

static int
RunDgram (XBSocket *stream)
{
	static const unsigned char expected[] = { 9, 9 };
	unsigned char received[2];
	XBSocket *dgram = NULL;
	const char *peer = Socket_HostName (stream, XBTrue);
	int sent = XB_SOCKET_WOULD_BLOCK;
	int got;
	int waits;

	if (peer == NULL || peer[0] == '\0') {
		return 0;
	}
	dgram = NewSocket (SOCK_DGRAM);
	if (dgram == NULL ||
		!Socket_SetAddressInet (dgram, XBTrue, peer, 16168) ||
		!Socket_Connect (dgram)) {
		return 0;
	}
	for (waits = 0; waits < WAIT_SLICES && sent == XB_SOCKET_WOULD_BLOCK; waits++) {
		sent = Socket_Send (dgram, expected, sizeof (expected));
		if (sent == XB_SOCKET_WOULD_BLOCK) {
			emscripten_sleep (10);
		}
	}
	if (sent != (int)sizeof (expected)) {
		return 0;
	}
	for (waits = 0; waits < WAIT_SLICES; waits++) {
		got = Socket_Receive (dgram, received, sizeof (received));
		if (got != XB_SOCKET_WOULD_BLOCK) {
			break;
		}
		emscripten_sleep (10);
	}
	if (got != (int)sizeof (expected) || memcmp (received, expected, sizeof (expected)) != 0) {
		return 0;
	}
	Socket_Close (dgram);
	Socket_Free (dgram);
	return 1;
}

EMSCRIPTEN_KEEPALIVE int
xb_test_run (void)
{
	XBSocket *listenSock = NULL;
	XBSocket *stream = NULL;
	XBWebMode mode = XBWeb_Mode ();
	const char *room = XBWeb_RoomCode ();
	char result[256];
	const char *peer;

	if (mode != XBWM_Host && mode != XBWM_Join) {
		return Fail ("mode");
	}
	if (!Socket_Init ()) {
		return Fail ("init");
	}

	if (mode == XBWM_Host) {
		static const unsigned char expected[] = { 1, 2, 3 };
		static const unsigned char reply[] = { 4, 5 };
		static const unsigned char afterListenClose[] = { 6 };
		unsigned char received[3];
		int i;

		listenSock = NewSocket (SOCK_STREAM);
		if (listenSock == NULL ||
			!Socket_SetAddressInet (listenSock, XBFalse, NULL, 16168) ||
			!Socket_Bind (listenSock) || !Socket_Listen (listenSock)) {
			return Fail ("listen");
		}
		Socket_RegisterRead (listenSock);
		for (i = 0; i < 400; i++) {
			struct timeval tv = { 0, 50000 };
			g_readyFd = -1;
			g_readyKind = 0;
			SelectSockets (&tv);
			if (g_readyFd == Socket_Fd (listenSock) && g_readyKind == 1) {
				break;
			}
		}
		if (g_readyFd != Socket_Fd (listenSock) || g_readyKind != 1) {
			return Fail ("accept-ready");
		}
		Socket_UnregisterRead (listenSock);
		stream = Socket_Alloc (Socket_Family (listenSock));
		if (stream == NULL || !Socket_Accept (stream, listenSock)) {
			return Fail ("accept");
		}
		if (!ReceiveExact (stream, received, sizeof (received)) ||
			memcmp (received, expected, sizeof (expected)) != 0) {
			return Fail ("host-recv");
		}
		/* Close listen only after the guest's connect has returned and its
		 * first bytes arrived: the host-stage status treats a closed listen
		 * with live accepted peers as "match", and the synthetic close must
		 * not race the guest's connect. */
		Socket_Close (listenSock);
		Socket_Free (listenSock);
		listenSock = NULL;

		if (!SendStream (stream, reply, sizeof (reply))) {
			return Fail ("host-send");
		}
		if (!SendStream (stream, afterListenClose, sizeof (afterListenClose))) {
			return Fail ("listen-close-send");
		}
		Socket_ShutdownWrite (stream);
		if (!ReceiveEof (stream)) {
			return Fail ("host-eof");
		}
	}
	else {
		static const unsigned char hello[] = { 1, 2, 3 };
		static const unsigned char expected[] = { 4, 5 };
		static const unsigned char afterListenClose[] = { 6 };
		unsigned char received[2];

		stream = NewSocket (SOCK_STREAM);
		if (stream == NULL ||
			!Socket_SetAddressInet (stream, XBTrue, room, 16168) ||
			!Socket_Connect (stream)) {
			return Fail ("connect");
		}
		if (!SendStream (stream, hello, sizeof (hello))) {
			return Fail ("client-send");
		}
		if (!ReceiveExact (stream, received, sizeof (received)) ||
			memcmp (received, expected, sizeof (expected)) != 0) {
			return Fail ("client-recv");
		}
		if (!ReceiveExact (stream, received, 1) || received[0] != afterListenClose[0]) {
			return Fail ("listen-close-recv");
		}
		Socket_ShutdownWrite (stream);
		if (!ReceiveEof (stream)) {
			return Fail ("client-eof");
		}
	}

	peer = Socket_HostName (stream, XBTrue);
	if (peer == NULL || peer[0] == '\0') {
		return Fail ("peer-name");
	}
	if (!RunDgram (stream)) {
		return Fail ("dgram");
	}
	if (mode == XBWM_Host) {
		snprintf (result, sizeof (result), "host-ok:%s listen-close-ok dgram-ok", peer);
	}
	else {
		snprintf (result, sizeof (result), "client-ok listen-close-ok dgram-ok");
	}
	xb_test_report (result);
	return 0;
}
