# OctoPrint-Filamon

This plugin, when finished, weill connect to a filament monitor* and send it's information to OctoFarm using self._plugin_manager.send_plugin_message("FilamentMonitor", json_msg)

json_msg is a dict that will look like: {"printername": "bender_prime", "spool_id": 1423659708, "temp": 38.0, "humidity": .48, "weight": 788}
where:
   spool_id is an RFID tag attached to the spool by the receiving department
   temp is the temp of the filament in the spool container
   humidity is the humidity of the filament in the spool container
   weight is the weight of the spool in the spool container (including the spool).

The empty spool weight is expected to be stored in a spools table or (more factored) a spool_type table with a spool_type remote key in the spools table).  This is subtracted from the current weight to yield filament weight remaining.

* The filament monitor is a small widget with temp, humidity, weight sensors and an RFID tag reader, using an ESP32, BME280, HX711 attached to a 5KG load cell.  It also has a 2.8-inch TFT with a resistive touch-screen and SD-card, and some room for expansion (extra pins brought out to headers with power and ground).  It's code (currently called FilaScale) is another repo of mine that's being actively developed.


## Setup

Install via the bundled [Plugin Manager](https://docs.octoprint.org/en/master/bundledplugins/pluginmanager.html)
or manually using this URL:

    https://github.com/wallaceowen/OctoPrint-Filamon/archive/master.zip

iI'm still getting familiar with how to install plugins.


## Configuration

Making use of the Settings mixin to hold the port and baudrate to the device.

## Other projects doing similar things:

1: FilaWeigher: https://automatedhome.party/2019/12/14/the-filaweigher-a-standalone-wifi-web-based-weight-sensor-for-3d-printer-filament-for-less-than-7/ and OctoPrint Filament Scale
Uses a WeMos D1 Mini (an ESP8266) with an HX711 bridge exciter/amplifier and a BME280, that reports weight over MQTT
Last updated two years ago

2: OctoPrint Filament Scale: https://tutorials-raspberrypi.com/digital-raspberry-pi-scale-weight-sensor-hx711/ and https://github.com/dieki-n/Octoprint-Filament-Scale
This project connects the load cell amplifier directly to the pi running octoprint.

Last updated two years ago


## Why a third path:
I needed something that provided more robust communications directly to a PI than 3.3v signalling to the HX711 would provide; And not to use a wireless protocol because I want to be able to support a large farm and adding dozens of wireless nodes to an industrial environment doesn't scale.  Since USB offers high noise immunity with it's differential signalling, and a FilaScale monitoring the spool will be in close proximity to the controlling OctoPi, a direct connection to it seemed the best approach.
