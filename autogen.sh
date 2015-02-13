#!/bin/sh

set -e

autoreconf --force --install --symlink --warnings=all

args="\
--prefix=/usr \
--sysconfdir=/usr/share/defaults"

./configure $args "$@"
make clean
