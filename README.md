# Home cluster — Debian and k3s rebuild

This branch prepares a fresh k3s cluster on the existing Debian installations.
Ansible manages the hosts over SSH; Flux manages Kubernetes add-ons and apps.
Secure Boot stays enabled on the HP machines. No OS reinstall or disk formatting
is part of these playbooks.

The running old cluster still watches `main`. The new Flux source watches the
existing branch name, `feat-upgrade-to-talos`, despite the change of platform.
Do not merge this replacement tree into `main` while the old Flux is active.
The replacement foundation has not been applied. All seven existing machines
have been updated to Debian 12.15, and the old cluster still runs k3s 1.27.3.
Live DNS, certificate renewal and Home Assistant proxy repairs restored browser
access; those repairs do not constitute a cluster cutover.

## Machines and storage

The source of truth is `ansible/inventory/hosts.yaml`; existing encrypted host
credentials remain alongside it.

| Host | Address | Hardware | Initial role | Internal disk serial |
|---|---|---|---|---|
| summoner | 192.168.1.15 | Minisforum GK41, 8 GB | Control plane + workloads | LCMLCCC11202554 |
| phoenix | 192.168.1.16 | HP EliteDesk 800 G2, 16 GB | Control plane + workloads | 2M0329SJGQFJ |
| bahamut | 192.168.1.17 | HP EliteDesk 800 G2, 16 GB | Control plane + workloads | 2M032LCJ78G7 |
| odin | 192.168.1.14 | Minisforum GK41, 8 GB | Worker | LCMLCCC11202425 |
| ifrit | 192.168.1.11 | Raspberry Pi 4, 4 GB | Radio worker | SD CID recorded in inventory |

Ramuh `.10` and Shiva `.12` remain in the `deferred` inventory group. Ifrit is
included in the new worker inventory because it owns the existing Z-Wave radio;
preparation verifies its recorded SD-card CID instead of an SSD serial. Home
Assistant and Z-Wave still use the old cluster; their PVCs depend on
Ceph on the Intel machines: leaving the Pis alone does not preserve that data.

Use `/var/lib/homelab/app-data` on the existing internal root filesystem for
future local application volumes. Preparation verifies the root disk serial and
rejects a separate mount at that path. It does not repartition disks. Kubernetes,
images, logs and app data share capacity, so free-space monitoring is required.
Bahamut's failed USB disk is excluded; other USB disks still hold old Ceph data.
No Ceph or Longhorn controller is included in the new tree.

The static local StorageClass and home, media and monitoring PV bindings are defined; there is
no dynamic provisioner. Production volume ownership, backup schedules and final
application restores remain prerequisites. Test node affinity, retained data, reboot recovery
and a restore from NAS before activating stateful workloads. No automatic
stateful failover is required: applications can wait for their owning node.

## Network and secrets

- LAN `192.168.1.0/24`; router/DNS `192.168.1.1`.
- DHCP `.100–.245`; API VIP `192.168.1.18` confirmed available by the owner.
- Keepalived advertises `.18` only on healthy control-plane nodes, using unicast
  VRRP between the three servers. Permit IP protocol 112 between them.
- Servers initially join summoner `.15`; clients and Cilium use `.18:6443`.
- Pod CIDR `10.42.0.0/16`; service CIDR `10.43.0.0/16`.
- Preserve BGP: local ASN `64513`, router ASN `64512`, peer `192.168.1.1`.
- BGP service pool `192.168.69.0/24`: internal ingress `.100`, external ingress
  `.101`, DNS `.180`. Do not advertise it from old and new clusters simultaneously.

Cloudflare DNS/tunnel credentials and Flux's SOPS identity remain encrypted in
`bootstrap/` and `kubernetes/`. DNS writes, certificate issuance and Cloudflare
tunnel HTTPS access have been verified on the old cluster. They must be tested
again after the replacement foundation is installed.
Keep the existing age recovery key outside both Git and the cluster. Restore it
locally as ignored `age.key` before decrypting secrets. Kubeconfig is ignored and
written with mode `0600`. Newly generated k3s server tokens must also be backed
up encrypted after installation; they are needed to restore etcd snapshots.

Edit Kubernetes YAML directly. The Talos generator and its tools are retired;
there is no `just configure` step to overwrite the source manifests.

## Validate locally

```sh
mise trust
mise install
uv sync --locked
just ansible deps
just ansible syntax
just validate
just check-charts
```

Ansible syntax checks do not contact hosts or decrypt inventory secrets. Tests
cover inventory, Cilium/k3s network agreement, Keepalived rendering and maintenance
guards. Kubernetes schema validation permits missing schemas and skips Secrets,
Gateway and HTTPRoute; chart rendering and live acceptance are separate checks.

The installer uses `xanmanning.k3s` v3.6.2 and pins k3s v1.37.1+k3s1. The role's
node-ready post-check is deferred because Cilium is installed in the next phase.
Bundled flannel, kube-proxy, network policy, CoreDNS, local storage, metrics-server,
ServiceLB and Traefik are disabled as appropriate; Flux owns their replacements.
Standalone Spegel is omitted; no Talos containerd paths remain.

## Debian maintenance over SSH

These commands affect only the explicitly selected host:

```sh
just ansible preflight k8s-bahamut
just ansible update k8s-bahamut
```

Use the existing SSH identity or the SOPS inventory credentials. SSH host-key
checking is enabled: verify the machine fingerprints before accepting them.
The age key must be available to SOPS on this workstation.

Updates stay on Debian 12/bookworm, use the configured repositories and accept only
Bookworm suite names. They do not rewrite repositories, perform a Debian
major-release upgrade, remove packages automatically, disable Secure Boot or
reboot. Review available signed kernel/firmware updates and cluster health before
a controlled one-at-a-time reboot. A Debian 13 migration needs a separate review
of its release notes and package changes.

## Cutover and fresh installation

1. Verify the recovery sets below and take final backups with writers stopped.
   Coordinate old Flux and old BGP shutdown before reusing the service addresses.
2. Review the old-cluster teardown separately. The old Ansible nuke routine is
   retired: it flushed all firewall rules and is unsuitable for a remote cutover.
   Follow k3s/Cilium teardown requirements to preserve SSH networking. This branch
   deliberately does not automate data deletion or a multi-minor in-place upgrade.
3. Update Debian, reboot and verify SSH, kernel, storage and Secure Boot state.
4. Run `just ansible prepare`, then `just ansible install` against all five initial
   nodes. Installation refuses existing `/var/lib/rancher/k3s` unless this rebuild
   already owns it; it never erases that directory. Partial bootstrap failures
   require inspection before retrying, rather than bypassing the guard.
5. Verify `.18:6443`, all five registered nodes and the private local kubeconfig.
   Publish the reviewed branch so the new Flux source can fetch it, then run
   `just bootstrap apps`.
6. Verify node readiness, Flux's observed Git revision, SOPS decryption, BGP,
   DNS/TLS and API failover. Add tested local storage/backups before restoring apps.

## Recovery copies and application migration

The missing application definitions are restored and suspended. See
[kubernetes/apps/README.md](kubernetes/apps/README.md) for the complete inventory,
activation checks and the archived Kubernetes Dashboard chart blocker.

Preliminary encrypted copies are saved locally under ignored `.rebuild/` and on
`192.168.1.50:/mnt/user/backups/`:

- `k3s-rebuild-20261016-home`: Home Assistant (SQLite online backup), Z-Wave store,
  and home-service Kubernetes configuration. Decryption, NAS checksums and the
  restored Home Assistant SQLite integrity check passed.
- `k3s-rebuild-20261016-apps`: ten media-service configurations, current/previous
  Vaultwarden container data, and media/security Kubernetes configuration.
  Fifteen encrypted files passed NAS checksum comparisons and 25 SQLite integrity
  checks. Lidarr/Sonarr cover-image caches are omitted; their settings, databases
  and existing backup files are included.

The NAS write/read/delete test passed and reported about 17 TB free. These are
live preliminary copies, not final cutover snapshots or application restore
acceptance. Vaultwarden's current database is empty; the owner stores passwords
elsewhere and does not require Vaultwarden recovery. Its old PVC was incorrectly
mounted at `/config` while actual data lived at `/data` in the container.

Restore MQTT, Z-Wave and Home Assistant first, reusing the existing radio and
security keys without resetting or re-pairing the lock. Then restore Frigate
with the USB Coral, validated Intel video decoding and NAS recording storage.
Next migrate wanted media apps and monitoring, checking current project support.
Add the Pis deliberately after their applications and USB devices are accounted
for. Home Assistant Green and a new Z-Wave adapter remain deferred purchases.
