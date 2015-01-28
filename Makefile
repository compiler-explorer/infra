.NOTPARALLEL: 
all: docker-images

DOCKER := sudo docker
COMPRESS_FLAGS := -9
BASE_DIR := docker/compiler-base
SOURCE_DIR := $(BASE_DIR)/gcc-explorer

docker-images: gcc-explorer-image d-explorer-image rust-explorer-image

.s3cfg: config.py
	echo 'from config import *; print "[default]\\naccess_key = {}\\nsecret_key={}\\n" \
		.format(S3_ACCESS_KEY, S3_SECRET_KEY)' | python > $@

$(BASE_DIR)/.s3cfg: .s3cfg
	cp $< $@

source:
	rm -rf $(SOURCE_DIR)
	mkdir -p $(SOURCE_DIR)
	cp -r gcc-explorer/* $(SOURCE_DIR)
	cd $(SOURCE_DIR) && $(shell pwd)/fixup-times.sh

compiler-base: $(BASE_DIR)/.s3cfg source
	$(DOCKER) build -t "mattgodbolt/gcc-explorer:base" $(BASE_DIR)

gcc-explorer-image: compiler-base
	$(DOCKER) build -t "mattgodbolt/gcc-explorer:gcc" docker/gcc-explorer

d-explorer-image: compiler-base
	$(DOCKER) build -t "mattgodbolt/gcc-explorer:d" docker/d-explorer

rust-explorer-image: compiler-base
	$(DOCKER) build -t "mattgodbolt/gcc-explorer:rust" docker/rust-explorer

clean:
	echo nothing to clean yet

.PHONY: all clean docker-images compiler-base gcc-explorer-image rust-explorer-image source
