from os import environ as e

from phytoworks import PWS

spot, device, duration = e["PWS_SPOT"], e["PWS_DEVICE"], int(e["PWS_DURATION"])
run = PWS().spots.get(spot).actions.run("pump.timed", {"duration": duration}, device=device)
print(run.id)
