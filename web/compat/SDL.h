/*
 * Minimal SDL 1.2 compatibility layer on top of SDL 2 for the XBlast web port.
 * Only the APIs XBlast actually uses are provided.
 */
#ifndef XBLAST_SDL12_SHIM_H
#define XBLAST_SDL12_SHIM_H

#include <SDL2/SDL.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef SDL_Keycode SDLKey;

/* SDL 1.2 keycode names that SDL 2 renamed or removed. */
#ifndef SDLK_PRINT
#define SDLK_PRINT SDLK_PRINTSCREEN
#endif
#ifndef SDLK_KP0
#define SDLK_KP0 SDLK_KP_0
#define SDLK_KP1 SDLK_KP_1
#define SDLK_KP2 SDLK_KP_2
#define SDLK_KP3 SDLK_KP_3
#define SDLK_KP4 SDLK_KP_4
#define SDLK_KP5 SDLK_KP_5
#define SDLK_KP6 SDLK_KP_6
#define SDLK_KP7 SDLK_KP_7
#define SDLK_KP8 SDLK_KP_8
#define SDLK_KP9 SDLK_KP_9
#endif
#ifndef SDLK_NUMLOCK
#define SDLK_NUMLOCK SDLK_NUMLOCKCLEAR
#endif
#ifndef SDLK_SCROLLOCK
#define SDLK_SCROLLOCK SDLK_SCROLLLOCK
#endif
#ifndef SDLK_LSUPER
#define SDLK_LSUPER SDLK_LGUI
#define SDLK_RSUPER SDLK_RGUI
#endif
#ifndef SDLK_COMPOSE
#define SDLK_COMPOSE SDLK_APPLICATION
#endif

typedef enum
{
	SDL_GRAB_QUERY = -1,
	SDL_GRAB_OFF = 0,
	SDL_GRAB_ON = 1
} SDL_GrabMode;

/* SDL1 video flags (SDL2 has no such surface flags). */
#ifndef SDL_SWSURFACE
#define SDL_SWSURFACE 0x00000000
#endif
#ifndef SDL_HWSURFACE
#define SDL_HWSURFACE 0x00000001
#endif
#ifndef SDL_DOUBLEBUF
#define SDL_DOUBLEBUF 0x00000002
#endif
#ifndef SDL_FULLSCREEN
#define SDL_FULLSCREEN 0x80000000
#endif

/* SDL1 video info, filled in by the shim. */
typedef struct SDL_VideoInfo
{
	Uint32 hw_available:1;
	Uint32 wm_available:1;
	Uint32 UnusedBits1:6;
	Uint32 UnusedBits2:1;
	Uint32 blit_hw:1;
	Uint32 blit_hw_CC:1;
	Uint32 blit_hw_A:1;
	Uint32 blit_sw:1;
	Uint32 blit_sw_CC:1;
	Uint32 blit_sw_A:1;
	Uint32 blit_fill:1;
	Uint32 UnusedBits3:16;
	Uint32 video_mem;
	SDL_PixelFormat *vfmt;
} SDL_VideoInfo;

/* Video */
extern SDL_Surface *SDL_SetVideoMode (int width, int height, int bpp, Uint32 flags);
extern SDL_Surface *SDL_GetVideoSurface (void);
extern void SDL_UpdateRect (SDL_Surface *screen, Sint32 x, Sint32 y, Uint32 w, Uint32 h);
extern void SDL_UpdateRects (SDL_Surface *screen, int numrects, SDL_Rect *rects);
extern int SDL_Flip (SDL_Surface *screen);
extern const SDL_VideoInfo *SDL_GetVideoInfo (void);
extern SDL_Surface *SDL_DisplayFormat (SDL_Surface *surface);
extern SDL_Surface *SDL_DisplayFormatAlpha (SDL_Surface *surface);
extern int SDL_SetColors (SDL_Surface *surface, SDL_Color *colors, int firstcolor, int ncolors);

/* Window manager */
extern int SDL_WM_ToggleFullScreen (SDL_Surface *surface);
extern SDL_GrabMode SDL_WM_GrabInput (SDL_GrabMode mode);
extern int SDL_WM_IconifyWindow (void);
extern void SDL_WM_SetCaption (const char *title, const char *icon);
extern void SDL_WM_GetCaption (char **title, char **icon);
extern void SDL_WM_SetIcon (SDL_Surface *icon, Uint8 *mask);

/* Engine helpers */
extern void XBWeb_Present (SDL_Surface *surface);
extern void XBWeb_PumpEvents (void);

#ifdef __cplusplus
}
#endif

#endif
