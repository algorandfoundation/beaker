#!/bin/bash
set -eu

# Make sure the version in setup.py is updated

echo "Removing previous builds"
rm dist/*

echo "Building dist files"
poetry build

echo "Uploading to pypi"
poetry publish --username $PYPI_USERNAME --password $PYPI_PASSWORD

