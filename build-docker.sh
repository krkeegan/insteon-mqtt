#!/bin/bash

docker run --rm --privileged \
  -v ~/.docker:/root/.docker \
  homeassistant/amd64-builder --armhf --test \
  -r https://github.com/krkeegan/insteon-mqtt \
  -b docker
