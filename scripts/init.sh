#!/bin/bash

REPO_ROOT=$(git rev-parse --show-toplevel)
KUBECONFIG=:"${REPO_ROOT}"/../k3s-ansible/kubeconfig:~/.kube/config kubectl config view --flatten > ~/.kube/config.tmp && \
  mv ~/.kube/config.tmp ~/.kube/config

need() {
    which "$1" &>/dev/null || die "Binary '$1' is missing but required"
}

need "kubectl"
need "helm"
need "flux"

message() {
  echo -e "\n######################################################################"
  echo "# $1"
  echo "######################################################################"
}

if [[ -f "${REPO_ROOT}"/master.key ]]; then
  echo "Applying existing sealed-secret key"
  #kubectl apply -f "${REPO_ROOT}"/master.key
fi

installFlux() {
  message "installing fluxv2"
  flux check --pre > /dev/null
  FLUX_PRE=$?
  if [ $FLUX_PRE != 0 ]; then 
    echo -e "flux prereqs not met:\n"
    flux check --pre
    exit 1
  fi
  if [ -z "$GITHUB_TOKEN" ]; then
    echo "GITHUB_TOKEN is not set! Check $REPO_ROOT/.secrets.env"
    exit 1
  fi
  flux bootstrap github \
    --owner=lokiraze \
    --repository=k3s-gitops \
    --branch master \
    --path cluster \
    --personal

  FLUX_INSTALLED=$?
  if [ $FLUX_INSTALLED != 0 ]; then 
    echo -e "flux did not install correctly, aborting!"
    exit 1
  fi
}

#installFlux


message "all done!"
kubectl get nodes -o=wide