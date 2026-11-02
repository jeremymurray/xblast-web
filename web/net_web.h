#ifndef XBLAST_NET_WEB_H
#define XBLAST_NET_WEB_H

#ifdef __EMSCRIPTEN__
typedef enum { XBWM_Solo = 0, XBWM_Host = 1, XBWM_Join = 2 } XBWebMode;
XBWebMode XBWeb_Mode (void);
const char *XBWeb_RoomCode (void);
void XBWeb_ClearIntent (void);
void XBWeb_ReloadLobby (void);
int XBWeb_AutoJoin (void);
void XBWeb_ClearAutoJoin (void);
void XBWeb_FlushConfig (void);
#endif

#endif
