""" Fake Filamon
    simulate the messaging protocol exchanged between octoprint-filamon and filamon box
"""

from __future__ import absolute_import

import time
import json
import threading

from . import filamon_connection as fc

JSON_DATA = {"printername": "bender_prime", "spool_id": 1423659708, "temp": 38.0, "humidity": .48, "weight": 788}
JSON_STRING = json.dumps(JSON_DATA)

class FakeFilamon(threading.Thread):
    def __init__(self, port):
        self.port = port
        self.filacon = fc.FilamonConnection("/dev/ttyUSB1", "/dev/ttyUSB0", 115200)
        self.filacon.connect()
        threading.Thread.__init__(self, name="FakeFilamon")
        self.daemon = True
        self.terminate = False
        self.retries = 3

    def stop(self):
        self.terminate = True
        self.join()

    def handle_client_msg(self, _type, body):
        if _type == fc.MT_STATUS:
            request = body.decode('utf-8')
            reply = JSON_STRING
            msg = self.filacon.compose(fc.MT_STATUS, reply.encode('utf-8'))
            self.filacon.send_msg(msg)

    def exchange(self):
        for tries in range(self.retries):
            _type = None
            try:
                _type, body = self.filacon.recv_msg()
            except fc.NoData:
                print('.')
                time.sleep(0.01)
            except (fc.ShortMsg, fc.BadMsgType, fc.BadSize, fc.BadCRC) as err:
                print("fake filamon: %s trying to get msg", str(err))
                continue
            except fc.NoConnection:
                print('fake filamon: No connection')
                raise
            else:
                # print('fake filamon: received type: %d body: [%s]'%( _type, body))
                self.handle_client_msg(_type, body)
                return
        raise fc.RetriesExhausted()

    def run(self):

        while not self.terminate:
            # Try to read a message
            try:
                self.exchange()
            except (fc.RetriesExhausted, fc.NoConnection) as err:
                # print("exhausted")
                time.sleep(1)

if __name__ == '__main__':

    import sys
    port = "/dev/ttyUSB1"
    if len(sys.argv) > 1:
        port = sys.argv[1]

    fake = FakeFilamon(port)
    fake.start()

    while True:
        ans = input("press q<enter> to quit")
        if ans == 'q':
            break

    fake.stop()
