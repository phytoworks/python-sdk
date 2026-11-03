from os import environ as e

from phytoworks import PWS

pws, device, duration = PWS(), e["PWS_DEVICE"], int(e["PWS_DURATION"])
topic = next(t["id"] for t in pws.telemetry.topics(device)["topics"] if t["name"] == e["PWS_SENSOR_TOPIC"])
points = pws.telemetry.batch(device, [topic], since="5m")["metrics"].get(topic, {}).get("dataPoints", [])
if points and float(points[-1]["value"]) < float(e["PWS_THRESHOLD"]):
    print(pws.spots.get(e["PWS_SPOT"]).actions.run("pump.timed", {"duration": duration}, device=device).id)
