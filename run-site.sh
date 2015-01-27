#/bin/bash

set -ex

GCC=$(sudo docker run -d -p 10240:10240 gcc-explorer)
D=$(sudo docker run -d -p 10241:10241 d-explorer)
RUST=$(sudo docker run -d -p 10242:10242 rust-explorer)

sudo docker run -p 80:80 -v /var/log/nginx:/var/log/nginx -v $(pwd)/nginx:/etc/nginx/sites-enabled dockerfile/nginx
