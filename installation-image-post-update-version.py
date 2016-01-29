#!/usr/bin/python3

import os
import sys

INSTALLER_VERSION = "6000"

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
    "Version" : 0, "Bundles" : ["kernel-native", "telemetrics", "os-core", "os-core-update"]}\n'
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


def disable_tty1_getty(path):
    """Add a symlink masking the systemd tty1 generator"""
    os.makedirs(path + "/etc/systemd/system/getty.target.wants")
    os.symlink("/dev/null", path + "/etc/systemd/system/getty.target.wants/getty@tty1.service")


def add_installer_service(path):
    os.symlink("{}/usr/lib/systemd/system/ister.service"
               .format(path),
               "{}/usr/lib/systemd/system/multi-user.target.wants/ister.service"
               .format(path))


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(-1)

    try:
        create_installer_config(sys.argv[1])
        append_installer_rootdelay(sys.argv[1])
        disable_tty1_getty(sys.argv[1])
        add_installer_service(sys.argv[1])
    except Exception as exep:
        print(exep)
        sys.exit(-1)
    sys.exit(0)
