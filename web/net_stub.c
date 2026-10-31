/*
 * Placeholder socket layer for the web build (M0).
 * The real implementation will be replaced by the WebRTC bridge.
 * For now every connection attempt fails; local single-player works.
 */
#include "xblast.h"

#include "socket.h"
#include "sdl_socket.h"

#ifdef __EMSCRIPTEN__
#include <emscripten.h>
#endif

struct _xb_socket
{
	int family;
	int fd;
	int dummy;
};

void
SelectSockets (struct timeval *timeout)
{
#ifdef __EMSCRIPTEN__
	long usec = timeout ? (long)timeout->tv_sec * 1000000 + timeout->tv_usec : 0;
	/* Use the Asyncify-aware sleep directly. A zero timeout must still yield,
	   otherwise the loop starves the browser event loop. */
	if (usec < 1000) {
		emscripten_sleep (1);
	}
	else {
		emscripten_sleep ((int)((usec + 999) / 1000));
	}
#else
	if (timeout != NULL) {
		usleep (timeout->tv_sec * 1000000 + timeout->tv_usec);
	}
#endif
}

XBBool
Socket_Init (void)
{
	return XBTrue;
}

void
Socket_Finish (void)
{
}

int
Socket_Fd (const XBSocket * pSocket)
{
	return pSocket ? pSocket->fd : -1;
}

int
Socket_Family (const XBSocket * pSocket)
{
	return pSocket ? pSocket->family : 0;
}

const char *
Socket_HostName (const XBSocket * pSocket, XBBool peer)
{
	(void)pSocket;
	(void)peer;
	return NULL;
}

unsigned
Socket_HostPort (const XBSocket * pSocket, XBBool peer)
{
	(void)pSocket;
	(void)peer;
	return 0;
}

XBSocket *
Socket_Alloc (int family)
{
	XBSocket *s = calloc (1, sizeof (XBSocket));
	if (s) {
		s->family = family;
		s->fd = -1;
	}
	return s;
}

void
Socket_Free (XBSocket * pSocket)
{
	free (pSocket);
}

XBBool
Socket_SetAddressInet (XBSocket * pSocket, XBBool peer, const char *hostName, unsigned short port)
{
	(void)pSocket;
	(void)peer;
	(void)hostName;
	(void)port;
	return XBFalse;
}

XBBool
Socket_SetBroadcast (XBSocket * pSocket, XBBool enable)
{
	(void)pSocket;
	(void)enable;
	return XBFalse;
}

XBBool
Socket_SetReuse (XBSocket * pSocket)
{
	(void)pSocket;
	return XBFalse;
}

void
Socket_RegisterWrite (XBSocket * pSocket)
{
	(void)pSocket;
}

void
Socket_RegisterRead (XBSocket * pSocket)
{
	(void)pSocket;
}

void
Socket_UnregisterWrite (XBSocket * pSocket)
{
	(void)pSocket;
}

void
Socket_UnregisterRead (XBSocket * pSocket)
{
	(void)pSocket;
}

XBBool
Socket_Open (XBSocket * pSocket, int type)
{
	(void)pSocket;
	(void)type;
	return XBFalse;
}

XBBool
Socket_Connect (XBSocket * pSocket)
{
	(void)pSocket;
	return XBFalse;
}

XBBool
Socket_Bind (XBSocket * pSocket)
{
	(void)pSocket;
	return XBFalse;
}

XBBool
Socket_Accept (XBSocket * pSocket, const XBSocket * pListen)
{
	(void)pSocket;
	(void)pListen;
	return XBFalse;
}

XBBool
Socket_Listen (XBSocket * pSocket)
{
	(void)pSocket;
	return XBFalse;
}

void
Socket_Close (XBSocket * pSocket)
{
	(void)pSocket;
}

void
Socket_ShutdownWrite (XBSocket * pSocket)
{
	(void)pSocket;
}

int
Socket_Send (const XBSocket * pSocket, const void *buf, size_t len)
{
	(void)pSocket;
	(void)buf;
	(void)len;
	return XB_SOCKET_ERROR;
}

int
Socket_Receive (const XBSocket * pSocket, void *buf, size_t len)
{
	(void)pSocket;
	(void)buf;
	(void)len;
	return XB_SOCKET_ERROR;
}

int
Socket_SendTo (XBSocket * pSocket, const void *buf, size_t len, const char *host,
			   unsigned short port)
{
	(void)pSocket;
	(void)buf;
	(void)len;
	(void)host;
	(void)port;
	return XB_SOCKET_ERROR;
}

int
Socket_ReceiveFrom (XBSocket * pSocket, void *buf, size_t len, const char **host,
					unsigned short *port)
{
	(void)pSocket;
	(void)buf;
	(void)len;
	(void)host;
	(void)port;
	return XB_SOCKET_ERROR;
}

const XBSocketInterface *
Socket_GetInterfaces (size_t *count)
{
	if (count) {
		*count = 0;
	}
	return NULL;
}

const char *
Socket_GetAutoInterface (XBSocket * pSocket, const char *hint)
{
	(void)pSocket;
	(void)hint;
	return NULL;
}
