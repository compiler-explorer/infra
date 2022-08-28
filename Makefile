.NOTPARALLEL:

PYTHON:=$(shell env PATH=/bin:/usr/bin:/usr/local/bin bash -c "command -v python3.10 || command -v python3.9 || command -v python3.8 || echo .python3.8-not-found")
VIRTUALENV?=.env
VIRTUALENV_DONE:=$(VIRTUALENV)/.done
export PYTHONPATH=$(CURDIR)/bin

.PHONY: help
help: # with thanks to Ben Rady
	@grep -E '^[0-9a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

PACKER ?= ../packer

$(PYTHON):
	@echo "Python 3.8, 3.9 or 3.10 not found on path. Please install (sudo apt install python3.8 python3.8-venv or similar)"
	@exit 1

config.json: make_json.py | $(PYTHON)
	$(PYTHON) make_json.py

.PHONY: packer
packer: config.json ## Builds the base image for compiler explorer nodes
	$(PACKER) build -timestamp-ui -var-file=config.json $(EXTRA_ARGS) packer-node.json

.PHONY: packer-local
packer-local: config.json ## Builds a local docker version of the compiler explorer node image
	$(PACKER) build -timestamp-ui -var-file=config.json $(EXTRA_ARGS) packer-local.json

.PHONY: packer-admin
packer-admin: config.json  ## Builds the base image for the admin server
	$(PACKER) build -timestamp-ui -var-file=config.json $(EXTRA_ARGS) packer-admin.json

.PHONY: packer-conan
packer-conan: config.json  ## Builds the base image for the CE conan-server
	$(PACKER) build -timestamp-ui -var-file=config.json $(EXTRA_ARGS) packer-conan.json

.PHONY: packer-win
packer-win: config.json  ## Builds the base image for the CE windows
	$(PACKER) build -timestamp-ui -var-file=config.json $(EXTRA_ARGS) packer-win.json

.PHONY: packer-builder
packer-builder: config.json  ## Builds the base image for the CE builder
	$(PACKER) build -timestamp-ui -var-file=config.json $(EXTRA_ARGS) packer-builder.json

.PHONY: clean
clean:  ## Cleans up anything
	rm -rf $(VIRTUALENV)

.PHONY: update-admin
update-admin:  ## Updates the admin website
	aws s3 sync admin/ s3://compiler-explorer/admin/ --cache-control max-age=5 --metadata-directive REPLACE

$(VIRTUALENV_DONE): requirements.txt | $(PYTHON)
	rm -rf $(VIRTUALENV)
	$(PYTHON) -m venv $(VIRTUALENV)
	$(VIRTUALENV)/bin/pip install --upgrade pip
	$(VIRTUALENV)/bin/pip install -r requirements.txt
	touch $(VIRTUALENV_DONE)

.PHONY: ce
ce: $(VIRTUALENV_DONE)  ## Installs and configures the python environment needed for the various admin commands

PY_SOURCE_ROOTS:=bin/lib bin/test lambda

.PHONY: test
test: ce  ## Runs the tests
	$(VIRTUALENV)/bin/pytest $(PY_SOURCE_ROOTS)

.PHONY: static-checks
static-checks: ce  ## Runs all the static tests
	env SKIP=test $(VIRTUALENV)/bin/pre-commit run --all-files

LAMBDA_PACKAGE_DIR:=$(CURDIR)/.dist/lambda-package
LAMBDA_PACKAGE:=$(CURDIR)/.dist/lambda-package.zip
LAMBDA_PACKAGE_SHA:=$(CURDIR)/.dist/lambda-package.zip.sha256
$(LAMBDA_PACKAGE): $(PYTHON) $(wildcard lambda/*) Makefile
	rm -rf $(LAMBDA_PACKAGE_DIR)
	mkdir -p $(LAMBDA_PACKAGE_DIR)
	$(PYTHON) -mpip install -r lambda/requirements.txt -t $(LAMBDA_PACKAGE_DIR)
	cp -R lambda/* $(LAMBDA_PACKAGE_DIR)
	rm -f $(LAMBDA_PACKAGE)
	cd $(LAMBDA_PACKAGE_DIR) && zip -r $(LAMBDA_PACKAGE) .

$(LAMBDA_PACKAGE_SHA): $(LAMBDA_PACKAGE)
	openssl dgst -sha256 -binary $(LAMBDA_PACKAGE) | openssl enc -base64 > $@

.PHONY: lambda-package
lambda-package: $(LAMBDA_PACKAGE) $(LAMBDA_PACKAGE_SHA)

.PHONY: upload-lambda
upload-lambda: lambda-package
	aws s3 cp $(LAMBDA_PACKAGE) s3://compiler-explorer/lambdas/lambda-package.zip
	aws s3 cp --content-type text/sha256 $(LAMBDA_PACKAGE_SHA) s3://compiler-explorer/lambdas/lambda-package.zip.sha256

.PHONY: terraform-apply
terraform-apply:
	cd terraform && terraform apply

.PHONY: pre-commit
pre-commit: ce  ## Runs all pre-commit hooks
	$(VIRTUALENV)/bin/pre-commit run --all-files

.PHONY: install-pre-commit
install-pre-commit: ce  ## Install pre-commit hooks
	$(VIRTUALENV)/bin/pre-commit install
