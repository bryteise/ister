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
# Using global is fine for us
# pylint: disable=W0603
# Warning for too many lines in the file isn't an issue
# pylint: disable=C0302
# We often don't use self when mocking so this warning isn't helpful
# pylint: disable=R0201
# Length of function names aren't particularly important for tests
# pylint: disable=C0103
# We do some useless seeming things to test now and then
# pylint: disable=W0104
# Classes are generally for mocking, don't need public methods
# pylint: disable=R0903
# Using lots of branches for a single test is fine
# pylint: disable=R0912
# Using lots of statements for a single test is fine
# pylint: disable=R0915
# Naked excepts are fine for us - especially in unit tests.
# pylint: disable=W0702
# Mock functions almost by definition do not make use of their inputs.
# Fine if they don't use them
# pylint: disable=W0613
# We don't need docstrings for many of these methods, especially when they are
# just mock methods anyways
# pylint: disable=missing-docstring
# Don't worry about protected access warnings since we want our unit tests to
# test those methods
# pylint: disable=protected-access


import functools
import json
import os
import sys
import shutil
import urllib.request as request
import tempfile
import socket
import netifaces
import pycurl

import ister
import ister_gui

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
    "Version" : 800, "Bundles" : ["linux-kvm"], \
    "HTTPSProxy" : "https://proxy.clear.com"}'


def good_latest_template():
    """Return string representation of good_latest_template"""
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
    "Version" : "latest", "Bundles" : ["linux-kvm"], \
    "HTTPSProxy" : "https://proxy.clear.com"}'


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
        """run_command_wrapper"""
        def mock_run_command(cmd, _=None, raise_exception=True,
                             log_output=True, environ=None, show_output=False):
            """mock_run_command wrapper"""
            COMMAND_RESULTS.append(cmd)
            if not raise_exception:
                COMMAND_RESULTS.append(False)
            if not log_output:
                COMMAND_RESULTS.append(False)
            if environ:
                https_proxy = environ.get("https_proxy")
                COMMAND_RESULTS.append(https_proxy)
            if show_output:
                COMMAND_RESULTS.append(True)
        global COMMAND_RESULTS
        COMMAND_RESULTS = []
        run_command = ister.run_command
        ister.run_command = mock_run_command
        try:
            func()
        except Exception as exep:
            raise exep
        finally:
            ister.run_command = run_command
    return wrapper


def makedirs_wrapper(test_type):
    """Wrapper for makedirs mocking"""
    def makedirs_type(func):
        """makedirs_type wrapper"""
        @functools.wraps(func)
        def wrapper():
            """makedirs_wrapper"""
            backup_makedirs = os.makedirs

            def mock_makedirs_good(dname, mode=0, exist_ok=False):
                """mock_makedirs_good wrapper"""
                COMMAND_RESULTS.append(dname)
                COMMAND_RESULTS.append(mode)
                COMMAND_RESULTS.append(exist_ok)
                return

            def mock_makedirs_bad(dname, mode=0, exist_ok=False):
                """mock_makedirs_bad wrapper"""
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
        """chroot_type wrapper"""
        @functools.wraps(func)
        def wrapper():
            """chroot_open_wrapper"""
            backup_open = os.open
            backup_chroot = os.chroot
            backup_chdir = os.chdir
            backup_close = os.close

            def mock_open_good(dest, perm):
                """mock_open_good wrapper"""
                COMMAND_RESULTS.append(dest)
                COMMAND_RESULTS.append(perm)
                return dest

            def mock_open_bad(dest, perm):
                """mock_open_bad wrapper"""
                del dest
                del perm
                raise Exception("open")

            def mock_open_silent(dest, perm):
                """mock_open_silent wrapper"""
                del perm
                return dest

            def mock_chroot_chdir_close_good(dest):
                """mock_chroot_chrdir_close_good wrapper"""
                COMMAND_RESULTS.append(dest)

            def mock_chroot_bad(dest):
                """mock_chroot_bad wrapper"""
                del dest
                raise Exception("chroot")

            def mock_chdir_bad(dest):
                """mock_chdir_bad wrapper"""
                del dest
                raise Exception("chdir")

            def mock_close_bad(dest):
                """mock_close_bad wrapper"""
                del dest
                raise Exception("close")

            def mock_chroot_chdir_close_silent(dest):
                """mock_chroot_chdir_close_silent wrapper"""
                del dest
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


def urlopen_wrapper(test_type, read_str):
    """Wrapper for urlopen"""
    def urlopen_type(func):
        """urlopen_type wrapper"""
        @functools.wraps(func)
        def wrapper():
            """open_wrapper"""
            backup_open = __builtins__.open

            class MockOpen():
                """MockOpen wrapper class"""
                def read(self):
                    """read wrapper"""
                    COMMAND_RESULTS.append("read")
                    return read_str

                def close(self):
                    """close wrapper"""
                    COMMAND_RESULTS.append("close")
                    return

                def __exit__(self, *args):
                    return

                def __enter__(self, *args):
                    return self

            def mock_open_good(url):
                """mock_open_good wrapper"""
                COMMAND_RESULTS.append(url)
                return MockOpen()

            def mock_open_bad(url):
                """mock_open_bad wrapper"""
                del url
                raise Exception("urlopen")

            if test_type == "good":
                request.urlopen = mock_open_good
            elif test_type == "bad":
                request.urlopen = mock_open_bad
            try:
                func()
            except Exception as exep:
                raise exep
            finally:
                request.urlopen = backup_open
        return wrapper
    return urlopen_type


def open_wrapper(test_type, read_str):
    """Wrapper for open"""
    def open_type(func):
        """open_type wrapper"""
        @functools.wraps(func)
        def wrapper():
            """open_wrapper"""
            backup_open = __builtins__.open

            class MockOpen():
                """MockOpen wrapper class"""
                def write(self, data):
                    """write wrapper"""
                    COMMAND_RESULTS.append(data)

                def read(self):
                    """read wrapper"""
                    COMMAND_RESULTS.append("read")
                    return read_str

                def close(self):
                    """close wrapper"""
                    COMMAND_RESULTS.append("close")
                    return

                def writelines(self, data):
                    """writelines wrapper"""
                    COMMAND_RESULTS.append(data)
                    return

                def readlines(self):
                    """readlines wrapper"""
                    COMMAND_RESULTS.append("readlines")
                    return read_str

                def __exit__(self, *args):
                    return

                def __enter__(self, *args):
                    return self

            def mock_open_good(dest, perm):
                """mock_open_good wrapper"""
                COMMAND_RESULTS.append(dest)
                COMMAND_RESULTS.append(perm)
                return MockOpen()

            def mock_open_bad(dest, perm):
                """mock_open_bad wrapper"""
                del dest
                del perm
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


def fdopen_wrapper(test_type, read_str):
    """Wrapper for fdopen"""
    def fd_open_type(func):
        """fdopen_type wrapper"""
        @functools.wraps(func)
        def fd_wrapper():
            """fdopen_wrapper"""
            backup_open = os.fdopen

            class MockOpen():
                """MockOpen wrapper class"""
                def write(self, data):
                    """write wrapper"""
                    COMMAND_RESULTS.append(data)

                def read(self):
                    """read wrapper"""
                    COMMAND_RESULTS.append("read")
                    return read_str

                def close(self):
                    """close wrapper"""
                    COMMAND_RESULTS.append("close")
                    return

                def writelines(self, data):
                    """writelines wrapper"""
                    global COMMAND_RESULTS
                    COMMAND_RESULTS += data
                    return

            def mock_open_good(dest, perm):
                """mock_open_good wrapper"""
                COMMAND_RESULTS.append(dest)
                COMMAND_RESULTS.append(perm)
                return MockOpen()

            def mock_open_bad(dest, perm):
                """mock_open_bad wrapper"""
                del dest
                del perm
                raise Exception("open")

            if test_type == "good":
                os.fdopen = mock_open_good
            elif test_type == "bad":
                os.fdopen = mock_open_bad
            try:
                func()
            except Exception as exep:
                raise exep
            finally:
                os.fdopen = backup_open
        return fd_wrapper
    return fd_open_type


def add_user_key_wrapper(func):
    """Wrapper for functions in add_user_key"""
    @functools.wraps(func)
    @makedirs_wrapper("good")
    def wrapper():
        """add_user_key_wrapper"""
        import pwd
        backup_chown = os.chown
        backup_getpwnam = pwd.getpwnam

        def mock_chown(dest, uid, gid):
            """mock_chown wrapper"""
            COMMAND_RESULTS.append(dest)
            COMMAND_RESULTS.append(uid)
            COMMAND_RESULTS.append(gid)

        def mock_getpwnam(dest):
            """mock_getpwnam wrapper"""
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
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("Bad command did not fail")


@run_command_wrapper
def run_command_with_env():
    """run_command with environment variable passed"""
    command = ["true", os.getenv("https_proxy")]
    ister.run_command("true", environ=os.environ)
    commands_compare_helper(command)


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
    for idx, item in enumerate(commands):
        del item
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
        """mock_check_output wrapper"""
        global COMMAND_RESULTS
        COMMAND_RESULTS = cmd
        return b"/dev/loop0"
    subprocess.check_output = mock_check_output
    template = {"PartitionLayout": [{"disk": "image"}]}
    commands = ["losetup", "--partscan", "--find", "--show",
                "image", "partprobe /dev/loop0"]
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
        """mock_check_output wrapper"""
        del cmd
        raise Exception("bad")
    subprocess.check_output = mock_check_output
    exception_flag = False
    template = {"PartitionLayout": [{"disk": "image"}]}
    try:
        ister.map_loop_device(template, 0)
    except Exception:
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
        """mock_check_output wrapper"""
        del cmd
        return b""
    subprocess.check_output = mock_check_output
    exception_flag = False
    template = {"PartitionLayout": [{"disk": "image"}]}
    try:
        ister.map_loop_device(template, 0)
    except Exception:
        exception_flag = True
    finally:
        subprocess.check_output = check_output_backup
    if not exception_flag:
        raise Exception("Did not detect losetup failure")


def get_device_name_good_virtual():
    """Get virtual device name"""
    template = {"dev": "/dev/loop0"}
    dev = ister.get_device_name(template, None)
    if dev != ("/dev/loop0p", "p"):
        raise Exception("Bad device name returned {0}".format(dev))


def get_device_name_good_physical():
    """Get physical device name"""
    listdir_backup = os.listdir

    def mock_listdir(directory):
        """mock_listdir wrapper"""
        del directory
        return ["sda", "sda1", "sda2"]

    os.listdir = mock_listdir
    dev = ister.get_device_name({}, "sda")
    os.listdir = listdir_backup
    if dev != ("/dev/sda", ""):
        raise Exception("Bad device name returned {0}".format(dev))


def get_device_name_good_mmcblk_physical():
    """Get physical device name"""
    listdir_backup = os.listdir

    def mock_listdir(directory):
        """mock_listdir wrapper"""
        del directory
        return ["mmcblk1", "mmcblk1p1", "mmcblk1p2"]

    os.listdir = mock_listdir
    dev = ister.get_device_name({}, "mmcblk1")
    os.listdir = listdir_backup
    if dev != ("/dev/mmcblk1p", "p"):
        raise Exception("Bad device name returned {0}".format(dev))


@run_command_wrapper
def create_filesystems_good():
    """Create filesystems without options"""
    listdir_backup = os.listdir

    def mock_listdir(directory):
        """mock_listdir wrapper"""
        del directory
        return ["sda", "sda1", "sda2", "sda3", "sda4",
                "sdb", "sdb1", "sdb2", "sdb3"]

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
    commands = ["mkfs.ext2 -F /dev/sda1",
                "mkfs.ext3 -F /dev/sda2",
                "mkfs.ext4 -F /dev/sda3",
                "mkfs.btrfs -f /dev/sda4",
                "mkfs.vfat /dev/sdb1",
                "sgdisk /dev/sdb "
                "--typecode=2:0657fd6d-a4ab-43c4-84e5-0933c84b4f4f",
                "mkswap /dev/sdb2",
                "mkfs.xfs -f /dev/sdb3"]
    os.listdir = mock_listdir
    ister.create_filesystems(template)
    os.listdir = listdir_backup
    commands_compare_helper(commands)


@run_command_wrapper
def create_filesystems_mmcblk_good():
    """Create filesystems without options"""
    listdir_backup = os.listdir

    def mock_listdir(directory):
        """mock_listdir wrapper"""
        del directory
        return ["mmcblk1", "mmcblk1p1", "mmcblk1p2", "mmcblk1p3"]

    template = {"FilesystemTypes": [{"disk": "mmcblk1", "type": "vfat",
                                     "partition": 1},
                                    {"disk": "mmcblk1", "type": "swap",
                                     "partition": 2},
                                    {"disk": "mmcblk1", "type": "ext4",
                                     "partition": 3}]}
    commands = ["mkfs.vfat /dev/mmcblk1p1",
                "sgdisk /dev/mmcblk1 "
                "--typecode=2:0657fd6d-a4ab-43c4-84e5-0933c84b4f4f",
                "mkswap /dev/mmcblk1p2",
                "mkfs.ext4 -F /dev/mmcblk1p3"]
    os.listdir = mock_listdir
    ister.create_filesystems(template)
    os.listdir = listdir_backup
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
                "sgdisk /dev/loop0 "
                "--typecode=2:0657fd6d-a4ab-43c4-84e5-0933c84b4f4f",
                "mkswap /dev/loop0p2",
                "mkfs.ext4 -F /dev/loop0p3"]
    ister.create_filesystems(template)
    commands_compare_helper(commands)


@run_command_wrapper
def create_filesystems_good_options():
    """Create filesystems with options"""
    listdir_backup = os.listdir

    def mock_listdir(directory):
        """mock_listdir wrapper"""
        del directory
        return ["sda", "sda1", "sda2", "sda3", "sda4",
                "sdb", "sdb1", "sdb2", "sdb3"]

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
    commands = ["mkfs.ext2 -F opt /dev/sda1",
                "mkfs.ext3 -F opt /dev/sda2",
                "mkfs.ext4 -F opt /dev/sda3",
                "mkfs.btrfs -f opt /dev/sda4",
                "mkfs.vfat opt /dev/sdb1",
                "sgdisk /dev/sdb "
                "--typecode=2:0657fd6d-a4ab-43c4-84e5-0933c84b4f4f",
                "mkswap opt /dev/sdb2",
                "mkfs.xfs -f opt /dev/sdb3"]
    os.listdir = mock_listdir
    ister.create_filesystems(template)
    os.listdir = listdir_backup
    commands_compare_helper(commands)


@run_command_wrapper
def setup_mounts_good():
    """Setup mount points for install"""
    backup_mkdtemp = tempfile.mkdtemp

    def mock_mkdtemp(*_, **kwargs):
        """mock_mkdtemp wrapper"""
        if not kwargs.get("prefix"):
            raise Exception("Missing prefix argument to mkdtemp")
        COMMAND_RESULTS.append(kwargs["prefix"])
        return "/tmp"
    tempfile.mkdtemp = mock_mkdtemp
    template = {"PartitionMountPoints": [{"mount": "/", "disk": "sda",
                                          "partition": 1},
                                         {"mount": "/boot", "disk": "sda",
                                          "partition": 2}],
                "FilesystemTypes": [{"disk": "sda", "partition": 1,
                                     "type": "vfat"},
                                    {"disk": "sda", "partition": 2,
                                     "type": "ext4"}],
                "Version": 10}
    commands = ["ister-10-",
                "sgdisk /dev/sda "
                "--typecode=1:4f68bce3-e8cd-4db1-96e7-fbcaf984b709",
                "mount /dev/sda1 /tmp/",
                "sgdisk /dev/sda "
                "--typecode=2:c12a7328-f81f-11d2-ba4b-00a0c93ec93b",
                "mkdir -p /tmp/boot",
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
def setup_mounts_good_mbr():
    """Setup mount points for mbr install"""
    backup_mkdtemp = tempfile.mkdtemp

    def mock_mkdtemp(*_, **kwargs):
        """mock_mkdtemp wrapper"""
        if not kwargs.get("prefix"):
            raise Exception("Missing prefix argument to mkdtemp")
        COMMAND_RESULTS.append(kwargs["prefix"])
        return "/tmp"
    tempfile.mkdtemp = mock_mkdtemp
    template = {"PartitionMountPoints": [{"mount": "/", "disk": "sda",
                                          "partition": 1},
                                         {"mount": "/boot", "disk": "sda",
                                          "partition": 2}],
                "FilesystemTypes": [{"disk": "sda", "partition": 1,
                                     "type": "ext4"},
                                    {"disk": "sda", "partition": 2,
                                     "type": "ext4"}],
                "Version": 10,
                "LegacyBios": True}
    commands = ["ister-10-",
                "sgdisk /dev/sda "
                "--typecode=1:4f68bce3-e8cd-4db1-96e7-fbcaf984b709",
                "mount /dev/sda1 /tmp/",
                "sgdisk /dev/sda --attributes=2:set:2",
                "mkdir -p /tmp/boot",
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
def setup_mounts_good_no_boot():
    """Setup mount points for install without a /boot (mbr type)"""
    backup_mkdtemp = tempfile.mkdtemp

    def mock_mkdtemp(*_, **kwargs):
        """mock_mkdtemp wrapper"""
        if not kwargs.get("prefix"):
            raise Exception("Missing prefix argument to mkdtemp")
        COMMAND_RESULTS.append(kwargs["prefix"])
        return "/tmp"
    tempfile.mkdtemp = mock_mkdtemp
    template = {"PartitionMountPoints": [{"mount": "/", "disk": "sda",
                                          "partition": 1}],
                "FilesystemTypes": [{"disk": "sda", "partition": 1,
                                     "type": "vfat"}],
                "Version": 10,
                "LegacyBios": True}
    commands = ["ister-10-",
                "sgdisk /dev/sda "
                "--typecode=1:4f68bce3-e8cd-4db1-96e7-fbcaf984b709",
                "sgdisk /dev/sda --attributes=1:set:2",
                "mount /dev/sda1 /tmp/"]
    try:
        target_dir = ister.setup_mounts(template)
    finally:
        tempfile.mkdtemp = backup_mkdtemp
    if target_dir != "/tmp":
        raise Exception("Target dir doesn't match expected: {0}"
                        .format(target_dir))
    commands_compare_helper(commands)


@run_command_wrapper
def setup_mounts_good_units():
    """Setup mount points for install"""
    backup_mkdtemp = ister.tempfile.mkdtemp
    backup_run_command = ister.run_command

    def mock_mkdtemp(*_, **__):
        """mock_mkdtemp wrapper"""
        del __
        return "/tmp"
    ister.tempfile.mkdtemp = mock_mkdtemp

    def mock_run_command(cmd, *_):
        """mock run for setup mounts test"""
        COMMAND_RESULTS.append(cmd)
        return (["", "X"],)
    ister.run_command = mock_run_command
    template = {"PartitionMountPoints": [{"mount": "/", "disk": "sda",
                                          "partition": 1},
                                         {"mount": "/boot", "disk": "sda",
                                          "partition": 2},
                                         {"mount": "/home", "disk": "sda",
                                          "partition": 3},
                                         {"mount": "/home/data", "disk": "sda",
                                          "partition": 4},
                                         {"mount": "/root", "disk": "sda",
                                          "partition": 5}],
                "FilesystemTypes": [{"disk": "sda", "partition": 1,
                                     "type": "vfat"},
                                    {"disk": "sda", "partition": 2,
                                     "type": "ext4"},
                                    {"disk": "sda", "partition": 3,
                                     "type": "ext4"},
                                    {"disk": "sda", "partition": 4,
                                     "type": "ext4"},
                                    {"disk": "sda", "partition": 5,
                                     "type": "ext4"}],
                "Version": 10}
    commands = ["sgdisk /dev/sda "
                "--typecode=1:4f68bce3-e8cd-4db1-96e7-fbcaf984b709",
                "mount /dev/sda1 /tmp/",
                "sgdisk /dev/sda "
                "--typecode=2:c12a7328-f81f-11d2-ba4b-00a0c93ec93b",
                "mkdir -p /tmp/boot",
                "mount /dev/sda2 /tmp/boot",
                'sgdisk /dev/sda '
                '--typecode=3:933AC7E1-2EB4-4F13-B844-0E14E2AEF915',
                'mkdir -p /tmp/home',
                'mount /dev/sda3 /tmp/home',
                'sgdisk /dev/sda '
                '--typecode=4:933AC7E1-2EB4-4F13-B844-0E14E2AEF915',
                'mkdir -p /tmp/home/data',
                'mount /dev/sda4 /tmp/home/data',
                'sgdisk --info=4 /dev/sda',
                'mkdir -p /tmp/root',
                'mount /dev/sda5 /tmp/root',
                'sgdisk --info=5 /dev/sda']
    try:
        _ = ister.setup_mounts(template)
    finally:
        ister.tempfile.mkdtemp = backup_mkdtemp
        ister.run_command = backup_run_command
    commands_compare_helper(commands)


@run_command_wrapper
def setup_mounts_virtual_good():
    """Setup virtual mount points for install"""
    backup_mkdtemp = tempfile.mkdtemp

    def mock_mkdtemp(*_, **kwargs):
        """mock_mkdtemp wrapper"""
        if not kwargs.get("prefix"):
            raise Exception("Missing prefix argument to mkdtemp")
        COMMAND_RESULTS.append(kwargs["prefix"])
        return "/tmp"
    tempfile.mkdtemp = mock_mkdtemp
    template = {"PartitionMountPoints": [{"mount": "/", "disk": "test",
                                          "partition": 1},
                                         {"mount": "/boot", "disk": "test",
                                          "partition": 2}],
                "FilesystemTypes": [{"disk": "test", "partition": 1,
                                     "type": "vfat"},
                                    {"disk": "test", "partition": 2,
                                     "type": "ext4"}],
                "dev": "/dev/loop0",
                "Version": 10}
    commands = ["ister-10-",
                "sgdisk /dev/loop0 "
                "--typecode=1:4f68bce3-e8cd-4db1-96e7-fbcaf984b709",
                "mount /dev/loop0p1 /tmp/",
                "sgdisk /dev/loop0 "
                "--typecode=2:c12a7328-f81f-11d2-ba4b-00a0c93ec93b",
                "mkdir -p /tmp/boot",
                "mount /dev/loop0p2 /tmp/boot"]
    try:
        target_dir = ister.setup_mounts(template)
    finally:
        tempfile.mkdtemp = backup_mkdtemp
    if target_dir != "/tmp":
        raise Exception("Target dir doesn't match expected: {0}"
                        .format(target_dir))
    commands_compare_helper(commands)


@run_command_wrapper
def setup_mounts_mmcblk_good():
    """Setup mount points for install"""
    listdir_backup = os.listdir

    def mock_listdir(directory):
        """mock_listdir wrapper"""
        del directory
        return ["sda", "sda1", "sda2", "mmcblk1", "mmcblk1p1", "mmcblk1p2"]

    backup_mkdtemp = tempfile.mkdtemp

    def mock_mkdtemp(*_, **kwargs):
        """mock_mkdtemp wrapper"""
        if not kwargs.get("prefix"):
            raise Exception("Missing prefix argument to mkdtemp")
        COMMAND_RESULTS.append(kwargs["prefix"])
        return "/tmp"
    tempfile.mkdtemp = mock_mkdtemp
    template = {"PartitionMountPoints": [{"mount": "/", "disk": "mmcblk1",
                                          "partition": 1},
                                         {"mount": "/boot", "disk": "mmcblk1",
                                          "partition": 2}],
                "FilesystemTypes": [{"disk": "mmcblk1", "partition": 1,
                                     "type": "vfat"},
                                    {"disk": "mmcblk1", "partition": 2,
                                     "type": "ext4"}],
                "Version": 10}
    commands = ["ister-10-",
                "sgdisk /dev/mmcblk1 "
                "--typecode=1:4f68bce3-e8cd-4db1-96e7-fbcaf984b709",
                "mount /dev/mmcblk1p1 /tmp/",
                "sgdisk /dev/mmcblk1 "
                "--typecode=2:c12a7328-f81f-11d2-ba4b-00a0c93ec93b",
                "mkdir -p /tmp/boot",
                "mount /dev/mmcblk1p2 /tmp/boot"]
    os.listdir = mock_listdir
    try:
        target_dir = ister.setup_mounts(template)
    finally:
        tempfile.mkdtemp = backup_mkdtemp
        os.listdir = listdir_backup
    if target_dir != "/tmp":
        raise Exception("Target dir doesn't match expected: {0}"
                        .format(target_dir))
    commands_compare_helper(commands)


def setup_mounts_bad():
    """Setup mount points mkdtemp failure"""
    backup_mkdtemp = tempfile.mkdtemp
    template = None

    def mock_mkdtemp(*_, **kwargs):
        """mock_mkdtemp wrapper"""
        if not kwargs.get("prefix"):
            # Lack of Exception causes test failure
            return True
        raise Exception("mkdtemp")
    tempfile.mkdtemp = mock_mkdtemp
    exception_flag = False
    try:
        _ = ister.setup_mounts(template)
    except Exception:
        exception_flag = True
    finally:
        tempfile.mkdtemp = backup_mkdtemp
    if not exception_flag:
        raise Exception("Failed to handle mkdtemp failure")


@open_wrapper("good", "")
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


@open_wrapper("good", "1\n")
def get_current_format_good():
    """Ensure correct data read from format file"""
    global COMMAND_RESULTS
    COMMAND_RESULTS = []
    commands = ["/usr/share/defaults/swupd/format",
                "r",
                "read",
                "1"]
    frmt = ister.get_current_format()
    COMMAND_RESULTS.append(frmt)
    commands_compare_helper(commands)


@open_wrapper("good", "")
@makedirs_wrapper("good")
def set_hostname_good():
    """Ensure /etc/hostname has the proper hostname"""
    global COMMAND_RESULTS
    COMMAND_RESULTS = []
    commands = ["/dne/etc/",
                0,
                False,
                "/dne/etc/hostname",
                "w",
                "clr0"]
    ister.set_hostname({"Hostname": "clr0"}, "/dne")
    commands_compare_helper(commands)


@run_command_wrapper
def copy_os_good():
    """Check installer command"""
    backup_add_bundles = ister.add_bundles
    ister.add_bundles = lambda x, y: None
    backup_which = shutil.which
    shutil.which = lambda x: False

    def args():
        """args empty object"""
        None
    args.contenturl = "ctest"
    args.versionurl = "vtest"
    args.format = "formattest"
    args.statedir = "/statetest"
    swupd_cmd = "swupd verify --install --path=/ --manifest=0 "              \
                "--contenturl=ctest --versionurl=vtest --format=formattest " \
                "--statedir=/statetest"
    commands = [swupd_cmd,
                os.getenv("https_proxy"),
                True]
    ister.copy_os(args, {"Version": 0, "DestinationType": ""}, "/")
    ister.add_bundles = backup_add_bundles
    shutil.which = backup_which
    commands_compare_helper(commands)


@run_command_wrapper
def copy_os_proxy_good():
    """Check installer command with proxy present"""
    backup_add_bundles = ister.add_bundles
    ister.add_bundles = lambda x, y: None
    backup_which = shutil.which
    shutil.which = lambda x: False

    def args():
        """args empty object"""
        None
    args.contenturl = "ctest"
    args.versionurl = "vtest"
    args.format = "formattest"
    args.statedir = "/statetest"
    swupd_cmd = "swupd verify --install --path=/ --manifest=0 "              \
                "--contenturl=ctest --versionurl=vtest --format=formattest " \
                "--statedir=/statetest"
    commands = [swupd_cmd,
                "https://to.clearlinux.org",
                True]
    template = {
        "Version": 0,
        "DestinationType": "",
        "HTTPSProxy": "https://to.clearlinux.org"
    }
    ister.copy_os(args, template, "/")
    ister.add_bundles = backup_add_bundles
    shutil.which = backup_which
    commands_compare_helper(commands)


@run_command_wrapper
def copy_os_format_good():
    """Check installer command with format string"""
    backup_add_bundles = ister.add_bundles
    ister.add_bundles = lambda x, y: None
    backup_which = shutil.which
    shutil.which = lambda x: False
    backup_get_current_format = ister.get_current_format
    ister.get_current_format = lambda: "test"

    def args():
        """args empty object"""
        None

    args.contenturl = "ctest"
    args.versionurl = "vtest"
    args.format = None
    args.statedir = "/statetest"
    swupd_cmd = "swupd verify --install --path=/ --manifest=0 "        \
                "--contenturl=ctest --versionurl=vtest --format=test " \
                "--statedir=/statetest"
    commands = [swupd_cmd,
                os.getenv("https_proxy"),
                True]
    ister.copy_os(args, {"Version": 0, "DestinationType": ""}, "/")
    ister.add_bundles = backup_add_bundles
    shutil.which = backup_which
    ister.get_current_format = backup_get_current_format
    commands_compare_helper(commands)


@run_command_wrapper
def copy_os_which_good():
    """Check installer command"""
    backup_add_bundles = ister.add_bundles
    ister.add_bundles = lambda x, y: None
    backup_which = shutil.which
    shutil.which = lambda x: True

    def args():
        """args empty object"""
        None

    args.contenturl = "ctest"
    args.versionurl = "vtest"
    args.format = "formattest"
    args.statedir = "/statetest"
    swupd_cmd = "swupd verify --install --path=/ --manifest=0 "              \
                "--contenturl=ctest --versionurl=vtest --format=formattest " \
                "--statedir=/statetest"
    swupd_cmd = "stdbuf -o 0 {0}".format(swupd_cmd)
    commands = [swupd_cmd,
                os.getenv("https_proxy"),
                True]
    ister.copy_os(args, {"Version": 0, "DestinationType": ""}, "/")
    ister.add_bundles = backup_add_bundles
    shutil.which = backup_which
    commands_compare_helper(commands)


@run_command_wrapper
@makedirs_wrapper("good")
def copy_os_physical_good():
    """Check installer command for physical install"""
    backup_add_bundles = ister.add_bundles
    ister.add_bundles = lambda x, y: None
    backup_which = shutil.which
    shutil.which = lambda x: False

    def args():
        """args empty object"""
        None

    args.contenturl = "ctest"
    args.versionurl = "vtest"
    args.format = "formattest"
    args.statedir = "/statetest"
    swupd_cmd = "swupd verify --install --path=/ --manifest=0 "              \
                "--contenturl=ctest --versionurl=vtest --format=formattest " \
                "--statedir=/statetest"
    commands = ["/var/lib/swupd",
                0,
                True,
                "//var/tmp",
                0,
                False,
                "mount --bind //var/tmp /var/lib/swupd",
                swupd_cmd,
                os.getenv("https_proxy"),
                True]
    ister.copy_os(args, {"Version": 0, "DestinationType": "physical"}, "/")
    ister.add_bundles = backup_add_bundles
    shutil.which = backup_which
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
        with ister.ChrootOpen("/tmp"):
            pass
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect open failure")


@chroot_open_wrapper("bad chroot")
def chroot_open_class_bad_chroot():
    """Ensure chroot failures handled in ChrootOpen"""
    exception_flag = False
    try:
        with ister.ChrootOpen("/tmp"):
            pass
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect chroot failure")


@chroot_open_wrapper("bad chdir")
def chroot_open_class_bad_chdir():
    """Ensure chdir failures handled in ChrootOpen"""
    exception_flag = False
    try:
        with ister.ChrootOpen("/tmp"):
            pass
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect chdir failure")


@chroot_open_wrapper("bad close")
def chroot_open_class_bad_close():
    """Ensure close failures handled in ChrootOpen"""
    exception_flag = False
    try:
        with ister.ChrootOpen("/tmp"):
            pass
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect close failure")


@run_command_wrapper
@chroot_open_wrapper("silent")
def create_account_good():
    """Create account no uid"""
    template = {"username": "user"}
    commands = ["useradd -U -m user -p ''"]
    ister.create_account(template, "/tmp")
    commands_compare_helper(commands)


@run_command_wrapper
@chroot_open_wrapper("silent")
def create_account_good_uid():
    """Create account with uid"""
    template = {"username": "user", "uid": "1000"}
    commands = ["useradd -U -m -u 1000 user -p ''"]
    ister.create_account(template, "/tmp")
    commands_compare_helper(commands)


@chroot_open_wrapper("silent")
@open_wrapper("good", "")
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
@open_wrapper("bad", "")
@add_user_key_wrapper
def add_user_key_bad():
    """Ensure failures during add_user_key are handled"""
    template = {"username": "user", "key": "public"}
    exception_flag = False
    try:
        ister.add_user_key(template, "/tmp")
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("Didn't handle failure during key add")


@open_wrapper("good", "")
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


@open_wrapper("bad", "")
@add_user_key_wrapper
def setup_sudo_bad():
    """Ensure failures during setup_sudo are handled"""
    template = {"username": "user"}
    exception_flag = False
    try:
        ister.setup_sudo(template, "/tmp")
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("Didn't handle failure during setup sudo")


def add_users_good():
    """Verify add users is successful with valid input"""
    backup_create_account = ister.create_account
    backup_add_user_key = ister.add_user_key
    backup_setup_sudo = ister.setup_sudo
    backup_disable_root_login = ister.disable_root_login
    backup_add_user_fullname = ister.add_user_fullname

    def mock_create_account(user, target_dir):
        """mock_create_account wrapper"""
        COMMAND_RESULTS.append(user["n"])
        COMMAND_RESULTS.append(target_dir)

    def mock_add_user_key(_, __):
        """mock_add_user_key wrapper"""
        del __
        COMMAND_RESULTS.append("key")

    def mock_setup_sudo(_, __):
        """mock_setup_sudo wrapper"""
        del __
        COMMAND_RESULTS.append("sudo")

    def mock_disable_root_login(_):
        """mock_disable_root_login wrapper"""
        COMMAND_RESULTS.append("password")

    def mock_add_user_fullname(_, __):
        """mock_add_user_fullname wrapper"""
        COMMAND_RESULTS.append("fullname")

    ister.create_account = mock_create_account
    ister.add_user_key = mock_add_user_key
    ister.setup_sudo = mock_setup_sudo
    ister.disable_root_login = mock_disable_root_login
    ister.add_user_fullname = mock_add_user_fullname
    global COMMAND_RESULTS
    COMMAND_RESULTS = []
    target_dir = "/tmp"
    commands = ["one",
                target_dir,
                "key",
                "sudo",
                "password",
                "two",
                target_dir,
                "key",
                "three",
                target_dir,
                "sudo",
                "password",
                "four",
                target_dir,
                "fullname"]
    template = {"Users": [{"n": "one", "key": "akey", "sudo": True},
                          {"n": "two", "key": "akey", "sudo": False},
                          {"n": "three", "sudo": True},
                          {"n": "four", "fullname": "Test User"}]}
    ister.add_users(template, target_dir)
    ister.create_account = backup_create_account
    ister.add_user_key = backup_add_user_key
    ister.setup_sudo = backup_setup_sudo
    ister.disable_root_login = backup_disable_root_login
    ister.add_user_fullname = backup_add_user_fullname
    commands_compare_helper(commands)


def add_users_none():
    """Verify that nothing happens without users to add"""
    backup_create_account = ister.create_account

    def mock_create_account(_, __):
        """mock_create_account wrapper"""
        del __
        raise Exception("Account creation attempted with no users")
    ister.create_account = mock_create_account
    try:
        ister.add_users({}, "")
    except Exception as exep:
        raise exep
    finally:
        ister.create_account = backup_create_account


@chroot_open_wrapper("silent")
def add_user_fullname():
    import subprocess

    global COMMAND_RESULTS
    COMMAND_RESULTS = []

    def mock_call(cmd):
        """mock_call wrapper"""
        COMMAND_RESULTS.extend(cmd)

    backup_call = subprocess.call
    subprocess.call = mock_call

    template = {"fullname": "Test User", "username": "user"}
    commands = ["chfn", "-f", "Test User", "user"]
    ister.add_user_fullname(template, "/tmp")
    subprocess.call = backup_call
    commands_compare_helper(commands)


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
        """mock_isdir wrapper"""
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
        """mock_isdir wrapper"""
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
        _ = ister.get_template_location("no-template.conf")
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("No error when reading from a nonexistant file")


def get_template_location_bad_no_equal():
    """Bad get_template_location test '=' content missing"""
    exception_flag = False
    try:
        _ = ister.get_template_location("bad-ister1.conf")
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("No error from loading no '=' template file")


def get_template_location_bad_malformed():
    """Bad get_template_location test (template variable missing)"""
    exception_flag = False
    try:
        _ = ister.get_template_location("bad-ister2.conf")
    except Exception:
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
                                    {"disk": "sda", "partition": 2,
                                     "size": "4G", "type": "swap"},
                                    {"disk": "sda", "partition": 3,
                                     "size": "rest", "type": "linux"}],
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


def validate_layout_good_missing_efi_virtual():
    """Good validate_layout without EFI partition type on virtual"""
    template = {"PartitionLayout": [{"disk": "sda", "partition": 1,
                                     "size": "4G", "type": "linux"}],
                "DestinationType": "virtual"}
    try:
        ister.validate_layout(template)
    except Exception as exep:
        raise Exception("Valid template failed to parse {}".format(exep))


def validate_layout_good_missing_boot():
    """Good validate_layout without boot partition (MBR type)"""
    template = {"PartitionLayout": [{"disk": "sda", "partition": 1,
                                     "size": "4G", "type": "linux"}],
                "DestinationType": "physical",
                "LegacyBios": True}
    try:
        ister.validate_layout(template)
    except Exception as exep:
        raise Exception("Valid template failed to parse {}".format(exep))


def validate_layout_bad_missing_disk():
    """Bad validate_layout no disk on partition"""
    exception_flag = False
    template = {"PartitionLayout": [{"partition": 1, "size": "512M",
                                     "type": "EFI"}]}
    try:
        ister.validate_layout(template)
    except Exception:
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
    except Exception:
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
    except Exception:
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
    except Exception:
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
    except Exception:
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
    except Exception:
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
    except Exception:
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
    except Exception:
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
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect duplicate partitions")


def validate_layout_bad_too_many_parts():
    """Bad validate_layout over 128 partitions"""
    exception_flag = False
    template = {"PartitionLayout": [{"disk": "sda", "partition": 1,
                                     "size": "1G", "ptype": "EFI"}]}
    for i in range(1, 129):
        template["PartitionLayout"].append({"disk": "sda", "partition": i,
                                            "size": "1G", "ptype": "linux"})
    try:
        ister.validate_layout(template)
    except Exception:
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
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect multiple disks when using virtual \
as destination")


def validate_layout_bad_missing_efi():
    """Bad validate_layout without EFI partition type"""
    exception_flag = False
    template = {"PartitionLayout": [{"disk": "sda", "partition": 1,
                                     "size": "4G", "type": "linux"}],
                "DestinationType": "physical",
                "LegacyBios": False}
    try:
        ister.validate_layout(template)
    except Exception:
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
    except Exception:
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
    except Exception as e:
        print(e)
        raise Exception("Valid template failed to parse")
    if len(partition_fstypes) != 7:
        raise Exception("Returned incorrect number of partition fstypes")
    for part in ["sda1", "sda2", "sda3", "sda4", "sda5", "sda6", "sda7"]:
        if part not in partition_fstypes:
            raise Exception("Missing {} from partition_fstypes".format(part))


def validate_fstypes_good_without_format():
    """Good validate_fstypes"""
    template = {"FilesystemTypes": [{"disk": "sda", "partition": 1,
                                     "type": "ext2", "disable_format": True},
                                    {"disk": "sda", "partition": 2,
                                     "type": "ext3", "disable_format": True},
                                    {"disk": "sda", "partition": 3,
                                     "type": "ext4"},
                                    {"disk": "sda", "partition": 4,
                                     "type": "vfat", "disable_format": True},
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
    except Exception:
        raise Exception("Valid template failed to parse")
    if len(partition_fstypes) != 7:
        raise Exception("Returned incorrect number of partition fstypes")
    for part in ["sda1", "sda2", "sda3", "sda4", "sda5", "sda6", "sda7"]:
        if part not in partition_fstypes:
            raise Exception("Missing {} from partition_fstypes".format(part))


def validate_fstypes_bad_format():
    """Bad validate_fstypes because root(/) can't have 'disable_format'"""
    exception_flag = False
    template = {"FilesystemTypes": [{"disk": "sda", "partition": 1,
                                     "type": "ext2", "disable_format": True},
                                    {"disk": "sda", "partition": 2,
                                     "type": "ext3", "disable_format": True},
                                    {"disk": "sda", "partition": 3,
                                     "type": "swap"}]}
    template["PartitionMountPoints"] = {"disk": "sda", "partition": 1,
                                        "mount": "/"}
    parts_to_size = {"sda1": "10G", "sda2": "10G", "sda3": "10G"}
    try:
        ister.validate_fstypes(template, parts_to_size)
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("Root (/) partition can not have the format disabled")


def validate_fstypes_bad_missing_disk():
    """Bad validate_fstypes missing disk"""
    exception_flag = False
    template = {"FilesystemTypes": [{"partition": 1, "type": "ext2"}]}
    try:
        ister.validate_fstypes(template, None)
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("Missing disk not detected")


def validate_fstypes_bad_missing_partition():
    """Bad validate_fstypes missing partition"""
    exception_flag = False
    template = {"FilesystemTypes": [{"disk": "sda", "type": "ext2"}]}
    try:
        ister.validate_fstypes(template, None)
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("Missing partition not detected")


def validate_fstypes_bad_missing_type():
    """Bad validate_fstypes missing type"""
    exception_flag = False
    template = {"FilesystemTypes": [{"partition": 1, "disk": "sda"}]}
    try:
        ister.validate_fstypes(template, None)
    except Exception:
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
    except Exception:
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
    except Exception:
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
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("fs not in partition map not detected")


def validate_hostname_good():
    """Good hostname value"""
    template = {"Hostname": "a" * 64}
    template.update(json.loads(good_virtual_disk_template()))
    try:
        ister.validate_template(template)
    except Exception:
        raise Exception("Valid hostname failed to parse")


def validate_hostname_bad():
    """Bad hostname value"""
    exception_flag = False
    template = {"Hostname": "a" * 256}
    template.update(json.loads(good_virtual_disk_template()))
    try:
        ister.validate_template(template)
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("Invalid hostname parsed")


def validate_static_ip_good():
    """Good static configuration"""
    template = {"Static_IP": {"address": "10.0.2.17/24",
                              "gateway": "10.0.2.2"}}
    template.update(json.loads(good_virtual_disk_template()))
    try:
        ister.validate_template(template)
    except Exception:
        raise Exception("Valid static ip configuration failed to parse")


def validate_static_ip_good_with_dns():
    """Good static configuration with dns"""
    template = {"Static_IP": {"address": "10.0.2.17/24",
                              "gateway": "10.0.2.2",
                              "dns": "10.0.2.3"}}
    template.update(json.loads(good_virtual_disk_template()))
    try:
        ister.validate_template(template)
    except Exception:
        raise Exception("Valid static ip configuration (+DNS) "
                        "failed to parse")


def validate_static_ip_good_with_dns_equals_to_address():
    """Good static configuration with dns equals to address"""
    template = {"Static_IP": {"address": "10.0.2.17/24",
                              "gateway": "10.0.2.2",
                              "dns": "10.0.2.17"}}
    template.update(json.loads(good_virtual_disk_template()))
    try:
        ister.validate_template(template)
    except Exception:
        raise Exception("Valid static ip configuration (+DNS=address) "
                        "failed to parse")


def validate_static_ip_good_with_dns_equals_to_gateway():
    """Good static configuration with dns equals to gateway"""
    template = {"Static_IP": {"address": "10.0.2.17/24",
                              "gateway": "10.0.2.2",
                              "dns": "10.0.2.2"}}
    template.update(json.loads(good_virtual_disk_template()))
    try:
        ister.validate_template(template)
    except Exception:
        raise Exception("Valid static ip configuration (+DNS=gateway) "
                        "failed to parse")


def validate_static_ip_bad_missing_address():
    """Bad static configuration, missing address"""
    exception_flag = False
    template = {"Static_IP": {"gateway": "10.0.2.17",
                              "dns": "10.0.2.3"}}
    template.update(json.loads(good_virtual_disk_template()))
    try:
        ister.validate_template(template)
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("Missing address in static configuration")


def validate_static_ip_bad_missing_gateway():
    """Bad static configuration, missing gateway"""
    exception_flag = False
    template = {"Static_IP": {"address": "10.0.2.17/24",
                              "dns": "10.0.2.3"}}
    template.update(json.loads(good_virtual_disk_template()))
    try:
        ister.validate_template(template)
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("Missing gateway in static configuration")


def validate_static_ip_bad_missing_mask():
    """Bad static configuration, missing mask"""
    exception_flag = False
    template = {"Static_IP": {"address": "10.0.2.17",
                              "gateway": "10.0.2.1",
                              "dns": "10.0.2.3"}}
    template.update(json.loads(good_virtual_disk_template()))
    try:
        ister.validate_template(template)
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("Missing mask in static configuration")


def validate_static_ip_bad_invalid_format_address():
    """Bad static configuration, invalid format address"""
    exception_flag = False
    template = {"Static_IP": {"address": "10.0.1000.17/24",
                              "gateway": "10.0.2.1",
                              "dns": "10.0.2.3"}}
    template.update(json.loads(good_virtual_disk_template()))
    try:
        ister.validate_template(template)
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("Invalid format address in static configuration")


def validate_static_ip_bad_invalid_format_gateway():
    """Bad static configuration, invalid format gateway"""
    exception_flag = False
    template = {"Static_IP": {"address": "10.0.1000.17/24",
                              "gateway": "10.0.a.1",
                              "dns": "10.0.2.3"}}
    template.update(json.loads(good_virtual_disk_template()))
    try:
        ister.validate_template(template)
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("Invalid format gateway in static configuration")


def validate_static_ip_bad_invalid_format_dns():
    """Bad static configuration, invalid format address"""
    exception_flag = False
    template = {"Static_IP": {"address": "10.0.1000.17/24",
                              "gateway": "10.0.2.1",
                              "dns": "10.0.3"}}
    template.update(json.loads(good_virtual_disk_template()))
    try:
        ister.validate_template(template)
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("Invalid format dns in static configuration")


def validate_static_ip_bad_repeated_values():
    """Bad static configuration with repeated values"""
    exception_flag = False
    template = {"Static_IP": {"address": "10.0.2.17/24",
                              "gateway": "10.0.2.17",
                              "dns": "10.0.2.3"}}
    template.update(json.loads(good_virtual_disk_template()))
    try:
        ister.validate_template(template)
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("Repeated values in static configuration")


def validate_partition_mounts_good():
    """Good validate_partition_mounts"""
    template = {"PartitionMountPoints": [{"disk": "sda", "partition": 1,
                                          "mount": "/boot"},
                                         {"disk": "sda", "partition": 2,
                                          "mount": "/"}]}
    partition_fstypes = set(["sda1", "sda2"])
    try:
        ister.validate_partition_mounts(template, partition_fstypes)
    except Exception:
        raise Exception("Valid template failed to parse")


def validate_partition_mounts_good_missing_boot_virtual():
    """Good validate_partition_mounts missing boot partition on virtual"""
    template = {"PartitionMountPoints": [{"disk": "sda", "partition": 1,
                                          "mount": "/"}],
                "DestinationType": "virtual"}
    partition_fstypes = set(["sda1"])
    try:
        ister.validate_partition_mounts(template, partition_fstypes)
    except Exception:
        raise Exception("Valid template failed to parse")


def validate_partition_mounts_good_missing_boot():
    """Good validate_partition_mounts missing boot partition (mbr type)"""
    template = {"PartitionMountPoints": [{"disk": "sda", "partition": 1,
                                          "mount": "/"}],
                "DestinationType": "virtual",
                "LegacyBios": True}
    partition_fstypes = set(["sda1"])
    try:
        ister.validate_partition_mounts(template, partition_fstypes)
    except Exception:
        raise Exception("Valid template failed to parse")


def validate_partition_mounts_bad_missing_disk():
    """Bad validate_partition_mounts missing disk"""
    exception_flag = False
    template = {"PartitionMountPoints": [{"partition": 1, "mount": "/boot"}]}
    try:
        ister.validate_partition_mounts(template, None)
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("missing disk not detected")


def validate_partition_mounts_bad_missing_partition():
    """Bad validate_partition_mounts missing partition"""
    exception_flag = False
    template = {"PartitionMountPoints": [{"disk": "sda", "mount": "/boot"}]}
    try:
        ister.validate_partition_mounts(template, None)
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("missing partition not detected")


def validate_partition_mounts_bad_missing_mount():
    """Bad validate_partition_mounts missing mount"""
    exception_flag = False
    template = {"PartitionMountPoints": [{"partition": 1, "disk": "sda"}]}
    try:
        ister.validate_partition_mounts(template, None)
    except Exception:
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
    except Exception:
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
    partition_fstypes = set(["sda1"])
    try:
        ister.validate_partition_mounts(template, partition_fstypes)
    except Exception:
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
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect invalid partition usage")


def validate_partition_mounts_bad_missing_boot():
    """Bad validate_partition_mounts missing boot partition"""
    exception_flag = False
    template = {"PartitionMountPoints": [{"disk": "sda", "partition": 1,
                                          "mount": "/"}],
                "LegacyBios": False}
    partition_fstypes = set(["sda1"])
    try:
        ister.validate_partition_mounts(template, partition_fstypes)
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect missing boot partition")


def validate_partition_mounts_bad_missing_root():
    """Bad validate_partition_mounts missing '/' partition"""
    exception_flag = False
    template = {"PartitionMountPoints": [{"disk": "sda", "partition": 1,
                                          "mount": "/boot"}]}
    partition_fstypes = set(["sda1"])
    try:
        ister.validate_partition_mounts(template, partition_fstypes)
    except Exception:
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
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect invalid template type")


def validate_user_template_good():
    """Good validate_user_template with sudo active"""
    template = [{"username": "user", "uid": "1000", "sudo": True,
                 "key": "{}/key.pub".format(os.getcwd()),
                 "password": "test"}]
    ister.validate_user_template(template)


def validate_user_template_good_no_sudo():
    """Good validate_user_template with sudo inactive"""
    template = [{"username": "user", "uid": "1000", "sudo": False,
                 "key": "{}/key.pub".format(os.getcwd())}]
    ister.validate_user_template(template)


def validate_user_template_good_key_missing_password():
    """Good validate_user_template with key and missing password"""
    template = [{"username": "user", "uid": "1000", "sudo": True,
                 "key": "{}/key.pub".format(os.getcwd())}]
    ister.validate_user_template(template)


def validate_user_template_bad_missing_name():
    """Bad validate_user_template missing username"""
    exception_flag = False
    template = [{"uid": "1000", "sudo": True}]
    try:
        ister.validate_user_template(template)
    except Exception:
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
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect duplicate username")


def validate_user_template_bad_missing_password():
    """Bad validate_user_template missing password"""
    exception_flag = False
    template = [{"username": "user", "uid": "1000", "sudo": True}]
    try:
        ister.validate_user_template(template)
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception('Failed to detect missing password')


def validate_user_template_bad_duplicate_uid():
    """Bad validate_user_template duplicate uid"""
    exception_flag = False
    template = [{"username": "user", "uid": "1000", "sudo": True},
                {"username": "usertwo", "uid": "1000", "sudo": True}]
    try:
        ister.validate_user_template(template)
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect duplicate uid")


def validate_user_template_bad_invalid_uid_low():
    """Bad validate_user_template invalid uid (0)"""
    exception_flag = False
    template = [{"username": "user", "uid": "0", "sudo": True}]
    try:
        ister.validate_user_template(template)
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect invalid uid (0)")


def validate_user_template_bad_invalid_uid_high():
    """Bad validate_user_template invalid uid (> uint32 max)"""
    exception_flag = False
    template = [{"username": "user", "uid": "4294967296", "sudo": True}]
    try:
        ister.validate_user_template(template)
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect invalid uid (> uint32 max)")


def validate_user_template_bad_invalid_sudo():
    """Bad validate_user_template invalid sudo option"""
    exception_flag = False
    template = [{"username": "user", "uid": "1000", "sudo": "bad"}]
    try:
        ister.validate_user_template(template)
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect invalid sudo option")


def validate_user_template_bad_missing_key():
    """Bad validate_user_template missing key file"""
    exception_flag = False
    template = [{"username": "user", "uid": "1000", "sudo": True,
                 "key": "/does/not/exist"}]
    try:
        ister.validate_user_template(template)
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect missing key file")


def validate_postnonchroot_template_good():
    """Good validate postnonchroot template"""
    global COMMAND_RESULTS
    COMMAND_RESULTS = []
    backup_isfile = os.path.isfile

    def mock_isfile(path):
        """mock_isfile wrapper"""
        COMMAND_RESULTS.append(path)
        return True
    os.path.isfile = mock_isfile
    commands = ["file1", "file2"]
    ister.validate_postnonchroot_template([])
    ister.validate_postnonchroot_template(commands)
    os.path.isfile = backup_isfile
    commands_compare_helper(commands)


def validate_postnonchroot_template_bad():
    """Bad validate postnonchroot template"""
    global COMMAND_RESULTS
    COMMAND_RESULTS = []
    backup_isfile = os.path.isfile
    exception_flag = False

    def mock_isfile(path):
        """mock_isfile wrapper"""
        COMMAND_RESULTS.append(path)
        return False
    os.path.isfile = mock_isfile
    commands = ["file1"]
    try:
        ister.validate_postnonchroot_template(commands)
    except Exception:
        exception_flag = True
    os.path.isfile = backup_isfile
    if not exception_flag:
        raise Exception("Failed to detect missing script file")


def validate_proxy_url_template_good():
    ister.validate_proxy_url_template("http://proxy.clear.com")
    ister.validate_proxy_url_template("https://proxy.clear.com")
    ister.validate_proxy_url_template("https://example.co")


def validate_proxy_url_template_bad():
    error = []
    try:
        ister.validate_proxy_url_template("httpproxy.clear.com")
        error.append("httpproxy.clear.com")
    except:
        pass

    try:
        ister.validate_proxy_url_template("not a url")
        error.append("not a url")
    except:
        pass

    try:
        ister.validate_proxy_url_template("clear.com")
        error.append("clear.com")
    except:
        pass

    if error:
        raise Exception("Incorrectly validated the following url(s): "
                        "{}".format(", ".join(error)))


def validate_template_good():
    """Good validate_template"""
    template = json.loads(good_virtual_disk_template())
    ister.validate_template(template)


def validate_template_latest_good():
    """Good validate_template"""
    template = json.loads(good_latest_template())
    ister.validate_template(template)


def validate_template_good_disable_partitioning():
    """Good validate tamplate without creating new partitions"""
    template = json.loads(good_virtual_disk_template())
    template['DisabledNewPartitions'] = True
    ister.validate_template(template)


def validate_template_bad_long_hostname():
    """Bad validate_template long hostname (Length > 255)"""
    exception_flag = False
    template = {"Hostname": ("a" * 256)}
    template.update(json.loads(good_virtual_disk_template()))
    try:
        ister.validate_template(template)
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to validate hostname max length")


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
    except Exception:
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
    except Exception:
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
    except Exception:
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
    except Exception:
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
    except Exception:
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
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect missing Version")


def validate_template_bad_short_hostname():
    """Bad validate_template short hostname (length = 0)"""
    exception_flag = False
    template = {"Hostname": ""}
    template.update(json.loads(good_virtual_disk_template()))
    try:
        ister.validate_template(template)
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to validate hostname minimum length")


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
    except Exception:
        exception_flag = True
    if not exception_flag:
        raise Exception("Failed to detect bad Version")


def parse_config_good():
    """Positive tests for configuration parsing"""
    # pylint: pylint: disable=R0914
    global COMMAND_RESULTS
    COMMAND_RESULTS = []
    backup_isfile = os.path.isfile
    backup_get_template_location = ister.get_template_location
    backup_check_kernel_cmdline = ister.check_kernel_cmdline

    def mock_isfile_true_etc(path):
        """mock_isfile_true_etc wrapper"""
        COMMAND_RESULTS.append(path)
        if path.startswith("/etc"):
            return True
        return False

    def mock_isfile_true_usr(path):
        """mock_isfile_true_usr wrapper"""
        COMMAND_RESULTS.append(path)
        if path.startswith("/usr"):
            return True
        return False

    def mock_isfile_false(path):
        """mock_isfile_false wrapper"""
        COMMAND_RESULTS.append(path)
        return False

    def mock_get_template_location_etc(path):
        """mock_get_template_location_etc wrapper"""
        COMMAND_RESULTS.append(path)
        return "file:///etc.json"

    def mock_get_template_location_usr(path):
        """mock_get_template_location_usr wrapper"""
        COMMAND_RESULTS.append(path)
        return "file:///usr.json"

    def mock_get_template_location_cmd(path):
        """mock_get_template_location_cmd wrapper"""
        COMMAND_RESULTS.append(path)
        return "file:///cmd.json"

    def mock_get_template_location_tmp(path):
        """mock_get_template_location_cmd wrapper"""
        COMMAND_RESULTS.append(path)
        return "http://pxeserver/config.json"

    def mock_check_kernel_cmdline_no(path, sleep_time=1):
        """mock_check_kernel_cmdline wrapper"""
        # COMMAND_RESULTS.append("no_kcmdline")
        return False, ""

    def mock_check_kernel_cmdline_yes(path, sleep_time=1):
        """mock_check_kernel_cmdline wrapper"""
        COMMAND_RESULTS.append(path)
        return True, "/tmp/abcxyz"

    try:

        def args():
            """args empty object"""
            None
        args.kcmdline = "/proc/cmdline_yes_ister_conf"
        args.config_file = None
        args.template_file = None
        # Check config from kernel command line/network
        ister.check_kernel_cmdline = mock_check_kernel_cmdline_yes
        ister.get_template_location = mock_get_template_location_tmp
        config = ister.parse_config(args)
        commands = ["/proc/cmdline_yes_ister_conf", "/tmp/abcxyz"]
        commands_compare_helper(commands)
        if config["template"] != "http://pxeserver/config.json":
            raise Exception("kernel cmdline template does not "
                            "match expected value")
        # Check config from default ister.conf in etc
        COMMAND_RESULTS = []
        ister.check_kernel_cmdline = mock_check_kernel_cmdline_no
        os.path.isfile = mock_isfile_true_etc
        ister.get_template_location = mock_get_template_location_etc
        config = ister.parse_config(args)
        commands = ["/etc/ister.conf", "/etc/ister.conf"]
        commands_compare_helper(commands)
        if config["template"] != "file:///etc.json":
            raise Exception("etc template does not match expected value")
        # Check config from ister.conf in /usr/share/defaults
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
        # See if template file was given on command line
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
        ister.check_kernel_cmdline = backup_check_kernel_cmdline


def parse_config_bad():
    """Negative tests for configuration parsing"""
    exception_flag = False

    def mock_isfile_false(path):
        """mock_isfile_false wrapper"""
        COMMAND_RESULTS.append(path)
        return False

    backup_isfile = os.path.isfile
    os.path.isfile = mock_isfile_false

    try:
        def args():
            """args empty object"""
            None
        args.config_file = None
        args.template_file = None
        args.kcmdline = "/proc/no_isterconf"
        ister.parse_config(args)
    except Exception:
        exception_flag = True
    finally:
        os.path.isfile = backup_isfile
    if not exception_flag:
        raise Exception("Failed to detect missing configuration file")


def handle_options_good():
    """Test all values handle options supports"""
    # Test short options first
    sys.argv = ["ister.py", "-c", "cfg", "-t", "tpt", "-C", "/", "-V", "/",
                "-f", "1", "-v", "-l", "log", "-L", "debug", "-S", "/"]
    try:
        args = ister.handle_options()
    except Exception:
        raise Exception("Unable to parse short arguments")
    if args.config_file != "cfg":
        raise Exception("Failed to correctly set short config file")
    if args.template_file != "tpt":
        raise Exception("Failed to correctly set short template file")
    if args.contenturl != "/":
        raise Exception("Failed to correctly set short contenturl")
    if args.versionurl != "/":
        raise Exception("Failed to correctly set short versionurl")
    if args.format != "1":
        raise Exception("Failed to correctly set short format")
    if args.verbose is not True:
        raise Exception("Failed to correctly set short verbose")
    if args.logfile != "log":
        raise Exception("Failed to correctly set short logfile")
    if args.loglevel != "debug":
        raise Exception("Failed to correctly set short loglevel")
    if args.statedir != "/":
        raise Exception("Failed to correctly set short state dir")
    # Test long options next
    sys.argv = ["ister.py", "--config-file=cfg", "--template-file=tpt",
                "--contenturl=/", "--versionurl=/", "--format=1", "--verbose",
                "--logfile=log", "--loglevel=debug", "--statedir=/"]
    try:
        args = ister.handle_options()
    except Exception:
        raise Exception("Unable to parse long arguments")
    if args.config_file != "cfg":
        raise Exception("Failed to correctly set long config file")
    if args.template_file != "tpt":
        raise Exception("Failed to correctly set long template file")
    if args.contenturl != "/":
        raise Exception("Failed to correctly set long contenturl")
    if args.versionurl != "/":
        raise Exception("Failed to correctly set long versionurl")
    if args.format != "1":
        raise Exception("Failed to correctly set long format")
    if args.verbose is not True:
        raise Exception("Failed to correctly set long verbose")
    if args.logfile != "log":
        raise Exception("Failed to correctly set long logfile")
    if args.loglevel != "debug":
        raise Exception("Failed to correctly set long loglevel")
    if args.statedir != "/":
        raise Exception("Failed to correctly set long state dir")
    # Test default options
    sys.argv = ["ister.py"]
    try:
        args = ister.handle_options()
    except Exception:
        raise Exception("Unable to parse default arguments")
    if args.config_file:
        raise Exception("Incorrect default config file set")
    if args.template_file:
        raise Exception("Incorrect default template file set")
    if args.contenturl != "https://download.clearlinux.org/update":
        raise Exception("Incorrect default contenturl set")
    if args.versionurl != "https://download.clearlinux.org/update":
        raise Exception("Incorrect default versionurl set")
    if args.format:
        raise Exception("Incorrect default format set")
    if args.verbose:
        raise Exception("Incorrect default verbose set")
    if args.logfile != "/var/log/ister.log":
        raise Exception("Incorrect default logfile set")
    if args.loglevel != "info":
        raise Exception("Incorrect default loglevel set")
    if args.statedir != "/var/lib/swupd":
        raise Exception("Incorrect default state dir set")


def handle_logging_good():
    """Test handle_logging"""

    class MockOpen():
        """Simple handling of open for logging"""
        def __init__(self, file, *_, **__):
            """set name for testing"""
            del __
            self.name = file

        def close(self):
            """mock close operation"""
            pass

    backup_open = __builtins__.open
    __builtins__.open = MockOpen
    backup_log = ister.LOG
    ister.LOG = ister.logging.getLogger("test")
    try:
        # Test for info level and logfile
        ister.handle_logging("info", "log")
        if len(ister.LOG.handlers) != 2:
            raise Exception("Incorrect handler numbers")
        if ister.LOG.handlers[1].stream.name.split('/')[-1] != "log":
            raise Exception("Incorrect logfile name")
        if ister.LOG.handlers[0].level != ister.logging.INFO:
            raise Exception("Incorrect logging level for info level")
        # Test for debug level
        ister.LOG.handlers = []
        ister.handle_logging("debug", "log")
        if ister.LOG.handlers[0].level != ister.logging.DEBUG:
            raise Exception("Incorrect logging level for debug level")
        # Test for error level
        ister.LOG.handlers = []
        ister.handle_logging("error", "log")
        if ister.LOG.handlers[0].level != ister.logging.ERROR:
            raise Exception("Incorrect logging level for error level")
    except Exception as exep:
        raise exep
    finally:
        __builtins__.open = backup_open
        ister.LOG = backup_log


@run_command_wrapper
def validate_network_good():
    """Test validate_network"""

    def mock_request_urlopen(url, **_):
        """mock handling urlopen"""
        COMMAND_RESULTS.append(url)

    urlopen_orig = request.urlopen
    request.urlopen = mock_request_urlopen

    url = "https://update.clearlinux.org"
    commands = [url]
    try:
        ister.validate_network(url)
    except Exception as exep:
        raise exep
    finally:
        request.urlopen = urlopen_orig
    commands_compare_helper(commands)


def validate_network_bad():
    """Test validate_network with bad URL"""
    exception_flag = False

    def mock_request_urlopen(_, **__):
        """mock urlopen with an error code"""
        del __
        exep = ister.URLError("Could not reach host")
        exep.code = 1
        raise exep

    urlopen_orig = request.urlopen
    request.urlopen = mock_request_urlopen

    url = "https://bad.url"
    try:
        ister.validate_network(url)
    except Exception as _:
        exception_flag = True
    finally:
        request.urlopen = urlopen_orig
    if not exception_flag:
        raise Exception("Failed to fail getting bad url")


@urlopen_wrapper("good", "baz")
@fdopen_wrapper("good", "")
@open_wrapper("good", "bar isterconf=http://localhost/")
def check_kernel_cmdline_good():
    """ If isterconf is on kernel command line, detect and fetch
    """
    global COMMAND_RESULTS
    COMMAND_RESULTS = []

    def mock_mkstemp():
        """ works as intended """
        COMMAND_RESULTS.append("mkstemp")
        return 42, "/tmp/xyzzy"

    def mock_copyfileobj(a, b):
        """ breadcrumbs for file copy """
        COMMAND_RESULTS.append(a.read())
        COMMAND_RESULTS.append(b.read())

    def mock_os_unlink(path):
        """ breadcrumb for os.unlink """
        COMMAND_RESULTS.append("unlink_{0}".format(path))

    mkstemp_orig = tempfile.mkstemp
    cfo_orig = shutil.copyfileobj
    unlink_orig = os.unlink

    tempfile.mkstemp = mock_mkstemp
    shutil.copyfileobj = mock_copyfileobj
    os.unlink = mock_os_unlink
    commands = []

    try:
        ister.check_kernel_cmdline("foo", sleep_time=0)
    except Exception as exep:
        raise exep
    finally:
        tempfile.mkstemp = mkstemp_orig
        shutil.copyfileobj = cfo_orig
        os.unlink = unlink_orig

    commands = ['foo', 'r', 'read', 'mkstemp',
                'http://localhost/', 42, 'wb', 'read',
                'baz', 'read', '', 'close']
    commands_compare_helper(commands)


@urlopen_wrapper("good", "baz")
@fdopen_wrapper("good", "")
@open_wrapper("good", "bar x y z")
def check_kernel_cmdline_bad_no_isterconf():
    """ If isterconf not on kernel command line, do nothing
    """
    global COMMAND_RESULTS
    COMMAND_RESULTS = []

    def mock_mkstemp():
        """ works as intended """
        COMMAND_RESULTS.append("mkstemp")
        return 42, "/tmp/xyzzy"

    def mock_copyfileobj(a, b):
        """ breadcrumbs for file copy """
        COMMAND_RESULTS.append(a.read())
        COMMAND_RESULTS.append(b.read())

    def mock_os_unlink(path):
        """ breadcrumb for os.unlink """
        COMMAND_RESULTS.append("unlink_{0}".format(path))

    mkstemp_orig = tempfile.mkstemp
    cfo_orig = shutil.copyfileobj
    unlink_orig = os.unlink

    tempfile.mkstemp = mock_mkstemp
    shutil.copyfileobj = mock_copyfileobj
    os.unlink = mock_os_unlink

    try:
        ister.check_kernel_cmdline("foo", sleep_time=0)
    except Exception as exep:
        raise exep
    finally:
        tempfile.mkstemp = mkstemp_orig
        shutil.copyfileobj = cfo_orig
        os.unlink = unlink_orig

    commands = ['foo', 'r', 'read']
    commands_compare_helper(commands)


@urlopen_wrapper("bad", "baz")
@fdopen_wrapper("good", "")
@open_wrapper("good", "bar isterconf=http://localhost/")
def check_kernel_cmdline_bad_urlopen_fails():
    """ If url given to isterconf param is bad, exception is raised.
    """
    global COMMAND_RESULTS
    COMMAND_RESULTS = []

    def mock_mkstemp():
        """ works as intended """
        COMMAND_RESULTS.append("mkstemp")
        return 42, "/tmp/xyzzy"

    def mock_copyfileobj(a, b):
        """ breadcrumbs for file copy """
        COMMAND_RESULTS.append(a.read())
        COMMAND_RESULTS.append(b.read())

    def mock_os_unlink(path):
        """ breadcrumb for os.unlink """
        COMMAND_RESULTS.append("unlink_{0}".format(path))

    mkstemp_orig = tempfile.mkstemp
    cfo_orig = shutil.copyfileobj
    unlink_orig = os.unlink

    tempfile.mkstemp = mock_mkstemp
    shutil.copyfileobj = mock_copyfileobj
    os.unlink = mock_os_unlink

    try:
        ister.check_kernel_cmdline("foo", sleep_time=0)
    except:
        exception_flag = True
    finally:
        tempfile.mkstemp = mkstemp_orig
        shutil.copyfileobj = cfo_orig
        os.unlink = unlink_orig
    if not exception_flag:
        raise Exception("Failed to fail getting bad url")


@urlopen_wrapper("good", "baz")
@fdopen_wrapper("bad", "")
@open_wrapper("good", "bar isterconf=http://localhost/")
def check_kernel_cmdline_bad_fdopen_fails():
    """ Exception raised if result of mkstemp can't be opened.
    """
    global COMMAND_RESULTS
    COMMAND_RESULTS = []

    def mock_mkstemp():
        """ works as intended """
        COMMAND_RESULTS.append("mkstemp")
        return 42, "/tmp/xyzzy"

    def mock_copyfileobj(a, b):
        """ breadcrumbs for file copy """
        COMMAND_RESULTS.append(a.read())
        COMMAND_RESULTS.append(b.read())

    def mock_os_unlink(path):
        """ breadcrumb for os.unlink """
        COMMAND_RESULTS.append("unlink_{0}".format(path))

    mkstemp_orig = tempfile.mkstemp
    cfo_orig = shutil.copyfileobj
    unlink_orig = os.unlink

    tempfile.mkstemp = mock_mkstemp
    shutil.copyfileobj = mock_copyfileobj
    os.unlink = mock_os_unlink

    try:
        ister.check_kernel_cmdline("foo", sleep_time=0)
    except:
        exception_flag = True
    finally:
        tempfile.mkstemp = mkstemp_orig
        shutil.copyfileobj = cfo_orig
        os.unlink = unlink_orig
    if not exception_flag:
        raise Exception("Failed to fail on fdopen")


def get_host_from_url_good_1():
    """ Validate hostname from valid url
    """
    host = ister.get_host_from_url("http://localhost/")
    if host != "localhost":
        raise Exception("Failed to parse hostname")


def get_host_from_url_good_2():
    """ Validate hostname from url with port
    """
    host = ister.get_host_from_url("http://localhost:5000/")
    if host != "localhost":
        raise Exception("Failed to parse hostname")


def get_host_from_url_bad_malformed_url():
    """ Exception raised if bad url given
    """
    host = ister.get_host_from_url("not_a_url")
    if host is not None:
        raise Exception("Invalid url-derived hostname")


def get_iface_for_host_good():
    """ Validate we find net device used to reach icis service
    """
    def mock_gethostbyname(host):
        """ yield ip addr """
        return "192.168.1.1"

    def mock_run_command(cmd):
        """ yield result of ip show route... """
        return ["default via 192.168.1.1 dev enp0s25 proto "
                "static metric 600"], 0

    gethostbyname_orig = socket.gethostbyname
    run_command_orig = ister.run_command
    socket.gethostbyname = mock_gethostbyname
    ister.run_command = mock_run_command

    iface = ister.get_iface_for_host("hostname")

    socket.get_hostbyname = gethostbyname_orig
    ister.run_command = run_command_orig

    if iface != "enp0s25":
        raise Exception("Failed to find outbound interface to "
                        "cloud-init-config server")


def get_iface_for_host_bad_no_route():
    """ Gracefully handle no route scenario
    """
    def mock_gethostbyname(host):
        """ yield ip addr """
        return "192.168.1.1"

    def mock_run_command(cmd):
        """ ip show route runs into error """
        return ["error"], 1

    gethostbyname_orig = socket.gethostbyname
    run_command_orig = ister.run_command
    socket.gethostbyname = mock_gethostbyname
    ister.run_command = mock_run_command

    iface = ister.get_iface_for_host("hostname")

    socket.get_hostbyname = gethostbyname_orig
    ister.run_command = run_command_orig

    if iface is not None:
        raise Exception("Did not return None for bad route")


def get_iface_for_host_bad_hostname():
    """ Gracefully handle bad hostname scenario
    """
    def mock_gethostbyname(host):
        """ invalid hostname... """
        return ""

    def mock_run_command(cmd):
        """ Result of ip show route on empty host... """
        return ["Error: an inet prefix is expected rather than \"\"."], 1

    gethostbyname_orig = socket.gethostbyname
    run_command_orig = ister.run_command
    socket.gethostbyname = mock_gethostbyname
    ister.run_command = mock_run_command

    iface = ister.get_iface_for_host("hostname")

    socket.get_hostbyname = gethostbyname_orig
    ister.run_command = run_command_orig

    if iface is not None:
        raise Exception("Did not return None for bad hostname")


def get_mac_for_iface_good():
    """ Obtain mac address of valid network interface
    """
    def mock_ifaddresses(iface):
        """ Good line for net device """
        return {17: [{'addr': 'aa:bb:cc:dd:ee:ff',
                      'broadcast': 'ff:ff:ff:ff:ff:ff'}]}

    ifaddresses_orig = netifaces.ifaddresses
    netifaces.ifaddresses = mock_ifaddresses

    mac = ister.get_mac_for_iface("net_device")

    netifaces.ifaddresses = ifaddresses_orig

    if mac != "aa:bb:cc:dd:ee:ff":
        raise Exception("Failed to find MAC for network interface")


def get_mac_for_iface_bad():
    """ Validate bad network interface scenario does not yield MAC addr
    """
    def mock_ifaddresses_bad(iface):
        """ Tried to get info for invalid net device """
        raise Exception("You must specify a valid interface name..")

    ifaddresses_orig = netifaces.ifaddresses
    netifaces.ifaddresses = mock_ifaddresses_bad

    mac = ister.get_mac_for_iface("net_device")

    netifaces.ifaddresses = ifaddresses_orig

    if mac is not None:
        raise Exception("Did not get None for invalid interface")


@urlopen_wrapper("good", b'{"mac": "default", "role": "compute"}')
def fetch_cloud_init_configs_good():
    """ Validate we handle valid json being returned
    """
    global COMMAND_RESULTS
    COMMAND_RESULTS = []

    pyobj_from_json = ister.fetch_cloud_init_configs("url", "mac")

    commands = ["urlget_config/mac", "read"]
    commands_compare_helper(commands)

    role = pyobj_from_json.get('role')

    if role != "compute":
        raise Exception("Expected role 'compute', got {0}".format(role))


@urlopen_wrapper("bad", b'{"mac": "default", "role": "compute"}')
def fetch_cloud_init_configs_bad_urlopen():
    """ urlopen failure returns "none"
    """
    pyobj_from_json = ister.fetch_cloud_init_configs("url", "mac")

    role = pyobj_from_json.get('role')

    if role is not None:
        raise Exception("Unexpectedly found role {0}".format(role))


def get_cloud_init_configs_good():
    """ Do we get a userdata file if everything is good?
    """
    def mock_get_host_from_url(icis_source):
        """ stub """
        return "host"

    def mock_get_iface_for_host(host):
        """ stub """
        return "iface"

    def mock_get_mac_for_iface(iface):
        """ stub """
        return "mac"

    def mock_fetch_cloud_init_configs(icis_source, mac):
        """ stub """
        return "good_configs"

    get_host_from_url_orig = ister.get_host_from_url
    get_iface_for_host_orig = ister.get_iface_for_host
    get_mac_for_iface_orig = ister.get_mac_for_iface
    fetch_cloud_init_configs_orig = ister.fetch_cloud_init_configs

    ister.get_host_from_url = mock_get_host_from_url
    ister.get_iface_for_host = mock_get_iface_for_host
    ister.get_mac_for_iface = mock_get_mac_for_iface
    ister.fetch_cloud_init_configs = mock_fetch_cloud_init_configs

    confs = ister.get_cloud_init_configs("source")

    ister.get_host_from_url = get_host_from_url_orig
    ister.get_iface_for_host = get_iface_for_host_orig
    ister.get_mac_for_iface = get_mac_for_iface_orig
    ister.fetch_cloud_init_configs = fetch_cloud_init_configs_orig

    if confs != "good_configs":
        raise Exception("Failed to get good configs")


def get_cloud_init_configs_bad_url_has_no_host():
    """ if get_host_from_url has problems, we should get None
    """
    def mock_get_host_from_url(icis_source):
        """ failed to get host from url """
        return None

    def mock_get_iface_for_host(host):
        """ stub """
        return "iface"

    def mock_get_mac_for_iface(iface):
        """ stub """
        return "mac"

    def mock_fetch_cloud_init_configs(icis_source, mac):
        """ stub """
        return "good_configs"

    get_host_from_url_orig = ister.get_host_from_url
    get_iface_for_host_orig = ister.get_iface_for_host
    get_mac_for_iface_orig = ister.get_mac_for_iface
    fetch_cloud_init_configs_orig = ister.fetch_cloud_init_configs

    ister.get_host_from_url = mock_get_host_from_url
    ister.get_iface_for_host = mock_get_iface_for_host
    ister.get_mac_for_iface = mock_get_mac_for_iface
    ister.fetch_cloud_init_configs = mock_fetch_cloud_init_configs

    confs = ister.get_cloud_init_configs("source")

    ister.get_host_from_url = get_host_from_url_orig
    ister.get_iface_for_host = get_iface_for_host_orig
    ister.get_mac_for_iface = get_mac_for_iface_orig
    ister.fetch_cloud_init_configs = fetch_cloud_init_configs_orig

    if confs is not None:
        raise Exception("Got confs from bad host")


def get_cloud_init_configs_bad_no_route_to_host():
    """ If get_iface_for_host runs into trouble, we should get None
    """
    def mock_get_host_from_url(icis_source):
        """ stub """
        return "host"

    def mock_get_iface_for_host(host):
        """ failed to get a valid Interface """
        return None

    def mock_get_mac_for_iface(iface):
        """ stub """
        return "mac"

    def mock_fetch_cloud_init_configs(icis_source, mac):
        """ stub """
        return "good_configs"

    get_host_from_url_orig = ister.get_host_from_url
    get_iface_for_host_orig = ister.get_iface_for_host
    get_mac_for_iface_orig = ister.get_mac_for_iface
    fetch_cloud_init_configs_orig = ister.fetch_cloud_init_configs

    ister.get_host_from_url = mock_get_host_from_url
    ister.get_iface_for_host = mock_get_iface_for_host
    ister.get_mac_for_iface = mock_get_mac_for_iface
    ister.fetch_cloud_init_configs = mock_fetch_cloud_init_configs

    confs = ister.get_cloud_init_configs("source")

    ister.get_host_from_url = get_host_from_url_orig
    ister.get_iface_for_host = get_iface_for_host_orig
    ister.get_mac_for_iface = get_mac_for_iface_orig
    ister.fetch_cloud_init_configs = fetch_cloud_init_configs_orig

    if confs is not None:
        raise Exception("Got confs from unreachable host")


def get_cloud_init_configs_bad_iface():
    """ 'None' is returned if somehow an invalid net interface is used
    """
    def mock_get_host_from_url(icis_source):
        """ stub """
        return "host"

    def mock_get_iface_for_host(host):
        """ stub """
        return "iface"

    def mock_get_mac_for_iface(iface):
        """ Could not find mac addr of iface """
        return None

    def mock_fetch_cloud_init_configs(icis_source, mac):
        """ stub """
        return "good_configs"

    get_host_from_url_orig = ister.get_host_from_url
    get_iface_for_host_orig = ister.get_iface_for_host
    get_mac_for_iface_orig = ister.get_mac_for_iface
    fetch_cloud_init_configs_orig = ister.fetch_cloud_init_configs

    ister.get_host_from_url = mock_get_host_from_url
    ister.get_iface_for_host = mock_get_iface_for_host
    ister.get_mac_for_iface = mock_get_mac_for_iface
    ister.fetch_cloud_init_configs = mock_fetch_cloud_init_configs

    confs = ister.get_cloud_init_configs("source")

    ister.get_host_from_url = get_host_from_url_orig
    ister.get_iface_for_host = get_iface_for_host_orig
    ister.get_mac_for_iface = get_mac_for_iface_orig
    ister.fetch_cloud_init_configs = fetch_cloud_init_configs_orig

    if confs is not None:
        raise Exception("Got confs for mac-address \'None\'")


def get_cloud_init_configs_bad_no_configs_for_target():
    """ If no configs exist for the install target, we get 'None'.
    """
    def mock_get_host_from_url(icis_source):
        """ stub """
        return "host"

    def mock_get_iface_for_host(host):
        """ stub """
        return "iface"

    def mock_get_mac_for_iface(iface):
        """ stub """
        return "mac"

    def mock_fetch_cloud_init_configs(icis_source, mac):
        """ Got empty result from ister cloud init svc """
        return dict()

    get_host_from_url_orig = ister.get_host_from_url
    get_iface_for_host_orig = ister.get_iface_for_host
    get_mac_for_iface_orig = ister.get_mac_for_iface
    fetch_cloud_init_configs_orig = ister.fetch_cloud_init_configs

    ister.get_host_from_url = mock_get_host_from_url
    ister.get_iface_for_host = mock_get_iface_for_host
    ister.get_mac_for_iface = mock_get_mac_for_iface
    ister.fetch_cloud_init_configs = mock_fetch_cloud_init_configs

    confs = ister.get_cloud_init_configs("source")

    ister.get_host_from_url = get_host_from_url_orig
    ister.get_iface_for_host = get_iface_for_host_orig
    ister.get_mac_for_iface = get_mac_for_iface_orig
    ister.fetch_cloud_init_configs = fetch_cloud_init_configs_orig

    if len(confs) > 0:
        raise Exception("expected empty dict")


@urlopen_wrapper("good", "cloud-init configs")
@open_wrapper("good", "not_used")
def fetch_cloud_init_role_good():
    """ With everything working, do we get a cloud-init userdata file?
    """
    global COMMAND_RESULTS
    COMMAND_RESULTS = []

    def mock_copyfileobj(a, b):
        """ breadcrumbs for file copy """
        COMMAND_RESULTS.append(a.read())
        COMMAND_RESULTS.append(b.read())

    cfo_orig = shutil.copyfileobj
    shutil.copyfileobj = mock_copyfileobj

    ister.fetch_cloud_init_role("source/", "compute", "/dir")

    shutil.copyfileobj = cfo_orig
    commands = ['source/get_role/compute',
                '/dir/etc/cloud-init-user-data', 'wb', 'read',
                'cloud-init configs', 'read', 'not_used', 'close']
    commands_compare_helper(commands)


@urlopen_wrapper("bad", "cloud-init configs")
@open_wrapper("good", "not_used")
def fetch_cloud_init_role_bad_cannot_open_url():
    """ Should get exception if urlopen runs into problems.
    """
    global COMMAND_RESULTS
    COMMAND_RESULTS = []
    exception_flag = False

    def mock_copyfileobj(a, b):
        """ breadcrumbs for file copy """
        COMMAND_RESULTS.append(a.read())
        COMMAND_RESULTS.append(b.read())

    cfo_orig = shutil.copyfileobj
    shutil.copyfileobj = mock_copyfileobj

    try:
        ister.fetch_cloud_init_role("source/", "compute", "/dir")
    except:
        exception_flag = True

    shutil.copyfileobj = cfo_orig
    commands = []
    commands_compare_helper(commands)
    if not exception_flag:
        raise Exception("bad urlopen did not throw exception")


@urlopen_wrapper("good", "cloud-init configs")
@open_wrapper("bad", "not_used")
def fetch_cloud_init_role_bad_cannot_target_file():
    """ Should get exception if cannot write out userdata file.
    """
    global COMMAND_RESULTS
    COMMAND_RESULTS = []
    exception_flag = False

    def mock_copyfileobj(a, b):
        """ breadcrumbs for file copy """
        COMMAND_RESULTS.append(a.read())
        COMMAND_RESULTS.append(b.read())

    cfo_orig = shutil.copyfileobj
    shutil.copyfileobj = mock_copyfileobj

    try:
        ister.fetch_cloud_init_role("source/", "compute", "/dir")
    except:
        exception_flag = True

    shutil.copyfileobj = cfo_orig
    commands = ["source/get_role/compute"]
    commands_compare_helper(commands)
    if not exception_flag:
        raise Exception("bad open did not throw exception")


@open_wrapper("good", ["line1",
                       "ExecStart=/usr/bin/cloud-init --fix-disk "
                       "--metadata --user-data-once"])
def modify_cloud_init_service_file_good():
    """ For valid systemd unit file - modify to use userdata file
    """
    global COMMAND_RESULTS
    COMMAND_RESULTS = []

    ister.modify_cloud_init_service_file("/dir")
    commands = ["/dir/usr/lib/systemd/system/cloud-init.service", "r",
                "readlines",
                "/dir/usr/lib/systemd/system/cloud-init.service", "w",
                "line1",
                "ExecStart=/usr/bin/cloud-init --fix-disk "
                "--user-data-file /etc/cloud-init-user-data"]
    commands_compare_helper(commands)


@open_wrapper("bad", ["line1", "line2"])
def modify_cloud_init_service_file_bad_open():
    """ Get Exception if can't open systemd unit file
    """
    global COMMAND_RESULTS
    COMMAND_RESULTS = []
    exception_flag = False

    try:
        ister.modify_cloud_init_service_file("/dir")
    except:
        exception_flag = True

    if not exception_flag:
        raise Exception("Open did not throw exception")


def cloud_init_configs_good():
    """ Successfuly fetch/install/configure cloud init configs
    """
    global COMMAND_RESULTS
    COMMAND_RESULTS = []

    def mock_get_cloud_init_configs(source):
        """ breadcrumbs and valid configs """
        COMMAND_RESULTS.append("get_cloud_init_configs")
        return {"mac": "default", "role": "compute"}

    def mock_fetch_cloud_init_role(source, role, target_dir):
        """ breadcrumb stub """
        COMMAND_RESULTS.append("fetch_cloud_init_role")

    def mock_modify_cloud_init_service_file(target_dir):
        """ breadcrumb stub """
        COMMAND_RESULTS.append("modify_cloud_init_service_file")

    template = {"IsterCloudInitSvc": "http://host/icis"}

    gcic_orig = ister.get_cloud_init_configs
    fcir_orig = ister.fetch_cloud_init_role
    mcisf_orig = ister.modify_cloud_init_service_file

    ister.get_cloud_init_configs = mock_get_cloud_init_configs
    ister.fetch_cloud_init_role = mock_fetch_cloud_init_role
    ister.modify_cloud_init_service_file = mock_modify_cloud_init_service_file

    ister.cloud_init_configs(template, "/path")

    ister.get_cloud_init_configs = gcic_orig
    ister.fetch_cloud_init_role = fcir_orig
    ister.modify_cloud_init_service_file = mcisf_orig

    commands = ["get_cloud_init_configs", "fetch_cloud_init_role",
                "modify_cloud_init_service_file"]
    commands_compare_helper(commands)


def cloud_init_configs_good_no_role():
    """ Do nothing if we can't get identify a role for install target
    """
    global COMMAND_RESULTS
    COMMAND_RESULTS = []

    def mock_get_cloud_init_configs(source):
        """ Role missing from result of get_cloud_init_configs """
        COMMAND_RESULTS.append("get_cloud_init_configs")
        return {"mac": "default"}

    def mock_fetch_cloud_init_role(source, role, target_dir):
        """ breadcrumb stub """
        COMMAND_RESULTS.append("fetch_cloud_init_role")

    def mock_modify_cloud_init_service_file(target_dir):
        """ breadcrumb stub """
        COMMAND_RESULTS.append("modify_cloud_init_service_file")

    template = {"IsterCloudInitSvc": "http://host/icis"}

    gcic_orig = ister.get_cloud_init_configs
    fcir_orig = ister.fetch_cloud_init_role
    mcisf_orig = ister.modify_cloud_init_service_file

    ister.get_cloud_init_configs = mock_get_cloud_init_configs
    ister.fetch_cloud_init_role = mock_fetch_cloud_init_role
    ister.modify_cloud_init_service_file = mock_modify_cloud_init_service_file

    ister.cloud_init_configs(template, "/path")

    ister.get_cloud_init_configs = gcic_orig
    ister.fetch_cloud_init_role = fcir_orig
    ister.modify_cloud_init_service_file = mcisf_orig

    commands = ['get_cloud_init_configs']
    commands_compare_helper(commands)


def gui_network_connection():
    """
    Test that network connection can be detected with successful pycurl perform
    """
    import time

    actual = []
    expected = ["https://www.clearlinux.org", 1, 1, 3]

    class mock_pycurl_curl():
        """mock pycurl.Curl class"""
        def __init__(self):
            self.URL = None
            self.HEADER = None
            self.NOBODY = None
            self.WRITEFUNCTION = None
            self.TIMEOUT = None

        def setopt(self, attr, val):
            # Don't copy storage class address
            if isinstance(val, str) or isinstance(val, int):
                actual.append(val)

        def perform(self):
            pass

    def mock_sleep(sec):
        """mock_sleep wrapper so the tests run faster"""
        del sec

    pycurl_backup = pycurl.Curl
    sleep_backup = time.sleep

    pycurl.Curl = mock_pycurl_curl
    time.sleep = mock_sleep

    netreq = ister_gui.NetworkRequirements(0, 0)
    # don't try to set hardware clock
    netreq.nettime = 'set'
    if not netreq._network_connection():
        raise Exception("No network detected")

    if actual != expected:
        raise Exception("pycurl.Curl options {} do not match "
                        "expected options {}".format(actual, expected))

    pycurl.Curl = pycurl_backup
    time.sleep = sleep_backup


def gui_network_connection_curl_exception():
    """
    Test that a failing pycurl perform results in failed network check with
    all pycurl opts set correctly
    """
    import time

    actual = []
    expected = ["https://www.clearlinux.org", 1, 1, 3]

    class mock_pycurl_curl():
        """mock pycurl.Curl class"""
        def __init__(self):
            self.URL = None
            self.HEADER = None
            self.NOBODY = None
            self.WRITEFUNCTION = None
            self.TIMEOUT = None

        def setopt(self, attr, val):
            # Don't copy storage class address
            if isinstance(val, str) or isinstance(val, int):
                actual.append(val)

        def perform(self):
            raise Exception("Connection error")

    def mock_sleep(sec):
        """mock_sleep wrapper so the tests run faster"""
        del sec

    pycurl_backup = pycurl.Curl
    sleep_backup = time.sleep

    pycurl.Curl = mock_pycurl_curl
    time.sleep = mock_sleep

    netreq = ister_gui.NetworkRequirements(0, 0)
    netreq.config = {}
    if netreq._network_connection():
        pycurl.Curl = pycurl_backup
        time.sleep = sleep_backup
        raise Exception("Network detected when curl failed")

    pycurl.Curl = pycurl_backup
    time.sleep = sleep_backup

    if actual != expected:
        raise Exception("pycurl.Curl options {} do not match "
                        "expected options {}".format(actual, expected))


@run_command_wrapper
@open_wrapper("good", "")
def gui_static_configuration():
    """
    Setting static ip configuration for the installer writes the configuration
    to /etc/systemd/network/10-en-static.network
    """
    import subprocess
    import time

    class Edit():
        """mock urwid.Edit class"""
        def __init__(self, edit_text):
            self.edit_text = edit_text

        def get_edit_text(self):
            return self.edit_text

    def mock_call(cmd):
        """mock_call wrapper"""
        del cmd

    def mock_makedirs(path):
        """mock_makedirs wrapper"""
        del path

    def mock_sleep(sec):
        """mock_sleep wrapper so the tests run faster"""
        del sec

    call_backup = subprocess.call
    makedirs_backup = os.makedirs
    sleep_backup = time.sleep

    subprocess.call = mock_call
    os.makedirs = mock_makedirs
    time.sleep = mock_sleep

    # we will be running the function twice, once without then once with DNS
    commands = ['/etc/systemd/network/10-en-static.network', 'w',
                '[Match]\n',
                'Name=enp0s1\n\n',
                '[Network]\n',
                'Address=10.0.2.15/24\n',
                'Gateway=10.0.2.2\n',
                '/etc/systemd/network/10-en-static.network', 'w',
                '[Match]\n',
                'Name=enp0s1\n\n',
                '[Network]\n',
                'Address=10.0.2.15/24\n',
                'Gateway=10.0.2.2\n',
                'DNS=10.0.2.3\n']

    netreq = ister_gui.NetworkRequirements(0, 0)
    netreq.config = {}
    netreq.ifaceaddrs = {"enp0s1": "10.0.2.15"}
    netreq.static_ip_e = Edit("10.0.2.15")
    netreq.mask_e = Edit("255.255.255.0")
    netreq.interface_e = Edit("enp0s1")
    netreq.gateway_e = Edit("10.0.2.2")
    netreq.static_ready = True
    try:
        netreq._static_configuration(None)
    except:
        # this method always exits with an exception (urwid.ExitMainLoop)
        pass

    # set dns and run _static_configuration again
    netreq.dns_e = Edit("10.0.2.3")
    try:
        netreq._static_configuration(None)
    except:
        # this method always exits with an exception (urwid.ExitMainLoop)
        pass

    commands_compare_helper(commands)

    subprocess.call = call_backup
    os.makedirs = makedirs_backup
    time.sleep = sleep_backup


def gui_set_proxy():
    """
    Setting the proxy in the gui results in the proxy getting stored
    in the template (config)
    """
    import time

    class Edit():
        """mock uwrid.Edit class"""
        def __init__(self, edit_text):
            self.edit_text = edit_text

        def get_edit_text(self):
            return self.edit_text

    def mock_sleep(sec):
        """mock_sleep wrapper so the tests run faster"""
        del sec

    sleep_backup = time.sleep
    time.sleep = mock_sleep

    netreq = ister_gui.NetworkRequirements(1, 1)
    netreq.config = {}
    netreq.https_proxy = Edit("http://to.clearlinux.org:1080")
    try:
        netreq._set_proxy(None)
    except Exception:
        # this method always exits with an exception (urwid.ExitMainLoop)
        pass

    time.sleep = sleep_backup
    if "HTTPSProxy" in netreq.config:
        if netreq.config["HTTPSProxy"] != "http://to.clearlinux.org:1080":
            raise Exception("Proxy not set properly in config")


def gui_set_fullname_fname_lname_present():
    """
    Set the user's full name in the gui with first and last names present
    """

    class Edit():
        """mock uwrid.Edit class"""
        def __init__(self, edit_text):
            self.edit_text = edit_text

        def get_edit_text(self):
            return self.edit_text

    userconfig = ister_gui.UserConfigurationStep(0, 0)
    temp = {}
    userconfig.edit_name = Edit("Test")
    userconfig.edit_lastname = Edit("User")
    userconfig._set_fullname(temp)
    if "fullname" not in temp or temp["fullname"] != "Test User":
        raise Exception("Gui failed to set user fullname properly")


def gui_set_fullname_fname_present():
    """
    Set the user's full name in the gui with only first name present
    """

    class Edit():
        """mock uwrid.Edit class"""
        def __init__(self, edit_text):
            self.edit_text = edit_text

        def get_edit_text(self):
            return self.edit_text

    userconfig = ister_gui.UserConfigurationStep(0, 0)
    temp = {}
    userconfig.edit_name = Edit("Test")
    userconfig.edit_lastname = Edit("")
    userconfig._set_fullname(temp)
    if "fullname" not in temp or temp["fullname"] != "Test":
        raise Exception("Gui failed to set user fullname properly")


def gui_set_fullname_lname_present():
    """
    Set the user's full name in the gui with only last name present
    """

    class Edit():
        """mock uwrid.Edit class"""
        def __init__(self, edit_text):
            self.edit_text = edit_text

        def get_edit_text(self):
            return self.edit_text

    userconfig = ister_gui.UserConfigurationStep(0, 0)
    temp = {}
    userconfig.edit_name = Edit("")
    userconfig.edit_lastname = Edit("User")
    userconfig._set_fullname(temp)
    if "fullname" not in temp or temp["fullname"] != "User":
        raise Exception("Gui failed to set user fullname properly")


def gui_set_fullname_none_present():
    """
    The user's full name should not be set in the gui if none are configured
    by the user
    """

    class Edit():
        """mock uwrid.Edit class"""
        def __init__(self, edit_text):
            self.edit_text = edit_text

        def get_edit_text(self):
            return self.edit_text

    userconfig = ister_gui.UserConfigurationStep(0, 0)
    temp = {}
    userconfig.edit_name = Edit("")
    userconfig.edit_lastname = Edit("")
    userconfig._set_fullname(temp)
    if "fullname" in temp:
        raise Exception("Gui set user fullname when no fullname was present")


def gui_set_hw_time():
    """
    Setting the hw clock first sets the system time then sets the hardware
    clock from the system time.
    """
    import subprocess
    import time

    global COMMAND_RESULTS
    COMMAND_RESULTS = []

    def mock_call(cmd):
        """mock_call wrapper"""
        COMMAND_RESULTS.extend(cmd)

    def mock_sleep(sec):
        """mock_sleep wrapper so the tests run faster"""
        del sec

    call_backup = subprocess.call
    sleep_backup = time.sleep

    subprocess.call = mock_call
    time.sleep = mock_sleep

    lines = ['Date: Sun, Jan 01 2000 00:00:00 GMT\r\n']
    commands = ['/usr/bin/date',
                '+%a, %d %b %Y %H:%M:%S',
                '--set=Sun, Jan 01 2000 00:00:00',
                'hwclock',
                '--systohc']

    netreq = ister_gui.NetworkRequirements(0, 0)
    netreq.config = {}
    netreq._set_hw_time(lines)

    subprocess.call = call_backup
    time.sleep = sleep_backup

    if not netreq.nettime:
        raise Exception('Date not set')

    commands_compare_helper(commands)


def gui_find_current_disk_success():
    """
    Finds the disk where root is currently mounted
    """
    import subprocess

    global COMMAND_RESULTS
    COMMAND_RESULTS = []

    def mock_check_output(cmd):
        COMMAND_RESULTS.extend(cmd)
        return u"NAME MOUNTPOINT\n" \
               "sda\n"             \
               "sda1\n"            \
               "sda2 [SWAP]\n"     \
               "sda3 /\n".encode('utf-8')

    commands = ["lsblk", "-l", "-o", "NAME,MOUNTPOINT"]
    check_output_backup = subprocess.check_output
    subprocess.check_output = mock_check_output
    chooseact = ister_gui.ChooseAction(0, 0)
    subprocess.check_output = check_output_backup
    if not chooseact.current:
        raise Exception("Unable to find root disk")

    commands_compare_helper(commands)


def gui_find_current_disk_failure():
    """
    Returns an empty string when root disk cannot be found
    """
    import subprocess

    global COMMAND_RESULTS
    COMMAND_RESULTS = []

    def mock_check_output(cmd):
        COMMAND_RESULTS.extend(cmd)
        return "NAME MOUNTPOINT\n" \
               "sda\n"             \
               "sda1\n"            \
               "sda2 [SWAP]\n"     \
               "sda3\n".encode('utf-8')

    commands = ["lsblk", "-l", "-o", "NAME,MOUNTPOINT"]
    check_output_backup = subprocess.check_output
    subprocess.check_output = mock_check_output
    chooseact = ister_gui.ChooseAction(0, 0)
    subprocess.check_output = check_output_backup
    if chooseact.current:
        raise Exception("Found root disk when there was none to be found")

    commands_compare_helper(commands)


@open_wrapper("good", "clear-linux-os")
def gui_mount_host_disk_normal():
    """
    Returns target directory and os disk name and boot partition for the
    correct disk
    """
    # pylint: disable=too-many-locals
    import subprocess

    global COMMAND_RESULTS
    COMMAND_RESULTS = []

    def mock_call(cmd):
        COMMAND_RESULTS.extend(cmd)
        return 0

    def mock_mkdtemp(prefix):
        return "/tmp/{}abcdefg123".format(prefix)

    def mock_get_list_of_disks():
        return ["sda", "sdb", "sdc"]

    def mock_get_disk_info(disk):
        if disk == "/dev/sda":
            return {"partitions": [{"type": "EFI System", "name": "/dev/sda1"},
                                   {"type": "", "name": "/dev/sda2"},
                                   {"type": "Linux root",
                                    "name": "/dev/sda3"}]}
        if disk == "/dev/sdb":
            return {"partitions": [{"name": "/dev/sdb1"},
                                   {"type": "SWAP", "name": "/dev/sdb2"}]}
        if disk == "/dev/sdc":
            return {"partitions": [{"type": "", "name": "/dev/sdc1"},
                                   {"type": "EFI System", "name": "/dev/sdc2"},
                                   {"type": "Linux root",
                                    "name": "/dev/sdc3"}]}

    def mock_find_current_disk(_):
        return "sda"

    call_backup = subprocess.call
    mkdtemp_backup = tempfile.mkdtemp
    get_list_of_disks_backup = ister_gui.get_list_of_disks
    get_disk_info_backup = ister_gui.get_disk_info
    find_current_disk_backup = ister_gui.ChooseAction._find_current_disk

    subprocess.call = mock_call
    tempfile.mkdtemp = mock_mkdtemp
    ister_gui.get_list_of_disks = mock_get_list_of_disks
    ister_gui.get_disk_info = mock_get_disk_info
    ister_gui.ChooseAction._find_current_disk = mock_find_current_disk

    commands = ['mount', '/dev/sdc3', '/tmp/ister-latest-abcdefg123',
                '/tmp/ister-latest-abcdefg123/usr/lib/os-release', 'r',
                'read',
                'mount', '/dev/sdc2', '/tmp/ister-latest-abcdefg123/boot']
    chooseact = ister_gui.ChooseAction(0, 0)
    config = {"Version": "latest"}
    os_disk, boot_part = chooseact._mount_host_disk(config)

    subprocess.call = call_backup
    tempfile.mkdtemp = mkdtemp_backup
    ister_gui.get_list_of_disks = get_list_of_disks_backup
    ister_gui.get_disk_info = get_disk_info_backup
    ister_gui.ChooseAction._find_current_disk = find_current_disk_backup

    if chooseact.target_dir != "/tmp/ister-latest-abcdefg123":
        raise Exception("Target directory {} did not match expected "
                        "/tmp/ister-latest-abcdefg123"
                        .format(chooseact.target_dir))

    if os_disk != "/dev/sdc3":
        raise Exception("OS disk {} did not match expected "
                        "/dev/sdc3".format(os_disk))

    if boot_part != "/dev/sdc2":
        raise Exception("OS boot partition {} did not match expected "
                        "/dev/sdc2".format(boot_part))

    commands_compare_helper(commands)


@open_wrapper("good", "clear-linux-os")
def gui_mount_host_disk_no_boot_on_host():
    """
    Returns target directory and os disk name for the correct disk. Boot
    partition name should be empty since it does not exist on the host disk.
    """
    # pylint: disable=too-many-locals
    import subprocess

    global COMMAND_RESULTS
    COMMAND_RESULTS = []

    class mock_alert():
        def __init__(self, _, __):
            pass

        def do_alert(self):
            pass

    def mock_call(cmd):
        COMMAND_RESULTS.extend(cmd)
        return 0

    def mock_mkdtemp(prefix):
        return "/tmp/{}abcdefg123".format(prefix)

    def mock_get_list_of_disks():
        return ["sda", "sdb", "sdc"]

    def mock_get_disk_info(disk):
        if disk == "/dev/sda":
            return {"partitions": [{"type": "EFI System", "name": "/dev/sda1"},
                                   {"type": "", "name": "/dev/sda2"},
                                   {"type": "root", "name": "/dev/sda3"}]}
        if disk == "/dev/sdb":
            return {"partitions": [{"name": "/dev/sdb2"},
                                   {"type": "SWAP", "name": "/dev/sdb2"}]}
        if disk == "/dev/sdc":
            return {"partitions": [{"type": "", "name": "/dev/sdc1"},
                                   {"type": "Linux root",
                                    "name": "/dev/sdc3"}]}

    def mock_find_current_disk(_):
        return "sda"

    call_backup = subprocess.call
    mkdtemp_backup = tempfile.mkdtemp
    get_list_of_disks_backup = ister_gui.get_list_of_disks
    get_disk_info_backup = ister_gui.get_disk_info
    find_current_disk_backup = ister_gui.ChooseAction._find_current_disk
    alert_backup = ister_gui.Alert

    subprocess.call = mock_call
    tempfile.mkdtemp = mock_mkdtemp
    ister_gui.get_list_of_disks = mock_get_list_of_disks
    ister_gui.get_disk_info = mock_get_disk_info
    ister_gui.ChooseAction._find_current_disk = mock_find_current_disk
    ister_gui.Alert = mock_alert

    commands = ['mount', '/dev/sdc3', '/tmp/ister-latest-abcdefg123',
                '/tmp/ister-latest-abcdefg123/usr/lib/os-release', 'r', 'read']
    chooseact = ister_gui.ChooseAction(0, 0)
    config = {"Version": "latest"}
    os_disk, boot_part = chooseact._mount_host_disk(config)

    subprocess.call = call_backup
    tempfile.mkdtemp = mkdtemp_backup
    ister_gui.get_list_of_disks = get_list_of_disks_backup
    ister_gui.get_disk_info = get_disk_info_backup
    ister_gui.ChooseAction._find_current_disk = find_current_disk_backup
    ister_gui.Alert = alert_backup

    if chooseact.target_dir != "/tmp/ister-latest-abcdefg123":
        raise Exception("Target directory {} did not match expected "
                        "/tmp/ister-latest-abcdefg123"
                        .format(chooseact.target_dir))

    if os_disk != "/dev/sdc3":
        raise Exception("OS disk {} did not match expected "
                        "/dev/sdc3".format(os_disk))

    if boot_part:
        raise Exception("OS boot partition found when it shouldn't have been")

    commands_compare_helper(commands)


@open_wrapper("good", "clear-linux-os")
def gui_get_root_present():
    import subprocess

    global COMMAND_RESULTS
    COMMAND_RESULTS = []

    def mock_call(cmd):
        COMMAND_RESULTS.extend(cmd)

    call_backup = subprocess.call
    subprocess.call = mock_call

    part_info = {"partitions": [{"name": "/dev/sda1"},
                                {"type": "Linux root", "name": "/dev/sda2"}]}
    commands = ['mount', '/dev/sda2', '/tmp/ister-latest-abcdefg123',
                '/tmp/ister-latest-abcdefg123/usr/lib/os-release', 'r', 'read']
    chooseact = ister_gui.ChooseAction(0, 0)
    chooseact.target_dir = "/tmp/ister-latest-abcdefg123"
    result = chooseact._get_part(part_info, "Linux root", chooseact.target_dir)
    subprocess.call = call_backup
    if result is not "/dev/sda2":
        raise Exception("OS root partition {} did not match expected /dev/sda2"
                        .format(result))

    commands_compare_helper(commands)


@open_wrapper("good", "clear-linux-os")
def gui_get_root_not_present():
    import subprocess

    global COMMAND_RESULTS
    COMMAND_RESULTS = []

    def mock_call(cmd):
        COMMAND_RESULTS.extend(cmd)

    call_backup = subprocess.call
    subprocess.call = mock_call

    part_info = {"partitions": [{"name": "/dev/sda1"},
                                {"type": "SWAP", "name": "/dev/sda2"}]}
    commands = []
    chooseact = ister_gui.ChooseAction(0, 0)
    chooseact.target_dir = "/tmp/ister-latest-abcdefg123"
    result = chooseact._get_part(part_info, 'Linux root', chooseact.target_dir)
    subprocess.call = call_backup
    if result:
        raise Exception("OS root partition reported as {} when none present"
                        .format(result))

    commands_compare_helper(commands)


def gui_get_boot_present():
    import subprocess

    global COMMAND_RESULTS
    COMMAND_RESULTS = []

    def mock_call(cmd):
        COMMAND_RESULTS.extend(cmd)

    call_backup = subprocess.call
    subprocess.call = mock_call

    part_info = {"partitions": [{"name": "/dev/sda1"},
                                {"type": "EFI System", "name": "/dev/sda2"}]}
    commands = ['mount', '/dev/sda2', '/tmp/ister-latest-abcdefg123/boot']
    chooseact = ister_gui.ChooseAction(0, 0)
    chooseact.target_dir = "/tmp/ister-latest-abcdefg123"
    result = chooseact._get_part(part_info,
                                 "EFI System",
                                 "{}/boot".format(chooseact.target_dir))
    subprocess.call = call_backup
    if result is not "/dev/sda2":
        raise Exception("OS boot partition {} did not match expected /dev/sda2"
                        .format(result))

    commands_compare_helper(commands)


def gui_get_boot_not_present():
    import subprocess

    global COMMAND_RESULTS
    COMMAND_RESULTS = []

    def mock_call(cmd):
        COMMAND_RESULTS.extend(cmd)

    call_backup = subprocess.call
    subprocess.call = mock_call

    part_info = {"partitions": [{"name": "/dev/sda1"},
                                {"type": "SWAP", "name": "/dev/sda2"}]}
    commands = []
    chooseact = ister_gui.ChooseAction(0, 0)
    chooseact.target_dir = "/tmp/ister-latest-abcdefg123"
    result = chooseact._get_part(part_info,
                                 "EFI System",
                                 "{}/boot".format(chooseact.target_dir))
    subprocess.call = call_backup
    if result:
        raise Exception("OS boot partition reported as {} when none present"
                        .format(result))

    commands_compare_helper(commands)


def gui_umount_host_disk():
    import subprocess

    global COMMAND_RESULTS
    COMMAND_RESULTS = []

    def mock_call(cmd):
        COMMAND_RESULTS.extend(cmd)

    def mock_rmdir(target_dir):
        COMMAND_RESULTS.append(target_dir)

    call_backup = subprocess.call
    rmdir_backup = os.rmdir

    subprocess.call = mock_call
    os.rmdir = mock_rmdir

    commands = ["umount",
                "/dev/sdc2",
                "umount",
                "/dev/sdc3",
                "ister-latest-abcdefg123"]
    chooseact = ister_gui.ChooseAction(0, 0)
    chooseact.target_dir = "ister-latest-abcdefg123"
    chooseact._umount_host_disk("/dev/sdc3",
                                "/dev/sdc2")

    subprocess.call = call_backup
    os.rmdir = rmdir_backup

    commands_compare_helper(commands)


def run_tests(tests):
    """Run ister test suite"""
    fail = 0
    flog = open("test-log", "w")

    with open("test-log", "w") as flog:
        for test in tests:
            try:
                test()
            except Exception as exep:
                print("Test: {0} FAIL: {1}.".format(test.__name__, exep))
                flog.write("Test: {0} FAIL: {1}.\n".format(test.__name__,
                                                           exep))
                fail += 1
            else:
                print("Test: {0} PASS.".format(test.__name__))
                flog.write("Test: {0} PASS.\n".format(test.__name__))

    return fail


if __name__ == '__main__':
    class log_wrapper():
        """ Trivial dummy log object that suffices for most tests."""
        def debug(self, _):
            """dummy debug"""
            pass

        def info(self, _):
            """dummy info"""
            pass

        def error(self, _):
            """dummy error"""
            pass

    ister.LOG = log_wrapper()

    TESTS = [
        run_command_good,
        run_command_with_env,
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
        get_device_name_good_mmcblk_physical,
        create_filesystems_good,
        create_filesystems_virtual_good,
        create_filesystems_mmcblk_good,
        create_filesystems_good_options,
        setup_mounts_good,
        setup_mounts_good_mbr,
        setup_mounts_good_no_boot,
        setup_mounts_virtual_good,
        setup_mounts_mmcblk_good,
        setup_mounts_bad,
        setup_mounts_good_units,
        add_bundles_good,
        get_current_format_good,
        set_hostname_good,
        copy_os_good,
        copy_os_proxy_good,
        copy_os_format_good,
        copy_os_which_good,
        copy_os_physical_good,
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
        add_user_fullname,
        post_install_nonchroot_good,
        cleanup_physical_good,
        cleanup_virtual_good,
        get_template_location_good,
        get_template_location_bad_missing,
        get_template_location_bad_no_equal,
        get_template_location_bad_malformed,
        get_template_good,
        validate_layout_good,
        validate_layout_good_missing_efi_virtual,
        validate_layout_good_missing_boot,
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
        validate_fstypes_good_without_format,
        validate_fstypes_bad_format,
        validate_fstypes_bad_missing_disk,
        validate_fstypes_bad_missing_partition,
        validate_fstypes_bad_missing_type,
        validate_fstypes_bad_type,
        validate_fstypes_bad_duplicate,
        validate_fstypes_bad_not_partition,
        validate_hostname_good,
        validate_hostname_bad,
        validate_static_ip_good,
        validate_static_ip_good_with_dns,
        validate_static_ip_good_with_dns_equals_to_address,
        validate_static_ip_good_with_dns_equals_to_gateway,
        validate_static_ip_bad_missing_address,
        validate_static_ip_bad_missing_gateway,
        validate_static_ip_bad_missing_mask,
        validate_static_ip_bad_invalid_format_address,
        validate_static_ip_bad_invalid_format_gateway,
        validate_static_ip_bad_invalid_format_dns,
        validate_static_ip_bad_repeated_values,
        validate_partition_mounts_good,
        validate_partition_mounts_good_missing_boot_virtual,
        validate_partition_mounts_good_missing_boot,
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
        validate_user_template_good_no_sudo,
        validate_user_template_good_key_missing_password,
        validate_user_template_bad_missing_name,
        validate_user_template_bad_duplicate_name,
        validate_user_template_bad_missing_password,
        validate_user_template_bad_duplicate_uid,
        validate_user_template_bad_invalid_uid_low,
        validate_user_template_bad_invalid_uid_high,
        validate_user_template_bad_invalid_sudo,
        validate_user_template_bad_missing_key,
        validate_postnonchroot_template_good,
        validate_postnonchroot_template_bad,
        validate_template_good,
        validate_template_latest_good,
        validate_template_good_disable_partitioning,
        validate_template_bad_long_hostname,
        validate_template_bad_missing_destination_type,
        validate_template_bad_missing_partition_layout,
        validate_template_bad_missing_filesystem_types,
        validate_template_bad_missing_partition_mount_points,
        validate_template_bad_missing_version,
        validate_template_bad_missing_bundles,
        validate_template_bad_short_hostname,
        validate_template_bad_version,
        validate_network_good,
        validate_network_bad,
        parse_config_good,
        parse_config_bad,
        handle_options_good,
        handle_logging_good,
        check_kernel_cmdline_good,
        check_kernel_cmdline_bad_no_isterconf,
        check_kernel_cmdline_bad_urlopen_fails,
        check_kernel_cmdline_bad_fdopen_fails,
        get_host_from_url_good_1,
        get_host_from_url_good_2,
        get_host_from_url_bad_malformed_url,
        get_iface_for_host_good,
        get_iface_for_host_bad_no_route,
        get_iface_for_host_bad_hostname,
        get_mac_for_iface_good,
        get_mac_for_iface_bad,
        fetch_cloud_init_configs_good,
        fetch_cloud_init_configs_bad_urlopen,
        get_cloud_init_configs_good,
        get_cloud_init_configs_bad_url_has_no_host,
        get_cloud_init_configs_bad_no_route_to_host,
        get_cloud_init_configs_bad_iface,
        get_cloud_init_configs_bad_no_configs_for_target,
        fetch_cloud_init_role_good,
        fetch_cloud_init_role_bad_cannot_open_url,
        fetch_cloud_init_role_bad_cannot_target_file,
        modify_cloud_init_service_file_good,
        modify_cloud_init_service_file_bad_open,
        cloud_init_configs_good,
        cloud_init_configs_good_no_role,
        gui_network_connection,
        gui_network_connection_curl_exception,
        gui_static_configuration,
        gui_set_proxy,
        gui_set_fullname_fname_lname_present,
        gui_set_fullname_fname_present,
        gui_set_fullname_lname_present,
        gui_set_fullname_none_present,
        validate_proxy_url_template_good,
        validate_proxy_url_template_bad,
        gui_set_hw_time,
        gui_find_current_disk_success,
        gui_find_current_disk_failure,
        gui_mount_host_disk_normal,
        gui_mount_host_disk_no_boot_on_host,
        gui_get_root_present,
        gui_get_root_not_present,
        gui_get_boot_present,
        gui_get_boot_not_present,
        gui_umount_host_disk
    ]

    failed = run_tests(TESTS)
    if failed > 0:
        sys.exit(1)
