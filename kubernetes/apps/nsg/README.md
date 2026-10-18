# No Shame Games

Shared LAN-only dependencies for games and Identity. This initial deployment creates:

- PostgreSQL 17 on Bahamut's internal disk, with separate `identity` and `steamtactics` database owners. Services connect to `postgres.nsg.svc.cluster.local:5432`.
- Redis at `redis.nsg.svc.cluster.local:6379`, authenticated and shared by games, with AOF persistence on Bahamut’s internal disk. Writes are synced every second. The 128Mi dataset limit uses `noeviction`: writes fail when full instead of silently discarding game state. The container has 384Mi headroom for persistence rewrites.

Credentials are in the SOPS-encrypted `nsg-dependencies` Secret. Applications must reference the appropriate database password, not the PostgreSQL superuser. PostgreSQL initialization creates empty databases only; application migrations create their schemas. Changing an initialization password in the Secret does not rotate an existing database role's password.

## Before merging / first activation

Run the scoped `ansible/playbooks/nsg-storage.yaml` playbook with the existing Ansible inventory and decryption setup. It verifies the root mount and creates `/var/lib/homelab/app-data/nsg-postgres` and `/var/lib/homelab/app-data/nsg-redis` on Bahamut. No existing data is reset. PostgreSQL and Redis cannot mount their local volumes until this directory exists.

Flux discovers this namespace through the existing recursive apps source. The PVs and PVCs are protected from pruning; each PV has Retain reclaim policy. The advertised capacities (20Gi PostgreSQL, 1Gi Redis) are not filesystem quotas and do not preallocate disk space. This is single-node storage: Bahamut downtime also means database downtime.

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
storage, so a pod replacement can recover data but Bahamut must be available.
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
The Fleet has one server, pinned to Bahamut with a retained 5Gi local save claim
at `/var/lib/homelab/app-data/colony-saves`. This does not preallocate 5Gi or impose
a filesystem quota. Multiple rolling-update pods can mount the RWO claim on the
same node; the chart separates saves by pod name. This deliberately avoids an
additional RWX storage service. Bahamut must be available, and retained files
alone do not automatically restore a session into a replacement server.

Chart 0.0.2 emits `maxUnavailable: 0`, rejected by Agones 1.61.0. A Helm
post-render patch sets it to 1; remove the patch when the upstream chart fixes
that setting. This can temporarily leave no unallocated spare during updates.

The published chart documents incompatible token-generator arguments and game
metadata contracts. Deployment readiness does not prove native multiplayer is
working; these application contracts still need verification/fixes in Colony.
