"""Linux installation gui"""

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

# global is handy here for now, but this could be fixed up
# pylint: disable=W0603
# Early on self not being used, will consider later on
# pylint: disable=R0201
# broad exceptions are fine
# pylint: disable=W0703
# use of format strings this way is prefered unless convinced otherwise
# pylint: disable=W1202
# pylint: disable=C0302

import argparse
import crypt
import json
import logging
import os
import re
import subprocess
import sys
import time

# pylint: disable=E0401
import urwid

import ister

PALETTE = [
    ('header', 'white', 'dark red', 'bold'),
    ('banner', 'black', 'light gray'),
    ('bg', 'black', 'dark blue'),
    ('p1', 'white', 'dark red'),
    ('p2', 'white', 'dark green'),
    ('p3', 'white', 'dark cyan'),
    ('p4', 'white', 'dark magenta'),
    ('reversed', 'white', ''),
    ('I say', 'black,bold', 'light gray', 'bold')]

MIN_WIDTH = 80
MIN_HEIGHT = 24
PERCENTAGE_W = 90
PERCENTAGE_H = 70
LINES = 0
COLUMNS = 0


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


def ister_wrapper(fn_name, *args):
    """Wrapper to dynamically call ister validations"""
    try:
        ister.__getattribute__(fn_name)(*args)
    except Exception as exc:
        return exc
    return None


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
            button = urwid.Button(label)
            urwid.connect_signal(button, 'click', self._on_click)
            button = urwid.AttrMap(button, None, focus_map='reversed')
            buttons.append(urwid.Padding(button, 'center', 9))

        # Add to frame
        nav = NavBar(buttons)
        self._frame.append(('pack', nav))
        self._frame.append(('pack', urwid.Divider()))

    def _set_ui(self):
        self._frame = FormController(self._frame)
        self._frame = urwid.LineBox(self._frame, title=self._title)
        self._frame = urwid.Filler(self._frame, valign='middle')
        self._fgwin = urwid.Padding(self._frame, 'center', ('relative', 50))
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
            unhandled_input=self.handle_key)

        self.term.main_loop = loop
        self.term.keygrab = True

    def quit(self, *args, **kwargs):
        """Breaks the loop to continue"""
        del args, kwargs
        raise urwid.ExitMainLoop()

    def handle_key(self, key):
        """It connects the signal, but does not do anything"""
        pass

    def main_loop(self):
        """Enters the loop to grab focus on the terminal UI"""
        self.term.main_loop.run()


class ButtonMenu(object):
    """Assemble the button menu - ultimately store it in self._ui"""
    # pylint: disable=R0903
    def __init__(self, title, choices):
        self._response = ''  # The choice made by the user is stored here.
        # These will sit above the list box
        self._frame_contents = [('pack', urwid.Divider()),
                                ('pack', urwid.Text(title)),
                                ('pack', urwid.Divider())]
        self._menu = []
        for choice in choices:
            button = urwid.Button(choice)
            urwid.connect_signal(button, 'click', self._item_chosen, choice)
            button = urwid.AttrMap(button, None, focus_map='reversed')
            self._menu.append(button)

        self._lb = urwid.ListBox(urwid.SimpleFocusListWalker(self._menu))
        self._frame_contents.append(self._lb)
        self._frame_contents = urwid.Pile(self._frame_contents)
        self._fgwin = urwid.Padding(self._frame_contents, left=2, right=2)
        self._ui = urwid.Overlay(self._fgwin,
                                 urwid.AttrMap(urwid.SolidFill(u' '), 'bg'),
                                 align='center',
                                 width=('relative', PERCENTAGE_W),
                                 valign='middle',
                                 height=('relative', PERCENTAGE_H))
        self._ui = urwid.AttrMap(self._ui, 'banner')

    # This callback is registered with urwid.MainLoop and gives us the
    # opportnity to intercept keystrokes and handle things like tabs.
    # In theory the callback for each keystroke should be function
    # fragment or class method but I just handled them in-line here.
    # Unhandled input is returned back to MainLoop for default handlers to
    # deal with. Another way to effect this would be to subclass the
    # ListBox class and override the keypress method.
    def _input_filter(self, keys, raw):
        # pylint: disable=W0212
        del raw
        i = self._lb.focus_position
        max_pos = len(self._lb.body.positions())
        if 'tab' in keys or 'down' in keys:
            self._lb.focus_position = (i + 1) % max_pos
            self._lb._invalidate()
        elif 'shift tab' in keys or 'up' in keys:
            self._lb.focus_position = (i - 1) % max_pos
            self._lb._invalidate()
        else:
            return keys

    def _item_chosen(self, button, choice):
        """ Callback trigged by button activation  """
        del button
        self._response = choice
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
    def __init__(self, buttons, ):
        self._lost_focus = False
        super(NavBar, self).__init__(buttons, dividechars=5)

    def keypress(self, size, key):
        # self.focus_position defined in parent
        # pylint: disable=E0203
        # pylint: disable=W0201
        """ Note, the first time this NavBar is entered via tab, it
            starts on first-position + 1. Which means "next" is
            selected on the first enter for a <prev><next> nav-bar
            which facillitates the default "enter info" <next>
            work flow. In other words, this is not a bug.
            Arguably it would be better to implement this in an
            explicit fashion vs. implicit fashion, but for now this works. """
        max_cols = len(self.contents)
        pos = self.focus_position
        key = super(NavBar, self).keypress(size, key)
        if key == 'tab':
            if self._lost_focus is True:
                self._lost_focus = False
                self.focus_position = 0
            elif pos < (max_cols - 1):
                self.focus_position = pos + 1
            elif pos == (max_cols - 1):
                self._lost_focus = True
                return key
        elif key == 'shift tab':
            if self._lost_focus is True:
                self._lost_focus = False
                self.focus_position = (max_cols - 1)
            elif pos > 0:
                self.focus_position = pos - 1
            elif pos == 0:
                self._lost_focus = True
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
        key = super(FormBody, self).keypress(size, key)
        pos = self.focus_position
        if key == 'tab' or key == 'enter':
            if self._lost_focus:
                self._lost_focus = False
                self.focus_position = 0
                self._invalidate()
            elif pos < (self._num_fields - 1):
                while pos < (self._num_fields - 1):
                    pos += 1
                    if self._body[pos].selectable():
                        break
                if pos == (self._num_fields - 1):
                    self._lost_focus = True
                    return 'tab'
                else:
                    self.focus_position = pos
                    self._invalidate()
            elif pos == (self._num_fields - 1):
                self._lost_focus = True
                return 'tab'
        elif key == 'shift tab' or key == 'enter':
            if self._lost_focus:
                self._lost_focus = False
                self.focus_position = (self._num_fields - 1)
                self._invalidate()
            elif pos > 0:
                while pos > 0:
                    pos -= 1
                    if self._body[pos].selectable():
                        break
                if pos == 0:
                    self._lost_focus = True
                    return 'tab'
                else:
                    self.focus_position = pos
                    self._invalidate()
            elif pos == 0:
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
        if key == 'tab':
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
            # Send the tab into the newly focused widget
            self.focus.keypress(size, key)
        elif key == 'shift tab':
            start = self.focus_position
            # Skip the header
            while True:
                pos = (pos - 1) % len(self.contents)
                self.focus_position = pos
                if self.focus.selectable():
                    break
                # guard against infinite spinning
                if pos == start:
                    break
            # Send the tab into the newly focused widget
            self.focus.keypress(size, key)
        else:
            return key


class SimpleForm(object):
    """ Creates a Form with a Header, FormBody (which contains form fields)
    And a NavBar, which contains buttons for previous and next.
    Prompt for input for one or more fields """
    # pylint: disable=R0902
    # pylint: disable=R0903
    def __init__(self, title, fields):
        self._title = title
        self._questions = fields
        self._answers = dict()
        self._clicked = ''
        self._next_id = 0

        # Build the forum
        self._frame = [('pack', urwid.Divider()),
                       ('pack', urwid.Text(title)),
                       ('pack', urwid.Divider())]

        self._form_body = FormBody(fields)
        self._frame.append(self._form_body)

        # Add the navigation buttons - for the installer common to
        # all forms.  <previous> <next> """

        self._add_nav_bar()
        self._set_ui()

    def _on_click(self, button):
        self._clicked = button.label
        raise urwid.ExitMainLoop()

    def _add_nav_bar(self):
        buttons = []
        # Previous Button
        button = urwid.Button(u'Previous')
        urwid.connect_signal(button, 'click', self._on_click)
        button = urwid.AttrMap(button, None, focus_map='reversed')
        buttons.append(urwid.Padding(button, 'center', width=12))

        # Next Button
        button = urwid.Button(u'Next')
        urwid.connect_signal(button, 'click', self._on_click)
        button = urwid.AttrMap(button, None, focus_map='reversed')
        buttons.append(urwid.Padding(button, 'center', width=8))

        # Add to frame
        nav = NavBar(buttons)
        self._frame.append(('pack', nav))
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

    def do_form(self):
        """Creates the loop and enter to it, to focus the UI"""
        main_loop = urwid.MainLoop(self._ui, palette=PALETTE)
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
        # pylint: disable=W1401
        first = re.compile('[a-z]')
        rest = re.compile('[a-z0-9\-_]')
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
        # pylint: disable=W1401
        # Backspace doesn't work when the edit accepts only numbers
        if key == 'backspace':
            key = super(IpEdit, self).keypress(size, key)
            return key
        first = re.compile('[1-9]')
        rest = re.compile('[0-9\.]')
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


class ProcessStep():
    """Defines a step tu be run by the installation handler"""
    def __init__(self):
        self._ui = None
        self._ui_widgets = None
        self._action = None
        self.action_map = dict()

    def get_next_step(self, action):
        """Returns the process step matched by action"""
        if action == 'Exit':
            exit(0)
        if action in self.action_map:
            return self.action_map[action]
        else:
            tmp = Alert(u'Error!', 'Not implemented yet')
            tmp.do_alert()
            return self

    def set_action(self, action, target):
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

    def run_ui(self):
        """Method to run the ui and return the action"""
        return 'Next'

    def build_ui_widgets(self):
        """Method to build all the widgets"""
        self._ui_widgets = None

    def build_ui(self):
        """Method to create the ui"""
        self._ui = True


class StartInstaller(ProcessStep):
    """UI to select automatic or manual installation"""
    def handler(self, config):
        choices = u'Automatic Manual(Advanced) Exit'.split()

        if not self._ui:
            self._ui = ButtonMenu(u'Choose Installation Type', choices)

        self._action = self._ui.run_ui()

        return self._action


class ConfigureHostname(ProcessStep):
    """UI to gather the host's name"""
    def handler(self, config):

        if not self._ui_widgets:
            self.build_ui_widgets()

        if not self._ui:
            self.build_ui()

        while True:
            self._action = self.run_ui()
            # Validate and ship out the hostname that was given to the configs
            if self._action == 'Next':
                config['Hostname'] = self._ui_widgets[0].get_edit_text()
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
        self._ui_widgets = list()
        hostname_field = HostnameEdit(u'{0:30}'.format('Hostname:'),
                                      align='left',
                                      edit_text=u'clr')
        self._ui_widgets.append(hostname_field)

    def build_ui(self):
        self._ui = SimpleForm(u'Configuring Hostname', self._ui_widgets)


class ConfirmStep(ProcessStep):
    """UI to show a confirm box"""
    def __init__(self, title, body):
        super(ConfirmStep, self).__init__()
        self._title = title
        self._body = body

    def handler(self, config):
        alert = Alert(self._title,
                      self._body,
                      labels=[u'Prev', u'No', u'Yes'])
        alert.do_alert()
        return alert.response


class SelectDeviceStep(ProcessStep):
    """UI to display the available disks"""
    def handler(self, config):
        config['DisabledNewPartitions'] = True
        choices = self._get_list_of_disks()
        other_options = ['Previous', 'Exit']
        choices.extend(other_options)
        self._ui = ButtonMenu(u'Choose destination', choices)
        self._action = self._ui.run_ui()
        if self._action not in other_options:
            keys = ['PartitionLayout',
                    'FilesystemTypes',
                    'PartitionMountPoints']
            for key in keys:
                for _iter in range(0, len(config[key])):
                    config[key][_iter]['disk'] = self._action
            return 'Next'
        return self._action

    def _get_list_of_disks(self):
        """"Queries for the available disks discarding the inst. source"""
        dir_path = '/sys/block'
        disks = [device for device in os.listdir(dir_path)
                 if 'pci' in os.readlink('{0}/{1}'.format(dir_path, device))]
        unmounted = list()
        content = ''
        with open('/proc/cmdline') as file:
            content = file.read()
        part_uuid = ''
        for split in content.split('\n')[0].split():
            value = 'root=PARTUUID='
            if value in split:
                part_uuid = split[len(value):]
        root_disk = os.readlink('/dev/disk/by-partuuid/{0}'.format(part_uuid))
        for disk in disks:
            if disk not in root_disk:
                unmounted.append(disk)
        return unmounted


class TerminalStep(ProcessStep):
    """UI to display cgdisk to manage partitioning"""
    def handler(self, config):
        disk = config['PartitionLayout'][0]['disk']
        term = Terminal(['cgdisk', '/dev/{0}'.format(disk)])
        term.main_loop()
        return 'Next'


class SetMountEachStep(ProcessStep):
    """UI to gather the mount point of the selected partition"""
    def __init__(self, partition):
        super(SetMountEachStep, self).__init__()
        self._partition = partition
        self.edit_m_point = urwid.Edit('{0:30}'.format('Enter mount point:'))
        self.check_format = urwid.CheckBox('Format')

    def handler(self, config):
        if not self._ui_widgets:
            self.build_ui_widgets()
        if not self._ui:
            self.build_ui()
        # Searchs in the config if the partition already has a mount point
        for point in config:
            if config[point]['part'] == self._partition:
                self.edit_m_point.set_edit_text(point)
                self.check_format.set_state(config[point]['format'])
        self._action = self.run_ui()
        point = self.edit_m_point.get_edit_text()
        _format = self.check_format.get_state()
        if point == '/':
            _format = True
        if self._action == 'Next' and len(point) > 0 and point[0] == '/':
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
    def handler(self, config):
        # pylint: disable=R0914
        mount_d = dict()
        display_fmt = '{0:20}{1:20}{2:20}{3:20}'
        choices = self._get_partition_list(config)
        sizes = self._get_partition_size(config, choices)
        for idx, choice in enumerate(choices):
            choices[idx] = display_fmt.format(choice, sizes[idx], '', '')
        other_options = ['Next', 'Previous', 'Exit']
        choices.extend(other_options)
        while True:
            self._ui = ButtonMenu(u'Set mount points', choices)
            self._action = self._ui.run_ui()
            partition = self._action.split()[0]
            if self._action in other_options:
                required_mounts = ['/', '/boot']
                if self._action == 'Next':
                    find = False
                    for mount in required_mounts:
                        if mount not in mount_d:
                            (Alert(u'Error!',
                                   u'Missing "{0}" mount point'.format(mount))
                             .do_alert())
                            find = True
                            break
                    if find:
                        continue
                    else:
                        break
                else:
                    return self._action
            point = SetMountEachStep(partition).handler(mount_d)
            if point not in other_options:
                idx = choices.index(self._action)
                _format = 'Format' if mount_d[point]['format'] else ''
                choices[idx] = display_fmt.format(partition,
                                                  sizes[idx],
                                                  point,
                                                  _format)
        self._save_config(config, mount_d)
        partitions = [choice for choice in choices
                      if choice not in other_options]
        self._search_swap(partitions, config, mount_d)
        exc = ister_wrapper('validate_disk_template', config)
        if exc is not None:
            return exc
        return self._action

    def _save_config(self, config, mount_d):
        disk = config['PartitionLayout'][0]['disk']
        config['PartitionLayout'] = list()
        config['FilesystemTypes'] = list()
        config['PartitionMountPoints'] = list()
        for point in mount_d:
            _type = 'EFI' if point == '/boot' else 'linux'
            part = mount_d[point]['part']
            part = part[len(disk):]
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
                config['FilesystemTypes'][-1]['disable_format'] = True
            config['PartitionMountPoints'].append({
                'disk': disk,
                'partition': part,
                'mount': point})

    def _search_swap(self, choices, config, mount_d):
        for choice in choices:
            part = choice.split()[0]
            for point in mount_d:
                if part == mount_d[point]['part']:
                    break
            else:
                output = subprocess.check_output('blkid | grep {0}'
                                                 .format(part),
                                                 shell=True)
                pttr = b'TYPE="'
                idx = output.index(pttr)
                output = output[idx + len(pttr):]
                output = output[: output.index(b'"')]
                if output == b'swap':
                    disk = config['PartitionLayout'][0]['disk']
                    part = part[len(disk):]
                    config['PartitionLayout'].append({
                        'disk': disk,
                        'partition': part,
                        'size': '1M',
                        'type': 'swap'})
                    config['FilesystemTypes'].append({
                        'disk': disk,
                        'partition': part,
                        'type': 'swap'})

    def _get_partition_list(self, config):
        disk = config['PartitionLayout'][0]['disk']
        dir_path = '/sys/block/{0}'.format(disk)
        return [part for part in os.listdir(dir_path) if disk in part]

    def _get_partition_size(self, config, partitions):
        disk = config['PartitionLayout'][0]['disk']
        results = list()
        prefix = ['B', 'K', 'M', 'G', 'T']
        for partition in partitions:
            fd_path = '/sys/block/{0}/{1}/size'.format(disk, partition)
            block_size = 512
            size = -1.0
            try:
                with open(fd_path) as file:
                    size = float(file.read()) * block_size
            except Exception:
                pass
            pref_idx = 0
            while int(size / 1024) > 0:
                size /= 1024
                pref_idx += 1
            results.append('{0:.1f}{1}'.format(size, prefix[pref_idx]))
        return results


class BundleSelectorStep(ProcessStep):
    """UI which displays the bundle list to be installed"""
    def __init__(self):
        super(BundleSelectorStep, self).__init__()
        self.bundles = [{'name': 'editors',
                         'desc': 'Popular text editors (terminal-based)'},
                        {'name': 'os-clr-on-clr',
                         'desc': 'Fills out dev tools for os development'},
                        {'name': 'devtools-basic',
                         'desc': 'gcc and minimal R, go, hpc, perl, python,'
                                 ' ruby'},
                        {'name': 'sysadmin',
                         'desc': 'Tools sys-admins commonly use'},
                        {'name': 'net-utils',
                         'desc': 'Core network config and debug'},
                        {'name': 'network-proxy-client',
                         'desc': 'Auto proxy detection for aware tools like '
                                 'swupd'}]
        self.required_bundles = list()
        try:
            output = subprocess.check_output('systemd-detect-virt',
                                             shell=True)
        except Exception:
            output = 'none'
        supported = {
            'none': {'name': 'kernel-native',
                     'desc': 'Required to run clear on baremetal'},
            'qemu': {'name': 'kernel-kvm',
                     'desc': 'Required to run clear on kvm'}}
        kernel = 'Kernel invalid'
        for key in supported:
            if key in str(output):
                kernel = supported[key]
        self.required_bundles.extend([
            {'name': 'os-core',
             'desc': 'Minimal packages to have clear fully functional'},
            kernel,
            {'name': 'os-core-update',
             'desc': 'Required to update the system'},
            {'name': 'os-utils',
             'desc': 'A core set of OS utilities'},
            {'name': 'telemetrics',
             'desc': 'Quality feedback for the OS'}])

    def handler(self, config):
        if not self._ui_widgets:
            self.build_ui_widgets()
        if not self._ui:
            self.build_ui()
        self._action = self.run_ui()
        config['Bundles'] = list()
        config['Bundles'].extend([bundle['name']
                                  for bundle in self.required_bundles])
        for widget in self._ui_widgets:
            if isinstance(widget, urwid.CheckBox) and widget.get_state():
                bundle = widget.get_label()
                bundle = bundle.split()[0]
                config['Bundles'].append(bundle)
        return self._action

    def run_ui(self):
        return self._ui.do_form()

    def build_ui_widgets(self):
        self._ui_widgets = [urwid.Text('Select the bundles to install:'),
                            urwid.Divider()]
        for bundle in self.bundles:
            check = urwid.CheckBox(bundle['name'])
            desc_text = urwid.Text(bundle['desc'])
            column = urwid.Columns([check, ('weight', 2, desc_text)])
            self._ui_widgets.append(column)
        for bundle in self.required_bundles:
            text_name = urwid.Text('[X] {0}'.format(bundle['name']))
            text_desc = urwid.Text(bundle['desc'])
            column = urwid.Columns([text_name, ('weight', 2, text_desc)])
            self._ui_widgets.append(column)

    def build_ui(self):
        self._ui = SimpleForm(u'Bundle selector', self._ui_widgets)


class UserConfigurationStep(ProcessStep):
    """UI to gather the user info"""
    # pylint: disable=R0902
    def __init__(self):
        super(UserConfigurationStep, self).__init__()
        fmt = '{0:30}'
        self.edit_name = urwid.Edit(fmt.format('Enter firstname:'))
        self.edit_lastname = urwid.Edit(fmt.format('Enter lastname:'))
        self.edit_username = UsernameEdit(fmt.format('Enter username:'))
        self.edit_password = urwid.Edit(fmt.format('Enter password:'),
                                        mask='*')
        self.edit_confirm_p = urwid.Edit(fmt.format('Confirm password:'),
                                         mask='*')
        self.sudo = urwid.CheckBox('Add user to sudoers?')
        urwid.connect_signal(self.edit_name, 'change', self._username_handler)
        urwid.connect_signal(self.edit_lastname,
                             'change',
                             self._username_handler)

    def _username_handler(self, edit, new_text):
        name_text = self.edit_name.get_edit_text()[0:1]
        lastname_text = self.edit_lastname.get_edit_text()[0:8]
        if edit == self.edit_name:
            name_text = new_text[0:1]
        else:
            lastname_text = new_text[0:8]
        self.edit_username.set_edit_text(name_text.lower() +
                                         lastname_text.lower())

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
                comp = self.edit_confirm_p.get_edit_text()
                if password == '':
                    Alert('Error!', 'Missing password').do_alert()
                elif password != comp:
                    Alert('Error!', 'The passwords do not match').do_alert()
                else:
                    break
                continue
        tmp = dict()
        tmp['username'] = self.edit_username.get_edit_text()
        tmp['password'] = crypt.crypt(self.edit_password.get_edit_text(),
                                      'aa')
        tmp['sudo'] = self.sudo.get_state()
        config['Users'] = [tmp]
        return self._action

    def run_ui(self):
        return self._ui.do_form()

    def build_ui_widgets(self):
        """Build ui handler
        The last urwid Divider helps to tab movement to work"""
        self._ui_widgets = [self.edit_name,
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
                            urwid.Divider()]

    def build_ui(self):
        self._ui = SimpleForm(u'User configuration', self._ui_widgets)


class StaticIpStep(ProcessStep):
    """UI to gather the static ip configuration"""
    def __init__(self):
        super(StaticIpStep, self).__init__()
        fmt = '{0:30}'
        self.edit_ip = IpEdit(fmt.format('Enter ip address:'))
        self.edit_mask = IpEdit(fmt.format('Enter mask:'))
        self.edit_gateway = IpEdit(fmt.format('Enter gateway:'))
        self.edit_dns = IpEdit(fmt.format('Enter DNS (optional):'))

    def _save_config(self, config):
        pows = [pow(2, idx) for idx in range(0, 8)]
        pows.reverse()
        mask = 0
        for octet in self.edit_mask.get_edit_text().split('.'):
            _tmp = int(octet)
            idx = 0
            while _tmp > 0:
                _tmp -= pows[idx]
                idx += 1
            mask += idx
        tmp = dict()
        tmp['address'] = '{0}/{1}'.format(self.edit_ip.get_edit_text(), mask)
        tmp['gateway'] = self.edit_gateway.get_edit_text()
        tmp['dns'] = self.edit_dns.get_edit_text()
        config['Static_IP'] = tmp

    def handler(self, config):
        if not self._ui_widgets:
            self.build_ui_widgets()
        if not self._ui:
            self.build_ui()
        # pylint: disable=W1401
        # http://stackoverflow.com/questions/10006459/
        # regular-expression-for-ip-address-validation
        pattern = re.compile('^(?:(?:2[0-4]\d|25[0-5]|1\d{2}|[1-9]?\d)\.){3}'
                             '(?:2[0-4]\d|25[0-5]|1\d{2}|[1-9]?\d)'
                             '(?:\:(?:\d|[1-9]\d{1,3}|[1-5]\d{4}|6[0-4]\d{3}'
                             '|65[0-4]\d{2}|655[0-2]\d|6553[0-5]))?$')
        while True:
            self._action = self.run_ui()
            if self._action == 'Previous':
                return self._action
            check = [(self.edit_ip, 'ip'),
                     (self.edit_mask, 'mask'),
                     (self.edit_gateway, 'gateway')]
            values = dict()
            error = ''
            for edit, field in check:
                text = edit.get_edit_text()
                values[text] = values.get(text, 0) + 1
                if not pattern.match(text):
                    error = ('The configuration for "{0}" is invalid'
                             .format(field))
                    break
            if error == '':
                for key in values:
                    if values[key] != 1:
                        error = 'Repeated values'
                        break
            if error == '' and self.edit_dns.get_edit_text() != '' \
                    and not pattern.match(self.edit_dns.get_edit_text()):
                error = 'The configuration for "dns" is invalid'
            if error == '':
                self._save_config(config)
                return self._action
            Alert('Error!', error).do_alert()

    def run_ui(self):
        return self._ui.do_form()

    def build_ui_widgets(self):
        self._ui_widgets = [self.edit_ip,
                            urwid.Divider(),
                            self.edit_mask,
                            urwid.Divider(),
                            self.edit_gateway,
                            urwid.Divider(),
                            self.edit_dns,
                            urwid.Divider()]

    def build_ui(self):
        self._ui = SimpleForm(u'Static ip configuration', self._ui_widgets)


class RunInstallation(ProcessStep):
    """Class to break the loop and proceed with the installation"""
    pass


class Installation(object):
    """Main object for installer ui"""

    # pylint: disable=too-many-instance-attributes

    def __init__(self, *args, **kwargs):
        # args unused for now
        del args
        self._steps = list()
        self.start = StartInstaller()
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
        self.args = kwargs
        try:
            with open('/etc/ister.json') as file:
                json_string = file.read()
                self.installation_d = json.loads(json_string)
        except Exception as exep:
            self.logger.error(exep)
            self._exit(-1, 'Template file does not exist')

    def _init_actions(self):
        config_hostname = ConfigureHostname()
        confirm_auto_install = ConfirmStep('Warning!',
                                           'Do you want to proceed with the '
                                           'automatic  installation (Will '
                                           'blow up the entire disk)?')
        confirm_manual_partition = ConfirmStep('Attention!',
                                               'Do you want to handle the '
                                               'partitions and mount points '
                                               'manually? (If not the device '
                                               'will be repartitioned and all '
                                               'existing data lost)')
        select_device = SelectDeviceStep()
        confirm_cgdisk = ConfirmStep('Attention!',
                                     'Do you want to open cgdisk to '
                                     'configure the partitions manually?')
        terminal_cgdisk = TerminalStep()
        set_mount_points = MountPointsStep()
        bundle_selector = BundleSelectorStep()
        confirm_new_username = ConfirmStep('Attention!',
                                           'Do you want to configure a new '
                                           'user?')
        user_configuration = UserConfigurationStep()
        confirm_dhcp = ConfirmStep('Attention!',
                                   'Do you want to use DHCP? '
                                   '(Select "No" for static)')
        static_ip_configuration = StaticIpStep()
        run = RunInstallation()

        self.start.set_action('Automatic', confirm_auto_install)
        confirm_auto_install.set_action('No', self.start)
        confirm_auto_install.set_action('Yes', run)
        self.start.set_action('Manual(Advanced)', confirm_manual_partition)
        confirm_manual_partition.set_action('Prev', self.start)
        confirm_manual_partition.set_action('No', config_hostname)
        confirm_manual_partition.set_action('Yes', select_device)
        select_device.set_action('Previous', confirm_manual_partition)
        select_device.set_action('Next', confirm_cgdisk)
        confirm_cgdisk.set_action('Prev', select_device)
        confirm_cgdisk.set_action('No', set_mount_points)
        confirm_cgdisk.set_action('Yes', terminal_cgdisk)
        terminal_cgdisk.set_action('Next', set_mount_points)
        set_mount_points.set_action('Previous', select_device)
        set_mount_points.set_action('Next', config_hostname)
        config_hostname.set_action('Previous', confirm_manual_partition)
        config_hostname.set_action('Next', bundle_selector)
        bundle_selector.set_action('Previous', config_hostname)
        bundle_selector.set_action('Next', confirm_new_username)
        confirm_new_username.set_action('Prev', bundle_selector)
        confirm_new_username.set_action('No', confirm_dhcp)
        confirm_new_username.set_action('Yes', user_configuration)
        user_configuration.set_action('Previous', bundle_selector)
        user_configuration.set_action('Next', confirm_dhcp)
        confirm_dhcp.set_action('Prev', confirm_new_username)
        confirm_dhcp.set_action('Yes', run)
        confirm_dhcp.set_action('No', static_ip_configuration)
        static_ip_configuration.set_action('Previous', confirm_new_username)
        static_ip_configuration.set_action('Next', run)

    def _exit(self, int_code, error_message=None):
        """UI to display error messages"""
        if int_code != 0:
            if error_message is None:
                error_message = 'An error ocurred during the installation, ' \
                                'please check the log file'
            alert = Alert('Error!', error_message)
            alert.do_alert()
        os.system('reset')
        exit(int_code)

    def get_part_list_from_fdisk(self):
        cmd = ['/usr/bin/fdisk', '-l', '/dev/sda']
        output = subprocess.check_output(cmd).decode()
        lines = output.split('\n')
        expr = re.compile('^Device')
        disk_empty = True
        # discard header...
        while len(lines) > 0:
            match = expr.match(lines[0])
            if match:
                disk_empty = False
                break
            else:
                lines.pop(0)

        if disk_empty:
            return "/dev/sda contents: no partitions found."

        lines.pop(0)  # header - add this back manually
        partitions = 'Device'.ljust(10) + ' ' + 'Size'.rjust(6) + ' ' + 'Type'.ljust(28) + '\n'

        expr = re.compile('(\S+)\s+\S+\s+\S+\s+\S+\s+(\S+)\s+(\S.*)')
        for l in lines:
            match = expr.match(l)
            if match:
                partitions += match.group(1).ljust(10) + ' ' +  match.group(2).rjust(6) + ' ' +  match.group(3).ljust(28) + '\n'
            else:
                break
        return partitions


    def run(self):
        """Starts up the installer ui"""

        step = self.start

        while not isinstance(step, RunInstallation):
            action = step.handler(self.installation_d)
            self.logger.debug(self.installation_d)
            if action == 'Abort' or action == 'Exit':
                self._exit(0)
            elif isinstance(action, Exception):
                self._exit(-1, str(action))
            step = step.get_next_step(action)
        self.automatic_install()
        os.system('reset')

    def check_swupd_log(self, title, previous_text, bundles_length):
        swupd_log = '/var/log/swupd/swupd-update.log'
        os.system('rm -rf {0}'.format(swupd_log))
        while not os.path.exists(swupd_log):
            time.sleep(.1)
        _map = [{'find': re.compile(r'Downloading file.*Manifest\.MoM\.tar'),
                 'text': 'Get information from server'}]
        rgx = re.compile(r'Downloading file.*swupd/pack-(.*)-from.*\.tar')
        rgx_d = re.compile(r'Untar of delta pack.*swupd/pack-(.*)-from.*\.tar')
        for idx in range(0, bundles_length):
            _map.append({'find': rgx, 'text': 'Downloading {0}'})
            _map.append({'find': rgx_d, 'text': 'Decompressing {0}'})
        _map.append({'find': '\n', 'text': 'Installing system'})
        _map.append({'find': 'Fix successful',
                     'text': 'Installation successful'})
        times = 5
        cursor = 0
        _kwargs = {'title': title, 'map': _map, 'global_idx': 0, 'content': '',
                   'previous_text': previous_text}
        while _kwargs['global_idx'] < len(_map):
            if _kwargs['content'].rfind(_map[-1]['find']) != -1:
                self.search_swupd_log(_kwargs)
                continue
            # To wait a little bit more when swupd becomes more verbose.
            # It happens when swupd start to check hashes of each file in
            # the filesystem
            if _kwargs['global_idx'] >= len(_map) - 2:
                time.sleep(.5)
            for idx in range(0, times):
                with open(swupd_log, encoding='utf-8') as file:
                    file.seek(cursor)
                    line = file.read()
                    # To sleep a little the cpu, maintains the cpu usage < 10%
                    # Without it becomes 100%
                    time.sleep(.5)
                    _kwargs['content'] += line
                    if cursor != file.tell():
                        cursor = file.tell()
                        self.search_swupd_log(_kwargs)
                        break

    def search_swupd_log(self, kwargs):
        _map = kwargs['map']
        title = kwargs['title']
        item = _map[kwargs['global_idx']]
        if isinstance(item['find'], str):
            index = kwargs['content'].find(item['find'])
            if index != -1:
                kwargs['content'] = kwargs['content'][index:]
                idx = 0
                try:
                    idx = kwargs['previous_text'].index('')
                except Exception:
                    return
                kwargs['previous_text'][idx] = item['text']
                kwargs['global_idx'] += 1
                _block = kwargs['global_idx'] == len(_map)
                Alert(title,
                      '\n'.join(kwargs['previous_text']),
                      block=_block).do_alert()
        else:
            match = item['find'].search(kwargs['content'])
            if match:
                kwargs['content'] = kwargs['content'][match.start() +
                                                      len(match.group()):]
                if len(match.groups()) == 0:
                    tmp = item['text']
                else:
                    tmp = item['text'].format(match.groups()[0])
                try:
                    index = kwargs['previous_text'].index('')
                except Exception:
                    return
                kwargs['previous_text'][index] = tmp
                kwargs['global_idx'] += 1
                Alert(title,
                      '\n'.join(kwargs['previous_text']),
                      block=False).do_alert()

    def automatic_install(self):
        """Initial installation method, use the default template unmodified"""
        with open('/tmp/template.json', 'w') as file:
            self.logger.debug(self.installation_d)
            file.write(json.dumps(self.installation_d))
        title = u'Automatic installation of ClearLinux v{0}' \
                .format(self.installation_d['Version'])

        # main_loop's closure calling the installer
        if self.args['no_install']:
            self._exit(0, 'dry run - actual install skipped.')
        supported = [
            {'name': 'url', 'out': '--url={0}'},
            {'name': 'format', 'out': '--format={0}'}]
        flags = ' '.join([item['out'].format(self.args[item['name']])
                          for item in supported
                          if self.args[item['name']] is not None])
        ister_log = '/var/log/ister.log'
        ister_cmd = [sys.executable,
                     '/usr/bin/ister.py',
                     '-t',
                     '/tmp/template.json',
                     flags,
                     '&> {0}'.format(ister_log)]
        self.logger.debug(' '.join(ister_cmd))
        _map = [{'text': u'Starting installation...'},
                {'find': 'mkfs.fat', 'text': 'Format EFI'},
                {'find': 'operation has completed', 'text': 'Format done'},
                {'find': 'mke2fs', 'text': 'Format other partitions'},
                {'find': 'operation has completed',
                 'text': 'Format done\nRunning swupd'}]
        text = _map[0]['text']
        Alert(title, text, block=False).do_alert()
        proc = subprocess.Popen(' '.join(ister_cmd), shell=True)
        # Real subprocess is the pid plus one, because pid is the parent
        path = '/proc/{0}'.format(proc.pid + 1)
        self.logger.debug('Starting ister')
        cursor = 0
        times = 20
        jump_open = False
        self.logger.debug(path)
        global_idx = 1
        # Wait subprocess to start
        time.sleep(1)
        previous_text = ['' for item in _map]
        previous_text[0] = _map[0]['text']
        swupd_length = len(self.installation_d['Bundles']) * 2 + 3
        previous_text.extend(['' for idx in range(0, swupd_length)])
        while proc.poll() is None:
            for idx, item in enumerate(_map[global_idx:]):
                index = text.find(item['find'])
                if index != -1:
                    text = text[index + len(item['find']):]
                    global_idx += 1
                    try:
                        _idx = previous_text.index('')
                    except Exception:
                        continue
                    previous_text[_idx] = item['text']
                    local_text = '\n'.join(previous_text)
                    Alert(title, local_text, block=False).do_alert()
                    break
            if global_idx == len(_map):
                self.check_swupd_log(title,
                                     previous_text,
                                     len(self.installation_d['Bundles']))
                break
            elif not jump_open:
                line = ''
                for i in range(0, times):
                    with open(ister_log) as file:
                        file.seek(cursor)
                        line = file.read()
                        if cursor != file.tell():
                            cursor = file.tell()
                            break
                        time.sleep(.25)
                else:
                    jump_open = True
                self.logger.debug(line)
                text += line
        with open(ister_log) as file:
            text = file.read()
            find = 'Adding any missing files'
            index = text.find(find)
            text = text[index + len(find):]
            Alert(title, text).do_alert()

        if 'Fix successful' in text:
            message = 'Successful installation, the system will be rebooted'
        else:
            message = ('An error has ocurred, check log file at {0}'
                       .format(self.template_path))
        Alert(title, message).do_alert()
        return


def handle_options():
    """Argument parser for the ui"""
    parser = argparse.ArgumentParser()
    parser.add_argument("-u", "--url", action="store", default=None,
                        help="URL to use for looking for update content")
    parser.add_argument("-f", "--format", action="store", default=None,
                        help="format to use for looking for update content")
    parser.add_argument("-n", "--no-install", action="store_true",
                        help="Dry run the UI - no install performed.")
    args = parser.parse_args()
    return args


def main():
    """Entry point for the ui"""
    setup()
    args = handle_options()
    ins = Installation(**vars(args))
    ins.run()

if __name__ == '__main__':
    main()
