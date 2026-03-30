#!/usr/bin/env python3
#
#  IPC server replacing D-Bus for Windows.
#  Uses JSON-RPC over TCP on localhost:48150.
#
#  Exposes the same logical interface as dbusserver.py:
#    Manager: Devices, Searching, StartSearch, StopSearch
#    Device: Register, StartListening, StopListening, GetJSONData, etc.
#

import errno
import json
import logging
import socket
import threading
from tuhi.gobject_compat import Object, Property, TYPE_PYOBJECT
from .drawing_win import Drawing

logger = logging.getLogger('tuhi.ipc')

IPC_PORT = 48150
IPC_HOST = '127.0.0.1'


class TuhiIPCDevice(Object):
    """
    Represents a device exposed over the IPC interface.
    Replaces TuhiDBusDevice from dbusserver.py.
    """
    __gsignals__ = {
        'register-requested': (1, None, ()),
    }

    def __init__(self, device, server):
        Object.__init__(self)
        self._server = server
        self.device_id = device.address.replace(':', '_')
        self.bluez_device_objpath = device.bluez_device.address
        self._name = device.name
        self.width, self.height = device.dimensions
        self.drawings = {}
        self._registered = device.registered
        self._listening = False
        self._listening_client = None
        self._live = False
        self._uhid_fd = None
        self._live_client = None
        self._battery_percent = 0
        self._battery_state = device.battery_state
        self._sync_state = 0

        device.connect('notify::registered', self._on_device_registered)
        device.connect('notify::battery-percent', self._on_battery_percent)
        device.connect('notify::battery-state', self._on_battery_state)
        device.connect('device-error', self._on_device_error)
        device.connect('notify::sync-state', self._on_sync_state)
        device.connect('notify::dimensions', self._on_dimensions)

    @Property
    def name(self):
        return self._name

    @Property
    def listening(self):
        return self._listening

    @listening.setter
    def listening(self, value):
        if self._listening == value:
            return
        self._listening = value
        self._server.broadcast_event('device_property_changed', {
            'device_id': self.device_id,
            'property': 'Listening',
            'value': value
        })

    @Property
    def live(self):
        return self._live

    @live.setter
    def live(self, value):
        if self._live == value:
            return
        self._live = value
        self._server.broadcast_event('device_property_changed', {
            'device_id': self.device_id,
            'property': 'Live',
            'value': value
        })

    @Property
    def uhid_fd(self):
        return self._uhid_fd

    @Property
    def registered(self):
        return self._registered

    @registered.setter
    def registered(self, value):
        self._registered = value

    @Property
    def battery_percent(self):
        return self._battery_percent

    @battery_percent.setter
    def battery_percent(self, value):
        if self._battery_percent == value:
            return
        self._battery_percent = value
        self._server.broadcast_event('device_property_changed', {
            'device_id': self.device_id,
            'property': 'BatteryPercent',
            'value': value
        })

    @Property
    def battery_state(self):
        return self._battery_state

    @battery_state.setter
    def battery_state(self, value):
        if self._battery_state == value:
            return
        self._battery_state = value
        self._server.broadcast_event('device_property_changed', {
            'device_id': self.device_id,
            'property': 'BatteryState',
            'value': value.value if hasattr(value, 'value') else value
        })

    @Property
    def objpath(self):
        return self.device_id

    def remove(self):
        pass

    def _on_device_registered(self, device, pspec):
        if self.registered == device.registered:
            return
        self.registered = device.registered

    def _on_battery_percent(self, device, pspec):
        self.battery_percent = device.battery_percent

    def _on_battery_state(self, device, pspec):
        self.battery_state = device.battery_state

    def _on_device_error(self, device, exception):
        logger.info('An error occurred while syncing the device')
        if self.listening:
            self._stop_listening(-exception.errno)

    def _on_dimensions(self, device, pspec):
        self.width, self.height = device.dimensions
        self._server.broadcast_event('device_property_changed', {
            'device_id': self.device_id,
            'property': 'Dimensions',
            'value': [self.width, self.height]
        })

    def _on_sync_state(self, device, pspec):
        self._sync_state = device.sync_state
        self._server.broadcast_event('device_signal', {
            'device_id': self.device_id,
            'signal': 'SyncState',
            'args': [device.sync_state]
        })

    def handle_method(self, method, args):
        """Handle an IPC method call for this device."""
        if method == 'Register':
            self.emit('register-requested')
            return {'result': 0}
        elif method == 'StartListening':
            self._start_listening()
            return {'result': 'ok'}
        elif method == 'StopListening':
            self._stop_listening()
            return {'result': 'ok'}
        elif method == 'StartLive':
            return self._start_live()
        elif method == 'StopLive':
            self._stop_live()
            return {'result': 'ok'}
        elif method == 'GetJSONData':
            return {'json': self._json_data(args)}
        elif method == 'GetProperties':
            return self._get_properties()
        else:
            return {'error': f'Unknown method: {method}'}

    def _get_properties(self):
        return {
            'device_id': self.device_id,
            'name': self._name,
            'address': self.bluez_device_objpath,
            'dimensions': [self.width, self.height],
            'listening': self._listening,
            'live': self._live,
            'battery_percent': self._battery_percent,
            'battery_state': self._battery_state.value if hasattr(self._battery_state, 'value') else self._battery_state,
            'drawings_available': list(self.drawings.keys()),
            'registered': self._registered,
        }

    def _start_listening(self):
        if self.listening:
            logger.debug(f'{self._name} - already listening')
            return
        logger.debug(f'Listening started on {self._name}')
        self.listening = True
        self.notify('listening')

    def _stop_listening(self, err=0):
        if not self.listening:
            return
        logger.debug(f'Listening stopped on {self._name}')
        self.notify('listening')
        self._server.broadcast_event('device_signal', {
            'device_id': self.device_id,
            'signal': 'ListeningStopped',
            'args': [err]
        })
        self.listening = False
        self.notify('listening')

    def _start_live(self):
        if self.live:
            logger.debug(f'{self._name} - already in live mode')
            return {'result': -errno.EBUSY}
        logger.debug(f'Live mode started on {self._name}')
        # On Windows, we pass -1 as fd since UHID is stubbed
        self._uhid_fd = -1
        self.live = True
        return {'result': 0}

    def _stop_live(self):
        if not self.live:
            return
        logger.debug(f'Live mode stopped on {self._name}')
        self._server.broadcast_event('device_signal', {
            'device_id': self.device_id,
            'signal': 'LiveStopped',
            'args': [0]
        })
        self.live = False

    def _json_data(self, args):
        file_format = args.get('file_version', 1)
        if file_format != Drawing.JSON_FILE_FORMAT_VERSION:
            return ''
        timestamp = args.get('timestamp', 0)
        try:
            drawing = self.drawings[timestamp]
        except KeyError:
            return ''
        else:
            return drawing.to_json()

    def add_drawing(self, drawing):
        self.drawings[drawing.timestamp] = drawing
        self._server.broadcast_event('device_property_changed', {
            'device_id': self.device_id,
            'property': 'DrawingsAvailable',
            'value': list(self.drawings.keys())
        })

    def notify_button_press_required(self):
        logger.debug('Sending ButtonPressRequired signal')
        self._server.broadcast_event('device_signal', {
            'device_id': self.device_id,
            'signal': 'ButtonPressRequired',
            'args': []
        })

    def __repr__(self):
        return f'{self.device_id} - {self._name}'


class TuhiIPCServer(Object):
    """
    JSON-RPC over TCP server, replacing TuhiDBusServer.
    """
    __gsignals__ = {
        'bus-name-acquired': (1, None, ()),
        'bus-name-lost': (1, None, ()),
        'search-start-requested': (1, None, (TYPE_PYOBJECT,)),
        'search-stop-requested': (1, None, ()),
    }

    def __init__(self):
        Object.__init__(self)
        self._devices = []
        self._is_searching = False
        self._clients = []
        self._clients_lock = threading.Lock()
        self._server_thread = None
        self._server_socket = None
        self._start_server()

    @Property
    def is_searching(self):
        return self._is_searching

    @is_searching.setter
    def is_searching(self, value):
        if self._is_searching == value:
            return
        self._is_searching = value
        self.broadcast_event('manager_property_changed', {
            'property': 'Searching',
            'value': value
        })

    def _start_server(self):
        """Start the TCP server in a background thread."""
        def _run():
            self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                self._server_socket.bind((IPC_HOST, IPC_PORT))
            except OSError as e:
                logger.error(f'Cannot bind to {IPC_HOST}:{IPC_PORT}: {e}')
                logger.error('Is another Tuhi process running?')
                self.emit('bus-name-lost')
                return

            self._server_socket.listen(5)
            logger.debug(f'IPC server listening on {IPC_HOST}:{IPC_PORT}')
            self.emit('bus-name-acquired')

            while True:
                try:
                    client_sock, addr = self._server_socket.accept()
                    logger.debug(f'IPC client connected from {addr}')
                    ct = threading.Thread(target=self._handle_client,
                                         args=(client_sock,), daemon=True)
                    ct.start()
                except OSError:
                    break  # Server socket closed

        self._server_thread = threading.Thread(target=_run, daemon=True)
        self._server_thread.start()

    def _handle_client(self, client_sock):
        """Handle a single client connection."""
        with self._clients_lock:
            self._clients.append(client_sock)

        buf = b''
        try:
            while True:
                data = client_sock.recv(4096)
                if not data:
                    break
                buf += data
                while b'\n' in buf:
                    line, buf = buf.split(b'\n', 1)
                    try:
                        request = json.loads(line.decode('utf-8'))
                        response = self._dispatch(request)
                        msg = json.dumps(response) + '\n'
                        client_sock.sendall(msg.encode('utf-8'))
                    except json.JSONDecodeError:
                        err = json.dumps({'error': 'Invalid JSON'}) + '\n'
                        client_sock.sendall(err.encode('utf-8'))
        except (ConnectionResetError, BrokenPipeError, OSError):
            pass
        finally:
            with self._clients_lock:
                if client_sock in self._clients:
                    self._clients.remove(client_sock)
            try:
                client_sock.close()
            except OSError:
                pass
            logger.debug('IPC client disconnected')

    def _dispatch(self, request):
        """Route an IPC request to the appropriate handler."""
        method = request.get('method', '')
        args = request.get('args', {})
        req_id = request.get('id', None)

        result = {}

        if method == 'GetDevices':
            result = {
                'devices': [d.device_id for d in self._devices if d.registered]
            }
        elif method == 'GetAllDevices':
            result = {
                'devices': [d._get_properties() for d in self._devices]
            }
        elif method == 'StartSearch':
            self._start_search()
            result = {'result': 'ok'}
        elif method == 'StopSearch':
            self._stop_search()
            result = {'result': 'ok'}
        elif method == 'GetManagerProperties':
            result = {
                'devices': [d.device_id for d in self._devices if d.registered],
                'searching': self._is_searching,
                'json_data_versions': [Drawing.JSON_FILE_FORMAT_VERSION],
            }
        elif method.startswith('Device.'):
            device_method = method[len('Device.'):]
            device_id = args.get('device_id', '')
            dev = self._find_device(device_id)
            if dev is None:
                result = {'error': f'Device not found: {device_id}'}
            else:
                result = dev.handle_method(device_method, args)
        else:
            result = {'error': f'Unknown method: {method}'}

        if req_id is not None:
            result['id'] = req_id
        return result

    def _find_device(self, device_id):
        for d in self._devices:
            if d.device_id == device_id:
                return d
        return None

    def broadcast_event(self, event_type, data):
        """Send an event to all connected clients."""
        msg = json.dumps({'event': event_type, 'data': data}) + '\n'
        encoded = msg.encode('utf-8')
        with self._clients_lock:
            dead_clients = []
            for client in self._clients:
                try:
                    client.sendall(encoded)
                except (BrokenPipeError, OSError):
                    dead_clients.append(client)
            for c in dead_clients:
                self._clients.remove(c)

    def _start_search(self):
        if self.is_searching:
            return
        self.is_searching = True
        self.emit('search-start-requested', self._on_search_stop)
        for d in self._devices:
            if not d.registered:
                self.broadcast_event('unregistered_device', {
                    'device_id': d.device_id
                })

    def _stop_search(self):
        if not self.is_searching:
            return
        self.is_searching = False
        self.emit('search-stop-requested')

    def _on_search_stop(self, status):
        logger.debug('Search has stopped')
        self.is_searching = False
        self.broadcast_event('search_stopped', {'status': status})

        for dev in self._devices:
            if dev.registered:
                continue
            dev.remove()
        self._devices = [d for d in self._devices if d.registered]

    def cleanup(self):
        if self._server_socket:
            self._server_socket.close()

    def create_device(self, device):
        dev = TuhiIPCDevice(device, self)
        dev.connect('notify::registered', self._on_device_registered)
        self._devices.append(dev)
        if not device.registered:
            self.broadcast_event('unregistered_device', {
                'device_id': dev.device_id
            })
        return dev

    def _on_device_registered(self, device, param):
        self.broadcast_event('manager_property_changed', {
            'property': 'Devices',
            'value': [d.device_id for d in self._devices if d.registered]
        })

        if not device.registered and self._is_searching:
            self.broadcast_event('unregistered_device', {
                'device_id': device.device_id
            })
