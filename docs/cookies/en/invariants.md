# Cookie module: key invariants

- [Go to cookies section](./README.md)
- [To the general documentation section](../README.md)

## Banner state and consent state are different

- Displaying and closing a banner does not equal consent;
- `dismiss` does not create or revoke consent;
- banner status fields (`dismissed_at`, `decided_at`) are maintained separately from consent records.

## Server database - source of truth

- the cookie decision is stored on the server;
- the anonymous script is stored in the database with a token;
- Once logged in, anonymous entries can be linked to the user.

## Replay and `outdated` are different mechanisms

- `outdated` appears when the relevant policy revision changes;
- repeat display by interval controls only the visibility of the banner;
- spaced repeat exposure does not change consent status by itself.

## Banner texts are separated from the cookie policy

- banner editions (`CookieBannerRevision`) are published separately from `CookiePolicyRevision`;
- publication of a banner edition does not translate consent into `outdated`.
