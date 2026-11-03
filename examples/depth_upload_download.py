from numpy import load

from phytoworks import PWS

pws = PWS()
uploaded = pws.media.upload_depth(load("depth.npy", allow_pickle=False, mmap_mode="r"), capture="capture-id")
restored, descriptor = pws.media.download_depth(uploaded.media_asset_id)
