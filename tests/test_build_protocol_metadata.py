"""Exercise the actual PowerShell metadata block for both package layouts."""
import json
from pathlib import Path
import subprocess

import pytest

from yt_downloader.updates.archive import SafePackageExtractor


@pytest.mark.parametrize('version,layout,protocols', [
    ('0.4.2', 'legacy-root', [1, 2]),
    ('0.5.0', 'internal-v1', [2]),
])
def test_build_script_serializes_protocol_capability_as_array(version, layout, protocols):
    script=(Path(__file__).resolve().parents[1]/'scripts/build.ps1').read_text(encoding='utf-8')
    block='$BuildInfo = [ordered]@{' + script.split('$BuildInfo = [ordered]@{',1)[1].split('\n}',1)[0] + '\n}'
    command=(f"$Version='{version}'; $HelperLayout='{layout}'; $ValidationOnly=$false; "
             "$SourceCommit='fixture'; $ToolVersions=@{}; " + block + '\n$BuildInfo | ConvertTo-Json -Depth 8')
    result=subprocess.run(['powershell','-NoProfile','-Command',command],check=True,capture_output=True,text=True)
    info=json.loads(result.stdout)
    assert info['supported_update_protocols']==protocols
    assert SafePackageExtractor.layout(info)==layout
