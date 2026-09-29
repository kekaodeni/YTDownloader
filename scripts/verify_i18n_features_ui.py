"""Capture offline Qt Quick language, advanced-download, and actionable-error acceptance views."""
from __future__ import annotations
import argparse, json
from pathlib import Path
from dataclasses import replace
from PySide6.QtCore import QObject, QEventLoop, QTimer, QPointF
from PySide6.QtWidgets import QApplication
from yt_downloader.core.errors import AppError
from yt_downloader.core.models import AppSettings
from yt_downloader.ui.quick_window import MainWindow
from yt_downloader.ui.quick_dialogs import ErrorSession
try:
    from verify_quick_ui import sample_video
except ModuleNotFoundError:
    from scripts.verify_quick_ui import sample_video


def wait(ms=350):
    loop=QEventLoop(); QTimer.singleShot(ms, loop.quit); loop.exec()


def find(window, name):
    item=window.root.findChild(QObject,name)
    if item is None:
        pending=[window.root.contentItem()]
        while pending:
            obj=pending.pop()
            if obj.objectName()==name: return obj
            pending.extend(obj.childItems())
    if item is None: raise RuntimeError(f'Missing QML item: {name}')
    return item


def reveal(window, name, margin=20):
    view=find(window,'taskList'); item=find(window,name)
    origin=float(view.property('originY'))
    top=float(item.mapToItem(view,QPointF(0,0)).y())
    maximum=max(origin,origin+float(view.property('contentHeight'))-view.height())
    view.setProperty('contentY',min(maximum,max(origin,float(view.property('contentY'))+top-margin)))
    wait(220)


def assert_controls_inside(window,names):
    for name in names:
        item=find(window,name)
        bounds=item.mapToItem(window.root.contentItem(),QPointF(0,0))
        if item.width()<=0 or item.height()<=0 or bounds.x() < -1 or bounds.y() < -1 or bounds.x()+item.width()>window.root.width()+1 or bounds.y()+item.height()>window.root.height()+1:
            raise RuntimeError(f'Advanced control clipped or outside the viewport: {name} at ({bounds.x():.1f}, {bounds.y():.1f}) size ({item.width():.1f}, {item.height():.1f}), root {window.root.width():.1f}x{window.root.height():.1f}')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--expected-dpr',type=float)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    app=QApplication.instance() or QApplication([]); app.setQuitOnLastWindowClosed(False)
    window=MainWindow(AppSettings(auto_check_updates=False),ytdlp_version='offline',ffmpeg_description='')
    window.root.resize(1140,900); window.show(); window.root.raise_(); window.root.requestActivate(); wait(500)
    dpr=float(window.root.devicePixelRatio())
    if args.expected_dpr is not None and abs(dpr-args.expected_dpr)>.02:
        raise RuntimeError(f'Expected devicePixelRatio {args.expected_dpr}, got {dpr}')
    captures=[]
    def snap(name):
        path=args.output/(name+'.png')
        if not window.grab().save(str(path)): raise RuntimeError(f'Could not save {path}')
        captures.append(str(path))
    window.theme.set_mode('light'); window.settings_page.setSetting('language','zh-CN'); window._select_page(2); wait()
    snap('settings-language-zh-CN-light')
    window.theme.set_mode('dark'); window.settings_page.setSetting('language','en-US'); window._select_page(2); wait()
    snap('settings-en-US-dark')
    media=sample_video()
    media=replace(media,title='어려워? 어렵냐고!',extractor_key='Youtube')
    page=window.download_page
    page.show_video(media); window._select_page(0); window.i18n.setLanguage('en-US'); wait()
    if page.state['embedThumbnail'] or page.state['embedMetadata'] or page.state['embedChapters'] or page.state['sponsorblockMark'] or page.state['remuxContainer']:
        raise RuntimeError('Fresh download defaults must leave post-processing disabled and preserve the original format')
    reveal(window,'advancedOptionsToggle'); wait()
    window.theme.set_mode('light'); wait(); snap('advanced-collapsed-light')
    window.theme.set_mode('dark'); wait(); snap('advanced-collapsed-dark')
    page.setAdvancedToggle('advancedExpanded',True); wait()
    reveal(window,'embedThumbnail'); wait()
    assert_controls_inside(window,('embedThumbnail','embedMetadata','embedChapters','remuxContainer'))
    window.theme.set_mode('light'); wait(); snap('advanced-expanded-defaults-off-light')
    window.theme.set_mode('dark'); wait(); snap('advanced-expanded-defaults-off-dark')
    page.setAdvancedToggle('clipEnabled',True)
    page.setAdvancedField('clipStart','03:15')
    page.setAdvancedField('clipEnd','05:40')
    wait(220)
    reveal(window,'clipStart'); wait()
    assert_controls_inside(window,('clipEnabled','clipStart','clipEnd'))
    window.theme.set_mode('light'); wait(); snap('clip-enabled-light')
    window.theme.set_mode('dark'); wait(); snap('clip-enabled-dark')
    page.setAdvancedToggle('clipEnabled',False)
    wait(220)
    page.setAdvancedToggle('embedThumbnail',True)
    page.setAdvancedToggle('embedMetadata',False)
    page.setAdvancedToggle('embedChapters',True)
    page.setAdvancedField('remuxContainer','mp4')
    page.setAdvancedToggle('sponsorblockMark',True); wait()
    reveal(window,'sponsorblockMark'); wait()
    assert_controls_inside(window,('embedThumbnail','embedMetadata','embedChapters','remuxContainer','sponsorblockMark'))
    window.theme.set_mode('light'); wait(); snap('postprocess-mixed-light')
    window.theme.set_mode('dark'); wait(); snap('postprocess-mixed-dark')
    page.setAdvancedToggle('clipEnabled',True); page.setAdvancedField('clipStart','03:15'); page.setAdvancedField('clipEnd','05:40')
    for locale in ('en-US','ru-RU'):
        window.i18n.setLanguage(locale); wait()
        wait(220)
        reveal(window,'advancedOptionsToggle'); wait()
        assert_controls_inside(window,('advancedOptionsToggle',))
        window.theme.set_mode('light' if locale == 'en-US' else 'dark'); wait()
        snap(f'advanced-header-longtext-{locale}-'+('light' if locale == 'en-US' else 'dark'))
        reveal(window,'clipStart'); wait()
        assert_controls_inside(window,('clipEnabled','clipStart','clipEnd','embedThumbnail','embedMetadata','embedChapters','remuxContainer','sponsorblockMark'))
        window.theme.set_mode('light' if locale == 'en-US' else 'dark'); wait()
        snap(f'advanced-longtext-{locale}-'+('light' if locale == 'en-US' else 'dark'))
    entries=[
      ('cookie-required','COOKIE_REQUIRED','error.cookie_required.title','error.cookie_required.body',('OPEN_COOKIE_MANAGER','REPARSE')),
      ('format-stale','FORMAT_UNAVAILABLE','error.format_unavailable.title','error.format_unavailable.body',('REPARSE',)),
      ('extractor-update','TEMPORARY_EXTRACTOR_ERROR','error.temporary_extractor.title','error.temporary_extractor.body',('RETRY','CHECK_APP_UPDATE')),
    ]
    for name,code,title,body,actions in entries:
        window.i18n.setLanguage('en-US'); window.theme.set_mode('light'); wait()
        error=AppError(code,'source placeholder','raw stderr must remain raw',title_message_id=title,body_message_id=body,recommended_actions=actions)
        callbacks={item:(lambda:None) for item in actions}
        dialog=ErrorSession(error,'redacted report',window,title_text='Error',actions=actions,action_callbacks=callbacks)
        dialog.show(); wait(); snap('error-'+name+'-light'); dialog.reject(); wait(200)
        window.theme.set_mode('dark'); dialog=ErrorSession(error,'redacted report',window,title_text='Error',actions=actions,action_callbacks=callbacks)
        dialog.show(); wait(); snap('error-'+name+'-dark'); dialog.reject(); wait(200)
    window.root.resize(800,700); window.theme.set_mode('light'); window._select_page(2)
    for locale in ('ru-RU','es-ES','pt-BR'):
        window.settings_page.setSetting('language',locale); wait()
        for name in ('languageField','profileExplainer','defaultDirectory'):
            item=find(window,name)
            bounds=item.mapToItem(window.root.contentItem(),QPointF(0,0))
            if item.width()<=0 or item.height()<=0 or bounds.x() < -1 or bounds.x()+item.width()>window.root.width()+1:
                raise RuntimeError(f'Long localized Settings control is clipped: {locale}:{name}')
        for item in window.root.findChildren(QObject):
            value=item.property('text')
            if isinstance(value,str) and '[missing:' in value:
                raise RuntimeError(f'Missing localized QML text in {locale}: {value}')
            visible = getattr(item, 'isVisible', None)
            if (locale != 'zh-CN' and isinstance(value,str) and callable(visible) and visible()
                    and any('\u3400' <= char <= '\u9fff' for char in value)):
                raise RuntimeError(f'Mixed-language CJK UI text in {locale}: {value}')
    report={'device_pixel_ratio':dpr,'screenshots':captures,'qml_warnings':list(window.qml_warnings)}
    (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    window.update(allowClose=True); window.close(); window.dispose(); app.processEvents()
    if report['qml_warnings']: raise RuntimeError('QML warnings: '+repr(report['qml_warnings']))
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
