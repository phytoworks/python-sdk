from phytoworks import PWS


def upload(client: PWS, *args, **metadata):
    return client.media.upload_registered_multispectral(
        *args, path="camera-metadata", radiometric_level="reflectance", **metadata
    )
