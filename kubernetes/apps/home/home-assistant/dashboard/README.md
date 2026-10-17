# Media dashboard

These files are the source copies of the live Home Assistant media dashboard.
They are not automatically deployed by Flux.

- Copy `media-poster-grid.js` to `/config/www/media-poster-grid.js`.
- Register `/local/media-poster-grid.js?v=2` as a JavaScript module under Settings → Dashboards → Resources. Increment the version after changing the script to refresh browser caches.
- Copy `media.yaml` to `/config/dashboards/media.yaml`.
- The existing `lovelace.dashboards.media-center` configuration points to this YAML file.

The grid reads the Sonarr/Radarr Upcoming Media sensors already configured in Home Assistant. No API keys are included in these files. Keep `/config/.storage` in backups to preserve integration setup and resource registration.

The previous live dashboard is saved as `/config/dashboards/media.before-grid.yaml` for rollback. Jellyfin recently-added artwork is not connected because the saved credentials were rejected.
