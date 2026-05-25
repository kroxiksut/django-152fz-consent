# Cookie module: texts and design

- [Go to cookies section](./README.md)
- [To the general documentation section](../README.md)

## Purpose

This document describes how to personalize the appearance and texts of the cookie banner:

- what can be customized without editing templates;
- what changes through the administrative panel;
- which is specified via `settings.py`;
- when out-of-the-box options are enough, and when you need your own CSS or JS.

## Where are texts and design stored?

The implementation uses the `CookieBannerRevision` model:

- stores texts, button labels and design parameters;
- published separately from `CookiePolicyRevision`;
- editable via the admin panel without storing arbitrary HTML or JavaScript;
- allows you to release new editions of the appearance regardless of the editions
Cookie Policy

This means that the banner design and banner texts are considered part of
versioned configuration, and not “hardwired” into the template forever.

## What can be changed without editing the code

Through `CookieBannerRevision` you can already configure:

- banner option;
- selection interface option;
- option for notification of re-consent;
- text preset;
- mobile overrides for variant and texts;
- banner position on computers and mobile devices;
- color preset;
- custom colors for key surfaces and buttons;
- internal and intersectional margins;
- dimming transparency;
- visibility of the close button;
- banner behavior after user selection;
- blocking mode until the first explicit choice;
- displaying the opt-out button and individual actions in the mobile version;
- connecting a custom cookie settings page template.

## Basic Display Options

Key option fields:

- `banner_variant`: `bar` | `card` | `modal`;
- `consent_ui_variant`: `inline` | `panel`;
- `reconsent_notice_variant`: `inline` | `alert`;
- `text_preset_code`: `ru_balanced` | `ru_formal` | `ru_compact`.

Practical meaning:

- `bar` is suitable for a discreet compact scenario;
- `card` is suitable for most regular sites and demo stands;
- `modal` is suitable for a tighter focus on user choice;
- `inline` makes the select block shorter;
- `panel` is better when there are more categories and explanations;
- `alert` makes the repeated request more noticeable than `inline`.

## Positioning and Layout

Separate position parameters are already available for the banner:

- `desktop_position`;
- `mobile_position`.

In particular, the lower options and the mode are supported
`bottom_fullwidth` - full-width bottom banner.

Use it like this:

- for a calm, unobtrusive interface - bottom placement;
- for a more explicit choice requirement - a modal banner;
- for a mobile scenario with long texts - the full-width option at the bottom.

## Colors and visual personalization

The visual block `CookieBannerRevision` already supports:

- `color_preset`;
- `custom_bg_color`;
- `custom_text_color`;
- `custom_primary_color`;
- `custom_primary_text_color`;
- `custom_border_color`;
- `custom_surface_color`;
- `custom_overlay_color`.

What does it give:

- you can take a boxed color preset and use it without additional
edits;
- you can customize your brand’s corporate colors using HEX values;
- you can separately control the panel background, text, main button, borders,
secondary substrate and darkening layer.

Restrictions:

- colors undergo basic validation;
- text and background are checked for minimal contrast for readability;
- arbitrary HTML and free inline style as the main design mechanism
are not used.

## Interface Padding and Density

Via `CookieBannerRevision` the following are configured:

- `panel_padding_px`;
- `section_gap_px`;
- `button_gap_px`;
- `overlay_opacity`.

This allows you to:

- make the banner denser for a compact interface;
- on the contrary, defuse it for a calmer visual rhythm;
- enhance or weaken the background darkening of the modal option.

Safe ranges are already limited at the model level, so random edits in
The admin panel should not “break” the layout.

## Mobile Overrides

There are separate overrides for the mobile version:

- `mobile_text_preset_code`;
- `mobile_banner_variant`;
- `mobile_consent_ui_variant`;
- `mobile_reconsent_notice_variant`;
- `mobile_close_control_placement`;
- `mobile_show_close_control`;
- `mobile_show_reject_action`;
- `mobile_blocking_mode_until_choice`;
- `mobile_hide_launcher_after_decision`;
- `mobile_keep_visible_after_accept_all`;
- `mobile_keep_visible_after_required_only`;
- `mobile_keep_visible_after_save_custom`.

If the field is empty or not specified, inheritance from the major version is used.

This is useful when:

- on mobile devices you need a shorter text preset;
- on mobile devices you need a different banner option;
- Close button behavior and banner visibility should be different from desktop
versions.

## Behavior and visibility

At the design and user script level the following are already supported:

- `show_close_control`;
- `close_control_placement`;
- `show_reject_action`;
- `blocking_mode_until_choice`;
- `hide_launcher_after_decision`;
- `keep_visible_after_accept_all`;
- `keep_visible_after_required_only`;
- `keep_visible_after_save_custom`;
- `hide_for_bots_override`.

Practical meaning:

- you can make the banner softer or more strict;
- you can leave the reopen button after the decision or hide it;
- You don’t have to close the banner automatically after certain actions;
- you can control banner display for bot-like requests separately from global ones
settings.

## What is configured via `settings.py`

Not all design lives only in the database. In `DJANGO_COOKIES_152FZ` remain
settings that are best set at the project level:

- `cookie_banner.preferences_page_template` - project page template
  `/cookies/`;
- `cookie_runtime.custom_css_url` - additional path to CSS;
- `cookie_runtime.custom_js_url` - additional path to JS;
- `cookie_runtime.preview_param` - preview parameter;
- `cookie_runtime.hide_for_bots` and related runtime settings.

The division of responsibility is as follows:

- database and admin panel - for texts, options, colors and editorial behavior;
- `settings.py` - for connecting project files and technical settings
environment.

## When the admin is enough, and when you need your own CSS

Usually the admin panel is enough if you need:

- select a banner option;
- switch text preset;
- customize brand colors;
- change padding and transparency;
- make a separate mobile version;
- change the behavior of buttons and display mode.

Custom CSS is needed if required:

- integrate the banner into the existing design system of the project;
- adjust typography that is not among the basic parameters;
- correct rare local interface states;
- adapt the appearance to an existing website theme.

Native JS is only needed for additional design behavior on top
standard contract, but not as the main way to customize texts and styles.

## Recommended Personalization Path

The practically safe order is:

1. Create a custom copy of `CookieBannerRevision` rather than editing
boxed edition directly.
2. Select base `banner_variant`, `consent_ui_variant` and `text_preset`.
3. Adjust colors via `color_preset` and `custom_*_color`.
4. Adjust the padding and transparency.
5. Check mobile overrides separately from the desktop version.
6. Only after this connect `custom_css_url` if standard fields
registration is not enough.

## What is visible in the administrative panel

In the administrative panel, the `Редакции cookie-баннера` section is already divided into
semantic blocks:

- `Тексты`;
- `Варианты отображения`;
- `Визуальная настройка`;
- `Видимость и кнопка закрытия`;
- `Устаревшие поля совместимости`.

Color fields use the browser's native color selection, so the basic
personalization can be done without manually entering all the values.

## Attribute contract in template

The following attributes are published in the markup:

- `data-cookie-banner-contract-version`;
- `data-cookie-banner-variant`;
- `data-cookie-banner-consent-ui`;
- `data-cookie-banner-reconsent-variant`;
- `data-cookie-banner-text-preset`;
- `data-cookie-banner-mobile-text-preset`;
- `data-cookie-banner-mobile-variant`;
- `data-cookie-banner-mobile-consent-ui`.

This is so that project CSS and project scripts can rely on
stable features of the current published edition.

## Lock mode before selection

- at `blocking_mode_until_choice=True` the banner blocks closing until explicit
choice;
- After a saved selection, reopening does not lock the page
automatically.

## Related documents

- [Cookie configuration](./configuration.md)
- [Usage and administrative setup](./operations-admin.md)
- [Cookie module invariants](./invariants.md)
- [Event Contracts and Integrations](./contracts.md)
