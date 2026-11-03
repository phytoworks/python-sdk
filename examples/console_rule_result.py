from os import environ as e

from phytoworks import PWS

pws, spot = PWS(), e["PWS_SPOT"]
rule = pws.rules.get(spot, e["PWS_RULE"])
print(rule.id, pws.rules.executions(spot, rule.id)[0].status)
