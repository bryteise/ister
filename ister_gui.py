#!/usr/bin/env python3
"""Clear Linux OS installation gui"""

#
# This file is part of ister.
#
# Copyright (C) 2015 Intel Corporation
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

# The array as default value is too handy here to worry about
# pylint: disable=dangerous-default-value
# Intended manipulation of internal state of the UI
# pylint: disable=protected-access
# global is handy here for now, but this could be fixed up
# pylint: disable=global-statement
# broad exceptions are fine
# pylint: disable=broad-except
# yeah this is pretty big
# pylint: disable=too-many-lines
# arguments differ is fine for the child classes
# pylint: disable=arguments-differ

import argparse
import crypt
import json
import logging
import os
import re
import subprocess
import threading
import sys
import pprint
import tempfile
import ipaddress
import signal
import time
import itertools
import netifaces
import pycurl
import urwid

import ister

PALETTE = [
    ('header', 'white', 'dark red', 'bold'),
    ('banner', 'white', 'dark gray'),
    ('bg', 'black', 'black'),
    ('p1', 'white', 'dark red'),
    ('p2', 'white', 'dark green'),
    ('p3', 'white', 'dark cyan'),
    ('p4', 'white', 'dark magenta'),
    ('reversed', 'light cyan', 'black'),
    ('I say', 'black,bold', 'dark gray', 'bold'),
    ('success', 'dark green', 'dark gray'),
    ('warn', 'dark red', 'dark gray'),
    ('button', 'light cyan', 'dark gray'),
    ('ex', 'light gray', 'dark gray'),
    ('popbg', 'white', 'dark blue')]

MIN_WIDTH = 80
MIN_HEIGHT = 24
MAX_WIDTH = 136
MAX_HEIGHT = 42
PERCENTAGE_W = 90
PERCENTAGE_H = 70
LINES = 0
COLUMNS = 0


def get_disk_info(disk):
    """Return dictionary with disk information"""
    info = {'partitions': []}
    cmd = ['/usr/bin/fdisk', '-l', disk]
    output = subprocess.check_output(cmd).decode('utf-8')
    lines = output.split('\n')
    expr = re.compile('^Device')
    # discard header...
    while lines:
        match = expr.match(lines[0])
        if match:
            break
        else:
            lines.pop(0)
    if lines:
        lines.pop(0)  # header - add this back manually
    expr = re.compile(r'(\S+)\s+\S+\s+\S+\s+\S+\s+(\S+)\s+(\S.*)')
    for line in lines:
        match = expr.match(line)
        if match:
            info['partitions'].append({
                'name': match.group(1),
                'size': match.group(2),
                'type': match.group(3),
                'number': match.group(1)[len(disk):]
            })
        else:
            break
    return info


def get_part_devname(part):
    """
    Return the parent device of the partition

    If called on a device name, we could get a list of identical strings for
    each partition the device contains:

    $ lsblk -no pkname /dev/sda
            # note the blank line here
    sda
    sda
    sda

    Just return the first one
    """
    cmd = ['/usr/bin/lsblk', '-no', 'pkname', os.path.join('/dev', part)]
    try:
        # need to strip out leading blank line for the case that lsblk is
        # called on a device name
        output = subprocess.check_output(cmd).decode('utf-8').strip()
    except subprocess.CalledProcessError:
        return None

    return output.splitlines()[0]


def get_list_of_disks():
    """"
    Queries for the available disks discarding the installer root disk

    Parses lsblk output to find list of disks and to find where / is mounted.
    The disk with a partition mounted to / is the installer disk and is
    ignored. A list of available disks by name (sdb, sdc, vda, etc.) is
    returned.

    The lsblk command `lsblk -lo NAME,TYPE,MOUNTPOINT outputs the following
    format.

    NAME TYPE MOUNTPOINT
    sda  disk        <--- disk, identified as current by sda3 mount point
    sda1 part
    sda2 part [SWAP]
    sda3 part /      <--- root partition
    sdb  disk        <--- disk, valid target because no root partition mounted
    sdb1 part
    sdb2 part

    For the above case this function would return ['sdb']
    """
    disks = []
    root_disk = ''
    output = subprocess.check_output([
        '/usr/bin/lsblk', '-lo', 'NAME,TYPE,MOUNTPOINT']).decode('utf-8')
    parts = output.split('\n')
    for part in parts:
        part = part.strip()
        if 'disk' in part:
            disks.append(part.split()[0])
        elif part.endswith('/'):
            root_disk = part.split()[0]

    # remove installer disk and return
    return [dsk for dsk in disks if dsk not in root_disk]


def compute_mask(mask_ip):
    """Compute the /<mask> notation from mask IP"""
    return sum([bin(int(x)).count("1") for x in mask_ip.split(".")])


def network_service_ready():
    """Check network status with increasing sleep times on each failure"""
    for i in [.1, 1, 2, 4]:
        try:
            out = subprocess.check_output(['/usr/bin/systemctl',
                                           'status',
                                           'systemd-networkd',
                                           'systemd-resolved'])
        except subprocess.CalledProcessError:
            return False

        if out.decode('utf-8').count('Active: active (running)') == 2:
            return True

        time.sleep(i)

    return False


def find_current_disk():
    """
    Find the current disk so it can be skipped when searching for a Linux
    root
    """
    cmd = ['lsblk', '-l', '-o', 'NAME,MOUNTPOINT']
    output = subprocess.check_output(cmd).decode('utf-8')
    for line in output.split('\n'):
        if '/' in line:
            return line.split()[0]

    return ''


def find_dns():
    """Find active DNS server by searching /etc/resolv.conf if it exists"""
    content = ''
    if os.path.exists('/etc/resolv.conf'):
        with open('/etc/resolv.conf', 'r') as resolv:
            content = resolv.readlines()

    # just report the first nameserver
    for line in content:
        if 'nameserver' in line:
            return line.split(' ')[1].strip()


def get_keyboards():
    """
    Get list of keyboards from localectl to create dropdown selection
    """
    try:
        out = subprocess.check_output(['localectl',
                                       'list-keymaps']).decode('utf-8')
    except subprocess.CalledProcessError:
        return ['us']

    # 'us' is default and should be first in the list
    kbs = ['us']
    # remove trailing empty line with [:-1]
    # extend by each keyboard in localectl list-keymaps output
    kbs.extend(k for k in out.split('\n')[:-1] if k != 'us')
    return kbs


def set_keyboard(keyboard):
    """
    Set system keymapping to keyboard
    """
    subprocess.call(['localectl', 'set-keymap', keyboard])


def restart_networkd_resolved():
    """Restart the network services then poll systemctl status output until
    both are back up"""
    # restart systemd-networkd and systemd-resolved
    subprocess.call(['/usr/bin/systemctl', 'restart',
                     'systemd-networkd', 'systemd-resolved'])

    if not network_service_ready():
        raise Exception('Unable to restart network services')


def static_set():
    """ Return a True if static has been configured on machine """
    return os.path.exists('/etc/systemd/network/10-en-static.network')


def setup():
    """Initialization method for getting screen dimensions"""
    global PERCENTAGE_W, PERCENTAGE_H, LINES, COLUMNS
    rows, columns = os.popen('stty size', 'r').read().split()
    rows, columns = int(rows), int(columns)
    if rows < MIN_HEIGHT:
        PERCENTAGE_H = 100
    if columns < MIN_WIDTH:
        PERCENTAGE_W = 100
    LINES = int(rows * PERCENTAGE_H / 100)
    COLUMNS = int(columns * PERCENTAGE_W / 100)
    if LINES > MAX_HEIGHT:
        LINES = int(MAX_HEIGHT)
    if COLUMNS > MAX_WIDTH:
        COLUMNS = int(MAX_WIDTH)


def ister_wrapper(fn_name, *args):
    """Wrapper to dynamically call ister validations"""
    # pylint: disable=no-member
    try:
        ister.__getattribute__(fn_name)(*args)
    except Exception as exc:
        return exc
    return None


# pylint: disable=too-many-arguments
# six is reasonable since this function in turn calls three other functions
def ister_button(message, on_press=None, user_data=None,
                 align='left', left=0, right=0):
    """
    Wrapper for ister_gui button creation since these are the steps nearly
    always taken
    """
    width = len(message) + 4
    button = urwid.Button(message, on_press=on_press, user_data=user_data)
    button = urwid.AttrMap(button, 'button', focus_map='reversed')
    return urwid.Padding(button, align=align, width=width,
                         left=left, right=right)


def required_bundles(config):
    """
    Determines the required bundles list from options set in the configuration
    dictionary. Returns a list of bundle dictionaries containing 'name' and
    'desc' fields.
    """
    reqd_bundles = []

    # configure core bundles (kernel, os-core, and os-core-update)
    # detect virtualization technology to determine which kernel to require
    try:
        output = subprocess.check_output('systemd-detect-virt',
                                         shell=True).decode('utf-8')
    except Exception:
        output = 'none'

    if 'qemu' in output or 'kvm' in output:
        kernel = {'name': 'kernel-kvm',
                  'desc': 'Required to run Clear Linux OS on kvm'}
    else:
        kernel = {'name': 'kernel-native',
                  'desc': 'Required to run Clear Linux OS on baremetal'}

    reqd_bundles.extend([
        {'name': 'os-core',
         'desc': 'Minimal packages to have Clear Linux OS fully '
                 'functional'},
        kernel,
        {'name': 'os-core-update',
         'desc': 'Required to update the system'}])

    # configure dynamically required bundles (sysadmin-basic, telemetrics)
    sysadmin_basic = {'name': 'sysadmin-basic',
                      'desc': 'Run common utilities useful for managing a '
                              'system (required when creating an admin user)'}
    telemetrics = {'name': 'telemetrics',
                   'desc': 'Collects anonymous reports to improve system '
                           'stability (opted in)'}
    # 'telemetrics' will exist in config['Bundles'] if the user opted in. This
    # is the only way to select the telemetrics bundle, so make it required.
    if 'telemetrics' in config['Bundles']:
        reqd_bundles.append(telemetrics)

    # if an administrative user is defined, that user will need sudo to operate
    # the system.
    if config.get('Users'):
        reqd_bundles.append(sysadmin_basic)

    return reqd_bundles


def search_swap(choices, config, mount_d):
    """
    Search for the name of the swap partition to add to config
    """
    for choice in choices:
        is_swap = True
        part = choice.split()[0]
        for point in mount_d:
            if part == mount_d[point]['part']:
                is_swap = False
                break
        if is_swap:
            output = subprocess.check_output('fdisk -l | grep {0}'
                                             .format(part),
                                             shell=True).decode('utf-8')
            if 'Linux swap' in output:
                # first try to set using lsblk -no pkname part
                disk = get_part_devname(part)
                # if that fails, alert and fallback to old
                # (unreliable) method
                if not disk:
                    Alert('Partition error',
                          'Unable to detect device name for {}. '
                          'Falling back to path parsing. This method is '
                          'unreliable and may result in a failed install.'
                          .format(part)).do_alert()
                    disk = ''.join(x for x in part if not x.isdigit())

                part = part[len(disk):]
                # strip prefix if it exists. Not needed here and ister.py
                # will add it back
                prefix = part[0] if not part[0].isdigit() else ''
                part = part.lstrip(prefix)

                config['PartitionLayout'].append({
                    'disk': disk,
                    'partition': part,
                    'size': '1M',
                    'type': 'swap'})
                config['FilesystemTypes'].append({
                    'disk': disk,
                    'partition': part,
                    'type': 'swap'})


def interface_list():
    """List all interface names"""
    # pylint: disable=no-member
    return [ifc for ifc in netifaces.interfaces() if ifc.startswith('e')]


class Alert(object):
    """Class to display alerts or confirm boxes"""
    # pylint: disable=R0902
    # pylint: disable=R0903
    def __init__(self, title, msg, **kwargs):
        self._frame = [('pack', urwid.Divider()),
                       ('pack', urwid.Text(msg)),
                       ('pack', urwid.Divider(u' ', 1))]
        self._block = kwargs.get('block', True)
        self._labels = kwargs.get('labels', [u'Ok'])
        self._title = title
        self.response = None
        self.loop = None
        if self._block:
            self._add_nav_bar()
        self._set_ui()

    def _on_click(self, button):
        self.response = button.label
        raise urwid.ExitMainLoop()

    def _add_nav_bar(self):
        buttons = list()
        for label in self._labels:
            button = ister_button(label,
                                  on_press=self._on_click,
                                  align='center')
            buttons.append(button)

        # Add to frame
        nav = NavBar(buttons)
        # Nav Bar always starts with focus in
        nav.have_focus = True
        self._frame.append(('pack', nav))
        self._frame.append(('pack', urwid.Divider()))

    def _set_ui(self):
        self._frame = FormController(self._frame)
        self._frame = urwid.LineBox(self._frame, title=self._title)
        self._frame = urwid.Filler(self._frame, valign='middle')
        self._fgwin = urwid.Padding(self._frame, 'center', ('relative', 75))
        self._ui = urwid.Overlay(self._fgwin,
                                 urwid.AttrMap(urwid.SolidFill(u' '), 'bg'),
                                 align='center',
                                 width=('relative', PERCENTAGE_W),
                                 valign='middle',
                                 height=('relative', PERCENTAGE_H))
        self._ui = urwid.AttrMap(self._ui, 'banner')

    def do_alert(self):
        """It creates the loop, if synchronous it will block"""
        self.loop = urwid.MainLoop(self._ui, palette=PALETTE)
        if self._block:
            self.loop.run()
        else:
            self.loop.start()
            self.loop.draw_screen()


class Terminal(object):
    """UI object that enables the installer to run external commands"""
    def __init__(self, cmd):
        self.term = urwid.Terminal(cmd)
        self.init_widget()

    def init_widget(self):
        """Initializes the minimal widgets to run"""
        mainframe = urwid.LineBox(
            urwid.Pile([('weight', 70, self.term)]))

        urwid.connect_signal(self.term, 'closed', self.quit)

        loop = urwid.MainLoop(
            mainframe,
            handle_mouse=False,
            unhandled_input=lambda: None)

        self.term.main_loop = loop
        self.term.keygrab = True

    @staticmethod
    def quit(*args, **kwargs):
        """Breaks the loop to continue"""
        del args, kwargs
        raise urwid.ExitMainLoop()

    def main_loop(self):
        """Enters the loop to grab focus on the terminal UI"""
        self.term.main_loop.run()


class PopUpDialog(urwid.WidgetWrap):
    """Pop up dialog box"""
    signals = ['close']

    def __init__(self, popup_msg, button_text):
        close_button = ister_button(button_text, on_press=self._emit, left=2)
        pile = urwid.Pile([urwid.Text(popup_msg), close_button])
        fill = urwid.Filler(pile)
        super(PopUpDialog, self).__init__(urwid.AttrWrap(fill, 'popbg'))

    def _emit(self, _):
        """Override urwid.WidgetWrap emit to always close"""
        super(PopUpDialog, self)._emit('close')


class PopUpWidget(urwid.PopUpLauncher):
    """Launches a pop up dialog box"""
    def __init__(self, button_text, popup_msg, close_button_text):
        super(PopUpWidget, self).__init__(
            ister_button(button_text, on_press=self.open_pop_up))
        self.popup_msg = popup_msg
        self.close_button_text = close_button_text

    def create_pop_up(self):
        """Initiate a pop up menu"""
        pop_up = PopUpDialog(self.popup_msg, self.close_button_text)
        urwid.connect_signal(pop_up, 'close',
                             lambda button: self.close_pop_up())
        return pop_up

    def get_pop_up_parameters(self):
        """Override urwid.PopUpLauncher.get_pop_up_parameters to set our own"""
        return {'left': 0, 'top': 1,
                'overlay_width': 32,
                'overlay_height': len(interface_list()) + 3}

    def open_pop_up(self, _):
        """
        Override urwid.PopUpLauncher.open_pop_up so we can pass it to
        ister_button
        """
        super(PopUpWidget, self).open_pop_up()


class ButtonMenu(object):
    """Assemble the button menu - ultimately store it in self._ui"""
    # pylint: disable=R0903
    def __init__(self, title, choices, selection):
        self._response = ''  # The choice made by the user is stored here.
        self.choices = choices
        self.selection = selection
        self.construct(title)

    def construct(self, title):
        """Construct the Button menu widgets"""
        # These will sit above the list box
        frame_contents = [('pack', urwid.Divider()),
                          ('pack', urwid.Text(title)),
                          ('pack', urwid.Divider())]
        self._menu = []
        for choice in self.choices:
            label = choice if self.selection != choice else '* ' + choice
            button = ister_button(label,
                                  on_press=self._item_chosen,
                                  user_data=choice)
            self._menu.append(button)

        self._lb = NavListBox(urwid.SimpleFocusListWalker(self._menu), self)
        frame_contents.append(self._lb)
        frame_contents = urwid.Pile(frame_contents)
        self._fgwin = urwid.Padding(frame_contents, left=2, right=2)
        self._ui = urwid.Overlay(self._fgwin,
                                 urwid.AttrMap(urwid.SolidFill(u' '), 'bg'),
                                 align='center',
                                 width=('relative', PERCENTAGE_W),
                                 valign='middle',
                                 height=('relative', PERCENTAGE_H))
        self._ui = urwid.AttrMap(self._ui, 'banner')

    # This callback is registered with urwid.MainLoop and gives us the
    # opportunity to intercept keystrokes and handle things like tabs.
    # In theory the callback for each keystroke should be function
    # fragment or class method but I just handled them in-line here.
    # Unhandled input is returned back to MainLoop for default handlers to
    # deal with. Another way to effect this would be to subclass the
    # ListBox class and override the keypress method.
    def _input_filter(self, keys, raw):
        # pylint: disable=W0212
        del raw
        i = self._lb.focus_position
        max_pos = len(self._menu)
        if 'tab' in keys or 'down' in keys:
            self._lb.focus_position = (i + 1) % max_pos
            self._lb._invalidate()
        else:
            return keys

    def _item_chosen(self, button, _):
        """ Callback trigged by button activation  """
        del button
        self._response = 'Next'
        raise urwid.ExitMainLoop()

    def run_ui(self):
        """ Runs the button menu and returns the choice made by the user. """
        main_loop = urwid.MainLoop(self._ui, palette=PALETTE,
                                   input_filter=self._input_filter)
        main_loop.run()
        return self._response


class NavBar(urwid.Columns):
    """ Builds and manages a nav-bar of buttons """
    # pylint: disable=R0903
    def __init__(self, buttons):
        self.have_focus = False
        super(NavBar, self).__init__(buttons, dividechars=5)

    def keypress(self, size, key):
        """ Get the key that was pressed """
        # self.focus_position defined in parent
        # pylint: disable=E0203
        # pylint: disable=W0201
        max_cols = len(self.contents)
        pos = self.focus_position
        # we will handle the following keys ourselves, don't call super
        if key not in ['tab', 'down', 'up', 'shift tab']:
            key = super(NavBar, self).keypress(size, key)
        # up and shift tab should behave like right in the navbar (so that the
        # Next option is selected first)
        elif key in ['up', 'shift tab']:
            key = super(NavBar, self).keypress(size, 'right')

        if key in ['tab', 'down']:
            if self.have_focus is False:
                self.have_focus = True
                # first focus should be the Next button in the last column if
                # it is present
                self.focus_position = max_cols - 1
            elif pos > 0:
                self.focus_position = pos - 1
            elif pos == 0:
                self.have_focus = False
                return key
        else:
            return key


class FormBody(urwid.ListBox):
    """ Adds a list of widgets to a list box.
    Includes navigation management """
    # pylint: disable=R0903
    def __init__(self, fields):
        self._lost_focus = False
        self._num_fields = len(fields)
        self._body = urwid.SimpleFocusListWalker(fields)
        super(FormBody, self).__init__(self._body)

    def keypress(self, size, key):
        """Manages key press event"""
        # self.focus_position defined in parent
        # pylint: disable=E0203
        # pylint: disable=W0201
        # pylint: disable=R0912

        # we will handle the following keys ourselves, don't call super
        if key not in ['tab', 'down', 'shift tab']:
            key = super(FormBody, self).keypress(size, key)
        # shift tab should behave like the up arrow
        elif key == 'shift tab':
            key = super(FormBody, self).keypress(size, 'up')

        pos = self.focus_position
        if key in ['tab', 'enter', 'down']:
            if self._lost_focus:
                self._lost_focus = False
                self.focus_position = 0
                pos = 0
                while pos <= (self._num_fields - 1):
                    if self._body[pos].selectable():
                        self.focus_position = pos
                        self._invalidate()
                        break
                    else:
                        pos += 1
                if pos > (self._num_fields - 1):
                    self._lost_focus = True
                    return 'tab'
            elif pos < (self._num_fields - 1):
                pos += 1
                while pos <= (self._num_fields - 1):
                    if self._body[pos].selectable():
                        self.focus_position = pos
                        self._invalidate()
                        break
                    else:
                        pos += 1
                if pos > (self._num_fields - 1):
                    self._lost_focus = True
                    return 'tab'
            elif pos >= (self._num_fields - 1):
                self._lost_focus = True
                return 'tab'
        else:
            return key


class FormController(urwid.Pile):
    """ Manages Focus navigation between a FormBody and NavBar """
    # pylint: disable=R0903
    def keypress(self, size, key):
        """Manages keypress event"""
        # self.focus_position defined in parent
        # pylint: disable=E0203
        # pylint: disable=W0201
        key = super(FormController, self).keypress(size, key)
        pos = self.focus_position
        if key in ['tab', 'down']:
            start = self.focus_position
            # Skip the header
            while True:
                pos = (pos + 1) % len(self.contents)
                self.focus_position = pos
                if self.focus.selectable():
                    break
                # guard against infinite spinning
                if pos == start:
                    break
            # Send the key into the newly focused widget
            self.focus.keypress(size, key)
        else:
            return key


class SimpleForm(object):
    """ Creates a Form with a Header, FormBody (which contains form fields)
    And a NavBar, which contains buttons for previous and next.
    Prompt for input for one or more fields """
    # pylint: disable=R0902
    # pylint: disable=R0903
    def __init__(self, title, fields, buttons=["Previous", "Next"],
                 align_title='left'):
        self._title = title
        self._questions = fields
        self._answers = dict()
        self._clicked = ''
        self._next_id = 0
        self.button_labels = buttons
        self._nav_bar_has_focus = True
        self.nav = None

        # Build the forum
        self._frame = [('pack', urwid.Divider()),
                       ('pack', urwid.Text(title, align=align_title)),
                       ('pack', urwid.Divider())]

        self._form_body = FormBody(fields)
        self._frame.append(self._form_body)

        for field in fields:
            if field.selectable():
                self._nav_bar_has_focus = False

        # This helps push the default focus to the NavBar
        if self._nav_bar_has_focus:
            self._form_body._selectable = False

        # Add the navigation buttons - for the installer common to
        # all forms.  <previous> <next> """

        self._add_nav_bar()
        self._set_ui()

    def _on_click(self, button):
        self._clicked = button.label
        raise urwid.ExitMainLoop()

    def _add_nav_bar(self):
        buttons = []

        for label in self.button_labels:
            button = ister_button(label,
                                  on_press=self._on_click,
                                  align='center')
            buttons.append(button)

        # Add to frame
        self.nav = NavBar(buttons)
        self.nav.have_focus = self._nav_bar_has_focus
        self._frame.append(('pack', self.nav))
        self._frame.append(('pack', urwid.Divider()))

    def _set_ui(self):
        self._frame = FormController(self._frame)
        self._fgwin = urwid.Padding(self._frame, left=2, right=2)
        self._ui = urwid.Overlay(self._fgwin,
                                 urwid.AttrMap(urwid.SolidFill(u' '), 'bg'),
                                 align='center',
                                 width=('relative', PERCENTAGE_W),
                                 valign='middle',
                                 height=('relative', PERCENTAGE_H))
        self._ui = urwid.AttrMap(self._ui, 'banner')

    def do_form(self, pop_ups=False):
        """Creates the loop and enter to it, to focus the UI"""
        main_loop = urwid.MainLoop(self._ui, palette=PALETTE, pop_ups=pop_ups)
        main_loop.run()
        return self._clicked


class HostnameEdit(urwid.Edit):
    """Widget to ask for hostname input"""
    # pylint: disable=R0903
    def keypress(self, size, key):
        """Manages key press event to validate input"""
        first = re.compile('[a-zA-Z0-9]')
        rest = re.compile('[a-zA-Z0-9-]')
        # Only allow valid hostnames. Only letters, numbers,
        # and '-' allowed.  Can't start with '-', Max length 63 """

        i = len(self.get_edit_text())

        if i == 0:
            match = first.match(key)
            if match:
                key = super(HostnameEdit, self).keypress(size, key)
        elif i < 63:
            match = rest.match(key)
            if match:
                key = super(HostnameEdit, self).keypress(size, key)
        elif key == 'backspace':
            key = super(HostnameEdit, self).keypress(size, key)
        return key


class UsernameEdit(urwid.Edit):
    """Widget to ask for username input"""
    # pylint: disable=R0903
    def keypress(self, size, key):
        """Manages key press event to validate input"""
        first = re.compile(r'[a-z]')
        rest = re.compile(r'[a-z0-9\-_]')
        # Only allow valid usernamces. Only lower letters, numbers,
        # and '-' allowed.  Can't start with '-', Max length 63

        i = len(self.get_edit_text())

        if i == 0:
            match = first.match(key)
            if match:
                key = super(UsernameEdit, self).keypress(size, key)
        elif i < 63:
            match = rest.match(key)
            if match:
                key = super(UsernameEdit, self).keypress(size, key)
        return key


class IpEdit(urwid.Edit):
    """Widget to ask for ip input"""
    # pylint: disable=R0903
    def keypress(self, size, key):
        """Manages key press event to validate input"""
        # Backspace doesn't work when the edit accepts only numbers
        if key == 'backspace':
            key = super(IpEdit, self).keypress(size, key)
            return key
        first = re.compile(r'[1-9]')
        rest = re.compile(r'[0-9\.]')
        # Only allow valid usernamces. Only lower letters, numbers,
        # and '-' allowed.  Can't start with '-', Max length 63

        i = len(self.get_edit_text())

        if i == 0:
            match = first.match(key)
            if match:
                key = super(IpEdit, self).keypress(size, key)
        elif i < 63:
            match = rest.match(key)
            if match:
                key = super(IpEdit, self).keypress(size, key)
        return key


class ProcessStep(object):
    """Defines a step to be run by the installation handler"""
    def __init__(self):
        self._ui = None
        self._ui_widgets = None
        self._action = None
        self.action_map = dict()
        self.display_fmt = None
        self._clicked = None

    def get_next_step(self, action):
        """Returns the process step matched by action"""
        if action == 'Exit':
            exit(0)
        if action in self.action_map:
            return self.action_map[action]

        tmp = Alert(u'Error!', '"{}" not implemented yet'.format(action))
        tmp.do_alert()
        return self

    def set_action(self, action, target, **_):
        """Sets process step to be matched by a key"""
        self.action_map[action] = target

    def handler(self, config):
        """Handles all the work for the current UI"""
        # Config is a reference
        # pylint: disable=W0613
        if not self._ui_widgets:
            self.build_ui_widgets()

        if not self._ui:
            self.build_ui()

        if self._ui:
            self._action = self.run_ui()

        return self._action

    @staticmethod
    def run_ui():
        """Method to run the ui and return the action"""
        return 'Next'

    def build_ui_widgets(self, *_):
        """Method to build all the widgets"""
        self._ui_widgets = None

    def build_ui(self):
        """Method to create the ui"""
        self._ui = True


class SplashScreen(ProcessStep):
    # pylint: disable=R0902
    """
    First screen to display information about Clear Linux OS and this installer
    """
    def __init__(self):
        super(SplashScreen, self).__init__()
        greeting = "The Clear Linux Project for Intel Architecture is a "     \
                   "distribution built for various Cloud use cases. We want " \
                   "to showcase the best of Intel Architecture technology "   \
                   "and performance, from low-level kernel features to "      \
                   "complex applications that span across the entire OS "     \
                   "stack. We're putting emphasis on Power and Performance "  \
                   "optimizations throughout the operating system as a "      \
                   "whole.\n\n"                                               \
                   "** More information can be found at clearlinux.org **"
        navigate = "Use TAB or ARROW keys to navigate, press ENTER to select"
        previous = "You can return to a < Previous > screen at any time."
        self.greeting = urwid.Padding(urwid.Text(greeting), left=20, right=20)
        self.navigate = urwid.Padding(urwid.Text(navigate), left=20, right=20)
        self.previous = urwid.Padding(urwid.Text(previous), left=20, right=20)

    def handler(self, config):
        """Handles all the work for the current UI"""
        if not self._ui_widgets:
            self.build_ui_widgets()

        if not self._ui:
            self.build_ui()

        if self._ui:
            self._action = self.run_ui()

        return self._action

    def run_ui(self):
        return self._ui.do_form()

    def build_ui_widgets(self):
        """Build ui handler
        The last urwid Divider helps to tab movement to work"""
        self._ui_widgets = [self.greeting,
                            urwid.Divider(),
                            urwid.Divider(),
                            urwid.Divider(),
                            self.navigate,
                            urwid.Divider(),
                            self.previous,
                            urwid.Divider()]

    def build_ui(self):
        self._ui = SimpleForm(
            u'Clear Linux OS for Intel Architecture Installer',
            self._ui_widgets, buttons=["Next"], align_title='center')


class KeyboardSelection(ButtonMenu):
    """
    Screen to allow user to select keyboard layout for installer
    """
    def __init__(self):
        self.action_map = {}
        self._action = None
        self.header = ('Keyboard Selection\n\n'
                       'Defaults to us\n'
                       'Current selection indicated by *\n'
                       'ESC, left arrow, q      - return to previous screen\n'
                       'tab, right arrow        - proceed to next screen '
                       'without changing keyboard map\n'
                       'j, k, up/down arrow     - navigate the list\n'
                       'enter                   - set keyboard mapping to '
                       'selection and proceed')
        self.selection = 'us'
        super(KeyboardSelection, self).__init__(self.header,
                                                get_keyboards(),
                                                self.selection)

    def handler(self, _):
        """Handles all the work for the current UI"""
        self.construct(self.header)
        if self._ui:
            self.run_ui()

        return self._action

    def run_ui(self):
        urwid.MainLoop(self._ui, palette=PALETTE).run()

    def set_action(self, action, target, **_):
        """Sets process step to be matched by a key"""
        self.action_map[action] = target

    def _item_chosen(self, button, choice):
        """ Callback trigged by button activation  """
        self._action = 'Next'
        try:
            set_keyboard(choice)
        except Exception:
            Alert('Error!',
                  'Unable to set keymapping to {}'.format(choice)).do_alert()

        self.selection = choice
        raise urwid.ExitMainLoop()

    def get_next_step(self, action):
        """Returns the process step matched by action"""
        if action == 'Exit':
            exit(0)
        if action in self.action_map:
            return self.action_map[action]

        tmp = Alert(u'Error!', '"{}" not implemented yet'.format(action))
        tmp.do_alert()
        return self


class NavListBox(urwid.ListBox):
    """
    Screen to allow user to select keyboard layout for installer
    """
    def __init__(self, body, press):
        self.press = press
        self.press._action = None
        super(NavListBox, self).__init__(body)

    def keypress(self, size, key):
        """ Get the key that was pressed """
        # pylint: disable=E0203
        # pylint: disable=W0201
        # we will handle the following keys ourselves, don't call super
        if key not in ['tab', 'j', 'k', 'q', 'right', 'left', 'esc']:
            key = super(NavListBox, self).keypress(size, key)
        elif key == 'j':
            key = super(NavListBox, self).keypress(size, 'down')
        elif key == 'k':
            key = super(NavListBox, self).keypress(size, 'up')

        if key in ['tab', 'right']:
            self.press._action = 'Next'
            raise urwid.ExitMainLoop
        elif key in ['esc', 'left', 'q']:
            self.press._action = 'Previous'
            raise urwid.ExitMainLoop
        else:
            return key


class ChooseAction(ProcessStep):
    """UI to select installation path (Install, Shell, or Repair)"""
    # pylint: disable=R0902
    def __init__(self, cur_step, tot_steps):
        super(ChooseAction, self).__init__()
        self.choices = {
            'Install': 'Install - Install Clear Linux OS',
            'Repair': 'Repair  - Attempt to repair host OS',
            'Shell': 'Shell   - Open shell in host OS'
        }
        self._clicked = None
        self.error = False
        self.current = find_current_disk()
        self.target_dir = None
        self.progress = urwid.Text('Step {} of {}'.format(cur_step, tot_steps))

    def build_ui_widgets(self):
        self._ui_widgets = [self.progress]
        for key in sorted(self.choices):
            button = ister_button(self.choices[key],
                                  on_press=self._item_chosen,
                                  user_data=key)
            self._ui_widgets.append(button)

        # Add the exit button last so it is at the bottom of the choices list
        exit_button = ister_button('Exit    - Exit installer',
                                   on_press=self._item_chosen,
                                   user_data='Exit')
        self._ui_widgets.append(exit_button)

    def _item_chosen(self, _, choice):
        self._clicked = choice
        raise urwid.ExitMainLoop()

    def build_ui(self):
        self._ui = SimpleForm('Choose Action', self._ui_widgets,
                              buttons=['Previous'])

    def run_ui(self):
        return self._ui.do_form()

    def handler(self, config):
        prefix = 'ister-{}-'.format(str(config["Version"]))
        self.target_dir = tempfile.mkdtemp(prefix=prefix)

        if not self._ui_widgets:
            self.build_ui_widgets()

        if not self._ui:
            self.build_ui()

        self._clicked = ''

        if self._ui:
            self._action = self.run_ui()

        if self._clicked:
            self._action = self._clicked

        if self._action == 'Shell':
            self.chroot_shell(config)

        if self._action == 'Repair':
            self.repair_host(config)

        return self._action

    def chroot_shell(self, config):
        """Chroot into host os (if one is found) and provide a shell"""
        root_part, boot_part = self._mount_host_disk(config)
        term = None
        if not self.error:
            os.environ['HOME'] = '/root'
            term = Terminal(['chroot', self.target_dir, '/bin/bash'])
        else:
            # ask user if they want a shell in the installer instead
            alert = Alert('Info',
                          'Open shell in installer instead?',
                          labels=['OK', 'Cancel'])
            alert.do_alert()
            if alert.response == 'OK':
                term = Terminal(['bash'])

        try:
            if term:
                term.main_loop()
        except Exception as excep:
            Alert('Error!', 'Error occurred in shell: {}'
                  .format(excep)).do_alert()

        self._umount_host_disk(root_part, boot_part)
        self.error = False
        self._action = 'return'

    def repair_host(self, config):
        """Run swupd verify --fix in the host os chroot"""
        root_part, boot_part = self._mount_host_disk(config)
        if self.error:
            self._umount_host_disk(root_part, boot_part)
            self._action = 'return'
            return

        watch = WatchableProcess(['swupd',
                                  'verify',
                                  '--path={}'.format(self.target_dir),
                                  '--statedir={}'
                                  .format(os.path.join(self.target_dir,
                                                       "var/lib/swupd")),
                                  '--fix'])
        watch.start()
        current = 0
        Alert('Repairing',
              'Repairing host os on {}...'.format(root_part),
              block=False).do_alert()
        while not watch.done:
            if len(watch.output) > current:
                current = len(watch.output)
                text = '\n'.join(watch.output[-10:])
                Alert('Repairing', text, block=False).do_alert()
        Alert('Repairing', '\n'.join(watch.output[-10:])).do_alert()

        if not watch.poll():
            Alert('Repairing', 'Successful repair').do_alert()
        else:
            Alert('Error!', 'Unable to repair host os').do_alert()

        self._umount_host_disk(root_part, boot_part)
        self.error = False
        self._action = 'return'

    def _mount_host_disk(self, config):
        """Search for and mount the host os disk"""
        root_part = ''
        boot_part = ''
        prefix = 'ister-{}-'.format(str(config["Version"]))
        self.target_dir = tempfile.mkdtemp(prefix=prefix)
        disks = get_list_of_disks()
        # search disks for root and boot partitions
        for disk in disks:
            if disk in self.current or root_part:
                continue
            part_info = get_disk_info('/dev/{}'.format(disk))
            root_part = self._get_part(part_info,
                                       'Linux root',
                                       self.target_dir)
            # only look for a boot partition on the same disk as the root
            # partition and only if a root partition is found
            if root_part:
                boot_part = self._get_part(part_info,
                                           'EFI System',
                                           '{}/boot'.format(self.target_dir))

        # error handling
        if not root_part:
            self.error = True
            Alert('Error!', 'Unable to find host OS in: {}'
                  .format(', '.join(disks))).do_alert()
            return (root_part, boot_part)

        if not boot_part:
            Alert('Information', 'Unable to find boot partition for {}'
                  .format(root_part)).do_alert()

        return (root_part, boot_part)

    def _get_part(self, part_info, pattern, target):
        """
        Find partition specified by pattern and mount it at target.
        This needs to return an empty string if it fails to find or mount the
        pattern so that it doesn't later break subprocess calls.
        """
        for part in part_info['partitions']:
            if part.get('type') and pattern in part['type']:
                part_found = part['name']
                try:
                    # try to mount partition
                    subprocess.call(['mount', part_found, target])
                    # only mount a linux root partition if it is Clear Linux OS
                    if 'Linux root' in pattern:
                        osf = '{}/usr/lib/os-release'.format(self.target_dir)
                        with open(osf, 'r') as os_release:
                            if 'clear-linux-os' in os_release.read():
                                for mount in ['/sys', '/proc']:
                                    subprocess.call(['mount', '-o', 'bind',
                                                     mount, target + mount])
                                return part_found
                        # if we have not returned at this point, unmount and
                        # keep looking, this is not Clear Linux.
                        subprocess.call(['umount', part_found])
                    # for other partition types, just return the name
                    else:
                        return part_found
                except Exception:
                    return ''

        # pattern not found in partition types
        return ''

    def _umount_host_disk(self, root_part, boot_part):
        """Unmount the os disk"""
        for mount in ['/sys', '/proc']:
            subprocess.call(['umount', self.target_dir + mount])
        subprocess.call(['umount', boot_part])
        subprocess.call(['umount', root_part])
        os.rmdir(self.target_dir)


class NetworkControl(object):
    """
    Record state of network configuration and create validated network
    configuration widgets. These widgets allow the user to define a static IP
    configuration with validated input while displaying the current detected
    settings on the installer for reference.
    """
    # pylint: disable=R0902
    def __init__(self, target, allow_reset=False, header=None, gen_en=False):
        left = 8
        self.target = target
        self.widgets = []
        # configure static ip settings section
        if header:
            self.static_header = urwid.Text(header)
        else:
            self.static_header = urwid.Text('Static IP Configuration')

        self.static_button = ister_button('Set static IP configuration',
                                          on_press=self.target,
                                          left=left)
        # go back two original widgets (through both Padding and AttrMap) to
        # set the label of the button.
        self.static_button.original_widget.original_widget.set_label(
            ('ex', 'Set static IP configuration'))
        # configure reset button
        if allow_reset:
            self.reset_button = ister_button(
                'Reset network to DHCP configuration',
                on_press=self._reset_network,
                left=left)
        # configure detected network settings section
        self.detected_header = urwid.Text('Detected network configuration on '
                                          'installer image')
        self.ifaceaddrs = None
        self.allow_generic_iface = gen_en
        self.iface_txt = 'Interface pattern: ' if gen_en else 'Interface: '
        self.static_ready = False
        self.static_edits = {}
        self.set_static_edits()
        self.update_widgets()
        self.reset = False

    def update_widgets(self):
        """
        Update widgets with latest network information that can be found
        """
        interface_ip = self.find_interface_ip()
        if interface_ip:
            interface_res = interface_ip[0]
            ip_res = interface_ip[1]
            mask_res = interface_ip[2]
        else:
            interface_res = 'none found'
            mask_res = 'none found'
            ip_res = 'none found'

        dns_res = find_dns()
        if not dns_res:
            dns_res = 'none found'

        if 'none found' in ''.join([interface_res, mask_res, ip_res, dns_res]):
            self.detected_header.set_text('Detected network configuration on '
                                          'installer image\nhit refresh to '
                                          'update')

        fmt = '{0:>20}'
        interface = urwid.Text(fmt.format('Interface: ') + interface_res)
        static_ip = urwid.Text(fmt.format('IP address: ') + ip_res)
        mask = urwid.Text(fmt.format('Subnet mask: ') + mask_res)
        dns = urwid.Text(fmt.format('DNS: ') + dns_res)
        # pylint: disable=E1103
        try:
            gateway = netifaces.gateways()['default'][netifaces.AF_INET][0]
        except Exception:
            gateway = 'none found'

        gateway = urwid.Text(fmt.format('Gateway: ') + gateway)
        self.title = urwid.Columns([self.static_header,
                                    self.detected_header])
        self.iface = urwid.Columns([self.interface_e, interface])
        self.static_ip = urwid.Columns([self.static_ip_e, static_ip])
        self.mask = urwid.Columns([self.mask_e, mask])
        self.gateway = urwid.Columns([self.gateway_e, gateway])
        self.dns = urwid.Columns([self.dns_e, dns])
        self.widgets = [self.title,
                        urwid.Divider(),
                        PopUpWidget('Show available interfaces',
                                    '\n'.join(interface_list()),
                                    'close'),
                        self.iface,
                        self.static_ip,
                        self.mask,
                        self.gateway,
                        self.dns,
                        urwid.Divider(),
                        self.static_button,
                        urwid.Divider()]

    def set_static_edits(self):
        """Set the edit captions for the static configuration section"""
        fmt = '{0:>20}'
        self.interface_e = urwid.Edit(fmt.format(self.iface_txt))
        if self.allow_generic_iface:
            self.interface_e.set_caption(
                ('success', '{0:>20}'.format(self.iface_txt)))
        self.static_ip_e = urwid.Edit(fmt.format('IP address: '))
        self.mask_e = urwid.Edit(fmt.format('Subnet mask: '))
        self.gateway_e = urwid.Edit(fmt.format('Gateway: '))
        self.dns_e = urwid.Edit(fmt.format('DNS: '))
        urwid.connect_signal(self.interface_e, 'change', self._activate_button)
        urwid.connect_signal(self.static_ip_e, 'change', self._activate_button)
        urwid.connect_signal(self.mask_e, 'change', self._activate_button)
        urwid.connect_signal(self.gateway_e, 'change', self._activate_button)
        urwid.connect_signal(self.dns_e, 'change', self._activate_button)

    def find_interface_ip(self):
        """Find active interface and ip address"""
        # pylint: disable=E1103
        addrs = {}
        mask = ''
        af_inet = netifaces.AF_INET
        for if_name in netifaces.interfaces():
            ifaddrs = netifaces.ifaddresses(if_name)
            if af_inet in ifaddrs:
                addrs = ifaddrs[af_inet][0]
                if addrs['addr'] and not addrs['addr'].startswith('127'):
                    addrs[if_name] = addrs['addr']
                    mask = addrs['netmask']

        self.ifaceaddrs = addrs
        for interface in addrs:
            if interface.startswith('e'):
                return (interface, addrs[interface], mask)

    def _activate_button(self, edit, new_text):
        # pylint: disable=too-many-branches
        # on a reset, these need to be manually cleared
        if self.reset:
            for key in self.static_edits:
                self.static_edits[key] = ''
            self.reset = False

        self.static_edits[edit] = new_text

        # wait for all required fields to be set updating the button
        # label with the new 'button' palette
        # `key` below is an object with a unique caption, so check against the
        # caption string.
        # Additionally, validate the edit text for valid interface/ip format,
        # make the caption green on a valid format.
        reqd_found = 0
        for key in self.static_edits:
            if not self.allow_generic_iface:
                if 'Interface' in key.caption and self.static_edits[key]:
                    if self.static_edits[key] in self.ifaceaddrs.keys():
                        reqd_found += 1
                        self.interface_e.set_caption(
                            ('success', '{0:>20}'.format(self.iface_txt)))
                    else:
                        self.interface_e.set_caption(
                            '{0:>20}'.format(self.iface_txt))

            if 'IP address' in key.caption and self.static_edits[key]:
                try:
                    ipaddress.ip_address(self.static_edits[key])
                    reqd_found += 1
                    self.static_ip_e.set_caption(
                        ('success', '{0:>20}'.format('IP address: ')))
                except Exception:
                    self.static_ip_e.set_caption(
                        '{0:>20}'.format('IP address: '))

            if 'Subnet mask' in key.caption and self.static_edits[key]:
                try:
                    ipaddress.ip_address(self.static_edits[key])
                    reqd_found += 1
                    self.mask_e.set_caption(
                        ('success', '{0:>20}'.format('Subnet mask: ')))
                except Exception:
                    self.mask_e.set_caption('{0:>20}'.format('Subnet mask: '))

            if 'Gateway' in key.caption and self.static_edits[key]:
                try:
                    ipaddress.ip_address(self.static_edits[key])
                    reqd_found += 1
                    self.gateway_e.set_caption(
                        ('success', '{0:>20}'.format('Gateway: ')))
                except Exception:
                    self.gateway_e.set_caption(('{0:>20}'.format('Gateway: ')))

            if 'DNS' in key.caption and self.static_edits[key]:
                try:
                    ipaddress.ip_address(self.static_edits[key])
                    self.dns_e.set_caption(
                        ('success', '{0:>20}'.format('DNS: ')))
                    reqd_found += 1
                except Exception:
                    self.dns_e.set_caption(
                        '{0:>20}'.format('DNS: '))

        reqd = 4 if self.allow_generic_iface else 5
        if reqd_found >= reqd:
            self.static_ready = True
            self.static_button.original_widget.original_widget.set_label(
                ('button', 'Set static IP configuration'))
        else:
            self.static_ready = False
            self.static_button.original_widget.original_widget.set_label(
                ('ex', 'Set static IP configuration'))

    def _reset_network(self, _):
        """Reset the network to original configuration by removing static
        network file and restarting network services"""
        try:
            os.remove('/etc/systemd/network/10-en-static.network')
        except FileNotFoundError:
            pass

        try:
            restart_networkd_resolved()
        except Exception as err:
            Alert('Error!', str(err)).do_alert()
            raise urwid.ExitMainLoop()

        # set necessary flags, then reset static edit text.
        self.static_ready = False
        self.reset = True
        self.set_static_edits()
        raise urwid.ExitMainLoop()


class NetworkRequirements(ProcessStep):
    """UI to verify and configure network connectivity to
    the version and content urls for the installer"""
    # pylint: disable=R0902
    def __init__(self, cur_step, tot_steps, content_url, version_url):
        super(NetworkRequirements, self).__init__()
        self.content_url = content_url
        self.version_url = version_url
        left = 8  # padding desired left of buttons, modifiable
        # configure proxy section
        self.proxy_header = urwid.Text('Proxy Settings')
        self.proxy_button = ister_button('Set proxy configuration',
                                         on_press=self._set_proxy,
                                         left=left)
        # initiate necessary instance variables
        self.progress = urwid.Text('Step {} of {}'.format(cur_step, tot_steps))
        self.https_proxy = None
        self.config = None
        self.nettime = False
        self.reset = False
        self.netcontrol = None
        # wait for network service to load the first time this screen is loaded
        self.timeout = ''
        if not network_service_ready():
            self.timeout = 'Network service timed out, hit refresh to retry'

    def handler(self, config):
        # make config an instance variable so we can copy proxy settings to it
        self.config = config
        self.netcontrol = NetworkControl(target=self._static_configuration,
                                         allow_reset=True,
                                         gen_en=True,
                                         header='Static IP Configuration '
                                                '(optional)')

        # normally much of this would belong in __init__, but we want it
        # refreshed every time the user refreshes/returns to the screen
        self.build_ui_widgets()
        self.build_ui()
        self._action = self.run_ui()
        if self._action == 'Refresh':
            # re-build the widgets
            return self._action

        # proxy settings may have been added during the self.run_ui() step,
        # copy our config instance back to the config.
        config = self.config
        return self._action

    def build_ui_widgets(self):
        """Build ui handler
        The last urwid Divider helps the tab movement to work"""
        if os.environ.get('https_proxy'):
            https_text = os.environ['https_proxy']
        else:
            https_text = ''

        fmt = '{0:>20}'
        self.https_proxy = urwid.Edit(fmt.format('HTTPS proxy: '), https_text)
        https_col = urwid.Columns(
            [self.https_proxy,
             urwid.Text(('ex', 'example: http://proxy.url.com:123'),
                        align='center')])
        if self.timeout:
            wired_req = urwid.Text(('warn', self.timeout))
        else:
            if self._network_connection():
                wired_req = urwid.Text(['* Connection to the update server: ',
                                        ('success', 'established')])
            else:
                wired_req = urwid.Text(['* Connection to the update server: ',
                                        ('warn', 'none detected, '),
                                        'install will fail'])

        self._ui_widgets = [self.progress,
                            urwid.Divider(),
                            wired_req,
                            urwid.Divider(),
                            self.proxy_header,
                            urwid.Divider(),
                            https_col,
                            urwid.Divider(),
                            self.proxy_button,
                            urwid.Divider()]
        self._ui_widgets.extend(self.netcontrol.widgets)
        if os.path.isfile('/etc/systemd/network/10-en-static.network'):
            self._ui_widgets.extend([self.netcontrol.reset_button,
                                     urwid.Divider()])

    def build_ui(self):
        self._ui = SimpleForm(u'Network Requirements',
                              self._ui_widgets, buttons=["Previous",
                                                         "Refresh",
                                                         "Next"])

    def run_ui(self):
        return self._ui.do_form(pop_ups=True)

    def _network_connection(self):
        """Check if connection to content and version urls are available"""
        # pylint: disable=E1103

        class Storage(object):
            """Storage class for pycurl"""
            # pylint: disable=R0903
            def __init__(self):
                self.buffer = []

            def store(self, buf):
                """Grab curl output"""
                self.buffer.append(buf.decode('utf-8'))

            def __str__(self):
                return ' '.join(self.buffer)

        def make_curl(url):
            """build curl object for url"""
            headers = Storage()
            curl = pycurl.Curl()
            curl.setopt(curl.URL, url)
            curl.setopt(curl.HEADER, 1)
            curl.setopt(curl.NOBODY, 1)
            curl.setopt(curl.WRITEFUNCTION, headers.store)
            curl.setopt(curl.TIMEOUT, 3)
            return headers, curl

        urls = {self.content_url: make_curl(self.content_url)}
        if self.content_url != self.version_url:
            urls[self.version_url] = make_curl(self.version_url)

        try:
            for (headers, curl) in urls.values():
                curl.perform()
                if '401' not in str(headers):
                    if not self.nettime:
                        self._set_hw_time(headers.buffer)
                else:
                    return False
        except Exception:
            return False

        return True

    def _set_hw_time(self, headers):
        for line in headers:
            if line.startswith('Date'):
                # remove Date: title
                line = line.replace('Date: ', '')
                # remove GMT and escaped chars from end of line, the date
                # command will default to UTC
                line = line.replace(' GMT\r\n', '')
                self.nettime = True
                try:
                    subprocess.call(['/usr/bin/date',
                                     '+%a, %d %b %Y %H:%M:%S',
                                     '--set={}'.format(line)])
                    subprocess.call(['hwclock', '--systohc'])
                except Exception as excep:
                    Alert('Error!',
                          'Unable to set system time, this may cause failures '
                          'with the Clear Linux OS Software Updater: {}'
                          .format(excep)).do_alert()

                break

    def _static_configuration(self, _):
        """
        Writes the configuration on /etc/systemd/network/10-en-static.network
        """
        if not self.netcontrol.static_ready:
            return

        try:
            ipaddress.ip_address(self.netcontrol.static_ip_e.get_edit_text())
            ipaddress.ip_address(self.netcontrol.gateway_e.get_edit_text())
        except ValueError:
            # the main loop is waiting on this method to exit so it can report
            # the error
            raise urwid.ExitMainLoop()

        path = '/etc/systemd/network/'
        if not os.path.exists(path):
            os.makedirs(path)

        with open(path + '10-en-static.network', 'w') as nfile:
            nfile.write('[Match]\n')
            nfile.write('Name={}\n\n'.format(
                self.netcontrol.interface_e.get_edit_text()))
            nfile.write('[Network]\n')
            nfile.write('Address={}/{}\n'.format(
                self.netcontrol.static_ip_e.get_edit_text(),
                compute_mask(self.netcontrol.mask_e.get_edit_text())))
            nfile.write('Gateway={}\n'.format(
                self.netcontrol.gateway_e.get_edit_text()))
            if self.netcontrol.dns_e.get_edit_text():
                nfile.write('DNS={}\n'.format(
                    self.netcontrol.dns_e.get_edit_text()))

        try:
            restart_networkd_resolved()
        except Exception as err:
            Alert('Error!', str(err)).do_alert()

        raise urwid.ExitMainLoop()

    def _set_proxy(self, _):
        """Set the user defined proxy for the installer in the template"""
        if self.https_proxy.get_edit_text():
            self.config['HTTPSProxy'] = self.https_proxy.get_edit_text()
            os.environ['https_proxy'] = self.https_proxy.get_edit_text()
        else:
            self.config.pop('HTTPSProxy', None)
            os.environ.pop('https_proxy', None)

        raise urwid.ExitMainLoop()


class TelemetryDisclosure(ProcessStep):
    # pylint: disable=R0902
    """UI to accept telemetry"""
    def __init__(self, cur_step, tot_steps):
        super(TelemetryDisclosure, self).__init__()
        self._msg_prefix = 'Allow the Clear Linux OS for Intel Architecture ' \
                           'to collect anonymous reports to improve system ' \
                           'stability? These reports only relate to ' \
                           'operating system details - no personally ' \
                           'identifiable information is collected.' \
                           '\n\n' \
                           'See http://clearlinux.org/features/telemetry ' \
                           'for more information.\n\n' \
                           'Intel\'s privacy policy can be found at ' \
                           'http://www.intel.com/privacy.\n\n'
        self._msg_suffix = 'Install the telemetrics bundle later if you '\
                           'change your mind.'
        self.progress = urwid.Text('Step {} of {}'.format(cur_step, tot_steps))
        self.message = urwid.Text(self._msg_prefix + self._msg_suffix)
        self.accept = urwid.CheckBox('Yes.',
                                     on_state_change=self._on_opt_in_change)

    def _on_opt_in_change(self, cbox, _):
        if cbox.get_state():
            cbox.set_label('Yes.')
            self.message.set_text(self._msg_prefix + self._msg_suffix)
        else:
            cbox.set_label('Yes. (Thank you!)')
            self.message.set_text(self._msg_prefix)
            # Shift focus past form body to nav bar
            self._ui._frame.focus_position += 1
            # Set focus to 'Next' button in column 1
            self._ui.nav.focus_position = 1

    def handler(self, config):
        """Handles all the work for the current UI"""
        if not self._ui_widgets:
            self.build_ui_widgets()

        if not self._ui:
            self.build_ui()

        if self._ui:
            self._action = self.run_ui()
        if self.accept.get_state():
            config['Bundles'].append('telemetrics')
        elif 'telemetrics' in config['Bundles']:
            config['Bundles'].remove('telemetrics')
        return self._action

    def run_ui(self):
        return self._ui.do_form()

    def build_ui_widgets(self):
        """Build ui handler
        The last urwid Divider helps to tab movement to work"""
        self._ui_widgets = [self.progress,
                            urwid.Divider(),
                            self.message,
                            urwid.Divider(),
                            self.accept,
                            urwid.Divider()]

    def build_ui(self):
        self._ui = SimpleForm(u'Stability Enhancement Program',
                              self._ui_widgets, buttons=["Previous", "Next"])


class StartInstaller(ProcessStep):
    """UI to select automatic or manual installation"""
    def __init__(self, cur_step, tot_steps):
        super(StartInstaller, self).__init__()
        self.choices = [u'Automatic', u'Manual(Advanced)', u'Exit']
        self._clicked = None
        self.progress = urwid.Text('Step {} of {}'.format(cur_step, tot_steps))

    def build_ui_widgets(self):
        self._ui_widgets = [self.progress, urwid.Divider()]
        for choice in self.choices:
            button = ister_button(choice,
                                  on_press=self._item_chosen,
                                  user_data=choice)
            self._ui_widgets.append(button)

    def _item_chosen(self, _, choice):
        self._clicked = choice
        raise urwid.ExitMainLoop()

    def build_ui(self):
        self._ui = SimpleForm(u'Choose Installation Type', self._ui_widgets,
                              buttons=['Previous'])

    def run_ui(self):
        return self._ui.do_form()

    def handler(self, config):
        if not self._ui_widgets:
            self.build_ui_widgets()

        if not self._ui:
            self.build_ui()

        self._clicked = ''

        if self._ui:
            self._action = self.run_ui()

        if self._clicked:
            self._action = self._clicked

        config['DisabledNewPartitions'] = False

        return self._action


class ConfigureCmdline(ProcessStep):
    """UI to add to kernel cmdline"""
    def __init__(self, cur_step, tot_steps):
        super(ConfigureCmdline, self).__init__()
        self.progress = urwid.Text('Step {} of {}'.format(cur_step, tot_steps))
        self.cmdline_field = urwid.Edit(
            u'{0:30}'.format('Append to cmdline (space-delimited): '),
            align='left')

    def handler(self, config):

        if not self._ui_widgets:
            self.build_ui_widgets()

        if not self._ui:
            self.build_ui()

        self._action = self.run_ui()
        if self._action == 'Next':
            # Just store as a string, since that is how it will be added to
            # the /etc/kernel/cmdline file by ister.py
            config['cmdline'] = self.cmdline_field.get_edit_text()

        return self._action

    def run_ui(self):
        return self._ui.do_form()

    def build_ui_widgets(self):
        desc = urwid.Text('console=tty0 console=ttyS0,115200n8 quiet '
                          'init=/usr/lib/systemd/systemd-bootchart '
                          'initcall_debug tsc=reliable no_timer_check '
                          'noreplace-smp kvm-intel.nested=1 '
                          'rootfstype=ext4,btrfs,xfs intel_iommu=igfx_off '
                          'cryptomgr.notests rcupdate.rcu_expedited=1 '
                          'i915.fastboot=1  rw rootwait')
        self._ui_widgets = [self.progress,
                            urwid.Divider(),
                            urwid.Text('Default kernel cmdline will be '
                                       'similar to this:'),
                            urwid.Divider(),
                            desc,
                            urwid.Divider(),
                            self.cmdline_field]

    def build_ui(self):
        self._ui = SimpleForm(u'Append to kernel cmdline', self._ui_widgets)


class ConfigureHostname(ProcessStep):
    """UI to gather the host's name"""
    def __init__(self, cur_step, tot_steps):
        super(ConfigureHostname, self).__init__()
        self.progress = urwid.Text('Step {} of {}'.format(cur_step, tot_steps))

    def handler(self, config):

        if not self._ui_widgets:
            self.build_ui_widgets()

        if not self._ui:
            self.build_ui()

        while True:
            self._action = self.run_ui()
            # Validate and ship out the hostname that was given to the configs
            if self._action == 'Next':
                config['Hostname'] = self._ui_widgets[2].get_edit_text()
                error = ister_wrapper('validate_hostname_template',
                                      config['Hostname'])
                if error is None:
                    break
                else:
                    alert = Alert(u'Error!', u'Hostname "{0}" is invalid'
                                  .format(config['Hostname']))
                    alert.do_alert()
                    continue
            else:
                break

        return self._action

    def run_ui(self):
        return self._ui.do_form()

    def build_ui_widgets(self):
        self._ui_widgets = [self.progress, urwid.Divider()]
        hostname_field = HostnameEdit(u'{0:30}'.format('Hostname:'),
                                      align='left',
                                      edit_text=u'clr')
        self._ui_widgets.append(hostname_field)

    def build_ui(self):
        self._ui = SimpleForm(u'Configuring Hostname', self._ui_widgets)


class ConfirmStep(ProcessStep):
    """UI to show a confirm box"""
    def __init__(self, title, body, cur_step=None, tot_steps=None):
        super(ConfirmStep, self).__init__()
        self._title = title
        if cur_step and tot_steps:
            self._body = 'Step {} of {}\n\n'.format(cur_step, tot_steps) + body
        else:
            self._body = body

    def handler(self, config):
        alert = Alert(self._title,
                      self._body,
                      labels=[u'No', u'Yes'])
        alert.do_alert()
        return alert.response


class ConfirmDiskWipe(ConfirmStep):
    """UI to display disk partitions and install confirmation"""
    def __init__(self, cur_step, tot_steps):
        self.text = ''
        self._cur_step = cur_step
        self._tot_steps = tot_steps
        super(ConfirmDiskWipe, self).__init__('Warning!', '')

    def handler(self, config):
        disk = '/dev/{0}'.format(config['PartitionLayout'][0]['disk'])
        self.text = ('Step {0} of {1}\n\n'
                     'All data on {2} will be erased during the installation '
                     '(final step). Do you want to proceed with {2}?\n\n'
                     .format(self._cur_step, self._tot_steps, disk))
        if self._cur_step == self._tot_steps:
            self.text += 'Selecting "Yes" will begin installation. This ' \
                         'step may take several minutes depending on '    \
                         'network speed.\n\n'
        disk_info = get_disk_info(disk)
        if not disk_info["partitions"]:
            self.text += "{0} contents: no partitions found.".format(disk)
        else:
            for part in disk_info["partitions"]:
                # leave space between part name and size so long partition
                # names such as mmcblk1p1 don't bump into the partition size
                self.text += '{0:10} {1:6}{2:28}\n'.format(part["name"],
                                                           part["size"],
                                                           part["type"])
        alert = Alert(self._title,
                      self.text,
                      labels=[u'No', u'Yes'])
        alert.do_alert()
        return alert.response


class PartitioningMenu(ProcessStep):
    """UI to select partitioning method"""
    def __init__(self, cur_step, tot_steps):
        super(PartitioningMenu, self).__init__()
        self.choices = {
            'Manual': 'Manually configure mounts and partitions',
            'Auto': 'Use default partition and mount scheme on target device',
        }
        self._clicked = None
        self.progress = urwid.Text('Step {} of {}'.format(cur_step, tot_steps))

    def build_ui_widgets(self):
        self._ui_widgets = [self.progress, urwid.Divider()]
        for key in sorted(self.choices):
            button = ister_button(self.choices[key],
                                  on_press=self._item_chosen,
                                  user_data=key)
            self._ui_widgets.append(button)

    def _item_chosen(self, _, choice):
        self._clicked = choice
        raise urwid.ExitMainLoop()

    def build_ui(self):
        self._ui = SimpleForm(u'Choose partitioning method', self._ui_widgets,
                              buttons=["Previous"])

    def run_ui(self):
        result = self._ui.do_form()
        return result

    def handler(self, config):
        if not self._ui_widgets:
            self.build_ui_widgets()

        if not self._ui:
            self.build_ui()

        self._clicked = ''

        if self._ui:
            self._action = self.run_ui()

        if self._clicked == 'Manual':
            config['DisabledNewPartitions'] = True
            self._action = self._clicked
        elif self._clicked == 'Auto':
            config['DisabledNewPartitions'] = False
            self._action = self._clicked

        return self._action


class SelectDeviceStep(ProcessStep):
    """UI to display the available disks"""
    def __init__(self, cur_step, tot_steps):
        super(SelectDeviceStep, self).__init__()
        self._clicked = None
        self._actions = None
        self.disks = []
        self.progress = 'Step {} of {}'.format(cur_step, tot_steps)

    def handler(self, config):
        # look every time, slow-loading or plug-in devices may show up late
        self.disks = get_list_of_disks()
        self.build_ui_widgets()

        self._ui = SimpleForm(u'Choose target device for installation',
                              self._ui_widgets, buttons=['Previous'])
        self._action = None
        self._clicked = None

        self._action = self.run_ui()
        if self._clicked == "Refresh":
            return self._clicked

        if self._clicked:
            keys = ['PartitionLayout',
                    'FilesystemTypes',
                    'PartitionMountPoints']
            for key in keys:
                for _iter in range(0, len(config[key])):
                    config[key][_iter]['disk'] = self._clicked
            self._action = 'Next'

        return self._action

    def run_ui(self):
        return self._ui.do_form()

    def _item_chosen(self, _, choice):
        self._clicked = choice
        raise urwid.ExitMainLoop()

    def _refresh(self, _):
        self._clicked = 'Refresh'
        raise urwid.ExitMainLoop()

    def build_ui_widgets(self):
        self._ui_widgets = [urwid.Text(self.progress)]
        if not self.disks:
            widget = urwid.Text(u"No free devices found.")
            self._ui_widgets.append(widget)
        else:
            for disk in self.disks:
                header = urwid.Text('/dev/{}'.format(disk))
                info = ''
                disk_info = get_disk_info('/dev/{}'.format(disk))
                if not disk_info["partitions"]:
                    info += 'no partitions found'
                else:
                    for part in disk_info["partitions"]:
                        # leave space between part name and size so long
                        # partition names such as mmcblk1p1 don't bump into the
                        # partition size
                        info += '{0:10} {1:6}{2:28}\n'.format(part["name"],
                                                              part["size"],
                                                              part["type"])

                info = urwid.Padding(urwid.Text(info), left=8)
                button = ister_button('Partition /dev/{}'.format(disk),
                                      on_press=self._item_chosen,
                                      user_data=disk)
                self._ui_widgets.extend([header,
                                         info,
                                         button,
                                         urwid.Divider()])

        self._ui_widgets.append(ister_button('Refresh device list',
                                             on_press=self._refresh))


class SelectMultiDeviceStep(SelectDeviceStep):
    """UI to display the available disks"""
    def handler(self, config):
        # look every time, slow-loading or plug-in devices may show up late
        self.disks = get_list_of_disks()
        config["Disks"] = self.disks
        other_options = ['Previous', 'Next']
        self.build_ui_widgets()
        self._ui = SimpleForm(u'Choose a drive to partition using cgdisk tool',
                              self._ui_widgets, buttons=other_options)
        self._clicked = None
        self._action = self.run_ui()
        if self._clicked:
            if self._clicked == 'Refresh':
                return self._clicked
            else:
                config["CurrentDisk"] = self._clicked
                return 'cgdisk'

        # get the list again, it might have changed
        config["Disks"] = get_list_of_disks()
        return self._action


class TerminalStep(ProcessStep):
    """UI to display cgdisk to manage partitioning"""
    def handler(self, config):
        term = Terminal(['cgdisk', '/dev/{0}'.format(config["CurrentDisk"])])
        term.main_loop()
        return 'Next'


class LogViewStep(ProcessStep):
    """UI to display log file"""
    def __init__(self, logfile):
        super(LogViewStep, self).__init__()
        self.logfile = logfile

    def handler(self, config):
        term = Terminal(['less', "-SN", self.logfile])
        term.main_loop()
        return 'Next'


class ShellStep(ProcessStep):
    """UI to display cgdisk to manage partitioning"""
    def handler(self, config):
        term = Terminal(['bash'])
        term.main_loop()
        return 'Next'


class SetMountEachStep(ProcessStep):
    """UI to gather the mount point of the selected partition"""
    def __init__(self, partition):
        super(SetMountEachStep, self).__init__()
        self._partition = partition
        self.edit_m_point = urwid.Edit('{0:30}'.format('Enter mount point:'))
        self.check_format = urwid.CheckBox('Format')
        self.options = []

    def handler(self, config):
        if not self._ui_widgets:
            self.build_ui_widgets()
        if not self._ui:
            self.build_ui()
        self.options = self._ui.button_labels
        # Searchs in the config if the partition already has a mount point
        for point in config:
            if config[point]['part'] == self._partition:
                self.edit_m_point.set_edit_text(point)
                self.check_format.set_state(config[point]['format'])
        self._action = self.run_ui()
        point = self.edit_m_point.get_edit_text()
        _format = self.check_format.get_state()
        if point == '/' and not _format:
            _format = True
            Alert('Information', "Format required for '/' partition, setting "
                  "format option...").do_alert()
        if self._action == 'Next' and point and point.startswith('/'):
            for key in list(config.keys()):
                if config[key]['part'] == self._partition:
                    del config[key]
            config[point] = {'part': self._partition, 'format': _format}
            return point
        return self._action

    def run_ui(self):
        return self._ui.do_form()

    def build_ui_widgets(self):
        self._ui_widgets = [self.edit_m_point,
                            urwid.Divider(),
                            self.check_format]

    def build_ui(self):
        title = u'Set mount point of {0}'.format(self._partition)
        self._ui = SimpleForm(title, self._ui_widgets)


class MountPointsStep(ProcessStep):
    """UI which displays the partitions of the selected disk"""
    # pylint: disable=too-many-instance-attributes
    def __init__(self, cur_step, tot_steps):
        super(MountPointsStep, self).__init__()
        self.progress = urwid.Text('Step {} of {}'.format(cur_step, tot_steps))
        self.display_fmt = '{0:12}{1:12}{2:30}{3:20}{4:6}'
        self.mount_d = {}
        self.choices = None

    def handler(self, config):
        # pylint: disable=R0914
        mount_d = self.mount_d
        self.choices = self._get_partitions(config)
        # if the user went back to cgdisk and deleted a partition, we have to
        # detect that here. After we get a list to remove, remove each key
        # (can't do it on the fly because it resizes the mount_d dict)
        removed = []
        for disk in mount_d:
            if not any(mount_d[disk]['part'] in chc for chc in self.choices):
                removed.append(disk)

        for disk in removed:
            mount_d.pop(disk, None)

        other_options = ['Previous', 'Next']
        required_mounts = ['/', '/boot']
        validated = False
        while not validated:
            self.build_ui_widgets()
            self._ui = SimpleForm(u'Set mount points',
                                  self._ui_widgets, buttons=other_options)
            self._clicked = None
            self._action = self._ui.do_form()
            if self._clicked:
                partition = self._clicked.split()[0]
                size = self._clicked.split()[1]
                part_type = self._clicked[24:54].strip()
                set_mount_step = SetMountEachStep(partition)
                point = set_mount_step.handler(mount_d)
                if point not in set_mount_step.options:
                    self._erase_dup_mount(point, partition)
                    idx = self.choices.index(self._clicked)
                    _format = 'Yes' if mount_d[point]['format'] else ''
                    self.choices[idx] = self.display_fmt.format(partition,
                                                                size,
                                                                part_type,
                                                                point,
                                                                _format)
            elif self._action == 'Next':
                validated = True
                for mount in required_mounts:
                    if mount not in mount_d:
                        validated = False
                        (Alert(u'Error!',
                               u'Missing "{0}" mount point'.format(mount))
                         .do_alert())
                        break
            else:
                return self._action
        self._save_config(config, mount_d)
        search_swap(self.choices, config, mount_d)
        exc = ister_wrapper('validate_disk_template', config)
        if exc is not None:
            return exc
        return self._action

    def _erase_dup_mount(self, point, part):
        for idx, chc in enumerate(self.choices):
            if '{} '.format(point) in chc and '{} '.format(part) not in chc:
                self.choices[idx] = \
                    (self.choices[idx]
                     .replace(point, ' ' * len(point))
                     .replace('Yes', '   '))

    def _item_chosen(self, _, choice):
        self._clicked = choice
        raise urwid.ExitMainLoop()

    def build_ui_widgets(self, *_):
        self._ui_widgets = [self.progress]
        if not self.choices:
            widget = urwid.Text(u"No partitions found.")
            self._ui_widgets.append(widget)
        else:
            wgt = urwid.Text("  " + self.display_fmt.format("Disk",
                                                            "Size",
                                                            "Partition type",
                                                            "Mount point",
                                                            "Format?"))
            self._ui_widgets.append(wgt)
            for part in self.choices:
                button = ister_button(part,
                                      on_press=self._item_chosen,
                                      user_data=part)
                self._ui_widgets.append(button)

    def _save_config(self, config, mount_d):
        config['PartitionLayout'] = list()
        config['FilesystemTypes'] = list()
        config['PartitionMountPoints'] = list()
        for point in mount_d:
            _type = 'EFI' if point == '/boot' else 'linux'
            part = mount_d[point]['part']
            # first try to set using lsblk -no pkname part
            disk = get_part_devname(part)
            # if that fails, alert and fallback to old
            # (unreliable) method
            if not disk:
                Alert('Partition error',
                      'Unable to detect device name for {}. '
                      'Falling back to path parsing. This method is '
                      'unreliable and may result in a failed install.'
                      .format(part)).do_alert()
                disk = ''.join(x for x in part if not x.isdigit())

            part = part[len(disk):]
            # strip off prefix if it exists and save for grep command below
            prefix = part[0] if not part[0].isdigit() else ''
            part = part.lstrip(prefix)

            config['PartitionLayout'].append({
                'disk': disk,
                'partition': part,
                'size': '1M',
                'type': _type})
            _type = 'vfat' if point == '/boot' else 'ext4'
            config['FilesystemTypes'].append({
                'disk': disk,
                'partition': part,
                'type': _type})
            if not mount_d[point]['format']:
                if 'TYPE="' in subprocess.check_output(
                        'blkid | grep {0}'
                        .format(disk+prefix+part), shell=True).decode('utf-8'):
                    config['FilesystemTypes'][-1]['disable_format'] = True
            config['PartitionMountPoints'].append({
                'disk': disk,
                'partition': part,
                'mount': point})
            self.mount_d = mount_d

    def _get_partitions(self, config):
        result = list()
        for disk in config['Disks']:
            disk_info = get_disk_info('/dev/{0}'.format(disk))
            for part in disk_info['partitions']:
                name = disk + part['number']
                mount = ''
                fmt = ''
                # look for partition name buried in the dict then set mount
                # point and format if it has already been set
                for mnt in self.mount_d:
                    if self.mount_d[mnt]['part'] == name:
                        mount = mnt
                        if self.mount_d[mnt]['format']:
                            fmt = 'Yes'

                result.append(self.display_fmt.format(name,
                                                      part['size'],
                                                      part['type'],
                                                      mount, fmt))
        return result


class BundleSelectorStep(ProcessStep):
    """UI which displays the bundle list to be installed"""
    # pylint: disable=too-many-instance-attributes
    def __init__(self, cur_step=None, tot_steps=None):
        super(BundleSelectorStep, self).__init__()
        self.bundles = [{'name': 'editors',
                         'desc': 'Popular text editors (terminal-based)'},
                        {'name': 'user-basic',
                         'desc': 'Captures most console work flows'},
                        {'name': 'openssh-server',
                         'desc': 'Secure shell server for remote login'},
                        {'name': 'desktop-autostart',
                         'desc': 'UI that automatically starts on boot'},
                        {'name': 'dev-utils',
                         'desc': 'Utilities to assist application '
                                 'development'}]
        self.default_bundles = [{'name': 'network-basic',
                                 'desc': 'Run network utilities and modify '
                                         'network settings'},
                                {'name': 'sysadmin-basic',
                                 'desc': 'Run common utilities useful for '
                                         'managing a system'}]
        self.required_bundles = []
        self.default_set = False
        self.sysadmin_basic_state = True
        if cur_step and tot_steps:
            self.progress = urwid.Text('Step {} of {}'.format(cur_step,
                                                              tot_steps))

    def handler(self, config):
        # required bundles list can change depending on configuration
        self.required_bundles = required_bundles(config)
        # find which lists sysadmin-basic is in
        sysadmin_reqd = any(bundle['name'] == 'sysadmin-basic'
                            for bundle in self.required_bundles)
        sysadmin_bundle = any(bundle['name'] == 'syadmin-basic'
                              for bundle in self.bundles)
        sysadmin_def = any(bundle['name'] == 'sysadmin-basic'
                           for bundle in self.default_bundles)
        sysadmin_basic = {'name': 'sysadmin-basic',
                          'desc': 'Run common utilities useful for managing a '
                                  'system'}
        # if syadmin-basic is in the required_bundles list, it must be removed
        # from the other bundle lists so it is not displayed multiple times
        if sysadmin_reqd:
            self.default_bundles = [
                bundle for bundle in self.default_bundles
                if not bundle.get('name') == 'sysadmin-basic']
            self.bundles = [bundle for bundle in self.bundles
                            if not bundle.get('name') == 'sysadmin-basic']
        # if sysadmin-basic is not in any of the lists, add it to the main
        # bundles list. Do not add it to the default_bundles list because
        # default_bundles is only processed the first time a user reaches this
        # screen.
        elif not (sysadmin_reqd or sysadmin_bundle or sysadmin_def):
            self.bundles.append(sysadmin_basic)

        # The first time a user reaches this screen, the remaining items in
        # default_bundles should be added to self.bundles and config['Bundles']
        # so they will be pre-selected. This list may or may not include
        # sysadmin-basic
        if not self.default_set:
            for bundle in self.default_bundles:
                config['Bundles'].append(bundle['name'])
            self.bundles.extend(self.default_bundles)
            self.default_set = True

        # build widgets and ui each time in case user went back and opted out
        # of telemetrics
        self.build_ui_widgets(config)
        self.build_ui()
        self._action = self.run_ui()
        wgen = (w for w in self._ui_widgets[2:]
                if isinstance(w, urwid.Columns))
        for widget in wgen:
            for content in widget.contents:
                if isinstance(content[0], urwid.CheckBox):
                    bundle = content[0].get_label()
                    bundle = bundle.split()[0]
                    if content[0].get_state():
                        if bundle not in config['Bundles']:
                            config['Bundles'].append(bundle)
                    else:
                        if bundle in config['Bundles']:
                            config['Bundles'].remove(bundle)

        # update only if user had chance to unselect - the user had a chance to
        # unselect the bundle if it is not in the required_bundles list.
        if not any(bundle['name'] == 'sysadmin-basic'
                   for bundle in self.required_bundles):
            self.sysadmin_basic_state = 'sysadmin-basic' in config['Bundles']

        return self._action

    def run_ui(self):
        return self._ui.do_form()

    def build_ui_widgets(self, config):
        self._ui_widgets = []
        if self.progress:
            self._ui_widgets = [self.progress, urwid.Divider()]
        self._ui_widgets.extend([urwid.Text('Select the bundles to install:'),
                                 urwid.Divider()])
        for bundle in self.bundles:
            state = True if bundle['name'] in config['Bundles'] else False
            # sysadmin-basic state needs to be handled differently.
            # the state must be remembered in case the user changes their mind
            # a couple times, causing the bundle to be added and removed from
            # the required bundles list.
            if bundle['name'] == 'sysadmin-basic':
                state = self.sysadmin_basic_state
            check = urwid.CheckBox(bundle['name'], state=state)
            desc_text = urwid.Text(bundle['desc'])
            column = urwid.Columns([check, ('weight', 2, desc_text)])
            self._ui_widgets.append(column)

        self._ui_widgets.extend([urwid.Divider(),
                                 urwid.Text('--- required ---')])
        for bundle in self.required_bundles:
            text_name = urwid.Text('    {0}'.format(bundle['name']))
            text_desc = urwid.Text(bundle['desc'])
            column = urwid.Columns([text_name, ('weight', 2, text_desc)])
            self._ui_widgets.append(column)

    def build_ui(self):
        self._ui = SimpleForm(u'Bundle selector', self._ui_widgets)


class ConfirmUserMenu(ProcessStep):
    """UI to confirm user creation"""
    def __init__(self, cur_step, tot_steps):
        super(ConfirmUserMenu, self).__init__()
        self.choices = {
            'mkuser': 'Create an administrative user',
            'nouser': 'No user creation (login as root)',
        }
        self._clicked = None
        self.progress = urwid.Text('Step {} of {}'.format(cur_step, tot_steps))

    def build_ui_widgets(self):
        self._ui_widgets = [self.progress, urwid.Divider()]
        for key in sorted(self.choices):
            button = ister_button(self.choices[key],
                                  on_press=self._item_chosen,
                                  user_data=key)
            self._ui_widgets.append(button)

    def _item_chosen(self, _, choice):
        self._clicked = choice
        raise urwid.ExitMainLoop()

    def build_ui(self):
        self._ui = SimpleForm(u'User configuration', self._ui_widgets,
                              buttons=["Previous"])

    def run_ui(self):
        result = self._ui.do_form()
        return result

    def handler(self, config):
        if not self._ui_widgets:
            self.build_ui_widgets()

        if not self._ui:
            self.build_ui()

        self._clicked = None

        if self._ui:
            self._action = self.run_ui()

        if self._clicked:
            self._action = self._clicked

        if self._action == 'nouser':
            config['Users'] = []

        return self._action


class UserConfigurationStep(ProcessStep):
    """UI to gather the user info"""
    # pylint: disable=too-many-instance-attributes
    def __init__(self, cur_step, tot_steps):
        super(UserConfigurationStep, self).__init__()
        fmt = '{0:>25}'
        self.edit_name = urwid.Edit(fmt.format('First Name: '))
        self.edit_lastname = urwid.Edit(fmt.format('Last Name: '))
        self.edit_username = UsernameEdit(fmt.format('* Username: '))
        self.edit_password = urwid.Edit(fmt.format('* Password: '),
                                        mask='*')
        self.edit_confirm_p = urwid.Edit(fmt.format('* Confirm password: '),
                                         mask='*')
        self.sudo = urwid.CheckBox('Add user to sudoers?')
        self.required = urwid.Text('* = required field')
        urwid.connect_signal(self.edit_name, 'change', self._username_handler)
        urwid.connect_signal(self.edit_lastname,
                             'change',
                             self._username_handler)
        self.progress = urwid.Text('Step {} of {}'.format(cur_step, tot_steps))

    def _username_handler(self, edit, new_text):
        new_text = new_text.lower()
        name_text = self.edit_name.get_edit_text()[0:1].lower()
        lastname_text = self.edit_lastname.get_edit_text()[0:8].lower()
        if edit == self.edit_name:
            name_text = new_text[0:1]
        else:
            lastname_text = new_text[0:8]

        # first letter of suggested username must be valid
        if not re.match('[a-z_]', name_text):
            name_text = ''

        # rest of suggested username must be valid
        for letter in lastname_text:
            if not re.match('[a-z0-9_-]', letter):
                lastname_text = lastname_text.replace(letter, '')

        self.edit_username.set_edit_text(name_text + lastname_text)

    def _set_fullname(self, user):
        fname = self.edit_name.get_edit_text()
        lname = self.edit_lastname.get_edit_text()
        if fname or lname:
            if fname and lname:
                user['fullname'] = '{} {}'.format(fname, lname)
            else:
                user['fullname'] = fname or lname

    def handler(self, config):
        if not self._ui_widgets:
            self.build_ui_widgets()
        if not self._ui:
            self.build_ui()
        while True:
            self._action = self.run_ui()
            if self._action == 'Previous':
                return self._action
            else:
                password = self.edit_password.get_edit_text()
                username = self.edit_username.get_edit_text()
                comp = self.edit_confirm_p.get_edit_text()
                if len(username) > 32 or len(username) < 3:
                    Alert('Error!',
                          'Username error. Max length = 32. '
                          'Min length = 3.').do_alert()
                elif password == '':
                    Alert('Error!', 'Missing password').do_alert()
                elif password != comp:
                    Alert('Error!', 'The passwords do not match').do_alert()
                else:
                    break
                continue
        tmp = dict()
        tmp['username'] = self.edit_username.get_edit_text()
        tmp['password'] = crypt.crypt(self.edit_password.get_edit_text())
        tmp['sudo'] = self.sudo.get_state()
        self._set_fullname(tmp)

        config['Users'] = [tmp]
        return self._action

    def run_ui(self):
        return self._ui.do_form()

    def build_ui_widgets(self):
        """Build ui handler
        The last urwid Divider helps to tab movement to work"""
        self._ui_widgets = [self.progress,
                            urwid.Divider(),
                            self.edit_name,
                            urwid.Divider(),
                            self.edit_lastname,
                            urwid.Divider(),
                            self.edit_username,
                            urwid.Divider(),
                            self.edit_password,
                            urwid.Divider(),
                            self.edit_confirm_p,
                            urwid.Divider(),
                            self.sudo,
                            urwid.Divider(),
                            self.required,
                            urwid.Divider()]

    def build_ui(self):
        self._ui = SimpleForm(u'User configuration', self._ui_widgets)


class ConfirmDHCPMenu(ProcessStep):
    """UI to confirm static ip configuration"""
    def __init__(self, cur_step, tot_steps):
        super(ConfirmDHCPMenu, self).__init__()
        self.choices = {
            'dhcp': 'Use DHCP',
            'staticip': 'Use static IP configuration',
        }
        self._clicked = None
        self.progress = urwid.Text('Step {} of {}'.format(cur_step, tot_steps))

    def build_ui_widgets(self):
        self._ui_widgets = [self.progress, urwid.Divider()]
        for key in sorted(self.choices):
            button = ister_button(self.choices[key],
                                  on_press=self._item_chosen,
                                  user_data=key)
            self._ui_widgets.append(button)

    def _item_chosen(self, _, choice):
        self._clicked = choice
        raise urwid.ExitMainLoop()

    def build_ui(self):
        self._ui = SimpleForm(u'Network configuration',
                              self._ui_widgets,
                              buttons=["Previous"])

    def run_ui(self):
        return self._ui.do_form()

    def handler(self, config):
        if not self._ui_widgets:
            self.build_ui_widgets()

        if not self._ui:
            self.build_ui()

        self._clicked = None

        if self._ui:
            self._action = self.run_ui()

        if self._clicked:
            self._action = self._clicked

        # remove the Static_IP field if it was set but the user decided to use
        # DHCP instead
        if self._action == 'dhcp':
            config.pop('Static_IP', None)

        return self._action


class StaticIpStep(ProcessStep):
    # pylint: disable=too-many-instance-attributes
    """UI to gather the static ip configuration"""
    def __init__(self, cur_step, tot_steps):
        super(StaticIpStep, self).__init__()
        self.netcontrol = None
        self.progress = urwid.Text('Step {} of {}'.format(cur_step, tot_steps))
        self.iface_s = ''
        self.static_ip_s = ''
        self.mask_s = ''
        self.gateway_s = ''
        self.dns_s = ''
        self.config = {}
        self.iface_res = ''
        self.ip_res = ''
        self.mask_res = ''
        self.dns_res = ''
        self.gate_r = ''

    def _save_config(self, _):
        """Save static IP configuration to config dict"""
        if not self.netcontrol.static_ready:
            return
        tmp = dict()
        tmp['address'] = '{}/{}'.format(
            self.netcontrol.static_ip_e.get_edit_text(),
            compute_mask(self.netcontrol.mask_e.get_edit_text()))
        tmp['gateway'] = self.netcontrol.gateway_e.get_edit_text()
        tmp['dns'] = self.netcontrol.dns_e.get_edit_text()
        tmp['iface'] = self.netcontrol.interface_e.get_edit_text() or 'en*'
        self.config['Static_IP'] = tmp
        raise urwid.ExitMainLoop()

    def handler(self, config):
        self.config = config
        self.netcontrol = NetworkControl(allow_reset=True,
                                         target=self._save_config,
                                         gen_en=True)
        if config.get('Static_IP'):
            self.setup_saved(config)
        else:
            self.clear_saved()

        # Only pre-populate with local network settings if static has been
        # configured by the user and there is no saved 'Static_IP' in the
        # install configuration.
        det = static_set() and not config.get('Static_IP')
        if det:
            # gather network data from installer image
            self.find_network()

        self.setup_netcontrol(det=det)
        self.build_ui_widgets()
        self.build_ui()
        self._action = self.run_ui()
        config = self.config
        if self._action == 'Next' and not config.get('Static_IP'):
            msg = 'Please set static IP configuration before continuing.'
            Alert('Information', msg).do_alert()
            return ''

        return self._action

    def setup_saved(self, config):
        """
        Record pre-existing configuration for pre-population of fields and
        confirmation message
        """
        static_config = config['Static_IP']
        ip_config = ipaddress.ip_interface(static_config.get('address'))
        self.iface_s = static_config.get('iface')
        self.static_ip_s = str(ip_config.ip)
        self.mask_s = str(ip_config.netmask)
        self.gateway_s = static_config.get('gateway')
        self.dns_s = static_config.get('dns')

    def clear_saved(self):
        """Clear saved information if it is no longer present in config"""
        self.iface_s = ''
        self.static_ip_s = ''
        self.mask_s = ''
        self.gateway_s = ''
        self.dns_s = ''

    def find_network(self):
        """
        Find the network information to pre-populate the static configuration
        fields.
        """
        if_ip = self.netcontrol.find_interface_ip()
        self.iface_res = if_ip[0] if if_ip else ''
        self.ip_res = if_ip[1] if if_ip else ''
        self.mask_res = if_ip[2] if if_ip else ''
        self.dns_res = find_dns() or ''
        # pylint: disable=E1103
        try:
            self.gate_r = netifaces.gateways()['default'][netifaces.AF_INET][0]
        except Exception:
            self.gate_r = ''

    def setup_netcontrol(self, det=False):
        """Pre-populate edit fields with saved data if available"""
        self.netcontrol.interface_e.set_edit_text(self.iface_res if det
                                                  else self.iface_s)
        self.netcontrol.static_ip_e.set_edit_text(self.ip_res if det
                                                  else self.static_ip_s)
        self.netcontrol.mask_e.set_edit_text(self.mask_res if det
                                             else self.mask_s)
        self.netcontrol.gateway_e.set_edit_text(self.gate_r if det
                                                else self.gateway_s)
        self.netcontrol.dns_e.set_edit_text(self.dns_res if det
                                            else self.dns_s)

    def run_ui(self):
        return self._ui.do_form(pop_ups=True)

    def build_ui_widgets(self):
        fmt = '{0:>20}'
        self._ui_widgets = [self.progress,
                            urwid.Divider()]
        self._ui_widgets.extend(self.netcontrol.widgets)

        if self.static_ip_s:
            self._ui_widgets.extend(
                [urwid.Text('Saved Configuration'),
                 urwid.Divider(),
                 urwid.Text(fmt.format('Interface: ') + self.iface_s),
                 urwid.Text(fmt.format('IP address: ') + self.static_ip_s),
                 urwid.Text(fmt.format('Subnet mask: ') + self.mask_s),
                 urwid.Text(fmt.format('Gateway: ') + self.gateway_s),
                 urwid.Text(fmt.format('DNS: ') + self.dns_s)])

    def build_ui(self):
        self._ui = SimpleForm(u'Network configuration', self._ui_widgets)


class RunInstallation(ProcessStep):
    """Class to break the loop and proceed with the installation"""
    pass


class WatchableProcess(threading.Thread):
    """Thread class to watch output of system command"""
    def __init__(self, cmd):
        self.poll = lambda *x: None
        self.cmd = cmd
        self.process = None
        self.output = []
        self.done = False
        threading.Thread.__init__(self)

    def run(self):
        self.process = subprocess.Popen(self.cmd,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE,
                                        bufsize=1)
        self.poll = self.process.poll
        lines = self.process.stdout
        for line in lines:
            self.output.append(line.decode('utf-8').strip())
        self.done = True


class Installation(object):
    """Main object for installer ui"""

    # pylint: disable=too-many-instance-attributes

    def __init__(self, *args, **kwargs):
        # args unused for now
        del args
        self.args = kwargs
        self._steps = list()
        self.start = SplashScreen()
        self._init_actions()
        self.current_w = None
        self.logger = logging.getLogger('ister_gui')
        self.template_path = '/var/log/ister_gui.log'
        _fh = logging.FileHandler(self.template_path)
        _fh.setLevel(logging.DEBUG)
        _formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        _fh.setFormatter(_formatter)
        self.logger.addHandler(_fh)
        self.logger.setLevel(logging.DEBUG)
        try:
            with open('/etc/ister.json') as infile:
                json_string = infile.read()
                self.installation_d = json.loads(json_string)
        except Exception as exep:
            self.logger.error(exep)
            self._exit(-1, 'Template file does not exist')

    def _init_actions(self):
        # pylint: disable=too-many-locals
        # pylint: disable=too-many-statements

        # current is the generator representing the current step.
        # calling next(current) advances the generator and returns an integer.
        # For steps with multiple screens, this integer must be saved to
        # another variable to be used more than once (meta_step).
        current = itertools.count(start=1)
        # auto install assumed so the total is lower
        total = 6
        # Select keyboard layout
        keyboard_select = KeyboardSelection()

        # Configure network for installer
        network_requirements = NetworkRequirements(next(current), total,
                                                   self.args['contenturl'],
                                                   self.args['versionurl'])

        # Choose action (install/repair/shell)
        choose_action = ChooseAction(next(current), total)

        # Telemetry opt-in
        telem_disclosure = TelemetryDisclosure(next(current), total)

        # Start installation (manual/automatic)
        startmenu = StartInstaller(next(current), total)

        # Select target device (for automatic install)
        automatic_device = SelectDeviceStep(next(current), total)

        # Confirm disk wipe
        confirm_disk_wipe = ConfirmDiskWipe(next(current), total)

        # The manual install route starts at step 5. The total must be updated
        # to the total in the manual path.
        current = itertools.count(start=5)
        total = 13

        # Partition menu
        part_menu = PartitioningMenu(next(current), total)

        # Partition meta-step
        meta_step = next(current)
        manual_part_device = SelectMultiDeviceStep(meta_step, total)
        manual_nopart_device = SelectDeviceStep(meta_step, total)

        # cgdisk terminal
        terminal_cgdisk = TerminalStep()

        # Mount points meta-step
        meta_step = next(current)
        set_mount_points = MountPointsStep(meta_step, total)
        confirm_disk_wipe2 = ConfirmDiskWipe(meta_step, total)

        # Configure kernel cmdline
        config_cmdline = ConfigureCmdline(next(current), total)

        # Configure hostname
        config_hostname = ConfigureHostname(next(current), total)

        # User configuration meta-step
        meta_step = next(current)
        confirm_user = ConfirmUserMenu(meta_step, total)
        user_configuration = UserConfigurationStep(meta_step, total)

        # Select bundle
        bundle_selector = BundleSelectorStep(next(current), total)

        # Networking meta-step
        meta_step = next(current)
        confirm_dhcp = ConfirmDHCPMenu(meta_step, total)
        static_ip_config = StaticIpStep(meta_step, total)

        # Confirm installation
        setup_msg = 'Setup is complete. Do you want to begin installation? '  \
                    'This step may take several minutes depending on '        \
                    'bundles selected and network speed.'
        confirm_installation = ConfirmStep('Attention!',
                                           setup_msg,
                                           next(current), total)
        run = RunInstallation()

        self.start.set_action('Next', keyboard_select)
        keyboard_select.set_action('Next', network_requirements)
        keyboard_select.set_action('Previous', self.start)
        network_requirements.set_action('Next', choose_action)
        network_requirements.set_action('Refresh', network_requirements)
        network_requirements.set_action('Previous', keyboard_select)
        network_requirements.set_action('', network_requirements)
        choose_action.set_action('Install', telem_disclosure)
        choose_action.set_action('return', choose_action)
        choose_action.set_action('Previous', network_requirements)
        telem_disclosure.set_action('Previous', choose_action)
        telem_disclosure.set_action('Next', startmenu)
        startmenu.set_action('Previous', telem_disclosure)
        startmenu.set_action('Automatic', automatic_device)
        automatic_device.set_action('Previous', startmenu)
        automatic_device.set_action('Refresh', automatic_device)
        automatic_device.set_action('Next', confirm_disk_wipe)
        confirm_disk_wipe.set_action('No', automatic_device)
        confirm_disk_wipe.set_action('Yes', run)
        startmenu.set_action('Manual(Advanced)', part_menu)
        part_menu.set_action('Manual', manual_part_device)
        part_menu.set_action('Auto', manual_nopart_device)
        part_menu.set_action('Previous', startmenu)
        manual_part_device.set_action('Previous', part_menu)
        manual_part_device.set_action('cgdisk', terminal_cgdisk)
        manual_part_device.set_action('Refresh', manual_part_device)
        manual_part_device.set_action('Next', set_mount_points)
        terminal_cgdisk.set_action('Next', manual_part_device)
        set_mount_points.set_action('Previous', manual_part_device)
        set_mount_points.set_action('Next', config_cmdline)
        manual_nopart_device.set_action('Previous', part_menu)
        manual_nopart_device.set_action('Refresh', manual_nopart_device)
        manual_nopart_device.set_action('Next', confirm_disk_wipe2)
        confirm_disk_wipe2.set_action('No', manual_nopart_device)
        confirm_disk_wipe2.set_action('Yes', config_cmdline)
        config_cmdline.set_action('Previous', part_menu)
        config_cmdline.set_action('Next', config_hostname)
        config_hostname.set_action('Previous', config_cmdline)
        config_hostname.set_action('Next', confirm_user)
        confirm_user.set_action('mkuser', user_configuration)
        confirm_user.set_action('nouser', bundle_selector)
        confirm_user.set_action('Previous', config_hostname)
        user_configuration.set_action('Previous', confirm_user)
        user_configuration.set_action('Next', bundle_selector)
        bundle_selector.set_action('Previous', confirm_user)
        bundle_selector.set_action('Next', confirm_dhcp)
        confirm_dhcp.set_action('dhcp', confirm_installation)
        confirm_dhcp.set_action('staticip', static_ip_config)
        confirm_dhcp.set_action('Previous', bundle_selector)
        static_ip_config.set_action('Previous', confirm_dhcp)
        static_ip_config.set_action('', static_ip_config)
        static_ip_config.set_action('Next', confirm_installation)
        confirm_installation.set_action('No', confirm_dhcp)
        confirm_installation.set_action('Yes', run)

    def _exit(self, int_code, message=None, title=None, reboot=False):
        """UI to display error messages"""
        if int_code != 0:
            if message is None:
                message = 'An error ocurred during the installation, ' \
                          'please check the log file'
            if title is None:
                title = 'Error!'
            alert = Alert(title, message)
            alert.do_alert()
        if self.args['dry_run'] or self.args['exit_after']:
            exit()
        if reboot:
            subprocess.call('reboot')
        subprocess.call('poweroff')

    def run(self):
        """Starts up the installer ui"""
        pprint.PrettyPrinter(indent=4)
        step = self.start
        # initiate the bundles list at the start, not in a screen, so it does
        # not get overwritten when a user returns to that screen.
        self.installation_d['Bundles'] = list()
        i = 0
        while not isinstance(step, RunInstallation):
            action = step.handler(self.installation_d)
            self.logger.debug("Stepping to % screen", type(step).__name__)
            self.logger.debug(self.installation_d)
            if action == 'Abort' or action == 'Exit':
                self._exit(0)
            elif isinstance(action, Exception):
                self._exit(-1, str(action))
            step = step.get_next_step(action)
            _ = pprint.pformat(step, indent=4)
            i += 1
        # Make sure that required bundles are included independently of
        # installation method.
        # the required bundles depend on the configuration in installation_d
        for bundle in required_bundles(self.installation_d):
            if bundle["name"] not in self.installation_d["Bundles"]:
                self.installation_d["Bundles"].append(bundle["name"])
        self.automatic_install()

    def automatic_install(self):
        """Initial installation method, use the default template unmodified"""
        with open('/tmp/template.json', 'w') as template:
            self.logger.debug(self.installation_d)
            template.write(json.dumps(self.installation_d))
        text = ""
        title = u'Automatic installation of Clear Linux OS {0}' \
                .format(self.installation_d['Version'])
        Alert(title, 'Starting....', block=False).do_alert()
        if self.args['no_install'] or self.args['dry_run']:
            self._exit(0, 'dry run - actual install skipped.')
        supported = [
            {'name': 'contenturl', 'out': '--contenturl={0}'},
            {'name': 'versionurl', 'out': '--versionurl={0}'},
            {'name': 'format', 'out': '--format={0}'}]
        flags = [item['out'].format(self.args[item['name']])
                 for item in supported if self.args[item['name']] is not None]
        ister_log = '/var/log/ister.log'
        ister_cmd = [sys.executable,
                     '/usr/bin/ister.py',
                     '-t',
                     '/tmp/template.json']
        ister_cmd.extend(flags)
        ister_cmd.extend(['-l', ister_log])
        self.logger.debug(' '.join(ister_cmd))
        watch = WatchableProcess(ister_cmd)
        watch.start()
        current = 0
        while not watch.done:
            if len(watch.output) > current:
                current = len(watch.output)
                text = '\n'.join(watch.output[-10:])
                Alert(title, text, block=False).do_alert()
        Alert(title, text).do_alert()

        if not watch.poll():
            message = ('Successful installation, the system will be rebooted\n'
                       'please remove installation media after restart')
            Alert(title, message).do_alert()
            self._exit(0, reboot=True)
        else:
            end_action = ''
            while not end_action:
                message = ('An error has ocurred, check log file at {0}?\n'
                           '(While in log view, press down "q" key to exit)\n'
                           '(While in shell, type "exit" or Ctrl+D to exit)'
                           .format("/var/log/ister.log"))
                alert = Alert(title, message, labels=[u'View log',
                                                      u'Shell',
                                                      u'Reboot',
                                                      u'Shut down'])
                alert.do_alert()
                if alert.response == 'View log':
                    LogViewStep("/var/log/ister.log").handler(
                        self.installation_d)
                elif alert.response == 'Shell':
                    ShellStep().handler(self.installation_d)
                else:
                    end_action = alert.response
            message = ('Unsuccessful installation, system will {0}'
                       .format(end_action.lower()))
            reboot = True if end_action == 'Reboot' else False
            self._exit(1, message=message, title=title, reboot=reboot)
        return


def handle_options():
    """Argument parser for the ui"""
    parser = argparse.ArgumentParser()
    parser.add_argument("-V", "--versionurl", action="store",
                        default="https://cdn.download.clearlinux.org/update",
                        help="URL to use for looking for update versions")
    parser.add_argument("-C", "--contenturl", action="store",
                        default="https://cdn.download.clearlinux.org/update",
                        help="URL to use for looking for update content")
    parser.add_argument("-f", "--format", action="store", default=None,
                        help="format to use for looking for update content")
    parser.add_argument("-n", "--no-install", action="store_true",
                        help="Dry run the UI - no install performed.")
    parser.add_argument("-d", "--dry-run", action="store_true",
                        help="Dry run the UI locally in test mode, no poweroff"
                        "on exit, no install performed.")
    parser.add_argument("-e", "--exit-after", action="store_true",
                        help="Do not reboot or poweroff after install, helpful"
                             " for letting unit files handle the post action")
    args = parser.parse_args()
    return args


def main():
    """Entry point for the ui"""
    setup()
    args = handle_options()
    # Don't die on CTRL-C, as it only freezes the TTY
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    ins = Installation(**vars(args))
    ins.run()


if __name__ == '__main__':
    main()
