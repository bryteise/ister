#!/usr/bin/python3

import os
import sys

INSTALLER_VERSION = "4340"

def create_installer_config(path):
    """Create a basicl installation configuration file"""
    config = u"template=file:///etc/ister.json\n"
    jconfig = u'{"DestinationType" : "physical", "PartitionLayout" : \
    [{"disk" : "sda", "partition" : 1, "size" : "512M", "type" : "EFI"}, \
    {"disk" : "sda", "partition" : 2, \
    "size" : "512M", "type" : "swap"}, {"disk" : "sda", "partition" : 3, \
    "size" : "rest", "type" : "linux"}], \
    "FilesystemTypes" : \
    [{"disk" : "sda", "partition" : 1, "type" : "vfat"}, \
    {"disk" : "sda", "partition" : 2, "type" : "swap"}, \
    {"disk" : "sda", "partition" : 3, "type" : "ext4"}], \
    "PartitionMountPoints" : \
    [{"disk" : "sda", "partition" : 1, "mount" : "/boot"}, \
    {"disk" : "sda", "partition" : 3, "mount" : "/"}], \
    "Version" : 0, "Bundles" : ["kernel-native", "os-core", "os-core-update", \
    "telemetrics"]}\n'
    if not os.path.isdir("{}/etc".format(path)):
        os.mkdir("{}/etc".format(path))
    with open("{}/etc/ister.conf".format(path), "w") as cfile:
        cfile.write(config)
    with open("{}/etc/ister.json".format(path), "w") as jfile:
        jfile.write(jconfig.replace('"Version" : 0',
                                    '"Version" : ' + INSTALLER_VERSION))


def append_installer_rootdelay(path):
    """Add a delay to the installer kernel commandline"""
    entry_path = path + "/boot/loader/entries/"
    entry_file = os.listdir(entry_path)
    if len(entry_file) != 1:
        raise Exception("Unable to find specific entry file in {0}, "
                        "found {1} instead".format(entry_path, entry_file))
    file_full_path = entry_path + entry_file[0]
    with open(file_full_path, "r") as entry:
        entry_content = entry.readlines()
    options_line = entry_content[-1]
    if not options_line.startswith("options "):
        raise Exception("Last line of entry file is not the kernel "
                        "commandline options")
    # Account for newline at the end of the line
    options_line = options_line[:-1] + " rootdelay=5\n"
    entry_content[-1] = options_line
    os.unlink(file_full_path)
    with open(file_full_path, "w") as entry:
        entry.writelines(entry_content)


def set_motd_notification(path):
    """Create a motd file for to display to users of installer images"""
    message = """Clear Linux for Intel Architecture installation image

!!!!RUNNING THE INSTALLATION COMMAND WILL WIPE YOUR DISK!!!!
You can login to the installer image as root and start an installation with:

    python3 /usr/bin/ister.py

Your computer will power off once installation completes successfully.
"""
    with open(path + "/etc/issue", "w") as mfile:
        mfile.write(message)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(-1)

    try:
        create_installer_config(sys.argv[1])
        append_installer_rootdelay(sys.argv[1])
        set_motd_notification(sys.argv[1])
    except Exception as exep:
        print(exep)
        sys.exit(-1)
    sys.exit(0)
