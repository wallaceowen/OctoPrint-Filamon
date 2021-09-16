# coding=utf-8
from __future__ import absolute_import

### (Don't forget to remove me)
# This is a basic skeleton for your plugin's __init__.py. You probably want to adjust the class name of your plugin
# as well as the plugin mixins it's subclassing from. This is really just a basic skeleton to get you started,
# defining your plugin as a template plugin, settings and asset plugin. Feel free to add or remove mixins
# as necessary.
#
# Take a look at the documentation on what other plugin mixins are available.

import time
import json
import threading

import octoprint.plugin

from . import filamon_connection as fc

TEST = True

class FilamonPlugin(octoprint.plugin.SettingsPlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.StartupPlugin,
    octoprint.plugin.ProgressPlugin):

    def on_startup(self, host, port):
        self._logger.info("Filament Monitor at startup.")

    def exchange(self, mt):
        # Send request
        bm = self.filamon.compose(mt)
        self._logger.info(f"Sending {bm}")
        self.filamon.send_msg(bm)

        for tries in range(fc.FILAMON_RETRIES):
            _type = None
            try:
                _type, body = self.filamon.recv_msg()
            except fc.NoData:
                continue
            except (fc.ShortMsg, fc.BadMsgType, fc.BadSize, fc.BadCRC) as err:
                self._logger.info("Caught error %s", err)
                continue
            except fc.NoConnection:
                logger.info('SERVER: lost connection')
                raise
            else:
                return (_type, body)

        raise fc.RetriesExhausted()

    # Fetch the latest status from Filamon
    def get_status(self):
        try:
            reply = self.exchange(fc.MT_STATUS)
        except fc.RetriesExhausted:
            self._logger.info("Filamon not talking to us")
        except fc.NoConnection:
            self._logger.info("Filamon not plugged in")
        else:
            _type, body = reply
            if _type == fc.MT_STATUS:
                json_msg = body.decode('utf-8')
                json_data = json.loads(json_msg)
                return json_data
            else:
                self._logger.debug("Received message type %s", _type)

    def send_status(self, status):
        self._plugin_manager.send_plugin_message("FilamentMonitor", status)

    # Connect to and reset the device on after startup

    def floop(self):
        status = self.get_status()
        self._logger.info(f"floop got status {status}")
        self.send_status(status)
        self.timer = threading.Timer(1.0, self.floop)
        self.timer.start()

    def on_after_startup(self):
        self._logger.info("Filament Monitor on_after_startup.  Config: %s, %s",
                self._settings.get(["port"]), self._settings.get(["baudrate"]))
        _, exclude, _, _ = self._printer.get_current_connection()
        preferred = self._settings.get(["port"])
        baudrate = self._settings.get(["baudrate"])
        self.filamon = fc.FilamonConnection(preferred, exclude, baudrate)
        self.filamon.connect()
        if self.filamon.connected():
            self._logger.info("Filament Monitor connected.")
            self.filamon.perform_reset()

            # just for testing (so we don't have to wait for a print to get to 1%!)
            if TEST:
                self.timer = threading.Timer(1.0, self.floop)
                self.timer.start()

    def on_print_progress(self):
        if self.filamon.connected():
            self.send_status()


    ##~~ SettingsPlugin mixin

    def get_settings_defaults(self):
        return {
            # put your plugin's default settings here
            'port': '/dev/ttyUSB0',
            'baudrate': 115200
        }

    def get_template_vars(self):
        return dict(port=self._settings.get(["port", "baudrate"]))

    ##~~ AssetPlugin mixin

    def get_assets(self):
        # Define your plugin's asset files to automatically include in the
        # core UI here.
        return {
            "js": ["js/filamon.js"],
            "css": ["css/filamon.css"],
            "less": ["less/filamon.less"]
        }

    ##~~ Softwareupdate hook

    def get_update_information(self):
        # Define the configuration for your plugin to use with the Software Update
        # Plugin here. See https://docs.octoprint.org/en/master/bundledplugins/softwareupdate.html
        # for details.
        return {
            "filamon": {
                "displayName": "Filamon Plugin",
                "displayVersion": self._plugin_version,

                # version check: github repository
                "type": "github_release",
                "user": "wallaceowen",
                "repo": "OctoPrint-Filamon",
                "current": self._plugin_version,

                # update method: pip
                "pip": "https://github.com/wallaceowen/OctoPrint-Filamon/archive/{target_version}.zip",
            }
        }


# If you want your plugin to be registered within OctoPrint under a different name than what you defined in setup.py
# ("OctoPrint-PluginSkeleton"), you may define that here. Same goes for the other metadata derived from setup.py that
# can be overwritten via __plugin_xyz__ control properties. See the documentation for that.
__plugin_name__ = "Filament Monitor"

# Starting with OctoPrint 1.4.0 OctoPrint will also support to run under Python 3 in addition to the deprecated
# Python 2. New plugins should make sure to run under both versions for now. Uncomment one of the following
# compatibility flags according to what Python versions your plugin supports!
#__plugin_pythoncompat__ = ">=2.7,<3" # only python 2
__plugin_pythoncompat__ = ">=3,<4" # only python 3
#__plugin_pythoncompat__ = ">=2.7,<4" # python 2 and 3

def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = FilamonPlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
    }
