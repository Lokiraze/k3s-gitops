# theme.park

Self-hosted theme files are served at `https://theme-park.lokiraze.dev` from the upstream 1.23.0 image, pinned by digest. Configuration and assets are regenerated from the image, so no persistent volume is required.

Sonarr, Lidarr, Bazarr, and Calibre-Web use the official theme.park LinuxServer Docker Mods, `TP_THEME=aquamarine`, and the local theme domain. Mods insert stylesheet links during container startup; Envoy does not modify HTML. Mod tags are upstream app-specific tags, downloaded by LinuxServer's mod loader.

This does not apply themes to Radarr/Prowlarr (home-operations images), Whisparr (Hotio), Seerr, external NAS apps, or Home Assistant. Those need application-specific configuration or a separately verified injection method. Homepage uses a matching custom palette rather than a theme.park stylesheet.

After Flux deploys, verify `/css/theme-options/aquamarine.css` returns CSS and check themed apps in a browser. The mod loader and styles have not been verified live until this deployment completes. A failed mod download may leave an app unthemed; check startup logs rather than assuming visual success from readiness alone.
