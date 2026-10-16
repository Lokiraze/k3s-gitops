export ANSIBLE_HOME := source_directory() + "/.dependencies"

set quiet
set default-list
set default-script
set shell := ['bash', '-euo', 'pipefail', '-c']
set script-interpreter := ['bash', '-euo', 'pipefail']

# Ansible config paths are relative to this directory.
deps:
    ANSIBLE_HOME="$PWD/.dependencies" uv run --project .. --locked ansible-galaxy install -r requirements.yaml

# No secrets are decrypted or machines contacted by syntax validation.
syntax:
    for play in playbooks/*.yaml; do
        ANSIBLE_VARS_ENABLED=host_group_vars uv run --project .. --locked ansible-playbook --syntax-check "$play"
    done

preflight host:
    uv run --project .. --locked ansible-playbook playbooks/cluster-preflight.yaml --limit '{{ host }}'

# Explicit maintenance acknowledgement is also enforced inside the playbook.
update host:
    uv run --project .. --locked ansible-playbook playbooks/cluster-rollout-update.yaml --limit '{{ host }}' -e maintenance_confirmed=true

prepare:
    uv run --project .. --locked ansible-playbook playbooks/cluster-prepare.yaml

install:
    uv run --project .. --locked ansible-playbook playbooks/cluster-installation.yaml
