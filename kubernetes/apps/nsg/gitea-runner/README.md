# Shared Gitea home build runner

Organization-scoped Gitea runner for all repositories in `games`, pinned to Phoenix. It polls
`https://git.noshamegames.com`; no inbound router port is needed.

- `home-rust`: Rust 1.99.1 with Clippy, Node and native build dependencies.
- `home`: Node 22 Debian image for general and release workflows.
- Capacity one: CI and release builds queue rather than compete for memory.
- Dedicated Docker-in-Docker daemon: jobs do not receive the node's container runtime socket.
- Docker daemon capped at 3 CPUs / 6 GiB, individual job containers at 3 CPUs / 5 GiB.
- Docker layers, BuildKit caches and Cargo volumes persist under
  `/var/lib/homelab/ci/gitea/docker`; registration under
  `/var/lib/homelab/ci/gitea/runner`. These paths survive pod replacement.
- Registration token is encrypted in `app/secret.sops.yaml`, scoped to the `games` organization.

The first startup builds the Rust CI image. Subsequent starts reuse Docker layers.
The first home build has cold caches; do not judge warm-build speed from it.
Monitor node disk usage: these build caches share Phoenix's internal disk.

Repositories opt in with `runs-on: home` or `runs-on: home-rust`.
Merge this configuration and the corresponding workflow changes for Flux ownership
and future jobs. Existing jobs on the VPS are unaffected. Removing the deployment
stops the runner but retains its disk data; switch workflow labels back before
removing it if jobs must continue on the VPS.

Verification does not require publishing a release. Use a CI run after merging
a repository's workflow changes; release publication remains triggered by user tags.
