"""A minimal recovery-only shell opened before history and regular update checks."""
import os
from pathlib import Path
import subprocess
import sys
import time

from PySide6.QtCore import QObject, QThreadPool, QTimer, Slot
from PySide6.QtWidgets import QApplication

from yt_downloader import __version__
from yt_downloader.core.errors import AppError
from yt_downloader.core.models import AppSettings
from yt_downloader.services.error_report_service import redact_sensitive
from yt_downloader.ui.quick_window import MainWindow
from yt_downloader.ui.quick_dialogs import ErrorSession
from yt_downloader.updates.archive import SafePackageExtractor as Archive
from yt_downloader.updates.installation import checked_path
from yt_downloader.updates.recovery import prepare_recovery
from yt_downloader.updates.signature import TrustedKeyring
from yt_downloader.updates.trusted_keys import PRODUCTION_TRUSTED_KEYS
from yt_downloader.workers.function_worker import FunctionWorker


def prepare_and_launch(request):
    pid = os.getpid()
    command = prepare_recovery(request, TrustedKeyring(PRODUCTION_TRUSTED_KEYS),
                               helper_version=__version__, parent_pid=pid)
    marker = checked_path(request.transaction/f'recovery-handoff-{pid}.json')
    if marker.exists():
        raise ValueError('A recovery handoff already exists; preserve it for inspection')
    environment = os.environ.copy()
    environment['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    process = subprocess.Popen(command, cwd=Path(command[0]).parent, env=environment,
                               close_fds=True, creationflags=0x08000000 if sys.platform == 'win32' else 0)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if marker.exists():
            value = Archive._load_json(checked_path(marker, exists=True))
            if value != dict(status='ready', transaction_id=request.transaction.name, parent_pid=pid,
                             helper_version=__version__):
                raise ValueError('Recovery helper handoff identity changed')
            return True
        if process.poll() is not None:
            raise RuntimeError(f'Recovery helper exited before handoff ({process.returncode})')
        time.sleep(0.05)
    # The helper is still waiting for this application, which stays alive on
    # failure. It times out without touching the installation.
    raise TimeoutError('Recovery helper did not confirm its independent checks')


class RecoveryStartup(QObject):
    def __init__(self, app, window, request):
        super().__init__(window)
        self.app, self.window, self.request = app, window, request
        self.worker = None
        self.error_dialog = None
        self.window.recovery_details_requested.connect(self.show_details)
        self.window.update(recoveryVisible=True, recoveryBusy=True,
                           recoveryText='正在恢复上一次未完成的更新…')

    def start(self):
        self.worker = FunctionWorker(prepare_and_launch, self.request)
        self.worker.signals.result.connect(self.prepared)
        self.worker.signals.error.connect(self.failed)
        QThreadPool.globalInstance().start(self.worker)

    @Slot(object)
    def prepared(self, _result):
        self.window.update(recoveryText='恢复程序已就绪，正在安全退出…', allowClose=True)
        self.app.quit()

    @Slot(object)
    def failed(self, error):
        safe = redact_sensitive(str(getattr(error, 'technical_message', error)))
        self.error_dialog = ErrorSession(AppError('update_recovery_failed',
                '更新恢复失败。安装、备份和诊断文件已保留，请查看详情。', safe),
                safe, self.window, title_text='更新恢复失败')
        self.window.update(recoveryBusy=False, recoveryText='更新恢复失败', allowClose=True)

    @Slot()
    def show_details(self):
        if self.error_dialog:
            self.error_dialog.show()


def run_recovery_startup(paths, request, error=None):
    app = QApplication([sys.argv[0]])
    app.setApplicationName('YT Downloader')
    window = MainWindow(AppSettings(auto_check_updates=False), ytdlp_version='', ffmpeg_description='')
    controller = RecoveryStartup(app, window, request)
    window.show()
    if error is not None:
        controller.failed(error)
    else:
        QTimer.singleShot(0, controller.start)
    try:
        return app.exec()
    finally:
        QThreadPool.globalInstance().waitForDone()
        window.dispose()
