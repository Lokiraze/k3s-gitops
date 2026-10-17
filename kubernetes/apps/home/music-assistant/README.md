# Music Assistant

Music Assistant runs on `k8s-bahamut` with retained local data at
`/var/lib/homelab/app-data/music-assistant-data`. The directory was created and
initialized with the pinned image before enabling Flux. The PV does not create
it automatically; preserve this directory during node maintenance.

After Flux reconciles, open <https://music-assistant.lokiraze.dev> and complete
first-run setup by creating an administrator account. Add your music sources and
confirm that your speakers are discovered and can play audio.

To expose Music Assistant players in Home Assistant, open **Settings → Devices &
services → Add integration → Music Assistant**. Use `http://192.168.1.17:8095`
and sign in with your Music Assistant administrator account when prompted.
The native Home Assistant integration is included in Home Assistant; no HACS
component is required. Importing existing Home Assistant media players into
Music Assistant is a separate, optional provider setup.

LAN players must be able to reach Bahamut directly: the UI/API uses TCP 8095 and
the stream server uses TCP 8097, with additional dynamic ports for individual
player protocols. Host networking enables mDNS/uPnP discovery. The HTTPS route
is for browser access; it does not replace direct LAN streaming. Music Assistant
and the players must share a layer-2 network. `NET_BIND_SERVICE` is the only
added capability, needed for AirPlay 2 PTP timing on UDP 319/320. Mounting SMB/NFS
shares inside this container is deliberately not enabled.

Validation: the pinned 2.10.7 image started on Bahamut with this configuration,
reported its LAN address as `192.168.1.17`, and served `/setup` through a temporary
Envoy HTTPS route with HTTP 200 and valid TLS. AirPlay PTP and mDNS sockets were
listening. Temporary test resources were deleted; first-run setup remains
incomplete for the owner to choose credentials. Speaker pairing, playback and
Home Assistant integration have not been tested. Upstream supports standalone
Docker/HAOS, but explicitly does not support Kubernetes deployments.

References: [installation](https://www.music-assistant.io/installation/),
[Home Assistant integration](https://www.music-assistant.io/integration/installation/),
[release 2.10.7](https://github.com/music-assistant/server/releases/tag/2.10.7).
