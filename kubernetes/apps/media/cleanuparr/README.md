# Cleanuparr

Open https://cleanuparr.lokiraze.dev on the home network and sign in through
Authelia. Cleanuparr's persisted General → Authentication settings use
`disableAuthForLocalAddresses: true` and `trustForwardedHeaders: false`, so the
internal gateway's requests do not require a second login. The NetworkPolicy
allows only that gateway to reach Cleanuparr's port; keep it in place whenever
local-address authentication bypass is enabled.

A fresh configuration needs Cleanuparr's initial administrator setup once, then
the authentication settings above. Connections and cleanup rules are stored in
its retained configuration. Queue cleanup remains disabled until its stall
rules have been reviewed and enabled.

Configuration is retained on Phoenix at
`/var/lib/homelab/app-data/cleanuparr-config`, owned by UID/GID 568. Prepare this
path with `ansible/playbooks/cleanuparr-storage.yaml` before deploying on a fresh
node. Restore it from backup when replacing the node. No download or library
filesystem is mounted; stalled queue handling uses the applications' APIs.
