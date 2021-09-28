""" Fake Filamon
    simulate the messaging protocol exchanged between octoprint-filamon and filamon box
"""

from __future__ import absolute_import

import time
import json
import threading

from .modules import filamon_connection as fc

STATUS_DATA = {"printername": "bender_prime", "spool_id": 1423659708, "temp": 38.0, "humidity": .48, "weight": 788}
STATUS_STRING = json.dumps(STATUS_DATA)

""" 
THRESHOLD_DATA = {
    "filament_type": "Nylon"
    "Humidity": { "min": 10, "max": 30 },
    "Weight": { "min": 200, "max": 5000 },
    "DryingTemp": { "min": 60, "max": 90 }
}
THRESHOLD_STRING = json.dumps(THRESHOLD_DATA)
"""

class FakeFilamon(threading.Thread):
    def __init__(self, port):
        self.port = port
        self.filamon = fc.FilamonConnection(None, "/dev/ttyUSB1", "/dev/ttyUSB0", 115200)
        try:
            self.filamon.connect()
        except fc.NoConnection:
            print("No connection!")
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
            reply = STATUS_STRING
            self.filamon.send_body(_type, reply)
        elif _type == fc.MT_THRESHOLD:
            request = body.decode('utf-8')
            print(f'(received body of threshold message: {request}')
            self.filamon.send_body(_type)

    def exchange(self):
        for tries in range(self.retries):
            try:
                _type, body = self.filamon.recv_msg()
            except fc.NoData:
                time.sleep(0.01)
            except (fc.ShortMsg, fc.BadMsgType, fc.BadSize, fc.BadCRC) as err:
                print(f"fake filamon: {err} trying to get msg", str(err))
                raise
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
