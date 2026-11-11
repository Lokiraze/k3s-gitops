# Lidarr storage

Lidarr's config uses Phoenix's 500 GB PNY CS900 USB SSD, identified by
`ata-PNY_CS900_500GB_SSD_PNY412022958311028CD`. The prepared ext4 filesystem has
label `phoenix-apps` and mounts by UUID at `/var/lib/homelab/ssd-data`.
Its `lidarr-config` directory is bind-mounted at
`/var/lib/homelab/app-data/lidarr-config`, preserving the existing local PV/PVC.
Music and downloads remain on the NAS; Phoenix's other application configs remain
on its internal filesystem.

After the manual migration, maintain these mounts from the `ansible` directory:

```sh
uv run --project .. --locked ansible-playbook playbooks/lidarr-ssd-storage.yaml
```

The playbook requires the prepared SSD, existing restore marker and database, and
either the correct bind mount or an empty target. It never formats, copies,
deletes data, stops applications, or reboots a node. Initial migration requires
stopping Lidarr's writers, verifying the copied data, and moving the original
directory aside before mounting over the empty target.

The initial rollback copy is
`/var/lib/homelab/app-data-rollback/lidarr-config-20261111`. Keep the underlying
bind target empty: if the SSD or bind mount is unavailable, Lidarr's existing
`verify-restored-data` init container must fail instead of starting with a stale
root-disk database. The bind mount depends on the SSD mount; `nofail` lets Phoenix
boot without that disk. This does not provide automatic stateful failover.
