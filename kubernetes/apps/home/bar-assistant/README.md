# Bar Assistant

Open `https://bar.lokiraze.dev`. Salt Rim automatically signs in through
Authelia using the existing home account; no separate Bar Assistant password is
needed. The OIDC client permits only `lokiraze`, and Bar Assistant creates or
links the account by email. The new-bar form can include the bundled cocktail
and ingredient collection. Outgoing email is not configured.

The API, Salt Rim web interface, and Meilisearch run on Phoenix. Total container
limits are 1.35 CPU cores, 1408 MiB RAM, and 768 MiB ephemeral storage. Search
indexing uses one thread and a 128 MiB indexing-memory budget. File caching and
sessions avoid a separate Redis service.

Retained local volumes use the prepared PNY SSD:

- `/var/lib/homelab/ssd-data/bar-assistant-data`, owned by `33:33`
- `/var/lib/homelab/ssd-data/bar-assistant-search`, owned by `1000:1000`

These directories were created only after verifying the existing SSD mount and
Lidarr database. The parent SSD mount is already persistent. The local-volume
paths must exist on that mounted SSD; Kubernetes does not create them. Keep the
encrypted app and search keys with the database when backing up or restoring.
Local PV sizes are scheduling metadata, not filesystem quotas.

The HTTPRoute exposes `/bar` for the API, `/search` for Meilisearch, and `/` for
Salt Rim, stripping the two prefixes before forwarding. Bar Assistant validates
its own API tokens after the Authelia SSO exchange; there is no second proxy
login gate. Password login and the registration form are disabled. The API's
registration service stays enabled for SSO provisioning, while Nginx blocks the
public password-registration route. Direct pod access remains limited to the
internal gateway and the API's connection to search. The route also adds a Home
dashboard link automatically.

The OAuth callback is `https://bar.lokiraze.dev/oauth/callback`, handled by Salt
Rim. Authelia reads its signing key from an encrypted Secret mounted as a second
configuration file; its HMAC secret and Bar Assistant's client secret are also
encrypted. The client-secret digest in Authelia's public configuration uses
escaped dollar signs for Flux substitution.

Home Assistant Marketplace has no default Bar Assistant entry. The community
[HA-Bar_Assistant integration](https://github.com/Aesgarth/HA-Bar_Assistant)
offers shopping-list synchronization and cocktail sensors, but its current
code uses API routes removed in Bar Assistant 6. It is not installed here.
