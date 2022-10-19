#!/bin/bash

set -euf -o pipefail

MODE=""

for arg in "$@"
do
  case $arg in
    -c|--check)
    MODE="check"
    shift
    ;;
  esac
done


pushd "$PWD" && \
  cd examples/amm && \  # source ../.venv/bin/activate \
  rm -rf artifacts/ && \
  python amm.py && \
  popd

if [[ "$MODE" == "check" && -n "$(git status --porcelain)" ]]; then
  git status --porcelain
  echo "Local changes exist - was \`make gen\` run?";
  exit 1;
fi
