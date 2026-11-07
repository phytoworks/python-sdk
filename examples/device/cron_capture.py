"""One capture per run, from your own scheduler: one image in one session.

    */30 * * * * python cron_capture.py ~/.config/pws/keys/<agent id>.key /data/capture 4024 3036

Your code moves the camera and writes image.jpg and image_thumb.jpg into the folder before this runs; the SDK
only registers, opens the session, uploads and settles it. A failure after start marks
the session FAILED, so it never stays open. Console shows the device online for five minutes after each run;
schedule it at least every four minutes to keep it online.
Several labelled views in one session (identity_label_keys) need PWS_MEDIA_MULTI_VIEW_WRITE_ENABLED on the Hub.
"""

import sys
from pathlib import Path

from phytoworks.device import Device

key_file, folder, width, height = sys.argv[1], Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
with Device(key_file) as device:
    device.register("camera-1", "Motorized camera")
    session = str(device.create_session("cron capture")["id"])
    device.start(session)
    try:
        image, thumbnail = folder / "image.jpg", folder / "image_thumb.jpg"
        device.upload_image(image, thumbnail=thumbnail, session=session, width=width, height=height)
        device.complete(session)
    except Exception as error:
        device.fail(session, reason=type(error).__name__)
        raise
