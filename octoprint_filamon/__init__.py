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

from .modules import filamon_connection as fc
from .modules.thresholds import DEFAULT_THRESHOLDS

TEST = True
POLL_INTERVAL = 5.0
VERBOSE = True
SEND_CONFIG_TO_FILAMON = False

class FilamonPlugin(octoprint.plugin.SettingsPlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.StartupPlugin,
    octoprint.plugin.ProgressPlugin):

    def on_startup(self, host, port):
        self._logger.debug("Filament Monitor at startup.")

    # Tell the device to send us status.
    # Either returns a tuple (msg_type, body) or raises RetriesExhausted or NoConnection
    def exchange(self, mt, body=''):
        self.filamon.send_body(mt, body)

        # Try to read that status
        for tries in range(fc.FILAMON_RETRIES):
            _type = None
            try:
                _type, body = self.filamon.recv_msg()
            except fc.NoData:
                continue
            except (fc.ShortMsg, fc.BadMsgType, fc.BadSize, fc.BadCRC) as err:
                self._logger.info("Caught error %s sending query to filascale", err)
            except fc.NoConnection:
                self._logger.info('SERVER: lost connection')
                raise
            else:
                return (_type, body)

        raise fc.RetriesExhausted()

    # Fetch the latest status from FilaScale.  Raises ValueError if no status available.
    def request_status(self):
        try:
            reply = self.exchange(fc.MT_STATUS)
        except fc.RetriesExhausted:
            self._logger.debug("FilaMon plugin: out of retries")
            self.filamon.perform_reset()
            raise ValueError
        except fc.NoConnection:
            raise ValueError
        else:
            _type, body = reply
            if _type == fc.MT_STATUS:
                json_msg = body.decode('utf-8')
                try:
                    json_data = json.loads(json_msg)
                except json.JSONDecodeError as err:
                    self._logger.exception("FilaScale got bad json \"%s\"", json_msg)
                    raise ValueError()
                else:
                    return json_data
            else:
                self._logger.info("Requested status but received type %s", _type)

    if SEND_CONFIG_TO_FILAMON:
        def send_configuration(self):
            thresholds = self._settings.get(["thresholds"])
            thresh_str = json.dumps(thresholds)
            self._logger.info("send_config: thresholds = %s", thresholds)
            if self.filamon.connected():
                try:
                    reply = self.exchange(fc.MT_CONFIG, thresh_str)
                except fc.RetriesExhausted:
                    self._logger.debug("FilaMon plugin: out of retries")
                    raise ValueError
                except fc.NoConnection:
                    pass
                else:
                    _type, body = reply
                    if _type == fc.MT_CONFIG:
                        json_msg = body.decode('utf-8')
                        try:
                            json_data = json.loads(json_msg)
                        except json.JSONDecodeError as err:
                            self._logger.exception("FilaScale got bad json \"%s\"", json_msg)
                            raise ValueError()
                        else:
                            self._logger.info("FilaScale got config reply \"%s\"", json_data)
                    else:
                        self._logger.info("Requested config but received type %s", _type)

            thresholds = self._settings.get(["thresholds"])

    # STATUS_FMT = "{\"spool_id\": %llu, \"temp\": %3.3f, \"humidity\": %3.3f, \"weight\": %3.3f}"
    def check_thresholds(self, status):
        self._logger.info("check_thresholds %s", status)

        def check_limit(which, limits, value):
            self._logger.info("checking %s limits %s against value %f", which, limits, value)
            # if value <= limits["min"] || value >= limits["max"]:
                # pass

        thresholds = self._settings.get(["thresholds"])
        filament_type = self._settings.get(["filament_type"])
        limits = thresholds[filament_type]
        ents = ( ("Humidity", "humidity"), ("DryingTemp", "temp"))
        for ent in ents:
            check_limit(ent[0], limits[ent[0]], status[ent[1]])

    # Keep up-to-date on the spool status, saving the latest in self.status
    def filascale_poll(self):
        if VERBOSE:
            self._logger.info("FilaScale polling")
        # Try to connect if not connected
        if not self.filamon.connected():
            if VERBOSE:
                self._logger.info("FilaScale connecting")
            self.filamon.connect()

        if self.filamon.connected():
            try:
                self.status = self.request_status()
            except ValueError:
                pass
            else:
                if VERBOSE:
                    self._logger.info(f"FilaScale status: {self.status}")
                self.check_thresholds(self.status)

        return True

    # Send status to octofarm
    def send_status(self):
        if not self.status is None:
            self._plugin_manager.send_plugin_message("FilamentMonitor", self.status)

    def connect_cb(self, port):
        if VERBOSE:
            self._logger.info("Filament Monitor connected on port %s", port)

    def on_after_startup(self):
        self.status = None
        if VERBOSE:
            self._logger.info("Filament Monitor config: %s, %s",
                    self._settings.get(["port"]), self._settings.get(["baudrate"]))
        _, exclude, _, _ = self._printer.get_current_connection()
        preferred = self._settings.get(["port"])
        baudrate = self._settings.get(["baudrate"])
        # Connect to the device
        self.filamon = fc.FilamonConnection(
                self._logger,
                preferred,
                exclude,
                baudrate,
                self.connect_cb)
        # self.filamon.set_connected_cb(self.connect_cb)
        self.filamon.connect()
        if SEND_CONFIG_TO_FILAMON:
            self.send_configuration()

        # whether we connected or not, start running filascale_poll every POLL_INTERVAL seconds
        self.timer = octoprint.util.RepeatedTimer(POLL_INTERVAL, self.filascale_poll)
        self.timer.start()

    def on_print_progress(self):
        if self.filamon.connected():
            self.send_status()

    ##~~ SettingsPlugin mixin
    def get_settings_defaults(self):
        return {
            'port': '/dev/ttyUSB0',
            'baudrate': 115200,
            'thresholds': DEFAULT_THRESHOLDS,
            'filament_type': 'Nylon'
        }

    def get_template_vars(self):
        return dict(
                port=self._settings.get(["port"]),
                baudrate=self._settings.get(["baudrate"]),
                thresholds=self._settings.get(["thresholds"])
                )

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


__plugin_name__ = "Filament Monitor"

__plugin_pythoncompat__ = ">=3,<4" # only python 3

def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = FilamonPlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
    }
