.NOTPARALLEL: 
all: docker-images

DOCKER := sudo docker
PACKER ?= ../packer/packer
SQUASH := sudo ./docker-squash -verbose

docker-images: gcc-explorer-image d-explorer-image rust-explorer-image gcc-explorer-image-1204 go-explorer-image

docker-squash:
	bash -c "tar zxf <(curl -L https://github.com/jwilder/docker-squash/releases/download/v0.0.11/docker-squash-linux-amd64-v0.0.11.tar.gz)"

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

docker/gcc-explorer/.s3cfg: .s3cfg
	cp $< $@
docker/go-explorer/.s3cfg: .s3cfg
	cp $< $@
docker/gcc-explorer-1204/.s3cfg: .s3cfg
	cp $< $@
docker/d-explorer/.s3cfg: .s3cfg
	cp $< $@
docker/rust-explorer/.s3cfg: .s3cfg
	cp $< $@

go-explorer-image: docker/go-explorer/.s3cfg docker-squash
	$(DOCKER) build -t "mattgodbolt/gcc-explorer-tmp:go" docker/go-explorer
	$(DOCKER) save "mattgodbolt/gcc-explorer-tmp:go" | $(SQUASH) -t "mattgodbolt/gcc-explorer:go" | $(DOCKER) load

gcc-explorer-image: docker/gcc-explorer/.s3cfg docker-squash
	$(DOCKER) build -t "mattgodbolt/gcc-explorer-tmp:gcc" docker/gcc-explorer
	$(DOCKER) save "mattgodbolt/gcc-explorer-tmp:gcc" | $(SQUASH) -t "mattgodbolt/gcc-explorer:gcc" | $(DOCKER) load

gcc-explorer-image-1204: docker/gcc-explorer-1204/.s3cfg docker-squash
	$(DOCKER) build -t "mattgodbolt/gcc-explorer-tmp:gcc1204" docker/gcc-explorer-1204
	$(DOCKER) save "mattgodbolt/gcc-explorer-tmp:gcc1204" | $(SQUASH) -t "mattgodbolt/gcc-explorer:gcc1204" | $(DOCKER) load

d-explorer-image: docker/d-explorer/.s3cfg docker-squash
	$(DOCKER) build -t "mattgodbolt/gcc-explorer-tmp:d" docker/d-explorer
	$(DOCKER) save "mattgodbolt/gcc-explorer-tmp:d" | $(SQUASH) -t "mattgodbolt/gcc-explorer:d" | $(DOCKER) load

rust-explorer-image: docker/rust-explorer/.s3cfg docker-squash
	$(DOCKER) build -t "mattgodbolt/gcc-explorer-tmp:rust" docker/rust-explorer
	$(DOCKER) save "mattgodbolt/gcc-explorer-tmp:rust" | $(SQUASH) -t "mattgodbolt/gcc-explorer:rust" | $(DOCKER) load

publish: docker-images
	sudo docker push mattgodbolt/gcc-explorer

clean:
	echo nothing to clean yet

.PHONY: all clean docker-images gcc-explorer-image gcc-explorer-image-1204 go-explorer-image 
.PHONY: rust-explorer-image source publish packer
