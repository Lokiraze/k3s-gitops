set no-exit-message
set quiet
set shell := ['bash', '-euo', 'pipefail', '-c']
set script-interpreter := ['bash', '-euo', 'pipefail']
set default-list
set default-script

kubernetes_dir := justfile_dir() + '/kubernetes'

[doc('Bootstrap apps into the k3s cluster')]
[group('bootstrap')]
apps: apps-ready apps-namespaces apps-secrets apps-crds apps-helm
    just log info "Cluster is bootstrapped — Flux will start syncing the Git repository"

[private]
apps-crds:
    just log info "Applying CRDs" stage "{{ recipe_name() }}"
    if ! helmfile --file "{{ source_directory() }}/helmfile/crds.yaml" template --quiet | yq eval-all --exit-status 'select(.kind == "CustomResourceDefinition")' | kubectl apply --server-side --force-conflicts --filename -; then
        just log fatal "Failed to apply crds"
    fi

[private]
apps-helm:
    just log info "Syncing helmfile" stage "{{ recipe_name() }}"
    if ! helmfile --file "{{ source_directory() }}/helmfile/apps.yaml" sync --hide-notes; then
        just log fatal "Failed to sync helmfile"
    fi

[private]
apps-namespaces:
    just log info "Applying namespaces for apps" stage "{{ recipe_name() }}"
    for app in "{{ kubernetes_dir }}/apps"/*/; do
        ns="$(basename "$app")"
        if kubectl create namespace "$ns" --dry-run=client -o yaml \
                | kubectl apply --server-side --filename - &>/dev/null; then
            just log info "Namespace applied" namespace "$ns"
        else
            just log fatal "Failed to apply namespace" namespace "$ns"
        fi
    done

[private]
apps-secrets:
    just log info "Applying secrets for apps" stage "{{ recipe_name() }}"
    for secret in \
        "{{ source_directory() }}/deploy-key.sops.yaml" \
        "{{ source_directory() }}/sops-age.sops.yaml" \
        "{{ kubernetes_dir }}/components/sops/cluster-secrets.sops.yaml"
    do
        name="$(basename "$secret" .sops.yaml)"
        if sops decrypt "$secret" \
                | kubectl --namespace flux-system apply --server-side --filename - &>/dev/null; then
            just log info "Secret applied" resource "$name"
        else
            just log fatal "Failed to apply secret" resource "$name"
        fi
    done

# Wait until nodes register as Ready=False. They only become Ready=True once the CNI is healthy.
[private]
apps-ready:
    just log info "Waiting for nodes to register as Ready=False" stage "{{ recipe_name() }}"
    if ! kubectl wait nodes --for=condition=Ready=True --all --timeout=10s &>/dev/null; then
        deadline=$((SECONDS + 600))
        until kubectl wait nodes --for=condition=Ready=False --all --timeout=10s &>/dev/null; do
            if (( SECONDS >= deadline )); then
                just log fatal "Timed out waiting for nodes to register"
            fi
            just log info "Nodes not available, waiting for nodes to be available. Retrying in 5 seconds..."
            sleep 5
        done
    fi

