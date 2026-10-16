# Application recovery definitions

The home, media, security and monitoring applications are present again, with
Frigate recovered from the older configuration tree. These are **suspended
recovery definitions**, not production-ready upgrades. Chart and image versions
are intentionally pinned to their historical values until each app's supported
upgrade path and restored data have been checked.

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
  class and its volumes are **not provisioned yet**; an unknown class cannot
  silently fall back to a default storage class and create an empty application.
- Removed dependencies on the retired nginx and local-path Helm releases.
- Disabled old Ingress generation. Ordinary HTTP services now have internal
  Envoy HTTPRoutes preserving their hostnames. The external-service definitions
  use EndpointSlice resources. Public access must be chosen separately.
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
   remain deferred nodes; coordinate their workloads and radio before cutover.
4. Verify namespace-local substitutions, API keys, NFS permissions and ingress.
   Check HA trusted proxies and each application's authentication before exposure.
5. Remove both suspension flags for that app only, verify its health and data,
   then validate HTTPS, backup and restore behavior.

MQTT retains its original settings and service address. Its old deployment had
no persistent data volume; decide on retained-message/session persistence before
activation. Vaultwarden recovery is optional: the owner stores passwords elsewhere.

## Validation and known blocker

Kustomize/schema checks pass within the repository validator's documented schema
exclusions. Nineteen historical application charts rendered with their saved
values. This does not pull application images or prove application startup.

Kubernetes Dashboard's upstream repository is archived and the saved Helm index
returns HTTP 404. Its HelmRepository is also suspended. Keep the definition for
reference and choose a maintained replacement before attempting activation.

The external routes are behind a separate suspended Kustomization at
`network/external/ks.yaml`. Their hostnames and backend addresses are retained,
but they now target internal Envoy ingress until access is deliberately enabled.
