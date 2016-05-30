#!/bin/bash

set -ex

. /site.sh

[[ ! -e /gcc-explorer/.git ]] && git clone -b ${BRANCH} --depth 1 https://github.com/mattgodbolt/gcc-explorer.git /gcc-explorer
cd /gcc-explorer
git pull
rm -rf node_modules
cp -r /tmp/node_modules .
make prereqs
./node_modules/.bin/forever -a -f -d -v -c \
	"node --prof --track_gc_object_stats --trace_gc_verbose --optimize_for_size --log_timer_events" \
	app.js --env amazon --port 10240 --lang C++
