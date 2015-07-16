#!/bin/bash

echo "=> Starting docker"
wrapdocker > /dev/null 2>&1 &
sleep 10
echo "=> Checking docker daemon"
docker version > /dev/null 2>&1 || (echo "   Failed to start docker (did you use --privileged when running this container?)" && exit 1)

echo "=> Starting tests"
make
