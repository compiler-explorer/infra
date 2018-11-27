.NOTPARALLEL: 
all: docker-images

DOCKER := sudo docker
PACKER ?= ../packer
KEY_FILE ?= $(HOME)/ec2-mattgodbolt.pem
KEY_PAIR_NAME ?= mattgodbolt

BUILD_OPT = $${https_proxy:+--build-arg https_proxy=$$https_proxy} $${http_proxy:+--build-arg http_proxy=$$http_proxy}

define add-image
DOCKER_IMAGES += $(2)-image

$(2)-image: base-image
	$(DOCKER) build $(BUILD_OPT) -t "mattgodbolt/compiler-explorer:$(1)" docker/$(2)

endef

base-image:
	$(DOCKER) build $(BUILD_OPT) -t "mattgodbolt/compiler-explorer:base" docker/base

$(eval $(call add-image,unified,unified-explorer))

exec-image:
	$(DOCKER) build $(BUILD_OPT) -t "mattgodbolt/compiler-explorer:exec" exec

DOCKER_IMAGES += exec-image

docker-images: $(DOCKER_IMAGES)

config.json: make_json.py
	python make_json.py

packer: config.json
	$(PACKER) build -var-file=config.json packer.json 

packer-admin: config.json
	$(PACKER) build -var-file=config.json packer-admin.json 

publish: docker-images
	$(DOCKER) push $(BUILD_OPT) mattgodbolt/compiler-explorer

clean:
	echo nothing to clean yet

update-admin:
	aws s3 sync admin/ s3://compiler-explorer/admin/ --cache-control max-age=5 --metadata-directive REPLACE

.PHONY: all clean docker-images base-image $(DOCKER_IMAGES) publish packer update-compilers build-compiler-images update-admin
