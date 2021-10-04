# coding=utf-8
from __future__ import absolute_import

import time
import json
import threading

import octoprint.plugin

from .modules import filamon_connection as fc
from .modules.thresholds import DEFAULT_THRESHOLDS

TEST = True
POLL_INTERVAL = 5.0
VERBOSE = True

class FilamonPlugin(octoprint.plugin.SettingsPlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.StartupPlugin,
    octoprint.plugin.ProgressPlugin):

    def on_startup(self, host, port):
        self._logger.debug("Filament Monitor at startup.")

    def check_thresholds(self, status):

        def check_limit(ent, status):
            parameter, key, limit, thresh = ent
            value = status[key]
            self._logger.info("checking %s limit %s %s value %f", parameter, limit, thresh, value)
            # Decorate the temperature plot with an orange glow?

        ents = (
                ("Humidity", "humidity", "MAX", self._settings.get(["maxhumidity"])),
                ("DryingTemp", "temp", "MAX", self._settings.get(["maxdrytemp"])),
                ("Weight", "weight", "MIN", self._settings.get(["minspoolwt"])),
                )
        for ent in ents:
            check_limit(ent, status)

    # Keep up-to-date on the spool status, saving the latest in self.status
    def filascale_poll(self):

        # Try to connect if not connected
        if not self.filamon.connected():
            if VERBOSE:
                self._logger.debug("trying to connect to a FilaScale")
            try:
                self.filamon.connect()
            except fc.NoConnection:
                pass

        if self.filamon.connected():
            try:
                self.status = self.filamon.request_status()
            except ValueError:
                pass
            else:
                if VERBOSE:
                    self._logger.info(f"FilaScale status: %s", self.status)
                self.check_thresholds(self.status)

        return True

    # Send status to octofarm
    def send_status(self):
        if not self.status is None:
            self._plugin_manager.send_plugin_message("FilamentMonitor", self.status)

    def connect_cb(self, port):
        if VERBOSE:
            self._logger.info("Filament Monitor connected on port %s", port)
        # Now we can send some message to the device if we like - we now believe it's there.

    def on_after_startup(self):
        self.status = None
        preferred = self._settings.get(["port"])
        baudrate = self._settings.get(["baudrate"])
        if VERBOSE:
            self._logger.info("Filament Monitor device config: port %s, baud %s",
                    preferred, baudrate)
        _, exclude, _, _ = self._printer.get_current_connection()

        # Connect to the device
        self.filamon = fc.FilamonConnection(
                self._logger,
                preferred,
                exclude,
                baudrate,
                self.connect_cb)
        try:
            self.filamon.connect()
        except fc.NoConnection:
            pass

        # whether we connected or not, start running filascale_poll every POLL_INTERVAL seconds
        # which will continue to try to connect and manage any discovered FilaScale device.
        self.timer = octoprint.util.RepeatedTimer(POLL_INTERVAL, self.filascale_poll)
        self.timer.start()

    def on_print_progress(self):
        if self.filamon.connected():
            self.send_status()

    ##~~ SettingsPlugin mixin
    def get_settings_defaults(self):
        thresholds = DEFAULT_THRESHOLDS
        return {
            'port': '/dev/ttyUSB0',
            'baudrate': 115200,
            'maxhumidity': thresholds["Humidity"]["max"],
            'maxdrytemp': thresholds["DryingTemp"]["max"],
            'minspoolwt': thresholds["Weight"]["min"]
        }

    def get_template_vars(self):
        # thresholds=self._settings.get(["thresholds"])
        return dict(
                port=self._settings.get(["port"]),
                baudrate=self._settings.get(["baudrate"]),
                maxhumidity=self._settings.get(["maxhumidity"]),
                maxdrytemp=self._settings.get(["maxdrytemp"]),
                minspoolwt=self._settings.get(["minspoolwt"]))

    def get_template_configs(self):
        return [
            dict(type="settings", custom_bindings=False)
        ]


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
