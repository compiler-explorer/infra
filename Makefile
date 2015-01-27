.NOTPARALLEL: 
all: docker-images

DOCKER := sudo docker
COMPRESS_FLAGS := -9

docker-images: gcc-explorer-image.xz rust-explorer-image.xz d-explorer-image.xz

gcc-explorer-image.xz: gcc-explorer-image
	$(DOCKER) save gcc-explorer | xz $(COMPRESS_FLAGS) > $@

rust-explorer-image.xz: rust-explorer-image
	$(DOCKER) save rust-explorer | xz $(COMPRESS_FLAGS) > $@

d-explorer-image.xz: d-explorer-image
	$(DOCKER) save d-explorer | xz $(COMPRESS_FLAGS) > $@

.s3cfg: config.py
	echo 'from config import *; print "[default]\\naccess_key = {}\\nsecret_key={}\\n" \
		.format(S3_ACCESS_KEY, S3_SECRET_KEY)' | python > $@

compiler-base/.s3cfg: .s3cfg
	cp $< $@

compiler-base: compiler-base/.s3cfg
	$(DOCKER) build -t "compiler-base" compiler-base

gcc-explorer-image: compiler-base
	$(DOCKER) build -t "gcc-explorer" gcc-explorer

d-explorer-image: compiler-base
	$(DOCKER) build -t "d-explorer" d-explorer

rust-explorer-image: compiler-base
	$(DOCKER) build -t "rust-explorer" rust-explorer

clean:
	echo nothing to clean yet

.PHONY: all clean docker-images compiler-base gcc-explorer-image rust-explorer-image
