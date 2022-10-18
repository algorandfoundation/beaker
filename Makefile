# ---- Setup ---- #

setup-development:
	pip install -e .
	pip install -r requirements.txt --upgrade

setup-wheel:
	pip install wheel

# ---- Docs and Distribution ---- #

bdist-wheel:
	python setup.py sdist bdist_wheel


# ---- Code Quality ---- #

ALLPY = beaker *.py
black:
	black --check $(ALLPY)

flake8:
	flake8 $(ALLPY)

MYPY = beaker examples/amm
mypy:
	mypy --show-error-codes $(MYPY)

lint: black flake8 mypy


# ---- Tests ---- #

tests:
	pytest beaker examples/amm

lint-and-test: lint tests

# ---- Integration Tests (algod required) ---- #

all-tests: lint-and-test

# ---- Local Github Actions Simulation via `act` ---- #
# assumes act is installed, e.g. via `brew install act`

ACT_JOB = run-integration-tests
local-gh-job:
	act -j $(ACT_JOB)

local-gh-simulate:
	act

# ---- Extras ---- #
coverage:
	pytest --cov-report html --cov=pyteal

gen:
	./scripts/gen.sh

gen-check:
	./scripts/gen.sh -c
