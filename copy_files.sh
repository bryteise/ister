#!/usr/bin/bash
# usage: update_gui_expect.sh <disk image> <file> <target dir>

function usage()
{
    echo "Usage: $0 <disk.img>"
    exit 1
}

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
sudo /usr/bin/mount ${next_dev}p2 $mnt
sudo cp $2 ${mnt}$3
sudo /usr/bin/umount $mnt
sudo /usr/bin/losetup -D
echo "$1 up to date with latest gui and installer"
