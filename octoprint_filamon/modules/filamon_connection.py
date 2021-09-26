# -*- coding: utf-8 -*-

""" FilaMon connection class
    Manages the transport layer between the filament monitor device and the FilaMon plugin.
    This is a binary protocol
    1 byte SYNC
    1 byte message type
    2 bytes uint16 length little-endian
    length bytes of payload
    2 bytes CRC16

    The payload carried in these packets is a json dictionary with the state of the spool associated
    with the named printer:
    {"printername": "bender_prime", "spool_id": 1423659708, "temp": 38.0, "humidity": .48, "weight": 788}

    The spool_id is a 48-bit unsigned number as read from a 125KHz RFID tag.  This is in support of automated
    tracking of filament inventory.  Tag attached to spool at receiving department, read by filament monitor
    as the sppol rotates in the drybox.

    """

from __future__ import absolute_import, unicode_literals

import sys
import glob
import serial
import time
import struct
import errno

from .crc import crc16

# How long we hold down the reset line
FILAMON_RESET_DURATION = 2.0
FILAMON_PAUSE_AFTER_RESET = 4.0

FILAMON_TIMEOUT = 1.0
FILAMON_BAUDRATE = 115200
FILAMON_RETRIES = 3
FILAMON_SYNC_BYTE = 0x55
FILAMON_MAX_DATA_SIZE=512

NUM_VALID_MESSAGES = 5
# Message types, umbered from zero.  This decl forces NUM_VALID_MESSAGES to be maintained.
# Note: Only STATUS message implemented so far.  May be the only one needed.
MT_STATUS, MT_CONFIG, MT_START, MT_STOP, MT_THRESHOLD = range(NUM_VALID_MESSAGES)

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

# Simple hex dumper for byte arrays.  (I still haven't memorised the grammar of the new
# formatting layout options.)
def bytes_to_hex(msg):
    return ' '.join(["%2.2X"%b for b in msg])

class FilamonConnection(object):
    def __init__(self,
            logger,
            preferred=None,
            excluded=None,
            baudrate=FILAMON_BAUDRATE,
            connected_cb=None):
        self._logger = logger
        self.preferred = preferred
        self.excluded = excluded
        self.baudrate = baudrate
        self.connected_cb = connected_cb
        self.interface = None
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
        ports = []

        # Start with the preferred port.  Cull it from the glob first
        if self.preferred:
            if self.preferred in globbed_ports:
                globbed_ports.remove(self.preferred)
            ports.append(self.preferred)

        # Remove the excluded port (presumably the one attached to the printer)
        if self.excluded:
            if self.excluded in globbed_ports:
                globbed_ports.remove(self.excluded)

        # Add the globbed ports
        ports.extend(globbed_ports)

        interface_config = {
                "bytesize": serial.EIGHTBITS,
                "baudrate": self.baudrate,
                "parity": serial.PARITY_NONE,
                "stopbits": serial.STOPBITS_ONE,
                "xonxoff": 0}
        for port in ports:
            interface_config["port"] = port
            try:
                ser = serial.Serial(**interface_config)
            except serial.SerialException as err:
                if err.errno == 2:
                    continue
                else:
                    raise
            except Exception as err:
                raise
            else:
                self.port = port
                self.interface = ser
                self.interface.timeout = FILAMON_TIMEOUT
                if self.connected_cb:
                    self.connected_cb(port)
                return True

    # Send the given message to the device.
    # Raises NoConnection for all OS errors except EAGAIN and EINTR
    def send_msg(self, bmsg):

        if not self.connected():
            raise NoConnection()

        while True:
            try:
                self.interface.write(bmsg)
            except OSError as err:
                if err.errno in (errno.EAGAIN, errno.EINTR):
                    continue
                else:
                    raise NoConnection()
            except Exception as err:
                raise NoConnection()
            else:
                break

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
                        raise NoConnection()
                    else:
                        break
                    self.interface.read(iw)

    # Eat all bytes in socket
    def drain_input(self):
        if self.interface:
            iw = self.interface.inWaiting()
            while iw > 0:
                try:
                    residue = self.interface.read(iw)
                except serial.SerialException as err:
                    if err.errno in (errno.EAGAIN, errno.EINTR):
                        continue
                    else:
                        raise NoConnection()
                except Exception as err:
                    self._logger.info("FilaMon plugin Got %s draining input", err)
                    raise NoConnection()
                else:
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

        # Low-level 'read some bytes'
        # Can raise:
        #  NoData, NoConnection
        def _read_bytes(qty):

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
                    raise NoConnection()
                except Exception as err:
                    raise NoConnection()
                else:
                    bytes_read = len(values)
                    if bytes_read:
                        for value in values:
                            total.append(value)
                        to_read -= bytes_read
                    else:
                        # If no bytes read, break out
                        break

            if not len(total):
                raise NoData()
            bstr = bytes(total)
            try:
                s = bstr.decode('utf-8')
            except UnicodeDecodeError:
                s = '|'
            # sys.stdout.write(s)
            return bytes(total)

        # Try to read an N-byte CRC.  Pass it the length of the CRC
        # in bytes and the struct form to exctract the value from the
        # received bytes
        def read_crc():
            rcrc_bytes = _read_bytes(2)
            if len(rcrc_bytes) == 2:
                results = struct.unpack('<H', rcrc_bytes)
                return results[0]
            else:
                raise ShortMsg()

        def parse_header(header_bytes):

            # If we can't read the header raise ShortMsg
            if not len(header_bytes) == 3:
                raise ShortMsg()

            # Get type and length
            _type, length = struct.unpack('<BH', header_bytes)

            # Validate type
            if not _type in range(NUM_VALID_MESSAGES):
                raise BadMsgType()

            # Validate length
            if length > FILAMON_MAX_DATA_SIZE:
                raise BadSize(length)

            return _type, length


        # Read bytes until we get a sync byte or an exception is raised
        def read_sync():
            while True:
                bytes_in = _read_bytes(1)
                if bytes_in[0] == FILAMON_SYNC_BYTE:
                    break

        def read_body(desired):
            if desired:
                try:
                    body = _read_bytes(desired)
                except Exception as err:
                    raise
                else:
                    if not len(body) == desired:
                        raise ShortMsg()
                    else:
                        return body
            else:
                return b''

        def check_crc(header_bytes, body, rcrc):
            # Compose the message to get our expected CRC
            # msg = chr(FILAMON_SYNC_BYTE)+header_bytes+body
            msg = [int(FILAMON_SYNC_BYTE)]
            msg.extend(header_bytes)
            msg.extend(body)

            # compute the CRC of the received message
            ccrc = crc16(msg)

            # Compare it to the sent CRC
            return rcrc == ccrc



        # READ A MESSAGE and CHECK IT
        # ---------------------------
        if not self.interface:
            raise NoConnection()

        # Read bytes until we get a sync byte or we time out
        read_sync()

        # Read the header
        header_bytes = _read_bytes(3)

        # extract the message type and length from the header
        _type, length = parse_header(header_bytes)

        # Read the body
        body = read_body(length)

        # read the received CRC.
        rcrc = read_crc()

        # Check the integrity of the message
        if check_crc(header_bytes, body, rcrc):
            return _type, body
        else:
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
            time.sleep(FILAMON_PAUSE_AFTER_RESET)

    # Compose a message.  Pass the type and optional body.
    def compose(self, _type, body=b''):
        vals = struct.pack("<BBH", 0x55, _type, len(body))
        ccrc = crc16(vals+body)
        if len(body):
            msg = struct.pack("<BBH%dsH"%len(body),
                    0x55, _type, len(body), body, ccrc)
        else:
            msg = struct.pack("<BBHH", 0x55, _type, 0, ccrc)
        return msg

    def send_body(self, _type, body=''):
        msg = self.compose(_type, body.encode('utf-8'))
        self.send_msg(msg)
