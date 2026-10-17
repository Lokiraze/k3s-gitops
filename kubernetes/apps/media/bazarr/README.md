# Bazarr subtitle setup

After Flux deploys Bazarr, open **https://bazarr.lokiraze.dev** on the home network.
Sonarr and Radarr are connected already. The `Korean + English` language profile
requests both languages, with no cutoff and no exclusion when Korean audio is
present. Existing embedded subtitles count toward those requirements.

## First login

The username is `bazarr`. Retrieve the generated initial password from the
repository root on the computer with your SOPS key:

```sh
SOPS_AGE_KEY_FILE=age.key mise exec -- sops --decrypt \
  --extract '["stringData"]["initial-password"]' \
  kubernetes/apps/media/bazarr/app/secret.sops.yaml
```

You can change it under Settings → General → Security. The initial password is
only used when creating a new config; restarting never overwrites saved settings.

## Enable a subtitle provider

1. Create and verify a free account at https://www.opensubtitles.com/.
2. In Bazarr, open Settings → Providers and add **OpenSubtitles.com**.
3. Enter that account's username and password directly in Bazarr and save.

VIP is optional. Free accounts have download limits; large backlogs can take
multiple days. Korean subtitles are less widely available than English, so some
episodes may remain missing. Bazarr does not translate subtitles automatically.

## Choose which shows get both languages

Open Series in Bazarr, select the desired Korean dramas, and assign the
**Korean + English** language profile. You can then search for missing subtitles.
No language profile has been assigned to your entire library.

Alternatively, add the `korean-drama` tag to a series in Sonarr. Bazarr's enabled
tag matching assigns the bilingual profile when it syncs that series. The Sonarr
`Korean Drama - WEB 1080p` quality profile selects video/audio; Bazarr's language
profile separately selects subtitle tracks.

In Jellyfin or another player, select Korean or English in the subtitle menu.
These are separate selectable tracks; displaying both simultaneously depends on
the player. Refresh the player's library if newly downloaded tracks do not appear.

## Storage and mappings

Bazarr uses `/var/lib/homelab/app-data/bazarr-config` on Phoenix's internal disk,
with a retained local PV. Restore that directory on a replacement node. It
contains the editable configuration, database, language profiles and backups.
The encrypted bootstrap config is only a first-start seed, not a database backup;
if rebuilding without a backup, recreate the bilingual language profile in Settings.

Sonarr's `/media` maps to `/tv`, using the NAS `tvshows` export. Radarr's `/media`
maps to `/movies`, using the separate `movies` export. Bazarr runs as UID/GID 568
and writes subtitle sidecar files next to the media. It does not need the downloads
share. Provider credentials entered in Bazarr remain in its persistent config.
