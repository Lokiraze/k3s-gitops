#!/usr/bin/env bash

# Wire up the env and validations
__dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "${__dir}/environment.sh"


# Create secrets file
truncate -s 0 "${GENERATED_SECRETS}"

#
# Helm Secrets
#

# Generate Helm Secrets
txt=$(find "${SECRET_ROOT}" -type f -name "*.txt")

if [[ ( -n $txt ) ]];
then
    # shellcheck disable=SC2129
    printf "%s\n%s\n%s\n" "#" "# Auto-generated helm secrets -- DO NOT EDIT." "#" >> "${GENERATED_SECRETS}"

    for file in "${SECRET_ROOT}"/helm-templates/*.txt; do
        # Get the path and basename of the txt file
        # e.g. "deployments/default/pihole/pihole"
        secret_path="$(dirname "$file")/$(basename -s .txt "$file")"
        # Get the filename without extension
        # e.g. "pihole"
        secret_name=$(basename "${secret_path}")
        # Get the relative path of deployment
        deployment=${file#"${CLUSTER_ROOT}"}
        # Get the namespace (based on folder path of manifest)
        namespace=$(echo "${deployment}" | awk -F/ '{print $2}')
        echo "[*] Generating helm secret '${secret_name}' in namespace '${namespace}'..."
        # Create secret
        envsubst < "$file" |
            # Create the Kubernetes secret
            kubectl -n "${namespace}" create secret generic "${secret_name}-helm-values" \
                --from-file=/dev/stdin --dry-run=client -o json |
            # Seal the Kubernetes secret
            kubeseal --format=yaml --cert="${PUB_CERT}" |
            # Remove null keys
            yq eval 'del(.metadata.creationTimestamp)' - |
            yq eval 'del(.spec.template.metadata.creationTimestamp)' - |
            # Format yaml file
            sed \
                -e 's/stdin\:/values.yaml\:/g' \
                -e '/^[[:space:]]*$/d' \
                -e '1s/^/---\n/' |
            # Write secret
            tee -a "${GENERATED_SECRETS}" >/dev/null 2>&1
    done
fi

#
# Generic Secrets
#

# shellcheck disable=SC2129
printf "%s\n%s\n%s\n" "#" "# Auto-generated generic secrets -- DO NOT EDIT." "#" >> "${GENERATED_SECRETS}"

# nginx basic auth
kubectl create secret generic bitwarden-admin-token \
    --from-literal=token="${BITWARDEN_ADMIN_TOKEN}" \
    --namespace home --dry-run=client -o json |
    kubeseal --format=yaml --cert="${PUB_CERT}" |
    # Remove null keys
    yq eval 'del(.metadata.creationTimestamp)' - |
    yq eval 'del(.spec.template.metadata.creationTimestamp)' - |
    # Format yaml file
    sed -e '1s/^/---\n/' |
    # Write secret
    tee -a "${GENERATED_SECRETS}" >/dev/null 2>&1

# DigitalOcean api key
kubectl create secret generic digitalocean-api-key \
    --from-literal=api-key="${DO_API_KEY}" \
    --namespace cert-manager --dry-run=client -o json |
    kubeseal --format=yaml --cert="${PUB_CERT}" |
    # Remove null keys
    yq eval 'del(.metadata.creationTimestamp)' - |
    yq eval 'del(.spec.template.metadata.creationTimestamp)' - |
    # Format yaml file
    sed -e '1s/^/---\n/' |
    # Write secret
    tee -a "${GENERATED_SECRETS}" >/dev/null 2>&1

# Remove empty new-lines
sed -i '/^[[:space:]]*$/d' "${GENERATED_SECRETS}"

# Validate Yaml
if ! yq eval "${GENERATED_SECRETS}" >/dev/null 2>&1; then
    echo "Errors in YAML"
    exit 1
fi

exit 0