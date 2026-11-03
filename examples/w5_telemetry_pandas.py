from os import environ as e

import pandas as pd

from phytoworks import PWS

history = PWS().telemetry.query(e["PWS_DEVICE"], e["PWS_TOPIC"], since=e.get("PWS_SINCE", "24h"))
print(pd.DataFrame([point for metric in history["metrics"] for point in metric["dataPoints"]]))
