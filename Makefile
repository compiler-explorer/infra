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

$(eval $(call add-image,d,d-explorer))
$(eval $(call add-image,gcc,gcc-explorer))
$(eval $(call add-image,go,go-explorer))
$(eval $(call add-image,rust,rust-explorer))
$(eval $(call add-image,cppx,cppx-explorer))
$(eval $(call add-image,ispc,ispc-explorer))
$(eval $(call add-image,haskell,haskell-explorer))
$(eval $(call add-image,swift,swift-explorer))
$(eval $(call add-image,pascal,pascal-explorer))

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

build-compiler-images:
	$(DOCKER) build $(BUILD_OPT) -t mattgodbolt/clang-builder clang
	$(DOCKER) push mattgodbolt/clang-builder
	$(DOCKER) build $(BUILD_OPT) -t mattgodbolt/gcc-builder gcc
	$(DOCKER) push mattgodbolt/gcc-builder
	$(DOCKER) build $(BUILD_OPT) -t mattgodbolt/gcc-cross gcc-cross
	$(DOCKER) push mattgodbolt/gcc-cross

update-compilers:
	$(DOCKER) build $(BUILD_OPT) -t mattgodbolt/gcc-builder:update update_compilers
	$(DOCKER) push mattgodbolt/gcc-builder:update
	python update_efs_compilers.py --key-file $(KEY_FILE) --key-pair-name $(KEY_PAIR_NAME)

clean:
	echo nothing to clean yet

.PHONY: all clean docker-images base-image $(DOCKER_IMAGES) publish packer update-compilers build-compiler-images
