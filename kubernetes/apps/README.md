# Application recovery definitions

The recovered applications are active except for Frigate (deferred) and
Vaultwarden (disabled). Application images are pinned to reviewed releases.
The generic application charts and Mosquitto now use app-template 5.3.0 from
`oci://ghcr.io/bjw-s-labs/helm`; Frigate retains its deferred recovery definition.

The source GitRepository is `flux-system`. Shared substitution values and chart
sources live under `flux-system/app-recovery/`; secrets remain SOPS-encrypted.
The recovery procedure and historical validation notes below explain how the
existing data was restored; they are not the current suspension status.

| Group | Restored applications |
|---|---|
| Home | Home Assistant, MQTT/Mosquitto, Z-Wave JS UI, Frigate |
| Media | Calibre-Web, Jellyseer, Lidarr, Podfetch, Podgrab, Prowlarr, Radarr, Recyclarr, Sonarr, Whisparr |
| Security | Vaultwarden |
| Monitoring | Grafana, kube-prometheus-stack |
| Dashboard | Hajimari |
| External routes | Jellyfin, robo, stash, torrent |
| Network | UniFi Network (fresh installation) |

UniFi uses the internal `https://unifi.lokiraze.dev` route, with dedicated device
adoption at `192.168.69.82:8080`. See [UniFi setup](network/unifi/README.md) for the
first-run wizard, inform-host setting and persistent storage details.

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
- Disabled Home Assistant's unauthenticated code-server sidecar.
- Removed Kubernetes Dashboard and its unused chart source at the owner's request.
- Preserved Frigate's USB Coral configuration, explicitly mounted `/dev/bus/usb`,
  and used secret-backed `FRIGATE_*` environment variables for camera URLs.

The original disabled Ingress values remain as migration references. Old nginx
snippets, theme injection, and authentication annotations are not implemented by
these new HTTPRoutes. Prometheus routing still requires
review rather than guessing its backend/TLS configuration.

## App-template migration

The 5.3.0 values use controllers, container-scoped settings and explicit volume
mounts. Service and workload names remain stable. Existing deployments retain
their immutable selectors through HelmRelease post-renderer patches; keep those
patches while upgrading the same deployments. Pods carry the new controller
labels, so the new chart's service selectors still select them. Deployments use
Recreate to avoid concurrent access to local application data and USB devices.

Restore guards mount only their existing config claim read-only at `/restore`.
Application mounts retain their paths, claims, NFS exports and security contexts.
Mosquitto retains its listener configuration and service address. Recyclarr retains
its persistent state and Forbid concurrency policy. Vaultwarden's obsolete separate
WebSocket listener was removed; current releases serve it on the HTTP port.

## Whisparr Eros v3

Whisparr targets Eros 3.6.5.1886. V3 uses `whisparr3.db` and does not convert
the v2 series/episode catalog. Its prepared database on Phoenix preserves the
existing user credentials, API key, 14 indexers, download client and root folder.
It uses v3's native quality profiles and definitions because their IDs differ
from v2. The startup guard requires the prepared v3 database.

The v3 library starts empty: the existing media needs importing through v3.
No media files were moved or deleted. The old `whisparr2.db` remains in the
config volume; the pre-upgrade snapshot contains 10 series and 90 file records.
Its encrypted backup is on the NAS under
`/mnt/user/backups/whisparr-20261017T130831Z/whisparr-v2-before-eros.sops.json`.
To roll back, restore the v2 image pin and v2 database guard together; changes
made to the v3 library will not appear in v2.

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
   Historical image availability and compatibility with k3s 1.36 are not proven
   by a successful Helm render. Check maintenance status of old projects such as
   Podgrab and Hajimari before choosing to continue or replace them.
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
Readarr is retired upstream and has been removed at the owner’s request. Its
existing backups are retained.

## Validation

Kustomize/schema checks pass within the repository validator's documented schema
exclusions. Nineteen historical application charts rendered with their saved
values. This does not pull application images or prove application startup.

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


### Media-library checks

On 2026-10-16, Phoenix mounted the existing books, music and downloads exports.
A Kubernetes pod also mounted all three exports using the application paths and
passed read-access checks as UID 568.
UID/GID 568 could read them and create, read, rename and delete disposable probe
files. All probes were removed. The Calibre `metadata.db` passed SQLite integrity
and contains 352 books. Lidarr's saved `/media/` root matches its rendered mount.
Calibre-Web's saved `config_calibre_dir` is unset; select `/books` after restoring
and signing in. Permission checks do not exercise download-client integration
or move any existing books, music or downloads.


### Frigate hardware and configuration checks

On 2026-10-16, a disposable pod on Bahamut tested
`ghcr.io/blakeblackshear/frigate:0.18.2` at digest
`sha256:fd60f99ffd4eb6c42360ed4e14953e270586f239309ab3983e55b2e97ffac09a`.
Its USB Coral delegate completed ten inferences using the bundled EdgeTPU model
(12.82 ms average, including the first inference). Intel VAAPI decoded a locally
generated H.264 video through `/dev/dri/renderD128`. No camera credentials,
recordings, production config volumes or MQTT access were supplied to the pod.

The same image parsed a five-camera candidate retaining the USB Coral and using
`preset-rtsp-generic` plus `preset-vaapi`, with obsolete RTMP roles removed.
Camera addresses were inert placeholders. The parser also accepted the original
configuration; parsing alone does not prove that its old FFmpeg arguments work.
The candidate is saved under ignored `.rebuild/frigate-0.18.2-candidate.yaml`.

Frigate remains suspended at its historical deployment definition until the
chart, writable local config/database volume, authenticated web route and NAS
recording mounts are migrated together. These hardware checks do not validate
live camera streams, H.265 decoding, recording retention or sustained load.
