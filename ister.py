#!/usr/bin/python3
"""Linux installation template system"""

#
# This file is part of ister.
#
# Copyright (C) 2014 Intel Corporation
#
# ister is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by the
# Free Software Foundation; version 3 of the License, or (at your
# option) any later version.
#
# You should have received a copy of the GNU General Public License
# along with this program in a file named COPYING; if not, write to the
# Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor,
# Boston, MA 02110-1301 USA
#

# If we see an exception it is always fatal so the broad exception
# warning isn't helpful.
# pylint: disable=W0703
# We aren't using classes for anything other than with handling so
# a warning about too few methods being implemented isn't useful.
# pylint: disable=R0903

import argparse
import ctypes
import json
import os
import pwd
import subprocess
import sys
import tempfile
import time
import urllib.request as request


def run_command(cmd, raise_exception=True):
    """Execute given command in a subprocess

    This function will raise an Exception if the command fails unless
    raise_exception is False.
    """
    try:
        if subprocess.call(cmd.split(" ")) != 0 and raise_exception:
            raise Exception("{0} failed".format(cmd))
    except Exception as exep:
        if raise_exception:
            raise Exception("{0} failed: {1}".format(cmd, exep))


def create_virtual_disk(template):
    """Create virtual disk file for install target
    """
    image_size = 0
    match = {"M": 1, "G": 1024, "T": 1024 * 1024}
    for part in template["PartitionLayout"]:
        if part["size"] != "rest":
            image_size += int(part["size"][:-1]) * match[part["size"][-1]]

    image_size += 1
    command = "qemu-img create {0} {1}M".\
              format(template["PartitionLayout"][0]["disk"], image_size)
    run_command(command)


def create_partitions(template, sleep_time=1):
    """Create partitions according to template configuration
    """
    match = {"M": 1, "G": 1024, "T": 1024 * 1024}
    parted = "parted -sa"
    alignment = "optimal"
    units = "unit MiB"
    disks = set()
    cdisk = ""
    for disk in template["PartitionLayout"]:
        disks.add(disk["disk"])
    # Setup GPT tables on disks
    for disk in sorted(disks):
        if template.get("DestinationType") == "physical":
            command = "{0} {1} /dev/{2} {3} mklabel gpt".\
                      format(parted, alignment, disk, units)
        else:
            command = "{0} {1} {2} {3} mklabel gpt".\
                      format(parted, alignment, disk, units)
        run_command(command)
        time.sleep(sleep_time)
    # Create partitions
    for part in sorted(template["PartitionLayout"], key=lambda v: v["disk"] +
                       str(v["partition"])):
        if part["disk"] != cdisk:
            start = 0
        if part["size"] == "rest":
            end = "-1M"
        else:
            mult = match[part["size"][-1]]
            end = int(part["size"][:-1]) * mult + start
        if part["type"] == "EFI":
            ptype = "fat32"
        elif part["type"] == "swap":
            ptype = "linux-swap"
        else:
            ptype = "ext2"
        if start == 0:
            # Using 0% on the first partition to get the first 1MB
            # border that is correctly aligned
            start = "0%"
        if template.get("DestinationType") == "physical":
            command = "{0} {1} -- /dev/{2} {3} mkpart primary {4} {5} {6}"\
                .format(parted, alignment, part["disk"], units, ptype,
                        start, end)
        else:
            command = "{0} {1} -- {2} {3} mkpart primary {4} {5} {6}"\
                .format(parted, alignment, part["disk"], units, ptype,
                        start, end)
        run_command(command)
        time.sleep(sleep_time)
        if part["type"] == "EFI":
            if template.get("DestinationType") == "physical":
                command = "parted -s /dev/{0} set {1} boot on"\
                    .format(part["disk"], part["partition"])
            else:
                command = "parted -s {0} set {1} boot on"\
                    .format(part["disk"], part["partition"])
            run_command(command)
            time.sleep(sleep_time)
        start = end
        cdisk = part["disk"]


def map_loop_device(template, sleep_time=1):
    """Setup a loop device for the image file

    This function will raise an Exception if the command fails.
    """
    disk_image = template["PartitionLayout"][0]["disk"]
    command = "losetup --partscan --find --show {0}".format(disk_image)
    try:
        dev = subprocess.check_output(command.split(" ")).decode("utf-8")\
                                                         .splitlines()
    except:
        raise Exception("losetup command failed: {0}: {1}"
                        .format(command, sys.exc_info()))
    if len(dev) != 1:
        raise Exception("losetup failed to create loop device")
    time.sleep(sleep_time)
    run_command("partprobe {0}".format(dev[0]))
    time.sleep(sleep_time)

    template["dev"] = dev[0]


def get_device_name(template, disk):
    """Return /dev/{loopXp, sdX} type device name
    """
    if template.get("dev"):
        dev = template["dev"] + "p"
    else:
        dev = "/dev/{0}".format(disk)
    return dev


def create_filesystems(template):
    """Create filesystems according to template configuration
    """
    fs_util = {"ext2": "mkfs.ext2", "ext3": "mkfs.ext3", "ext4": "mkfs.ext4",
               "btrfs": "mkfs.btrfs", "vfat": "mkfs.vfat", "swap": "mkswap",
               "xfs": "mkfs.xfs"}
    for fst in template["FilesystemTypes"]:
        dev = get_device_name(template, fst["disk"])
        if fst.get("options"):
            command = "{0} {1} {2}{3}".format(fs_util[fst["type"]],
                                              fst["options"], dev,
                                              fst["partition"])
        else:
            command = "{0} {1}{2}".format(fs_util[fst["type"]], dev,
                                          fst["partition"])
        if fst["type"] == "swap":
            if template.get("dev"):
                base_dev = dev[:-1]
            else:
                base_dev = dev
            run_command("sgdisk {0} --typecode={1}:\
0657fd6d-a4ab-43c4-84e5-0933c84b4f4f"
                        .format(base_dev, fst["partition"]))
        run_command(command)


def setup_mounts(template):
    """Mount target folder

    Returns target folder name

    This function will raise an Exception on finding an error.
    """
    try:
        target_dir = tempfile.mkdtemp()
    except:
        raise Exception("Failed to setup mounts for install")

    for part in sorted(template["PartitionMountPoints"], key=lambda v:
                       v["mount"]):
        dev = get_device_name(template, part["disk"])
        if template.get("dev"):
            base_dev = dev[:-1]
        else:
            base_dev = dev
        if part["mount"] == "/":
            run_command("sgdisk {0} --typecode={1}:\
4f68bce3-e8cd-4db1-96e7-fbcaf984b709"
                        .format(base_dev, part["partition"]))
            if template.get("dev"):
                run_command("sgdisk {0} --partition-guid={1}:\
4f68bce3-e8cd-4db1-96e7-fbcaf984b709"
                            .format(base_dev, part["partition"]))
        if part["mount"] == "/boot":
            run_command("sgdisk {0} --typecode={1}:\
c12a7328-f81f-11d2-ba4b-00a0c93ec93b"
                        .format(base_dev, part["partition"]))
        if part["mount"] != "/":
            run_command("mkdir {0}{1}".format(target_dir, part["mount"]))
        run_command("mount {0}{1} {2}{3}".format(dev,
                                                 part["partition"],
                                                 target_dir,
                                                 part["mount"]))

    return target_dir


def add_bundles(template, target_dir):
    """Create bundle subscription file
    """
    bundles_dir = "/usr/share/clear/bundles/"
    os.makedirs(target_dir + bundles_dir)
    for bundle in template["Bundles"]:
        open(target_dir + bundles_dir + bundle, "w").close()


def copy_os(args, template, target_dir):
    """Wrapper for running install command
    """
    add_bundles(template, target_dir)
    swupd_command = "swupd_verify -V --fix --path={0} --manifest={1}"\
                    .format(target_dir, template["Version"])
    if args.url:
        swupd_command += " --url={0}".format(args.url)
    # FIXME: remove the format=staging once swupd_verify gets fixed
    if args.format:
        swupd_command += " --format={0}".format(args.format)
    if template["DestinationType"] == "physical":
        os.makedirs("/var/lib/swupd", exist_ok=True)
        os.makedirs("{0}/var/tmp".format(target_dir))
        run_command("mount --bind /var/lib/swupd {0}/var/tmp"
                    .format(target_dir))
    run_command(swupd_command)
    run_command("kernel_updater.sh -p {0}".format(target_dir))
    run_command("gummiboot_updaters.sh -p {0}".format(target_dir))


class ChrootOpen(object):
    """Class encapsulating chroot setup and teardown
    """
    def __init__(self, target_dir):
        """Stores the target directory for the chroot
        """
        self.target_dir = target_dir
        self.old_root = -1

    def __enter__(self):
        """Using the target directory, setup the chroot

        This function will raise an Exception on finding an error.
        """
        try:
            self.old_root = os.open("/", os.O_RDONLY)
            os.chroot(self.target_dir)
        except:
            raise Exception("Unable to setup chroot to create users")

        return self.target_dir

    def __exit__(self, *args):
        """Using the old root, teardown the chroot

        This function will raise an Exception on finding an error.
        """
        try:
            os.chdir(self.old_root)
            os.chroot(".")
            os.close(self.old_root)
        except:
            raise Exception("Unable to restore real root after chroot")


def create_account(user, target_dir):
    """Add user to the system

    Create a new account on the system with a home directory and one time
    passwordless login. Also add a new group with same name as the user
    """

    os.makedirs(target_dir + "/home", exist_ok=True)
    if user.get("uid"):
        command = "useradd -U -m -p '' -u {0} {1}"\
            .format(user["uid"], user["username"])
    else:
        command = "useradd -U -m -p '' {}".format(user["username"])

    with ChrootOpen(target_dir) as _:
        run_command(command)


def add_user_key(user, target_dir):
    """Append public key to user's ssh authorized_keys file

    This function will raise an Exception on finding an error.
    """
    # Must run pwd.getpwnam outside of chroot to load installer shared
    # lib instead of target which prevents umount on cleanup
    pwd.getpwnam("root")
    with ChrootOpen(target_dir) as _:
        try:
            os.makedirs("/home/{0}/.ssh".format(user["username"]), mode=0o0700)
            pwinfo = pwd.getpwnam(user["username"])
            uid = pwinfo[2]
            gid = pwinfo[3]
            os.chown("/home/{0}/.ssh".format(user["username"]), uid, gid)
            akey = open("/home/{0}/.ssh/authorized_keys"
                        .format(user["username"]), "a")
            akey.write(user["key"])
            akey.close()
            os.chown("/home/{0}/.ssh/authorized_keys"
                     .format(user["username"]), uid, gid)
        except Exception as exep:
            raise Exception("Unable to add {0}'s ssh key to authorized "
                            "keys: {1}".format(user["username"], exep))


def setup_sudo(user, target_dir):
    """Append user to sudoers file

    This function will raise an Exception on finding an error.
    """
    sudoer_template = "{} ALL=(ALL) NOPASSWD: ALL\n".format(user["username"])
    try:
        os.makedirs("{0}/etc/sudoers.d".format(target_dir))
        conf = open("{0}/etc/sudoers.d/{1}"
                    .format(target_dir, user["username"]), "w")
        conf.write(sudoer_template)
        conf.close()
    except:
        raise Exception("Unable to add sudoer conf file for {}"
                        .format(user["username"]))


def add_users(template, target_dir):
    """Create user accounts with no password one time logins

    Will setup sudo and ssh key access if specified in template.
    """
    users = template.get("Users")
    if not users:
        return

    for user in users:
        create_account(user, target_dir)
        if user.get("key"):
            add_user_key(user, target_dir)
        if user.get("sudo") and user["sudo"]:
            setup_sudo(user, target_dir)


def post_install_nonchroot(template, target_dir):
    """Run non chroot post install scripts

    All post scripts must be executable.

    The mount root for the install is passed as an argument to each script.
    """
    if not template.get("PostNonChroot"):
        return

    for script in template["PostNonChroot"]:
        run_command(script + " {}".format(target_dir))


def cleanup(template, target_dir, raise_exception=True):
    """Unmount and remove temporary files
    """
    if target_dir:
        if os.path.isdir("{0}/var/tmp".format(target_dir)):
            run_command("umount /var/lib/swupd",
                        raise_exception=raise_exception)
            run_command("rm -fr {0}/var/tmp".format(target_dir),
                        raise_exception=raise_exception)
        run_command("umount -R {}".format(target_dir),
                    raise_exception=raise_exception)
        run_command("rm -fr {}".format(target_dir))

    if template.get("dev"):
        run_command("losetup --detach {0}".format(template["dev"]),
                    raise_exception=raise_exception)


def get_template_location(path):
    """Read the installer configuration file for the template location

    This function will raise an Exception on finding an error.
    """
    conf_file = open(path, "r")
    contents = conf_file.readline().rstrip().split('=')
    conf_file.close()
    if contents[0] != "template" or len(contents) != 2:
        raise Exception("Invalid configuration file")
    return contents[1]


def get_template(template_location):
    """Fetch JSON template file for installer
    """
    json_file = request.urlopen(template_location)
    return json.loads(json_file.read().decode("utf-8"))


def validate_layout(template):
    """Validate partition layout is sane

    Returns mapping of layout to disk partitions.

    This function will raise an Exception on finding an error.
    """
    disk_to_parts = {}
    parts_to_size = {}
    has_efi = False
    accepted_ptypes = ["EFI", "linux", "swap"]
    accepted_sizes = ["M", "G", "T"]

    for layout in template["PartitionLayout"]:
        disk = layout.get("disk")
        part = layout.get("partition")
        size = layout.get("size")
        ptype = layout.get("type")

        if not disk or not part or not size or not ptype:
            raise Exception("Invalid PartitonLayout section: {}"
                            .format(layout))

        if size[-1] not in accepted_sizes and size != "rest":
            raise Exception("Invalid size specified in section {1}"
                            .format(layout))
        if size != "rest" and int(size[:-1]) <= 0:
            raise Exception("Invalid size specified in section {1}"
                            .format(layout))

        if ptype not in accepted_ptypes:
            raise Exception("Invalid partiton type {0}, supported types \
are: {1}".format(ptype, accepted_ptypes))

        if ptype == "EFI" and has_efi:
            raise Exception("Multiple EFI partitions defined")

        if ptype == "EFI":
            has_efi = True

        disk_part = disk + str(part)
        if disk_to_parts.get(disk):
            if part in disk_to_parts[disk]:
                raise Exception("Duplicate disk {0} and partition {1} entry \
in PartitionLayout".format(disk, part))
            disk_to_parts[disk].append(part)
        else:
            disk_to_parts[disk] = [part]
        parts_to_size[disk_part] = size

    for disk in disk_to_parts:
        if len(disk_to_parts[disk]) > 128:
            raise Exception("GPT disk with more than 128 partitions: {0}"
                            .format(disk))

    if template["DestinationType"] == "virtual" and len(disk_to_parts) != 1:
        raise Exception("Mulitple files for virtual disk \
destination is unsupported")
    if not has_efi:
        raise Exception("No EFI partition defined")

    for key in disk_to_parts:
        parts = sorted(disk_to_parts[key])
        for part in parts:
            if parts_to_size[key + str(part)] == "rest" and part != parts[-1]:
                raise Exception("Partition other than last uses rest of \
disk {0} partition {1}".format(key, part))

    return parts_to_size


def validate_fstypes(template, parts_to_size):
    """Validate filesystem types are sane

    Returns a set of disk partitions with filesystem type information.

    This function will raise an Exception on finding an error.
    """
    partition_fstypes = set()
    accepted_fstypes = ["ext2", "ext3", "ext4", "vfat", "btrfs", "xfs", "swap"]

    for fstype in template["FilesystemTypes"]:
        disk = fstype.get("disk")
        part = fstype.get("partition")
        fstype = fstype.get("type")
        if not disk or not part or not fstype:
            raise Exception("Invalid FilesystemTypes section: {}"
                            .format(fstype))

        if fstype not in accepted_fstypes:
            raise Exception("Invalid filesystem type {0}, supported types \
are: {1}".format(fstype, accepted_fstypes))

        disk_part = disk + str(part)
        if disk_part in partition_fstypes:
            raise Exception("Duplicate disk {0} and partition {1} entry in \
FilesystemTypes".format(disk, part))
        if disk_part not in parts_to_size:
            raise Exception("disk {0} partition {1} used in FilesystemTypes \
not found in PartitionLayout".format(disk, part))
        partition_fstypes.add(disk_part)

    return partition_fstypes


def validate_partition_mounts(template, partition_fstypes):
    """Validate partition mount points are sane

    This function will raise an Exception on finding an error.
    """
    has_rootfs = False
    has_boot = False
    disk_partitions = set()
    partition_mounts = set()
    for pmount in template["PartitionMountPoints"]:
        disk = pmount.get("disk")
        part = pmount.get("partition")
        mount = pmount.get("mount")
        if not disk or not part or not mount:
            raise Exception("Invalid PartitionMountPoints section: {}"
                            .format(pmount))

        if mount == "/":
            has_rootfs = True
        if mount == "/boot":
            has_boot = True
        disk_part = disk + str(part)
        if mount in partition_mounts:
            raise Exception("Duplicate mount points found")
        if disk_part in disk_partitions:
            raise Exception("Duplicate disk {0} and partition {1} entry in \
PartitionMountPoints".format(disk, part))
        if disk_part not in partition_fstypes:
            raise Exception("disk {0} partition {1} used in \
PartitionMountPoints not found in FilesystemTypes"
                            .format(disk, part))
        partition_mounts.add(mount)
        disk_partitions.add(disk_part)

    if not has_rootfs:
        raise Exception("Missing rootfs mount")
    if not has_boot:
        raise Exception("Missing boot mount")


def validate_type_template(template):
    """Attempt to verify the type of install target is sane

    This function will raise an Exception on finding an error.
    """
    dest_type = template["DestinationType"]
    if dest_type not in ("physical", "virtual"):
        raise Exception("Invalid destination type")


def validate_disk_template(template):
    """Attempt to verify all disk layout related information is sane
    """
    parts_to_size = validate_layout(template)
    partition_fstypes = validate_fstypes(template, parts_to_size)
    validate_partition_mounts(template, partition_fstypes)


def validate_user_template(users):
    """Attempt to verify all user related information is sane

    Also cache the users public keys, so we fail early if the key isn't
    found.

    This function will raise an Exception on finding an error.
    """
    max_uid = ctypes.c_uint32(-1).value
    uids = {}
    unames = {}
    for user in users:
        name = user.get("username")
        uid = user.get("uid")
        sudo = user.get("sudo")
        key = user.get("key")

        if not name:
            raise Exception("Missing username for user entry: {}".format(user))
        if unames.get(name):
            raise Exception("Duplicate username: {}".format(name))
        unames[name] = name

        if uid:
            iuid = int(uid)
        if uid and uids.get(uid):
            raise Exception("Duplicate UID: {}".format(uid))
        elif uid:
            if iuid < 1 or iuid > max_uid:
                raise Exception("Invalid UID: {}".format(uid))
            uids[uid] = uid

        if sudo is not None:
            if sudo is not True and sudo is not False:
                raise Exception("Invalid sudo option")

        if key:
            with open(user["key"], "r") as key_file:
                user["key"] = key_file.read()


def validate_postnonchroot_template(scripts):
    """Attempt to verify all post scripts exist

    This function will raise an Exception on finding an error.
    """
    for script in scripts:
        if not os.path.isfile(script):
            raise Exception("Missing post nonchroot script {}"
                            .format(script))


def validate_template(template):
    """Attempt to verify template is sane

    This function will raise an Exception on finding an error.
    """
    if not template.get("DestinationType"):
        raise Exception("Missing DestinationType field")
    if not template.get("PartitionLayout"):
        raise Exception("Missing PartitionLayout field")
    if not template.get("FilesystemTypes"):
        raise Exception("Missing FilesystemTypes field")
    if not template.get("PartitionMountPoints"):
        raise Exception("Missing PartitionMountPoints field")
    if not template.get("Version"):
        raise Exception("Missing Version field")
    if not template.get("Bundles"):
        raise Exception("Missing Bundles field")
    validate_type_template(template)
    validate_disk_template(template)
    if template["Version"] <= 0:
        raise Exception("Invalid version number")
    if template.get("Users"):
        validate_user_template(template["Users"])
    if template.get("PostNonChroot"):
        validate_postnonchroot_template(template["PostNonChroot"])


def parse_config(args):
    """Setup configuration dict holding ister settings

    This function will raise an Exception on finding an error.
    """
    config = {}
    if args.config_file:
        config["template"] = get_template_location(args.config_file)
    elif os.path.isfile("/etc/ister.conf"):
        config["template"] = get_template_location("/etc/ister.conf")
    elif os.path.isfile("/usr/share/defaults/ister/ister.conf"):
        config["template"] = get_template_location(
            "/usr/share/defaults/ister/ister.conf"
        )
    elif args.template_file:
        pass
    else:
        raise Exception("Couldn't find configuration file")

    if args.template_file:
        if args.template_file[0] == "/":
            config["template"] = "file://" + args.template_file
        else:
            config["template"] = "file://" + os.path.\
                                 abspath(args.template_file)

    return config


def set_motd_notification(target_dir):
    """Create a motd file for to display to users of installer images

    This function will raise an Exception on finding an error.
    """
    message = """Clear Linux for Intel Architecture installation in progress.

You can login to the installer image and check installation status with:

    systemctl status ister

Your computer will power off once installation completes successfully.
"""
    try:
        with open(target_dir + "/etc/issue", "w") as mfile:
            mfile.write(message)
    except:
        raise Exception("Unable to set installer image message")


def install_os(args):
    """Install the OS

    Start out parsing the configuration file for URI of the template.
    After the template file is located, download the template and validate it.
    If the template is valid, run the installation procedure.

    This function will raise an Exception on finding an error.
    """
    target_dir = None
    configuration = parse_config(args)
    template = get_template(configuration["template"])
    validate_template(template)
    try:
        if template["DestinationType"] == "virtual":
            create_virtual_disk(template)
        create_partitions(template)
        if template["DestinationType"] == "virtual":
            map_loop_device(template)
        create_filesystems(template)
        target_dir = setup_mounts(template)
        copy_os(args, template, target_dir)
        add_users(template, target_dir)
        post_install_nonchroot(template, target_dir)
        if args.installer:
            set_motd_notification(target_dir)
    except Exception as excep:
        raise excep
    finally:
        cleanup(template, target_dir, False)


def handle_options():
    """Setup option parsing
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config-file", action="store",
                        default=None,
                        help="Path to configuration file to use")
    parser.add_argument("-t", "--template-file", action="store",
                        default=None,
                        help="Path to template file to use")
    parser.add_argument("-i", "--installer", action="store_true",
                        default=False,
                        help="Setup image to be an installer")
    parser.add_argument("-u", "--url", action="store", default=None,
                        help="URL to use for looking for update content")
    parser.add_argument("-f", "--format", action="store", default=None,
                        help="format to use for looking for update content")
    args = parser.parse_args()
    return args


def main():
    """Start the installer
    """
    args = handle_options()
    try:
        install_os(args)
    except Exception as exep:
        print("Failed: {}".format(exep))
        sys.exit(-1)

    sys.exit(0)

if __name__ == '__main__':
    main()
