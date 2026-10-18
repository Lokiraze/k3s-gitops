# Media dashboard

These files are the source copies of the live Home Assistant media dashboard.
They are not automatically deployed by Flux.

- Copy `media-poster-grid.js` to `/config/www/media-poster-grid.js`.
- Register `/local/media-poster-grid.js?v=2` as a JavaScript module under Settings → Dashboards → Resources. Increment the version after changing the script to refresh browser caches.
- Copy `media.yaml` to `/config/dashboards/media.yaml`.
- The existing `lovelace.dashboards.media-center` configuration points to this YAML file.

The grid reads the Sonarr/Radarr Upcoming Media sensors already configured in Home Assistant. No API keys are included in these files. Keep `/config/.storage` in backups to preserve integration setup and resource registration.

The previous live dashboard is saved as `/config/dashboards/media.before-grid.yaml` for rollback. Jellyfin recently-added artwork is not connected because the saved credentials were rejected.

## Home Controls

`home-controls.yaml` is the source copy of `/config/dashboards/home-controls.yaml`,
registered under the existing `home-controls` dashboard. It shows the five Frigate
camera previews and links to the ten existing Keymaster code slots. PIN values
are stored by Keymaster, never in this file. Adding the dashboard does not change
slot names, PINs, enabled state, lock pairing, or thermostat settings.

The live dashboard was updated directly; Flux does not copy this file. The prior
version is saved at `/config/dashboards/home-controls.before-camera-codes.yaml`.

## Air filter reminder

Copy `../packages/air_filter_maintenance.yaml` to
`/config/packages/air_filter_maintenance.yaml`. The live configuration enables
`homeassistant.packages: !include_dir_named packages`. This adds a restored
last-completed date, a status sensor, and the completion script used by Home
Controls. An unset date starts overdue; completion sets today's local date and
makes the next due date 90 days later. No phone notifications are configured.
