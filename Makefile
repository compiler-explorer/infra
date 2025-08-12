.NOTPARALLEL:

# Use system uv if available, otherwise install locally
UV_SYSTEM:=$(shell command -v uv 2>/dev/null)
UV_BIN:=$(if $(UV_SYSTEM),$(UV_SYSTEM),$(CURDIR)/.uv/uv)
UV_VENV:=$(CURDIR)/.venv
UV_DEPS:=$(UV_VENV)/.deps
export PYTHONPATH=$(CURDIR)/bin

.PHONY: help
help: # with thanks to Ben Rady
	@grep -E '^[0-9a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

PACKER ?= packer

$(CURDIR)/.uv/uv:
	@echo "Installing uv..."
	@mkdir -p $(dir $@)
	@curl -LsSf https://astral.sh/uv/install.sh | UV_NO_MODIFY_PATH=1 UV_INSTALL_DIR=$(CURDIR)/.uv sh -s

# Only require local uv installation if system uv is not available
# When UV_SYSTEM is set, UV_BIN points to the system uv, so no dependency needed
# When UV_SYSTEM is empty, UV_BIN points to .uv/uv, but we don't want a circular dependency
ifneq ($(UV_SYSTEM),)
$(UV_BIN):
	@true
endif

config.json: make_json.py | $(UV_DEPS)
	$(UV_BIN) run python make_json.py

.PHONY: packer
packer: config.json ## Builds the base image for compiler explorer nodes
	$(PACKER) build -timestamp-ui -var-file=config.json $(EXTRA_ARGS) packer/node.pkr.hcl

.PHONY: packer-local
packer-local: config.json ## Builds a local docker version of the compiler explorer node image
	$(PACKER) build -timestamp-ui -var-file=config.json $(EXTRA_ARGS) packer/local.pkr.hcl

.PHONY: packer-admin
packer-admin: config.json  ## Builds the base image for the admin server
	$(PACKER) build -timestamp-ui -var-file=config.json $(EXTRA_ARGS) packer/admin.pkr.hcl

.PHONY: packer-conan
packer-conan: config.json  ## Builds the base image for the CE conan-server
	$(PACKER) build -timestamp-ui -var-file=config.json $(EXTRA_ARGS) packer/conan.pkr.hcl

.PHONY: packer-gpu-node
packer-gpu-node: config.json  ## Builds the base image for the CE gpu nodes
	$(PACKER) build -timestamp-ui -var-file=config.json $(EXTRA_ARGS) packer/gpu-node.pkr.hcl

.PHONY: packer-aarch64-node
packer-aarch64-node: config.json  ## Builds the base image for the CE aarch64 nodes
	$(PACKER) build -timestamp-ui -var-file=config.json $(EXTRA_ARGS) packer/aarch64-node.pkr.hcl

.PHONY: packer-smb
packer-smb: config.json  ## Builds the base image for the CE smb-server
	$(PACKER) build -timestamp-ui -var-file=config.json $(EXTRA_ARGS) packer/smb.pkr.hcl

.PHONY: packer-smb-local
packer-smb-local: config.json  ## Builds the base image for the CE smb-server for local testing
	$(PACKER) build -timestamp-ui -var-file=config.json $(EXTRA_ARGS) packer/smb-local.pkr.hcl

.PHONY: packer-win
packer-win: config.json  ## Builds the base image for the CE windows
	$(PACKER) build -timestamp-ui -var-file=config.json $(EXTRA_ARGS) packer/win.pkr.hcl

.PHONY: packer-builder
packer-builder: config.json  ## Builds the base image for the CE builder
	$(PACKER) build -timestamp-ui -var-file=config.json $(EXTRA_ARGS) packer/builder.pkr.hcl

.PHONY: clean
clean:  ## Cleans up everything
	rm -rf $(CURDIR)/.uv $(UV_VENV) uv.lock

.PHONY: update-admin
update-admin:  ## Updates the admin website
	aws s3 sync admin/ s3://compiler-explorer/admin/ --cache-control max-age=5 --metadata-directive REPLACE

.PHONY: ce
ce: $(UV_BIN) $(UV_DEPS)  ## Installs and configures the python environment needed for the various admin commands

$(UV_DEPS): $(UV_BIN) pyproject.toml
	$(UV_BIN) sync --no-install-project
	@touch $@

PY_SOURCE_ROOTS:=bin/lib bin/test lambda

.PHONY: test
test: ce test-compilation-lambda  ## Runs all tests (Python and Node.js)
	$(UV_BIN) run pytest $(PY_SOURCE_ROOTS)

.PHONY: static-checks
static-checks: ce  ## Runs all the static tests
	env SKIP=test $(UV_BIN) run pre-commit run --all-files

.PHONY: mugs
mugs: ce  ## Generate all ABI reference mug designs (SVG + PNG)
	$(UV_BIN) run mugs/make_x86_64_systemv_mug.py mugs/x86_64_systemv_abi_mug.svg
	$(UV_BIN) run mugs/make_x86_64_msvc_mug.py mugs/x86_64_msvc_abi_mug.svg
	$(UV_BIN) run mugs/make_arm64_mug.py mugs/arm64_abi_mug.svg

LAMBDA_PACKAGE:=$(CURDIR)/.dist/lambda-package.zip
LAMBDA_PACKAGE_SHA:=$(CURDIR)/.dist/lambda-package.zip.sha256
$(LAMBDA_PACKAGE) $(LAMBDA_PACKAGE_SHA): $(wildcard lambda/*.py) lambda/pyproject.toml lambda/uv.lock Makefile scripts/build_lambda_deterministic.py
	$(UV_BIN) run python scripts/build_lambda_deterministic.py $(CURDIR)/lambda $(LAMBDA_PACKAGE)

.PHONY: lambda-package  ## builds lambda
lambda-package: $(LAMBDA_PACKAGE) $(LAMBDA_PACKAGE_SHA)

.PHONY: check-lambda-changed
check-lambda-changed: lambda-package
	@mkdir -p $(dir $(LAMBDA_PACKAGE))
	@echo "Checking if lambda package has changed..."
	@aws s3 cp s3://compiler-explorer/lambdas/lambda-package.zip.sha256 $(LAMBDA_PACKAGE_SHA).remote 2>/dev/null || (echo "Remote lambda SHA doesn't exist yet" && touch $(LAMBDA_PACKAGE_SHA).remote)
	@if [ ! -f $(LAMBDA_PACKAGE_SHA).remote ] || ! cmp -s $(LAMBDA_PACKAGE_SHA) $(LAMBDA_PACKAGE_SHA).remote; then \
		echo "Lambda package has changed"; \
		echo "LAMBDA_CHANGED=1" > $(LAMBDA_PACKAGE_SHA).status; \
	else \
		echo "Lambda package has not changed"; \
		echo "LAMBDA_CHANGED=0" > $(LAMBDA_PACKAGE_SHA).status; \
	fi

.PHONY: check-compilation-lambda-changed
check-compilation-lambda-changed: compilation-lambda-package
	@mkdir -p $(dir $(COMPILATION_LAMBDA_PACKAGE))
	@echo "Checking if compilation lambda package has changed..."
	@aws s3 cp s3://compiler-explorer/lambdas/compilation-lambda-package.zip.sha256 $(COMPILATION_LAMBDA_PACKAGE_SHA).remote 2>/dev/null || (echo "Remote compilation lambda SHA doesn't exist yet" && touch $(COMPILATION_LAMBDA_PACKAGE_SHA).remote)
	@if [ ! -f $(COMPILATION_LAMBDA_PACKAGE_SHA).remote ] || ! cmp -s $(COMPILATION_LAMBDA_PACKAGE_SHA) $(COMPILATION_LAMBDA_PACKAGE_SHA).remote; then \
		echo "Compilation lambda package has changed"; \
		echo "COMPILATION_LAMBDA_CHANGED=1" > $(COMPILATION_LAMBDA_PACKAGE_SHA).status; \
	else \
		echo "Compilation lambda package has not changed"; \
		echo "COMPILATION_LAMBDA_CHANGED=0" > $(COMPILATION_LAMBDA_PACKAGE_SHA).status; \
	fi

.PHONY: upload-compilation-lambda
upload-compilation-lambda: check-compilation-lambda-changed
	@. $(COMPILATION_LAMBDA_PACKAGE_SHA).status && \
	if [ "$$COMPILATION_LAMBDA_CHANGED" = "1" ]; then \
		echo "Uploading new compilation lambda package to S3..."; \
		aws s3 cp $(COMPILATION_LAMBDA_PACKAGE) s3://compiler-explorer/lambdas/compilation-lambda-package.zip; \
		aws s3 cp --content-type text/sha256 $(COMPILATION_LAMBDA_PACKAGE_SHA) s3://compiler-explorer/lambdas/compilation-lambda-package.zip.sha256; \
		echo "Compilation lambda package uploaded successfully!"; \
	else \
		echo "Compilation lambda package hasn't changed. No upload needed."; \
	fi

.PHONY: upload-lambda
upload-lambda: check-lambda-changed
	@. $(LAMBDA_PACKAGE_SHA).status && \
	if [ "$$LAMBDA_CHANGED" = "1" ]; then \
		echo "Uploading new lambda package to S3..."; \
		aws s3 cp $(LAMBDA_PACKAGE) s3://compiler-explorer/lambdas/lambda-package.zip; \
		aws s3 cp --content-type text/sha256 $(LAMBDA_PACKAGE_SHA) s3://compiler-explorer/lambdas/lambda-package.zip.sha256; \
		echo "Lambda package uploaded successfully!"; \
	else \
		echo "Lambda package hasn't changed. No upload needed."; \
	fi

EVENTS_LAMBDA_PACKAGE_DIR:=$(CURDIR)/.dist/events-lambda-package
EVENTS_LAMBDA_PACKAGE:=$(CURDIR)/.dist/events-lambda-package.zip
EVENTS_LAMBDA_PACKAGE_SHA:=$(CURDIR)/.dist/events-lambda-package.zip.sha256
EVENTS_LAMBDA_DIR:=$(CURDIR)/events-lambda
$(EVENTS_LAMBDA_PACKAGE): $(wildcard events-lambda/*.js) events-lambda/package.json Makefile
	rm -rf $(EVENTS_LAMBDA_PACKAGE_DIR)
	mkdir -p $(EVENTS_LAMBDA_PACKAGE_DIR)
	cd $(EVENTS_LAMBDA_DIR) && npm i && npm run lint && npm install --no-audit --ignore-scripts --production && npm install --no-audit --ignore-scripts --production --cpu arm64 && cd ..
	cp -R $(EVENTS_LAMBDA_DIR)/* $(EVENTS_LAMBDA_PACKAGE_DIR)
	rm -f $(EVENTS_LAMBDA_PACKAGE)
	cd $(EVENTS_LAMBDA_PACKAGE_DIR) && zip -r $(EVENTS_LAMBDA_PACKAGE) .

$(EVENTS_LAMBDA_PACKAGE_SHA): $(EVENTS_LAMBDA_PACKAGE)
	openssl dgst -sha256 -binary $(EVENTS_LAMBDA_PACKAGE) | openssl enc -base64 > $@

.PHONY: events-lambda-package  ## builds events lambda
events-lambda-package: $(EVENTS_LAMBDA_PACKAGE) $(EVENTS_LAMBDA_PACKAGE_SHA)

COMPILATION_LAMBDA_PACKAGE:=$(CURDIR)/.dist/compilation-lambda-package.zip
COMPILATION_LAMBDA_PACKAGE_SHA:=$(CURDIR)/.dist/compilation-lambda-package.zip.sha256
$(COMPILATION_LAMBDA_PACKAGE) $(COMPILATION_LAMBDA_PACKAGE_SHA): $(wildcard compilation-lambda/*.js) $(wildcard compilation-lambda/lib/*.js) compilation-lambda/package.json Makefile scripts/build_nodejs_lambda_deterministic.py
	$(UV_BIN) run python scripts/build_nodejs_lambda_deterministic.py $(CURDIR)/compilation-lambda $(COMPILATION_LAMBDA_PACKAGE)

.PHONY: compilation-lambda-package  ## builds compilation lambda
compilation-lambda-package: $(COMPILATION_LAMBDA_PACKAGE) $(COMPILATION_LAMBDA_PACKAGE_SHA)

.PHONY: test-compilation-lambda  ## runs compilation lambda tests
test-compilation-lambda:
	cd compilation-lambda && npm install && npm test

.PHONY: events-lambda-package  ## Builds events-lambda
events-lambda-package: $(EVENTS_LAMBDA_PACKAGE) $(EVENTS_LAMBDA_PACKAGE_SHA)

.PHONY: upload-events-lambda
upload-events-lambda: events-lambda-package  ## Uploads events-lambda to S3
	aws s3 cp $(EVENTS_LAMBDA_PACKAGE) s3://compiler-explorer/lambdas/events-lambda-package.zip
	aws s3 cp --content-type text/sha256 $(EVENTS_LAMBDA_PACKAGE_SHA) s3://compiler-explorer/lambdas/events-lambda-package.zip.sha256

.PHONY: terraform-apply
terraform-apply:  upload-lambda upload-compilation-lambda upload-events-lambda ## Applies terraform
	terraform -chdir=terraform apply

.PHONY: terraform-plan
terraform-plan:  upload-lambda upload-compilation-lambda upload-events-lambda ## Plans terraform changes
	terraform -chdir=terraform plan

.PHONY: pre-commit
pre-commit: ce  ## Runs all pre-commit hooks
	$(UV_BIN) run pre-commit run --all-files

.PHONY: install-pre-commit
install-pre-commit: ce  ## Install pre-commit hooks
	$(UV_BIN) run pre-commit install
