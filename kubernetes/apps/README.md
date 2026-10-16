# Application recovery definitions

The home, media, security and monitoring applications are present again, with
Frigate recovered from the older configuration tree. These are **suspended
recovery definitions**, not production-ready upgrades. Chart and image versions
remain at historical values except for the tested replacements documented below.
Each app still needs its remaining activation checks.

Every restored application has `spec.suspend: true` in both `ks.yaml` and its
`app/helmrelease.yaml`. Changing only one does not start it. The source GitRepository
is the new `flux-system` repository. Shared legacy substitution values and chart
sources live under `flux-system/app-recovery/`; secrets remain SOPS-encrypted.

| Group | Restored applications |
|---|---|
| Home | Home Assistant, MQTT/Mosquitto, Z-Wave JS UI, Frigate |
| Media | Calibre-Web, Jellyseer, Lidarr, Podfetch, Podgrab, Prowlarr, Radarr, Readarr, Recyclarr, Sonarr, Whisparr |
| Security | Vaultwarden |
| Monitoring | Grafana, kube-prometheus-stack, Kubernetes Dashboard |
| Dashboard | Hajimari |
| External routes | Jellyfin, robo, stash, torrent |

## Changes already made

- Updated HelmRelease and HelmRepository API versions and Flux source references.
- Kept application settings, NFS locations, USB identifiers and encrypted secrets.
- Changed old Ceph/local-path claims to explicit `local-app-data` claims. That
  class uses `kubernetes.io/no-provisioner`, `WaitForFirstConsumer` and `Retain`.
  It never creates empty directories or volumes automatically. Home Assistant
  and Z-Wave, all ten media config claims, Grafana and Prometheus have explicit
  PV/PVC bindings. Frigate still needs its storage/config migration.
- Removed dependencies on the retired nginx and local-path Helm releases.
- Disabled old Ingress generation. Ordinary HTTP services now have internal
  Envoy HTTPRoutes preserving their hostnames. The external-service definitions
  use EndpointSlice resources. Jellyfin preserves its existing public access
  through `envoy-external`; robo, stash and torrent remain internal.
- Corrected Vaultwarden's persistent mount to `/data`.
- Disabled Home Assistant's unauthenticated code-server sidecar and removed
  Dashboard's insecure-login flags and automatic cluster-admin binding.
- Preserved Frigate's USB Coral configuration, explicitly mounted `/dev/bus/usb`,
  and used secret-backed `FRIGATE_*` environment variables for camera URLs.

The original disabled Ingress values remain as migration references. Old nginx
snippets, theme injection, and authentication annotations are not implemented by
these new HTTPRoutes. Prometheus and Kubernetes Dashboard routing still require
review rather than guessing their backend/TLS configuration.

## Checks before enabling an app

Home Assistant's local volume is assigned to Bahamut; Z-Wave's is assigned to
Ifrit, alongside its existing radio. All local volumes use
`/var/lib/homelab/app-data/<claim-name>`. Ifrit is now an initial worker with a
checked SD-card identity; final data ownership must be checked before activation.
This is not an SSD-backed volume on Ifrit. Production data directories are not
created by these manifests.

After a final restore and offline integrity/ownership checks, the restore
operator must write `.restore-verified` inside the data directory, containing
exactly the PVC name. Init containers
check that marker and the essential application configuration before startup.
Do not create the marker for an empty directory. Missing local paths fail mount;
unverified directories fail initialization. Keep the applications suspended until
their final restores and node placement are accepted.

| Data | Owning node | Restore layout |
|---|---|---|
| Home Assistant | Bahamut | Config files at volume root |
| Z-Wave | Ifrit | Original controller store at volume root |
| Ten media config claims | Phoenix | Each app's original config at its volume root |
| Grafana | Odin | `grafana.db` at volume root |
| Prometheus (one replica) | Odin | Snapshot block directories under `prometheus-db/` |

Media and monitoring have the same verified-restore marker gate. Prometheus's
marker belongs at the volume root, alongside `prometheus-db/`; its operator-owned
claim is explicitly pre-bound to the retained PV. Grafana uses an existing claim.
Each monitoring claim requests 10Gi for binding; this is not an enforced quota.

Static PV capacities are binding metadata, **not filesystem quotas**. The volumes
share their node's root filesystem and require free-space monitoring. Retained
PVs and their StorageClass are excluded from Flux pruning; removing an app does
not constitute permission to erase its data.

1. Select a supported image/chart version and review its data/config migration.
   Historical image availability and compatibility with k3s 1.37 are not proven
   by a successful Helm render. Check maintenance status of old projects such as
   Readarr, Podgrab and Hajimari before choosing to continue or replace them.
2. Choose the owning node, create retained local storage and restore its data.
   Verify UID/GID, the actual mounted path, and recovery after reboot. Do not
   enable stateful apps against empty claims. Frigate also needs its old beta
   configuration migrated to a supported version; the saved camera definitions
   are a reference, not a validated current Frigate configuration.
3. For Z-Wave, verify the existing controller path and `usb=zwave` node label;
   for Frigate, verify the `tpu=google-coral` label and hardware access. The Pis
   Ramuh and Shiva remain deferred; Ifrit is an initial worker for Z-Wave.
4. Verify namespace-local substitutions, API keys, NFS permissions and ingress.
   Check HA trusted proxies and each application's authentication before exposure.
5. Remove both suspension flags for that app only, verify its health and data,
   then validate HTTPS, backup and restore behavior.

MQTT retains its original settings and service address. Its old deployment had
no persistent data volume; decide on retained-message/session persistence before
activation. Vaultwarden recovery is optional: the owner stores passwords elsewhere.
Readarr is retired upstream; the owner chose to keep its backups and leave it
disabled. Do not include Readarr in a bulk application activation.

## Validation and known blocker

Kustomize/schema checks pass within the repository validator's documented schema
exclusions. Nineteen historical application charts rendered with their saved
values. This does not pull application images or prove application startup.

Kubernetes Dashboard's upstream repository is archived and the saved Helm index
returns HTTP 404. Its HelmRepository is also suspended. Keep the definition for
reference and choose a maintained replacement before attempting activation.

The external routes are behind a separate suspended Kustomization at
`network/external/ks.yaml`. Their hostnames and backend addresses are retained,
and retain their internal/public split. They remain suspended until cutover.


## Tested media image replacements

Calibre-Web 0.6.27 and Lidarr 3.1.0.4875 now use LinuxServer stable images pinned
by manifest digest because their old images cannot be pulled anonymously.
LinuxServer initialization runs as root; PUID/PGID keep both application
processes at 568, verified in the running test containers.

On 2026-10-16, both images started on Phoenix from disposable copies of the
restored NAS backups, with all network traffic denied and no media/download
mounts. Calibre-Web served its login page; Lidarr returned healthy and completed
its database migration. After stopping both containers, SQLite integrity passed;
Calibre-Web retained its two user records, and Lidarr retained 513 artists,
7,388 albums, 367,177 tracks and 26,309 track-file records. Configured download
clients, indexers and quality profiles retained their record counts.

These checks do not validate library access, downloads, login credentials,
external integrations, or operation on the replacement cluster. Both apps remain
suspended. Keep the original backups; migrated databases must not be opened by
older application versions.
