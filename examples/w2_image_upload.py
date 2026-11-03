from os import environ as env

from phytoworks import PWS

width, height = int(env["PWS_IMAGE_WIDTH"]), int(env["PWS_IMAGE_HEIGHT"])
image, thumbnail, capture = (env[f"PWS_{key}"] for key in ("IMAGE_FILE", "THUMBNAIL_FILE", "CAPTURE_SESSION"))
print(PWS().media.upload(image, thumbnail=thumbnail, capture=capture, width=width, height=height).media_asset_id)
