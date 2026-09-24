"""Source GUI smoke for the history, Cookie and download-page UI revision."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from yt_downloader.core.models import AppSettings, CookieProfile, HistoryRecord, TaskStatus
from yt_downloader.ui.quick_window import MainWindow
from verify_quick_ui import sample_video


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-dpr', type=float, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)

    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow(AppSettings(auto_check_updates=False), ytdlp_version='fixture', ffmpeg_description='fixture')
    window.root.resize(1200, 800)
    window.show()

    if abs(window.root.devicePixelRatio() - args.expected_dpr) > .02:
        window.dispose()
        raise ValueError(f'Expected DPR {args.expected_dpr}, got {window.root.devicePixelRatio()}')

    def find(name: str):
        item = window.root.findChild(QObject, name)
        if item is None:
            pending = [window.root.contentItem()]
            while pending:
                current = pending.pop()
                if current.objectName() == name:
                    return current
                pending.extend(current.childItems())
        assert item is not None, name
        return item

    def names():
        pending = [window.root.contentItem()]
        while pending:
            item = pending.pop()
            yield item.objectName()
            pending.extend(item.childItems())

    def click(name: str):
        item = find(name)
        point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
        QTest.mouseClick(window.root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)

    def wait(ms=160):
        QTimer.singleShot(ms, app.quit)
        app.exec()

    screenshots: list[str] = []

    def capture(name: str):
        path = args.output / f'{name}.png'
        assert window.grab().save(str(path)), path
        screenshots.append(path.name)

    def reveal(item_name: str):
        view = find('taskList')
        item = find(item_name)
        top = item.mapToItem(view, QPointF(0, 0)).y()
        origin_y = float(view.property('originY'))
        maximum = max(origin_y, origin_y + float(view.property('contentHeight')) - view.height())
        view.setProperty('contentY', min(maximum, max(origin_y, float(view.property('contentY')) + top - 24)))

    try:
        for theme_mode in ('light', 'dark'):
            window.theme.set_mode(theme_mode)
            window.download_page.show_video(sample_video())
            window._select_page(0)
            wait()
            assert 'nativeFormatSwitch' not in set(names())
            assert find('cookieManagementButton').property('appearance') == 'normal'
            assert find('formatCombo').property('enabled')
            assert window.download_page.state['qualityAuto'] is True
            assert 'yt-dlp' in find('formatSelectionHint').property('text')
            capture(f'download-top-{theme_mode}')

            filename, directory = find('filenameInput'), find('directoryInput')
            origin = window.root.contentItem()
            filename_x = filename.mapToItem(origin, QPointF(0, 0)).x()
            directory_x = directory.mapToItem(origin, QPointF(0, 0)).x()
            assert abs(filename_x - directory_x) < 1
            assert filename.height() <= 42 and directory.height() <= 42
            reveal('filenameInput')
            wait()
            capture(f'download-fields-{theme_mode}')

            history = window.history_page
            records = [HistoryRecord(f'{theme_mode}-{i}', 'fixture', 'https://example.org/video',
                                     f'历史记录 {i}', args.output / f'{theme_mode}-{i}.mp4',
                                     '1080p', 1000, None, TaskStatus.COMPLETED, 'fixture') for i in range(2)]
            history.set_records(records)

            def delete_confirmed(ids):
                removed = set(ids)
                history.set_records([record for record in records if record.task_id not in removed])
                history.batch_delete_succeeded(len(removed), 0)

            history.delete_many_requested.connect(delete_confirmed)
            window._select_page(1)
            wait()
            click('historyManageToggle')
            wait()
            actions = [find(name) for name in ('historySelectAll', 'historySelectNone',
                                                'historyDeleteSelected', 'historyClear',
                                                'historyManageToggle')]
            assert all(action.isVisible() for action in actions)
            centers = [action.y() + action.height() / 2 for action in actions]
            assert max(centers) - min(centers) < 1
            check = find(f'historySelect-{theme_mode}-0')
            indicator = find(f'historyCheckboxIndicator-{theme_mode}-0')
            assert check.isVisible() and indicator.width() <= 18 and indicator.height() <= 18
            assert abs(indicator.y() + indicator.height() / 2 - check.height() / 2) < 1
            capture(f'history-manage-{theme_mode}')
            click('historySelectAll')
            click('historyDeleteSelected')
            wait()
            assert find('dialog-confirm').property('visible')
            find('dialog-confirm').property('session').answer(True)
            wait()
            assert not history.state['managing'] and history.state['checkedCount'] == 0
            assert history.model.count == 0
            history.delete_many_requested.disconnect(delete_confirmed)

            profile = CookieProfile(f'{theme_mode}-fixture', '浏览器配置', 'browser',
                                    browser='firefox', domain_hint='example.org')
            window.cookies.set_profiles((profile,))
            window._select_page(2)
            settings_scroll = find('settingsScroll')
            settings_scroll.setProperty('contentY', 0)
            wait()
            help_button = find('cookiePrivacyHelp')
            edit_button = find(f'cookieEdit-{profile.id}')
            delete_button = find(f'cookieDelete-{profile.id}')
            assert help_button.property('appearance') == 'normal'
            assert help_button.property('text') == '查看 Cookie 用途与隐私说明'
            assert delete_button.property('appearance') == 'danger'
            assert abs(edit_button.height() - delete_button.height()) < 1
            capture(f'settings-cookie-{theme_mode}')
            click('cookiePrivacyHelp')
            wait()
            info = next(session for session in window.dialogs.sessions if session.state['kind'] == 'info')
            info.reject()
            wait()

        assert not window.qml_warnings, window.qml_warnings
        report = {
            'device_pixel_ratio': window.root.devicePixelRatio(),
            'qml_warnings': window.qml_warnings,
            'screenshots': screenshots,
            'checks': [
                'history_toolbar_alignment', 'compact_centered_checkbox',
                'confirmed_delete_exits_management', 'cookie_help_button',
                'cookie_delete_danger_button', 'download_cookie_button',
                'native_ytdlp_default_without_switch', 'aligned_filename_directory_fields',
                'light_dark_theme',
            ],
        }
        (args.output / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False))
        return 0
    finally:
        for session in tuple(window.dialogs.sessions):
            session.reject()
        window.update(allowClose=True)
        window.close()
        window.dispose()
        window.theme.deleteLater()
        window.deleteLater()
        app.processEvents()


if __name__ == '__main__':
    raise SystemExit(main())
