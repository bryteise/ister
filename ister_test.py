#!/usr/bin/env python3

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

import ister
import json
import os
import time

def good_min_template():
    return u'{"ImageSourceType": "local", "ImageSourceLocation": "file:///good.raw.xz"}'
def good_min_remote_template():
    return u'{"ImageSourceType": "local", "ImageSourceLocation": "http://10.0.2.2:8001/good.raw.xz"}'
def good_user_template():
    return u'{"ImageSourceType": "local", "ImageSourceLocation": "file:///good.raw.xz", \
    "Users": [{"username": "test"}]}'
def good_user_key_template():
    return u'{"ImageSourceType": "local", "ImageSourceLocation": "file:///good.raw.xz", \
    "Users": [{"username": "test", "key": "file:///root/key.pub"}]}'
def good_user_uid_template():
    return u'{"ImageSourceType": "local", "ImageSourceLocation": "file:///good.raw.xz", \
    "Users": [{"username": "test", "uid": 1000}]}'
def good_user_sudop_template():
    return u'{"ImageSourceType": "local", "ImageSourceLocation": "file:///good.raw.xz", \
    "Users": [{"username": "test", "sudo": "password"}]}'
def good_disk_template():
    return u'{"ImageSourceType": "local", "ImageSourceLocation": "file:///good.raw.xz", \
    "PartitionLayout": \
    [{"disk": "sdb", "partition": 1, "size": "512M", "type": "EFI"}, {"disk": "sdb", "partition": 2, \
    "size": "512M", "type": "swap"}, {"disk": "sdb", "partition": 3, "size": "rest", "type": "linux"}], \
    "FilesystemTypes": \
    [{"disk": "sdb", "partition": 1, "type": "vfat"}, {"disk": "sdb", "partition": 2, "type": "swap"}, \
    {"disk": "sdb", "partition": 3, "type": "ext4"}], \
    "PartitionMountPoints": \
    [{"disk": "sdb", "partition": 1, "mount": "/boot"}, {"disk": "sdb", "partition": 3, "mount": "/"}]}'
def full_user_install_template():
    return u'{"ImageSourceType": "local", "ImageSourceLocation": "file:///good.raw.xz", \
    "PartitionLayout": \
    [{"disk": "sdb", "partition": 1, "size": "512M", "type": "EFI"}, {"disk": "sdb", "partition": 2, \
    "size": "512M", "type": "swap"}, {"disk": "sdb", "partition": 3, "size": "rest", "type": "linux"}], \
    "FilesystemTypes": \
    [{"disk": "sdb", "partition": 1, "type": "vfat"}, {"disk": "sdb", "partition": 2, "type": "swap"}, \
    {"disk": "sdb", "partition": 3, "type": "ext4"}], \
    "PartitionMountPoints": \
    [{"disk": "sdb", "partition": 1, "mount": "/boot"}, {"disk": "sdb", "partition": 3, "mount": "/"}], \
    "Users": [{"username": "user", "key": "file:///root/key.pub", "uid": 1001, "sudo": "password"}]}'

def read_good_local_conf():
    template_file = ister.get_template_location("/root/good-ister.conf")
    if template_file != u"file:///tmp/template.json":
        raise Exception("Incorrect template file path")

def load_min_good_local_template():
    filename = "file:///root/min-good.json"
    template = ister.get_template(filename)
    good = json.loads(good_min_template())
    if template != good:
        raise Exception("JSON template doesn't match")

def load_min_good_remote_template():
    filename = "http://10.0.2.2:8001/min-good.json"
    template = ister.get_template(filename)
    good = json.loads(good_min_template())
    if template != good:
        raise Exception("JSON remote template doesn't match")

def validate_good_template():
    good_templates = [good_min_template, good_min_remote_template, good_user_template, good_user_key_template, good_user_uid_template, good_user_sudop_template, good_disk_template, full_user_install_template]

    for template_string in good_templates:
        template = json.loads(template_string())
        try:
            ister.validate_template(template)
        except Exception as e:
            raise Exception("JSON template {0} ({1}) is invalid: {2}".format(template_string.__name__, template_string(), e))

def validate_fs_default_detection():
    template = json.loads(good_min_template())
    try:
        dev = ister.find_target_disk()
    except Exception as e:
        raise Exception("Unable to find target device: ", e)
    try:
        ister.insert_fs_defaults(template)
    except Exception as e:
        raise Exception("Unable to add default disk target: ", e)

    if not template.get("PartitionLayout"):
        raise Exception("Failed to insert PartitionLayout to template")
    if template["PartitionLayout"] != [{"disk" : dev, "partition" : 1, "size" : "512M", "type" : "EFI" },
                                       {"disk" : dev, "partition" : 2, "size" : "rest", "type" : "linux" }]:
        raise Exception("Failed to setup PartitionLayout correctly")
    if not template.get("FilesystemTypes"):
        raise Exception("Failed to insert FilesystemTypes to template")
    if template["FilesystemTypes"] != [{"disk" : dev, "partition" : 1, "type" : "vfat" },
                                      {"disk" : dev, "partition" : 2, "type" : "ext4" }]:
        raise Exception("Failed to setup FilesystemTypes correctly")
    if not template.get("PartitionMountPoints"):
        raise Exception("Failed to insert PartitionMountPoints to template")
    if template["PartitionMountPoints"] != [{"disk" : dev, "partition" : 1, "mount" : "/boot" },
                                            {"disk" : dev, "partition" : 2, "mount" : "/" }]:
        raise Exception("Failed to setup PartitionMountPoints correctly")

def validate_full_user_install():
    template = json.loads(full_user_install_template())
    try:
        ister.create_partitions(template)
    except Exception as e:
        raise Exception("Unable to create partitions ({0}): {1}".format(template["PartitionLayout"], e))

    try:
        ister.create_filesystems(template)
    except Exception as e:
        raise Exception("Unable to create filesystems ({0}): {1}".format(template["FilesystemTypes"], e))

    try:
        (s, t) = ister.setup_mounts(template)
    except Exception as e:
        raise Exception("Unable to setup mount points ({0}): {1}".format(template["PartitionMountPoints"], e))

    try:
        ister.copy_files(s, t)
    except Exception as e:
        raise Exception("Unable to install OS: {0}".format(e))

    try:
        uuids = ister.get_uuids(template)
    except Exception as e:
        raise Exception("Unable to get uuids in ({0}): {1}".format(template, e))

    try:
        ister.update_loader(uuids, t)
    except Exception as e:
        raise Exception("Unable to update loader conf: {0}".format(e))

    try:
        ister.update_fstab(uuids, t)
    except Exception as e:
        raise Exception("Unable to update fstab: {0}".format(e))

    try:
        ister.add_users(template, t)
    except Exception as e:
        raise Exception("Unable to add users: {0}".format(e))

    try:
        ister.cleanup(template, s, t)
    except Exception as e:
        raise Exception("Unable to cleanup after install: {}".format(e))

def run_tests(tests):
    flog = open("/root/test-log", "w")

    for test in tests:
        try:
            test()
        except Exception as e:
            flog.write("Test: {0} failed: {1}.\n".format(test.__name__, e))
        else:
            flog.write("Test: {0} passed.\n".format(test.__name__))

    flog.close()

if __name__ == '__main__':
    # In case network-online.service doesn't work right
    time.sleep(3)
    tests = [
        read_good_local_conf,
        load_min_good_local_template,
        load_min_good_remote_template,
        validate_good_template,
        validate_fs_default_detection,
        validate_full_user_install
    ]

    run_tests(tests)
