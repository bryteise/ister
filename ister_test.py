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

import ister
import json
import time
import os


# def good_user_template():
#     """Return string representation of good_user_template"""
#     return u'{"ImageSourceType": "local", "ImageSourceLocation": \
#     "file:///good.raw.xz", \
#     "Users": [{"username": "test"}]}'


# def good_user_key_template():
#     """Return string representation of good_user_key_template"""
#     return u'{"ImageSourceType": "local", "ImageSourceLocation": \
#     "file:///good.raw.xz", \
#     "Users": [{"username": "test", "key": "file:///root/key.pub"}]}'


# def good_user_uid_template():
#     """Return string representation of good_user_uid_template"""
#     return u'{"ImageSourceType": "local", "ImageSourceLocation": \
#     "file:///good.raw.xz", \
#     "Users": [{"username": "test", "uid": 1000}]}'


# def good_user_sudop_template():
#     """Return string representation of good_user_sudop_template"""
#     return u'{"ImageSourceType": "local", "ImageSourceLocation": \
#     "file:///good.raw.xz", \
#     "Users": [{"username": "test", "sudo": "password"}]}'


# def good_post_install_template():
#     """Return string representation of good_post_package_install_template"""
#     return u'{"ImageSourceType": "local", "ImageSourceLocation": \
#     "file:///good.raw.xz", \
#     "PostInstallPackages": [{"packagemanager": "zypper", "type": "single", \
#     "name": "linux"}]}'


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
    "partition" : 3, "mount" : "/"}]}'


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


def read_good_local_conf():
    """Run read_good_local_conf test"""
    template_file = ister.get_template_location("good-ister.conf")
    if template_file != u"file:///tmp/template.json":
        raise Exception("Incorrect template file path")


def validate_good_template():
    """Run validate_good_template test"""
    good_templates = [good_virtual_disk_template, full_user_install_template]

    for template_string in good_templates:
        template = json.loads(template_string())
        try:
            ister.validate_template(template)
        except Exception as exep:
            raise Exception("JSON template {0} ({1}) is invalid: {2}"
                            .format(template_string.__name__,
                                    template_string(), exep))


def validate_full_user_install():
    """Run validate_full_user_install test"""
    template = json.loads(full_user_install_template())
    try:
        ister.create_virtual_disk(template)
    except Exception as exep:
        raise Exception("Unable to create virtual disk ({0}): {1}"
                        .format(template["PartitionLayout"], exep))

    try:
        ister.create_partitions(template)
    except Exception as exep:
        raise Exception("Unable to create partitions ({0}): {1}"
                        .format(template["PartitionLayout"], exep))

    try:
        ister.map_loop_device(template)
    except Exception as exep:
        raise Exception("Unable to map loop device ({0}): {1}"
                        .format(template["PartitionLayout"], exep))

    try:
        ister.create_filesystems(template)
    except Exception as exep:
        raise Exception("Unable to create filesystems ({0}): {1}"
                        .format(template["FilesystemTypes"], exep))

    try:
        target = ister.setup_mounts(template)
    except Exception as exep:
        raise Exception("Unable to setup mount points ({0}): {1}"
                        .format(template["PartitionMountPoints"], exep))

    # try:
    #     ister.copy_files(source, target)
    # except Exception as exep:
    #     raise Exception("Unable to install OS: {0}".format(exep))

    # try:
    #     uuids = ister.get_uuids(template)
    # except Exception as exep:
    #     raise Exception("Unable to get uuids in ({0}): {1}"
    #                     .format(template, exep))

    # try:
    #     ister.update_loader(uuids, target)
    # except Exception as exep:
    #     raise Exception("Unable to update loader conf: {0}".format(exep))

    # try:
    #     ister.update_fstab(uuids, target)
    # except Exception as exep:
    #     raise Exception("Unable to update fstab: {0}".format(exep))

    # try:
    #     ister.setup_machine_id(target)
    # except Exception as exep:
    #     raise Exception("Unable to setup machine-id: {0}".format(exep))

    # try:
    #     ister.add_users(template, target)
    # except Exception as exep:
    #     raise Exception("Unable to add users: {0}".format(exep))

    try:
        ister.cleanup(template, target)
        os.remove(template["PartitionLayout"][0]["disk"])
    except Exception as exep:
        raise Exception("Unable to cleanup after install: {}".format(exep))


def run_tests(tests):
    """Run ister test suite"""
    flog = open("test-log", "w")

    for test in tests:
        try:
            test()
        except Exception as exep:
            print("Test: {0} failed: {1}.".format(test.__name__, exep))
            flog.write("Test: {0} failed: {1}.\n".format(test.__name__, exep))
        else:
            print("Test: {0} passed.".format(test.__name__))
            flog.write("Test: {0} passed.\n".format(test.__name__))

    flog.close()

if __name__ == '__main__':
    TESTS = [
        read_good_local_conf,
        validate_good_template,
        validate_full_user_install
    ]

    run_tests(TESTS)
