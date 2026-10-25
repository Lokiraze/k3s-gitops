# No Shame Games

Shared LAN-only dependencies for games and Identity. This initial deployment creates:

- PostgreSQL 17 on Odin's internal disk, with separate `identity` and `steamtactics` database owners. Services connect to `postgres.nsg.svc.cluster.local:5432`.
- Redis at `redis.nsg.svc.cluster.local:6379`, authenticated and shared by games, with AOF persistence on Odin’s internal disk. Writes are synced every second. The 128Mi dataset limit uses `noeviction`: writes fail when full instead of silently discarding game state. The container has 384Mi headroom for persistence rewrites.

Credentials are in the SOPS-encrypted `nsg-dependencies` Secret. Applications must reference the appropriate database password, not the PostgreSQL superuser. PostgreSQL initialization creates empty databases only; application migrations create their schemas. Changing an initialization password in the Secret does not rotate an existing database role's password.

## Before merging / first activation

Run the scoped `ansible/playbooks/nsg-storage.yaml` playbook with the existing Ansible inventory and decryption setup. It verifies the root mount and creates `/var/lib/homelab/app-data/nsg-postgres` and `/var/lib/homelab/app-data/nsg-redis` on Odin. No existing data is reset. PostgreSQL and Redis cannot mount their local volumes until this directory exists.

Flux discovers this namespace through the existing recursive apps source. The PVs and PVCs are protected from pruning; each PV has Retain reclaim policy. The advertised capacities (20Gi PostgreSQL, 1Gi Redis) are not filesystem quotas and do not preallocate disk space. This is single-node storage: Odin downtime also means database downtime.

No routes, LoadBalancers, development seed accounts, Identity application, game workloads, NATS, or Agones are deployed here yet. ClusterIP limits normal exposure to cluster networking, but is not a pod-level isolation policy.

Before storing real accounts or game progress, configure and test PostgreSQL backups and restore. Retained local storage is not a backup. Backup destination and schedule remain part of the cluster integration work.

After Flux applies: check both deployments are Ready, verify authenticated connections to each database and Redis, and verify unauthenticated Redis connections are rejected. This configuration has not yet been live-deployed or runtime-verified.

## Private Gitea registry

The SOPS-encrypted `gitea-registry` Secret in `nsg` uses a dedicated `read:package` token on Gitea's existing `ci-bot` account, which belongs to `games`. It grants package read access only; it is not a CI publishing credential.

Game and Identity pod specifications must reference `imagePullSecrets: [{name: gitea-registry}]`. Flux OCIRepository resources in `nsg` can use `secretRef: {name: gitea-registry}` for chart downloads. Sources in other namespaces need their own Secret there. The chart must be published before Flux can fetch it.

An authenticated manifest request for `games/colony:latest` succeeded during credential setup. That checks registry access, not a live Kubernetes image pull or an unpublished Helm chart. The Secret becomes available after merge and Flux reconciliation.

## Agones

The shared controller is managed by the `agones` Flux Kustomization in
`kubernetes/apps/agones-system`, using the official Agones 1.61.0 chart.
Game servers and their `agones-sdk` service account live in `nsg`.
Future game Kustomizations should depend on `agones` so their Fleet resources
are applied only after its HelmRelease and CRDs are ready.

Game APIs allocate through the Kubernetes GameServerAllocation API; the external
allocator and ping services are disabled. Dynamic game ports are 7000–7100 on
the selected node's LAN address (UDP for Colony). HTTP Gateway routes do not
carry that traffic. No router WAN forwarding is required for LAN play.

There is one controller and one extensions replica, with 512Mi memory limits
each. Maintenance can briefly interrupt new allocations. CRD cleanup on
uninstall is disabled to preserve game resources. After Flux installs the chart,
verify a disposable GameServer reaches Ready and can be allocated, then test its
UDP endpoint from a LAN client before declaring gameplay networking ready.

## Shared Redis

Use separate Redis database numbers or application-supported key prefixes for
separate games. Check each application's configuration before assigning it a
database; this isolates names, not memory capacity or administrative commands.
All applications still share the same process, memory limit, and password.
Normal key expiration remains in effect. Persistence does not restore expired
lobbies or make application restart recovery automatic.

AOF `everysec` can lose roughly the last second of writes after a sudden host
failure. Automatic AOF rewriting compacts the log. Redis uses retained local
storage, so a pod replacement can recover data but Odin must be available.
After this change is merged, verify `aof_enabled:1`, `aof_last_write_status:ok`,
and a disposable key surviving a Redis restart before deploying game state.

## Colony

The `colony` Flux Kustomization follows stable chart versions `>=0.0.2 <1.0.0`
from the private Gitea registry. It waits for Agones and the `colony-database`
Job, which creates the Colony PostgreSQL role/database without resetting existing
ones. Credentials and the shared Identity JWT signing key are SOPS-encrypted.
Changing the stored database password later requires a database role rotation;
the initialization Job does not rotate existing passwords.

Colony uses shared Redis database **1**; Identity uses database **0**. Reserve a
separate database or supported key prefix for subsequent games. The API is LAN
only at `https://colony.lokiraze.dev`; this is an API for the native client, not a
player website. Identity remains `https://nsg.lokiraze.dev`.

Admin is disabled because the shipped admin service lacks user authentication.
The Fleet has one server, pinned to Odin with a retained 5Gi local save claim
at `/var/lib/homelab/app-data/colony-saves`. This does not preallocate 5Gi or impose
a filesystem quota. Multiple rolling-update pods can mount the RWO claim on the
same node; the chart separates saves by pod name. This deliberately avoids an
additional RWX storage service. Odin must be available, and retained files
alone do not automatically restore a session into a replacement server.

Chart 0.0.2 emits `maxUnavailable: 0`, rejected by Agones 1.61.0. A Helm
post-render patch sets it to 1; remove the patch when the upstream chart fixes
that setting. This can temporarily leave no unallocated spare during updates.

The published chart documents incompatible token-generator arguments and game
metadata contracts. Deployment readiness does not prove native multiplayer is
working; these application contracts still need verification/fixes in Colony.

## SteamTactics

Flux follows stable private chart versions `>=0.0.5 <1.0.0`. API/player web and
one Agones room use the published image digests. No Redis or NATS is needed by
this runtime. The existing `steamtactics` PostgreSQL owner/database and Identity
player JWT signing key are referenced through the encrypted runtime Secret.

The bootstrap Job seeds only an empty database, before API schema migration.
`seed-configmap.yaml` is copied from SteamTactics tag `v0.0.5` (commit
`41405db2d9309d4b57b48b29026d26e2be59c051`), not a continuously synchronized
catalog. Existing databases are left unchanged; later catalog changes require a
separate deliberate migration. The published test booster pack supplies the
configured starter pack. API artwork initialization copies missing baked-in
files to a retained 1Gi local claim on Odin; the API is pinned there. Run the
NSG storage playbook before merging. This capacity does not preallocate disk or
impose a filesystem quota.

Use `https://nsg.lokiraze.dev/steamtactics` for the Identity-authenticated player.
The portal's `/api` route reaches SteamTactics, while `/identity` keeps reaching
Identity. `/games/steamtactics/*` redirects to `https://steamtactics.lokiraze.dev/*`
for federation assets with CORS allowing the portal origin. The standalone
SteamTactics host serves only a signed-out preview and assets; it is not a
replacement login flow. Browser federation, login and a real completed match
must be verified after installation.

Admin/API administration and admin web are disabled pending authenticated access.
The same Agones 1.61.0 `maxUnavailable: 1` post-render compatibility override used
for Colony is applied to this chart's room Fleet. One ready room provides initial
capacity; multiple simultaneous games may require increasing room replicas.

SteamTactics 0.0.5 also binds rooms to port 8080, which conflicts with the
Agones SDK sidecar's health listener. The Fleet post-render patch moves the
room environment variable and both container/Agones port declarations to 8081.
The named readiness probe follows that port. API and web services stay on 8080.
Remove this override once the upstream chart offers a nonconflicting room port.
