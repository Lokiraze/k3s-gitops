set quiet
set minimum-version := '1.55.1'
set default-list
set default-script
set shell := ['bash', '-euo', 'pipefail', '-c']
set script-interpreter := ['bash', '-euo', 'pipefail']

mod bootstrap 'bootstrap'
mod kube 'kubernetes'
mod ansible 'ansible'

[private]
log lvl msg *args:
    gum log -t rfc3339 -s -l "{{ lvl }}" "{{ msg }}" {{ args }}

# Source manifests are edited directly now; there is no template render step.
validate:
    uv run --locked pytest -q
    bash scripts/validate-kubernetes.sh kubernetes

check-charts:
    helmfile --file bootstrap/helmfile/apps.yaml template --quiet > /dev/null
    helmfile --file bootstrap/helmfile/crds.yaml template --quiet > /dev/null
