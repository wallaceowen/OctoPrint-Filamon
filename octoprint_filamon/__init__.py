# coding=utf-8
from __future__ import absolute_import

### (Don't forget to remove me)
# This is a basic skeleton for your plugin's __init__.py. You probably want to adjust the class name of your plugin
# as well as the plugin mixins it's subclassing from. This is really just a basic skeleton to get you started,
# defining your plugin as a template plugin, settings and asset plugin. Feel free to add or remove mixins
# as necessary.
#
# Take a look at the documentation on what other plugin mixins are available.

import json

import octoprint.plugin

from . import filamon_connection as fc

class FilamonPlugin(octoprint.plugin.SettingsPlugin,
    octoprint.plugin.AssetPlugin,
    octoprint.plugin.TemplatePlugin,
    octoprint.plugin.StartupPlugin,
    octoprint.plugin.ProgressPlugin):

    def on_startup(self, host, port):
        self._logger.info("Filament Monitor at startup.")
        self.filamon = fc.FilamonConnection(self._printer, self._logger)

    def exchange(self, mt):
        # Send request
        bm = self.filamon.compose(mt)
        self.filamon.send_msg(bm)
        try:
            reply = self.filamon.recv_msg()
        except fc.NoData:
            self._logger.info("Filamon not talking to us")
        except (fc.NoConnection, fc.ShortMsg, fc.BadMsgType, fc.BadSize, fc.BadCRC) as err:
            self._logger.info("Caught exception %s", err)
        else:
            if reply[0] == MT_STATUS:
                json_bytes = reply[1]
                json_msg = json_bytes.decode('utf-8')
                json_data = json.loads(json_msg)
            self._plugin_manager.send_plugin_message("FilamentMonitor", json_msg)

    def on_after_startup(self):
        self._logger.info("Filament Monitor after startup")
        self.filamon.connect()
        if self.filamon.connected():
            # Reset the monitor on our startup so we know it doesn't give us anything we're not yet
            # prepared to handle
            self.filamon.send_reset()
            self.exchange(fc.MT_STATUS)

    def on_print_progress(self):
        if self.filamon.connected():
            self.exchange(fc.MT_STATUS)


    ##~~ SettingsPlugin mixin

    def get_settings_defaults(self):
        return {
            # put your plugin's default settings here
        }

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
__plugin_name__ = "Filamon Plugin"

# Starting with OctoPrint 1.4.0 OctoPrint will also support to run under Python 3 in addition to the deprecated
# Python 2. New plugins should make sure to run under both versions for now. Uncomment one of the following
# compatibility flags according to what Python versions your plugin supports!
#__plugin_pythoncompat__ = ">=2.7,<3" # only python 2
#__plugin_pythoncompat__ = ">=3,<4" # only python 3
__plugin_pythoncompat__ = ">=2.7,<4" # python 2 and 3

def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = FilamonPlugin()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
    }
