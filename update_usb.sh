#!/usr/bin/bash
# usage: update_installer.sh <disk image>

function usage()
{
    echo "Usage: $0 <USB Dev>"
    exit 1
}

function run_cmd()
{
    ${@}
    status=$?
    if [ ${status} -ne 0 ]
    then
        echo "Error ${status}: ${@}"
        exit ${status}
    fi
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
run_cmd "sudo /usr/bin/mount ${1}3 $mnt"
run_cmd "sudo cp ister_gui.py ${mnt}/usr/bin/ister_gui.py"
run_cmd "sudo cp ister.py ${mnt}/usr/bin/ister.py"
run_cmd "sync"
#read -p "Enter to umount"
run_cmd "sudo /usr/bin/umount $mnt"
run_cmd "sudo eject $1"
echo "$1 up to date with latest gui and installer"
