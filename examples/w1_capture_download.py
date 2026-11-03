from phytoworks import PWS

pws = PWS()
session = pws.captures.latest()
print(session.download(dest="./captures") if session else "no capture session yet")
