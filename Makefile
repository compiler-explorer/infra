.NOTPARALLEL: 
all: docker-images

DOCKER := sudo docker
PACKER ?= ../packer

define add-image
DOCKER_IMAGES += $(2)-image

docker/$(2)/.s3cfg: .s3cfg
	cp $$< $$@

$(2)-image: docker/$(2)/.s3cfg base-image
	$(DOCKER) build -t "mattgodbolt/gcc-explorer:$(1)" docker/$(2)

endef

base-image:
	$(DOCKER) build -t "mattgodbolt/gcc-explorer:base" docker/base

$(eval $(call add-image,d,d-explorer))
$(eval $(call add-image,gcc,gcc-explorer))
$(eval $(call add-image,go,go-explorer))
$(eval $(call add-image,rust,rust-explorer))

exec-image:
	$(DOCKER) build -t "mattgodbolt/gcc-explorer:exec" exec

DOCKER_IMAGES += exec-image

docker-images: $(DOCKER_IMAGES)

.s3cfg: config.py
	echo 'from config import *; print "[default]\\naccess_key = {}\\nsecret_key={}\\n" \
		.format(S3_ACCESS_KEY, S3_SECRET_KEY)' | python > $@

config.json: config.py make_json.py
	python make_json.py

packer/id_rsa: config.py
	echo 'from config import *; print PRIVATE_KEY' | python > $@

packer/id_rsa.pub: config.py
	echo 'from config import *; print PUBLIC_KEY' | python > $@

packer/dockercfg: config.py
	echo 'from config import *; print DOCKER_CFG' | python > $@

packer: config.json packer/id_rsa packer/id_rsa.pub packer/dockercfg
	$(PACKER) build -var-file=config.json packer.json 

publish: docker-images
	$(DOCKER) push mattgodbolt/gcc-explorer

build-compiler-images:
	$(DOCKER) build -t mattgodbolt/clang-builder clang
	$(DOCKER) push mattgodbolt/clang-builder
	$(DOCKER) build -t mattgodbolt/gcc-builder gcc
	$(DOCKER) push mattgodbolt/gcc-builder
	$(DOCKER) build -t mattgodbolt/gcc-cross gcc-cross
	$(DOCKER) push mattgodbolt/gcc-cross

update-compilers:
	$(DOCKER) build -t mattgodbolt/gcc-builder:update update_compilers
	$(DOCKER) push mattgodbolt/gcc-builder:update
	python update_efs_compilers.py

clean:
	echo nothing to clean yet

.PHONY: all clean docker-images base-image $(DOCKER_IMAGES) publish packer update-compilers build-compiler-images
