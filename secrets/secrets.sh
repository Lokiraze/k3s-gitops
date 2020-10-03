#!/usr/bin/env bash

#
# Get Absolute Path of the base repos
export REPO_ROOT=$(git rev-parse --show-toplevel)

need() {
    if ! [ -x "$(command -v $1)" ]; then
      echo "Error: Unable to find binary $1"
      exit 1
    fi
}

# Verify we have dependencies
need "kubeseal"
need "kubectl"
need "sed"
need "envsubst"
need "yq"

# Work-arounds for MacOS
if [ "$(uname)" == "Darwin" ]; then
  # brew install gnu-sed
  need "gsed"
  # use sed as alias to gsed
  export PATH="/usr/local/opt/gnu-sed/libexec/gnubin:$PATH"
  # Source secrets.env
  set -a
  . "${REPO_ROOT}/secrets/.secrets.env"
  set +a
  echo "The Domain is currently set to: ${DOMAIN}"
else
  . "${REPO_ROOT}/secrets/.secrets.env"
  echo "The Domain is currently set to: ${DOMAIN}"
fi