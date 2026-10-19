# Top Down Shooter

Flux watches `games/charts/tds` in the private Gitea OCI registry for stable
versions `>=0.0.2 <1.0.0`. The chart supplies immutable image digests.

The internal player origin is `https://tds.lokiraze.dev` (standalone shell at
`/tds`). Identity's `/games/tds` federation assets redirect to this origin;
TDS owns its own `/api` proxy. Login remains in the Identity portal at
`https://nsg.lokiraze.dev`. The privileged admin service is disabled.

Bootstrap creates the `tds` PostgreSQL role/database on the shared server and
loads the catalog from `top-down-shooter` tag `v0.0.2`, `config/seed.sql`, only
when the public schema is empty. This is initial content, not an upgrade
migration. The bootstrap must complete before the API starts.

Runtime credentials are SOPS encrypted. The API uses Identity's player signing
key, shared Redis database 2 with prefix `nsg:tds:`, and the shared authenticated
NATS service. One Agones server uses dynamic LAN UDP ports. No additional PVC
is required: game assets are in the server image and persistent data uses the
existing PostgreSQL and Redis volumes.

NATS is core NATS, without durable result delivery across API outages. Native
client download archives are not provisioned; `downloads.existingClaim` remains
unset. These manifests do not claim native gameplay or downloads are verified.

After merge, check both Flux Kustomizations, the HelmRelease, API health,
Identity federation loading, and the Agones Ready state. Then verify a real
login, allocation and native match before calling the game playable.
