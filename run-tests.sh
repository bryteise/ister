#!/bin/bash

set -eu
set -o pipefail
set -o errtrace

# test_image is a raw disk image
# source_image is a xz compressed disk image
# device is a nbd device node
test_image=$1
source_image=$2
device=$3

enable_nbd() {
    local __nbd_cleanup=$1
    if [ -b "/dev/nbd0" ] ; then
	eval $__nbd_cleanup=0
    else
	modprobe nbd max_part=16 &> /dev/null
	eval $__nbd_cleanup=1
    fi
}

setup() {
    local timg=$1
    local simg=$2
    local dev=$3
    cp "${timg}" test.img
    qemu-img create target.img -f qcow2 1500M &> /dev/null
    qemu-nbd -c "${dev}" test.img &> /dev/null
    partprobe "${dev}" &> /dev/null
    mkdir test/
    mount "${dev}p2" test/ &> /dev/null
    mount "${dev}p1" test/boot/ &> /dev/null
    cp ister-test.service test/usr/lib/systemd/system/multi-user.target.wants/ister.service
    cp "${simg}" test/good.raw.xz
    cp "${simg}" good.raw.xz
    cp ister.py test/root/
    cp ister_test.py test/root/
    cp good-ister.conf test/root/
    cp min-good.json test/root/
    cp key.pub test/root/
    umount test/boot/ &> /dev/null
    umount test/ &> /dev/null
    qemu-nbd -d "${dev}" &> /dev/null
}

run_qemu() {
    qemu-system-x86_64 -bios efi.bios -m 1024 -usb -device usb-kbd -cpu qemu64,+vmx -enable-kvm -hda test.img -hdb target.img &> /dev/null
}

run_tests() {
    python3 -m http.server 8001 &
    local httpd_process=$!
    run_qemu
    kill "${httpd_process}"
}

copy_logs() {
    local dev=$1
    qemu-nbd -c "${dev}" test.img &> /dev/null
    partprobe "${dev}"
    mount "${dev}p2" test/ &> /dev/null
    cp test/root/test-log ./
    umount test/ &> /dev/null
    qemu-nbd -d "${dev}" &> /dev/null
    cat test-log
}

cleanup() {
    rm -rf test/
    rm -fr target/
    rm -f test.img
    rm -f target.img
    rm -f good.raw.xz
    if [ "${nbd_cleanup}" -eq 1 ] ; then
	rmmod nbd &> /dev/null
    fi
}

error() {
    set +e
    local lno=$1

    echo "Error near ${lno}"

    umount test/boot/ &> /dev/null
    umount test/ &> /dev/null
    umount target/boot/ &> /dev/null
    umount target/ &> /dev/null
    qemu-nbd -d "${device}" &> /dev/null
    cleanup
    exit -1
}
trap 'error ${LINENO}' ERR

enable_nbd nbd_cleanup

setup "${test_image}" "${source_image}" "${device}"
(run_tests &> /dev/null)
copy_logs "${device}"
cleanup
exit 0
