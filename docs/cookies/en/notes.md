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
- the no-JavaScript fallback is provided via `<noscript>`.

## Boxed texts and localization

- the default load creates the policy text variants `short` and `full`;
- variants participate in the normal revision lifecycle;
- re-running the load does not create duplicates of the active revision;
- public labels and fallback strings are supplied in Russian localization.

## Interface behavior

- captions and explanations are consistent with the `dismiss` and re-display modes;
- bot suppression settings are configured separately from the main status logic;
- an optional media and icon slot is supported;
- the scenario for refusing optional cookies is recorded as a separate action.
