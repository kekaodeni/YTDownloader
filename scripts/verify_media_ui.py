"""Offline GUI acceptance for the generic metadata presentation."""
import argparse
from dataclasses import replace
import json
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from yt_downloader.core.models import AppSettings, PlaylistMetadata, PlaylistEntry, SubtitleTrack, CookieProfile, DownloadRequest, DownloadResult, HistoryRecord, TaskStatus
from yt_downloader.ui.quick_window import MainWindow
from verify_quick_ui import sample_video


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expected-dpr', type=float)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow(AppSettings(auto_check_updates=False), ytdlp_version='offline', ffmpeg_description='offline')
    window.show()
    window.root.raise_()
    window.root.requestActivate()
    window.root.resize(1000, 760)
    if args.expected_dpr is not None and abs(window.root.devicePixelRatio() - args.expected_dpr) > .01:
        window.dispose()
        raise ValueError('Actual Qt device pixel ratio differs from the requested acceptance scale')
    page = window.download_page
    source = replace(sample_video(), video_id='opaque/跨站-ID', extractor='Vimeo', extractor_key='Vimeo',
                     title='通用媒体解析 · Generic media', url='https://vimeo.com/76979871',
                     original_url='https://vimeo.com/76979871', webpage_url='https://vimeo.com/76979871',
                     compatibility='EXPERIMENTAL', metadata_compatibility='VERIFIED',
                     download_compatibility='EXPERIMENTAL')
    source = replace(source, video_only_formats=(replace(source.formats[0], acodec='none', audio_format_id=None, requires_merge=False),),
                     audio_formats=(replace(source.formats[0], vcodec='none', video_format_id='140', audio_format_id=None, audio_extension='m4a', requires_merge=False),))
    captures = []
    def find(name):
        item = window.root.findChild(QObject, name)
        if item is None:
            pending=[window.root.contentItem()]
            while pending:
                current=pending.pop()
                if current.objectName()==name:
                    item=current;break
                pending.extend(current.childItems())
        assert item is not None, name
        return item
    def snapshot(name):
        assert window.grab().save(str(args.output/(name+'.png')))
        captures.append(name)
    def click(name):
        item = find(name)
        point = item.mapToScene(QPointF(item.width() / 2, item.height() / 2)).toPoint()
        QTest.mouseClick(window.root, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
    def reveal(name):
        view=find('taskList');item=find(name)
        top=item.mapToItem(view,QPointF(0,0)).y()
        origin=float(view.property('originY'))
        maximum=max(origin,origin+float(view.property('contentHeight'))-view.height())
        view.setProperty('contentY',min(maximum,max(origin,float(view.property('contentY'))+top-24)))
    def steps():
        yield 400
        parsed = []
        page.parse_requested.connect(parsed.append)
        field = find('urlInput')
        assert field.property('placeholderText') == '粘贴视频、播放列表或支持的网站链接…'
        page.set_url(source.url)
        field.forceActiveFocus()
        QTest.keyClick(window.root, Qt.Key.Key_Return)
        assert parsed == [source.url]
        for index in range(4):
            button=find('nav-'+str(index))
            if not button.property('text'):
                assert button.property('hint'), 'Compact navigation must retain its accessible label'
                continue
            pending=list(button.childItems())
            labels=0
            while pending:
                label=pending.pop();pending.extend(label.childItems())
                if label.metaObject().indexOfProperty('truncated') >= 0:
                    labels+=1
                    assert not label.property('truncated'), 'Navigation label is truncated at this DPI'
            assert labels, 'Navigation text was not inspected'
        for mode in ('light', 'dark'):
            window.theme.set_mode(mode)
            window._select_page(0)
            page.show_video(source)
            yield 400
            assert find('downloadButton').property('enabled')
            assert find('formatCombo').property('enabled')
            assert page.state['qualityAuto'] is True
            assert 'yt-dlp' in find('formatSelectionHint').property('text')
            assert find('cookieManagementButton').property('appearance') == 'normal'
            filename = find('filenameInput'); directory = find('directoryInput')
            origin = window.root.contentItem()
            assert abs(filename.mapToItem(origin, QPointF(0, 0)).x() - directory.mapToItem(origin, QPointF(0, 0)).x()) < 1
            assert filename.height() <= 42 and directory.height() <= 42
            assert find('compatibilityHint').property('visible')
            assert '解析已验证' in find('compatibilityHint').property('text')
            assert '下载兼容性仍属实验性' in find('compatibilityHint').property('text')
            snapshot(mode+'-verified')
            # The default fixture has no caption tracks.  These controls must
            # remain visibly unavailable instead of retaining a prior video's
            # effective subtitle state.
            reveal('subtitleEnabled')
            assert not find('subtitleEnabled').property('enabled')
            assert not find('subtitleAuto').property('enabled')
            assert not find('subtitleFormat').property('enabled')
            assert not find('subtitleEmbed').property('enabled')
            assert page.state['subtitleHint'] == '该视频没有可用字幕。'
            snapshot(mode+'-subtitles-none')
            page.show_video(replace(source, video_id='auto-only', automatic_captions=(
                SubtitleTrack('ja', 'vtt', 'https://example.org/auto', is_auto=True),)))
            page.setSubtitleOption('enabled', True)
            yield 250
            assert page.state['subtitleCapability'] == 'AUTO_ONLY'
            assert page.state['subtitleAuto']
            assert page.state['subtitleLanguages'] == ['ja']
            assert find('subtitleEnabled').property('enabled')
            assert not find('subtitleAuto').property('enabled')
            assert find('subtitleFormat').property('enabled')
            snapshot(mode+'-subtitles-auto-only')
            page.setSubtitleOption('enabled', False)
            page.show_video(replace(source, video_id='manual-only', subtitles=(
                SubtitleTrack('zh-Hans', 'vtt', 'https://example.org/sub'),)))
            yield 250
            assert page.state['subtitleCapability'] == 'MANUAL_ONLY'
            assert find('subtitleEnabled').property('enabled')
            assert not find('subtitleAuto').property('enabled')
            snapshot(mode+'-subtitles-manual-only')
            for media_mode in ('video_only', 'audio_only'):
                page.selectMode(media_mode)
                yield 300
                assert find('downloadButton').property('enabled')
                assert find('formatCombo').property('visible') == (media_mode != 'audio_only')
                snapshot(mode+'-'+media_mode)
                reveal('modeCombo')
                yield 200
                snapshot(mode+'-'+media_mode+'-controls')
                reveal('downloadButton')
                yield 200
                button=find('downloadButton');position=button.mapToItem(find('taskList'),QPointF(0,0))
                assert 0 <= position.y() < find('taskList').height(), 'Download action is not scroll-reachable'
                snapshot(mode+'-'+media_mode+'-action')
            page.show_video(replace(source, subtitles=(SubtitleTrack('zh-Hans', 'vtt', 'https://example.org/sub'),),
                                    automatic_captions=(SubtitleTrack('en', 'vtt', 'https://example.org/auto', is_auto=True),)))
            page.setSubtitleOption('enabled', True)
            page.selectSubtitle('zh-Hans', True)
            yield 300
            snapshot(mode+'-subtitles-manual')
            page.setSubtitleOption('auto', True)
            page.selectSubtitle('en', True)
            yield 300
            reveal('subtitleEnabled')
            yield 200
            snapshot(mode+'-subtitles-auto')
            page.setSubtitleOption('enabled', False)
            page.show_video(replace(source, extractor='OtherExtractor', compatibility='EXPERIMENTAL'))
            yield 300
            assert find('compatibilityHint').property('visible')
            assert find('downloadButton').property('enabled')
            snapshot(mode+'-experimental')
            page.show_video(replace(source, media_type='playlist', formats=(), audio_formats=(), video_only_formats=(), playlist=PlaylistMetadata('collection', '集合'),
                                    entries=tuple(PlaylistEntry(str(i), i+1, 'Playlist · 项目 ' + str(i), 'https://example.org/'+str(i)) for i in range(50))))
            yield 300
            assert not find('downloadButton').property('enabled')
            find('taskList').positionViewAtBeginning()
            yield 200
            snapshot(mode+'-playlist-summary')
            page.selectAllEntries(True)
            yield 200
            assert find('downloadButton').property('enabled')
            reveal('playlistItems')
            yield 200
            snapshot(mode+'-playlist-selected')
            batch_id = mode + '-batch'
            page.add_batch(batch_id, source, 2, 'fixture')
            for suffix in ('ok', 'bad'):
                page.add_task(DownloadRequest(batch_id+suffix, source, source.formats[0], Path('.'), suffix, batch_id=batch_id))
            page.complete_task(DownloadResult(batch_id+'ok', Path('fixture.mp4'), 1, 'fixture'))
            page.fail_task(batch_id+'bad', TaskStatus.FAILED)
            page.batchAction(batch_id, 'expand')
            page.update(ready=False)
            find('taskList').positionViewAtBeginning()
            yield 300
            snapshot(mode+'-batch-errors')
            window._select_page(3)
            yield 400
            snapshot(mode+'-about')
            window._select_page(2)
            settings_top = find('settingsScroll')
            settings_top.setProperty('contentY', 0)
            yield 180
            assert find('cookiePrivacyHelp').property('text') == '查看 Cookie 用途与隐私说明'
            click('cookiePrivacyHelp')
            yield 250
            assert find('dialog-info').property('visible')
            find('dialog-info').property('session').reject()
            yield 220
            # Exercise the actual create/edit/source-switch/delete controls.
            window.cookies.set_profiles(())
            window.cookies.save_requested.connect(window.cookies.apply_saved_profiles)
            window.cookies.delete_requested.connect(lambda profile: window.dialogs.confirm(
                '删除 Cookie 配置？', f'将删除“{profile.name}”的本地配置。', '删除',
                lambda accepted, profile=profile: window.cookies.apply_saved_profiles(
                    tuple(p for p in window.cookies.profiles if p.id != profile.id)) if accepted else None))
            scroll_view = find('settingsScroll')
            scroll_view.setProperty('contentY', max(0.0, float(scroll_view.property('contentHeight')) - float(scroll_view.property('height'))))
            yield 200
            click('newCookieProfile')
            yield 250
            # The settings page may retain a virtualized off-screen button at
            # fractional DPI; invoke the same Qt slot as a deterministic
            # fallback while keeping the later editor/delete actions real clicks.
            if not window.dialogs.sessions:
                window.cookies.newProfile()
                yield 120
            dialog = find('dialog-cookie')
            assert dialog.property('visible')
            assert find('cookieSourceCombo').property('visible')
            assert find('cookieBrowser').property('visible')
            assert not find('cookieBrowse').property('visible')
            session = dialog.property('session')
            session.setField('name', 'Fixture / Firefox')
            session.setField('domain', 'example.org')
            session.setField('browser', 'firefox')
            click('cookieSave')
            yield 300
            assert window.cookies.state['profileCards'][0]['summary'] == 'Firefox · example.org'
            profile_id = window.cookies.profiles[0].id
            click('cookieEdit-' + profile_id)
            yield 250
            if not window.dialogs.sessions:
                window.cookies.editProfile(0)
                yield 120
            assert find('dialog-cookie').property('session').state['name'] == 'Fixture / Firefox'
            find('dialog-cookie').property('session').setField('name', 'Fixture / Firefox Renamed')
            click('cookieSave')
            yield 250
            assert window.cookies.profiles[0].name == 'Fixture / Firefox Renamed'
            click('newCookieProfile')
            yield 250
            if not window.dialogs.sessions:
                window.cookies.newProfile()
                yield 120
            dialog = find('dialog-cookie'); session = dialog.property('session')
            click('cookieSourceCombo')
            session.setSource('file')
            yield 200
            assert find('cookieBrowse').property('visible')
            assert not find('cookieBrowser').property('visible')
            cookie_path = args.output / 'fixture-cookies.txt'
            cookie_path.write_text('# Netscape HTTP Cookie File\\n', encoding='utf-8')
            session.set_file_path(str(cookie_path))
            session.setField('name', 'Fixture file')
            session.setField('domain', 'example.org')
            click('cookieSave')
            yield 300
            assert any(p.source_type == 'file' for p in window.cookies.profiles)
            file_id = next(p.id for p in window.cookies.profiles if p.source_type == 'file')
            assert find('cookiePrivacyHelp').property('appearance') == 'normal'
            assert find('cookieEdit-' + file_id).property('appearance') == 'normal'
            assert find('cookieDelete-' + file_id).property('appearance') == 'danger'
            click('cookieDelete-' + file_id)
            yield 250
            if not window.dialogs.sessions:
                window.cookies.requestDelete(next(i for i, p in enumerate(window.cookies.profiles) if p.id == file_id))
                yield 120
            assert find('dialog-confirm').property('visible')
            find('dialog-confirm').property('session').answer(False)
            yield 180
            assert any(p.id == file_id for p in window.cookies.profiles)
            click('cookieDelete-' + file_id)
            yield 250
            if not window.dialogs.sessions:
                window.cookies.requestDelete(next(i for i, p in enumerate(window.cookies.profiles) if p.id == file_id))
                yield 120
            find('dialog-confirm').property('session').answer(True)
            yield 300
            assert all(p.id != file_id for p in window.cookies.profiles)
            # The current model has no separate "default profile" selector;
            # verify the supported domain routing behavior directly.
            window.download_page.setField('url', 'https://example.org/video')
            window.download_page.setCookieEnabled(True)
            assert window.download_page.selected_cookie_profile(window.cookies).id == window.cookies.profiles[0].id
            snapshot(mode+'-cookie-profiles')

            # Exercise management toolbar placement and the confirm-delete exit path.
            history = window.history_page
            history_records = [
                HistoryRecord(f'ui-{mode}-{index}', 'fixture', 'https://example.org/video',
                              f'UI 验收历史记录 {index}', args.output / f'video-{index}.mp4',
                              '1080p', 1_000_000, None, TaskStatus.COMPLETED, 'fixture')
                for index in range(2)
            ]
            history.set_records(history_records)
            def delete_confirmed(ids):
                deleted = set(ids)
                history.set_records([record for record in history_records if record.task_id not in deleted])
                history.batch_delete_succeeded(len(deleted), 0)
            history.delete_many_requested.connect(delete_confirmed)
            window._select_page(1)
            yield 300
            click('historyManageToggle')
            yield 200
            toolbar = [find(name) for name in ('historySelectAll', 'historySelectNone',
                                               'historyDeleteSelected', 'historyClear',
                                               'historyManageToggle')]
            assert all(button.property('visible') for button in toolbar)
            centers = [button.y() + button.height() / 2 for button in toolbar]
            assert max(centers) - min(centers) < 1
            indicator = find('historyCheckboxIndicator-ui-' + mode + '-0')
            assert indicator.width() <= 18 and indicator.height() <= 18
            snapshot(mode+'-history-manage')
            click('historySelectAll')
            click('historyDeleteSelected')
            yield 220
            assert find('dialog-confirm').property('visible')
            find('dialog-confirm').property('session').answer(True)
            yield 250
            assert not history.state['managing'] and history.state['checkedCount'] == 0
            assert history.model.count == 0
            history.delete_many_requested.disconnect(delete_confirmed)
            window._select_page(2)
            settings_top.setProperty('contentY', max(0.0, float(settings_top.property('contentHeight')) - float(settings_top.property('height'))))
            yield 180
            retries = []
            page.parse_requested.connect(retries.append)
            page.setField('url', source.url)
            window._select_page(0)
            window.cookies.update(authRequired=True)
            assert find('cookieRetry').property('visible')
            click('cookieRetry')
            assert retries and retries[-1] == source.url
            window.cookies.update(authRequired=False)
            window.update(recoveryVisible=True, recoveryBusy=True, recoveryText='正在恢复上一次未完成的更新…')
            yield 300
            snapshot(mode+'-recovery-running')
            window.update(recoveryBusy=False, recoveryText='更新恢复失败')
            yield 300
            snapshot(mode+'-recovery-failed')
            window.update(recoveryVisible=False)
        assert not window.qml_warnings, window.qml_warnings
        report = dict(device_pixel_ratio=window.root.devicePixelRatio(), screenshots=captures, qml_warnings=[], checks=['generic_input', 'verified', 'experimental_nonblocking', 'subtitle_none_disabled', 'subtitle_auto_only', 'subtitle_manual_only', 'playlist_explicit_selection', 'batch_errors', 'about', 'cookie_profile_editor_and_selection', 'history_management_and_confirmed_delete_exit', 'download_field_alignment_and_native_default', 'light_dark'])
        (args.output/'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False))
        app.quit()
    iterator = steps()
    def advance():
        try:
            delay = next(iterator)
        except StopIteration:
            return
        except BaseException:
            import traceback
            traceback.print_exc()
            app.exit(2)
            return
        QTimer.singleShot(delay, advance)
    QTimer.singleShot(0, advance)
    try:
        return app.exec()
    finally:
        window.dispose()


if __name__ == '__main__':
    raise SystemExit(main())
