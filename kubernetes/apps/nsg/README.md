# No Shame Games

Shared LAN-only dependencies for games and Identity. This initial deployment creates:

- PostgreSQL 17 on Bahamut's internal disk, with separate `identity` and `steamtactics` database owners. Services connect to `postgres.nsg.svc.cluster.local:5432`.
- Redis at `redis.nsg.svc.cluster.local:6379`, authenticated and configured as a disposable cache. Restarting it discards cached state; never use this instance for durable game state or queues.

Credentials are in the SOPS-encrypted `nsg-dependencies` Secret. Applications must reference the appropriate database password, not the PostgreSQL superuser. PostgreSQL initialization creates empty databases only; application migrations create their schemas. Changing an initialization password in the Secret does not rotate an existing database role's password.

## Before merging / first activation

Run the scoped `ansible/playbooks/nsg-storage.yaml` playbook with the existing Ansible inventory and decryption setup. It verifies the root mount and creates `/var/lib/homelab/app-data/nsg-postgres` on Bahamut. No existing data is reset. PostgreSQL cannot mount its local volume until this directory exists.

Flux discovers this namespace through the existing recursive apps source. Both the PV and PVC are protected from pruning; the PV has Retain reclaim policy. The advertised 20Gi capacity is not a filesystem quota. This is single-node storage: Bahamut downtime also means database downtime.

No routes, LoadBalancers, development seed accounts, Identity application, game workloads, NATS, or Agones are deployed here yet. ClusterIP limits normal exposure to cluster networking, but is not a pod-level isolation policy.

Before storing real accounts or game progress, configure and test PostgreSQL backups and restore. Retained local storage is not a backup. Backup destination and schedule remain part of the cluster integration work.

After Flux applies: check both deployments are Ready, verify authenticated connections to each database and Redis, and verify unauthenticated Redis connections are rejected. This configuration has not yet been live-deployed or runtime-verified.
