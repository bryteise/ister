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
if [ -e ${mnt}/canary ]
then
        rc=0
else
        rc=1
fi
sudo /usr/bin/umount $mnt
sudo /usr/bin/losetup -D
exit $rc
