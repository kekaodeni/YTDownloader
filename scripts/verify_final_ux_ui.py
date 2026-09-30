"""Render and inspect the real Qt Quick settings and viewport at a requested DPI."""
from pathlib import Path
from dataclasses import replace
import argparse,json,os,sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QPointF,QTimer
from PySide6.QtWidgets import QApplication
from yt_downloader.core.models import DownloadRequest
from yt_downloader.services.settings_service import SettingsService
from yt_downloader.services.cookie_service import CookieProfileStore
from yt_downloader.ui.quick_window import MainWindow
from scripts.verify_i18n_features_ui import find,wait,reveal
from scripts.verify_quick_ui import sample_video

def descendants(item):
 for child in item.childItems():
  yield child
  yield from descendants(child)

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path);parser.add_argument('--expected-dpr',type=float,required=True);args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
 app=QApplication([]);app.setQuitOnLastWindowClosed(False)
 data=Path(os.environ['LOCALAPPDATA'])/'YTDownloader';settings=SettingsService(data/'settings.json',default_download_directory=args.output).load()
 w=MainWindow(replace(settings,language='zh-CN',auto_check_updates=False),ytdlp_version=__import__('yt_dlp.version',fromlist=['__version__']).__version__,ffmpeg_description='');w.root.resize(1200,950);w.show();w.root.raise_();w.root.requestActivate();wait(500)
 w.cookies.set_profiles(CookieProfileStore(data/'cookie-profiles.json').load())
 # Acknowledge the real autosave signal in memory; do not write user settings.
 w.settings_page.save_requested.connect(w.settings_page.mark_saved)
 assert abs(w.root.devicePixelRatio()-args.expected_dpr)<.02, w.root.devicePixelRatio()
 snapshots=[];cases=[]
 def snap(name):
  p=args.output/(name+'.png');assert w.grab().save(str(p));snapshots.append(str(p))
 def inspect_settings():
  page=find(w,'settingsPage');nav=find(w,'settingsNavigation');scroll=find(w,'settingsScroll')
  for item in descendants(page):
   if not item.isVisible():continue
   if item.objectName() in ('settingRowLabel','settingRowDescription'):
    assert item.property('contentHeight')<=item.height()+1,(item.property('text'),item.width(),item.height(),item.property('contentHeight'))
   if item.objectName()=='settingsCategory-'+str(w.settings_page.state['category']):
    p=item.mapToItem(scroll,QPointF(0,0));assert p.x()>=-1 and p.x()+item.width()<=scroll.width()+1,(item.objectName(),p.x(),item.width(),scroll.width())
  before=nav.mapToScene(QPointF(0,0));scroll.setProperty('contentY',max(0,scroll.property('contentHeight')-scroll.height()));wait(60);assert nav.mapToScene(QPointF(0,0))==before;scroll.setProperty('contentY',0);wait(60)
 for theme in ('light','dark'):
  w.theme.set_mode(theme);w._select_page(2);wait(400)
  for category,name in enumerate(('appearance','download','cookies','network','updates','tools')):
   w.settings_page.selectCategory(category);find(w,'settingsScroll').setProperty('contentY',0);wait(280);inspect_settings();snap('settings-'+theme+'-'+name)
  for locale in ('ru-RU','es-ES','pt-BR'):
   w.settings_page.setSetting('language',locale)
   assert w.i18n.currentLocale==locale
   for width in (1200,600):
    w.root.resize(width,900)
    for category in range(6):
     w.settings_page.selectCategory(category);wait(240);inspect_settings();cases.append([theme,locale,width,category])
    snap('settings-'+theme+'-'+locale+'-'+str(width))
  w.settings_page.setSetting('language','zh-CN');w.root.resize(1200,950)
  w._select_page(0);page=w.download_page;media=sample_video();page.show_video(media)
  # More rows provide a genuine middle viewport after collapsing advanced options.
  for i in range(3):page.add_task(DownloadRequest('anchor-'+str(i),media,media.formats[0],args.output,'viewport'))
  wait(400)
  # Complete the normal page-entry fade before measuring layout mutations.
  # grabWindow also drives frames when a desktop window is occluded.
  for _ in range(6):
   w.grab();wait(80)
   if find(w,'videoPanel').opacity()==1:break
  assert find(w,'videoPanel').opacity()==1
  view=find(w,'taskList')
  for field in ('advancedExpanded','clipEnabled'):
   for position in ('top','middle','bottom'):
    for enabled in (True,False):
     page.setAdvancedToggle('advancedExpanded',field=='clipEnabled' or not enabled);page.setAdvancedToggle('clipEnabled',not enabled if field=='clipEnabled' else False);wait(100)
     item=find(w,'advancedOptionsToggle' if field=='advancedExpanded' else 'clipEnabled')
     maximum=max(0,view.property('contentHeight')-view.height());origin=view.property('originY')
     if position=='top':view.setProperty('contentY',origin)
     elif position=='middle':reveal(w,item.objectName(),100)
     else:view.setProperty('contentY',origin+maximum)
     wait(80);maximum=max(0,view.property('contentHeight')-view.height());gap=maximum-(view.property('contentY')-view.property('originY'));bottom=maximum>0 and gap<=6;anchor=item.mapToScene(QPointF(0,0)).y();observations=[]
     def frame():
      assert not w.grab().isNull();m=max(0,view.property('contentHeight')-view.height());observations.append((m-(view.property('contentY')-view.property('originY')),item.mapToScene(QPointF(0,0)).y(),find(w,'videoPanel').opacity()))
     timer=QTimer();timer.timeout.connect(frame);timer.start(5)
     # Offscreen top/bottom actions are driven through the same QML viewport
     # preparation entry point, without synthetic clicks outside the window.
     from PySide6.QtCore import QMetaObject,Q_ARG
     if field=='advancedExpanded':assert QMetaObject.invokeMethod(item,'clicked')
     else:assert QMetaObject.invokeMethod(item,'changed',Q_ARG(bool,enabled))
     assert page.state[field]==enabled
     wait(180);timer.stop()
     assert observations
     if bottom:assert all(abs(a-gap)<2 for a,b,c in observations),(theme,field,position,enabled,observations)
     else:assert all(abs(b-anchor)<2 for a,b,c in observations),(theme,field,position,enabled,observations)
     assert all(c==1 for a,b,c in observations),(theme,field,position,enabled,observations)
     cases.append([theme,field,position,enabled,len(observations)])
 assert not w.qml_warnings,w.qml_warnings
 report={'dpr':w.root.devicePixelRatio(),'cases':cases,'screenshots':snapshots,'qml_warnings':w.qml_warnings,'ffmpegVersion':w.settings_page.state['ffmpegVersion']}
 (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 w.update(allowClose=True);w.close();w.dispose();print('FINAL UX PASS',args.expected_dpr,len(cases))
if __name__=='__main__':main()
