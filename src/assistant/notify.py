import shutil
import subprocess

NOTIFY_SEND: str = "notify-send"


def notification_available() -> bool:
    return shutil.which(NOTIFY_SEND) is not None


def send_notification(title: str, body: str) -> bool:
    if shutil.which(NOTIFY_SEND) is None:
        return False
    try:
        subprocess.run([NOTIFY_SEND, title, body], check=False)
        return True
    except OSError:
        return False
