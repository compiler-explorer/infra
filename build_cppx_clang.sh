#!/bin/bash

docker run --rm -v$HOME/.ssh:/root/.ssh:ro -v$HOME/.s3cfg:/root/.s3cfg:ro mattgodbolt/clang-builder bash build.sh ignored s3://compiler-explorer/opt/
