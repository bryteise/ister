#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# vim: ts=4 sw=4 tw=80 et ai si
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

# We aren't splitting ister up just yet so ignore too many lines error
# pylint: disable=too-many-lines
# As much as it pains us, global for the LOG handler is reasonable here
# pylint: disable=global-statement
# If we see an exception it is always fatal so the broad exception
# warning isn't helpful.
# pylint: disable=broad-except
# We aren't using classes for anything other than with handling so
# a warning about too few methods being implemented isn't useful.
# pylint: disable=too-few-public-methods
# Too many branches is probably something we'd have hoped to avoid but this
# logic for partition creation was born to be ugly, good spot for cleanup
# though for the adventurous sort
# pylint: disable=too-many-branches
# We aren't worried too much about performance of ister itself here, so using
# .format() for the logging functions (which always formats the string) is ok.
# pylint: disable=logging-format-interpolation


import argparse
import ctypes
import json
import logging
import os
import pwd
import re
import shlex
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
import base64
import binascii
import traceback
import urllib.request as request
from urllib.error import URLError, HTTPError
from urllib.parse import urlparse
from contextlib import closing
import netifaces
import pycryptsetup

LOG = None

def run_command(cmd, raise_exception=True, log_output=True, environ=None,
                show_output=False, shell=False):
    """
    Execute given command in a subprocess and return a (stdout, stderr,
    exitcode) tuple, where 'stdout' is the standard output of the command,
    'stderr' is the standard error, and 'exitcode' is the exit status.

    This function will raise an Exception if the command fails unless
    raise_exception is False.
    """
    try:
        LOG.debug("Running command {0}".format(cmd))
        sys.stdout.flush()
        if shell:
            full_cmd = cmd
        else:
            full_cmd = shlex.split(cmd)
        proc = subprocess.Popen(full_cmd,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                env=environ, shell=shell)

        # The following code makes an assumption that 'cmd' outputs to 'stdout',
        # but uses 'stderr' only in case of failure. Therefore we first exhaust
        # the 'stdout' pipe and then look to the 'stderr' pipe. If 'cmd' outputs
        # to 'stderr' as part of its normal operation, the below code may cause
        # a deadlock:
        # * 'cmd' prints to 'stderr'
        # * 'stderr' pipe is full and 'cmd' gets blocked
        # * we keep waiting on 'stdout'
        # * deadlock
        output = []
        for stream in (proc.stdout, proc.stderr):
            lines = []
            output.append(lines)
            for line in stream:
                decoded_line = line.decode('ascii', 'ignore').rstrip()
                lines.append(decoded_line)
                if show_output:
                    LOG.info(decoded_line)
                elif log_output:
                    LOG.debug(decoded_line)

        if proc.poll() and raise_exception:
            if output[1]:
                LOG.debug("Error {0}".format('\n'.join(output[1])))
            raise Exception("{0}".format(cmd))
        return output[0], output[1], proc.returncode
    except Exception as exep:
        if raise_exception:
            raise Exception("{0} failed: {1}".format(cmd, exep))


def validate_network(url):
    """Validate there is network connection to swupd
    """
    LOG.info("Verifying network connection")
    url = url if url else "https://update.clearlinux.org"
    try:
        _ = request.urlopen(url, timeout=3)
    except HTTPError as exep:
        if hasattr(exep, 'code'):
            LOG.info("SWUPD server error: {0}".format(exep.code))
            raise exep
    except URLError as exep:
        if hasattr(exep, 'reason'):
            LOG.info("Network error: Cannot reach swupd server: {0}"
                     .format(exep.reason))
            raise exep


def create_virtual_disk(template):
    """Create virtual disk file for install target
    """
    LOG.info("Creating virtual disk")
    image_size = 0
    # number of kilobytes in each of the following
    match = {"M": 1024, "G": 1024 ** 2, "T": 1024 ** 3}
    for part in template["PartitionLayout"]:
        if part["size"] != "rest":
            image_size += int(part["size"][:-1]) * match[part["size"][-1]]

    # Add extra buffer, note disk sizes should be multiples of 4kb.
    # Increase buffer by 1MB to give parted wiggle room due to dd using 1K
    # sector sizes and parted is getting partition sizes specified in MiB.
    image_size += 1024
    command = "dd if=/dev/zero of={0} bs=1024 count=0 seek={1}".\
              format(template["PartitionLayout"][0]["disk"], image_size)
    run_command(command)


def create_partitions(template, sleep_time=1):
    """Create partitions according to template configuration
    """
    LOG.info("Creating partitions")
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
        LOG.debug("Creating GPT label in {0}".format(disk))
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
        LOG.debug("Creating partition {0} in {1}".format(ptype, part["disk"]))
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
    LOG.info("Mapping loop device")
    disk_image = template["PartitionLayout"][0]["disk"]
    command = "losetup --partscan --find --show {0}".format(disk_image)
    try:
        dev = subprocess.check_output(command.split(" ")).decode("utf-8")\
                                                         .splitlines()
    except Exception:
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
    # handle loop devices, disk can be None
    if template.get("dev"):
        return ("{}p".format(template["dev"]), "p")

    # if not a loop device, search for partition format in /dev
    devices = os.listdir("/dev")
    devgen = (name for name in devices if disk in name)
    for name in devgen:
        part = name.replace(disk, "")
        if part:
            prefix = "p" if part.startswith("p") else ""
            return ("/dev/{}{}".format(disk, prefix), prefix)

    # if we got this far, no partitions were found and nothing would be
    # returned, resulting in a failed install.
    raise Exception("No partitions found on /dev/{}".format(disk))


def create_filesystems(template):
    """Create filesystems according to template configuration
    """

    # Filesystem-specific format tool options.
    fs_util = {"ext2": {"cmd" : "mkfs.ext2 -F", "label" : "-L"},
               "ext3": {"cmd" : "mkfs.ext3 -F", "label" : "-L"},
               "ext4": {"cmd" : "mkfs.ext4 -F", "label" : "-L"},
               "btrfs": {"cmd" : "mkfs.btrfs -f", "label" : "-L"},
               "vfat": {"cmd" : "mkfs.vfat", "label" : "-n"},
               "swap": {"cmd" : "mkswap", "label" : "-L"},
               "xfs": {"cmd" : "mkfs.xfs -f", "label" : "-L"}}

    LOG.info("Creating file systems")
    for fst in template["FilesystemTypes"]:
        (dev, prefix) = get_device_name(template, fst["disk"])
        fsu = fs_util[fst["type"]]
        LOG.debug("Creating file system {0} in {1}{2}"
                  .format(fst["type"], dev, fst["partition"]))

        opts = fst.get("options", "")
        if opts:
            opts = " " + opts
        if "label" in fst:
            opts += " {0} {1}".format(fsu["label"], fst["label"])
        command = "{0}{1} {2}{3}".format(fsu["cmd"], opts, dev,
                                         fst["partition"])
        if fst["type"] == "swap":
            if prefix:
                base_dev = dev[:-1]
            else:
                base_dev = dev
            run_command("sgdisk {0} --typecode={1}:\
0657fd6d-a4ab-43c4-84e5-0933c84b4f4f"
                        .format(base_dev, fst["partition"]))
        if "disable_format" not in fst:
            if "encryption" in fst:
                encr = fst["encryption"]
                c_dev="{0}{1}".format(dev, fst["partition"])
                c = pycryptsetup.CryptSetup(device=c_dev)
                c.luksFormat(cipher = "aes", cipherMode= "xts-plain64",
                             keysize = 512, hashMode = "sha256")
                c.addKeyByPassphrase(encr["passphrase"], encr["passphrase"])
                c.activate(name=encr["name"], passphrase=encr["passphrase"])
                command = "{0}{1} /dev/mapper/{2}".format(fsu["cmd"], opts,
                                                          encr["name"])
            run_command(command)
            if fst["type"] == "swap":
                run_command("swapon {0}{1}".format(dev, fst["partition"]),
                            raise_exception=False)


def create_target_dir(args, template):
    """Create the target root directory
    """

    if args.target_dir:
        target_dir = args.target_dir
        if not os.path.isdir(target_dir):
            raise Exception("Target directory {0} does not exist".format(target_dir))
    else:
        try:
            prefix = "ister-" + str(template["Version"]) + "-"
            target_dir = tempfile.mkdtemp(prefix=prefix)
        except Exception:
            raise Exception("Failed to setup mounts for install")

    LOG.debug("Installation target directory: {0}".format(target_dir))
    return target_dir

def setup_mounts(target_dir, template):
    """Mount target folder

    Returns target folder name

    This function will raise an Exception on finding an error.
    """
    LOG.info("Setting up mount points")

    has_boot = False

    units_dir = os.path.join(target_dir, "etc", "systemd", "system",
                             "local-fs.target.wants")

    def get_uuid(part_num, dev):
        """Get the uuid for a partition on a device"""
        result = run_command("sgdisk --info={0} {1}".format(part_num, dev))
        return result[0][1].split()[-1]

    def create_mount_unit(filename, uuid, mount, fs_type):
        """Create mount unit file for systemd
        """
        LOG.debug("Creating mount unit for UUID: {0}".format(uuid))
        unit = "[Unit]\nDescription = Mount for %s\n\n" % mount
        unit += "[Mount]\nWhat = PARTUUID={0}\n\
Where = {1}\nType = {2}\n\n".format(uuid, mount, fs_type)
        unit += "[Install]\nWantedBy = multi-user.target\n"
        unit_file = open(filename, 'w')
        unit_file.write(unit)
        unit_file.close()

    parts = sorted(template["PartitionMountPoints"], key=lambda v: v["mount"])
    for part in parts:
        if part["mount"] == "/boot":
            has_boot = True
    for part in parts:
        dev, prefix = get_device_name(template, part["disk"])
        if prefix:
            base_dev = dev[:-1]
        else:
            base_dev = dev
        LOG.debug("Mounting {0}{1} in {2}".format(dev,
                                                  part['partition'],
                                                  part["mount"]))
        fs_type = [x["type"] for x in template["FilesystemTypes"]
                   if x['disk'] == part['disk'] and
                   x['partition'] == part['partition']][-1]
        if part["mount"] == "/":
            run_command("sgdisk {0} --typecode={1}:\
4f68bce3-e8cd-4db1-96e7-fbcaf984b709"
                        .format(base_dev, part["partition"]))
            if not has_boot and template.get("LegacyBios"):
                run_command("sgdisk {0} --attributes={1}:set:2"
                            .format(base_dev, part["partition"]))
        if part["mount"] == "/boot" and not template.get("LegacyBios"):
            run_command("sgdisk {0} --typecode={1}:\
c12a7328-f81f-11d2-ba4b-00a0c93ec93b"
                        .format(base_dev, part["partition"]))
        if part["mount"] == "/boot" and template.get("LegacyBios"):
            run_command("sgdisk {0} --attributes={1}:set:2"
                        .format(base_dev, part["partition"]))
        if part["mount"] == "/srv":
            run_command("sgdisk {0} --typecode={1}:\
3B8F8425-20E0-4F3B-907F-1A25A76F98E8"
                        .format(base_dev, part["partition"]))
        if part["mount"] == "/home" or part["mount"].startswith('/home/'):
            run_command("sgdisk {0} --typecode={1}:\
933AC7E1-2EB4-4F13-B844-0E14E2AEF915"
                        .format(base_dev, part["partition"]))
        if part["mount"] != "/":
            run_command("mkdir -p {0}{1}".format(target_dir, part["mount"]))
        if "encryption" in part:
            run_command("mount /dev/mapper/{0} {1}{2}".format(
                                                 part["encryption"]["name"],
                                                 target_dir,
                                                 part["mount"]))
        else:
            command = "mount {0}{1} {2}{3}".format(dev, part["partition"],
                                                   target_dir, part["mount"])
            run_command(command)
        if part["mount"] not in ["/", "/boot", "/srv", "/home"]:
            if not part["mount"].startswith("/usr"):
                filename = part["mount"][1:].replace("/", "-") + ".mount"
                if not os.path.exists(units_dir):
                    os.makedirs(units_dir)
                create_mount_unit(os.path.join(units_dir, filename),
                                  get_uuid(part["partition"], base_dev),
                                  part["mount"], fs_type)


def add_bundles(template, target_dir):
    """Create bundle subscription file
    """
    bundles_dir = "/usr/share/clear/bundles/"
    os.makedirs(target_dir + bundles_dir)
    for index, bundle in enumerate(template["Bundles"]):
        open(target_dir + bundles_dir + bundle, "w").close()

    # pylint: disable=undefined-loop-variable
    # since we never reach this point with an empty Bundles list
    LOG.info("Installing {} bundles (and dependencies)...".format(index + 1))


def copy_os(args, template, target_dir):
    """Wrapper for running install command
    """
    package_manager = template["SoftwareManager"]
    LOG.info("Starting {0}. May take several minutes".format(package_manager))
    if package_manager == "swupd":
        copy_os_swupd(args, template, target_dir)
    elif package_manager == "dnf":
        copy_os_dnf(args, template, target_dir)


def copy_os_swupd(args, template, target_dir):
    """Wrapper for running install command with swupd
    """
    add_bundles(template, target_dir)

    if args.fast_install:
        args.statedir = "{0}/tmp/swupd".format(target_dir)

    if template["DestinationType"] == "physical":
        os.makedirs(args.statedir, exist_ok=True)
        os.chmod(args.statedir, stat.S_IRWXU)
        os.makedirs("{0}/var/tmp".format(target_dir))
        os.chmod("{0}/var/tmp".format(target_dir), stat.S_IRWXU)
        run_command("mount --bind {0}/var/tmp {1}"
                    .format(target_dir, args.statedir))

    cmd = "swupd verify --install"
    cmd += " --path={0}".format(target_dir)
    cmd += " --manifest={0}".format(template["Version"])
    if args.contenturl:
        cmd += " --contenturl={0}".format(args.contenturl)
    if args.versionurl:
        cmd += " --versionurl={0}".format(args.versionurl)
    if args.format:
        cmd += " --format={0}".format(args.format)
    cmd += " --statedir={0}".format(args.statedir)
    if args.cert_file:
        cmd += " --certpath={0}".format(args.cert_file)
    if shutil.which("stdbuf"):
        cmd = "stdbuf -o 0 {0}".format(cmd)
    cmd_env = get_cmd_env(template)
    run_command(cmd, environ=cmd_env, show_output=True)

    if args.fast_install:
        run_command("rm -rf {0}".format(args.statedir))


def copy_os_dnf(args, template, target_dir):
    """Wrapper for running install command with dnf
    """
    cmd = "dnf install --assumeyes"
    if args.dnf_config:
        cmd += " --config {0}".format(args.dnf_config)
    cmd += " --installroot {0}".format(target_dir)
    cmd += " {0}".format(" ".join(template["Bundles"]))
    if shutil.which("stdbuf"):
        cmd = "stdbuf -o 0 {0}".format(cmd)
    cmd_env = get_cmd_env(template)
    run_command(cmd, environ=cmd_env, show_output=True)


def get_cmd_env(template):
    """Get the environment variables with which commands will execute
    """
    cmd_env = os.environ
    if template.get("HTTPSProxy"):
        cmd_env["https_proxy"] = template["HTTPSProxy"]
        LOG.debug("https_proxy: {}".format(template["HTTPSProxy"]))
    return cmd_env


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
            os.chdir("/")
        except Exception:
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
        except Exception:
            raise Exception("Unable to restore real root after chroot")


def get_user_homedir(username):
    """Returns user's home directory path."""
    if username == "root":
        return os.path.join(os.sep, "root")
    return os.path.join(os.sep, "home", username)

def create_account(user, target_dir):
    """Add user to the system

    Create a new account on the system with a home directory and one time
    passwordless login. Also add a new group with same name as the user
    """

    os.makedirs(target_dir + get_user_homedir(user["username"]), exist_ok=True)
    if user.get("password"):
        opts = "-p '{0}'".format(user["password"])
    else:
        opts = "-p ''"
    if user.get("uid"):
        opts += " -u {0}".format(user["uid"])

    command = "useradd -U -m {0} {1}".format(opts, user["username"])

    with ChrootOpen(target_dir) as _:
        _, stderr, ret = run_command(command, raise_exception=False)
        if ret == 9:
            # '9' is a documented exit code for the "user already exists" case.
            # In this case just modify the existing user settings.
            command = "usermod {0} {1}".format(opts, user["username"])
            run_command(command)
        elif ret != 0 or stderr:
            if stderr:
                LOG.debug(stderr)
            raise Exception("failed to create user '{0}', 'useradd' returned "
                            "exit status '{1}'".format(user["username"], ret))

def add_user_fullname(user, target_dir):
    """Add user's full name to /etc/passwd

    If the user's full name is set in the template, use chfn to set their full
    name in the GECOS field of the /etc/passwd file
    """
    try:
        command = ["chfn", "-f", user["fullname"], user["username"]]

        with ChrootOpen(target_dir) as _:
            subprocess.call(command)
    except Exception as exep:
        print(exep)
        LOG.info("Unable to set user {} full name: {}".format(user["username"],
                                                              exep))


def add_user_key(user, target_dir):
    """Append public key to user's ssh authorized_keys file

    This function will raise an Exception on finding an error.
    """
    # Must run pwd.getpwnam outside of chroot to load installer shared
    # lib instead of target which prevents umount on cleanup
    pwd.getpwnam("root")

    sshdir = os.path.join(get_user_homedir(user["username"]), ".ssh")
    akey_path = os.path.join(sshdir, "authorized_keys")
    with ChrootOpen(target_dir) as _:
        try:
            os.makedirs(sshdir, mode=0o0700, exist_ok=True)
            pwinfo = pwd.getpwnam(user["username"])
            uid = pwinfo[2]
            gid = pwinfo[3]
            os.chown(sshdir, uid, gid)
            with open(akey_path, "a") as akey_fobj:
                akey_fobj.write(user["key"])
            os.chown(akey_path, uid, gid)
        except Exception as exep:
            raise Exception("Unable to add {0}'s ssh key to authorized "
                            "keys: {1}".format(user["username"], exep))


def disable_root_login(target_dir):
    """Disables the login for root if there is a user with sudo active

    It reads the line of /etc/shadow for the user previously created and
    then it changes the username to root and the password to !. Finally, it
    writes the result at the end.
    """
    line = ''
    with open("{0}/etc/shadow".format(target_dir)) as file:
        line = file.read().split('\n')[0]
    line = line.split(':')
    line[0] = 'root'
    line[1] = '!'
    line = ':'.join(line)
    with open("{0}/etc/shadow".format(target_dir), "a") as file:
        file.write(line)


def setup_sudo(user, target_dir):
    """Add user to sudo (wheel) group

    This function will raise an Exception on finding an error.
    """
    try:
        command = ["usermod", "-a", "-G", "wheel", user["username"]]

        with ChrootOpen(target_dir) as _:
            subprocess.call(command)
    except Exception:
        raise Exception("Unable to add sudo group for {}"
                        .format(user["username"]))


def add_users(template, target_dir):
    """Create user accounts with no password one time logins

    Will setup sudo and ssh key access if specified in template.
    """
    users = template.get("Users")
    if not users:
        return

    LOG.info("Adding new user")
    for user in users:
        create_account(user, target_dir)
        if user.get("key"):
            add_user_key(user, target_dir)
        if user.get("sudo") and user["sudo"]:
            setup_sudo(user, target_dir)
            disable_root_login(target_dir)
        if user.get("fullname"):
            add_user_fullname(user, target_dir)


def set_hostname(template, target_dir):
    """Writes the hostname to /etc/hostname
    """

    hostname = template.get("Hostname")
    if not hostname:
        return
    LOG.info("Setting up hostname")
    path = '{0}/etc/'.format(target_dir)
    if not os.path.exists(path):
        os.makedirs(path)

    with open(path + "hostname", "w") as file:
        file.write(hostname)


def set_mirror_url(template, target_dir):
    """Writes custom mirror url to <target disk>/etc/swupd/mirror_contenturl
    """
    target_mirror_url = template.get("MirrorURL")
    if not target_mirror_url:
        return

    LOG.info("Setting custom mirror url")
    path = '{0}/etc/swupd/'.format(target_dir)
    if not os.path.exists(path):
        os.makedirs(path)

    with open(path + "mirror_contenturl", "w") as file:
        file.write(target_mirror_url)


def set_mirror_version_url(template, target_dir):
    """Writes custom mirror version url to <target disk>/etc/swupd/mirror_versionurl
    """
    target_mirror_version_url = template.get("VersionURL")
    if not target_mirror_version_url:
        return

    LOG.info("Setting custom mirror version url")
    path = '{0}/etc/swupd/'.format(target_dir)
    if not os.path.exists(path):
        os.makedirs(path)

    with open(path + "mirror_versionurl", "w") as file:
        file.write(target_mirror_version_url)


def set_static_configuration(template, target_dir):
    """Writes the configuration on /etc/systemd/network/10-en-static.network
    """

    static_conf = template.get("Static_IP")
    if not static_conf:
        return

    path = '{0}/etc/systemd/network/'.format(target_dir)
    if not os.path.exists(path):
        os.makedirs(path)

    with open(path + "10-en-static.network", "w") as file:
        file.write("[Match]\n")
        file.write("Name={}\n\n".format(static_conf["iface"]))
        file.write("[Network]\n")
        file.write("Address={0}\n".format(static_conf["address"]))
        file.write("Gateway={0}\n".format(static_conf["gateway"]))
        if "dns" in static_conf:
            file.write("DNS={0}\n".format(static_conf["dns"]))


def set_kernel_cmdline_appends(template, target_dir):
    """Write template['cmdline'] to /etc/kernel/cmdline
    """
    if not template.get("cmdline"):
        return

    cmdline_path = os.path.join(target_dir, "etc/kernel/")
    if not os.path.exists(cmdline_path):
        os.makedirs(cmdline_path)

    with open(os.path.join(cmdline_path, "cmdline"), "w") as cmdline_f:
        cmdline_f.write(template["cmdline"])

    run_command("{0}/usr/bin/clr-boot-manager update --path {0}"
                .format(target_dir))


def pre_install_shell(template):
    """Run pre install commands
    """
    if not template.get("PreInstallShell"):
        return
    LOG.info("Running pre install commands")
    for cmdl in template["PreInstallShell"]:
        run_command(cmdl, shell=True)


def post_install_nonchroot(template, target_dir):
    """Run non chroot post install scripts

    All post scripts must be executable.

    The mount root for the install is passed as an argument to each script.
    """
    if not template.get("PostNonChroot"):
        return
    LOG.info("Running post non-chroot scripts")
    for script in template["PostNonChroot"]:
        run_command(script + " {}".format(target_dir))


def post_install_nonchroot_shell(template, target_dir):
    """Run non chroot post install commands

    The mount root for the install is passed as the ISTER_CHROOT environment
    variable.
    """
    if not template.get("PostNonChrootShell"):
        return
    LOG.info("Running post non-chroot commands")
    script_env = os.environ
    script_env["ISTER_CHROOT"] = target_dir
    for cmdl in template["PostNonChrootShell"]:
        run_command(cmdl, shell=True, environ=script_env)


def post_install_chroot(template, target_dir):
    """Run chroot post install scripts

    All post scripts must be executable.
    """
    if not template.get("PostChroot"):
        return
    LOG.info("Running post scripts")
    with ChrootOpen(target_dir) as _:
        for script in template["PostChroot"]:
            run_command(script)


def post_install_chroot_shell(template, target_dir):
    """Run chroot post install commands
    """
    if not template.get("PostChrootShell"):
        return
    LOG.info("Running post commands")
    with ChrootOpen(target_dir) as _:
        for cmdl in template["PostChrootShell"]:
            run_command(cmdl, shell=True)

def cleanup(args, template, target_dir, raise_exception=True):
    """Unmount and remove temporary files
    """
    if args.no_unmount:
        LOG.info("Skip unmounting target image at {0}".format(target_dir))
        return

    LOG.info("Cleaning up")
    if target_dir:
        if os.path.isdir("{0}/var/tmp".format(target_dir)):
            run_command("umount {0}".format(args.statedir),
                        raise_exception=raise_exception)
            run_command("rm -fr {0}/var/tmp".format(target_dir),
                        raise_exception=raise_exception)
        try:
            run_command("umount -R {}".format(target_dir))
        except Exception:
            run_command("lsof {}/boot".format(target_dir),
                        raise_exception=raise_exception)

        if not args.target_dir:
            # --target-dir was not used.
            run_command("rm -fr {}".format(target_dir),
                        raise_exception=raise_exception)

    # Turn off any swap devices we enabled
    for fst in template["FilesystemTypes"]:
        (dev, _) = get_device_name(template, fst["disk"])
        if fst["type"] == "swap":
            run_command("swapoff {0}{1}".format(dev, fst["partition"]),
                        raise_exception=raise_exception)

    if template.get("dev"):
        run_command("losetup --detach {0}".format(template["dev"]),
                    raise_exception=raise_exception)
    for dev_entry in template['PartitionMountPoints']:
        if 'encryption' in dev_entry:
            c = pycryptsetup.CryptSetup(name=dev_entry['encryption']['name'])
            c.deactivate()


def get_template_location(path):
    """Read the installer configuration file for the template location

    This function will raise an Exception on finding an error.
    """
    with open(path, "r") as conf_file:
        contents = conf_file.readline().rstrip().split('=')

    if contents[0] != "template" or len(contents) != 2:
        # This does not look like a valid configuration file. Let's assume this
        # is the template.
        return "file://" + path
    return contents[1]


def get_template(template_location):
    """Fetch JSON template file for installer
    """
    json_file = request.urlopen(template_location)
    parsed_json = json.loads(json_file.read().decode("utf-8"))
    # Supply default SoftwareManager value if not defined for backwards compatibility
    if not parsed_json.get("SoftwareManager"):
        parsed_json["SoftwareManager"] = "swupd"
    return parsed_json


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
            raise Exception("Invalid PartitionLayout section: {}"
                            .format(layout))

        if size[-1] not in accepted_sizes and size != "rest":
            raise Exception("Invalid size specified in section {0}"
                            .format(layout))
        if size != "rest" and int(size[:-1]) <= 0:
            raise Exception("Invalid size specified in section {0}"
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
    if not has_efi and template["DestinationType"] != "virtual" and \
       template.get("LegacyBios") is not True:
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
    force_fmt = [(item.get("disk"), item.get("partition"))
                 for item in template.get("PartitionMountPoints", list())
                 if item.get("mount", "") == "/"]
    for fstype in template["FilesystemTypes"]:
        disk = fstype.get("disk")
        part = fstype.get("partition")
        disable_fmt = fstype.get("disable_format")
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
        if force_fmt and force_fmt[0][0] == disk \
                and force_fmt[0][1] == part and disable_fmt is not None:
            raise Exception("/ does not apply to disable_format")
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
    if not has_boot and template["DestinationType"] != "virtual" and \
       template.get("LegacyBios") is not True:
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


def validate_version_template(template):
    """Attempt to verify the version is sane
    """
    version = template["Version"]
    if isinstance(version, int) and version <= 0:
        raise Exception("Invalid version number")
    if isinstance(version, str) and version != "latest":
        raise Exception("Invalid version string (must be 'latest')")


def validate_softmgr_template(template):
    """Attempt to verify the package manager is sane
    """
    package_manager = template["SoftwareManager"]
    if package_manager != "dnf" and package_manager != "swupd":
        raise Exception("Invalid package manager.  Use either swupd or dnf")


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
        password = user.get("password")

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
            if not isinstance(sudo, bool):
                raise Exception("Invalid sudo option")
            if sudo and not key and (password is None or password == ""):
                raise Exception("Missing password for user entry: {0}"
                                .format(user))

        if key:
            try:
                with open(user["key"], "r") as key_file:
                    user["key"] = key_file.read()
            except FileNotFoundError:
                # Let's assume this is the public key value, not the file name
                # containing the public key.
                pass
            except OSError as err:
                raise Exception("failed to read public SSH key file for user "
                                "'{0}': {1}".format(name, err))
            # Basic key validation: check that it consists of 3 components
            # (type, str, comment) and the str part is a base64-ecoded string.
            key = user["key"].split()
            if len(key) < 3:
                raise Exception("Invalid public SSH for user '{}'".format(name))
            try:
                # SSH keys are not necessarioly padded as base64 requires, so
                # pad the key before running the check.
               base64.b64decode(key[1], validate=True)
            except binascii.Error as err:
                raise Exception("Invalid public SSH for user '{0}', base64 "
                                "decoding failed: {1}".format(name, err))


def validate_hostname_template(hostname):
    """Attemp to verify if the hostname has an accepted value

    This function will raise an Exception on finding an error.
    """
    pattern = re.compile("^[a-zA-Z0-9][a-zA-Z0-9-]{0,63}$")
    if not pattern.match(hostname):
        raise Exception("Hostname can only contain letters, digits and dashes")


def validate_static_ip_template(static_conf):
    """Attemp to verify if the static ip configuration is good
    This function will raise an Exception on finding an error.
    """
    # pylint: disable=W1401
    # http://stackoverflow.com/questions/10006459/
    # regular-expression-for-ip-address-validation
    pattern = re.compile("^(?:(?:2[0-4]\d|25[0-5]|1\d{2}|[1-9]?\d)\.){3}"
                         "(?:2[0-4]\d|25[0-5]|1\d{2}|[1-9]?\d)"
                         "(?:\:(?:\d|[1-9]\d{1,3}|[1-5]\d{4}|6[0-4]\d{3}"
                         "|65[0-4]\d{2}|655[0-2]\d|6553[0-5]))?$")
    if "address" not in static_conf:
        raise Exception("Missing address in {0}".format(static_conf))
    if "gateway" not in static_conf:
        raise Exception("Missing gateway in {0}".format(static_conf))
    # tmp contains mask <address>/<mask>
    tmp = static_conf["address"].split('/')
    if len(tmp) <= 1:
        raise Exception("Missing mask prefix in {0}"
                        .format(static_conf["address"]))
    address = tmp[0]
    mask = tmp[1]
    if not mask.isdigit():
        raise Exception("The mask should be an integer, found '{0}'"
                        .format(mask))
    ips = [address, static_conf["gateway"]]
    if "dns" in static_conf:
        ips.append(static_conf['dns'])
    for item in ips:
        if not pattern.match(item):
            raise Exception("Invalid ip format for entry '{0}'".format(item))
    if ips[0] == ips[1]:
        raise Exception("Gateway has equal value to address '{0}'"
                        .format(static_conf))


def validate_postnonchroot_template(scripts):
    """Attempt to verify all post non-chroot scripts exist

    This function will raise an Exception on finding an error.
    """
    for script in scripts:
        if not os.path.isfile(script):
            raise Exception("Missing post nonchroot script {}"
                            .format(script))


def validate_legacybios_template(legacy):
    """Attempt to verify legacy bios setting is valid

    This function will raise an Exception on finding an error.
    """
    if not isinstance(legacy, bool):
        raise Exception("Invalid type for LegacyBios, must be True or False")


def validate_proxy_url_template(proxy):
    """Attempt to verify the proxy setting is valid

    This function will raise an Exception on finding an error.
    """
    url = urlparse(proxy)
    if not (url.scheme and url.netloc):
        raise Exception("Invalid proxy url: {}".format(proxy))


def validate_mirror_url_template(mirror):
    """Attempt to verify the mirror setting is valid

    This function will raise an Exception on finding an error.
    """
    url = urlparse(mirror)
    if not (url.scheme and url.netloc):
        raise Exception("Invalid mirror url: {}".format(mirror))


def validate_mirror_version_url_template(version):
    """Attempt to verify the version setting is valid

    This function will raise an Exception on finding an error.
    """
    url = urlparse(version)
    if not (url.scheme and url.netloc):
        raise Exception("Invalid version url: {}".format(version))


def validate_cmdline_template(cmdline):
    """Attempt to verify the cmdline configuration

    This function will raise an Exception on finding an error.
    """
    if not isinstance(cmdline, str):
        raise Exception("cmdline must be stored as a string")


def validate_template(template):
    """Attempt to verify template is sane

    This function will raise an Exception on finding an error.
    """
    LOG.info("Validating configuration")
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
    validate_version_template(template)
    validate_softmgr_template(template)
    if template.get("Users"):
        validate_user_template(template["Users"])
    if template.get("Hostname") is not None:
        validate_hostname_template(template["Hostname"])
    if template.get("Static_IP") is not None:
        validate_static_ip_template(template['Static_IP'])
    if template.get("PostNonChroot"):
        validate_postnonchroot_template(template["PostNonChroot"])
    if template.get("LegacyBios"):
        validate_legacybios_template(template["LegacyBios"])
    if template.get("HTTPSProxy"):
        validate_proxy_url_template(template["HTTPSProxy"])
    if template.get("HTTPProxy"):
        validate_proxy_url_template(template["HTTPProxy"])
    if template.get("MirrorURL"):
        validate_mirror_url_template(template["MirrorURL"])
    if template.get("VersionURL"):
        validate_mirror_version_url_template(template["VersionURL"])
    if template.get("cmdline"):
        validate_cmdline_template(template["cmdline"])
    LOG.debug("Configuration is valid:")
    LOG.debug(template)


def check_kernel_cmdline(f_kcmdline, sleep_time=15):
    """Check if ister.conf defined via kernel command line (pxe envs)

    Kernel command line trumps ister invocation args.
    Return a tuple (True/False, "path")
    """
    LOG.debug("Inspecting kernel command line for ister.conf location")
    LOG.debug("kernel command line file: {0}".format(f_kcmdline))
    kernel_args = list()
    ister_conf_uri = None
    with open(f_kcmdline, "r") as file:
        kernel_args = file.read().split(' ')
    for opt in kernel_args:
        if opt.startswith("isterconf="):
            ister_conf_uri = opt.split("=")[1]

    LOG.debug("ister_conf_uri = {0}".format(ister_conf_uri))

    # Fetch the file
    if ister_conf_uri:
        tmpfd, abs_path = tempfile.mkstemp()
        LOG.debug("ister_conf tmp file = {0}".format(abs_path))
        # in a PXE environment it's possible systemd launched us
        # before the network is up. This is primitive but effective.
        # And generally only pxe boots will trigger this.
        time.sleep(sleep_time)
        with request.urlopen(ister_conf_uri) as response:
            with closing(os.fdopen(tmpfd, "wb")) as out_file:
                shutil.copyfileobj(response, out_file)
                return True, abs_path
        os.unlink(abs_path)
    return False, ''


def get_host_from_url(url):
    """ Given url, return the host:port portion
        Try to be protocol agnostic
    """
    LOG.debug("Extracting host component of cloud-init-svc url")
    parsed = urlparse(url)
    LOG.debug("URL parsed")
    return parsed.hostname or None


def get_iface_for_host(host):
    """ Get interface being used to reach host
    """
    LOG.debug("Finding interface used to reach {0}".format(host))
    ip_addr = socket.gethostbyname(host)
    cmd = "ip route show to match {0}".format(ip_addr)
    iface = None

    output, _, ret = run_command(cmd)
    LOG.debug("Output from ip route show...")
    LOG.debug(output)
    if ret == 0:
        match = re.match(r'.*dev (\w+)', output[-1])
        iface = match.group(1)
        # Maybe make sure this really exists?

    return iface


def get_mac_for_iface(iface):
    """ Get the MAC address for iface
    """
    # pylint: disable=E1101
    LOG.debug("Determining MAC address for iface {0}".format(iface))
    try:
        addrs = netifaces.ifaddresses(iface)
    except Exception:
        return None
    macs = addrs[netifaces.AF_LINK]
    mac = macs[0].get('addr')
    LOG.debug("FOUND MAC address {0}".format(mac))
    return mac


def fetch_cloud_init_configs(src_url, mac):
    """ Fetch the json configs from ister-cloud-init-svc for mac
    """
    src_url += 'get_config/{0}'.format(mac)
    LOG.debug("Fetching cloud init configs from:\n"
              "\t{0}".format(src_url))
    try:
        json_file = request.urlopen(src_url)
    except Exception:
        json_file = None

    if json_file is not None:
        return json.loads(json_file.read().decode("utf-8"))

    return dict()


def get_cloud_init_configs(icis_source):
    """ Fetch configs from ister-cloud-init-svc
    """

    # TODO: Iterate over all interfaces in the future?

    # extract hostname/ip from url
    host = get_host_from_url(icis_source)
    if not host:
        LOG.debug("Could not extract hostname for ister cloud "
                  "init service from url: {0}".format(icis_source))
        return None

    # get interface being used to communicate
    iface = get_iface_for_host(host)
    if not iface:
        LOG.debug("No route to ister-cloud-init-svc host?"
                  "  Failed to find interface for route")
        return None

    mac = get_mac_for_iface(iface)
    if not mac:
        LOG.debug("Could not find MAC for iface: {0}".format(iface))
        return None

    # query icis service for confs
    icis_confs = fetch_cloud_init_configs(icis_source, mac)

    # return confs
    return icis_confs


def fetch_cloud_init_role(icis_source, role, target_dir):
    """ Get role from icis_source - install into target
    """
    icis_role_url = icis_source + "get_role/" + role
    out_file = target_dir + "/etc/cloud-init-user-data"
    LOG.debug("Fetching role file from {0}".format(icis_role_url))

    with request.urlopen(icis_role_url) as response:
        with closing(open(out_file, 'wb')) as out_file:
            shutil.copyfileobj(response, out_file)


def modify_cloud_init_service_file(target_dir):
    """ Modify cloud-init service file to use userdata file
        that was just installed.
    """
    LOG.debug("Updating cloud-init.service to user role file for user-data")
    cloud_init_file = target_dir + "/usr/lib/systemd/system/ucd.service"

    with open(cloud_init_file, "r") as service_file:
        lines = service_file.readlines()
    with open(cloud_init_file, "w") as service_file:
        for line in lines:
            service_file.write(re.sub("(ExecStart.*) --metadata "
                                      "--user-data-once",
                                      r"\1 --user-data-file "
                                      r"/etc/cloud-init-user-data", line))


def cloud_init_configs(template, target_dir):
    """ fetch configs from ister-cloud-init-svc and set appropriate
    template entries. Configs from ister-cloud-init-svc trump
    anything already in the template.
    """

    icis_source = template.get("IsterCloudInitSvc")

    if icis_source:
        icis_confs = get_cloud_init_configs(icis_source)

    icis_role = icis_confs.get('role')

    if icis_role:
        fetch_cloud_init_role(icis_source, icis_role, target_dir)
        modify_cloud_init_service_file(target_dir)


def parse_config(args):
    """Setup configuration dict holding ister settings

    This function will raise an Exception on finding an error.
    """
    LOG.info("Reading configuration")
    config = {}

    kcmdline, kconf_file = check_kernel_cmdline(args.kcmdline)

    if kcmdline:
        config["template"] = get_template_location(kconf_file)
    elif args.config_file:
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
    LOG.debug("File found: {0}".format(config["template"]))
    return config


def install_os(args, template):
    """Install the OS

    Start out parsing the configuration file for URI of the template.
    After the template file is located, download the template and validate it.
    If the template is valid, run the installation procedure.

    This function will raise an Exception on finding an error.
    """
    target_dir = None

    validate_template(template)
    try:
        # Disabling this until implementation replaced with pycurl
        # validate_network(args.url)
        pre_install_shell(template)
        if template["DestinationType"] == "virtual":
            create_virtual_disk(template)
        if not template.get("DisabledNewPartitions", False):
            create_partitions(template)
        if template["DestinationType"] == "virtual":
            map_loop_device(template)
        create_filesystems(template)
        target_dir = create_target_dir(args, template)
        setup_mounts(target_dir, template)
        copy_os(args, template, target_dir)
        add_users(template, target_dir)
        set_hostname(template, target_dir)
        set_mirror_url(template,target_dir)
        set_mirror_version_url(template,target_dir)
        set_static_configuration(template, target_dir)
        set_kernel_cmdline_appends(template, target_dir)
        if template.get("IsterCloudInitSvc"):
            LOG.debug("Detected IsterCloudInitSvc directive")
            cloud_init_configs(template, target_dir)
        post_install_nonchroot(template, target_dir)
        post_install_nonchroot_shell(template, target_dir)
        post_install_chroot(template, target_dir)
        post_install_chroot_shell(template, target_dir)
    except Exception as excep:
        LOG.error("Couldn't install ClearLinux")
        raise excep
    finally:
        cleanup(args, template, target_dir, False)


def handle_logging(level, logfile, shandler=logging.StreamHandler(sys.stdout)):
    """Setup log levels and direct logs to a file"""
    # Apparently the LOG object's level trumps level of handler?
    LOG.setLevel(logging.DEBUG)

    shandler.setLevel(logging.INFO)
    if level == 'debug':
        shandler.setLevel(logging.DEBUG)
    elif level == 'error':
        shandler.setLevel(logging.ERROR)
    LOG.addHandler(shandler)

    if logfile:
        open(logfile, 'w').close()
        fhandler = logging.FileHandler(logfile)
        fhandler.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            '%(asctime)s-%(levelname)s: %(message)s')
        fhandler.setFormatter(formatter)
        LOG.addHandler(fhandler)


def handle_options(sys_args):
    """Setup option parsing
    """
    parser = argparse.ArgumentParser(prog='ister')
    parser.add_argument("-c", "--config-file", action="store",
                        default=None,
                        help="Path to configuration file to use")
    parser.add_argument("-s", "--cert-file", action="store",
                        default=None,
                        help="Path to certificate file used by swupd")
    parser.add_argument("-t", "--template-file", action="store",
                        default=None,
                        help="Path to template file to use")
    parser.add_argument("-V", "--versionurl", action="store",
                        default=None,
                        help="URL to use for looking for update versions")
    parser.add_argument("-C", "--contenturl", action="store",
                        default=None,
                        help="URL to use for looking for update content")
    parser.add_argument("-f", "--format", action="store",
                        default=None,
                        help="format to use for looking for update content")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Output logging to console stream")
    parser.add_argument("-L", "--loglevel", action="store",
                        default="info",
                        help="loglevel: debug, info, error. default=info")
    parser.add_argument("-l", "--logfile", action="store",
                        default="/var/log/ister.log",
                        help="Output debug logging to a file")
    parser.add_argument("-k", "--kcmdline", action="store",
                        default="/proc/cmdline",
                        help="File to inspect for kernel cmdline opts")
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("-S", "--statedir", action="store",
                       default="/var/lib/swupd",
                       help="Path to swupd state dir")
    group.add_argument("-F", "--fast-install", action="store_true",
                       help="Move swupd state dir inside image for a faster install")
    parser.add_argument("-D", "--target-dir", action="store",
                        default=None,
                        help="Target root directory path, 'mktemp' by default")
    parser.add_argument("-m", "--no-unmount", action="store_true",
                        help="Do not unmount the target file-systems when done")
    parser.add_argument("-d", "--dnf-config", action="store",
                        default=None,
                        help="DNF configuration file for installing packages")
    args = parser.parse_args(sys_args)
    return args


def main():
    """Start the installer
    """
    global LOG
    args = handle_options(sys.argv[1:])

    LOG = logging.getLogger(__name__)
    handle_logging(args.loglevel, args.logfile)

    try:
        configuration = parse_config(args)
        template = get_template(configuration["template"])
        install_os(args, template)
    except Exception as exep:
        if args.loglevel == "debug":
            traceback.print_exc()
        LOG.error("Failed: {}".format(repr(exep)))
        sys.exit(-1)
    LOG.info("Successful installation")
    sys.exit(0)


if __name__ == '__main__':
    main()
