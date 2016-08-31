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
# pylint: disable=W0102
# Intended manipulation of internal state of the UI
# pylint: disable=W0212
# global is handy here for now, but this could be fixed up
# pylint: disable=W0603
# Avoiding too many nested blocks is definitely a clean up todo
# pylint: disable=R0101
# Early on self not being used, will consider later on
# pylint: disable=R0201
# Use of too many returns is hard to avoid here, but it is something to
# consider when refactoring
# pylint: disable=R0911
# Too many variables isn't really a problem though it looks a bit strange
# pylint: disable=R0914
# Use of too many statements isn't something to avoid for now
# pylint: disable=R0915
# broad exceptions are fine
# pylint: disable=W0703
# use of format strings this way is prefered unless convinced otherwise
# pylint: disable=W1202
# pylint: disable=C0302
# pylint: disable=R0204

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
import time
import ipaddress
import netifaces
import pycurl

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
MAX_WIDTH = 136
MAX_HEIGHT = 42
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
    if LINES > MAX_HEIGHT:
        LINES = int(MAX_HEIGHT)
    if COLUMNS > MAX_WIDTH:
        COLUMNS = int(MAX_WIDTH)


def ister_wrapper(fn_name, *args):
    """Wrapper to dynamically call ister validations"""
    try:
        ister.__getattribute__(fn_name)(*args)
    except Exception as exc:
        return exc
    return None


def get_disk_info(disk):
    """Return dictionary with disk information"""
    info = {'partitions': []}
    cmd = ['/usr/bin/fdisk', '-l', disk]
    output = subprocess.check_output(cmd).decode('utf-8')
    lines = output.split('\n')
    expr = re.compile('^Device')
    # discard header...
    while len(lines) > 0:
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
            buttons.append(urwid.Padding(button, 'center', len(label) + 4))

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
        max_pos = len(self._menu)
        if 'tab' in keys or 'down' in keys:
            self._lb.focus_position = (i + 1) % max_pos
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
    def __init__(self, title, fields, buttons=["Previous", "Next"]):
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
                       ('pack', urwid.Text(title)),
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
            button = urwid.Button(label)
            urwid.connect_signal(button, 'click', self._on_click)
            button = urwid.AttrMap(button, None, focus_map='reversed')
            buttons.append(urwid.Padding(button, 'center', width=12))

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
    """Defines a step tu be run by the installation handler"""
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
        else:
            tmp = Alert(u'Error!', 'Not implemented yet')
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

    def run_ui(self):
        """Method to run the ui and return the action"""
        return 'Next'

    def build_ui_widgets(self, *_):
        """Method to build all the widgets"""
        self._ui_widgets = None

    def build_ui(self):
        """Method to create the ui"""
        self._ui = True


class ConditionalStep(ProcessStep):
    """Defines a conditional ProcessStep"""
    def get_next_step(self, action):
        """Returns the process step matched by action"""
        if action == 'Exit':
            exit(0)
        if action in self.action_map:
            targets = self.action_map[action]
            if targets[1]:
                if not self.validate_condition():
                    return targets[1]
            return targets[0]
        else:
            tmp = Alert(u'Error!', 'Not implemented yet')
            tmp.do_alert()
            return self

    def set_action(self, action, target, target_false=None, **_):
        """Sets process step to be matched by a key"""
        self.action_map[action] = (target, target_false)

    def validate_condition(self):
        """Abstract method to validate step condition"""
        return True


class NetworkRequirements(ProcessStep):
    """UI to verify and configure network connectivity to
    https://www.clearlinux.org for the installer"""
    # pylint: disable=R0902
    def __init__(self):
        # allow time to start network unit on boot
        time.sleep(.8)
        super(NetworkRequirements, self).__init__()
        static_button = urwid.Button('Set static ip configuration',
                                     on_press=self._static_configuration)
        reset_button = urwid.Button('Reset network to default configuration',
                                    on_press=self._reset_network)
        proxy_button = urwid.Button('Set installer proxy settings',
                                    on_press=self._set_proxy)
        static_button = urwid.AttrMap(static_button, None,
                                      focus_map='reversed')
        reset_button = urwid.AttrMap(reset_button, None,
                                     focus_map='reversed')
        proxy_button = urwid.AttrMap(proxy_button, None,
                                     focus_map='reversed')
        self.static_col = urwid.Columns([static_button, urwid.Divider()])
        self.reset_col = urwid.Columns([reset_button, urwid.Divider()])
        self.proxy_col = urwid.Columns([proxy_button, urwid.Divider()])
        self.installer_proxy = urwid.Edit('installer proxy: ', '')
        self.progress = urwid.Text('Step 1 of 5')
        self.static_ip = None
        self.interface = None
        self.gateway = None
        self.error = None
        self.config = None
        self.ifaceaddrs = None

    def handler(self, config):
        # make config an insance variable so we can copy proxy settings to it
        self.config = config

        # normally much of this would belong in __init__, but we want it
        # refreshed every time the user refreshes/returns to the screen
        self.build_ui_widgets()
        self.build_ui()
        self._action = self.run_ui()
        if self._action == 'Refresh':
            # re-build the widgets
            return self._action

        self.error = ''
        try:
            ipaddress.ip_address(self.static_ip.get_edit_text())
        except Exception as err:
            self.error = 'The configuration for "ip" is invalid {}'.format(err)
            # an empty action signals to refresh the page
            self._action = ''
        if self.interface.get_edit_text() not in self.ifaceaddrs.keys():
            self.error = 'Interface "{}" not detected'\
                         .format(self.interface.get_edit_text())
            # an empty action signals to refresh the page
            self._action = ''

        if not self.error:
            config = self.config
            return self._action
        else:
            Alert('Error!', self.error).do_alert()
            self.error = ''
            return self._action

    def build_ui_widgets(self):
        """Build ui handler
        The last urwid Divider helps the tab movement to work"""
        fmt = '{0:>25}'
        wired = '* Connection to clearlinux.org: '
        wired += 'established' if self._network_connection() else \
                 'none detected, install will fail'
        wired_req = urwid.Text(wired)
        interface_ip = self._find_interface_ip()
        interface_msg = 'Interface: '
        ip_msg = 'IP address: '
        if interface_ip:
            interface_res = interface_ip[0]
            ip_res = interface_ip[1]
        else:
            interface_res = 'none found'
            ip_res = 'none found'

        self.interface = urwid.Edit(fmt.format(interface_msg),
                                    interface_res)
        self.static_ip = urwid.Edit(fmt.format(ip_msg), ip_res)
        # pylint: disable=E1103
        try:
            gateway = netifaces.gateways()['default'][netifaces.AF_INET][0]
        except Exception:
            gateway = 'none found'

        self.gateway = urwid.Edit(fmt.format('Gateway: '), gateway)
        self._ui_widgets = [self.progress,
                            urwid.Divider(),
                            wired_req,
                            urwid.Divider(),
                            self.installer_proxy,
                            urwid.Divider(),
                            self.proxy_col,
                            urwid.Divider(),
                            self.interface,
                            self.static_ip,
                            self.gateway,
                            urwid.Divider(),
                            self.static_col,
                            urwid.Divider(),
                            self.reset_col,
                            urwid.Divider()]

    def build_ui(self):
        self._ui = SimpleForm(u'Network Requirements',
                              self._ui_widgets, buttons=["Refresh", "Ok"])

    def run_ui(self):
        return self._ui.do_form()

    def _network_connection(self):
        """Check if connection to https://www.clearlinux.org is available"""
        # pylint: disable=E1103

        class Storage(object):
            """Storage class for pycurl"""
            # pylint: disable=R0903
            def __init__(self):
                self.buffer = ''
                self.line = 0

            def store(self, buf):
                """Grab curl output"""
                self.line = self.line + 1
                self.buffer = "{}{}: {}".format(self.buffer, self.line, buf)

            def __str__(self):
                return self.buffer

        headers = Storage()

        curl = pycurl.Curl()
        curl.setopt(curl.URL, 'https://www.clearlinux.org')
        curl.setopt(curl.HEADER, 1)
        curl.setopt(curl.NOBODY, 1)
        curl.setopt(curl.HEADERFUNCTION, headers.store)
        curl.setopt(curl.TIMEOUT, 1)
        if 'Proxy' in self.config and self.config['Proxy']:
            curl.setopt(curl.PROXY, self.config['Proxy'])

        try:
            curl.perform()
        except Exception:
            return False

        return bool('401' not in str(headers))

    def _static_configuration(self, _):
        """
        Writes the configuration on /etc/systemd/network/10-en-static.network
        """
        try:
            ipaddress.ip_address(self.static_ip.get_edit_text())
        except:
            # the main loop is waiting on this method to exit so it can report
            # the error
            raise urwid.ExitMainLoop()

        if self.interface.get_edit_text() not in self.ifaceaddrs.keys():
            # the main loop is waiting on this method to exit so it can report
            # the error
            raise urwid.ExitMainLoop()

        path = '/etc/systemd/network/'
        if not os.path.exists(path):
            os.makedirs(path)

        with open(path + "10-en-static.network", "w") as nfile:
            nfile.write("[Match]\n")
            nfile.write("Name={}\n\n".format(self.interface.get_edit_text()))
            nfile.write("[Network]\n")
            nfile.write("Address={0}\n".format(self.static_ip.get_edit_text()))
            nfile.write("Gateway={0}\n".format(self.gateway.get_edit_text()))

        try:
            subprocess.call(['/usr/bin/systemctl', 'restart',
                             'systemd-networkd', 'systemd-resolved'])
        except Exception as err:
            Alert('Error!', err).do_alert()

        raise urwid.ExitMainLoop()

    def _reset_network(self, _):
        """Reset the network to original configuration by removing static
        network file and restarting network services"""
        try:
            os.remove('/etc/systemd/network/10-en-static.network')
        except FileNotFoundError:
            pass

        try:
            subprocess.call(['/usr/bin/systemctl', 'restart',
                             'systemd-networkd', 'systemd-resolved'])
        except:
            raise urwid.ExitMainLoop()

        # give the network a chance to start up again
        time.sleep(.1)
        raise urwid.ExitMainLoop()

    def _set_proxy(self, _):
        """Set the user defined proxy for the installer in the template"""
        if self.installer_proxy.get_edit_text():
            self.config['Proxy'] = self.installer_proxy.get_edit_text()

        raise urwid.ExitMainLoop()

    def _find_interface_ip(self):
        """Find active interface and ip address"""
        # pylint: disable=E1103
        addrs = {}
        af_inet = netifaces.AF_INET
        for if_name in netifaces.interfaces():
            ifaddrs = netifaces.ifaddresses(if_name)
            if af_inet in ifaddrs:
                ip_addrs = ifaddrs[af_inet][0]
                if ip_addrs['addr'] and '127.0.' not in ip_addrs['addr']:
                    addrs[if_name] = ip_addrs['addr']

        self.ifaceaddrs = addrs
        for interface in addrs:
            if interface.startswith('e'):
                return (interface, addrs[interface])


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
                           'for more information.\n\n'
        self._msg_suffix = 'Install the telemetrics-client bundle later if '\
                           'you change your mind.'
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

        config['Bundles'] = list()
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
            button = urwid.Button(choice)
            urwid.connect_signal(button, 'click', self._item_chosen, choice)
            button = urwid.AttrMap(button, None, focus_map='reversed')
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
        self.text = ('Step {} of {}\n\n'
                     'All data on {} will be erased!'
                     ' Do you want to proceed with the installation?\n\n'
                     .format(self._cur_step, self._tot_steps, disk))
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
            button = urwid.Button(self.choices[key])
            urwid.connect_signal(button, 'click', self._item_chosen, key)
            button = urwid.AttrMap(button, None, focus_map='reversed')
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
        self.disks = self._get_list_of_disks()
        self.progress = 'Step {} of {}'.format(cur_step, tot_steps)

    def handler(self, config):
        self.build_ui_widgets()

        self._ui = SimpleForm(u'Choose target device for installation',
                              self._ui_widgets, buttons=['Previous'])
        self._action = None
        self._clicked = None

        self._action = self.run_ui()

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

    def build_ui_widgets(self):
        self._ui_widgets = [urwid.Text(self.progress)]
        if len(self.disks) == 0:
            widget = urwid.Text(u"No free devices found.")
            self._ui_widgets.append(widget)
        else:
            for disk in self.disks:
                button = urwid.Button(disk)
                urwid.connect_signal(button, 'click', self._item_chosen, disk)
                button = urwid.AttrMap(button, None, focus_map='reversed')
                self._ui_widgets.append(button)

    def _get_list_of_disks(self):
        """"Queries for the available disks discarding the inst. source"""
        dir_path = '/sys/block'
        disks = [device for device in os.listdir(dir_path)
                 if 'pci' in os.readlink('{0}/{1}'.format(dir_path, device))]
        unmounted = list()

        output = subprocess.check_output([
            '/usr/bin/lsblk', '-o',
            'MOUNTPOINT,PARTUUID']).decode('utf-8')
        parts = output.split('\n')

        expr = re.compile(r'(\S*)\s*(\S*)')
        for line in parts:
            match = expr.match(line)
            if match:
                if match.group(1) == '/':
                    part_uuid = match.group(2)

        root_disk = os.readlink('/dev/disk/by-partuuid/{0}'.format(part_uuid))
        for disk in disks:
            if disk not in root_disk:
                unmounted.append(disk)
        return unmounted


class SelectMultiDeviceStep(SelectDeviceStep):
    """UI to display the available disks"""
    def handler(self, config):
        config["Disks"] = self.disks[:]
        other_options = ['Previous', 'Done']
        self.build_ui_widgets()
        self._ui = SimpleForm(u'Choose a drive to partition using cgdisk tool',
                              self._ui_widgets, buttons=other_options)
        self._clicked = None
        self._action = self.run_ui()
        if self._clicked:
            config["CurrentDisk"] = self._clicked
            return 'Next'
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
    def __init__(self, cur_step, tot_steps):
        super(MountPointsStep, self).__init__()
        self.progress = urwid.Text('Step {} of {}'.format(cur_step, tot_steps))

    def handler(self, config):
        # pylint: disable=R0914
        mount_d = dict()
        self.display_fmt = '{0:12}{1:12}{2:30}{3:20}{4:6}'
        choices = self._get_partitions(config)
        other_options = ['Previous', 'Done']
        required_mounts = ['/', '/boot']
        validated = False
        while not validated:
            self.build_ui_widgets(choices)
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
                    idx = choices.index(self._clicked)
                    _format = 'Yes' if mount_d[point]['format'] else ''
                    choices[idx] = self.display_fmt.format(partition,
                                                           size,
                                                           part_type,
                                                           point,
                                                           _format)
            elif self._action == 'Done':
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
        partitions = [choice for choice in choices
                      if choice not in other_options]
        self._search_swap(partitions, config, mount_d)
        exc = ister_wrapper('validate_disk_template', config)
        if exc is not None:
            return exc
        return self._action

    def _item_chosen(self, _, choice):
        self._clicked = choice
        raise urwid.ExitMainLoop()

    def build_ui_widgets(self, choices, *_):
        self._ui_widgets = [self.progress]
        if len(choices) == 0:
            widget = urwid.Text(u"No partitions found.")
            self._ui_widgets.append(widget)
        else:
            wgt = urwid.Text("  " + self.display_fmt.format("Disk",
                                                            "Size",
                                                            "Partition type",
                                                            "Mount point",
                                                            "Format?"))
            self._ui_widgets.append(wgt)
            for part in choices:
                button = urwid.Button(part)
                urwid.connect_signal(button, 'click', self._item_chosen, part)
                button = urwid.AttrMap(button, None, focus_map='reversed')
                self._ui_widgets.append(button)

    def _save_config(self, config, mount_d):
        config['PartitionLayout'] = list()
        config['FilesystemTypes'] = list()
        config['PartitionMountPoints'] = list()
        for point in mount_d:
            _type = 'EFI' if point == '/boot' else 'linux'
            part = mount_d[point]['part']
            disk = ''.join(x for x in part if not x.isdigit())
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
                if 'TYPE="' in subprocess.check_output(
                        'blkid | grep {0}'
                        .format(disk+part), shell=True).decode('utf-8'):
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
                                                 shell=True).decode('utf-8')
                pttr = 'TYPE="'
                if pttr in output:
                    idx = output.index(pttr)
                    output = output[idx + len(pttr):]
                    output = output[: output.index('"')]
                    if output == 'swap':
                        disk = ''.join(x for x in part if not x.isdigit())
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

    def _get_partitions(self, config):
        result = list()
        for disk in config['Disks']:
            disk_info = get_disk_info('/dev/{0}'.format(disk))
            for part in disk_info['partitions']:
                result.append(self.display_fmt.format(disk+part['number'],
                                                      part['size'],
                                                      part['type'],
                                                      '', ''))
        return result


class BundleSelectorStep(ProcessStep):
    """UI which displays the bundle list to be installed"""
    def __init__(self, cur_step=None, tot_steps=None):
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
                                             shell=True).decode('utf-8')
        except Exception:
            output = 'none'
        if 'qemu' in output or 'kvm' in output:
            kernel = {'name': 'kernel-kvm',
                      'desc': 'Required to run Clear Linux OS on kvm'}
        else:
            kernel = {'name': 'kernel-native',
                      'desc': 'Required to run Clear Linux OS on baremetal'}
        self.required_bundles.extend([
            {'name': 'os-core',
             'desc': 'Minimal packages to have Clear Linux OS fully '
                     'functional'},
            kernel,
            {'name': 'os-core-update',
             'desc': 'Required to update the system'},
            {'name': 'os-utils',
             'desc': 'A core set of OS utilities'}])
        if cur_step and tot_steps:
            self.progress = urwid.Text('Step {} of {}'.format(cur_step,
                                                              tot_steps))

    def handler(self, config):
        if not self._ui_widgets:
            self.build_ui_widgets()
        if not self._ui:
            self.build_ui()
        self._action = self.run_ui()
        for widget in self._ui_widgets[2:]:
            if isinstance(widget, urwid.Columns):
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
        return self._action

    def run_ui(self):
        return self._ui.do_form()

    def build_ui_widgets(self):
        self._ui_widgets = []
        if self.progress:
            self._ui_widgets = [self.progress, urwid.Divider()]
        self._ui_widgets.extend([urwid.Text('Select the bundles to install:'),
                                 urwid.Divider()])
        for bundle in self.bundles:
            check = urwid.CheckBox(bundle['name'])
            desc_text = urwid.Text(bundle['desc'])
            column = urwid.Columns([check, ('weight', 2, desc_text)])
            self._ui_widgets.append(column)

        self._ui_widgets.extend([urwid.Divider(),
                                 urwid.Text('--- required ---')])
        for bundle in self.required_bundles:
            text_name = urwid.Text('[X] {0}'.format(bundle['name']))
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
            button = urwid.Button(self.choices[key])
            urwid.connect_signal(button, 'click', self._item_chosen, key)
            button = urwid.AttrMap(button, None, focus_map='reversed')
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

        return self._action


class UserConfigurationStep(ProcessStep):
    """UI to gather the user info"""
    # pylint: disable=R0902
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
        tmp['password'] = crypt.crypt(self.edit_password.get_edit_text(),
                                      'aa')
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
            button = urwid.Button(self.choices[key])
            urwid.connect_signal(button, 'click', self._item_chosen, key)
            button = urwid.AttrMap(button, None, focus_map='reversed')
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

        return self._action


class StaticIpStep(ProcessStep):
    # pylint: disable=R0902
    """UI to gather the static ip configuration"""
    def __init__(self, cur_step, tot_steps):
        super(StaticIpStep, self).__init__()
        fmt = '{0:30}'
        self.edit_ip = IpEdit(fmt.format('Enter ip address:'))
        self.edit_mask = IpEdit(fmt.format('Enter mask:'))
        self.edit_gateway = IpEdit(fmt.format('Enter gateway:'))
        self.edit_dns = IpEdit(fmt.format('Enter DNS (optional):'))
        self.progress = urwid.Text('Step {} of {}'.format(cur_step, tot_steps))
        self.subtitle = urwid.Text('Static IP configuration')

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
                try:
                    ipaddress.ip_address(text)
                except Exception:
                    error = ('The configuration for "{0}" is invalid'
                             .format(field))
                    break
            if error == '':
                for key in values:
                    if values[key] != 1:
                        error = 'Repeated values'
                        break
            if error == '' and self.edit_dns.get_edit_text() != '':
                try:
                    ipaddress.ip_address(self.edit_dns.get_edit_text())
                except Exception:
                    error = 'The configuration for "dns" is invalid'
            if error == '':
                self._save_config(config)
                return self._action
            Alert('Error!', error).do_alert()

    def run_ui(self):
        return self._ui.do_form()

    def build_ui_widgets(self):
        self._ui_widgets = [self.progress,
                            urwid.Divider(),
                            self.subtitle,
                            urwid.Divider(),
                            self.edit_ip,
                            urwid.Divider(),
                            self.edit_mask,
                            urwid.Divider(),
                            self.edit_gateway,
                            urwid.Divider(),
                            self.edit_dns,
                            urwid.Divider()]

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
        self._steps = list()
        self.start = NetworkRequirements()
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
            with open('/etc/ister.json') as infile:
                json_string = infile.read()
                self.installation_d = json.loads(json_string)
        except Exception as exep:
            self.logger.error(exep)
            self._exit(-1, 'Template file does not exist')

    def _init_actions(self):
        telem_disclosure = TelemetryDisclosure(2, 5)
        startmenu = StartInstaller(3, 5)
        config_hostname = ConfigureHostname(7, 11)
        confirm_disk_wipe = ConfirmDiskWipe(5, 5)
        confirm_disk_wipe2 = ConfirmDiskWipe(6, 11)
        part_menu = PartitioningMenu(4, 11)
        automatic_device = SelectDeviceStep(4, 5)
        manual_part_device = SelectMultiDeviceStep(5, 11)
        manual_nopart_device = SelectDeviceStep(5, 11)
        terminal_cgdisk = TerminalStep()
        set_mount_points = MountPointsStep(6, 11)
        bundle_selector = BundleSelectorStep(8, 11)
        confirm_user = ConfirmUserMenu(9, 11)
        user_configuration = UserConfigurationStep(9, 11)
        confirm_dhcp = ConfirmDHCPMenu(10, 11)
        static_ip_config = StaticIpStep(10, 11)
        confirm_installation = ConfirmStep('Attention!', 'Setup is complete. '
                                           'Do you want to begin '
                                           'installation?', 11, 11)
        run = RunInstallation()

        self.start.set_action('Ok', telem_disclosure)
        self.start.set_action('Refresh', self.start)
        self.start.set_action('', self.start)
        telem_disclosure.set_action('Previous', self.start)
        telem_disclosure.set_action('Next', startmenu)
        startmenu.set_action('Previous', telem_disclosure)
        startmenu.set_action('Automatic', automatic_device)
        automatic_device.set_action('Previous', startmenu)
        automatic_device.set_action('Next', confirm_disk_wipe)
        confirm_disk_wipe.set_action('No', automatic_device)
        confirm_disk_wipe.set_action('Yes', run)
        startmenu.set_action('Manual(Advanced)', part_menu)
        part_menu.set_action('Manual', manual_part_device)
        part_menu.set_action('Auto', manual_nopart_device)
        part_menu.set_action('Previous', startmenu)
        manual_part_device.set_action('Previous', part_menu)
        manual_part_device.set_action('Next', terminal_cgdisk)
        manual_part_device.set_action('Done', set_mount_points)
        terminal_cgdisk.set_action('Next', manual_part_device)
        set_mount_points.set_action('Previous', manual_part_device)
        set_mount_points.set_action('Done', config_hostname)
        manual_nopart_device.set_action('Previous', part_menu)
        manual_nopart_device.set_action('Next', confirm_disk_wipe2)
        confirm_disk_wipe2.set_action('No', manual_nopart_device)
        confirm_disk_wipe2.set_action('Yes', config_hostname)
        config_hostname.set_action('Previous', part_menu)
        config_hostname.set_action('Next', bundle_selector)
        bundle_selector.set_action('Previous', config_hostname)
        bundle_selector.set_action('Next', confirm_user)
        confirm_user.set_action('mkuser', user_configuration)
        confirm_user.set_action('nouser', confirm_dhcp)
        confirm_user.set_action('Previous', bundle_selector)
        user_configuration.set_action('Previous', confirm_user)
        user_configuration.set_action('Next', confirm_dhcp)
        confirm_dhcp.set_action('dhcp', confirm_installation)
        confirm_dhcp.set_action('staticip', static_ip_config)
        confirm_dhcp.set_action('Previous', confirm_user)
        static_ip_config.set_action('Previous', confirm_dhcp)
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
        if self.args['dry_run']:
            exit()
        if reboot:
            subprocess.call('reboot')
        subprocess.call('poweroff')

    def run(self):
        """Starts up the installer ui"""
        pprint.PrettyPrinter(indent=4)
        step = self.start
        i = 0
        while not isinstance(step, RunInstallation):
            action = step.handler(self.installation_d)
            self.logger.debug(
                "Stepping to {0} screen".format(type(step).__name__))
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
        for bundle in BundleSelectorStep().required_bundles:
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
            message = 'Successful installation, the system will be rebooted'
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
                        default="https://download.clearlinux.org/update",
                        help="URL to use for looking for update versions")
    parser.add_argument("-C", "--contenturl", action="store",
                        default="https://download.clearlinux.org/update",
                        help="URL to use for looking for update content")
    parser.add_argument("-f", "--format", action="store", default=None,
                        help="format to use for looking for update content")
    parser.add_argument("-n", "--no-install", action="store_true",
                        help="Dry run the UI - no install performed.")
    parser.add_argument("-d", "--dry-run", action="store_true",
                        help="Dry run the UI locally in test mode, no poweroff"
                        "on exit, no install performed.")
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
