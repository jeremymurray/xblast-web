/*
 * SDL 1.2 video/window shim implemented on SDL 2 for the XBlast web port.
 * The engine keeps drawing into a plain software surface; this layer
 * uploads that surface to a streaming texture and presents it.
 */
#include <SDL2/SDL.h>
#include <string.h>
#include <stdlib.h>

#include "SDL.h"

static SDL_Window *webWindow = NULL;
static SDL_Renderer *webRenderer = NULL;
static SDL_Texture *webTexture = NULL;
static SDL_Surface *webScreen = NULL;
static int webFullscreen = 0;
static SDL_GrabMode webGrab = SDL_GRAB_OFF;

static char webTitle[256] = "XBlast TNT";
static char webIconTitle[256] = "XBlast TNT";

static SDL_VideoInfo webVideoInfo;

static void
DestroyVideo (void)
{
	if (webTexture) {
		SDL_DestroyTexture (webTexture);
		webTexture = NULL;
	}
	if (webRenderer) {
		SDL_DestroyRenderer (webRenderer);
		webRenderer = NULL;
	}
	if (webWindow) {
		SDL_DestroyWindow (webWindow);
		webWindow = NULL;
	}
	if (webScreen) {
		SDL_FreeSurface (webScreen);
		webScreen = NULL;
	}
}

SDL_Surface *
SDL_SetVideoMode (int width, int height, int bpp, Uint32 flags)
{
	Uint32 windowFlags = SDL_WINDOW_SHOWN;
	(void)bpp;

	DestroyVideo ();

	if (flags & SDL_FULLSCREEN) {
		windowFlags |= SDL_WINDOW_FULLSCREEN_DESKTOP;
		webFullscreen = 1;
	}

	webWindow = SDL_CreateWindow (webTitle, SDL_WINDOWPOS_CENTERED, SDL_WINDOWPOS_CENTERED,
								  width, height, windowFlags);
	if (!webWindow) {
		return NULL;
	}

	webRenderer = SDL_CreateRenderer (webWindow, -1, SDL_RENDERER_ACCELERATED);
	if (!webRenderer) {
		webRenderer = SDL_CreateRenderer (webWindow, -1, 0);
	}
	if (!webRenderer) {
		return NULL;
	}
	SDL_RenderSetLogicalSize (webRenderer, width, height);

	webTexture = SDL_CreateTexture (webRenderer, SDL_PIXELFORMAT_ARGB8888,
									SDL_TEXTUREACCESS_STREAMING, width, height);
	if (!webTexture) {
		return NULL;
	}

	webScreen = SDL_CreateRGBSurfaceWithFormat (0, width, height, 32, SDL_PIXELFORMAT_ARGB8888);
	if (!webScreen) {
		fprintf (stderr, "xb: screen surface creation failed\n");
		return NULL;
	}

	webVideoInfo.hw_available = 0;
	webVideoInfo.wm_available = 1;
	webVideoInfo.blit_hw = 0;
	webVideoInfo.blit_hw_CC = 0;
	webVideoInfo.blit_hw_A = 0;
	webVideoInfo.blit_sw = 1;
	webVideoInfo.blit_sw_CC = 1;
	webVideoInfo.blit_sw_A = 1;
	webVideoInfo.blit_fill = 1;
	webVideoInfo.video_mem = 0;
	webVideoInfo.vfmt = webScreen->format;

	return webScreen;
}

SDL_Surface *
SDL_GetVideoSurface (void)
{
	return webScreen;
}

const SDL_VideoInfo *
SDL_GetVideoInfo (void)
{
	static SDL_PixelFormat fallbackFormat;

	if (!webVideoInfo.vfmt) {
		SDL_zero (fallbackFormat);
		fallbackFormat.BitsPerPixel = 32;
		fallbackFormat.BytesPerPixel = 4;
		fallbackFormat.Rmask = 0x00FF0000;
		fallbackFormat.Gmask = 0x0000FF00;
		fallbackFormat.Bmask = 0x000000FF;
		fallbackFormat.Amask = 0xFF000000;
		webVideoInfo.vfmt = &fallbackFormat;
	}
	return &webVideoInfo;
}

void
XBWeb_Present (SDL_Surface *surface)
{
	if (!surface || !webTexture || surface != webScreen) {
		return;
	}
	SDL_UpdateTexture (webTexture, NULL, surface->pixels, surface->pitch);
	SDL_RenderClear (webRenderer);
	SDL_RenderCopy (webRenderer, webTexture, NULL, NULL);
	SDL_RenderPresent (webRenderer);
}

/* web port: feed engine key events from the on-screen touch controls. */
enum
{
	XBWEB_KEY_UP = 0,
	XBWEB_KEY_DOWN,
	XBWEB_KEY_LEFT,
	XBWEB_KEY_RIGHT,
	XBWEB_KEY_STOP,
	XBWEB_KEY_BOMB,
	XBWEB_KEY_SPECIAL,
	XBWEB_KEY_PAUSE,
	XBWEB_KEY_BACK,
	XBWEB_KEY_SELECT
};

int
XBWeb_SendKey (int action, int down)
{
	SDL_Event event;
	SDL_Keycode sym;

	switch (action) {
	case XBWEB_KEY_UP:		sym = SDLK_UP;			break;
	case XBWEB_KEY_DOWN:	sym = SDLK_DOWN;		break;
	case XBWEB_KEY_LEFT:	sym = SDLK_LEFT;		break;
	case XBWEB_KEY_RIGHT:	sym = SDLK_RIGHT;		break;
	case XBWEB_KEY_STOP:	sym = SDLK_BACKSPACE;	break;
	case XBWEB_KEY_BOMB:	sym = SDLK_RETURN;		break;
	case XBWEB_KEY_SPECIAL:	sym = SDLK_TAB;			break;
	case XBWEB_KEY_PAUSE:	sym = SDLK_p;			break;
	case XBWEB_KEY_BACK:	sym = SDLK_ESCAPE;		break;
	case XBWEB_KEY_SELECT:	sym = SDLK_SPACE;		break;
	default:
		return 0;
	}

	SDL_zero (event);
	event.type = down ? SDL_KEYDOWN : SDL_KEYUP;
	event.key.state = down ? SDL_PRESSED : SDL_RELEASED;
	event.key.keysym.sym = sym;
	event.key.keysym.scancode = SDL_GetScancodeFromKey (sym);
	event.key.keysym.mod = KMOD_NONE;
	return SDL_PushEvent (&event) > 0;
}

void
SDL_UpdateRect (SDL_Surface *surface, Sint32 x, Sint32 y, Uint32 w, Uint32 h)
{
	SDL_Rect rect;

	if (!surface || !webTexture || surface != webScreen) {
		return;
	}
	if (w == 0 || h == 0) {
		SDL_UpdateTexture (webTexture, NULL, surface->pixels, surface->pitch);
		return;
	}
	rect.x = x;
	rect.y = y;
	rect.w = (int)w;
	rect.h = (int)h;
	SDL_UpdateTexture (webTexture, &rect,
					   (const Uint8 *)surface->pixels + y * surface->pitch +
					   x * surface->format->BytesPerPixel, surface->pitch);
}

void
SDL_UpdateRects (SDL_Surface *surface, int numrects, SDL_Rect *rects)
{
	int i;

	for (i = 0; i < numrects; i++) {
		SDL_UpdateRect (surface, rects[i].x, rects[i].y, rects[i].w, rects[i].h);
	}
}

int
SDL_Flip (SDL_Surface *surface)
{
	XBWeb_Present (surface);
	return 0;
}

SDL_Surface *
SDL_DisplayFormat (SDL_Surface *surface)
{
	if (!surface) {
		return NULL;
	}
	return SDL_ConvertSurfaceFormat (surface, SDL_PIXELFORMAT_ARGB8888, 0);
}

SDL_Surface *
SDL_DisplayFormatAlpha (SDL_Surface *surface)
{
	return SDL_DisplayFormat (surface);
}

int
SDL_SetColors (SDL_Surface *surface, SDL_Color *colors, int firstcolor, int ncolors)
{
	if (!surface || !surface->format || !surface->format->palette) {
		return 0;
	}
	return SDL_SetPaletteColors (surface->format->palette, colors, firstcolor, ncolors);
}

int
SDL_WM_ToggleFullScreen (SDL_Surface *surface)
{
	(void)surface;
	if (!webWindow) {
		return 0;
	}
	webFullscreen = !webFullscreen;
	if (SDL_SetWindowFullscreen (webWindow, webFullscreen ? SDL_WINDOW_FULLSCREEN_DESKTOP : 0) != 0) {
		webFullscreen = !webFullscreen;
		return 0;
	}
	return 1;
}

SDL_GrabMode
SDL_WM_GrabInput (SDL_GrabMode mode)
{
	if (!webWindow) {
		return webGrab;
	}
	if (mode == SDL_GRAB_QUERY) {
		return webGrab;
	}
	webGrab = mode;
	SDL_SetWindowGrab (webWindow, mode == SDL_GRAB_ON ? SDL_TRUE : SDL_FALSE);
	return webGrab;
}

int
SDL_WM_IconifyWindow (void)
{
	if (webWindow) {
		SDL_MinimizeWindow (webWindow);
	}
	return 1;
}

void
SDL_WM_SetCaption (const char *title, const char *icon)
{
	if (title) {
		strncpy (webTitle, title, sizeof (webTitle) - 1);
		webTitle[sizeof (webTitle) - 1] = '\0';
	}
	if (icon) {
		strncpy (webIconTitle, icon, sizeof (webIconTitle) - 1);
		webIconTitle[sizeof (webIconTitle) - 1] = '\0';
	}
	if (webWindow) {
		SDL_SetWindowTitle (webWindow, webTitle);
	}
}

void
SDL_WM_GetCaption (char **title, char **icon)
{
	if (title) {
		*title = webTitle;
	}
	if (icon) {
		*icon = webIconTitle;
	}
}

void
SDL_WM_SetIcon (SDL_Surface *icon, Uint8 *mask)
{
	(void)icon;
	(void)mask;
}
