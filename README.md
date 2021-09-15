# OctoPrint-Filamon

This plugin connects to a filament monitor* and sends it's information to OctoFarm using self._plugin_manager.send_plugin_message("FilamentMonitor", json_msg)

json_msg is a dict that look like: {"printername": "bender_prime", "spool_id": 1423659708, "temp": 38.0, "humidity": .48, "weight": 788}
where:
   spool_id is an RFID tag attached to the spool by the receiving department
   temp is the temp of the filament in the spool container
   humidity is the humidity of the filament in the spool container
   weight is the weight of the spool in the spool container (including the spool).

The empty spool weight is expected to be stored in a spools table or (more factored) a spool_type table with a spool_type remote key in the spools table).

* The filament monitor is a small widget with temp, humidity, weight sensors and an RFID tag reader, using an ESP32, BME280, HX711 attached to a 5KG load cell.  It also has a 2.8-inch TFT with a resistive touch-screen and SD-card, and some room for expansion (extra pins brought out to headers with power and ground).  It's code (currently called FilaScale) is another repo of mine that's being actively developed.


## Setup

Install via the bundled [Plugin Manager](https://docs.octoprint.org/en/master/bundledplugins/pluginmanager.html)
or manually using this URL:

    https://github.com/wallaceowen/OctoPrint-Filamon/archive/master.zip

Learning how to tell people how to install my plugin still (like what it expects for the serial port, etc)

## Configuration

Still learning how configuration works by looking at other's code
