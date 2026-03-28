/*
 * lang.h  —  Multi-language string table
 * Supports: EN (English), TH (Thai)
 * Live switch — no restart needed.
 */

#ifndef LANG_H
#define LANG_H

typedef enum { LANG_EN = 0, LANG_TH = 1 } LangID;

/* Current active language — write to change */
extern LangID g_lang;

/* Get localised string by key */
const char *L(const char *key);

/* Toggle between EN / TH */
void lang_toggle(void);

/* Language display name for UI button */
const char *lang_name(void);

#endif /* LANG_H */
