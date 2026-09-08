"""Temporarily test a supported refresh rate, always restoring the original mode."""
import argparse
import ctypes
from ctypes import wintypes as w
import subprocess
import sys
from pathlib import Path

class Point(ctypes.Structure):
    _fields_=[('x',w.LONG),('y',w.LONG)]

class Mode(ctypes.Structure):
    _fields_=[('name',w.WCHAR*32),('spec',w.WORD),('driver',w.WORD),('size',w.WORD),('extra',w.WORD),
              ('fields',w.DWORD),('position',Point),('orientation',w.DWORD),('fixed',w.DWORD),
              ('color',w.SHORT),('duplex',w.SHORT),('yres',w.SHORT),('tt',w.SHORT),('collate',w.SHORT),
              ('form',w.WCHAR*32),('logpixels',w.WORD),('bpp',w.DWORD),('width',w.DWORD),('height',w.DWORD),
              ('flags',w.DWORD),('freq',w.DWORD),('icmMethod',w.DWORD),('icmIntent',w.DWORD),('media',w.DWORD),
              ('dither',w.DWORD),('res1',w.DWORD),('res2',w.DWORD),('panWidth',w.DWORD),('panHeight',w.DWORD)]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--hz',type=int,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    user=ctypes.windll.user32
    original=Mode();original.size=ctypes.sizeof(Mode)
    if not user.EnumDisplaySettingsW(None,-1,ctypes.byref(original)):raise RuntimeError('Cannot read current mode')
    index=0;target=None
    while True:
        mode=Mode();mode.size=ctypes.sizeof(Mode)
        if not user.EnumDisplaySettingsW(None,index,ctypes.byref(mode)):break
        if (mode.width,mode.height,mode.bpp,mode.freq)==(original.width,original.height,original.bpp,args.hz):
            target=mode;break
        index+=1
    if target is None:raise RuntimeError('Requested refresh is not a supported mode')
    if user.ChangeDisplaySettingsExW(None,ctypes.byref(target),None,2,None)!=0:raise RuntimeError('Driver rejected test mode')
    print(f'Testing {args.hz} Hz; original {original.freq} Hz will be restored',flush=True)
    try:
        if user.ChangeDisplaySettingsExW(None,ctypes.byref(target),None,4,None)!=0:raise RuntimeError('Cannot set temporary mode')
        result=subprocess.run([sys.executable,str(Path(__file__).with_name('verify_quick_ui.py')),'--output',str(args.output),'--motion-seconds','17'],timeout=90)
        return result.returncode
    finally:
        status=user.ChangeDisplaySettingsExW(None,ctypes.byref(original),None,4,None)
        restored=Mode();restored.size=ctypes.sizeof(Mode)
        user.EnumDisplaySettingsW(None,-1,ctypes.byref(restored))
        print(f'Restored {restored.freq} Hz (status {status})',flush=True)
        if status!=0 or restored.freq!=original.freq:raise RuntimeError('Display restoration failed')

if __name__=='__main__':raise SystemExit(main())
