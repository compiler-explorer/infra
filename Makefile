.NOTPARALLEL: 
all: docker-images

DOCKER := sudo docker
PACKER ?= ../packer/packer

define add-image
DOCKER_IMAGES += $(2)-image

docker/$(2)/.s3cfg: .s3cfg
	cp $$< $$@

docker/$(2)/package.json: package.json
	cp $$< $$@

$(2)-image: docker/$(2)/.s3cfg docker/$(2)/package.json
	$(DOCKER) build -t "mattgodbolt/gcc-explorer:$(1)" docker/$(2)

endef

$(eval $(call add-image,d,d-explorer))
$(eval $(call add-image,gcc,gcc-explorer))
$(eval $(call add-image,gcc1204,gcc-explorer-1204))
$(eval $(call add-image,go,go-explorer))
$(eval $(call add-image,rust,rust-explorer))

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
	sudo docker push mattgodbolt/gcc-explorer

clean:
	echo nothing to clean yet

.PHONY: all clean docker-images $(DOCKER_IMAGES) publish packer 
