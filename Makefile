.NOTPARALLEL: 

PYTHON:=$(shell which python3.8 || echo .python3.8-not-found)
VIRTUALENV?=.env
export PYTHONPATH=$(CURDIR)/bin

.PHONY: help
help: # with thanks to Ben Rady
	@grep -E '^[0-9a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

PACKER ?= ../packer

$(PYTHON):
	@echo "Python 3.8 not found on path. Please install (sudo apt install python3.8 python3.8-venv or similar)"
	@exit 1

config.json: make_json.py | $(PYTHON)
	$(PYTHON) make_json.py

.PHONY: packer
packer: config.json ## Builds the base image for compiler explorer nodes
	$(PACKER) build -timestamp-ui -var-file=config.json packer.json

.PHONY: packer-local
packer-local: config.json ## Builds a local docker version of the compiler explorer node image
	$(PACKER) build -timestamp-ui -var-file=config.json packer-local.json

.PHONY: packer-admin
packer-admin: config.json  ## Builds the base image for the admin server
	$(PACKER) build -timestamp-ui -var-file=config.json packer-admin.json

.PHONY: clean
clean:  ## Cleans up anything
	rm -rf $(VIRTUALENV)

.PHONY: update-admin
update-admin:  ## Updates the admin website
	aws s3 sync admin/ s3://compiler-explorer/admin/ --cache-control max-age=5 --metadata-directive REPLACE

$(VIRTUALENV): requirements.txt | $(PYTHON)
	rm -rf $(VIRTUALENV)
	$(PYTHON) -m venv $(VIRTUALENV)
	if [[ ! -x $(VIRTUALENV)/bin/pip ]]; then $(PYTHON) -m ensurepip --root $(VIRTUALENV); fi
	ls -l $(VIRTUALENV)/bin
	$(VIRTUALENV)/bin/pip install -r requirements.txt

.PHONY: ce
ce: $(VIRTUALENV)  ## Installs and configures the python environment needed for the various admin commands

.PHONY: test
test: ce  ## Runs the tests
	$(VIRTUALENV)/bin/pytest bin

.PHONY: static-checks
static-checks: ce  ## Runs all the static tests
	$(VIRTUALENV)/bin/mypy --ignore-missing-imports bin
