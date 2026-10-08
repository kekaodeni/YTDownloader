import io
import json
import struct
import pytest
from yt_downloader.browser_companion.protocol import (
    ProtocolError, read_message, write_message, validate_message, validate_url, MAX_MESSAGE_BYTES)

@pytest.mark.parametrize('url', ['https://www.youtube.com/watch?v=8kIJ7QLTSRc',
    'https://www.bilibili.com/bangumi/play/ss46089', 'https://x.com/user/status/123',
    'https://new-public-site.org/video', 'https://example.org/a?x=1&y=2#chapter',
    'https://example.org/$(calc)', 'https://example.org/;powershell'])
def test_public_url_preserved(url):
    assert validate_url(url) == url

@pytest.mark.parametrize('url', ['chrome://settings', 'edge://extensions', 'about:addons',
    'file:///C:/secret', 'javascript:alert(1)', 'https://user:secret@example.org/',
    'http://localhost/', 'http://127.0.0.1/', 'http://[::1]/', 'http://10.0.0.1/',
    'http://192.168.1.1/', 'http://2130706433/', 'http://0x7f000001/',
    'https://printer.local/', 'https://intranet/', 'https://example.org/\ncmd',
    'https://example.org/' + 'x' * 8192])
def test_sensitive_or_invalid_url_rejected(url):
    with pytest.raises(ProtocolError): validate_url(url)

def test_native_framing_utf8_and_little_endian():
    message = dict(protocol=1, action='ping', request_id='request-1')
    output = io.BytesIO()
    write_message(output, message)
    assert struct.unpack('<I', output.getvalue()[:4])[0] == len(output.getvalue()[4:])
    output.seek(0)
    assert read_message(output) == message

@pytest.mark.parametrize('data', [b'\x01', struct.pack('<I', 4)+b'{}',
    struct.pack('<I', MAX_MESSAGE_BYTES+1), struct.pack('<I', 1)+b'\xff',
    struct.pack('<I', 1)+b'{', struct.pack('<I', 2)+b'[]',
    struct.pack('<I', 13)+b'{"x":1,"x":2}'])
def test_corrupt_or_oversized_message(data):
    with pytest.raises(ProtocolError): read_message(io.BytesIO(data))

@pytest.mark.parametrize('action', ['execute', 'extract_cookies', 'download', 'write_file'])
def test_no_arbitrary_actions(action):
    with pytest.raises(ProtocolError): validate_message(dict(protocol=1,action=action,request_id='r'))

def test_protocol_and_unknown_fields_rejected():
    for request in [dict(protocol=True,action='ping',request_id='r'),
        dict(protocol=2,action='ping',request_id='r'),
        dict(protocol=1,action='ping',request_id='r',cookie='secret')]:
        with pytest.raises(ProtocolError): validate_message(request)

def test_empty_input_is_clean_disconnect():
    assert read_message(io.BytesIO()) is None


@pytest.mark.parametrize('browser', [[], {}, 1, None])
def test_ipc_browser_identity_must_be_a_string(browser):
    with pytest.raises(ProtocolError):
        validate_message(dict(protocol=1, action='ping', request_id='r', browser=browser), ipc=True)
