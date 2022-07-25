#!/bin/bash

echo "Removing previous builds"
rm dist/*


echo "Building dist files"
python -m build

echo "Uploading to pypi"
python -m twine upload dist/*

