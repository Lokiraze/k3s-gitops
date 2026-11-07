# Tactics Battle Arena

Flux watches `games/charts/tactics` in the private Gitea OCI registry for stable
versions `>=0.0.5 <1.0.0`. The published chart supplies immutable image digests
and selects amd64 nodes for its API, player and server.

The LAN player origin is `https://tactics.lokiraze.dev` (standalone shell at
`/tactics`). Identity's `/games/tactics` federation assets redirect to this origin;
Tactics owns its own `/api` proxy. Login remains in the Identity portal at
`https://nsg.lokiraze.dev/tactics`. The privileged admin service is disabled.

Bootstrap creates the `tactics` PostgreSQL role/database on the shared server and
loads the catalog only when the public schema is empty. The seed is copied from
`tactics-battle-arena` tag `v0.0.5`, commit
`d91f15915612909f0634bd42e955dd02519a9a2f`, with the missing equipment
`stat_requirements` column added to match that release's model and inserts,
and two apostrophes in action descriptions escaped for SQL.
It is initial content, not an upgrade migration. Existing databases are left
unchanged, and later catalog updates require a deliberate migration. Changing
the encrypted database password does not rotate an existing PostgreSQL role.
The bootstrap must complete before the API starts its additive schema migration.

Runtime credentials are SOPS encrypted. The API uses Identity's player signing
key, shared Redis database **3** with prefix `nsg:tactics:`, and authenticated
shared NATS with subject `tactics.game.results`. The API and game server share a
dedicated netcode key. Redis databases 0, 1 and 2 remain assigned to Identity,
Colony and TDS respectively; separate databases do not isolate Redis capacity.

One Agones server uses dynamic LAN UDP ports 7000–7100, mapped to container
port 12025. No additional PVC is required: game assets are in the images and
persistent data uses the existing PostgreSQL and Redis volumes. The chart names
workloads `tactics-tactics-api`, `tactics-tactics-player` and
`tactics-tactics-server`. API replacement briefly disconnects WebSockets.

Core NATS does not preserve results across API/broker outages. Native download
archives are not provisioned (`player.downloadsExistingClaim` is unset), and
browser WebTransport gameplay is not configured by the HTTP routes.

After merge, verify both Flux Kustomizations, the HelmRelease, API health,
Identity federation loading and the Agones Ready state. Then verify a real
login, allocation and native match before calling the game playable.
