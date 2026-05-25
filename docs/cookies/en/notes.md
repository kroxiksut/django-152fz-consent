# Cookie module: additional notes

- [Go to cookies section](./README.md)
- [To the general documentation section](../README.md)

## Contract Updates

- a separate cookie router `django_cookies_152fz.urls` is used;
- `cookie_preferences.html` uses a block contract for overrides;
- Banner entry points and settings pages are controlled by settings
`cookie_banner.show_launcher` and `cookie_banner.show_preferences_link`;
- setting `cookie_banner.preferences_page_template` allows you to embed the page
cookie settings in the project layout;
- the fallback script without JavaScript is saved via `<noscript>`.

## Boxed texts and localization

- the default load creates policy text variants `short` and `full`;
- variants participate in the normal revision life cycle;
- restarting the download does not create duplicates of the active edition;
- public signatures and backup strings are supplied in Russian localization.

## Interface behavior

- captions and explanations are consistent with the `dismiss` and replay modes;
- Suppression settings for bots are set separately from the main status logic;
- optional media and icon slot supported;
- The script for refusing optional cookies is saved as a separate action.
