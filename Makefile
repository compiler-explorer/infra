.NOTPARALLEL: 
all: docker-images

docker-images: gcc-explorer-image d-explorer-image

.s3cfg: config.py
	echo 'from config import *; print "[default]\\naccess_key = {}\\nsecret_key={}\\n" \
		.format(S3_ACCESS_KEY, S3_SECRET_KEY)' | python > $@

compiler-base/.s3cfg: .s3cfg
	cp $< $@

compiler-base: compiler-base/.s3cfg
	sudo docker build -t "compiler-base" compiler-base

gcc-explorer-image: compiler-base
	sudo docker build -t "gcc-explorer" gcc-explorer
d-explorer-image: compiler-base
	sudo docker build -t "d-explorer" d-explorer

clean:
	echo nothing to clean yet

.PHONY: all clean docker-images compiler-base gcc-explorer-image
