#!/bin/bash

set -e

URL=${1:-godbolt.org}
shift

test/remote-test.py "http://gcc.${URL}/" test/remote-cases/c++ "$*"
test/remote-test.py "http://d.${URL}/" test/remote-cases/d "$*"
test/remote-test.py "http://go.${URL}/" test/remote-cases/go "$*"
test/remote-test.py "http://rust.${URL}/" test/remote-cases/rust "$*"
