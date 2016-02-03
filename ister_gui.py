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

import argparse
import crypt
import ister
import json
import logging
import os
import re
import subprocess
import sys
import time

import urwid

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
PERCENTAGE_W = 60
PERCENTAGE_H = 40
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
        return str(exc)
    return None


class Widget(object):
    """Main UI display element base class"""
    def __init__(self, *args, **kwargs):
        # args unused for now
        del args
        self.title = kwargs.get('title', '')
        self.widget = None
        self.response = None
        self.loop = None

    def exit_program(self, button=None):
        """Stop the UI"""
        # button unused for now
        del button
        raise urwid.ExitMainLoop()

    def redraw(self):
        """Redraw UI element"""
        if self.loop is None:
            raise Exception('redraw can not be called before main_loop')
        else:
            self.loop.draw_screen()

    def init_widget(self):
        """Setup the UI element with default settings"""
        header = urwid.Padding(urwid.Text(self.title), left=2, right=2)
        header = urwid.AttrWrap(header, 'header')
        self.widget = urwid.Frame(self.widget, header=header)
        self.widget = urwid.Overlay(self.widget,
                                    urwid.SolidFill(u' '),
                                    align='center',
                                    width=('relative', PERCENTAGE_W),
                                    valign='middle',
                                    height=('relative', PERCENTAGE_H))
        self.widget = urwid.AttrMap(self.widget, 'bg')
        if self.loop:
            self.loop.widget = self.widget
        else:
            self.loop = urwid.MainLoop(self.widget, palette=PALETTE)

    def main_loop(self, func=None):
        """Display UI loop"""
        if func is None:
            self.loop.run()
        else:
            self.loop.start()
            self.loop.draw_screen()
            func()
            self.loop.stop()


class Confirm(Widget):
    """Confirmation UI element"""
    def __init__(self, text, *args, **kwargs):
        super(Confirm, self).__init__(*args, **kwargs)
        self.text = text
        self.only_ok = kwargs.get('only_ok', False)
        self.has_answer = False
        self.init_widget()
        self.response=''

    def init_widget(self):
        """Add text and actions for Confirmation button"""
        text = urwid.Text(('I say', self.text))
        btns = list()
        if self.only_ok:
            btns.append(urwid.AttrMap(urwid.Button(u'Ok'), None, 'reversed'))
            urwid.connect_signal(btns[-1].original_widget,
                                 'click',
                                 self.on_yes_clicked)
        else:
            btns.append(urwid.AttrMap(urwid.Button(u'No'),
                                      None, 'reversed'))
            urwid.connect_signal(btns[-1].original_widget,
                                 'click',
                                 self.on_no_clicked)
            btns.append(urwid.AttrMap(urwid.Button(u'Yes'), None, 'reversed'))
            urwid.connect_signal(btns[-1].original_widget,
                                 'click',
                                 self.on_yes_clicked)
        buttons = [(8, btn) for btn in btns]
        div = urwid.Divider()
        buttons = urwid.Columns(buttons, dividechars=5)
        pile = urwid.Pile([text, div, buttons])
        frame = urwid.Filler(pile, valign='middle')
        frame = urwid.Padding(frame, 'center', ('relative', 50))
        self.widget = urwid.AttrMap(frame, 'banner')
        super(Confirm, self).init_widget()

    def on_no_clicked(self, button):
        """Setup handler for no button"""
        self.has_answer = True
        self.response = 'no'
        del button
        raise urwid.ExitMainLoop()

    def on_yes_clicked(self, button):
        """Setup handler for yes button"""
        del button
        self.response = 'yes'
        self.has_answer = True
        raise urwid.ExitMainLoop()


class Edit(Widget):
    """Class for an editable field"""
    def __init__(self, question, *args, **kwargs):
        super(Edit, self).__init__(*args, **kwargs)
        self.questions = question
        self.answers = dict()
        self.has_answer = False
        self.widgets = dict()
        self.maps = dict()
        self.maps_out = dict()
        self.init_widget()

    def init_widget(self):
        """Initialize the ui objects"""
        ask_l = list()
        for question in self.questions:
            mask = question.get('mask', None)
            if 'type' not in question:
                edit = urwid.Edit(('I say', question['text']), mask=mask)
            else:
                edit = question['type'](('I say', question['text']))
            if 'map_output' in question:
                if question['key'] not in self.maps:
                    self.maps[question['key']] = question['map_output']
                if question['map_output'] not in self.maps_out:
                    self.maps_out[question['map_output']] = list()
                self.maps_out[question['map_output']]\
                    .append({'key': question['key'],
                             'ln': question['map_ln']})
                urwid.connect_signal(edit,
                                     'change',
                                     self.on_edit_change,
                                     question['key'])
            self.widgets[question['key']] = edit
            ask_l.append(edit)
            ask_l.append(urwid.Divider())
        btn_exit = urwid.Button(u'Exit')
        btn_next = urwid.Button(u'Next')
        buttons = [(8, btn) for btn in [btn_exit, btn_next]]
        buttons = urwid.Columns(buttons, dividechars=5)
        ask_l.append(buttons)
        pile = urwid.Pile(ask_l)
        frame = urwid.Filler(pile, valign='middle')
        frame = urwid.Padding(frame, left=2, right=2)
        self.widget = urwid.AttrMap(frame, 'banner')
        urwid.connect_signal(btn_exit, 'click', self.on_exit_clicked)
        urwid.connect_signal(btn_next, 'click', self.on_next_clicked)
        super(Edit, self).init_widget()

    def on_edit_change(self, edit, new_edit_text, _id):
        """Refresh edit widget's display text"""
        # edit unused for now
        del edit
        if _id not in self.maps:
            return
        text = ''.join([(self.widgets[item['key']].get_edit_text()
                         if item['key'] != _id
                         else new_edit_text)[:item['ln']]
                        for item in self.maps_out[self.maps[_id]]])
        self.widgets[self.maps[_id]].set_edit_text(text.lower())

    def on_exit_clicked(self, button):
        """edit widget exit button handler"""
        # button unused for now
        del button
        raise urwid.ExitMainLoop()

    def on_next_clicked(self, button):
        """edit widget next button handler"""
        # button unused for now
        del button
        self.has_answer = True
        for key, widget in self.widgets.items():
            self.answers[key] = (widget.get_edit_text()
                                 if isinstance(widget, urwid.Edit)
                                 else widget.get_state())
        raise urwid.ExitMainLoop()


class Menu(Widget):
    """Class for a menu item list"""
    def __init__(self, menu_choices, *args, **kwargs):
        super(Menu, self).__init__(*args, **kwargs)
        self.choices = menu_choices[:]
        self.checkbox_type = kwargs.get('checkbox', False)
        self.required_choices = kwargs.get('required_choices', list())[:]
        self.choices.extend(self.required_choices)
        self.response = self.required_choices
        self.init_widget()

    def init_widget(self):
        """Initialize the ui objects"""
        body = [urwid.Divider()]
        item_class = urwid.CheckBox if self.checkbox_type else urwid.Button
        for choice in self.choices:
            button = item_class(choice)
            if self.checkbox_type:
                if choice in self.required_choices:
                    text = '[X] {0}'.format(choice)
                    body.append(urwid.AttrMap(urwid.Text(text),
                                              None,
                                              focus_map='reversed'))
                    continue
                urwid.connect_signal(button,
                                     'change',
                                     self.check_chosen,
                                     choice)
            else:
                urwid.connect_signal(button, 'click', self.item_chosen, choice)
            body.append(urwid.AttrMap(button, None, focus_map='reversed'))
        if self.checkbox_type:
            body.append(urwid.Divider())
            exit_btn = urwid.Button('Done')
            urwid.connect_signal(exit_btn, 'click', self.exit_chosen, exit_btn)
            body.append(exit_btn)
        listbox = urwid.ListBox(urwid.SimpleFocusListWalker(body))
        frame = urwid.Padding(listbox, left=2, right=2)
        self.widget = urwid.AttrMap(frame, 'banner')
        super(Menu, self).init_widget()

    def item_chosen(self, button, choice):
        """Implement item selection"""
        self.response = choice
        self.exit_chosen(button, choice)

    def exit_chosen(self, button, choice):
        """menu item exit handler"""
        # button unused for now
        del button
        # choice unused for now
        del choice
        self.exit_program()

    def check_chosen(self, checkbox, new_state, choice):
        """menu item selection handler"""
        # checkbox unused for now
        del checkbox
        if new_state:
            self.response.append(choice)
        else:
            self.response.remove(choice)


class Messagebox(Widget):
    """Message UI element"""
    def __init__(self, body, *args, **kwargs):
        super(Messagebox, self).__init__(*args, **kwargs)
        self.body = body
        self.init_widget()

    def init_widget(self):
        """Initialize message element text and settings"""
        text = '\n'.join(self.body.split('\n')[-1*LINES + 1:])
        fill = urwid.Filler(urwid.Text(('banner', text), align='center'))
        self.frame = urwid.Padding(fill, left=2, right=2)
        self.widget = urwid.AttrMap(self.frame, 'banner')
        super(Messagebox, self).init_widget()

    def update_text(self, text):
        """Update message text"""
        self.body = text
        self.init_widget()
        self.redraw()


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


class Installation(object):
    """Main object for installer ui"""

    # pylint: disable=too-many-instance-attributes

    def __init__(self, *args, **kwargs):
        # args unused for now
        del args
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
        self.process = [
            self._configure_installation,
            self._configure_hostname,
            self._configure_username,
            self._bundle_selector,
        ]
        self.device = None
        self.mount_points = dict()
        try:
            with open('/etc/ister.json') as file:
                json_string = file.read()
                self.logger.debug(json_string)
                self.installation_d = json.loads(json_string)
        except Exception as exep:
            self.logger.error(exep)
            self._exit(-1, 'Template file does not exist')

    def _exit(self, int_code, error_message=None):
        """UI to display error messages"""
        if error_message is None:
            error_message = 'An error ocurred during the installation, ' \
                            'please check the log file'
        self.current_w = Confirm(error_message,
                                 title='Error',
                                 only_ok=True)
        self.current_w.main_loop()
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

        while True:
            self._select_auto_or_manual()
            if 'Auto' in self.current_w.response:
                partitions = self.get_part_list_from_fdisk()
                self.current_w = Confirm('WARNING! All data on /dev/sda will be erased!\n\n' +
                                    partitions + '\n\nProceed?',
                                    title='Confirm Auto-install')
                self.current_w.main_loop()
                if self.current_w.response == 'yes':
                    self.automatic_install()
                    break
            elif 'Manual' in self.current_w.response:
                self.manual_install()
                break
            else:
                return

        self.current_w = Confirm('The installation has been completed '
                                 'successfully. The system will be rebooted.',
                                 title='Success',
                                 only_ok=True)
        self.current_w.main_loop()

    def _select_auto_or_manual(self):
        """UI to select the installation type"""
        choices = u'Auto-install Manual(Advanced) Exit'.split()
        self.current_w = Menu(choices,
                              title=u'Which type of installation do you want?')
        self.current_w.main_loop()

    def automatic_install(self):
        """Initial installation method, use the default template unmodified"""
        with open('/tmp/template.json', 'w') as file:
            self.logger.debug(self.installation_d)
            file.write(json.dumps(self.installation_d))
        message = u'Automatic installation of ClearLinux v{0}' \
            .format(self.installation_d['Version'])
        self.current_w = Messagebox(u'Starting installation...\n',
                                    title=message)

        def handle():
            """main_loop's closure calling the installer"""
            supported = [
                {'name': 'url', 'out': '--url={0}'},
                {'name': 'format', 'out': '--format={0}'}]
            flags = ' '.join([item['out'].format(self.args[item['name']])
                              for item in supported
                              if self.args[item['name']] is not None])
            ister_cmd = [sys.executable,
                         '/usr/bin/ister.py',
                         '-t',
                         '/tmp/template.json',
                         flags]
            self.logger.debug(' '.join(ister_cmd))
            proc = subprocess.Popen(['bash', '-c', ' '.join(ister_cmd)],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
            self.logger.debug('Starting ister')
            errors = [
                r'Unable to download [0-9]+ Manifest.MoM']
            steps = [
                {'match': 'mkfs', 'msg': 'Creating partitions'},
                {'match': 'swupd-client', 'msg': 'Swupd done'},
                {'match': 'Inspected', 'equal': True},
                {'match': 'were missing', 'equal': True},
                {'match': 'did not match', 'equal': True},
                {'match': 'found which should be deleted', 'equal': True}]
            index = 0
            while True:
                line = (proc.stdout.readline().decode('utf-8')
                        .replace('\n', ''))
                if line == '' and proc.poll() is not None:
                    break

                for error in errors:
                    if re.match(error, line):
                        self._exit(-1, 'Ister returned the following error: '
                                   '"{0}"'.format(line))

                self.logger.debug(line)
                if index >= len(steps) or steps[index]['match'] not in line:
                    continue
                message = (line if 'equal' in steps[index]
                           else steps[index]['msg'])
                self.current_w.update_text(u'{0}{1}\n'
                                           .format(self.current_w.body,
                                                   message))
                index += 1
            self.logger.debug('Ister output done')
            self.logger.info('Ister returncode = {0}'.format(proc.returncode))
            time.sleep(2)

            if proc.returncode != 0:
                self.logger.debug(proc.stderr.read())
                self._exit(-1, 'Installation error. See /var/log/ister_gui.log for details.\n\nHint: Log in on another tty (ctrl-alt-F2)')

        self.current_w.main_loop(handle)

    def manual_install(self):
        """front end to run all the manual installation processes"""
        for func in self.process:
            if not func():
                exit(0)

        self.automatic_install()

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

    def _select_device(self):
        """UI to ask the user the device where ister will install"""
        # It queries all the disks available on the system
        choices = self._get_list_of_disks()
        self.current_w = Menu(choices, title='Select the destination disk')
        self.current_w.main_loop()
        self.device = self.current_w.response

    def _manage_partitions(self):
        """UI to ask the user if he wants to partition the device manually
        If he answers yes, the installer opens cgdisk /dev/{device}
        """
        self.current_w = Confirm('Do you want to open cgdisk to configure '
                                 'the partitions manually?')
        self.current_w.main_loop()
        loop = self.current_w.has_answer
        while loop:
            self.current_w = Terminal(['cgdisk', ('/dev/{0}'
                                                  .format(self.device))])
            self.current_w.main_loop()

            choices = ['Go back', 'Continue']
            self.current_w = Menu(choices, title='Are you okay with the '
                                                 'current partitions?')
            self.current_w.main_loop()
            loop = True if 'back' in self.current_w.response else False

    def _get_partition_list(self):
        """Queries the partitions on self.device and returns them as a list"""
        cmd = 'lsblk /dev/{0} -o name -n | grep -oE [0-9]+'.format(self.device)
        proc = subprocess.Popen(['bash', '-c', cmd],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        partitions = ['/dev/{0}{1}'.format(self.device, number)
                      for number in (proc.communicate()[0].decode('utf-8')
                                     .split('\n'))
                      if number != '']
        for i in range(0, len(partitions)):
            proc = subprocess.Popen(['lsblk',
                                     partitions[i],
                                     '-n',
                                     '-o',
                                     'size'],
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
            size = proc.communicate()[0].decode('utf-8').replace('\n', '')
            partitions[i] = '{0}         {1}'.format(partitions[i], size)
        return partitions

    def _fill_template_disk_info(self):
        """Handler to fill template when the user is done  mount points
        * Size does not matters because ister partitioning won't be activated
        """
        # Cleans the previous values
        self.installation_d['PartitionLayout'] = list()
        self.installation_d['FilesystemTypes'] = list()
        self.installation_d['PartitionMountPoints'] = list()

        _pl = list()
        fst = list()
        pmp = list()

        _ister_types = {'/boot': 'EFI'}
        _linux_types = {'/boot': 'vfat'}
        for key in self.mount_points:
            part = self.mount_points[key]['part']
            _format = self.mount_points[key]['format']
            index = 0
            for char in part:
                if char.isnumeric():
                    break
                index += 1
            part_num = part[index:]
            _type = _ister_types[key] if key in _ister_types else 'linux'
            _pl.append({'disk': self.device,
                        'partition': part_num,
                        'size': '1M',
                        'type': _type})
            _type = _linux_types[key] if key in _linux_types else 'ext4'
            fst.append({'disk': self.device,
                        'partition': part_num,
                        'type': _type})
            if key != '/' and not _format:
                fst[-1]['disable_format'] = True
            pmp.append({'disk': self.device,
                        'partition': part_num,
                        'mount': key})

        self.installation_d['PartitionLayout'].extend(_pl)
        self.installation_d['FilesystemTypes'].extend(fst)
        self.installation_d['PartitionMountPoints'].extend(pmp)

    def _set_partition_mount_point(self, partitions):
        """UI to set the mount point and if the partition needs format"""
        str_fmt = '{0}          {1}          {2}          {3}'
        choice = self.current_w.response
        index = partitions.index(choice)
        splitted = [item for item in choice.split() if item != '']
        part, size = splitted[0], splitted[1]
        m_point = splitted[2] if len(splitted) == 3 else ''
        questions = [{'text': 'Enter the mount point for "{0}"\n'
                              .format(part),
                      'key': 'm_point'},
                     {'text': 'Format',
                      'key': 'format',
                      'type': urwid.CheckBox}]
        self.current_w = Edit(questions,
                              title=('Configuring mount point for "{0}"'
                                     .format(part)))
        self.current_w.main_loop()
        if not self.current_w.has_answer:
            return
        answer = self.current_w.answers['m_point']
        _format = self.current_w.answers['format']
        # If empty it means the user wants to unset the mount point
        if answer == '':
            partitions[index] = str_fmt.format(part, size, answer, '')
            if m_point in self.mount_points:
                del self.mount_points[m_point]
            return
        # Checks if another partitions has the same mount point,
        # if yes it erases
        for ite, item in enumerate(partitions[:]):
            splitted = item.split()
            if len(splitted) == 3 and splitted[2] == answer:
                partitions[ite] = str_fmt.format(splitted[0],
                                                 splitted[1],
                                                 '',
                                                 '')
        self.mount_points[answer] = {'part': part, 'format': _format}
        msg_fmt = 'Format' if _format or answer == '/' else ''
        partitions[index] = str_fmt.format(part, size, answer, msg_fmt)

    def _set_mount_points(self):
        """UI with the available partitions
        When a user selects a partition the installer will prompt for its
        mount point
        """
        partitions = self._get_partition_list()
        partitions.append('Done')

        while True:
            self.current_w = Menu(partitions, title='Configuring mount points')
            self.current_w.main_loop()

            if self.current_w.response == 'Done':
                self._fill_template_disk_info()
                exc = ister_wrapper('validate_disk_template',
                                    self.installation_d)
                self.logger.debug(exc)
                if exc is None:
                    break
                else:
                    # Displays a warning message obtained from ister validation
                    message = exc
                    self.current_w = Confirm(message,
                                             title='Error',
                                             only_ok=True)
                    self.current_w.main_loop()
                    continue
            self._set_partition_mount_point(partitions)

    def _configure_installation(self):
        """Scheduler that calls the handlers to conf the installation dest"""
        self.current_w = Confirm('Do you want to handle the partitions '
                                 'and mount points manually? (If not the '
                                 'device will be repatitioned and all '
                                 'existing data lost)')
        self.current_w.main_loop()
        if not self.current_w.has_answer:
            self.logger.debug(self.installation_d)
            return True
        self._select_device()
        self._manage_partitions()
        self._set_mount_points()
        self.installation_d['DisabledNewPartitions'] = True
        return True

    def _configure_hostname(self):
        """UI to fill the hostname on the template"""
        questions = [{'text': 'Enter the hostname:\n', 'key': 'hostname'}]
        while True:
            self.current_w = Edit(questions, title='Configuring hostname')
            self.current_w.main_loop()

            if self.current_w.has_answer:
                self.installation_d['Hostname'] = \
                    self.current_w.answers.get('hostname', '')
                error = ister_wrapper('validate_hostname_template',
                                      self.installation_d['Hostname'])
                if error is None:
                    return True
                self.current_w = Confirm(error, only_ok=True)
                self.current_w.main_loop()
            else:
                return False

    def _configure_username(self):
        """UI to add a user to the template

        First it asks if the user wants to configure a new user.
        """
        self.current_w = Confirm('Do you want to configure a new user?')
        self.current_w.main_loop()
        if not self.current_w.has_answer:
            return True
        questions = [
            {'text': 'Enter your first name:\n',
             'key': 'first_name',
             'map_output': 'username',
             'map_ln': 1},
            {'text': 'Enter your last name:\n',
             'key': 'last_name',
             'map_output': 'username',
             'map_ln': 8},
            {'text': 'Enter the username:\n',
             'key': 'username'},
            {'text': 'Enter the password:\n',
             'key': 'password',
             'mask': '*'}
            ]
        self.current_w = Edit(questions, title='Configuring user')
        self.current_w.main_loop()
        if not self.current_w.has_answer \
            and 'username' in self.current_w.answers \
                and 'password' in self.current_w.answers:
            self.logger.error('A user configuration is needed')
            self._exit(-1)
        self.logger.debug(self.current_w.answers)
        self.installation_d['Users'] = list()
        user = dict()
        user['username'] = self.current_w.answers.get('username', '')
        user['password'] = crypt.crypt(self.current_w.answers
                                       .get('password', ''), 'aa')
        self.current_w = Confirm('Do you want to add the user to the sudoers '
                                 'file?')
        self.current_w.main_loop()
        user['sudo'] = self.current_w.has_answer
        self.logger.debug(user)
        self.installation_d['Users'].append(user)
        return True

    def _bundle_selector(self):
        """UI to let the user select the bundles to fill the template"""
        bundles = ['os-utils -> A core set of OS utilities',
                   'editors -> Popular text editors (terminal-based)',
                   'os-clr-on-clr -> Fills out dev tools for os development',
                   'devtools-basic -> gcc and minimal R, go, hpc, perl, '
                   'python, ruby',
                   'sysadmin -> Tools sys-admins commonly use',
                   'net-utils -> Core network config and debug',
                   'network-proxy-client -> Auto proxy detection for aware '
                   'tools like swupd']
        required_bundles = \
            ['os-core -> Minimal packages to have clear fully functional',
             'kernel-native -> Required to run clear on baremetal',
             'os-core-update -> Required to update the system',
             'telemetrics -> Quality feedback for the OS']
        selection = None
        backup = None
        while True:
            self.current_w = (Menu(bundles,
                                   title='Which bundles do you want to '
                                         'install?',
                                   checkbox=True,
                                   required_choices=required_bundles)
                              if backup is None else backup)
            self.current_w.main_loop()
            backup = self.current_w
            selection = self.current_w.response
            del self.current_w
            message = ('Do you want to continue the installation with the '
                       'bundles listed below?\n\n- {0}'
                       .format('\n- '.join(selection)))
            self.current_w = Confirm(message)
            self.current_w.main_loop()
            if self.current_w.has_answer:
                break
            del self.current_w
        selected = list()
        for item in selection:
            selected.append(item.split('->')[0].strip())
        self.logger.info(selected)
        self.installation_d['Bundles'] = selected
        return True


def handle_options():
    """Argument parser for the ui"""
    parser = argparse.ArgumentParser()
    parser.add_argument("-u", "--url", action="store", default=None,
                        help="URL to use for looking for update content")
    parser.add_argument("-f", "--format", action="store", default=None,
                        help="format to use for looking for update content")
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
