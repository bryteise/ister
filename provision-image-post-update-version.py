#!/usr/bin/python3

import os
import sys

INSTALLER_VERSION = "5210"

def create_provision_config(path):
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


def add_provision_symlink(path):
    os.symlink("{}/usr/lib/systemd/system/ister-provision.service"
               .format(path),
               "{}/usr/lib/systemd/system/multi-user.target.wants/ister-provision.service"
               .format(path))


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(-1)

    try:
        create_provision_config(sys.argv[1])
        add_provision_symlink(sys.argv[1])
    except Exception as exep:
        print(exep)
        sys.exit(-1)
    sys.exit(0)
