.NOTPARALLEL: 
all: docker-images

DOCKER := sudo docker
COMPRESS_FLAGS := -9

docker-images: gcc-explorer-image d-explorer-image rust-explorer-image

.s3cfg: config.py
	echo 'from config import *; print "[default]\\naccess_key = {}\\nsecret_key={}\\n" \
		.format(S3_ACCESS_KEY, S3_SECRET_KEY)' | python > $@

compiler-base/.s3cfg: .s3cfg
	cp $< $@

compiler-base: compiler-base/.s3cfg
	$(DOCKER) build -t "mattgodbolt/gcc-explorer:base" compiler-base

gcc-explorer-image: compiler-base
	$(DOCKER) build -t "mattgodbolt/gcc-explorer:gcc" gcc-explorer

d-explorer-image: compiler-base
	$(DOCKER) build -t "mattgodbolt/gcc-explorer:d" d-explorer

rust-explorer-image: compiler-base
	$(DOCKER) build -t "mattgodbolt/gcc-explorer:rust" rust-explorer

clean:
	echo nothing to clean yet

.PHONY: all clean docker-images compiler-base gcc-explorer-image rust-explorer-image
