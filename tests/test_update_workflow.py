from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from yt_downloader.app import AppController
from yt_downloader.core.errors import AppError
from yt_downloader.updates.models import UpdateCapability, UpdateState
from yt_downloader.updates.service import UpdateService
from yt_downloader.updates.signature import TrustedKeyring
from yt_downloader.updates.state import UpdateStateStore
from test_update_service import ImmediateRunner, _signed_release


@pytest.fixture
def service(tmp_path):
    release, raw, signature, public = _signed_release()
    return UpdateService(
        current_version='0.4.0', discovery=SimpleNamespace(check=lambda _: [release]),
        fetch_bytes={release.manifest_url: raw, release.signature_url: signature}.__getitem__,
        keyring=TrustedKeyring({'test': public}), state_store=UpdateStateStore(tmp_path/'state.json'),
        downloader=None, staging_root=tmp_path/'staging', capability=UpdateCapability.AUTO_INSTALL,
        runner=ImmediateRunner(),
    )


@pytest.fixture
def controller(service, quick_window):
    controller = AppController.__new__(AppController)
    controller.window = quick_window
    controller.updates = service
    controller.update_capability = service.capability
    controller._update_dialog = None
    controller.show_error = Mock()
    service.state_changed.connect(controller._update_state_changed)
    service.update_available.connect(controller._update_available)
    service.failed.connect(controller._update_failed)
    service.progress.connect(controller._update_progress)
    service.ready.connect(controller._update_ready)
    return controller


def test_manual_check_opens_one_dialog_automatic_only_banner(controller):
    service = controller.updates
    service.check(manual=False)
    assert controller._update_dialog is None
    assert controller.window.state['updateVisible']
    service.check(manual=True)
    assert controller._update_dialog is not None
    first = controller._update_dialog
    controller._show_update_dialog()
    assert controller._update_dialog is first
    assert len(controller.window.dialogs.sessions) == 1


@pytest.mark.parametrize('result', [None, UpdateState.NO_COMPATIBLE_UPDATE, 'error'])
def test_new_check_clears_previous_candidate(controller, result):
    service = controller.updates
    service.check(manual=True)
    def check(_):
        if result == 'error':
            raise TimeoutError('offline')
        return []
    service.discovery.check = check
    if result is UpdateState.NO_COMPATIBLE_UPDATE:
        service._check_worker = lambda: result
    service.check(manual=True)
    assert service.manifest is None
    assert not service.download()
    assert controller._update_dialog is None
    assert not controller.window.state['updateVisible']


@pytest.mark.parametrize('state', [UpdateState.DOWNLOADING, UpdateState.VERIFYING, UpdateState.READY_TO_INSTALL])
def test_reopen_uses_current_update_state(controller, state):
    service = controller.updates
    service.check(manual=True)
    controller._update_dialog.reject()
    service._set_state(state)
    controller._show_update_dialog()
    dialog = controller._update_dialog
    assert not dialog.state['canDownload']
    assert dialog.state['canInstall'] == (state is UpdateState.READY_TO_INSTALL)
    assert controller.window.state['updateReview']


def test_pending_package_cannot_be_replaced_by_check(service):
    service._set_state(UpdateState.READY_TO_INSTALL)
    assert not service.check(manual=True)


@pytest.mark.parametrize('operation', ['check', 'download', 'prepare'])
def test_retry_uses_failed_operation_not_manifest(controller, operation):
    service = controller.updates
    service.check(manual=True)
    service.last_operation = operation
    service._operation_failed(AppError('test', '失败', 'test'), True)
    service.check = Mock()
    service.download = Mock()
    controller._request_update_install = Mock()
    controller._retry_update()
    assert service.check.called == (operation == 'check')
    assert service.download.called == (operation == 'download')
    assert controller._request_update_install.called == (operation == 'prepare')


def test_progress_clock_zero_elapsed_and_new_attempt_reset(service):
    service.clock = lambda: 10.0
    service._download_started = 10.0
    service._report_progress((25, 100))
    assert service.latest_progress.speed is None
    service.clock = lambda: 15.0
    service._report_progress((25, 100))
    assert service.latest_progress.speed == 5.0
    assert service.latest_progress.eta == 15
    service._report_progress((100, 100))
    assert service.latest_progress.eta == 0
    service._download_started = 15.0
    service._report_progress((0, 100))
    assert service.latest_progress.speed is None
    assert service.latest_progress.eta is None


def test_reopened_dialog_restores_progress_without_installing(controller):
    service = controller.updates
    service.check(manual=True)
    service._set_state(UpdateState.DOWNLOADING)
    service._download_started = 0
    service.clock = lambda: 5.0
    service._report_progress((25, 100))
    controller._update_dialog.reject()
    controller._show_update_dialog()
    assert controller._update_dialog.state['progress'] == .25
    service._set_state(UpdateState.READY_TO_INSTALL)
    assert controller._update_dialog.state['canInstall']


def test_launch_failure_keeps_application_alive_and_can_retry(controller, monkeypatch):
    import yt_downloader.app as app_module
    controller.app = Mock()
    controller.queue = SimpleNamespace(is_busy=False)
    controller.metadata_process = SimpleNamespace(is_running=False)
    controller._thumbnail_workers = controller._settings_workers = []
    controller.updates.last_operation = 'prepare'
    monkeypatch.setattr(app_module.subprocess, 'Popen', Mock(side_effect=OSError('launch failed')))
    controller._launch_prepared_updater(('X:/staging/YTDownloaderUpdater.exe',))
    controller.app.quit.assert_not_called()
    assert controller.updates.state is UpdateState.FAILED
    assert controller.show_error.call_args.kwargs['retry_callback'] == controller._retry_update


def test_tasks_started_during_preparation_prevent_exit(controller, monkeypatch):
    import yt_downloader.app as app_module
    controller.app = Mock()
    controller.queue = SimpleNamespace(is_busy=True)
    controller.metadata_process = SimpleNamespace(is_running=False)
    controller._thumbnail_workers = controller._settings_workers = []
    launch = Mock()
    monkeypatch.setattr(app_module.subprocess, 'Popen', launch)
    controller._launch_prepared_updater(('X:/staging/YTDownloaderUpdater.exe',))
    controller.app.quit.assert_not_called()
    launch.assert_not_called()
    assert controller.updates.state is UpdateState.READY_TO_INSTALL


def test_prepare_failure_retries_prepare_without_redownload(service, tmp_path):
    from yt_downloader.updates.models import VerifiedUpdatePackage
    service.check(manual=True)
    service.verified_package = VerifiedUpdatePackage('fixture', tmp_path/'package.zip', service.manifest)
    service._set_state(UpdateState.READY_TO_INSTALL)
    service.prepare_install_command = Mock(side_effect=OSError('permission denied'))
    assert service.prepare_install(tmp_path, tmp_path/'data', 1)
    assert service.state is UpdateState.FAILED
    assert service.last_operation == 'prepare'
    service.prepare_install_command = Mock(return_value=('helper.exe', '--transaction', 'fixture'))
    assert service.prepare_install(tmp_path, tmp_path/'data', 1)
    assert service.state is UpdateState.PREPARING_EXIT


def test_missing_prepared_command_reports_failure(controller):
    service = controller.updates
    service.last_operation = 'prepare'
    service._install_prepared(None)
    assert service.state is UpdateState.FAILED
    controller.show_error.assert_called_once()
