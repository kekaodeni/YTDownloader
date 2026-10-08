"""Qt event-loop IPC, restricted to the current Windows user."""
from collections import OrderedDict
import struct
import time
from PySide6.QtCore import QObject, QTimer, QLockFile
from PySide6.QtNetwork import QLocalServer
from .ipc_client import endpoint_name
from .protocol import MAX_MESSAGE_BYTES, ProtocolError, decode_message, frame, response, validate_message

class DesktopIPC(QObject):
    def __init__(self, parent=None, *, name=None, lock_path=None):
        super().__init__(parent)
        self.name = name or endpoint_name()
        from yt_downloader.infrastructure.paths import AppPaths
        lock_path = lock_path or AppPaths.discover().data / 'browser-companion' / 'instance.lock'
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = QLockFile(str(lock_path))
        self.server = QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.setMaxPendingConnections(16)
        self.server.newConnection.connect(self._connect)
        self.receiver = None
        self.pending = []
        self.seen = OrderedDict()
        self.sockets = set()

    def listen(self):
        # Windows cleans up pipes on process exit; never remove a live peer.
        if not self.lock.tryLock(0): return False
        if self.server.listen(self.name): return True
        self.lock.unlock()
        return False

    def set_receiver(self, receiver):
        self.receiver = receiver
        for message in self.pending: receiver(message)
        self.pending.clear()

    def _connect(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            # Windows reports a client PID only for a local named-pipe client.
            # Reject a remote SMB client even if it can authenticate as this user.
            import os
            if os.name == 'nt':
                import ctypes
                from ctypes import wintypes
                kernel = ctypes.WinDLL('kernel32', use_last_error=True)
                kernel.GetNamedPipeClientProcessId.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.ULONG)]
                pid = wintypes.ULONG()
                if not kernel.GetNamedPipeClientProcessId(int(socket.socketDescriptor()), ctypes.byref(pid)) or not pid.value:
                    socket.abort()
                    socket.deleteLater()
                    continue
            self.sockets.add(socket)
            state = bytearray()
            timer = QTimer(socket)
            timer.setSingleShot(True)
            timer.timeout.connect(socket.abort)
            timer.start(5000)
            socket.disconnected.connect(lambda s=socket: (self.sockets.discard(s), s.deleteLater()))
            socket.readyRead.connect(lambda s=socket,b=state: self._read(s,b))
            if socket.bytesAvailable(): self._read(socket, state)

    def _read(self, socket, data):
        if len(data) > MAX_MESSAGE_BYTES + 4:
            socket.abort(); return
        data.extend(bytes(socket.read(MAX_MESSAGE_BYTES + 5 - len(data))))
        if len(data) < 4: return
        length = struct.unpack('<I', data[:4])[0]
        if not 0 < length <= MAX_MESSAGE_BYTES or len(data) > length + 4:
            socket.abort(); return
        if len(data) < length + 4: return
        request_id = ''
        try:
            message = decode_message(bytes(data[4:]))
            validate_message(message, ipc=True)
            request_id = message['request_id']
            now = time.monotonic()
            self.seen = OrderedDict((key,value) for key,value in self.seen.items() if now - value[0] < 120)
            if request_id in self.seen:
                previous = self.seen[request_id]
                result = previous[1] if previous[2] == message else response(request_id, 'invalid_message')
            else:
                result = self.receiver(message) if self.receiver else self._queue(message)
                if len(self.seen) >= 256: self.seen.popitem(last=False)
                self.seen[request_id] = (now, result, message)
        except ProtocolError as error: result = response(request_id, error.status)
        except Exception: result = response(request_id, 'host_unavailable')
        socket.write(frame(result))
        socket.flush()
        socket.disconnectFromServer()

    def _queue(self, message):
        if len(self.pending) >= 16: return response(message['request_id'], 'busy')
        self.pending.append(message)
        return response(message['request_id'], 'accepted')

    def close(self):
        for socket in tuple(self.sockets): socket.abort()
        self.server.close()
        self.lock.unlock()
