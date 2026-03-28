/*
 * main.c  —  BlackCat SMART entry point
 * Requests admin elevation then launches GUI.
 */

#include "../include/smart.h"
#include <windows.h>

/* Defined in gui.cpp */
extern int gui_main(void);

static int is_admin(void)
{
    BOOL elevated = FALSE;
    HANDLE token  = NULL;
    if (OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &token)) {
        TOKEN_ELEVATION elev = {0};
        DWORD len = sizeof(elev);
        if (GetTokenInformation(token, TokenElevation, &elev, sizeof(elev), &len))
            elevated = elev.TokenIsElevated;
        CloseHandle(token);
    }
    return (int)elevated;
}

static void relaunch_as_admin(void)
{
    wchar_t path[MAX_PATH];
    GetModuleFileNameW(NULL, path, MAX_PATH);
    ShellExecuteW(NULL, L"runas", path, NULL, NULL, SW_SHOWNORMAL);
}

int WINAPI WinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance,
                   LPSTR lpCmdLine, int nCmdShow)
{
    (void)hInstance; (void)hPrevInstance;
    (void)lpCmdLine; (void)nCmdShow;

    if (!is_admin()) {
        int r = MessageBoxW(NULL,
            L"BlackCat SMART needs Administrator privileges\n"
            L"to read SMART data directly from hardware.\n\n"
            L"Relaunch as Administrator?",
            L"BlackCat SMART",
            MB_YESNO | MB_ICONQUESTION);
        if (r == IDYES)
            relaunch_as_admin();
        return 0;
    }

    return gui_main();
}
