# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import glob
import serial
import time
import json

import octoprint.plugin
# from octoprint.server import printer
from octoprint.printer import PrinterInterface
import octoprint.settings

from . import binfmt

# How long we hold down the reset line
FILAMON_RESET_DURATION = 0.1
FILAMON_TIMEOUT = 1.0
FILAMON_BAUDRATE = 115200

def to_hex(msg):
    return ' '.join(["%2.2X"%ord(c) for c in msg])

class FilamonConnection():
    def __init__(self, printer, logger, connected_cb = None):
        self._printer = printer
        self._logger = logger
        self.connected_cb = connected_cb
        self.interface = None

    def set_connected_cb(self, connected_cb):
        self.connected_cb = connected_cb

    def connect(self):

        if self.interface:
            self.disconnect()

        ports = glob.glob("/dev/ttyUSB*")
        _, exclude, _, _ = self._printer.get_current_connection()
        if exclude:
            self._logger.info(f"excluding: {exclude}")
            ports.remove(exclude)
            ports.remove("/dev/ttyUSB1")
        self._logger.info(f"ports: {ports}")
        ports = ("/dev/ttyUSB0",)

        for port in ports:
            interface_config = {
                    "bytesize": serial.EIGHTBITS,
                    "baudrate": FILAMON_BAUDRATE,
                    "parity": serial.PARITY_NONE,
                    "stopbits": serial.STOPBITS_ONE,
                    "xonxoff": 0}
            interface_config["port"] = port
            try:
                ser = serial.Serial(**interface_config)
            except serial.SerialException as err:
                self._logger.info("Attempt to connect to serial port %s raised %s", port, err)
                raise
            else:
                self.port = port
                self.interface = ser
                self.interface.timeout = FILAMON_TIMEOUT
                if self.connected_cb:
                    self.connected_cb(port)
                self._logger.info("Found port %s serial instance %s", port, ser)
                return True

    def reset_monitor(self):
        if self.interface:
            # The reset line is attached to RTS.  Pull it low for 100mS
            self.interface.rts = 0
            time.sleep(FILAMON_RESET_DURATION)
            self.interface.rts = 1

    def set_timeout(self, timeout):
        if self.interface:
            self.interface.timeout = timeout

    def disconnect(self):
        if self.interface:
            self.interface.close()
            self.interface = None

    # Return True if filament monitor is connected
    def connected(self):
        return self.interface is not None

    # Eat all bytes in socket
    def drain_input(self):
        if self.interface:
            while True:
                iw = self.interface.inWaiting()
                if iw > 0:
                    residue = to_hex(self._read_bytes(iw))
                    self._logger.warning("Filament monitor is drooling (%s).  Flushing input.", residue)
                else:
                    break

    def send_data(self, msg_type, data=""):
        self._logger.info(f"sending {data} as binary")
        if self.interface:
            msg = binfmt.build_msg(msg_type, data)
            self.interface.write(msg)

    def recv_data(self):
        if self.interface:
            self._logger.info("trying to receive data")
            msg = self.interface.read()
            if len(msg):
                print(f"   -=-=-=-=- msg: {msg}")
                msg_type, body = binfmt.decompose_msg(msg)
                return (msg_type, body)
            else:
                self._logger.info("No message found")


