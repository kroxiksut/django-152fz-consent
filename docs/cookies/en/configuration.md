# Cookie module: configuration

- [Go to cookies section](./README.md)
- [To the general documentation section](../README.md)

## Where is the configuration set?

The cookie module configuration is set in `settings.py` in the `DJANGO_COOKIES_152FZ` dictionary.

```python
DJANGO_COOKIES_152FZ = {
    "enable_cookies": True,
    "default_cookie_category_codes": ["necessary"],
    "cookie_banner": {...},
    "cookie_runtime": {...},
    "cookie_retention": {...},
}
```

## Root keys

### `enable_cookies`

- Type: `bool`
- Purpose: Global enablement of the cookie stream.
- Default: `True`

### `default_cookie_category_codes`

- Type: `list[str]`
- Purpose: Default mandatory category codes.
- Default: `["necessary"]`

## Section `cookie_banner`

This section defines the basic parameters of the banner and settings page.

```python
"cookie_banner": {
    "bootstrap_initial_revision": True,
    "preferences_page_template": "django_cookies_152fz/cookie_preferences.html",
    "banner_variant": "card",
    "consent_ui_variant": "panel",
    "reconsent_notice_variant": "inline",
    "text_preset": "ru_balanced",
}
```

Keys:
- `bootstrap_initial_revision`: automatically create a starting version of the banner.
- `preferences_page_template`: path to the page template `/cookies/`.
- `banner_variant`: banner option (`bar`, `card`, `modal`).
- `consent_ui_variant`: selection interface option (`inline`, `panel`).
- `reconsent_notice_variant`: re-consent notification option (`inline`, `alert`).
- `text_preset`: text preset code (`ru_balanced`, `ru_formal`, `ru_compact`).

## Section `cookie_runtime`

The section defines the behavior of the banner in the request and environment.

```python
"cookie_runtime": {
    "force_banner": False,
    "preview_param": "cookie_banner_preview",
    "custom_css_url": "",
    "custom_js_url": "",
    "hide_for_bots": True,
    "bot_patterns": [],
    "user_agent_mode": "all",
    "shared_subdomain": False,
    "site_domain": "",
    "cookie_domain": "",
    "geo_signal_hook": "",
}
```

Keys:
- `force_banner`: force the banner to be shown.
- `preview_param`: URL parameter name for preview mode.
- `custom_css_url`: additional path to custom styles.
- `custom_js_url`: Additional path to the user script.
- `hide_for_bots`: hide banner for robots.
- `bot_patterns`: custom robot recognition templates.
- `user_agent_mode`: user agent processing mode (`off`, `all`, `unique`).
- `shared_subdomain`: Enable common mode for subdomains.
- `site_domain`: Site domain for safe return checks.
- `cookie_domain`: Anonymous token cookie setting domain.
- `geo_signal_hook`: path to the geosignal object being called.

## Section `cookie_retention`

This section defines the rules for clearing audits and volume limits.

```python
"cookie_retention": {
    "batch_size": 500,
    "records_older_than_days": None,
    "events_older_than_days": None,
    "banner_states_older_than_days": None,
    "records_max_count": None,
    "events_max_count": None,
    "banner_states_max_count": None,
    "private_records_older_than_days": None,
    "private_events_older_than_days": None,
    "private_signal_paths": [],
    "protect_current_records": True,
}
```

Keys:
- `batch_size`: removal chunk size.
- `records_older_than_days`: retention period for consent records.
- `events_older_than_days`: retention period for consent events.
- `banner_states_older_than_days`: retention period for banner states.
- `records_max_count`: limit on number of consent records.
- `events_max_count`: limit on the number of consent events.
- `banner_states_max_count`: limit on the number of banner states.
- `private_records_older_than_days`: separate term for private entries.
- `private_events_older_than_days`: separate term for private events.
- `private_signal_paths`: private event source paths.
- `protect_current_records`: protection of current records from deletion.

## What is configured in the administrative panel and what in `settings.py`

In the administrative panel:
- cookie categories;
- integration registry;
- editions of the cookie policy;
- cookie banner editions;
- text presets;
- CSV export separator.

In `settings.py`:
- technical display behavior;
- domain parameters and processing modes;
- audit cleanup rules;
- connecting custom style files and scripts.

## Configuration profile from demo site

The demo site for the public circuit used the following working profile:

```python
DJANGO_COOKIES_152FZ = {
    "enable_cookies": True,
    "cookie_banner": {
        "bootstrap_initial_revision": True,
        "banner_variant": "card",
        "consent_ui_variant": "panel",
        "text_preset": "ru_balanced",
        "show_launcher": True,
        "show_preferences_link": False,
    },
    "cookie_runtime": {
        "force_banner": False,
        "preview_param": "cookie_banner_preview",
        "custom_css_url": "",
        "custom_js_url": "",
        "hide_for_bots": True,
        "bot_patterns": [
            "googlebot",
            "yandexbot",
            "bingbot",
            "duckduckbot",
            "crawler",
            "spider",
            "bot",
        ],
        "user_agent_mode": "all",
        "shared_subdomain": False,
        "site_domain": "",
        "cookie_domain": "",
        "geo_signal_hook": "",
    },
}
```

This profile showed predictable behavior:
- the banner is available on all pages via the reopen button;
- the interface is not overloaded with a separate link in the top menu;
- robots are not shown the visual layer of the banner;
- There is a manual preview option to check the display.

More details on the sections of the administrative panel: [Usage, admin menu and settings](./operations-admin.md).

### CSV delimiter for event export

`csv_export_delimiter` in `CookieAdminSettings` controls the separator for `CookieConsentEvent` admin CSV export.

Allowed values: `,`, `;`, `\t`, `|`.
Invalid values fall back to `,`.

