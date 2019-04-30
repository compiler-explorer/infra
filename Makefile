.NOTPARALLEL: 
all: docker-images

help: # with thanks to Ben Rady
	@grep -E '^[0-9a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

DOCKER := docker
PACKER ?= ../packer

BUILD_OPT = $${https_proxy:+--build-arg https_proxy=$$https_proxy} $${http_proxy:+--build-arg http_proxy=$$http_proxy}

define add-image
DOCKER_IMAGES += $(2)-image

$(2)-image: base-image
	$(DOCKER) build $(BUILD_OPT) -t "mattgodbolt/compiler-explorer:$(1)" docker/$(2)

endef

base-image:
	$(DOCKER) build $(BUILD_OPT) -t "mattgodbolt/compiler-explorer:base" docker/base

$(eval $(call add-image,unified,unified-explorer))

docker-images: $(DOCKER_IMAGES)  ## Builds all the docker images (deprecated in favour of docker hub)

config.json: make_json.py
	python make_json.py

packer: config.json ## Builds the base image for compiler explorer nodes
	$(PACKER) build -var-file=config.json packer.json 

packer-admin: config.json  ## Builds the base image for the admin server
	$(PACKER) build -var-file=config.json packer-admin.json 

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

.PHONY: all clean docker-images base-image $(DOCKER_IMAGES) packer update-compilers build-compiler-images update-admin ce test
