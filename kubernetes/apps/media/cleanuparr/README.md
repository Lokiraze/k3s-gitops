# Cleanuparr

Open https://cleanuparr.lokiraze.dev on the home network and sign in through
Authelia. Complete Cleanuparr's initial setup, then add the arr applications and
download client through its settings. Queue cleanup is disabled on a fresh
installation; configure and review its stall rules before enabling it.

Configuration is retained on Phoenix at
`/var/lib/homelab/app-data/cleanuparr-config`, owned by UID/GID 568. Prepare this
path with `ansible/playbooks/cleanuparr-storage.yaml` before deploying on a fresh
node. Restore it from backup when replacing the node. No download or library
filesystem is mounted; stalled queue handling uses the applications' APIs.
