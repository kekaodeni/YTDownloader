from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from semver import Version


class UpdateState(str, Enum):
    IDLE = 'IDLE'
    CHECKING = 'CHECKING'
    UP_TO_DATE = 'UP_TO_DATE'
    AVAILABLE = 'AVAILABLE'
    DOWNLOADING = 'DOWNLOADING'
    CANCELLING = 'CANCELLING'
    VERIFYING = 'VERIFYING'
    READY_TO_INSTALL = 'READY_TO_INSTALL'
    PREPARING_EXIT = 'PREPARING_EXIT'
    INSTALLING = 'INSTALLING'
    ROLLING_BACK = 'ROLLING_BACK'
    FAILED = 'FAILED'


class UpdateCapability(str, Enum):
    CHECK_ONLY = 'CHECK_ONLY'
    DOWNLOAD_AND_VERIFY = 'DOWNLOAD_AND_VERIFY'
    AUTO_INSTALL = 'AUTO_INSTALL'


@dataclass(frozen=True, slots=True)
class UpdateRelease:
    version: Version
    tag: str
    manifest_url: str
    signature_url: str
    release_url: str
