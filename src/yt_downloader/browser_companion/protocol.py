"""Bounded UTF-8 messages shared by Native Messaging and local byte pipes."""
import ipaddress
import json
import re
import struct
from urllib.parse import urlsplit

PROTOCOL = 1
HOST_NAME = 'io.github.kekaodeni.ytdownloader'
MAX_MESSAGE_BYTES = 32768
MAX_URL_LENGTH = 8192
ACTIONS = frozenset({'ping', 'send_url', 'get_capabilities'})

class ProtocolError(ValueError):
    def __init__(self, status='invalid_message'):
        self.status = status
        super().__init__(status)  # Never interpolate an untrusted payload.

def validate_url(value):
    if not isinstance(value, str) or not value or len(value) > MAX_URL_LENGTH:
        raise ProtocolError('invalid_url')
    try:
        from yt_downloader.core.url import normalize_media_url
        normalize_media_url(value)
        parsed = urlsplit(value)
        host = parsed.hostname.encode('idna').decode('ascii').lower().rstrip('.')
        if ('.' not in host and ':' not in host or host == 'localhost' or
                host.endswith(('.localhost', '.local', '.internal', '.lan', '.home', '.test', '.invalid'))):
            raise ValueError()
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            if re.fullmatch(r'[0-9.]+|(?:0x[0-9a-f]+)(?:\.(?:0x)?[0-9a-f]+)*', host): raise ValueError()
        else:
            if not address.is_global or address.is_multicast: raise ValueError()
    except (ValueError, UnicodeError, AttributeError):
        raise ProtocolError('invalid_url') from None
    return value

def validate_message(message, *, ipc=False):
    if not isinstance(message, dict): raise ProtocolError()
    if type(message.get('protocol')) is not int or message['protocol'] != PROTOCOL:
        raise ProtocolError('protocol_mismatch')
    action = message.get('action')
    if not isinstance(action, str): raise ProtocolError()
    if action not in ACTIONS and not (ipc and action == 'activate'): raise ProtocolError()
    request_id = message.get('request_id')
    if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', request_id): raise ProtocolError()
    allowed = {'protocol', 'action', 'request_id'} | ({'url'} if action == 'send_url' else set())
    if ipc: allowed |= {'browser'}
    if set(message) - allowed: raise ProtocolError()
    if ipc and (not isinstance(message.get('browser', ''), str) or
                message.get('browser', '') not in {'', 'chrome', 'edge', 'firefox'}): raise ProtocolError()
    if action == 'send_url': validate_url(message.get('url'))
    return message

def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ProtocolError()
        result[key] = value
    return result

def decode_message(data):
    try:
        result = json.loads(data.decode('utf-8'), object_pairs_hook=_object,
                            parse_constant=lambda _: (_ for _ in ()).throw(ProtocolError()))
        if not isinstance(result, dict): raise ProtocolError()
        return result
    except (ValueError, UnicodeError, RecursionError): raise ProtocolError() from None

def frame(message):
    data = json.dumps(message, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
    if not 0 < len(data) <= MAX_MESSAGE_BYTES: raise ProtocolError()
    return struct.pack('<I', len(data)) + data

def _read_exact(stream, count):
    chunks = bytearray()
    while len(chunks) < count:
        part = stream.read(count - len(chunks))
        if not part: raise ProtocolError()
        chunks.extend(part)
    return bytes(chunks)

def read_message(stream):
    prefix = stream.read(4)
    if not prefix: return None
    if len(prefix) < 4: prefix += _read_exact(stream, 4 - len(prefix))
    length = struct.unpack('<I', prefix)[0]
    if not 0 < length <= MAX_MESSAGE_BYTES: raise ProtocolError()
    return decode_message(_read_exact(stream, length))

def write_message(stream, message):
    stream.write(frame(message))
    stream.flush()

def response(request_id, status, **values):
    return dict(protocol=PROTOCOL, request_id=request_id, status=status, **values)
