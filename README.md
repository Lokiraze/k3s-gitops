# Home cluster — Debian and k3s rebuild

This branch prepares a fresh k3s cluster on the existing Debian installations.
Ansible manages the hosts over SSH; Flux manages Kubernetes add-ons and apps.
Secure Boot stays enabled on the HP machines. No OS reinstall or disk formatting
is part of these playbooks.

The old cluster's six Flux controllers are stopped, its Kustomizations and
HelmReleases are suspended, and its source is pinned to the pre-rebuild commit.
The replacement Flux source follows `main`; merge this tree before bootstrapping
the new cluster. Keep old Flux frozen throughout the cutover. Its old root
Kustomization can reset the source to `main`, so do not blindly resume it during
rollback after the merge.
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
| bahamut | 192.168.1.17 | HP EliteDesk 800 G2, 16 GB | Control plane + Frigate only | 2M032LCJ78G7 |
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
and a restore from NAS before activating stateful workloads. Local volumes do not provide automatic stateful failover: a service is unavailable while its storage node is unreachable.

Bahamut is reserved for Frigate with the `dedicated=frigate:NoSchedule` taint; only Frigate tolerates it among application workloads. Kubernetes system services still run there. Frigate requests 2 CPU cores and 4 GiB of memory and is limited to 3 cores and 6 GiB. Home Assistant and Music Assistant use Summoner storage. PostgreSQL, Redis, Colony saves, and SteamTactics artwork use Odin storage. Moving these volumes requires stopping writers and verifying a data copy before rebinding; changing node affinity alone does not migrate data.

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

The installer uses `xanmanning.k3s` v3.6.2 and pins k3s v1.37.1+k3s1, the latest upstream release. The role's
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

## Detached recovery prerequisite check

Run `just ansible recovery-check k8s-bahamut` (or use `all` for all seven hosts).
The playbook creates a disposable network namespace, proves that broken routing
and firewall rules each block a local ping, then schedules systemd to restore
both after SSH disconnects. It also checks that a canceled timer never fires.
The test removes its namespace, timers and private temporary state afterward.
It neither stops Kubernetes nor changes the host's networking.

All seven hosts passed this probe on 2026-10-16. The probe is **not a host rollback
script**: transient timers do not survive reboot, and it does not test recovering
SSH from Cilium BPF filters or restoring the old cluster. Those remain cutover
gates. The initial test exposed an empty iptables snapshot; the probe now requires
an explicit filter-table snapshot before testing restoration.

Live Cilium 1.14.5 attaches BPF filters to the management interface. Its cleanup
must run only after the agent is stopped, and Ceph mounts must be detached before
network shutdown. Upstream cleanup reports individual errors on stderr without
necessarily failing its exit status; check the remaining BPF attachments/maps,
routes and SSH reachability explicitly. A zero exit code alone is insufficient.

## Host-local management rescue

`ansible/playbooks/files/host-network-recovery.py` now implements capture,
quiescence checks, a ten-minute recovery timer, repair and cancellation. Corrected
copies and network snapshots are staged privately on all seven hosts under
`/var/lib/homelab/network-recovery/`; **none is armed**. Recapture within an hour
of the actual cutover while the old Cilium agent is still running.

The tool preserves the running agent's CLI and accepts exactly Cilium 1.14.5
(`cleanup`) or 1.20.2 (`post-uninstall-cleanup`). It prefers `cilium-dbg` in newer
images and chooses the command from the saved client's version, not the daemon's.
Rescue uses only `--bpf-state`; full cleanup remains a separate operation.
Unknown versions are rejected before changing the pidfile or network. The real
1.20.2 CLI and flags were checked on Intel and ARM Debian using help only; no
production BPF cleanup was executed. It refuses to arm or repair
while k3s services, container shims, Cilium/Ceph processes or Ceph/RBD mounts remain.
A host-wide lock and active-capture record prevent competing timers. Cancellation
can disarm without working networking or intact snapshot contents. After teardown,
repair removes Cilium BPF state and restores management IPv4 addressing, LAN
policy routing and the captured IPv4 firewall. It never restarts the cluster.

The actual IPv4 repair function passed a Linux namespace test on Bahamut with a
down interface, missing address, blocked firewall, missing main routing lookup
and a blocking policy rule; repeating the repair passed too. This does **not**
prove recovery from real host BPF failure or a lost SSH connection. IPv6, reboot
recovery and full-cluster rollback are outside this tool's scope. Do not begin
teardown until the shutdown/restore runbook and remaining foundation gates pass.

## Runtime shutdown rehearsal

The separate-runtime test in `ansible/playbooks/files/runtime-shutdown-check.py`
passed on Bahamut (Intel) and Ifrit (ARM64). A disposable container survived its
containerd daemon being killed, reconnected with the same PID, then exited with
code 0 after SIGTERM. Stopping its sandbox left no tasks before test metadata was
removed. No production runtime or container was stopped.

The original containerd config, binary hash and full startup arguments are now
preserved in each host's private network-recovery capture. k3s supplies the root,
state and socket as command-line options; copying only the TOML is insufficient.

`cilium-cleanup-check.py --require-clean` is a read-only BPF postcondition for the
future cleanup. It checks Cilium programs, maps, links, network/cgroup attachments
and pinned maps, while preserving systemd's unrelated BPF protections. All seven
live hosts correctly fail this gate while Cilium is running. bpftool is included
in host preparation. Real CNI teardown and whole-cluster rollback remain untested.

## Cutover and fresh installation

The old etcd snapshot was restored with k3s v1.27.3+k3s1 and its original server
token in a disconnected container. The restored API returned all 15 original
PVC bindings and 135 readable Secret objects, with scheduling disabled. The
original token must exist at `server/token` for that version's snapshot reset;
`--token-file` alone did not satisfy its restore check. This verifies control-plane
recovery, not the full seven-node Ceph/BGP rollback.

Final read-only backup Pod manifests cover all 15 PVCs and passed server-side
dry-run validation against that restored API. They have not been applied to
production. The reviewed cutover plan requires stopped writers, verified NAS
copies of the final snapshot and application data, off-host path-preservation
records, and MQTT retained-message replay before clients restart on rollback.

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
activation checks.

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

Isolated restore checks passed for Home Assistant, MQTT and Z-Wave UI. Home
Assistant served its frontend as UID 568 from a restored copy, with SQLite
integrity and its saved integration entry preserved. The containers had no
network or USB access. The retained MQTT
payload matched exactly, and Z-Wave's security keys and controller path were
unchanged after startup. The MQTT snapshot is encrypted locally and in the NAS
`k3s-rebuild-20261016-home-pre-cutover` directory. The old broker has no persistent
storage; this snapshot covers retained messages, not client sessions or queued
messages. Refresh it after stopping publishers during cutover.

The NAS write/read/delete test passed and reported about 17 TB free. These are
live preliminary copies, not final cutover snapshots or full device-reconnection
acceptance. Vaultwarden's current database is empty; the owner stores passwords
elsewhere and does not require Vaultwarden recovery. Its old PVC was incorrectly
mounted at `/config` while actual data lived at `/data` in the container.

Restore MQTT, Z-Wave and Home Assistant first, reusing the existing radio and
security keys without resetting or re-pairing the lock. Then restore Frigate
with the USB Coral, validated Intel video decoding and NAS recording storage.
Next migrate wanted media apps and monitoring, checking current project support.
Add the Pis deliberately after their applications and USB devices are accounted
for. Home Assistant Green and a new Z-Wave adapter remain deferred purchases.
