#!/usr/bin/env python

from __future__ import absolute_import

import struct

from crc import crc16

""" Exchange binary messages with another
Message format: HEADER BODY CRC
HEADER is SOH, len
BODY is <array of len bytes>
CRC is computed over the entire message
"""
SOH=0x55

def to_hex(msg):
    if type(msg) == str:
        return ' '.join(["%2.2X"%ord(c) for c in msg])
    else:
        return ' '.join(["%2.2X"%c for c in msg])


def build_msg(msg_type, body=""):
    header = struct.pack("@BBH", SOH, msg_type, len(body))
    # crc = crc16(body)
    crc = crc16(header+body.encode('utf-8'))
    if len(body):
        fmt = "@BBH{}sH".format(len(body))
        # print(f"build_msg - fmt = {fmt}")
        msg = struct.pack(fmt,
                SOH, msg_type, len(body), body.encode('utf-8'), crc)
    else:
        msg = struct.pack("@BBHH", SOH, msg_type, 0, crc)
    return msg

def decompose_msg(msg):
    # print(f"decompose_msg got msg {msg}")
    sig, msg_type, len_body = struct.unpack("@BBH",
            msg[:struct.calcsize("@BBH")])
    # print(f'sig: {sig} msg_type: {msg_type} len_body: {len_body}')
    # body = struct.unpack_from(f"{len_body}s".encode("utf-8"),
    header_size = struct.calcsize("@BBH")
    body = struct.unpack_from(f"{len_body}s",
            # msg, struct.calcsize("@BBH"))
            msg, header_size)[0]
    # mycrc = crc16(msg[:struct.calcsize("@BBH")]+body.decode('utf-8'))
    received_crc = struct.unpack_from("@H", msg,
            struct.calcsize("@BBH")
            +struct.calcsize(f"{len_body}s"))[0]
    # crc = crc16(body)
    crc = crc16(msg[:struct.calcsize("@BBH")]+body)
    # print('crc: {:02x} received_crc: {:02x}'.format(crc, received_crc))
    if crc == received_crc:
        return msg_type, body.decode('utf-8')

if __name__ == '__main__':
    import json

    data = {'a': 1, 'b': 2}
    jstr = json.dumps(data)
    # msg = build_msg(1, "This is a test")
    msg = build_msg(1, jstr)
    hexmsg = to_hex(msg)
    print(f"msg = {hexmsg}")
    msg_type, body = decompose_msg(msg)
    print(f'msg_type: {msg_type} body: {body}')
    d = json.loads(body)
    print(f'data: {d}')
    print('----------------------------------------------')
    msg = build_msg(1)
    hexmsg = to_hex(msg)
    print(f"msg = {hexmsg}")
    msg_type, body = decompose_msg(msg)
    print(f'msg_type: {msg_type} body: {body}')
