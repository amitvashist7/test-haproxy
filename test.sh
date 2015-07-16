#!/bin/bash

echo "=> Building testing environment image"
docker build -t test-haproxy -f Dockerfile-test .

docker run --privileged -ti --rm -e DOCKER_USER=${DOCKER_USER} -e DOCKER_PASS=${DOCKER_PASS} -e TUTUM_USER=${TUTUM_USER} -e TUTUM_APIKEY=${TUTUM_APIKEY} test-haproxy
