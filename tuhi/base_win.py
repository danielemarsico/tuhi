#!/usr/bin/env python3
#
#  Windows-compatible Tuhi orchestrator.
#  Replaces base.py, using gobject_compat, bleak BLE, and IPC server
#  instead of GObject/GLib, BlueZ, and D-Bus.
#

import argparse
import enum
import logging
import sys
import time
import threading
from pathlib import Path

from tuhi.gobject_compat import Object, Property, timeout_add_seconds, source_remove, TYPE_PYOBJECT
from tuhi.ipc_server import TuhiIPCServer
from tuhi.ble_bleak import BleakDeviceManager
from tuhi.wacom_win import WacomDevice, DeviceMode
from tuhi.config_win import TuhiConfig, get_default_data_dir

DEFAULT_CONFIG_PATH = get_default_data_dir()

logger = logging.getLogger('tuhi')

WACOM_COMPANY_IDS = [0x4755, 0x4157, 0x424d]


class TuhiDevice(Object):
    '''
    Glue object to combine the backend BLE device with the frontend
    IPC server device.
    '''

    class BatteryState(enum.Enum):
        UNKNOWN = 0
        CHARGING = 1
        DISCHARGING = 2

    __gsignals__ = {
        'device-error': (1, None, (TYPE_PYOBJECT,)),
    }

    BATTERY_UPDATE_MIN_INTERVAL = 300

    def __init__(self, bluez_device, config, uuid=None, mode=DeviceMode.LISTEN):
        Object.__init__(self)
        self.config = config
        self._wacom_device = None
        assert uuid is not None or mode == DeviceMode.REGISTER
        self._mode = mode
        self._battery_state = TuhiDevice.BatteryState.UNKNOWN
        self._battery_percent = 0
        self._last_battery_update_time = 0
        self._battery_timer_source = None
        self._signals = {'connected': None, 'disconnected': None}
        self._bluez_device = bluez_device
        self._tuhi_dbus_device = None

    @Property
    def dimensions(self):
        if self._wacom_device is None:
            return 0, 0
        return self._wacom_device.dimensions

    @Property
    def mode(self):
        return self._mode

    @mode.setter
    def mode(self, mode):
        if self._mode != mode:
            self._mode = mode
            self.notify('registered')

    @Property
    def registered(self):
        return self.mode == DeviceMode.LISTEN

    @Property
    def name(self):
        return self._bluez_device.name

    @Property
    def address(self):
        return self._bluez_device.address

    @Property
    def bluez_device(self):
        return self._bluez_device

    @Property
    def dbus_device(self):
        return self._tuhi_dbus_device

    @dbus_device.setter
    def dbus_device(self, device):
        assert self._tuhi_dbus_device is None
        self._tuhi_dbus_device = device
        self._tuhi_dbus_device.connect('register-requested', self._on_register_requested)
        self._tuhi_dbus_device.connect('notify::listening', self._on_listening_updated)
        self._tuhi_dbus_device.connect('notify::live', self._on_live_updated)

        drawings = self.config.load_drawings(self.address)
        if drawings:
            logger.debug(f'{self.address}: loaded {len(drawings)} drawings from disk')
        for d in drawings:
            self._tuhi_dbus_device.add_drawing(d)

    @Property
    def listening(self):
        return self._tuhi_dbus_device.listening

    @Property
    def live(self):
        return self._tuhi_dbus_device.live

    @Property
    def battery_percent(self):
        return self._battery_percent

    @battery_percent.setter
    def battery_percent(self, value):
        self._battery_percent = value

    @Property
    def battery_state(self):
        return self._battery_state

    @battery_state.setter
    def battery_state(self, value):
        self._battery_state = value

    @Property
    def sync_state(self):
        return self._sync_state

    def _connect_device(self, mode):
        if self._signals['connected'] is None:
            self._signals['connected'] = self._bluez_device.connect(
                'connected', self._on_bluez_device_connected, mode)
        if self._signals['disconnected'] is None:
            self._signals['disconnected'] = self._bluez_device.connect(
                'disconnected', self._on_bluez_device_disconnected)
        self._bluez_device.connect_device()

    def register(self):
        self._connect_device(DeviceMode.REGISTER)

    def listen(self):
        self._connect_device(DeviceMode.LISTEN)

    def _on_bluez_device_connected(self, bluez_device, mode):
        logger.debug(f'{bluez_device.address}: connected for {mode}')
        if self._wacom_device is None:
            self._wacom_device = WacomDevice(bluez_device, self.config)
            self._wacom_device.connect('drawing', self._on_drawing_received)
            self._wacom_device.connect('done', self._on_fetching_finished, bluez_device)
            self._wacom_device.connect('button-press-required', self._on_button_press_required)
            self._wacom_device.connect('notify::uuid', self._on_uuid_updated, bluez_device)
            self._wacom_device.connect('battery-status', self._on_battery_status, bluez_device)
            self._wacom_device.connect('notify::sync-state', self._on_sync_state)
            self._wacom_device.connect('notify::dimensions', self._on_dimensions)

        if mode == DeviceMode.REGISTER:
            self._wacom_device.start_register()
        elif mode == DeviceMode.LIVE:
            self._wacom_device.start_live(self._tuhi_dbus_device.uhid_fd)
        else:
            self._wacom_device.start_listen()

        try:
            bluez_device.disconnect(self._signals['connected'])
            self._signals['connected'] = None
        except KeyError:
            pass

    def _on_dimensions(self, device, pspec):
        self.notify('dimensions')

    def _on_sync_state(self, device, pspec):
        self._sync_state = device.sync_state
        self.notify('sync-state')

    def _on_bluez_device_disconnected(self, bluez_device):
        logger.debug(f'{bluez_device.address}: disconnected')
        try:
            bluez_device.disconnect(self._signals['disconnected'])
            self._signals['disconnected'] = None
        except KeyError:
            pass

    def _on_register_requested(self, dbus_device):
        if self.mode == DeviceMode.LISTEN:
            return
        self.register()

    def _on_drawing_received(self, device, drawing):
        logger.debug('Drawing received')
        self._tuhi_dbus_device.add_drawing(drawing)
        self.config.store_drawing(self.address, drawing)

    def _on_fetching_finished(self, device, exception, bluez_device):
        if self.live:
            return
        bluez_device.disconnect_device()
        if exception is not None:
            logger.info(exception)
            self.emit('device-error', exception)

    def _on_button_press_required(self, device):
        self._tuhi_dbus_device.notify_button_press_required()

    def _on_uuid_updated(self, wacom_device, pspec, bluez_device):
        self.config.new_device(bluez_device.address, wacom_device.uuid, wacom_device.protocol)
        self.mode = DeviceMode.LISTEN

    def _on_listening_updated(self, dbus_device, pspec):
        self.notify('listening')

    def _on_live_updated(self, dbus_device, pspec):
        if self.live:
            self._connect_device(DeviceMode.LIVE)
        else:
            if self._wacom_device is not None:
                self._wacom_device.stop_live()

    def _on_battery_status(self, wacom_device, percent, is_charging, bluez_device):
        if is_charging:
            self.battery_state = TuhiDevice.BatteryState.CHARGING
        else:
            self.battery_state = TuhiDevice.BatteryState.DISCHARGING
        self.battery_percent = percent

        if self._battery_timer_source is not None:
            source_remove(self._battery_timer_source)
        self._battery_timer_source = timeout_add_seconds(
            self.BATTERY_UPDATE_MIN_INTERVAL, self._on_battery_timeout)
        self._last_battery_update_time = time.time()

    def _on_battery_timeout(self):
        if self._last_battery_update_time < time.time() - self.BATTERY_UPDATE_MIN_INTERVAL:
            self.battery_state = TuhiDevice.BatteryState.UNKNOWN
        self._battery_timer_source = None
        return False


class Tuhi(Object):
    '''
    Main entry point and glue object between BLE backend and IPC server.
    '''
    __gsignals__ = {
        'device-added': (1, None, (TYPE_PYOBJECT,)),
        'device-connected': (1, None, (TYPE_PYOBJECT,)),
        'terminate': (1, None, ()),
    }

    def __init__(self, config_dir=None):
        Object.__init__(self)
        self.server = TuhiIPCServer()
        self.server.connect('bus-name-acquired', self._on_tuhi_bus_name_acquired)
        self.server.connect('bus-name-lost', self._on_tuhi_bus_name_lost)
        self.server.connect('search-start-requested', self._on_start_search_requested)
        self.server.connect('search-stop-requested', self._on_stop_search_requested)
        self.bluez = BleakDeviceManager()
        self.bluez.connect('discovery-started', self._on_bluez_discovery_started)
        self.bluez.connect('discovery-stopped', self._on_bluez_discovery_stopped)

        self.config = TuhiConfig()
        self.devices = {}
        self._search_stop_handler = None

    def _on_tuhi_bus_name_acquired(self, dbus_server):
        self.bluez.connect_to_bluez()
        for dev in self.bluez.devices:
            self._add_device(self.bluez, dev)

        self.bluez.connect('device-added',
                           lambda mgr, dev: self._add_device(mgr, dev, True))
        self.bluez.connect('device-updated',
                           lambda mgr, dev: self._add_device(mgr, dev, True))

    def _on_tuhi_bus_name_lost(self, dbus_server):
        self.emit('terminate')

    def _on_start_search_requested(self, dbus_server, stop_handler):
        self._search_stop_handler = stop_handler
        self.bluez.start_discovery()

    def _on_stop_search_requested(self, dbus_server):
        self._search_stop_handler(0)
        self._search_stop_handler = None
        self.bluez.stop_discovery()

        unregistered = [addr for (addr, d) in self.devices.items() if not d.registered]
        for addr in unregistered:
            del self.devices[addr]

    def _on_bluez_discovery_started(self, manager):
        if not self._search_stop_handler:
            return

    def _on_bluez_discovery_stopped(self, manager):
        if self._search_stop_handler is not None:
            self._search_stop_handler(0)
        self._on_listening_updated(None, None)

    def _add_device(self, manager, bluez_device, from_live_update=False):
        if bluez_device.vendor_id is not None and bluez_device.vendor_id not in WACOM_COMPANY_IDS:
            return

        try:
            config = self.config.devices[bluez_device.address]
            uuid = config['uuid']
        except KeyError:
            if bluez_device.vendor_id is None:
                return
            uuid = None

        if from_live_update and len(bluez_device.manufacturer_data or []) == 4:
            mode = DeviceMode.REGISTER
        else:
            mode = DeviceMode.LISTEN
            if uuid is None:
                logger.info(f'{bluez_device.address}: device without config, must be registered first')
                return
            logger.debug(f'{bluez_device.address}: UUID {uuid} protocol: {config["Protocol"]}')

        if bluez_device.address not in self.devices:
            d = TuhiDevice(bluez_device, self.config, uuid, mode)
            d.dbus_device = self.server.create_device(d)
            d.connect('notify::listening', self._on_listening_updated)
            self.devices[bluez_device.address] = d

        d = self.devices[bluez_device.address]

        if mode == DeviceMode.REGISTER:
            d.mode = mode
            logger.debug(f'{bluez_device.address}: call Register() on device')
        elif d.listening:
            d.listen()

    def _on_listening_updated(self, tuhi_dbus_device, pspec):
        listen = self._search_stop_handler is not None
        for dev in self.devices.values():
            if dev.listening:
                listen = True
                break

        if listen:
            self.bluez.start_discovery()
        else:
            self.bluez.stop_discovery()


def setup_logging(config_dir):
    session_log_file = Path(config_dir, 'session-logs',
                            f'tuhi-{time.strftime("%y-%m-%d-%H-%M-%S")}.log')
    session_log_file.parent.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        fmt='%(asctime)s %(levelname)s: %(name)s: %(message)s',
        datefmt='%H:%M:%S')

    fh = logging.FileHandler(session_log_file)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(formatter)

    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    logger.addHandler(fh)
    logger.info(f'Session log: {session_log_file}')


def main(args=sys.argv):
    if sys.version_info < (3, 12):
        sys.exit('Python 3.12 or later required')

    desc = 'Daemon to extract pen stroke data from Wacom SmartPad devices (Windows)'
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument('-v', '--verbose',
                        help='Show debugging information',
                        action='store_true',
                        default=False)
    parser.add_argument('--config-dir',
                        help='Base directory for configuration',
                        type=str,
                        default=DEFAULT_CONFIG_PATH)
    parser.add_argument('--peek',
                        help='Download first drawing only but do not remove it from device',
                        action='store_true',
                        default=False)

    ns = parser.parse_args(args[1:])
    TuhiConfig.set_base_path(ns.config_dir)
    TuhiConfig().peek_at_drawing = ns.peek
    setup_logging(ns.config_dir)

    if ns.verbose:
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)

    try:
        tuhi = Tuhi(config_dir=ns.config_dir)
        logger.info('Tuhi Windows server running. Press Ctrl+C to exit.')
        logger.info(f'IPC server on 127.0.0.1:48150')

        # Keep the main thread alive (replaces GLib.MainLoop)
        stop_event = threading.Event()
        tuhi.connect('terminate', lambda t: stop_event.set())
        stop_event.wait()
    except KeyboardInterrupt:
        logger.info('Shutting down...')
