#/bin/bash

set -ex

GCC=$(sudo docker run --name gcc -d -p 10240:10240 gcc-explorer)
D=$(sudo docker run --name d -d -p 10241:10241 d-explorer)
RUST=$(sudo docker run --name rust -d -p 10242:10242 rust-explorer)

sudo docker run \
	-p 80:80 \
	-v /var/log/nginx:/var/log/nginx \
	-v $(pwd)/nginx:/etc/nginx/sites-enabled \
	--link gcc:gcc --link d:d --link rust:rust \
	dockerfile/nginx
