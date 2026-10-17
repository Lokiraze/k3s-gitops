# UniFi Network

Open **https://unifi.lokiraze.dev** on the home network after Flux deploys this
application. Complete the first-run wizard and create the administrator account.
This is a fresh controller; no devices are reset or adopted automatically.

In UniFi's device settings, enable **Inform Host Override** and set the host to
`192.168.69.82`. For devices requiring manual layer-3 adoption, run this on the
UniFi device using its existing SSH credentials:

```sh
set-inform http://192.168.69.82:8080/inform
```

The browser hostname points to the internal HTTPS gateway, whereas adoption uses
the dedicated LoadBalancer address. UDP discovery broadcasts do not cross routed
networks; use the inform address for devices on other subnets. The service exposes
TCP 8080/8443 and UDP 3478/10001. Guest portal and speed-test ports are not enabled.

UniFi and MongoDB run in one pod on Phoenix. MongoDB listens only on loopback,
uses SOPS-encrypted credentials, and is not exposed by any Service. Its major
version is pinned; MongoDB major upgrades require a separate migration.

The retained local volumes use Phoenix's internal disk:

- `/var/lib/homelab/app-data/unifi-config`: application config, keystore and backups.
- `/var/lib/homelab/app-data/unifi-db`: MongoDB data.

Both directories were explicitly provisioned for this fresh installation. On a
replacement node, restore these directories before deploying; the static PVs do
not create them. Deleting manifests does not erase the retained PV data. For
backups, export UniFi `.unf` backups and keep copies off the node; do not copy a
running MongoDB data directory as a consistent backup.

The existing `lokiraze-dev-production-tls` Secret supplies the trusted certificate.
An init container imports it into UniFi's keystore. Reloader restarts the pod when
the Secret changes, importing the renewed certificate. The internal gateway
validates the backend certificate with system CAs using `BackendTLSPolicy`.
Certificate renewal causes a brief controller interruption; it does not restart
UniFi access points or switches.
