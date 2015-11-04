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
        # button unused for now
        del button
        raise urwid.ExitMainLoop()

    def on_yes_clicked(self, button):
        """Setup handler for yes button"""
        # button unused for now
        del button
        self.has_answer = True
        raise urwid.ExitMainLoop()


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


class Installation(object):
    """Main object for installer ui"""
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
        try:
            with open('/etc/ister.json') as file:
                json_string = file.read()
                self.logger.debug(json_string)
                self.installation_d = json.loads(json_string)
        except Exception as exep:
            self.logger.error(exep)
            self._exit(-1, 'Template file does not exist')

    def _exit(self, int_code, error_message=None):
        if error_message is None:
            error_message = 'An error ocurred during the installation, ' \
                            'please check the log file'
        self.current_w = Confirm(error_message,
                                 title='Error',
                                 only_ok=True)
        self.current_w.main_loop()
        exit(int_code)

    def run(self):
        """Starts up the installer ui"""
        self.current_w = Confirm('Do you want to execute the installation?')
        self.current_w.main_loop()
        if not self.current_w.has_answer:
            return

        self.automatic_install()

        self.current_w = Confirm('The installation has been completed '
                                 'successfully. The system will be rebooted.',
                                 title='Success',
                                 only_ok=True)
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
                self._exit(-1, 'Ister failed..., please check the log file')

        self.current_w.main_loop(handle)


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
