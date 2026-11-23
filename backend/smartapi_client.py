from SmartApi import SmartConnect
import pyotp

from config import (
    ANGEL_API_KEY,
    ANGEL_CLIENT_CODE,
    ANGEL_PASSWORD,
    ANGEL_TOTP_SECRET,
)


def connect_angel():
    if not all([
        ANGEL_API_KEY,
        ANGEL_CLIENT_CODE,
        ANGEL_PASSWORD,
        ANGEL_TOTP_SECRET,
    ]):
        raise ValueError("Angel One credentials are not configured")

    smart_api = SmartConnect(api_key=ANGEL_API_KEY)

    totp = pyotp.TOTP(ANGEL_TOTP_SECRET).now()

    session = smart_api.generateSession(
        ANGEL_CLIENT_CODE,
        ANGEL_PASSWORD,
        totp
    )

    if not session or not session.get("status"):
        raise RuntimeError("Angel One login failed")

    return smart_api
