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


def good_min_template():
    """Return string representation of good_min_template"""
    return u'{"ImageSourceType": "local", "ImageSourceLocation": \
    "file:///good.raw.xz"}'


def good_min_remote_template():
    """Return string representation of good_min_remote_template"""
    return u'{"ImageSourceType": "local", "ImageSourceLocation": \
    "http://10.0.2.2:8001/good.raw.xz"}'


def good_user_template():
    """Return string representation of good_user_template"""
    return u'{"ImageSourceType": "local", "ImageSourceLocation": \
    "file:///good.raw.xz", \
    "Users": [{"username": "test"}]}'


def good_user_key_template():
    """Return string representation of good_user_key_template"""
    return u'{"ImageSourceType": "local", "ImageSourceLocation": \
    "file:///good.raw.xz", \
    "Users": [{"username": "test", "key": "file:///root/key.pub"}]}'


def good_user_uid_template():
    """Return string representation of good_user_uid_template"""
    return u'{"ImageSourceType": "local", "ImageSourceLocation": \
    "file:///good.raw.xz", \
    "Users": [{"username": "test", "uid": 1000}]}'


def good_user_sudop_template():
    """Return string representation of good_user_sudop_template"""
    return u'{"ImageSourceType": "local", "ImageSourceLocation": \
    "file:///good.raw.xz", \
    "Users": [{"username": "test", "sudo": "password"}]}'


def good_post_install_template():
    """Return string representation of good_post_package_install_template"""
    return u'{"ImageSourceType": "local", "ImageSourceLocation": \
    "file:///good.raw.xz", \
    "PostInstallPackages": [{"packagemanager": "zypper", "type": "single", \
    "name": "linux"}]}'


def good_disk_template():
    """Return string representation of good_disk_template"""
    return u'{"ImageSourceType": "local", "ImageSourceLocation": \
    "file:///good.raw.xz", \
    "PartitionLayout": \
    [{"disk": "sdb", "partition": 1, "size": "512M", "type": "EFI"}, \
    {"disk": "sdb", "partition": 2, \
    "size": "512M", "type": "swap"}, {"disk": "sdb", "partition": 3, \
    "size": "rest", "type": "linux"}], \
    "FilesystemTypes": \
    [{"disk": "sdb", "partition": 1, "type": "vfat"}, {"disk": "sdb", \
    "partition": 2, "type": "swap"}, \
    {"disk": "sdb", "partition": 3, "type": "ext4"}], \
    "PartitionMountPoints": \
    [{"disk": "sdb", "partition": 1, "mount": "/boot"}, {"disk": "sdb", \
    "partition": 3, "mount": "/"}]}'


def full_user_install_template():
    """Return string representation of full_user_install_template"""
    return u'{"ImageSourceType": "local", "ImageSourceLocation": \
    "file:///good.raw.xz", "PartitionLayout": \
    [{"disk": "sdb", "partition": 1, "size": "512M", "type": "EFI"}, \
    {"disk": "sdb", "partition": 2, "size": "512M", "type": "swap"}, \
    {"disk": "sdb", "partition": 3, "size": "rest", "type": "linux"}], \
    "FilesystemTypes": \
    [{"disk": "sdb", "partition": 1, "type": "vfat"}, {"disk": "sdb", \
    "partition": 2, "type": "swap"}, \
    {"disk": "sdb", "partition": 3, "type": "ext4"}], \
    "PartitionMountPoints": \
    [{"disk": "sdb", "partition": 1, "mount": "/boot"}, {"disk": "sdb", \
    "partition": 3, "mount": "/"}], \
    "Users": [{"username": "user", "key": "file:///root/key.pub", \
    "uid": 1001, "sudo": "password"}]}'


def read_good_local_conf():
    """Run read_good_local_conf test"""
    template_file = ister.get_template_location("/root/good-ister.conf")
    if template_file != u"file:///tmp/template.json":
        raise Exception("Incorrect template file path")


def load_min_good_local_template():
    """Run load_min_good_local_template test"""
    filename = "file:///root/min-good.json"
    template = ister.get_template(filename)
    good = json.loads(good_min_template())
    if template != good:
        raise Exception("JSON template doesn't match")


def load_min_good_remote_template():
    """Run load_min_good_remote_template test"""
    filename = "http://10.0.2.2:8001/min-good.json"
    template = ister.get_template(filename)
    good = json.loads(good_min_template())
    if template != good:
        raise Exception("JSON remote template doesn't match")


def get_valid_remote_image():
    """Run get_valid_remote_image test"""
    template = json.loads(good_min_remote_template())
    try:
        ister.get_source_image(template)
    except:
        raise Exception("Unable to download template file")
    if template["ImageSourceLocation"] != "file:///image.xz":
        raise Exception("Failed to update ImageSourceLocation")


def validate_good_template():
    """Run validate_good_template test"""
    good_templates = [good_min_template, good_min_remote_template,
                      good_user_template, good_user_key_template,
                      good_user_uid_template, good_user_sudop_template,
                      good_disk_template, full_user_install_template,
                      good_post_install_template]

    for template_string in good_templates:
        template = json.loads(template_string())
        try:
            ister.validate_template(template)
        except Exception as exep:
            raise Exception("JSON template {0} ({1}) is invalid: {2}"
                            .format(template_string.__name__,
                                    template_string(), exep))


def validate_fs_default_detection():
    """Run validate_fs_default_detection test"""
    template = json.loads(good_min_template())
    try:
        dev = ister.find_target_disk()
    except Exception as exep:
        raise Exception("Unable to find target device: ", exep)
    try:
        ister.insert_fs_defaults(template)
    except Exception as exep:
        raise Exception("Unable to add default disk target: ", exep)

    if not template.get("PartitionLayout"):
        raise Exception("Failed to insert PartitionLayout to template")
    if template["PartitionLayout"] != [{"disk": dev, "partition": 1,
                                        "size": "512M", "type": "EFI"},
                                       {"disk": dev, "partition": 2,
                                        "size": "rest", "type": "linux"}]:
        raise Exception("Failed to setup PartitionLayout correctly")
    if not template.get("FilesystemTypes"):
        raise Exception("Failed to insert FilesystemTypes to template")
    if template["FilesystemTypes"] != [{"disk": dev, "partition": 1,
                                        "type": "vfat"},
                                       {"disk": dev, "partition": 2,
                                        "type": "ext4"}]:
        raise Exception("Failed to setup FilesystemTypes correctly")
    if not template.get("PartitionMountPoints"):
        raise Exception("Failed to insert PartitionMountPoints to template")
    if template["PartitionMountPoints"] != [{"disk": dev, "partition": 1,
                                             "mount": "/boot"},
                                            {"disk": dev, "partition": 2,
                                             "mount": "/"}]:
        raise Exception("Failed to setup PartitionMountPoints correctly")


def validate_full_user_install():
    """Run validate_full_user_install test"""
    template = json.loads(full_user_install_template())
    try:
        ister.create_partitions(template)
    except Exception as exep:
        raise Exception("Unable to create partitions ({0}): {1}"
                        .format(template["PartitionLayout"], exep))

    try:
        ister.create_filesystems(template)
    except Exception as exep:
        raise Exception("Unable to create filesystems ({0}): {1}"
                        .format(template["FilesystemTypes"], exep))

    try:
        (source, target) = ister.setup_mounts(template)
    except Exception as exep:
        raise Exception("Unable to setup mount points ({0}): {1}"
                        .format(template["PartitionMountPoints"], exep))

    try:
        ister.copy_files(source, target)
    except Exception as exep:
        raise Exception("Unable to install OS: {0}".format(exep))

    try:
        uuids = ister.get_uuids(template)
    except Exception as exep:
        raise Exception("Unable to get uuids in ({0}): {1}"
                        .format(template, exep))

    try:
        ister.update_loader(uuids, target)
    except Exception as exep:
        raise Exception("Unable to update loader conf: {0}".format(exep))

    try:
        ister.update_fstab(uuids, target)
    except Exception as exep:
        raise Exception("Unable to update fstab: {0}".format(exep))

    try:
        ister.add_users(template, target)
    except Exception as exep:
        raise Exception("Unable to add users: {0}".format(exep))

    try:
        ister.cleanup(source, target)
    except Exception as exep:
        raise Exception("Unable to cleanup after install: {}".format(exep))


def validate_post_package_install():
    """Run validate_post_package_install test"""
    template = json.loads(good_post_install_template())

    try:
        ister.validate_template(template)
    except Exception as exep:
        raise Exception("Unable to validate template ({0}): {1}"
                        .format(template, exep))

    try:
        ister.create_partitions(template)
    except Exception as exep:
        raise Exception("Unable to create partitions ({0}): {1}"
                        .format(template["PartitionLayout"], exep))

    try:
        ister.create_filesystems(template)
    except Exception as exep:
        raise Exception("Unable to create filesystems ({0}): {1}"
                        .format(template["FilesystemTypes"], exep))

    try:
        (source, target) = ister.setup_mounts(template)
    except Exception as exep:
        raise Exception("Unable to setup mount points ({0}): {1}"
                        .format(template["PartitionMountPoints"], exep))

    try:
        ister.copy_files(source, target)
    except Exception as exep:
        raise Exception("Unable to install OS: {0}".format(exep))

    try:
        uuids = ister.get_uuids(template)
    except Exception as exep:
        raise Exception("Unable to get uuids in ({0}): {1}"
                        .format(template, exep))

    try:
        ister.update_loader(uuids, target)
    except Exception as exep:
        raise Exception("Unable to update loader conf: {0}".format(exep))

    try:
        ister.post_install_packages(template, target)
    except Exception as exep:
        raise Exception("Unable to post install package: {0}".format(exep))

    try:
        ister.cleanup(source, target)
    except Exception as exep:
        raise Exception("Unable to cleanup after install: {}".format(exep))


def validate_remote_image_setup():
    """Run validate_remote_image_setup test"""
    template = json.loads(good_min_remote_template())
    ister.get_source_image(template)
    ister.insert_fs_defaults(template)
    try:
        ister.create_partitions(template)
    except Exception as exep:
        raise Exception("Unable to create partitions ({0}): {1}"
                        .format(template["PartitionLayout"], exep))

    try:
        ister.create_filesystems(template)
    except Exception as exep:
        raise Exception("Unable to create filesystems ({0}): {1}"
                        .format(template["FilesystemTypes"], exep))

    try:
        (source, target) = ister.setup_mounts(template)
    except Exception as exep:
        raise Exception("Unable to setup mount points ({0}): {1}"
                        .format(template["PartitionMountPoints"], exep))

    try:
        ister.cleanup(source, target)
    except Exception as exep:
        raise Exception("Unable to cleanup after install: {}".format(exep))


def run_tests(tests):
    """Run ister test suite"""
    flog = open("/root/test-log", "w")

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
    # In case network-online.service doesn't work right
    time.sleep(3)
    TESTS = [
        read_good_local_conf,
        load_min_good_local_template,
        load_min_good_remote_template,
        get_valid_remote_image,
        validate_good_template,
        validate_fs_default_detection,
        validate_full_user_install,
        validate_post_package_install,
        validate_remote_image_setup
    ]

    run_tests(TESTS)
