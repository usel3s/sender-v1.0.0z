import random
from dataclasses import dataclass


@dataclass
class DeviceFingerprint:
    device_model: str
    system_version: str
    app_version: str
    lang_code: str


ANDROID_DEVICES = [
    ("Samsung SM-G991B", "SDK 33", "10.14.5", "ru"),
    ("Xiaomi 2201116SG", "SDK 31", "10.12.0", "ru"),
    ("Google Pixel 7", "SDK 34", "10.14.5", "en"),
    ("OnePlus LE2123", "SDK 33", "10.13.1", "ru"),
    ("Huawei ELS-NX9", "SDK 29", "10.11.0", "ru"),
]


def generate_fingerprint() -> DeviceFingerprint:
    model, system, app, lang = random.choice(ANDROID_DEVICES)
    return DeviceFingerprint(
        device_model=model,
        system_version=system,
        app_version=app,
        lang_code=lang,
    )


def client_kwargs_from_fingerprint(
    api_id: int,
    api_hash: str,
    fingerprint: DeviceFingerprint,
    phone_number: str | None = None,
    proxy: dict | None = None,
    ipv6: bool = False,
) -> dict:
    kwargs = {
        "api_id": api_id,
        "api_hash": api_hash,
        "device_model": fingerprint.device_model,
        "system_version": fingerprint.system_version,
        "app_version": fingerprint.app_version,
        "lang_code": fingerprint.lang_code,
        "ipv6": ipv6,
    }
    if phone_number:
        kwargs["phone_number"] = phone_number
    if proxy:
        kwargs["proxy"] = proxy
    return kwargs
