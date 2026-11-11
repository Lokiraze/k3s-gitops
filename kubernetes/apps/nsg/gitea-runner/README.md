# Shared Gitea home build runner

The home runner is disabled (`replicas: 0`). On 2026-11-09, disk pressure on
Phoenix evicted the runner and other application pods during a launcher release.
Both `rust` and `release` jobs should use the existing VPS runners. This also
pauses ordinary CI at home because launcher release builds use the `rust` label.
Keep the home runner disabled until build storage is isolated from application
storage. Its Docker caches and registration remain on disk.

The live Deployment has `kustomize.toolkit.fluxcd.io/reconcile: disabled` to
prevent Flux from restoring a replica before this change reaches `main`. Remove
that annotation only after Flux's source contains `replicas: 0`.

Organization-scoped Gitea runner for all repositories in `games`, pinned to Phoenix. It polls
`https://git.noshamegames.com`; no inbound router port is needed.

- `rust`: Rust 1.99.1 with Clippy, Node and native build dependencies.
- `release`: Node 22 Debian image with Python, pip, Docker CLI, Buildx and Helm 3.17.3 preinstalled.
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

Repositories use `runs-on: release` or `runs-on: rust`; the VPS remains eligible
for jobs using these shared labels while the home runner is disabled.

Verification does not require publishing a release. Use a CI run after merging
a repository's workflow changes; release publication remains triggered by user tags.

The VPS has separate `runner-rust` (`rust`) and `runner-release` (`release`)
Docker Compose services. The Rust runner uses the same Rust CI Dockerfile.
When enabled, the home runner advertises both labels. Gitea assigns queued jobs to an available matching
runner; it does not prefer home or migrate an in-flight job after a host failure.
Runner configuration sets `CARGO_BUILD_JOBS` to 3 at home and 2 on the VPS.

Both hosts build `release-ci:1` from `app/Dockerfile.release`. Release workflows
should use `runs-on: release` without a `container:` override to use that image.
Python and pip use `/opt/venv`, so jobs can install their own Python packages.

Helm is installed with its upstream SHA-256 checksum verified during the image
build. Its version matches the previous Colony release workflow.
