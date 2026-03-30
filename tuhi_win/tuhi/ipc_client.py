#!/usr/bin/env python3
#
#  IPC client replacing D-Bus client for Windows.
#  Connects to the JSON-RPC TCP server from ipc_server.py.
#

import json
import logging
import socket
import threading
from tuhi.gobject_compat import Object, Property, timeout_add_seconds, TYPE_PYOBJECT

logger = logging.getLogger('tuhi.ipc_client')

IPC_PORT = 48150
IPC_HOST = '127.0.0.1'


class IPCError(Exception):
    def __init__(self, message):
        self.message = message


class IPCConnection:
    """Manages a TCP connection to the Tuhi IPC server."""

    def __init__(self):
        self._sock = None
        self._lock = threading.Lock()
        self._recv_buf = b''
        self._event_callbacks = []
        self._listener_thread = None
        self._connected = False
        self._request_id = 0
        self._pending_responses = {}  # id -> threading.Event, result
        self._response_lock = threading.Lock()

    def connect(self):
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.connect((IPC_HOST, IPC_PORT))
            self._connected = True
            self._listener_thread = threading.Thread(
                target=self._listen, daemon=True
            )
            self._listener_thread.start()
        except (ConnectionRefusedError, OSError) as e:
            raise IPCError(f'Cannot connect to Tuhi server: {e}')

    def _listen(self):
        """Background thread to receive events and responses."""
        buf = b''
        while self._connected:
            try:
                data = self._sock.recv(4096)
                if not data:
                    break
                buf += data
                while b'\n' in buf:
                    line, buf = buf.split(b'\n', 1)
                    try:
                        msg = json.loads(line.decode('utf-8'))
                        if 'event' in msg:
                            self._handle_event(msg)
                        elif 'id' in msg:
                            self._handle_response(msg)
                    except json.JSONDecodeError:
                        pass
            except (ConnectionResetError, OSError):
                break
        self._connected = False

    def _handle_event(self, msg):
        for cb in self._event_callbacks:
            try:
                cb(msg['event'], msg.get('data', {}))
            except Exception:
                logger.exception('Error in event callback')

    def _handle_response(self, msg):
        req_id = msg['id']
        with self._response_lock:
            if req_id in self._pending_responses:
                event, _ = self._pending_responses[req_id]
                self._pending_responses[req_id] = (event, msg)
                event.set()

    def on_event(self, callback):
        self._event_callbacks.append(callback)

    def call(self, method, args=None, timeout=10):
        """Send a request and wait for the response."""
        with self._lock:
            self._request_id += 1
            req_id = self._request_id

        request = {'method': method, 'id': req_id}
        if args is not None:
            request['args'] = args

        event = threading.Event()
        with self._response_lock:
            self._pending_responses[req_id] = (event, None)

        msg = json.dumps(request) + '\n'
        self._sock.sendall(msg.encode('utf-8'))

        if event.wait(timeout):
            with self._response_lock:
                _, response = self._pending_responses.pop(req_id)
            return response
        else:
            with self._response_lock:
                self._pending_responses.pop(req_id, None)
            raise IPCError(f'Timeout waiting for response to {method}')

    def close(self):
        self._connected = False
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass


class TuhiIPCClientDevice(Object):
    """
    Client-side device proxy, replacing TuhiDBusClientDevice.
    """
    __gsignals__ = {
        'button-press-required': (1, None, ()),
        'registered': (1, None, ()),
        'device-error': (1, None, (int,)),
    }

    def __init__(self, manager, device_props):
        Object.__init__(self)
        self.manager = manager
        self._conn = manager._conn
        self._device_id = device_props['device_id']
        self._name = device_props.get('name', 'UNKNOWN')
        self._address = device_props.get('address', '')
        self._dimensions = tuple(device_props.get('dimensions', [0, 0]))
        self._listening = device_props.get('listening', False)
        self._live = device_props.get('live', False)
        self._battery_percent = device_props.get('battery_percent', 0)
        self._battery_state = device_props.get('battery_state', 0)
        self._drawings_available = device_props.get('drawings_available', [])
        self._connected = True  # We're connected if we have the proxy
        self._sync_state = 0
        self.is_registering = False
        self.objpath = self._device_id

    @Property
    def address(self):
        return self._address

    @Property
    def name(self):
        return self._name

    @Property
    def dimensions(self):
        return self._dimensions

    @Property
    def listening(self):
        return self._listening

    @Property
    def drawings_available(self):
        return self._drawings_available

    @Property
    def battery_percent(self):
        return self._battery_percent

    @Property
    def battery_state(self):
        return self._battery_state

    @Property
    def connected(self):
        return self._connected

    @Property
    def sync_state(self):
        return self._sync_state

    @Property
    def live(self):
        return self._live

    def register(self):
        logger.debug(f'{self}: Register')
        self.is_registering = True
        self.manager.connect('notify::devices', self._on_mgr_devices_updated)
        self._conn.call('Device.Register', {'device_id': self._device_id})

    def start_listening(self):
        self._conn.call('Device.StartListening', {'device_id': self._device_id})

    def stop_listening(self):
        try:
            self._conn.call('Device.StopListening', {'device_id': self._device_id})
        except IPCError:
            pass

    def json(self, timestamp):
        resp = self._conn.call('Device.GetJSONData', {
            'device_id': self._device_id,
            'file_version': 1,
            'timestamp': timestamp
        })
        return resp.get('json', '')

    def start_live(self, fd=-1):
        self._conn.call('Device.StartLive', {'device_id': self._device_id})

    def stop_live(self):
        self._conn.call('Device.StopLive', {'device_id': self._device_id})

    def handle_event(self, event_type, data):
        """Handle an IPC event directed at this device."""
        if event_type == 'device_signal':
            signal = data.get('signal', '')
            args = data.get('args', [])
            if signal == 'ButtonPressRequired':
                self.emit('button-press-required')
            elif signal == 'ListeningStopped':
                err = args[0] if args else 0
                if err < 0:
                    logger.error(f'{self}: an error occurred: {err}')
                self.emit('device-error', err)
                self.notify('listening')
            elif signal == 'SyncState':
                self._sync_state = args[0] if args else 0
                self.notify('sync-state')
            elif signal == 'LiveStopped':
                self.notify('live')
        elif event_type == 'device_property_changed':
            prop = data.get('property', '')
            value = data.get('value')
            if prop == 'DrawingsAvailable':
                self._drawings_available = value
                self.notify('drawings-available')
            elif prop == 'Listening':
                self._listening = value
                self.notify('listening')
            elif prop == 'BatteryPercent':
                self._battery_percent = value
                self.notify('battery-percent')
            elif prop == 'BatteryState':
                self._battery_state = value
                self.notify('battery-state')
            elif prop == 'Live':
                self._live = value
                self.notify('live')
            elif prop == 'Dimensions':
                self._dimensions = tuple(value)
                self.notify('dimensions')

    def _on_mgr_devices_updated(self, manager, pspec):
        if not self.is_registering:
            return
        for d in manager.devices:
            if d.address == self.address:
                self.is_registering = False
                logger.info(f'{self}: Registration successful')
                self.emit('registered')

    def terminate(self):
        pass

    def __repr__(self):
        return f'{self._address} - {self._name}'


class TuhiIPCClientManager(Object):
    """
    Client-side manager proxy, replacing TuhiDBusClientManager.
    """
    __gsignals__ = {
        'unregistered-device': (1, None, (TYPE_PYOBJECT,)),
    }

    def __init__(self):
        Object.__init__(self)
        self._conn = IPCConnection()
        self._devices = {}
        self._unregistered_devices = {}
        self._online = False

        logger.info('Connecting to Tuhi IPC server...')
        try:
            self._conn.connect()
            self._conn.on_event(self._on_event)
            self._online = True
            self._init()
        except IPCError as e:
            logger.error(f'Failed to connect: {e.message}')
            self._reconnect_timer = timeout_add_seconds(2, self._try_reconnect)

    def _try_reconnect(self):
        try:
            self._conn.connect()
            self._conn.on_event(self._on_event)
            self._online = True
            self._init()
            return False  # Stop timer
        except IPCError:
            return True  # Keep retrying

    def _init(self):
        logger.info('Manager is online')
        resp = self._conn.call('GetAllDevices')
        for dev_props in resp.get('devices', []):
            if dev_props.get('registered', False):
                device = TuhiIPCClientDevice(self, dev_props)
                self._devices[device.address] = device

    @Property
    def online(self):
        return self._online

    @Property
    def devices(self):
        return list(self._devices.values())

    @Property
    def unregistered_devices(self):
        return list(self._unregistered_devices.values())

    @Property
    def searching(self):
        try:
            resp = self._conn.call('GetManagerProperties')
            return resp.get('searching', False)
        except IPCError:
            return False

    def start_search(self):
        self._unregistered_devices = {}
        self._conn.call('StartSearch')

    def stop_search(self):
        try:
            self._conn.call('StopSearch')
        except IPCError:
            pass
        self._unregistered_devices = {}

    def terminate(self):
        for dev in self._devices.values():
            dev.terminate()
        self._devices = {}
        self._unregistered_devices = {}
        self._conn.close()

    def _on_event(self, event_type, data):
        if event_type == 'unregistered_device':
            device_id = data.get('device_id', '')
            dev = TuhiIPCClientDevice(self, data)
            self._unregistered_devices[device_id] = dev
            self.emit('unregistered-device', dev)

        elif event_type == 'search_stopped':
            self.notify('searching')

        elif event_type == 'manager_property_changed':
            prop = data.get('property', '')
            if prop == 'Devices':
                # Refresh device list off the listener thread to avoid deadlock
                def _refresh():
                    try:
                        resp = self._conn.call('GetAllDevices')
                        for dev_props in resp.get('devices', []):
                            addr = dev_props.get('address', '')
                            if dev_props.get('registered') and addr not in self._devices:
                                device = TuhiIPCClientDevice(self, dev_props)
                                self._devices[device.address] = device
                        self.notify('devices')
                    except IPCError:
                        pass
                threading.Thread(target=_refresh, daemon=True).start()
            elif prop == 'Searching':
                self.notify('searching')

        elif event_type in ('device_signal', 'device_property_changed'):
            device_id = data.get('device_id', '')
            # Route to appropriate device
            for dev in list(self._devices.values()) + list(self._unregistered_devices.values()):
                if dev._device_id == device_id:
                    dev.handle_event(event_type, data)
                    break

    def __getitem__(self, btaddr):
        return self._devices[btaddr]
