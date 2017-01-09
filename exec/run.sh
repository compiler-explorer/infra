#!/bin/bash

ulimit -t 3 # CPU time in seconds
ulimit -m $((128 * 1024)) # RSS limit in K
ulimit -v $((256 * 1024)) # virtual RAM limit in K

sudo -n -u ce-user -- "$*"
