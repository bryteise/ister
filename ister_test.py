#!/usr/bin/env python3
"""Linux installation template system test suite"""

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

import imp
import ister
import functools
import json
import time
import os
import sys

COMMAND_RESULTS = []


def good_virtual_disk_template():
    """Return string representation of good_virtual_disk_template"""
    return u'{"DestinationType" : "virtual", "PartitionLayout" : \
    [{"disk" : "gvdt", "partition" : 1, "size" : "512M", "type" : "EFI"}, \
    {"disk" : "gvdt", "partition" : 2, \
    "size" : "512M", "type" : "swap"}, {"disk" : "gvdt", "partition" : 3, \
    "size" : "rest", "type" : "linux"}], \
    "FilesystemTypes" : \
    [{"disk" : "gvdt", "partition" : 1, "type" : "vfat"}, {"disk" : "gvdt", \
    "partition" : 2, "type" : "swap"}, \
    {"disk" : "gvdt", "partition" : 3, "type" : "ext4"}], \
    "PartitionMountPoints" : \
    [{"disk" : "gvdt", "partition" : 1, "mount" : "/boot"}, {"disk" : "gvdt", \
    "partition" : 3, "mount" : "/"}], \
    "Version" : 800, "Bundles" : ["linux-kvm"]}'


def full_user_install_template():
    """Return string representation of full_user_install_template"""
    return u'{"DestinationType" : "virtual", "PartitionLayout": \
    [{"disk": "fuit", "partition": 1, "size": "512M", "type": "EFI"}, \
    {"disk": "fuit", "partition": 2, "size": "512M", "type": "swap"}, \
    {"disk": "fuit", "partition": 3, "size": "rest", "type": "linux"}], \
    "FilesystemTypes": \
    [{"disk": "fuit", "partition": 1, "type": "vfat"}, {"disk": "fuit", \
    "partition": 2, "type": "swap"}, \
    {"disk": "fuit", "partition": 3, "type": "ext4"}], \
    "PartitionMountPoints": \
    [{"disk": "fuit", "partition": 1, "mount": "/boot"}, {"disk": "fuit", \
    "partition": 3, "mount": "/"}], \
    "Users": [{"username": "user", "key": "key.pub", \
    "uid": 1001, "sudo": "password"}]}'


def run_command_wrapper(func):
    """Wrapper for tests whose functions use run_command"""
    @functools.wraps(func)
    def wrapper():
        def mock_run_command(cmd, _=None, raise_exception=True):
            global COMMAND_RESULTS
            COMMAND_RESULTS.append(cmd)
            if not raise_exception:
                COMMAND_RESULTS.append(False)
        global COMMAND_RESULTS
        COMMAND_RESULTS = []
        rc = ister.run_command
        ister.run_command = mock_run_command
        try:
            func()
        except Exception as exep:
            raise exep
        finally:
            ister.run_command = rc
    return wrapper


def makedirs_wrapper(test_type):
    """Wrapper for makedirs mocking"""
    def makedirs_type(func):
        @functools.wraps(func)
        def wrapper():
            backup_makedirs = os.makedirs
            def mock_makedirs_good(dname, mode=0, exist_ok=False):
                global COMMAND_RESULTS
                COMMAND_RESULTS.append(dname)
                COMMAND_RESULTS.append(mode)
                COMMAND_RESULTS.append(exist_ok)
                return
            def mock_makedirs_bad(dname, mode=0, exist_ok=False):
                global COMMAND_RESULTS
                COMMAND_RESULTS.append(dname)
                COMMAND_RESULTS.append(mode)
                COMMAND_RESULTS.append(exist_ok)
                raise Exception("mock makedirs bad")
            if test_type == "good":
                os.makedirs = mock_makedirs_good
            else:
                os.makedirs = mock_makedirs_bad
            try:
                func()
            except Exception as exep:
                raise exep
            finally:
                os.makedirs = backup_makedirs
        return wrapper
    return makedirs_type


def chroot_open_wrapper(test_type):
    """Wrapper for chroot mocking"""
    def chroot_type(func):
        @functools.wraps(func)
        def wrapper():
            backup_open = os.open
            backup_chroot = os.chroot
            backup_chdir = os.chdir
            backup_close = os.close
            def mock_open_good(dest, perm):
                global COMMAND_RESULTS
                COMMAND_RESULTS.append(dest)
                COMMAND_RESULTS.append(perm)
                return dest
            def mock_open_bad(dest, perm):
                raise Exception("open")
            def mock_open_silent(dest, perm):
                return dest
            def mock_chroot_chdir_close_good(dest):
                global COMMAND_RESULTS
                COMMAND_RESULTS.append(dest)
            def mock_chroot_bad(dest):
                raise Exception("chroot")
            def mock_chdir_bad(dest):
                raise Exception("chdir")
            def mock_close_bad(dest):
                raise Exception("close")
            def mock_chroot_chdir_close_silent(dest):
                return
            os.open = mock_open_silent
            os.chroot = mock_chroot_chdir_close_silent
            os.chdir = mock_chroot_chdir_close_silent
            os.close = mock_chroot_chdir_close_silent
            if test_type == "good":
                os.open = mock_open_good
                os.chroot = mock_chroot_chdir_close_good
                os.chdir = mock_chroot_chdir_close_good
                os.close = mock_chroot_chdir_close_good
            elif test_type == "bad open":
                os.open = mock_open_bad
            elif test_type == "bad chroot":
                os.chroot = mock_chroot_bad
            elif test_type == "bad chdir":
                os.chdir = mock_chdir_bad
            elif test_type == "bad close":
                os.close = mock_close_bad
            try:
                func()
            except Exception as exep:
                raise exep
            finally:
                os.open = backup_open
                os.chroot = backup_chroot
                os.chdir = backup_chdir
                os.close = backup_close
        return wrapper
    return chroot_type


def open_wrapper(test_type):
    """Wrapper for open"""
    def open_type(func):
        @functools.wraps(func)
        def wrapper():
            backup_open = __builtins__.open
            class MockOpen():
                def write(self, data):
                    global COMMAND_RESULTS
                    COMMAND_RESULTS.append(data)
                def close(self):
                    global COMMAND_RESULTS
                    COMMAND_RESULTS.append("close")
                    return
                def writelines(self, data):
                    global COMMAND_RESULTS
                    COMMAND_RESULTS += data
                    return
                def __exit__(self, *args):
                    return
                def __enter__(self, *args):
                    return self
            def mock_open_good(dest, perm):
                global COMMAND_RESULTS
                COMMAND_RESULTS.append(dest)
                COMMAND_RESULTS.append(perm)
                return MockOpen()
            def mock_open_bad(dest, perm):
                raise Exception("open")
            if test_type == "good":
                __builtins__.open = mock_open_good
            elif test_type == "bad":
                __builtins__.open = mock_open_bad
            try:
                func()
            except Exception as exep:
                raise exep
            finally:
                __builtins__.open = backup_open
        return wrapper
    return open_type

def add_user_key_wrapper(func):
    """Wrapper for functions in add_user_key"""
    @functools.wraps(func)
    @makedirs_wrapper("good")
    def wrapper():
        import pwd
        backup_chown = os.chown
        backup_getpwnam = pwd.getpwnam
        def mock_chown(dest, uid, gid):
            global COMMAND_RESULTS
            COMMAND_RESULTS.append(dest)
            COMMAND_RESULTS.append(uid)
            COMMAND_RESULTS.append(gid)
        def mock_getpwnam(dest):
            global COMMAND_RESULTS
            COMMAND_RESULTS.append(dest)
            return [0, 0, 1000, 1000]
        os.chown = mock_chown
        pwd.getpwnam = mock_getpwnam
        try:
            func()
        except Exception as exep:
            raise exep
        finally:
            os.chown = backup_chown
            pwd.getpwnam = backup_getpwnam
    return wrapper


def run_command_good():
    """Good run_command test"""
    ister.run_command("true")


def run_command_bad():
    """Bad run_command test"""
    exception_flag = False
    try:
        ister.run_command("not-a-binary", False)
    except:
        raise Exception("Command raised exception with surpression enabled")
    try:
        ister.run_command("not-a-binary")
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Bad command did not fail")


@run_command_wrapper
def create_virtual_disk_good_meg():
    """Create disk with size specified in megabytes"""
    template = {"PartitionLayout": [{"size": "20000M", "disk": "vdisk_tmp"},
                                    {"size": "50M"}]}
    command = "qemu-img create vdisk_tmp 20051M"
    ister.create_virtual_disk(template)
    if command != COMMAND_RESULTS[0] or len(COMMAND_RESULTS) != 1:
        raise Exception("command to create image doesn't match expected "
                        "result: {0}".format(COMMAND_RESULTS))


@run_command_wrapper
def create_virtual_disk_good_gig():
    """Create disk with size specified in gigabytes"""
    template = {"PartitionLayout": [{"size": "20G", "disk": "vdisk_tmp"},
                                    {"size": "1G"}]}
    command = "qemu-img create vdisk_tmp 21505M"
    ister.create_virtual_disk(template)
    if command != COMMAND_RESULTS[0] or len(COMMAND_RESULTS) != 1:
        raise Exception("command to create image doesn't match expected "
                        "result: {0}".format(COMMAND_RESULTS))


@run_command_wrapper
def create_virtual_disk_good_tera():
    """Create disk with size specified in terabytes"""
    template = {"PartitionLayout": [{"size": "1T", "disk": "vdisk_tmp"}]}
    command = "qemu-img create vdisk_tmp 1048577M"
    ister.create_virtual_disk(template)
    if command != COMMAND_RESULTS[0] or len(COMMAND_RESULTS) != 1:
        raise Exception("command to create image doesn't match expected "
                        "result: {0}".format(COMMAND_RESULTS))


def commands_compare_helper(commands):
    """Helper function to verify expected commands vs results"""
    if len(commands) != len(COMMAND_RESULTS):
        raise Exception("results {0} don't match expectations: {1}"
                        .format(COMMAND_RESULTS, commands))
    for idx in range(len(commands)):
        if commands[idx] != COMMAND_RESULTS[idx]:
            raise Exception("command at position {0} doesn't match expected "
                            "result: \n{1}\n{2}".format(idx, commands[idx],
                                                        COMMAND_RESULTS[idx]))


@run_command_wrapper
def create_partitions_good_physical_min():
    """Setup minimal partition table on disk"""
    commands = ["parted -sa optimal /dev/sda unit MiB mklabel gpt",
                "parted -sa optimal -- /dev/sda unit MiB mkpart primary fat32 "
                "0% 512",
                "parted -s /dev/sda set 1 boot on",
                "parted -sa optimal -- /dev/sda unit MiB mkpart primary ext2 "
                "512 -1M"]
    template = {"PartitionLayout": [{"partition": 1, "disk": "sda",
                                     "size": "512M", "type": "EFI"},
                                    {"partition": 2, "disk": "sda",
                                     "size": "rest", "type": "linux"}],
                "DestinationType": "physical"}
    ister.create_partitions(template, 0)
    commands_compare_helper(commands)


@run_command_wrapper
def create_partitions_good_physical_swap():
    """Setup with swap partition table on multidisk"""
    commands = ["parted -sa optimal /dev/sda unit MiB mklabel gpt",
                "parted -sa optimal /dev/sdb unit MiB mklabel gpt",
                "parted -sa optimal -- /dev/sda unit MiB mkpart primary fat32 "
                "0% 512",
                "parted -s /dev/sda set 1 boot on",
                "parted -sa optimal -- /dev/sda unit MiB mkpart primary "
                "linux-swap 512 4608",
                "parted -sa optimal -- /dev/sda unit MiB mkpart primary ext2 "
                "4608 -1M",
                "parted -sa optimal -- /dev/sdb unit MiB mkpart primary ext2 "
                "0% -1M"]
    template = {"PartitionLayout": [{"partition": 1, "disk": "sda",
                                     "size": "512M", "type": "EFI"},
                                    {"partition": 2, "disk": "sda",
                                     "size": "4096M", "type": "swap"},
                                    {"partition": 3, "disk": "sda",
                                     "size": "rest", "type": "linux"},
                                    {"partition": 1, "disk": "sdb",
                                     "size": "rest", "type": "linux"}],
                "DestinationType": "physical"}
    ister.create_partitions(template, 0)
    commands_compare_helper(commands)


@run_command_wrapper
def create_partitions_good_physical_specific():
    """Setup with partition table on multidisk"""
    commands = ["parted -sa optimal /dev/sda unit MiB mklabel gpt",
                "parted -sa optimal /dev/sdb unit MiB mklabel gpt",
                "parted -sa optimal -- /dev/sda unit MiB mkpart primary fat32 "
                "0% 512",
                "parted -s /dev/sda set 1 boot on",
                "parted -sa optimal -- /dev/sda unit MiB mkpart primary ext2 "
                "512 4608",
                "parted -sa optimal -- /dev/sdb unit MiB mkpart primary ext2 "
                "0% -1M"]
    template = {"PartitionLayout": [{"partition": 1, "disk": "sda",
                                     "size": "512M", "type": "EFI"},
                                    {"partition": 2, "disk": "sda",
                                     "size": "4096M", "type": "linux"},
                                    {"partition": 1, "disk": "sdb",
                                     "size": "rest", "type": "linux"}],
                "DestinationType": "physical"}
    ister.create_partitions(template, 0)
    commands_compare_helper(commands)


@run_command_wrapper
def create_partitions_good_virtual_swap():
    """Setup with swap partition table on virtual image"""
    commands = ["parted -sa optimal image unit MiB mklabel gpt",
                "parted -sa optimal -- image unit MiB mkpart primary fat32 "
                "0% 512",
                "parted -s image set 1 boot on",
                "parted -sa optimal -- image unit MiB mkpart primary "
                "linux-swap 512 4608",
                "parted -sa optimal -- image unit MiB mkpart primary ext2 "
                "4608 -1M"]
    template = {"PartitionLayout": [{"partition": 1, "disk": "image",
                                     "size": "512M", "type": "EFI"},
                                    {"partition": 2, "disk": "image",
                                     "size": "4096M", "type": "swap"},
                                    {"partition": 3, "disk": "image",
                                     "size": "rest", "type": "linux"}],
                "DestinationType": "virtual"}
    ister.create_partitions(template, 0)
    commands_compare_helper(commands)


@run_command_wrapper
def map_loop_device_good():
    """Create loop device for virtual image"""
    import subprocess
    check_output_backup = subprocess.check_output
    def mock_check_output(cmd):
        global COMMAND_RESULTS
        COMMAND_RESULTS = cmd
        return b"/dev/loop0"
    subprocess.check_output = mock_check_output
    template = {"PartitionLayout": [{"disk": "image"}]}
    commands = ["losetup", "--partscan", "--find", "--show", "image", "partprobe /dev/loop0"]
    try:
        ister.map_loop_device(template, 0)
    finally:
        subprocess.check_output = check_output_backup
    dev = template.get("dev")
    if not dev:
        raise Exception("Didn't set dev in template")
    if dev != "/dev/loop0":
        raise Exception("Incorrect dev set: {0}".format(dev))
    commands_compare_helper(commands)


def map_loop_device_bad_check_output():
    """Handle losetup check_output Exception"""
    import subprocess
    check_output_backup = subprocess.check_output
    def mock_check_output(cmd):
        raise Exception("bad")
    subprocess.check_output = mock_check_output
    exception_flag = False
    template = {"PartitionLayout": [{"disk": "image"}]}
    try:
        ister.map_loop_device(template, 0)
    except:
        exception_flag = True
    finally:
        subprocess.check_output = check_output_backup
    if not exception_flag:
        raise Exception("Failed to manage check_output Exception")


def map_loop_device_bad_losetup():
    """Handle losetup failure"""
    import subprocess
    check_output_backup = subprocess.check_output
    def mock_check_output(cmd):
        return b""
    subprocess.check_output = mock_check_output
    exception_flag = False
    template = {"PartitionLayout": [{"disk": "image"}]}
    try:
        ister.map_loop_device(template, 0)
    except:
        exception_flag = True
    finally:
        subprocess.check_output = check_output_backup
    if not exception_flag:
        raise Exception("Did not detect losetup failure")


def get_device_name_good_virtual():
    """Get virtual device name"""
    template = {"dev": "/dev/loop0"}
    dev = ister.get_device_name(template, None)
    if dev != "/dev/loop0p":
        raise Exception("Bad device name returned {0}".format(dev))


def get_device_name_good_physical():
    """Get physical device name"""
    dev = ister.get_device_name({}, "sda")
    if dev != "/dev/sda":
        raise Exception("Bad device name returned {0}".format(dev))


@run_command_wrapper
def create_filesystems_good():
    """Create filesystems without options"""
    template = {"FilesystemTypes": [{"disk": "sda", "type": "ext2",
                                     "partition": 1},
                                    {"disk": "sda", "type": "ext3",
                                     "partition": 2},
                                    {"disk": "sda", "type": "ext4",
                                     "partition": 3},
                                    {"disk": "sda", "type": "btrfs",
                                     "partition": 4},
                                    {"disk": "sdb", "type": "vfat",
                                     "partition": 1},
                                    {"disk": "sdb", "type": "swap",
                                     "partition": 2},
                                    {"disk": "sdb", "type": "xfs",
                                     "partition": 3}]}
    commands = ["mkfs.ext2 /dev/sda1",
                "mkfs.ext3 /dev/sda2",
                "mkfs.ext4 /dev/sda3",
                "mkfs.btrfs /dev/sda4",
                "mkfs.vfat /dev/sdb1",
                "sgdisk /dev/sdb --typecode=2:0657fd6d-a4ab-43c4-84e5-0933c84b4f4f",
                "mkswap /dev/sdb2",
                "mkfs.xfs /dev/sdb3"]
    ister.create_filesystems(template)
    commands_compare_helper(commands)


@run_command_wrapper
def create_filesystems_virtual_good():
    """Create virtual filesystems options"""
    template = {"FilesystemTypes": [{"disk": "test", "type": "vfat",
                                     "partition": 1},
                                    {"disk": "test", "type": "swap",
                                     "partition": 2},
                                    {"disk": "test", "type": "ext4",
                                     "partition": 3}],
                "dev": "/dev/loop0"}
    commands = ["mkfs.vfat /dev/loop0p1",
                "sgdisk /dev/loop0 --typecode=2:0657fd6d-a4ab-43c4-84e5-0933c84b4f4f",
                "mkswap /dev/loop0p2",
                "mkfs.ext4 /dev/loop0p3"]
    ister.create_filesystems(template)
    commands_compare_helper(commands)


@run_command_wrapper
def create_filesystems_good_options():
    """Create filesystems with options"""
    template = {"FilesystemTypes": [{"disk": "sda", "type": "ext2",
                                     "partition": 1, "options": "opt"},
                                    {"disk": "sda", "type": "ext3",
                                     "partition": 2, "options": "opt"},
                                    {"disk": "sda", "type": "ext4",
                                     "partition": 3, "options": "opt"},
                                    {"disk": "sda", "type": "btrfs",
                                     "partition": 4, "options": "opt"},
                                    {"disk": "sdb", "type": "vfat",
                                     "partition": 1, "options": "opt"},
                                    {"disk": "sdb", "type": "swap",
                                     "partition": 2, "options": "opt"},
                                    {"disk": "sdb", "type": "xfs",
                                     "partition": 3, "options": "opt"}]}
    commands = ["mkfs.ext2 opt /dev/sda1",
                "mkfs.ext3 opt /dev/sda2",
                "mkfs.ext4 opt /dev/sda3",
                "mkfs.btrfs opt /dev/sda4",
                "mkfs.vfat opt /dev/sdb1",
                "sgdisk /dev/sdb --typecode=2:0657fd6d-a4ab-43c4-84e5-0933c84b4f4f",
                "mkswap opt /dev/sdb2",
                "mkfs.xfs opt /dev/sdb3"]
    ister.create_filesystems(template)
    commands_compare_helper(commands)


@run_command_wrapper
def setup_mounts_good():
    """Setup mount points for install"""
    import tempfile
    backup_mkdtemp = tempfile.mkdtemp
    def mock_mkdtemp():
        return "/tmp"
    tempfile.mkdtemp = mock_mkdtemp
    template = {"PartitionMountPoints": [{"mount": "/", "disk": "sda",
                                          "partition": 1},
                                         {"mount": "/boot", "disk": "sda",
                                          "partition": 2}]}
    commands = ["sgdisk /dev/sda --typecode=1:4f68bce3-e8cd-4db1-96e7-fbcaf984b709",
                "mount /dev/sda1 /tmp/",
                "sgdisk /dev/sda --typecode=2:c12a7328-f81f-11d2-ba4b-00a0c93ec93b",
                "mkdir /tmp/boot",
                "mount /dev/sda2 /tmp/boot"]
    try:
        target_dir = ister.setup_mounts(template)
    finally:
        tempfile.mkdtemp = backup_mkdtemp
    if target_dir != "/tmp":
        raise Exception("Target dir doesn't match expected: {0}"
                        .format(target_dir))
    commands_compare_helper(commands)


@run_command_wrapper
def setup_mounts_virtual_good():
    """Setup virtual mount points for install"""
    import tempfile
    backup_mkdtemp = tempfile.mkdtemp
    def mock_mkdtemp():
        return "/tmp"
    tempfile.mkdtemp = mock_mkdtemp
    template = {"PartitionMountPoints": [{"mount": "/", "disk": "test",
                                          "partition": 1},
                                         {"mount": "/boot", "disk": "test",
                                          "partition": 2}],
                "dev": "/dev/loop0"}
    commands = ["sgdisk /dev/loop0 --typecode=1:4f68bce3-e8cd-4db1-96e7-fbcaf984b709",
                "sgdisk /dev/loop0 --partition-guid=1:4f68bce3-e8cd-4db1-96e7-fbcaf984b709",
                "mount /dev/loop0p1 /tmp/",
                "sgdisk /dev/loop0 --typecode=2:c12a7328-f81f-11d2-ba4b-00a0c93ec93b",
                "mkdir /tmp/boot",
                "mount /dev/loop0p2 /tmp/boot"]
    try:
        target_dir = ister.setup_mounts(template)
    finally:
        tempfile.mkdtemp = backup_mkdtemp
    if target_dir != "/tmp":
        raise Exception("Target dir doesn't match expected: {0}"
                        .format(target_dir))
    commands_compare_helper(commands)


def setup_mounts_bad():
    """Setup mount points mkdtemp failure"""
    import tempfile
    backup_mkdtemp = tempfile.mkdtemp
    def mock_mkdtemp():
        raise Exception("mkdtemp")
    tempfile.mkdtemp = mock_mkdtemp
    exception_flag = False
    try:
        target_dir = ister.setup_mounts(template)
    except:
        exception_flag = True
    finally:
        tempfile.mkdtemp = backup_mkdtemp
    if not exception_flag:
        raise Exception("Failed to handle mkdtemp failure")


@open_wrapper("good")
@makedirs_wrapper("good")
def add_bundles_good():
    """Ensure bundle outputs to correct file"""
    global COMMAND_RESULTS
    COMMAND_RESULTS = []
    commands = ["/dne/usr/share/clear/bundles/",
                0,
                False,
                "/dne/usr/share/clear/bundles/a",
                "w",
                "close",
                "/dne/usr/share/clear/bundles/b",
                "w",
                "close"]
    ister.add_bundles({"Bundles": ['a', 'b']}, "/dne")
    commands_compare_helper(commands)


@run_command_wrapper
def copy_os_good():
    """Check installer command"""
    backup_add_bundles = ister.add_bundles
    ister.add_bundles = lambda x,y: None
    args = lambda: None
    args.url = None
    args.format = None
    commands = ["swupd_verify -V --fix --path=/ --manifest=0",
                "kernel_updater.sh -p /",
                "gummiboot_updaters.sh -p /"]
    ister.copy_os(args, {"Version": 0, "DestinationType": ""}, "/")
    ister.add_bundles = backup_add_bundles
    commands_compare_helper(commands)


@run_command_wrapper
def copy_os_url_good():
    """Check installer command with url string"""
    backup_add_bundles = ister.add_bundles
    ister.add_bundles = lambda x,y: None
    args = lambda: None
    args.url = "/"
    args.format = None
    commands = ["swupd_verify -V --fix --path=/ --manifest=0 --url=/",
                "kernel_updater.sh -p /",
                "gummiboot_updaters.sh -p /"]
    ister.copy_os(args, {"Version": 0, "DestinationType": ""}, "/")
    ister.add_bundles = backup_add_bundles
    commands_compare_helper(commands)


@run_command_wrapper
@makedirs_wrapper("good")
def copy_os_physical_good():
    """Check installer command for physical install"""
    backup_add_bundles = ister.add_bundles
    ister.add_bundles = lambda x,y: None
    args = lambda: None
    args.url = "/"
    args.format = None
    commands = ["swupd_verify -V --fix --path=/ --manifest=0",
                "kernel_updater.sh -p /",
                "gummiboot_updaters.sh -p /",
                "/var/lib/swupd",
                0,
                True,
                "//var/tmp",
                0,
                False,
                "mount --bind /var/lib/swupd //var/tmp"]
    ister.copy_os(args, {"Version": 0, "DestinationType": "physical"}, "/")
    ister.add_bundles = backup_add_bundles
    commands_compare_helper(commands)


@chroot_open_wrapper("good")
def chroot_open_class_good():
    """Handle creation and teardown of chroots"""
    global COMMAND_RESULTS
    COMMAND_RESULTS = []
    commands = ["/",
                os.O_RDONLY,
                "/tmp",
                "/",
                ".",
                "/"]
    with ister.ChrootOpen("/tmp") as dest:
        if dest != "/tmp":
            raise Exception("target dir incorrect: {0}".format(dest))
    commands_compare_helper(commands)


@chroot_open_wrapper("bad open")
def chroot_open_class_bad_open():
    """Ensure open failures handled in ChrootOpen"""
    exception_flag = False
    try:
        with ister.ChrootOpen("/tmp") as dest:
            pass
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect open failure")


@chroot_open_wrapper("bad chroot")
def chroot_open_class_bad_chroot():
    """Ensure chroot failures handled in ChrootOpen"""
    exception_flag = False
    try:
        with ister.ChrootOpen("/tmp") as dest:
            pass
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect chroot failure")


@chroot_open_wrapper("bad chdir")
def chroot_open_class_bad_chdir():
    """Ensure chdir failures handled in ChrootOpen"""
    exception_flag = False
    try:
        with ister.ChrootOpen("/tmp") as dest:
            pass
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect chdir failure")


@chroot_open_wrapper("bad close")
def chroot_open_class_bad_close():
    """Ensure close failures handled in ChrootOpen"""
    exception_flag = False
    try:
        with ister.ChrootOpen("/tmp") as dest:
            pass
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect close failure")


@run_command_wrapper
@chroot_open_wrapper("silent")
def create_account_good():
    """Create account no uid"""
    template = {"username": "user"}
    commands = ["useradd -U -m -p '' user"]
    ister.create_account(template, "/tmp")
    commands_compare_helper(commands)


@run_command_wrapper
@chroot_open_wrapper("silent")
def create_account_good_uid():
    """Create account with uid"""
    template = {"username": "user", "uid": "1000"}
    commands = ["useradd -U -m -p '' -u 1000 user"]
    ister.create_account(template, "/tmp")
    commands_compare_helper(commands)


@chroot_open_wrapper("silent")
@open_wrapper("good")
@add_user_key_wrapper
def add_user_key_good():
    """Add user keyfile to user's authorized keys"""
    global COMMAND_RESULTS
    COMMAND_RESULTS = []
    template = {"username": "user", "key": "public"}
    commands = ["root",
                "/home/user/.ssh",
                448,
                False,
                "user",
                "/home/user/.ssh",
                1000,
                1000,
                "/home/user/.ssh/authorized_keys",
                "a",
                "public",
                "close",
                "/home/user/.ssh/authorized_keys",
                1000,
                1000]
    ister.add_user_key(template, "/tmp")
    commands_compare_helper(commands)


@chroot_open_wrapper("silent")
@open_wrapper("bad")
@add_user_key_wrapper
def add_user_key_bad():
    """Ensure failures during add_user_key are handled"""
    template = {"username": "user", "key": "public"}
    exception_flag = False
    try:
        ister.add_user_key(template, "/tmp")
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Didn't handle failure during key add")


@open_wrapper("good")
@add_user_key_wrapper
def setup_sudo_good():
    """Add user to sudoers file"""
    global COMMAND_RESULTS
    COMMAND_RESULTS = []
    template = {"username": "user"}
    commands = ["/tmp/etc/sudoers.d",
                0,
                False,
                "/tmp/etc/sudoers.d/user",
                "w",
                "user ALL=(ALL) NOPASSWD: ALL\n",
                "close"]
    ister.setup_sudo(template, "/tmp")
    commands_compare_helper(commands)


@open_wrapper("bad")
@add_user_key_wrapper
def setup_sudo_bad():
    """Ensure failures during setup_sudo are handled"""
    template = {"username": "user"}
    exception_flag = False
    try:
        ister.setup_sudo(template, "/tmp")
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Didn't handle failure during setup sudo")


def add_users_good():
    """Verify add users is successful with valid input"""
    backup_create_account = ister.create_account
    backup_add_user_key = ister.add_user_key
    backup_setup_sudo = ister.setup_sudo
    def mock_create_account(user, target_dir):
        global COMMAND_RESULTS
        COMMAND_RESULTS.append(user["n"])
        COMMAND_RESULTS.append(target_dir)
    def mock_add_user_key(_, __):
        global COMMAND_RESULTS
        COMMAND_RESULTS.append("key")
    def mock_setup_sudo(_, __):
        global COMMAND_RESULTS
        COMMAND_RESULTS.append("sudo")
    ister.create_account = mock_create_account
    ister.add_user_key = mock_add_user_key
    ister.setup_sudo = mock_setup_sudo
    global COMMAND_RESULTS
    COMMAND_RESULTS = []
    target_dir = "/tmp"
    commands = ["one",
                target_dir,
                "key",
                "sudo",
                "two",
                target_dir,
                "key",
                "three",
                target_dir,
                "sudo",
                "four",
                target_dir]
    template = {"Users": [{"n": "one", "key": "akey", "sudo": True},
                          {"n": "two", "key": "akey", "sudo": False},
                          {"n": "three", "sudo": True},
                          {"n": "four"}]}
    ister.add_users(template, target_dir)
    ister.create_account = backup_create_account
    ister.add_user_key = backup_add_user_key
    ister.setup_sudo = backup_setup_sudo
    commands_compare_helper(commands)


def add_users_none():
    """Verify that nothing happens without users to add"""
    backup_create_account = ister.create_account
    def mock_create_account(_, __):
        raise Exception("Account creation attempted with no users")
    ister.create_account = mock_create_account
    try:
        ister.add_users({}, "")
    except Exception as exep:
        raise exep
    finally:
        ister.create_account = backup_create_account


@run_command_wrapper
def post_install_nonchroot_good():
    """Test post install script execution"""
    commands = ["file1 /tmp"]
    ister.post_install_nonchroot({"PostNonChroot": ["file1"]}, "/tmp")
    commands_compare_helper(commands)


@run_command_wrapper
def cleanup_physical_good():
    """Test cleanup of virtual device"""
    backup_isdir = os.path.isdir
    def mock_isdir(path):
        global COMMAND_RESULTS
        COMMAND_RESULTS.append(path)
        return True
    os.path.isdir = mock_isdir
    commands = ["/tmp/var/tmp",
                "umount /var/lib/swupd",
                "rm -fr /tmp/var/tmp",
                "umount -R /tmp",
                "rm -fr /tmp"]
    ister.cleanup({}, "/tmp")
    os.path.isdir = backup_isdir
    commands_compare_helper(commands)


@run_command_wrapper
def cleanup_virtual_good():
    """Test cleanup of virtual device"""
    backup_isdir = os.path.isdir
    def mock_isdir(path):
        global COMMAND_RESULTS
        COMMAND_RESULTS.append(path)
        return False
    os.path.isdir = mock_isdir
    template = {"dev": "image"}
    commands = ["/tmp/var/tmp",
                "umount -R /tmp",
                "rm -fr /tmp",
                "losetup --detach image"]
    ister.cleanup(template, "/tmp")
    os.path.isdir = backup_isdir
    commands_compare_helper(commands)


def get_template_location_good():
    """Good get_template_location test"""
    template_file = ister.get_template_location("good-ister.conf")
    if template_file != u"file:///tmp/template.json":
        raise Exception("Incorrect template file path {}"
                        .format(template_file))


def get_template_location_bad_missing():
    """Bad get_template_location test (file not found)"""
    exception_flag = False
    try:
        template_file = ister.get_template_location("no-template.conf")
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("No error when reading from a nonexistant file")


def get_template_location_bad_no_equal():
    """Bad get_template_location test '=' content missing"""
    exception_flag = False
    try:
        template_file = ister.get_template_location("bad-ister1.conf")
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("No error from loading no '=' template file")


def get_template_location_bad_malformed():
    """Bad get_template_location test (template variable missing)"""
    exception_flag = False
    try:
        template_file = ister.get_template_location("bad-ister2.conf")
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("No error from loading malformed template file")


def get_template_good():
    """Test loading valid json file"""
    try:
        template = ister.get_template("file://{0}/test.json"
                                      .format(os.getcwd()))
        if template != {"test": 1}:
            raise Exception("json does not match expected value")
    except Exception as exep:
        raise exep


def validate_layout_good():
    """Good validate_layout full run"""
    template = {"PartitionLayout": [{"disk": "sda", "partition": 1,
                                     "size": "512M", "type": "EFI"},
                                    {"disk": "sda", "partition": 2, "size": "4G",
                                     "type": "swap"},
                                    {"disk": "sda", "partition": 3, "size": "rest",
                                     "type": "linux"}],
                "DestinationType": "disk"}
    try:
        parts_to_size = ister.validate_layout(template)
    except Exception as exep:
        raise Exception("Valid template failed to parse {}".format(exep))
    if len(parts_to_size) != 3:
        raise Exception("Incorrect partition count")
    if parts_to_size["sda1"] != "512M":
        raise Exception("Incorrect partition 1 size")
    if parts_to_size["sda2"] != "4G":
        raise Exception("Incorrect partition 2 size")
    if parts_to_size["sda3"] != "rest":
        raise Exception("Incorrect partition 3 size")


def validate_layout_bad_missing_disk():
    """Bad validate_layout no disk on partition"""
    exception_flag = False
    template = {"PartitionLayout": [{"partition": 1, "size": "512M",
                                     "type": "EFI"}]}
    try:
        ister.validate_layout(template)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect missing disk")

def validate_layout_bad_missing_part():
    """Bad validate_layout no part on partition"""
    exception_flag = False
    template = {"PartitionLayout": [{"disk": "sda", "size": "512M",
                                     "type": "EFI"}]}
    try:
        ister.validate_layout(template)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect missing part")


def validate_layout_bad_missing_size():
    """Bad validate_layout no size on partition"""
    exception_flag = False
    template = {"PartitionLayout": [{"disk": "sda", "partition": 1,
                                     "type": "EFI"}]}
    try:
        ister.validate_layout(template)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect missing size")


def validate_layout_bad_missing_ptype():
    """Bad validate_layout no ptype on partition"""
    exception_flag = False
    template = {"PartitionLayout": [{"disk": "sda", "partition": 1,
                                     "size": "512M"}]}
    try:
        ister.validate_layout(template)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect missing ptype")


def validate_layout_bad_size_type():
    """Bad validate_layout size type"""
    exception_flag = False
    template = {"PartitionLayout": [{"disk": "sda", "partition": 1,
                                     "size": "1Z", "ptype": "EFI"}]}
    try:
        ister.validate_layout(template)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect invalid size type")


def validate_layout_negative_size():
    """Bad validate_layout negative partition size"""
    exception_flag = False
    template = {"PartitionLayout": [{"disk": "sda", "partition": 1,
                                     "size": "-32M", "ptype": "EFI"}]}
    try:
        ister.validate_layout(template)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect negative partition size")


def validate_layout_bad_ptype():
    """Bad validate_layout ptype"""
    exception_flag = False
    template = {"PartitionLayout": [{"disk": "sda", "partition": 1,
                                     "size": "1G", "ptype": "notaptype"}]}
    try:
        ister.validate_layout(template)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect invalid ptype")


def validate_layout_bad_multiple_efis():
    """Bad validate_layout multiple efi partitions"""
    exception_flag = False
    template = {"PartitionLayout": [{"disk": "sda", "partition": 1,
                                     "size": "1G", "ptype": "EFI"},
                                    {"disk": "sda", "partition": 2,
                                     "size": "1G", "ptype": "EFI"}]}
    try:
        ister.validate_layout(template)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect two EFI partitions")


def validate_layout_bad_duplicate_parts():
    """Bad validate_layout disk has duplicate partitions"""
    exception_flag = False
    template = {"PartitionLayout": [{"disk": "sda", "partition": 1,
                                     "size": "1G", "ptype": "EFI"},
                                    {"disk": "sda", "partition": 1,
                                     "size": "1G", "ptype": "swap"}]}
    try:
        ister.validate_layout(template)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect duplicate partitions")


def validate_layout_bad_too_many_parts():
    """Bad validate_layout over 128 partitions"""
    exception_flag = False
    template = {"PartitionLayout": [{"disk": "sda", "partition": 1,
                                     "size": "1G", "ptype": "EFI"}]}
    for i in range(1,129):
        template["PartitionLayout"].append({"disk": "sda", "partition": i,
                                            "size": "1G", "ptype": "linux"})
    try:
        ister.validate_layout(template)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect over 128 partitions")


def validate_layout_bad_virtual_multi_disk():
    """Bad validate_layout with multiple disks with virtual destination"""
    exception_flag = False
    template = {"PartitionLayout": [{"disk": "sda", "partition": 1,
                                     "size": "512M", "type": "EFI"},
                                    {"disk": "sda", "partition": 2,
                                     "size": "4G", "type": "swap"},
                                    {"disk": "sdb", "partition": 3,
                                     "size": "rest", "type": "linux"}],
                "DestinationType": "virtual"}
    try:
        ister.validate_layout(template)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect multiple disks when using virtual \
as destination")


def validate_layout_bad_missing_efi():
    """Bad validate_layout without EFI partition type"""
    exception_flag = False
    template = {"PartitionLayout": [{"disk": "sda", "partition": 1,
                                     "size": "4G", "type": "linux"}],
                "DestinationType": "virtual"}
    try:
        ister.validate_layout(template)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect missing EFI partition")


def validate_layout_bad_too_greedy():
    """Bad validate_layout with non last partition using rest of disk"""
    exception_flag = False
    template = {"PartitionLayout": [{"disk": "sda", "partition": 1,
                                     "size": "512M", "type": "EFI"},
                                    {"disk": "sda", "partition": 2,
                                     "size": "rest", "type": "linux"},
                                    {"disk": "sda", "partition": 3,
                                     "size": "rest", "type": "linux"}],
                "DestinationType": "virtual"}
    try:
        ister.validate_layout(template)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect same disk rest partitions")


def validate_fstypes_good():
    """Good validate_fstypes"""
    template = {"FilesystemTypes": [{"disk": "sda", "partition": 1,
                                     "type": "ext2"},
                                    {"disk": "sda", "partition": 2,
                                     "type": "ext3"},
                                    {"disk": "sda", "partition": 3,
                                     "type": "ext4"},
                                    {"disk": "sda", "partition": 4,
                                     "type": "vfat"},
                                    {"disk": "sda", "partition": 5,
                                     "type": "btrfs"},
                                    {"disk": "sda", "partition": 6,
                                     "type": "xfs"},
                                    {"disk": "sda", "partition": 7,
                                     "type": "swap"}]}
    parts_to_size = {"sda1": "10G", "sda2": "10G", "sda3": "10G",
                     "sda4": "10G", "sda5": "10G", "sda6": "10G",
                     "sda7": "10G"}
    try:
        partition_fstypes = ister.validate_fstypes(template, parts_to_size)
    except:
        raise Exception("Valid template failed to parse")
    if len(partition_fstypes) != 7:
        raise Exception("Returned incorrect number of partition fstypes")
    for part in ["sda1", "sda2", "sda3", "sda4", "sda5", "sda6", "sda7"]:
        if not part in partition_fstypes:
            raise Exception("Missing {} from partition_fstypes".format(part))


def validate_fstypes_bad_missing_disk():
    """Bad validate_fstypes missing disk"""
    exception_flag = False
    template = {"FilesystemTypes": [{"partition": 1, "type": "ext2"}]}
    try:
        ister.validate_fstypes(template, None)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Missing disk not detected")


def validate_fstypes_bad_missing_partition():
    """Bad validate_fstypes missing partition"""
    exception_flag = False
    template = {"FilesystemTypes": [{"disk": "sda", "type": "ext2"}]}
    try:
        ister.validate_fstypes(template, None)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Missing partition not detected")


def validate_fstypes_bad_missing_type():
    """Bad validate_fstypes missing type"""
    exception_flag = False
    template = {"FilesystemTypes": [{"partition": 1, "disk": "sda"}]}
    try:
        ister.validate_fstypes(template, None)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Missing type not detected")


def validate_fstypes_bad_type():
    """Bad validate_fstypes bad type"""
    exception_flag = False
    template = {"FilesystemTypes": [{"type": "bad", "partition": 1,
                                     "disk": "sda"}]}
    try:
        ister.validate_fstypes(template, None)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Bad fs type not detected")


def validate_fstypes_bad_duplicate():
    """Bad validate_fstypes duplicate entries"""
    exception_flag = False
    template = {"FilesystemTypes": [{"type": "ext4", "partition": 1,
                                     "disk": "sda"},
                                    {"type": "ext3", "partition": 1,
                                     "disk": "sda"}]}
    parts_to_size = {"sda1": "10G"}
    try:
        ister.validate_fstypes(template, parts_to_size)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("duplicate fs not detected")


def validate_fstypes_bad_not_partition():
    """Bad validate_fstypes fs not in partiton map"""
    exception_flag = False
    template = {"FilesystemTypes": [{"type": "ext4", "partition": 1,
                                     "disk": "sda"}]}
    parts_to_size = {}
    try:
        ister.validate_fstypes(template, parts_to_size)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("fs not in partition map not detected")


def validate_partition_mounts_good():
    """Good validate_partition_mounts"""
    template = {"PartitionMountPoints": [{"disk": "sda", "partition": 1,
                                          "mount": "/boot"},
                                         {"disk": "sda", "partition": 2,
                                          "mount": "/"}]}
    partition_fstypes = set(["sda1", "sda2"])
    try:
        ister.validate_partition_mounts(template, partition_fstypes)
    except:
        raise Exception("Valid template failed to parse")


def validate_partition_mounts_bad_missing_disk():
    """Bad validate_partition_mounts missing disk"""
    exception_flag = False
    template = {"PartitionMountPoints": [{"partition": 1, "mount": "/boot"}]}
    try:
        ister.validate_partition_mounts(template, None)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("missing disk not detected")


def validate_partition_mounts_bad_missing_partition():
    """Bad validate_partition_mounts missing partition"""
    exception_flag = False
    template = {"PartitionMountPoints": [{"disk": "sda", "mount": "/boot"}]}
    try:
        ister.validate_partition_mounts(template, None)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("missing partition not detected")


def validate_partition_mounts_bad_missing_mount():
    """Bad validate_partition_mounts missing mount"""
    exception_flag = False
    template = {"PartitionMountPoints": [{"partition": 1, "disk": "sda"}]}
    try:
        ister.validate_partition_mounts(template, None)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("missing mount not detected")


def validate_partition_mounts_bad_duplicate_mount():
    """Bad validate_partition_mounts duplicate mount points"""
    exception_flag = False
    template = {"PartitionMountPoints": [{"disk": "sda", "partition": 1,
                                          "mount": "/boot"},
                                         {"disk": "sda", "partition": 2,
                                          "mount": "/boot"}]}
    partition_fstypes = set(["sda1", "sda2"])
    try:
        ister.validate_partition_mounts(template, partition_fstypes)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect duplicate mount points")


def validate_partition_mounts_bad_duplicate_disk_partitions():
    """Bad validate_partition_mounts duplicate disk partitions"""
    exception_flag = False
    template = {"PartitionMountPoints": [{"disk": "sda", "partition": 1,
                                          "mount": "/boot"},
                                         {"disk": "sda", "partition": 1,
                                          "mount": "/"}]}
    partition_fstypes = set("sda1")
    try:
        ister.validate_partition_mounts(template, partition_fstypes)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect duplicate disk partitions")


def validate_partition_mounts_bad_not_partition():
    """Bad validate_partition_mounts used invalid partition"""
    exception_flag = False
    template = {"PartitionMountPoints": [{"disk": "sda", "partition": 1,
                                          "mount": "/boot"}]}

    partition_fstypes = set()
    try:
        ister.validate_partition_mounts(template, partition_fstypes)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect invalid partition usage")


def validate_partition_mounts_bad_missing_boot():
    """Bad validate_partition_mounts missing boot partition"""
    exception_flag = False
    template = {"PartitionMountPoints": [{"disk": "sda", "partition": 1,
                                          "mount": "/"}]}
    partition_fstypes = set("sda1")
    try:
        ister.validate_partition_mounts(template, partition_fstypes)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect missing boot partition")


def validate_partition_mounts_bad_missing_root():
    """Bad validate_partition_mounts missing '/' partition"""
    exception_flag = False
    template = {"PartitionMountPoints": [{"disk": "sda", "partition": 1,
                                          "mount": "/boot"}]}
    partition_fstypes = set("sda1")
    try:
        ister.validate_partition_mounts(template, partition_fstypes)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect missing '/' partition")


def validate_type_template_good_physical():
    """Good validate_type_template physical"""
    template = {"DestinationType": "physical"}
    ister.validate_type_template(template)


def validate_type_template_good_virtual():
    """Good validate_type_template virtual"""
    template = {"DestinationType": "virtual"}
    ister.validate_type_template(template)


def validate_type_template_bad():
    """Bad validate_type_template invalid type"""
    exception_flag = False
    template = {"DestinationType": "bad"}
    try:
        ister.validate_type_template(template)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect invalid template type")


def validate_user_template_good():
    """Good validate_user_template"""
    template = [{"username": "user", "uid": "1000", "sudo": True,
                 "key": "{}/key.pub".format(os.getcwd())}]
    ister.validate_user_template(template)


def validate_user_template_bad_missing_name():
    """Bad validate_user_template missing username"""
    exception_flag = False
    template = [{"uid": "1000", "sudo": True}]
    try:
        ister.validate_user_template(template)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect missing username")


def validate_user_template_bad_duplicate_name():
    """Bad validate_user_template duplicate username"""
    exception_flag = False
    template = [{"username": "user", "uid": "1000", "sudo": True},
                {"username": "user", "uid": "1001", "sudo": True}]
    try:
        ister.validate_user_template(template)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect duplicate username")


def validate_user_template_bad_duplicate_uid():
    """Bad validate_user_template duplicate uid"""
    exception_flag = False
    template = [{"username": "user", "uid": "1000", "sudo": True},
                {"username": "usertwo", "uid": "1000", "sudo": True}]
    try:
        ister.validate_user_template(template)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect duplicate uid")


def validate_user_template_bad_invalid_uid_low():
    """Bad validate_user_template invalid uid (0)"""
    exception_flag = False
    template = [{"username": "user", "uid": "0", "sudo": True}]
    try:
        ister.validate_user_template(template)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect invalid uid (0)")


def validate_user_template_bad_invalid_uid_high():
    """Bad validate_user_template invalid uid (> uint32 max)"""
    exception_flag = False
    template = [{"username": "user", "uid": "4294967296", "sudo": True}]
    try:
        ister.validate_user_template(template)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect invalid uid (> uint32 max)")


def validate_user_template_bad_invalid_sudo():
    """Bad validate_user_template invalid sudo option"""
    exception_flag = False
    template = [{"username": "user", "uid": "1000", "sudo": "bad"}]
    try:
        ister.validate_user_template(template)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect invalid sudo option")


def validate_user_template_bad_missing_key():
    """Bad validate_user_template missing key file"""
    exception_flag = False
    template = [{"username": "user", "uid": "1000", "sudo": "password",
                 "key": "/does/not/exist"}]
    try:
        ister.validate_user_template(template)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect missing key file")


def validate_postnonchroot_template_good():
    global COMMAND_RESULTS
    COMMAND_RESULTS = []
    backup_isfile = os.path.isfile
    def mock_isfile(path):
        global COMMAND_RESULTS
        COMMAND_RESULTS.append(path)
        return True
    os.path.isfile = mock_isfile
    commands = ["file1", "file2"]
    ister.validate_postnonchroot_template([])
    ister.validate_postnonchroot_template(commands)
    os.path.isfile = backup_isfile
    commands_compare_helper(commands)


def validate_postnonchroot_template_bad():
    global COMMAND_RESULTS
    COMMAND_RESULTS = []
    backup_isfile = os.path.isfile
    exception_flag = False
    def mock_isfile(path):
        global COMMAND_RESULTS
        COMMAND_RESULTS.append(path)
        return False
    os.path.isfile = mock_isfile
    commands = ["file1"]
    try:
        ister.validate_postnonchroot_template(commands)
    except:
        exception_flag = True
    os.path.isfile = backup_isfile
    if not exception_flag:
        raise Exception("Failed to detect missing script file")


def validate_template_good():
    """Good validate_template"""
    template = json.loads(good_virtual_disk_template())
    ister.validate_template(template)


def validate_template_bad_missing_destination_type():
    """Bad validate_template missing DestinationType"""
    exception_flag = False
    template = {"PartitionLayout": [],
                "FilesystemTypes": [],
                "PartitionMountPoints": [],
                "Version": 10,
                "Bundles": []}
    try:
        ister.validate_template(template)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect missing DestinationType")


def validate_template_bad_missing_partition_layout():
    """Bad validate_template missing PartitionLayout"""
    exception_flag = False
    template = {"DestinationType": [],
                "FilesystemTypes": [],
                "PartitionMountPoints": [],
                "Version": 10,
                "Bundles": []}
    try:
        ister.validate_template(template)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect missing PartitionLayout")


def validate_template_bad_missing_filesystem_types():
    """Bad validate_template missing FilesystemTypes"""
    exception_flag = False
    template = {"PartitionLayout": [],
                "DestinationType": [],
                "PartitionMountPoints": [],
                "Version": 10,
                "Bundles": []}
    try:
        ister.validate_template(template)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect missing FilesystemTypes")


def validate_template_bad_missing_partition_mount_points():
    """Bad validate_template missing PartitionMountPoints"""
    exception_flag = False
    template = {"PartitionLayout": [],
                "FilesystemTypes": [],
                "DestinationType": [],
                "Version": 10,
                "Bundles": []}
    try:
        ister.validate_template(template)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect missing PartitionMountPoints")


def validate_template_bad_missing_version():
    """Bad validate_template missing Version"""
    exception_flag = False
    template = {"PartitionLayout": [],
                "FilesystemTypes": [],
                "DestinationType": [],
                "PartitionMountPoints": [],
                "Bundles": []}
    try:
        ister.validate_template(template)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect missing Version")


def validate_template_bad_missing_bundles():
    """Bad validate_template missing Bundles"""
    exception_flag = False
    template = {"PartitionLayout": [],
                "FilesystemTypes": [],
                "DestinationType": [],
                "PartitionMountPoints": [],
                "Version": 10}
    try:
        ister.validate_template(template)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect missing Version")


def validate_template_bad_version():
    """Bad validate_template bad Version"""
    exception_flag = False
    template = {"PartitionLayout": [],
                "FilesystemTypes": [],
                "DestinationType": [],
                "PartitionMountPoints": [],
                "Version": 0}
    try:
        ister.validate_template(template)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect bad Version")


def parse_config_good():
    """Positive tests for configuration parsing"""
    global COMMAND_RESULTS
    COMMAND_RESULTS = []
    backup_isfile = os.path.isfile
    backup_get_template_location = ister.get_template_location
    def mock_isfile_true_etc(path):
        global COMMAND_RESULTS
        COMMAND_RESULTS.append(path)
        if path.startswith("/etc"):
            return True
        else:
            return False
    def mock_isfile_true_usr(path):
        global COMMAND_RESULTS
        COMMAND_RESULTS.append(path)
        if path.startswith("/usr"):
            return True
        else:
            return False
    def mock_isfile_false(path):
        global COMMAND_RESULTS
        COMMAND_RESULTS.append(path)
        return False
    def mock_get_template_location_etc(path):
        global COMMAND_RESULTS
        COMMAND_RESULTS.append(path)
        return "file:///etc.json"
    def mock_get_template_location_usr(path):
        global COMMAND_RESULTS
        COMMAND_RESULTS.append(path)
        return "file:///usr.json"
    def mock_get_template_location_cmd(path):
        global COMMAND_RESULTS
        COMMAND_RESULTS.append(path)
        return "file:///cmd.json"
    try:
        args = lambda: None
        args.config_file = None
        args.template_file = None
        os.path.isfile = mock_isfile_true_etc
        ister.get_template_location = mock_get_template_location_etc
        config = ister.parse_config(args)
        commands = ["/etc/ister.conf", "/etc/ister.conf"]
        commands_compare_helper(commands)
        if config["template"] != "file:///etc.json":
            raise Exception("etc template does not match expected value")
        COMMAND_RESULTS = []
        os.path.isfile = mock_isfile_true_usr
        ister.get_template_location = mock_get_template_location_usr
        config = ister.parse_config(args)
        commands = ["/etc/ister.conf", "/usr/share/defaults/ister/ister.conf",
                    "/usr/share/defaults/ister/ister.conf"]
        commands_compare_helper(commands)
        if config["template"] != "file:///usr.json":
            raise Exception("usr template does not match expected value")
        COMMAND_RESULTS = []
        args.config_file = "cmd.conf"
        os.path.isfile = mock_isfile_false
        ister.get_template_location = mock_get_template_location_cmd
        config = ister.parse_config(args)
        commands = ["cmd.conf"]
        commands_compare_helper(commands)
        if config["template"] != "file:///cmd.json":
            raise Exception("cmd template does not match expected value")
        args.template_file = "/template.json"
        config = ister.parse_config(args)
        if config["template"] != "file:///template.json":
            raise Exception("full template arg does not match expected value")
        args.template_file = "template.json"
        config = ister.parse_config(args)
        if config["template"] != "file://{0}/template.json".format(
                os.getcwd()):
            raise Exception("relative template arg does not match expected "
                            "value")
    except Exception as exep:
        raise exep
    finally:
        os.path.isfile = backup_isfile
        ister.get_template_location = backup_get_template_location


def parse_config_bad():
    """Negative tests for configuration parsing"""
    exception_flag = False
    try:
        args = lambda: None
        args.config_file = None
        args.template_file = None
        ister.parse_config(args)
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect missing configuration file")


@open_wrapper("good")
def set_motd_notification_good():
    """Verify motd is written correctly"""
    global COMMAND_RESULTS
    COMMAND_RESULTS = []
    message = """Clear Linux for Intel Architecture installation in progress.

You can login to the installer image and check installation status with:

    systemctl status ister

Your computer will power off once installation completes successfully.
"""
    commands = ["/tmp/etc/issue",
                "w",
                message]
    ister.set_motd_notification("/tmp")
    commands_compare_helper(commands)


@open_wrapper("bad")
def set_motd_notification_bad():
    """Verify motd setting exceptions are handled as expected"""
    exception_flag = False
    try:
        ister.set_motd_notification("/tmp")
    except:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect setting motd failure")


def handle_options_good():
    """Test all values handle options supports"""
    # Test short options first
    sys.argv = ["ister.py", "-c", "cfg", "-t", "tpt", "-i", "-u", "/"]
    args = ister.handle_options()
    if not args.config_file == "cfg":
        raise Exception("Failed to correctly set short config file")
    if not args.template_file == "tpt":
        raise Exception("Failed to correctly set short template file")
    if not args.installer:
        raise Exception("Failed to correctly set short installer")
    if not args.url:
        raise Exception("Failed to correctly set short url")
    # Test long options next
    sys.argv = ["ister.py", "--config-file=cfg", "--template-file=tpt",
                "--installer", "--url=/"]
    args = ister.handle_options()
    if not args.config_file == "cfg":
        raise Exception("Failed to correctly set long config file")
    if not args.template_file == "tpt":
        raise Exception("Failed to correctly set long template file")
    if not args.installer:
        raise Exception("Failed to correctly set long installer")
    if not args.url:
        raise Exception("Failed to correctly set long url")
    # Test default options
    sys.argv = ["ister.py"]
    args = ister.handle_options()
    if args.config_file:
        raise Exception("Incorrect default config file set")
    if args.template_file:
        raise Exception("Incorrect default template file set")
    if args.installer:
        raise Exception("Incorrect default installer set")
    if args.url:
        raise Exception("Incorrect default url set")


def run_tests(tests):
    """Run ister test suite"""
    failed = 0
    flog = open("test-log", "w")

    with open("test-log", "w") as flog:
        for test in tests:
            try:
                test()
            except Exception as exep:
                print("Test: {0} FAIL: {1}.".format(test.__name__, exep))
                flog.write("Test: {0} FAIL: {1}.\n".format(test.__name__, exep))
                failed += 1
            else:
                print("Test: {0} PASS.".format(test.__name__))
                flog.write("Test: {0} PASS.\n".format(test.__name__))

    return failed

if __name__ == '__main__':
    TESTS = [
        run_command_good,
        run_command_bad,
        create_virtual_disk_good_meg,
        create_virtual_disk_good_gig,
        create_virtual_disk_good_tera,
        create_partitions_good_physical_min,
        create_partitions_good_physical_swap,
        create_partitions_good_physical_specific,
        create_partitions_good_virtual_swap,
        map_loop_device_good,
        map_loop_device_bad_check_output,
        map_loop_device_bad_losetup,
        get_device_name_good_virtual,
        get_device_name_good_physical,
        create_filesystems_good,
        create_filesystems_virtual_good,
        create_filesystems_good_options,
        setup_mounts_good,
        setup_mounts_virtual_good,
        setup_mounts_bad,
        add_bundles_good,
        copy_os_good,
        copy_os_url_good,
        chroot_open_class_good,
        chroot_open_class_bad_open,
        chroot_open_class_bad_chroot,
        chroot_open_class_bad_chdir,
        chroot_open_class_bad_close,
        create_account_good,
        create_account_good_uid,
        add_user_key_good,
        add_user_key_bad,
        setup_sudo_good,
        setup_sudo_bad,
        add_users_good,
        add_users_none,
        post_install_nonchroot_good,
        cleanup_physical_good,
        cleanup_virtual_good,
        get_template_location_good,
        get_template_location_bad_missing,
        get_template_location_bad_no_equal,
        get_template_location_bad_malformed,
        get_template_good,
        validate_layout_good,
        validate_layout_bad_missing_disk,
        validate_layout_bad_missing_part,
        validate_layout_bad_missing_size,
        validate_layout_bad_missing_ptype,
        validate_layout_bad_size_type,
        validate_layout_negative_size,
        validate_layout_bad_ptype,
        validate_layout_bad_multiple_efis,
        validate_layout_bad_duplicate_parts,
        validate_layout_bad_too_many_parts,
        validate_layout_bad_virtual_multi_disk,
        validate_layout_bad_missing_efi,
        validate_layout_bad_too_greedy,
        validate_fstypes_good,
        validate_fstypes_bad_missing_disk,
        validate_fstypes_bad_missing_partition,
        validate_fstypes_bad_missing_type,
        validate_fstypes_bad_type,
        validate_fstypes_bad_duplicate,
        validate_fstypes_bad_not_partition,
        validate_partition_mounts_good,
        validate_partition_mounts_bad_missing_disk,
        validate_partition_mounts_bad_missing_partition,
        validate_partition_mounts_bad_missing_mount,
        validate_partition_mounts_bad_duplicate_mount,
        validate_partition_mounts_bad_duplicate_disk_partitions,
        validate_partition_mounts_bad_not_partition,
        validate_partition_mounts_bad_missing_boot,
        validate_partition_mounts_bad_missing_root,
        validate_type_template_good_physical,
        validate_type_template_good_virtual,
        validate_type_template_bad,
        validate_user_template_good,
        validate_user_template_bad_missing_name,
        validate_user_template_bad_duplicate_name,
        validate_user_template_bad_duplicate_uid,
        validate_user_template_bad_invalid_uid_low,
        validate_user_template_bad_invalid_uid_high,
        validate_user_template_bad_invalid_sudo,
        validate_user_template_bad_missing_key,
        validate_postnonchroot_template_good,
        validate_postnonchroot_template_bad,
        validate_template_good,
        validate_template_bad_missing_destination_type,
        validate_template_bad_missing_partition_layout,
        validate_template_bad_missing_filesystem_types,
        validate_template_bad_missing_partition_mount_points,
        validate_template_bad_missing_version,
        validate_template_bad_missing_bundles,
        validate_template_bad_version,
        parse_config_good,
        parse_config_bad,
        set_motd_notification_good,
        set_motd_notification_bad,
        handle_options_good
    ]

    failed = run_tests(TESTS)
    if failed > 0:
        sys.exit(1)
