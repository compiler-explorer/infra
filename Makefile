.NOTPARALLEL: 

help: # with thanks to Ben Rady
	@grep -E '^[0-9a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

PACKER ?= ../packer

config.json: make_json.py
	python3 make_json.py

packer: config.json ## Builds the base image for compiler explorer nodes
	$(PACKER) build -timestamp-ui -var-file=config.json packer.json

packer-local: config.json ## Builds a local docker version of the compiler explorer node image
	$(PACKER) build -timestamp-ui -var-file=config.json packer-local.json

packer-admin: config.json  ## Builds the base image for the admin server
	$(PACKER) build -timestamp-ui -var-file=config.json packer-admin.json

clean:
	echo nothing to clean yet

update-admin:  ## Updates the admin website
	aws s3 sync admin/ s3://compiler-explorer/admin/ --cache-control max-age=5 --metadata-directive REPLACE

VIRTUALENV?=.env

$(VIRTUALENV): requirements.txt
	rm -rf $(VIRTUALENV)
	python3 -mvenv $(VIRTUALENV)	
	$(VIRTUALENV)/bin/pip install -r requirements.txt

ce: $(VIRTUALENV)  ## Installs and configures the python environment needed for the various admin commands

test: ce  ## Runs the tests
	$(VIRTUALENV)/bin/nosetests bin

.PHONY: clean packer packer-admin packer-local update-admin ce test
