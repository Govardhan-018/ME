import re

def run(query: str) -> str:
    km = re.search(r'-?\d+(?:\.\d+)?', query.lower())
    if km:
        return f"{float(km.group()) * 0.621371} miles"
    else:
        return "Could not parse a number from your query."