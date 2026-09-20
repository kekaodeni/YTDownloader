"""Offline GUI acceptance for the generic metadata presentation."""
import argparse
from dataclasses import replace
import json
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from yt_downloader.core.models import AppSettings, PlaylistMetadata, PlaylistEntry, SubtitleTrack, CookieProfile, DownloadRequest, DownloadResult, TaskStatus
from yt_downloader.ui.quick_window import MainWindow
from verify_quick_ui import sample_video


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = MainWindow(AppSettings(auto_check_updates=False), ytdlp_version='offline', ffmpeg_description='offline')
    window.show()
    window.root.raise_()
    window.root.requestActivate()
    window.root.resize(1000, 760)
    page = window.download_page
    source = replace(sample_video(), video_id='opaque/跨站-ID', extractor='Vimeo', extractor_key='Vimeo',
                     title='通用媒体解析 · Generic media', url='https://vimeo.com/76979871',
                     original_url='https://vimeo.com/76979871', webpage_url='https://vimeo.com/76979871',
                     compatibility='VERIFIED')
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
            assert not find('compatibilityHint').property('visible')
            snapshot(mode+'-verified')
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
            window.cookies.set_profiles((CookieProfile('fixture', 'Fixture / Firefox', 'browser', browser='firefox'),))
            window.cookies.selectProfile(1)
            yield 300
            snapshot(mode+'-cookie-browser')
            window.cookies.edit('source', 'file')
            yield 300
            snapshot(mode+'-cookie-file')
            window.cookies.selectProfile(0)
            window.update(recoveryVisible=True, recoveryBusy=True, recoveryText='正在恢复上一次未完成的更新…')
            yield 300
            snapshot(mode+'-recovery-running')
            window.update(recoveryBusy=False, recoveryText='更新恢复失败')
            yield 300
            snapshot(mode+'-recovery-failed')
            window.update(recoveryVisible=False)
        assert not window.qml_warnings, window.qml_warnings
        report = dict(screenshots=captures, qml_warnings=[], checks=['generic_input', 'verified', 'experimental_nonblocking', 'playlist_explicit_selection', 'batch_errors', 'about', 'light_dark'])
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
