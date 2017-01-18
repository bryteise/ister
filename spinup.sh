#!/bin/bash

set -e

x(){
    echo -- "$@" >&2
    "$@"
}

runinst(){
    qemu-system-x86_64 -enable-kvm -m 1024 -vnc 0.0.0.0:0 -cpu host \
      -drive file=installer.img,if=virtio,aio=threads -net nic,model=virtio \
      -drive file=installer-target.img,if=virtio,aio=threads \
      -net user,hostfwd=tcp::$1-:22 -smp 2 -bios ./OVMF.fd &
}

newtarget(){
        x rm -f installer-target.img
        x qemu-img create installer-target.img 10G
}

if [[ -z $1 ]]; then
        port="2233"
else
        port=$1
fi

if [[ ! -f ./installer-target.img ]]; then
        echo "Creating new installer target"
        newtarget
fi
echo Using port $port
runinst $port
bg_pid=$!
sleep 1
vncviewer 0.0.0.0
sudo kill $bg_pid

