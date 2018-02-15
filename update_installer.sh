#!/usr/bin/bash
# usage: update_installer.sh <disk image>

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
sudo cp ister_gui.py ${mnt}/usr/bin/ister_gui.py
sudo cp ister.py ${mnt}/usr/bin/ister.py
sync
#read -p "Enter to umount"
sudo /usr/bin/umount $mnt
sudo /usr/bin/losetup -D
echo "$1 up to date with latest gui and installer"
