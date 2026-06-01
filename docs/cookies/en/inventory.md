# Cookie module: inventory and hints

- [Go to cookies section](./README.md)
- [To the general documentation section](../README.md)

## Recommendation inventory

The minimum recommended inventory scenario has been implemented:
- analysis of known integrations (`CookieRegistryItem`) and the input list;
- category hint: `necessary` / `functional` / `analytics` / `marketing`;
- a mandatory manual-check flag for each result.

Technical entry points:
- `django_cookies_152fz.inventory.build_best_effort_inventory_hints(...)`;
- `django_cookies_152fz.inventory.build_inventory_hints_for_registry_items()`;
- command `inventory_152fz_cookie_integrations`.

## Layer restrictions

- this is a hint layer, not an automatic legal classification;
- a full-fledged page scanner is not a required part of the core;
- automatic analysis of all database tables and external CRMs is not included in this layer;
- inventory launch is disabled by default: `enable_registry_hints=False`.
