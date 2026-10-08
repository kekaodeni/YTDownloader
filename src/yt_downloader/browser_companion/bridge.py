"""Native Messaging host: authenticated origin -> fixed app -> URL-only IPC."""
from collections import OrderedDict
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from .ipc_client import send_local
from .protocol import (ACTIONS, PROTOCOL, ProtocolError, read_message, response,
                       validate_message, write_message)
from .registration import ConnectionManager

def authorize_caller(argv, config, root):
    for browser, entry in config.get('browsers', {}).items():
        extension_id = entry['extension_id']
        if browser in {'chrome', 'edge'}:
            if (argv and argv[0] == 'chrome-extension://' + extension_id + '/' and
                    all(re.fullmatch(r'--parent-window=\d+|--desktop-probe', arg) for arg in argv[1:])): return browser
        elif browser == 'firefox' and len(argv) in {2,3} and argv[1] == extension_id:
            if len(argv) == 3 and argv[2] != '--desktop-probe': continue
            if Path(argv[0]).resolve() == (root / 'firefox.json').resolve(): return browser
    raise ProtocolError('unauthorized_extension')

def launch_app(config):
    launch = config.get('launch', {})
    path = Path(launch.get('path', ''))
    if not path.is_file(): raise ProtocolError('app_launch_failed')
    if launch.get('mode') == 'frozen' and path.name == 'YTDownloader.exe':
        args, cwd = [str(path)], str(path.parent)
    elif launch.get('mode') == 'source' and path.name.lower() in {'python.exe', 'pythonw.exe'}:
        cwd = str(Path(launch.get('root', '')))
        if not (Path(cwd) / 'src/yt_downloader/__main__.py').is_file(): raise ProtocolError('app_launch_failed')
        args = [str(path), '-m', 'yt_downloader']
    else: raise ProtocolError('app_launch_failed')
    # No URL, options, program name or command from the extension enters argv.
    subprocess.Popen(args, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True,
                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

class NativeBridge:
    def __init__(self, config, browser, *, client=send_local, launcher=launch_app, timeout=45):
        self.config, self.browser = config, browser
        self.client, self.launcher, self.timeout = client, launcher, timeout
        self.seen = OrderedDict()

    def handle(self, message):
        validate_message(message)
        request_id = message['request_id']
        if request_id in self.seen:
            old, result = self.seen[request_id]
            return result if old == message else response(request_id, 'invalid_message')
        payload = dict(message, browser=self.browser)
        action = message['action']
        try:
            result = self.client(payload)
        except OSError:
            if action != 'send_url':
                result = response(request_id, 'accepted', bridge_ready=True, app_running=False,
                                  actions=sorted(ACTIONS))
            else:
                try: self.launcher(self.config)
                except (OSError, ProtocolError): return response(request_id, 'app_launch_failed')
                deadline = time.monotonic() + self.timeout
                result = response(request_id, 'host_unavailable')
                while time.monotonic() < deadline:
                    try:
                        result = self.client(payload, timeout=min(5, max(.1, deadline - time.monotonic())))
                        break
                    except OSError: time.sleep(.1)
        if result.get('request_id') != request_id or result.get('protocol') != PROTOCOL:
            result = response(request_id, 'protocol_mismatch')
        if len(self.seen) >= 256: self.seen.popitem(last=False)
        self.seen[request_id] = (dict(message), result)
        return result

def main(argv=None):
    from yt_downloader.infrastructure.paths import AppPaths
    manager = ConnectionManager(AppPaths.discover().data)
    try:
        config = manager.load()
        browser = authorize_caller(list(argv if argv is not None else sys.argv[1:]), config, manager.root)
    except (OSError, ValueError, KeyError): return 2
    if os.name == 'nt':
        import msvcrt
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    bridge = NativeBridge(config, '' if '--desktop-probe' in (argv if argv is not None else sys.argv[1:]) else browser)
    while True:
        request_id = ''
        try:
            message = read_message(sys.stdin.buffer)
            if message is None: return 0
            candidate_id = message.get('request_id')
            if isinstance(candidate_id, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,64}', candidate_id): request_id = candidate_id
            validate_message(message)
            request_id = message['request_id']
            result = bridge.handle(message)
        except ProtocolError as error:
            result = response(request_id, error.status)
        except Exception:
            result = response(request_id, 'host_unavailable')
        try: write_message(sys.stdout.buffer, result)
        except (OSError, BrokenPipeError): return 0
        if not request_id: return 2
