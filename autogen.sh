#!/bin/sh

set -e

autoreconf --force --install --symlink --warnings=all

args="\
--prefix=/usr"

./configure $args "$@"
make clean
