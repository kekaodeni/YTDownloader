"""Windows 10/11 native WinRT toasts, without a service or Python WinRT DLLs.

Per-user AUMID registration follows WindowsCommunityToolkit's unpackaged app
registration. The OS PowerShell 5.1 WinRT bridge is launched without a window;
only escaped, locally generated toast XML crosses that bridge.
"""
import base64
import json
import logging
from pathlib import Path
import os
import subprocess
import sys
import uuid
from xml.etree.ElementTree import Element, SubElement, tostring

from PySide6.QtCore import QObject, QThreadPool, Signal
from yt_downloader.workers.function_worker import FunctionWorker


AUMID = 'YTDownloader.Desktop'


def toast_xml(title, body):
    toast = Element('toast', duration='short')
    binding = SubElement(SubElement(toast, 'visual'), 'binding', template='ToastGeneric')
    SubElement(binding, 'text').text = str(title)[:180]
    SubElement(binding, 'text').text = str(body)[:512]
    SubElement(toast, 'audio', silent='true')
    return tostring(toast, encoding='unicode')


def _encoded_script(script):
    return base64.b64encode(script.encode('utf-16-le')).decode('ascii')


def send_windows_toast(title, body, icon_path='', *, app_id=AUMID):
    if sys.platform != 'win32':
        return {'supported': False}
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, 'Software\\Classes\\AppUserModelId\\' + app_id) as key:
        winreg.SetValueEx(key, 'DisplayName', 0, winreg.REG_SZ, 'YTDownloader')
        if icon_path:
            winreg.SetValueEx(key, 'IconUri', 0, winreg.REG_SZ, str(icon_path))
    tag = uuid.uuid4().hex[:16]
    payload = base64.b64encode(json.dumps(dict(id=app_id, xml=toast_xml(title, body), tag=tag)).encode()).decode()
    script = r'''
$ErrorActionPreference = 'Stop'
$p = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__PAYLOAD__')) | ConvertFrom-Json
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] > $null
[Windows.UI.Notifications.ToastNotification, Windows.UI.Notifications, ContentType=WindowsRuntime] > $null
[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType=WindowsRuntime] > $null
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml($p.xml)
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
$toast.Tag = $p.tag
$toast.Group = 'downloads'
$notifier = [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($p.id)
$notifier.Show($toast)
$history = [Windows.UI.Notifications.ToastNotificationManager]::History.GetHistory($p.id)
$found = @($history | Where-Object { $_.Tag -eq $p.tag }).Count -gt 0
@{supported=$true; setting=$notifier.Setting.ToString(); in_history=$found; tag=$p.tag} | ConvertTo-Json -Compress
'''.replace('__PAYLOAD__', payload)
    powershell = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    # CREATE_NO_WINDOW already hides the process. Windows PowerShell 5.1 can
    # stall at startup when -WindowStyle Hidden is combined with no console.
    try:
        result = subprocess.run([str(powershell), '-NoProfile', '-NonInteractive',
                                 '-EncodedCommand', _encoded_script(script)],
                                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=15,
                                creationflags=subprocess.CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired:
        # Do not include the encoded title/body payload in application logs.
        raise RuntimeError('Windows toast bridge timed out') from None
    if result.returncode:
        raise RuntimeError(f'Windows toast bridge failed ({result.returncode})')
    return json.loads(result.stdout.strip())


class WindowsNotificationSink(QObject):
    delivered = Signal(object)

    def __init__(self, icon_path='', parent=None):
        super().__init__(parent)
        self.icon_path = str(icon_path)
        self.workers = []

    def send(self, title, body):
        if sys.platform != 'win32':
            return
        worker = FunctionWorker(send_windows_toast, title, body, self.icon_path)
        self.workers.append(worker)
        worker.signals.result.connect(self.delivered)
        worker.signals.error.connect(lambda error: logging.getLogger(__name__).warning('%s', error.technical_message))
        worker.signals.finished.connect(lambda: self.workers.remove(worker) if worker in self.workers else None)
        QThreadPool.globalInstance().start(worker)
