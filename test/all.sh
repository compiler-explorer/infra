#!/bin/bash

set -e

URL=${1:-godbolt.org}
ARGS=${2}

test/remote-test.py http://gcc.${URL}/ test/remote-cases/c++ ${ARGS}
test/remote-test.py http://d.${URL}/ test/remote-cases/d ${ARGS}
test/remote-test.py http://go.${URL}/ test/remote-cases/go ${ARGS}
test/remote-test.py http://rust.${URL}/ test/remote-cases/rust ${ARGS}
