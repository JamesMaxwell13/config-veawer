from __future__ import annotations

from ..models import DevicePlatformProfile


class TerminalBootstrapPolicy:
    @staticmethod
    def enter_config_mode(profile: DevicePlatformProfile) -> list[str]:
        if profile.vendor == DevicePlatformProfile.VENDOR_CISCO:
            return ["terminal length 0", "configure terminal"]
        if profile.vendor == DevicePlatformProfile.VENDOR_DLINK:
            return ["config"]
        return []

    @staticmethod
    def leave_config_mode(profile: DevicePlatformProfile) -> list[str]:
        if profile.vendor == DevicePlatformProfile.VENDOR_CISCO:
            return ["end"]
        if profile.vendor == DevicePlatformProfile.VENDOR_DLINK:
            return ["exit"]
        return []
