#!/usr/bin/bash
# usage: update_gui_expect.sh <disk image> <expect file> <expect service>

function usage()
{
    echo "Usage: $0 <disk.img> <file.expect> <expect.service>"
    exit 1
}

if [ $# -ne 3 ]
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

if [ ! -e $2 ]
then
        echo $2: Does not exist
        exit 1
fi

if [ ! -e $3 ]
then
        echo $3: Does not exist
        exit 1
fi

mnt=$(/usr/bin/mktemp -d)
next_dev=$(sudo losetup -f --show -P $1)
sudo /usr/bin/mount ${next_dev}p2 $mnt
sudo cp ister_gui.py ${mnt}/usr/bin/ister_gui.py
sudo cp ister.py ${mnt}/usr/bin/ister.py
sudo cp $2 ${mnt}/usr/bin
sudo cp $3 ${mnt}/usr/lib/systemd/system/ister.service
sudo /usr/bin/umount $mnt
sudo /usr/bin/losetup -D
echo "$1 set to use expect to drive install"
