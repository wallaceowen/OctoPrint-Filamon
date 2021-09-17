
import sys


from octoprint_filamon.fake_octo import FakeOcto

port = "/dev/ttyUSB1"
if len(sys.argv) > 1:
    port = sys.argv[1]

fake = FakeOcto(port)
fake.start()

while True:
    ans = input("press q<enter> to quit")
    if ans == 'q':
        break

fake.stop()

