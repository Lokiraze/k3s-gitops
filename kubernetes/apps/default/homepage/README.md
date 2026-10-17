# Homepage

Homepage replaces Hajimari at `https://lokiraze.dev`. It discovers Gateway API HTTPRoutes using its read-only service account. The dashboard has no central list of app links.

To add an app, annotate its HTTPRoute:

```yaml
metadata:
  annotations:
    gethomepage.dev/enabled: "true"
    gethomepage.dev/name: App name
    gethomepage.dev/group: Media
    gethomepage.dev/icon: mdi-play
    gethomepage.dev/href: https://app.${SECRET_DOMAIN}
```

Use the route's actual hostname. These links are intended for the home network; Homepage's route uses `envoy-internal`. No app credentials or widgets containing API keys are added by this configuration.

The dashboard uses Homepage's built-in styling with no custom CSS. Homepage itself has no theme.park integration. Config files are stored in Git; runtime logs/default generated files use emptyDir.

## Migration and verification

After merging, Flux prunes Hajimari and installs Homepage and theme.park. The apex page may be briefly unavailable while the new pod starts. No persistent Hajimari data volumes are removed (the old installation used emptyDir).

Verify the two HelmReleases are Ready, open `https://lokiraze.dev`, and check that the Home, Media, and Infrastructure groups populate from annotated routes. Click links to confirm destinations. Appearance and live discovery must be checked after deployment; manifest tests do not prove browser behavior.
