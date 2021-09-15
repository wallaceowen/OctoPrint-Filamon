""" Fake Filamon
    simulate the messaging protocol exchanged between octoprint-filamon and filamon box
"""

from . import filamon_connection as fc

class FakeFilamon(threading.Thread):
    def __init__(self, port):
        self.port = port
        self.filacon = fc.FilamonConnection
        threading.Thread.__init__(self, name="FakeFilamon")
        self.daemon = True
        self.terminate = False

    def stop(self):
        self.terminate = True
        self.join()

    def run(self):
        while not self.terminate:
            # Try to read a message

