#!/bin/bash

REPO_ROOT=$(git rev-parse --show-toplevel)
KUBECONFIG=:"${REPO_ROOT}"/provision/kubeconfig:~/.kube/config kubectl config view --flatten > ~/.kube/config.tmp && \
  mv ~/.kube/config.tmp ~/.kube/config


kubectl get nodes -o=wide
