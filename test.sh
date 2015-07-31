#!/bin/bash

echo "=> Building testing environment image"
docker build -t test-haproxy -f Dockerfile-test .

docker run --privileged -ti --rm test-haproxy
