# -*- coding: utf-8 -*-
from __future__ import absolute_import, unicode_literals

import glob
import serial
import time
import struct

# import octoprint.plugin
# from octoprint.printer import PrinterInterface
# import octoprint.settings

from . import crc

# How long we hold down the reset line
FILAMON_RESET_DURATION = 0.1
FILAMON_TIMEOUT = 0.2
FILAMON_BAUDRATE = 115200

# Max size for payload
MAX_DATA_SIZE=512

# Number of message types
NUM_VALID_MESSAGES = 4

FILAMON_RETRIES = 3

# Message types, umbered from zero.  This decl forces NUM_VALID_MESSAGES to be maintained.
MT_STATUS, MT_CONFIG, MT_START, MT_STOP = range(NUM_VALID_MESSAGES)

class NoConnection(Exception):
    def __str__(self):
        return "No connection"

class NoData(Exception):
    def __str__(self):
        return "No Data"

class ShortMsg(Exception):
    def __str__(self):
        return "Short Message"

class BadSize(Exception):
    def __str__(self):
        return "Bad message size"

# Ran out of retries - we can't communicate with the chip resetter
class RetriesExhausted(Exception):
    def __str__(self):
        return "Retries exhausted"

class BadCRC(Exception):
    def __str__(self):
        return "Bad CRC"

# Message type field contains an invalid message ID
class BadMsgType(Exception):
    def __str__(self):
        return "Invalid Message type"

def bytes_to_hex(msg):
    return ' '.join(["%2.2X"%b for b in msg])

class FilamonConnection():
    def __init__(self, preferred=None, exclude=None, baudrate=FILAMON_BAUDRATE, connected_cb = None):
        self.preferred = preferred
        self.exclude = exclude
        self.baudrate = baudrate
        self.connected_cb = connected_cb
        self.interface = None
        self.debug = False
        self.show_bytes = False

    def set_connected_cb(self, connected_cb):
        self.connected_cb = connected_cb

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

    def connect(self):

        if self.interface:
            self.disconnect()

        globbed_ports = glob.glob("/dev/ttyUSB*")
        print(f"globbed_ports: {globbed_ports}")
        if self.exclude:
            print(f"excluding: {self.exclude}")
            globbed_ports.remove(self.exclude)

        ports = []
        print(f"self.preferred: {self.preferred}")
        print(f"ports: {ports}")
        if self.preferred:
            if self.preferred in globbed_ports:
                globbed_ports.remove(self.preferred)
            ports.append(self.preferred)
        ports.extend(globbed_ports)

        interface_config = {
                "bytesize": serial.EIGHTBITS,
                "baudrate": self.baudrate,
                "parity": serial.PARITY_NONE,
                "stopbits": serial.STOPBITS_ONE,
                "xonxoff": 0}
        print(f"ports: {ports}")
        for port in ports:
            interface_config["port"] = port
            try:
                ser = serial.Serial(**interface_config)
            except serial.SerialException as err:
                if err.errno == 2:
                    print(f"Attempt to connect to non-existent serial port {port} raised {err}")
                    continue
                else:
                    print(f"opening {port} raised {err}")
            except Exception as err:
                print(f"opening {port} raised {err}")
                raise
            else:
                self.port = port
                self.interface = ser
                self.interface.timeout = FILAMON_TIMEOUT
                if self.connected_cb:
                    self.connected_cb(port)
                print(f"Found port {port} serial instance {ser}")
                return True

    # Send the given message to the device.
    # Raises NoConnection for all OS errors except EAGAIN and EINTR
    def send_msg(self, msg):

        if not self.connected():
            raise NoConnection()

        while True:
            try:
                if self.show_bytes:
                    print('<USB SERIAL> Sending {} to remote'.format(bytes_to_hex(msg)))
                self.interface.write(msg)
            except OSError:
                if err.errno in (errno.EAGAIN, errno.EINTR):
                    print('send to remote device got EAGAIN')
                    continue
                else:
                    raise NoConnection()
            except Exception as err:
                print(f"in usb_comms.send_msg(): unhandled {err}")
                raise NoConnection()
            else:
                break

    # Low-level 'read some bytes'
    # Can raise:
    #  NoData, NoConnection
    def _read_bytes(self, qty):

        if not self.connected():
            raise NoConnection()

        to_read = qty
        total = []
        while to_read > 0:
            bytes_read = 0
            try:
                values = self.interface.read(to_read)
            except serial.SerialException as err:
                if err.errno in (errno.EAGAIN, errno.EINTR):
                    continue
                else:
                    raise NoConnection()
            except serial.serialutil.SerialException as err:
                print(f"in _read_bytes(): unhandled serial exception {err}")
                raise NoConnection()
            except Exception as err:
                print(f"in _read_bytes(): unhandled exception {err}")
                raise NoConnection()
            else:
                bytes_read = len(values)
                if bytes_read:
                    if self.show_bytes:
                        print('<USB SERIAL> Received {} from remote'.format(bytes_to_hex(values)))
                    total.extend(values)
                    to_read -= bytes_read
                else:
                    # If no btres read, break out
                    break
        if not bytes_read:
            raise NoData()
        return ''.join(total)

    # Eat all bytes in socket
    def drain_input(self):
        if self.interface:
            while True:
                iw = self.interface.inWaiting()
                if iw > 0:
                    try:
                        residue = self.interface.read(iw)
                    except serial.SerialException as err:
                        if err.errno in (errno.EAGAIN, errno.EINTR):
                            continue
                        else:
                            raise NoConnection()
                    except Exception as err:
                        print(f"in drain_input(): unhandled exception {err}")
                        raise NoConnection()
                    else:
                        print(f"monitor drooling {residue}")
                        break
                    self.interface.read(iw)

    # Receive a message from the serial port, in the expected form:
    # 1 bytes SYNC
    # 1 byte  MSG_TYPE
    # 2 bytes length, litte-endian.  0: no data.
    # length bytes of data
    # 2 bytes of CRC-16
    #
    # Returns a tuple: (_type, body) or None,
    # or raises whatever exception _read_bytes() raises, which is either NoData or NoConnection,
    # or raises ShortMsg, BadMsgType, BadSize or BadCRC
    #
    def recv_msg(self):

        # Try to read an N-byte CRC.  Pass it the length of the CRC
        # in bytes and the struct form to exctract the value from the
        # received bytes
        def read_crc():
            rcrc_bytes = self._read_bytes(2)
            if len(rcrc_bytes) == 2:
                results = struct.unpack('<H', rcrc_bytes)
                return results[0]
            else:
                raise ShortMsg()

        # If the interface isn't configured, raise an exception, which
        # will get it configured and call us again.
        if not self.interface:
            raise NoConnection()

        # Read bytes until we get a sync byte or an exception is raised
        while True:
            ch = self._read_bytes(1)
            if self.debug:
                print("read_msg() looking for sync got {}".format(bytes_to_hex(ch)))
            if not ord(ch) == SYNC_BYTE:
                continue
            else:
                break

        # Try to read the header
        header_bytes = self._read_bytes(3)

        # If we can't, raise ShortMsg
        if not len(header_bytes) == 3:
            raise ShortMsg()

        if self.debug:
            print("received 3 byte header {}".format(bytes_to_hex(header_bytes)))

        # Get type and length
        _type, length = struct.unpack('<BH', header_bytes)
        if self.debug:
            print(f"_type {type} length {length}")

        # Validate type
        if not _type in range(NUM_VALID_MESSAGES):
            raise BadMsgType()

        # Validate length
        if length > MAX_DATA_SIZE:
            print("Bad length field {} ({})".format(length, length))
            raise BadSize(length)

        # Try to read body if there is one
        body = b''
        if length:
            if self.debug:
                print(f"Trying to read {length} bytes body")
            body = self._read_bytes(length)
            if not len(body) == length:
                raise ShortMsg()

        # Compose the message to get our expected CRC
        # msg = chr(SYNC_BYTE)+header_bytes+body
        msg = chr(SYNC_BYTE)
        msg.extend(header_bytes)
        msg.extend(body)

        if self.debug:
            print("usb read_msg received {} byte msg (minus CRC): [{}]".format(
                len(msg), bytes_to_hex(msg)))

        # compute the CRC.
        ccrc = crc.crc16(msg)

        # read the received CRC.
        rcrc = read_crc()

        if rcrc == ccrc:
            return _type, body
        else:
            print(f"Error with crc: {rcrc} != {ccrc} msg = {msg}")
            raise BadCRC()

    def set_timeout(self, timeout):
        self.interface.timeout = timeout

    def get_timeout(self):
        return self.interface.timeout

    def perform_reset(self):
        if self.interface:
            # The reset line is attached to RTS.  Pull it low for 100mS
            self.interface.rts = 0
            time.sleep(FILAMON_RESET_DURATION)
            self.interface.rts = 1

    # Compose a message.  Pass the type and optional body.
    def compose(self, _type, body=b''):
        vals = struct.pack("<BBH", 0x55, _type, len(body))
        ccrc = crc.crc16(vals+body)
        if self.debug:
            print(f"compose: type = {type} vals = {bvals} body=[%s] ccrc=%4.4X",
                    _type, bytes_to_hex(vals), bytes_to_hex(body), ccrc)
        if len(body):
            msg = struct.pack("<BBH%dsH"%len(body),
                    0x55, _type, len(body), body, ccrc)
        else:
            msg = struct.pack("<BBHH", 0x55, _type, 0, ccrc)
        return msg
