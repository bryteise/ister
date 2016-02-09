#!/usr/bin/bash

function usage()
{
    echo "Usage: $0 <disk.img>"
    exit 1
}

if [ $# -ne 1 ]
then
        usage
fi

if [ $1 == "-h" ]
then
        usage
fi

if [ ! -e $1 ]
then
        echo $1: Does not exist
        exit 1
fi

mnt=$(/usr/bin/mktemp -d)
next_dev=$(sudo losetup -f --show -P $1)
sudo /usr/bin/mount ${next_dev}p3 $mnt

if [ ! -e ${mnt}/usr/bin ]
then
        echo "Install to installer-target.img failed"
        sudo /usr/bin/losetup -D
        exit 1
else
        sudo /usr/bin/cp -f boot-canary.sh ${mnt}/usr/bin/boot-canary.sh
        sudo /usr/bin/cp -f boot-canary.service ${mnt}/usr/lib/systemd/system/boot-canary.service
        sudo /usr/bin/ln -f -s ../boot-canary.service ${mnt}/usr/lib/systemd/system/multi-user.target.wants
        sudo /usr/bin/umount $mnt
        sudo /usr/bin/losetup -D
        echo "Canary script and service installed to $1"
fi
