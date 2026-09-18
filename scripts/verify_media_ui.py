"""Offline GUI acceptance for the generic metadata presentation."""
import argparse
from dataclasses import replace
import json
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from yt_downloader.core.models import AppSettings, PlaylistMetadata
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
        assert item is not None, name
        return item
    def snapshot(name):
        assert window.grab().save(str(args.output/(name+'.png')))
        captures.append(name)
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
            page.show_video(replace(source, extractor='OtherExtractor', compatibility='EXPERIMENTAL'))
            yield 300
            assert find('compatibilityHint').property('visible')
            assert find('downloadButton').property('enabled')
            snapshot(mode+'-experimental')
            page.show_video(replace(source, media_type='playlist', formats=(), audio_formats=(), video_only_formats=(), playlist=PlaylistMetadata('collection', '集合')))
            yield 300
            assert not find('downloadButton').property('enabled')
            snapshot(mode+'-playlist-summary')
            window._select_page(3)
            yield 400
            snapshot(mode+'-about')
        assert not window.qml_warnings, window.qml_warnings
        report = dict(screenshots=captures, qml_warnings=[], checks=['generic_input', 'verified', 'experimental_nonblocking', 'playlist_download_disabled', 'about', 'light_dark'])
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
