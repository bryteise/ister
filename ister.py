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

import ctypes
import json
import os
import pwd
import subprocess
import sys
import tempfile
import time
import urllib.request as request


def select_disk(install_disk):
    """Find the target disk given the install disk

    This function will raise an Exception on finding an error.
    """
    if install_disk.find("/dev/sda") == 0:
        return "sdb"
    else:
        return "sda"


def find_target_disk():
    """Search for the first disk that isn't the installer

    Disk detection is by process of elimination to find the installer,
    then the target disk will be the first disk not the installer.
    Ensure that we have at least two disks, then check if either of
    the first two disks doesn't have two partitions as the installer
    will contain two. Next check blkid for the UUID given to the
    installer image. And finally fallback to the output of mount to
    see if a '/dev/sdx' shows up with '/' as the mount point.

    This function will raise an Exception on finding an error.
    """
    install_uuid = 'UUID="53E0-A0AB"'

    try:
        blkid = subprocess.check_output("blkid").decode("utf-8").splitlines()
    except:
        raise Exception("Call to blkid failed")
    for line in blkid:
        if line.find(install_uuid) == 0:
            return select_disk(line)

    try:
        mount = subprocess.check_output("mount").decode("utf-8").splitlines()
    except:
        raise Exception("Call to mount failed")
    for line in mount:
        if line.find("/dev/sd") == 0:
            if line.find("on / ") != -1:
                return select_disk(line)

    # In the case of a PXE boot, there will be no installer UUID
    # found, only a target partition.
    sda = 0
    sdb = 0

    for line in blkid:
        if line.find("/dev/sda") == 0:
            sda = 1
        if line.find("/dev/sdb") == 0:
            sdb = 1

    if sda and not sdb:
        return "sda"

    raise Exception("Could not distinguish install disk")


def insert_fs_defaults(template):
    """Add default partition, filesystem and mounts to the template

    Used when the template doesn't specify partition and filesystem
    sections. The default inserted will be to use the first non install
    disk (sdx) and split it into two partitions. The first partition will
    be the EFI partition and will be 512M in size the second partition
    will be ext4 and take up the rest of the disk.
    """
    dev = find_target_disk()
    template["PartitionLayout"] = [{"disk": dev, "partition": 1, "size":
                                    "512M", "type": "EFI"},
                                   {"disk": dev, "partition": 2, "size":
                                    "rest", "type": "linux"}]
    template["FilesystemTypes"] = [{"disk": dev, "partition": 1, "type":
                                    "vfat"},
                                   {"disk": dev, "partition": 2, "type":
                                    "ext4"}]
    template["PartitionMountPoints"] = [{"disk": dev, "partition": 1, "mount":
                                         "/boot"},
                                        {"disk": dev, "partition": 2, "mount":
                                         "/"}]
    return


def run_command(cmd, raise_exception=True):
    """Execute given command in a subprocess

    This function will raise an Exception if the command fails.
    """
    if subprocess.call(cmd.split(" ")) != 0 and raise_exception:
        raise Exception("{0} failed".format(cmd))


def create_partitions(template):
    """Create partitions according to template configuration
    """
    match = {"M": 1, "G": 1024, "T": 1024 * 1024}
    parted = "parted -sa"
    alignment = "minimal"
    disks = set()
    cdisk = ""
    for disk in template["PartitionLayout"]:
        disks.add(disk["disk"])
    for disk in disks:
        command = "{0} {1} /dev/{2} mklabel gpt".\
                  format(parted, alignment, disk)
        run_command(command)
        command = "partprobe /dev/{0}".format(disk)
        run_command(command)
    for part in sorted(template["PartitionLayout"], key=lambda v: v["disk"]
                       + str(v["partition"])):
        if part["disk"] != cdisk:
            start = 0
        if part["size"] == "rest":
            end = -1
        else:
            mult = match[part["size"][-1]]
            end = int(part["size"][:-1]) * mult + start
        if part["type"] == "EFI":
            ptype = "fat32"
        elif part["type"] == "swap":
            ptype = "linux-swap"
        else:
            ptype = "ext2"
        command = "{0} {1} -- /dev/{2} mkpart primary {3} {4} {5}"\
            .format(parted, alignment, part["disk"], ptype, start, end)
        run_command(command)
        command = "partprobe /dev/{}".format(part["disk"])
        run_command(command)
        if part["type"] == "EFI":
            command = "parted -s /dev/{0} set {1} boot on"\
                .format(part["disk"], part["partition"])
            run_command(command)
        start = end
        cdisk = part["disk"]


def create_filesystems(template):
    """Create filesystems according to template configuration
    """
    fs_util = {"ext2": "mkfs.ext2", "ext3": "mkfs.ext3", "ext4": "mkfs.ext4",
               "btrfs": "mkfs.btrfs", "vfat": "mkfs.vfat", "swap": "mkswap"}
    for fst in template["FilesystemTypes"]:
        if fst.get("options"):
            command = "{0} {1} /dev/{2}{3}".format(fs_util[fst["type"]],
                                                   fst["options"], fst["disk"],
                                                   fst["partition"])
        else:
            command = "{0} /dev/{1}{2}".format(fs_util[fst["type"]],
                                               fst["disk"],
                                               fst["partition"])
        run_command(command)


def setup_mounts(template):
    """Mount source and target folders

    Returns a tuple containing source and target folders.

    This function will raise an Exception on finding an error.
    """
    try:
        source_dir = tempfile.mkdtemp()
        target_dir = tempfile.mkdtemp()
    except:
        raise Exception("Failed to setup mounts for install")

    prefix_len = len("file://")
    source_image_compressed = template["ImageSourceLocation"][prefix_len:]
    if not os.path.exists(source_image_compressed):
        raise Exception("Source image ({}) not found"
                        .format(source_image_compressed))

    try:
        with open("/tmp/source", "w") as ofile:
            if subprocess.call("xz -dc {0}"
                               .format(source_image_compressed)
                               .split(" "), stdout=ofile) != 0:
                raise Exception()
    except:
        raise Exception("Failed to extract source image")
    run_command("modprobe nbd max_part=2")
    run_command("qemu-nbd -c /dev/nbd0 /tmp/source")
    run_command("partprobe /dev/nbd0")
    run_command("mount -o ro /dev/nbd0p2 {}".format(source_dir))
    run_command("mount -o ro /dev/nbd0p1 {}/boot".format(source_dir))
    for part in sorted(template["PartitionMountPoints"], key=lambda v:
                       v["mount"]):
        if part["mount"] != "/":
            run_command("mkdir {0}{1}".format(target_dir, part["mount"]))
        run_command("mount /dev/{0}{1} {2}{3}".format(part["disk"],
                                                      part["partition"],
                                                      target_dir,
                                                      part["mount"]))

    return (source_dir, target_dir)


def copy_files(source_dir, target_dir, mini_rsync=False):
    """Sync files, from source to target folders

    Allow just syncing folders with mini_rsync
    """
    if mini_rsync:
        command = ['rsync', '-aAHX', '--exclude', 'lost+found',
                   '-f', "+ */", '-f', "- *", '{}/'.format(source_dir),
                   target_dir]
    else:
        command = ['rsync', '-aAHX', '--exclude', 'lost+found', '{}/'
                   .format(source_dir), target_dir]
    if subprocess.call(command) != 0:
        raise Exception("rsync failed with: {}".format(" ".join(command)))


def match_uuids(updated_layout, used_partitions):
    """Match uuids from blkid to devices in updated_layout

    This function will raise an exception on finding an error.
    """
    uuids = []

    try:
        blkids = subprocess.check_output("blkid").decode("utf-8").splitlines()
    except:
        raise Exception("Call to blkid failed")

    for line in blkids:
        uuid = ""
        # Example line:
        # /dev/sda1: SEC_TYPE="msdos" UUID="53E0-A0AB" TYPE="vfat" \
        #    PARTLABEL="EFI System"
        # PARTUUID="4921334c-d69f-43c0-a85d-cb4976817b93"
        pline = line.split(" ")
        dev = pline[0][:-1]
        if dev.find("/dev/nbd0") == 0:
            continue
        disk_part = os.path.basename(dev)
        if not updated_layout.get(disk_part):
            continue
        if disk_part not in used_partitions:
            continue
        for i in pline:
            if i.find('UUID="') == 0:
                uuid = i.split('"')[1]
        if uuid == "":
            raise Exception("Partition uuid not found in {}".format(line))
        updated_layout[disk_part]["uuid"] = uuid
        uuids.append(updated_layout[disk_part])

    return uuids


def get_uuids(template):
    """Relate partition uuids from blkid to partition layout

    In order to relate partition uuids from blkid, first update partition
    layout information to match what blkid returns.
    """
    used_disk_part = []
    updated_layout = {}

    for part in template["PartitionLayout"]:
        disk_part = part["disk"] + str(part["partition"])
        updated_layout[disk_part] = part.copy()
        if updated_layout[disk_part]["type"] == "swap":
            updated_layout[disk_part]["mount"] = "none"

    for part in template["FilesystemTypes"]:
        disk_part = part["disk"] + str(part["partition"])
        updated_layout[disk_part]["type"] = part["type"]

    for part in template["PartitionMountPoints"]:
        disk_part = part["disk"] + str(part["partition"])
        used_disk_part.append(disk_part)
        updated_layout[disk_part]["mount"] = part["mount"]
        if part.get("options"):
            updated_layout[disk_part]["options"] = part["options"]

    return match_uuids(updated_layout, used_disk_part)


def update_loader(uuids, target_dir):
    """Update root UUID in bootloader configuration

    This function will raise an Exception on finding an error.
    """
    for part in uuids:
        if part["mount"] == "/":
            uuid = part["uuid"]
            break
    try:
        with open("{}/boot/loader/entries/default.conf"
                  .format(target_dir), "r+") as loader:
            conf = loader.readlines()
            # 3rd line contains:
            # options root=UUID=0000-0000 kernel commandline options
            options = conf[3].split(' ')
            root_len = len("root=")
            for i in range(len(options)):
                if options[i][:root_len] == "root=":
                    options[i] = "root=UUID={}".format(uuid)
                    break
            conf[3] = ' '.join(options)
            loader.seek(0)
            loader.truncate()
            loader.writelines(conf)
    except Exception as exep:
        raise Exception("Unable to open or invalid bootloader configuration \
        file: {}".format(exep))


def update_fstab(uuids, target_dir):
    """Add PARTUUID entries to /etc/fstab

    This function will raise an Exception on finding an error.
    """
    default_options = "rw,relatime 0 0"
    try:
        fstab = open("{}/etc/fstab".format(target_dir), "w")
    except:
        raise Exception("Failed to open {}/etc/fstab".format(target_dir))

    try:
        for part in uuids:
            if part.get("options"):
                options = part["options"]
            else:
                options = default_options
            line = "UUID={0}	{1}	{2}	{3}\n".\
                   format(part["uuid"], part["mount"], part["type"], options)
            fstab.write(line)
    except:
        raise Exception("Failed to update {}/etc/fstab".format(target_dir))
    finally:
        fstab.close()

    return


def setup_machine_id(target_dir):
    """Create a machine-id for the target system
    """

    command = "systemd-machine-id-setup --root={}".format(target_dir)
    run_command(command)


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

        return True


def create_account(user, target_dir):
    """Add user to the system

    Create a new account on the system with a home directory and one time
    passwordless login. Also add a new group with same name as the user
    """

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
    key = request.urlopen(user["key"]).read().decode("utf-8")
    # Must run pwd.getpwnam outside of chroot to load installer shared
    # lib instead of target which prevents umount on cleanup
    pwd.getpwnam("root")
    with ChrootOpen(target_dir) as _:
        try:
            os.makedirs("/home/{0}/.ssh".format(user["username"]), mode=700)
            pwinfo = pwd.getpwnam(user["username"])
            uid = pwinfo[2]
            gid = pwinfo[3]
            os.chown("/home/{0}/.ssh".format(user["username"]), uid, gid)
            akey = open("/home/{0}/.ssh/authorized_keys"
                        .format(user["username"]), "a")
            akey.write(key)
            akey.close()
            os.chown("/home/{0}/.ssh/authorized_keys"
                     .format(user["username"]), uid, gid)
        except Exception as exep:
            raise Exception("Unable to add {0}'s ssh key to authorized \
            keys: {1}".format(user["username"], exep))


def setup_sudo(user, target_dir):
    """Append user to sudoers file

    This function will raise an Exception on finding an error.
    """
    sudoer_template = "{} ALL=(ALL) ALL".format(user["username"])
    try:
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
        if user.get("sudo"):
            setup_sudo(user, target_dir)


def install_packages(packages):
    """Install packages to the current rootfs
    """
    for package in packages:
        if package["packagemanager"] == "zypper":
            if package["type"] == "group":
                command = "zypper -n in -t pattern {}".format(package["name"])
            else:
                command = "zypper -n in {}".format(package["name"])
        run_command(command)


def post_install_packages(template, target_dir):
    """Install packages after system installation completed
    """
    packages = template.get("PostInstallPackages")
    if not packages:
        return

    with ChrootOpen(target_dir) as _:
        install_packages(packages)


def cleanup(source_dir, target_dir, raise_exception=True):
    """Unmount and remove temporary files

    This function may raise an Exception on finding an error.
    """
    run_command("umount -R {}".format(target_dir),
                raise_exception=raise_exception)
    run_command("umount -R {}".format(source_dir),
                raise_exception=raise_exception)
    run_command("rm -fr {}".format(target_dir))
    run_command("rm -fr {}".format(source_dir))
    run_command("qemu-nbd -d /dev/nbd0", raise_exception=raise_exception)


def do_install(template):
    """Create partitions, filesystems, and copy files for install
    """
    create_partitions(template)
    create_filesystems(template)
    (source_dir, target_dir) = setup_mounts(template)
    copy_files(source_dir, target_dir)
    uuids = get_uuids(template)
    update_loader(uuids, target_dir)
    update_fstab(uuids, target_dir)
    setup_machine_id(target_dir)
    add_users(template, target_dir)
    post_install_packages(template, target_dir)
    cleanup(source_dir, target_dir)


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
        parts_to_size[disk_part] = size

    if not has_efi:
        raise Exception("No EFI partition defined")

    for key in disk_to_parts:
        parts = sorted(disk_to_parts[key])
        for part in parts:
            if parts_to_size[key + part] == "rest" and part != parts[-1]:
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
        if not disk or not part or not type:
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
    partition_mounts = set()
    for pmount in template["PartitionMountPoints"]:
        disk = pmount.get("disk")
        part = pmount.get("partition")
        mount = pmount.get("mount")
        if not disk or not part or not mount:
            raise Exception("Invalid PartitionMountPoints section: {}"
                            .format(pmount))

        disk_part = disk + str(part)
        if disk_part in partition_mounts:
            raise Exception("Duplicate disk {0} and partition {1} entry in \
            PartitionMountPoints".format(disk, part))
        if disk_part not in partition_fstypes:
            raise Exception("disk {0} partition {1} used in \
            PartitionMountPoints not found in FilesystemTypes"
                            .format(disk, part))
        partition_mounts.add(disk_part)


def validate_disk_template(template):
    """Attempt to verify all disk layout related information is sane

    This function will raise an Exception on finding an error.
    """
    if not template.get("PartitionLayout"):
        raise Exception("Invalid template, missing PartitionLayout")
    elif not template.get("FilesystemTypes"):
        raise Exception("Invalid template, missing FilesystemTypes")
    elif not template.get("PartitionMountPoints"):
        raise Exception("Invalid template, missing PartitionMountPoints")

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

        if user.get("key"):
            request.urlopen(user["key"])

        if sudo:
            if sudo != "password":
                raise Exception("Invalid sudo option: {}".format(sudo))


def validate_post_install_packages(post_packages):
    """Attempt to verify all package related information is sane

    This function will raise an Exception on finding an error.
    """
    accepted_package_managers = ["zypper"]
    accepted_package_types = ["single", "group"]
    for package in post_packages:
        package_manager = package.get("packagemanager")
        package_type = package.get("type")
        package_name = package.get("name")

        if not package_manager:
            raise Exception("Missing package manager for post install \
            entry: {}".format(package))
        if not package_type:
            raise Exception("Missing package type for post install entry: {}"
                            .format(package))
        if not package_name:
            raise Exception("Missing package name for post install entry: {}"
                            .format(package))

        if package_manager not in accepted_package_managers:
            raise Exception("Invalid package manager {0}, accepted package \
            managers are: {1}".format(package_manager,
                                      accepted_package_managers))
        if package_type not in accepted_package_types:
            raise Exception("Invalid package type {0}, accepted package types \
            are: {1}".format(package_type, accepted_package_types))


def validate_template(template):
    """Attempt to verify template is sane

    This function will raise an Exception on finding an error.
    """
    disk_info = False
    if not template.get("ImageSourceType"):
        raise Exception("Missing ImageSourceType field")
    if not template.get("ImageSourceLocation"):
        raise Exception("Missing ImageSourceLocation field")
    if template.get("ParitionLayout"):
        disk_info = True
    if template.get("FilesystemTypes"):
        disk_info = True
    if template.get("PartitionMountPoints"):
        disk_info = True

    if disk_info:
        validate_disk_template(template)
    else:
        insert_fs_defaults(template)

    if template.get("Users"):
        validate_user_template(template["Users"])

    if template.get("PostInstallPackages"):
        validate_post_install_packages(template["PostInstallPackages"])
    return


def get_source_image(template):
    """Download install source image

    If download is successful, update ImageSourceLocation to be the local file.
    """
    request.urlretrieve(template["ImageSourceLocation"], "/tmp/image.xz")
    template["ImageSourceLocation"] = "file:///tmp/image.xz"


def install_os():
    """Install the OS

    Start out parsing the configuration file for URI of the template.
    After the template file is located, download the template and validate it.
    If the template is valid, run the installation procedure and reboot.

    This function will raise an Exception on finding an error.
    """
    template_location = get_template_location("/etc/ister.conf")
    template = get_template(template_location)
    validate_template(template)
    if template["ImageSourceType"] == "remote":
        get_source_image(template)

    do_install(template)


def main():
    """Start the installer
    """
    console = os.open("/dev/tty1", os.O_RDWR)
    os.write(console, b"\x1b[2J\x1b[H")
    os.write(console, b"Starting installation\n")
    try:
        install_os()
    except Exception as exep:
        os.write(console, "Installation failed: {}\n".format(exep)
                 .encode("ascii"))
        time.sleep(5)
        sys.exit(-1)

    os.write(console, b"Installation complete")
    time.sleep(5)
    sys.exit(0)

if __name__ == '__main__':
    main()
