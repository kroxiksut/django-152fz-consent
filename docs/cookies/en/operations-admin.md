# Cookie module: use and administration

- [Go to cookies section](./README.md)
- [To the general documentation section](../README.md)

## What kind of document is this

The document describes the working scenario for using the cookie module:
- how to include a module in a project;
- where categories, policies and banners are configured in the administrative panel;
- which sections in the administrative panel are for viewing only;
- what commands to use for initial initialization and maintenance.

## Quick launch path

1. Connect apps and routes.
2. Perform migrations.
3. Run initial boxed data initialization.
4. Check the cookie categories and integrations registry.
5. Prepare and publish an edition of the cookie policy.
6. Prepare and publish an edited cookie banner.
7. Connect the banner to the website template.
8. Check the settings page `/cookies/` and banner actions `/cookies/banner/`.

## Connection to the project

### Applications

Make sure `INSTALLED_APPS` has:
- `django_cookies_152fz`;
- `django_consent_152fz` (if a common loop of consents and settings checks is used).

### Routes

Connect the cookie module routes:

```python
from django.urls import include, path

urlpatterns = [
    path("", include("django_cookies_152fz.urls")),
]
```

Available routes:
- `/cookies/` — category selection management page;
- `/cookies/banner/` — banner action handler.

### Sample

Include the banner tag in the base template:

```django
{% load cookies_tags %}
...
{% render_cookie_banner %}
```

## Settings in `settings.py`

The basic configuration of the cookie module is set in `DJANGO_152FZ_COOKIES`.

```python
DJANGO_152FZ_COOKIES = {
    "enable_cookies": True,
    "default_cookie_category_codes": ["necessary"],
    "cookie_banner": {
        "bootstrap_initial_revision": True,
        "preferences_page_template": "django_cookies_152fz/cookie_preferences.html",
        "banner_variant": "card",
        "consent_ui_variant": "panel",
        "reconsent_notice_variant": "inline",
        "text_preset": "ru_balanced",
    },
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
    },
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
    },
}
```

Where to configure what:
- display behavior and banner options: `cookie_banner`;
- technical behavior in request and domain: `cookie_runtime`;
- cleaning and audit volumes: `cookie_retention`.

## Primary initialization

After migrations run:

```bash
python manage.py bootstrap_152fz_cookie_defaults
```

The team creates:
- boxed cookie categories;
- starting version of the cookie policy;
- starting edition of the cookie banner.

## Full menu map of the administrative panel

All registered cookie entities are listed below.

### `Настройки админ-инструментов cookie`

What is this:
- a single entry for technical settings of the administrative panel.

What can be configured:
- `csv_export_delimiter` — CSV export separator.

Peculiarities:
- access only to superuser;
- the entry cannot be deleted;
- You can only add one entry.

### `Cookie-категории`

What is this:
- directory of categories for grouping cookies and building a snapshot in the policy edition.

What can be configured:
- code, title, description;
- mandatory category;
- sort order;
- activity.

When to change:
- when a new processing category appears or classification changes.

### `Элементы cookie-реестра`

What is this:
- a register of technical integrations (cookies and scripts) that are based on the user’s decision.

What can be configured:
- integration code;
- category;
- supplier;
- appointment;
- shelf life;
- cleaning strategy;
- source(`src_url`);
- activity.

When to change:
- when connecting/disconnecting external systems and analytics.

### `Текстовые пресеты cookie-policy`

What is this:
- cookie policy text templates.

What can be configured:
- preset code and title;
- policy text;
- signs of a boxed/custom version;
- activity.

Actions:
- cloning selected presets into custom presets.

### `Редакции cookie-policy`

What is this:
- versioned versions of the cookie policy text that are published and become active.

What can be configured:
- format and text of the editorial;
- snapshot of categories;
- a sign of an active editorial team.

Actions:
- publication of the selected boxed version of the text;
- creating a custom draft from a boxed version;
- cloning selected editions into drafts.

Important:
- when published, a new active edition disables the previous one;
- the registry is synchronized into a revision snapshot;
- previous valid consents are converted to obsolete.

### `Текстовые пресеты cookie-баннера`

What is this:
- cookie banner text templates.

What can be configured:
- headings, captions, button texts, texts for mode without JavaScript;
- signs of a boxed/custom version;
- activity.

Actions:
- cloning selected presets into custom presets.

### `Редакции cookie-баннера`

What is this:
- versioned versions of the cookie banner (texts, display options and visual parameters).

Where are the settings:
- block `Тексты`: all custom banner signatures;
- block `Варианты отображения`: banner option, selection interface type, notification option;
- block `Визуальная настройка`: color and visual parameters;
- block `Видимость и кнопка закрытия`: show, close, blocking behavior and mobile overrides;
- block `Устаревшие поля совместимости`: backward compatibility fields.

Actions:
- cloning selected banner editions into custom drafts.

Important:
- For boxed editions, protected text fields are read-only;
- When published, a new active edition disables the previous one.

### `Элементы реестра редакции cookie-policy`

What is this:
- a snapshot of the integration register at the time of a specific policy revision.

Mode:
- Viewing only, no editing.

Purpose:
- audit of compliance with the published policy and composition of integrations.

### `Записи cookie-согласий`

What is this:
- the final state of category selection for the subject.

Mode:
- viewing only.

Purpose:
- control of current/outdated status;
- search by user, anonymous token, request ID.

### `События cookie-согласий`

What is this:
- Log of consent events (acceptance, update, deprecation and related actions).

Mode:
- viewing only.

Actions:
- export selected events to CSV.

### `Состояния cookie-баннера`

What is this:
- server state of the banner life cycle by subject.

Mode:
- viewing only.

Purpose:
- diagnostics of replay, close, selected action and blocking mode.

## Where to configure by task

### You need to change the cookie policy text

1. Open `Текстовые пресеты cookie-policy` and prepare the variant.
2. In `Редакции cookie-policy`, create a revision (or draft from a preset).
3. Publish the editorial office as active.

### You need to change the appearance/behavior of the banner

1. Open `Текстовые пресеты cookie-баннера` and correct the texts.
2. Open `Редакции cookie-баннера`.
3. Set up the blocks `Варианты отображения`, `Визуальная настройка`, `Видимость и кнопка закрытия`.
4. Publish the editorial.

### Need to add a new integration (script/cookie)

1. Add or update the category in `Cookie-категории` (if required).
2. Add an entry to `Элементы cookie-реестра`.
3. Check that the active `Редакции cookie-policy` reflects the current snapshot.

### Need to export events to CSV

1. Open `События cookie-согласий`.
2. Select entries.
3. Apply action `Экспортировать выбранные события в CSV`.
4. If necessary, specify the delimiter in `Настройки админ-инструментов cookie` in advance.

### Need to clear old audit records

Run:

```bash
python manage.py cleanup_152fz_cookie_audit --dry-run
python manage.py cleanup_152fz_cookie_audit
```

Cleaning parameters are set in `DJANGO_152FZ_COOKIES["cookie_retention"]`.

## Practice from demo site

Below are solutions that showed stable behavior on the demo site and are suitable as a working implementation template.

### Embedding a banner

- the banner is connected once in the base website template via `{% render_cookie_banner %}`;
- this covers all public pages without duplicating template markup;
- A separate link in the top menu to the cookie settings page is not required if the banner reopen button is enabled.

### Routes

- the main set of project routes is connected separately from the cookie routes;
- a separate prefix `/cookies/` is used for the cookie module;
- this simplifies diagnostics and reduces the risk of route name collisions.

### Working profile settings

For a public site, the demo consistently used the following scheme:
- `cookie_banner.show_launcher=True`;
- `cookie_banner.show_preferences_link=False`;
- `cookie_runtime.hide_for_bots=True`;
- `cookie_runtime.preview_param="cookie_banner_preview"`;
- an explicit list of robot templates in `cookie_runtime.bot_patterns`.

The meaning of the scheme:
- the user can always reopen the banner with a button;
- extra entry points to the settings page do not overload the interface;
- For search robots, the banner does not interfere with crawling pages;
- Banner preview mode is available manually via the URL parameter.

### Data Initialization

- after migrations, `bootstrap_152fz_cookie_defaults` is launched;
- for a demonstration stand, automation of this step via `post_migrate` is acceptable;
- For a production environment, it is better to use an explicit command run in the deployment script to avoid implicit data changes.

### Checks after changes

After each change in cookie settings in the demo, the following were necessarily rechecked:
- displaying the banner and page `/cookies/` in Russian and English;
- saving category selection;
- re-selection;
- no errors in the browser console and in the server log;
- absence of regressions in the base site (public pages, forms, login, administrative panel).

A separate checklist from the demo: `demo/notes/smoke-checklist.md`.

## Integration Inventory

To check the compliance of the registry with categories:

```bash
python manage.py inventory_152fz_cookie_integrations
```

This is a supporting report. The classification decision is made by the operator.

#### CSV delimiter behavior for event export

- `Cookie consent events` export uses `csv_export_delimiter` from `Cookie admin settings`.
- Allowed delimiters: `,`, `;`, `TAB` (`\t`), `|`.
- Invalid values safely fall back to `,`.

