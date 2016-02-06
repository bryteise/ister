#!/usr/bin/bash
# usage: update_gui_expect.sh <disk image>

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
fi

mnt=$(/usr/bin/mktemp -d)
next_dev=$(sudo losetup -f --show -P $1)
sudo /usr/bin/mount ${next_dev}p2 $mnt
sudo cp ister_gui.py ${mnt}/usr/bin/ister_gui.py
sudo cp autoinstall-first-gen.expect ${mnt}/usr/bin
sudo cp ister-expect.service ${mnt}/usr/lib/systemd/system/ister.service
sudo /usr/bin/umount $mnt
sudo /usr/bin/losetup -D
echo "ister_gui.py copied to ${mnt}/usr/bin/ister_gui.py"
