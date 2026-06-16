"""
Offline + (optional) live test of the self-extension skill subsystem.

Run from the project root:  python scripts/test_skills.py
The offline portion needs no Ollama; the live portion runs only if Ollama is up.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests

from core.skills import registry, runner, synthesizer

PASS, FAIL = "PASS", "FAIL"
results = []


def check(label, cond):
    results.append((label, bool(cond)))
    print(f"  [{PASS if cond else FAIL}] {label}")


print("\n== 1. static safety check ==")
good = "import math\n\ndef run(query: str) -> str:\n    return str(math.sqrt(16))\n"
bad_net = "import socket\n\ndef run(query):\n    return 'x'\n"
bad_io = "def run(query):\n    return open('x').read()\n"
bad_os = "import os\n\ndef run(query):\n    return os.getcwd()\n"
check("clean compute code passes", synthesizer.static_safety(good)[0] is True)
check("socket rejected", synthesizer.static_safety(bad_net)[0] is False)
check("open() rejected", synthesizer.static_safety(bad_io)[0] is False)
check("os import rejected", synthesizer.static_safety(bad_os)[0] is False)
check("test may import its own skill", synthesizer.static_safety(
    "from foo import run\nassert run('') == ''\n", extra_allowed=frozenset({"foo"}))[0] is True)


print("\n== 2. validation harness (no Ollama) ==")
skill_code = (
    "import re\n\n"
    "def run(query: str) -> str:\n"
    "    m = re.search(r'-?\\d+(?:\\.\\d+)?', query)\n"
    "    if not m:\n"
    "        return 'Give me a Celsius value, e.g. \"30C to F\".'\n"
    "    c = float(m.group())\n"
    "    return f'{c}C = {c * 9 / 5 + 32:g}F'\n"
)
good_test = (
    "from celsius_to_fahrenheit import run\n"
    "assert '32' in run('0 C to F')\n"
    "assert '212' in run('100C')\n"
    "print('ALL TESTS PASSED')\n"
)
bad_test = (
    "from celsius_to_fahrenheit import run\n"
    "assert '999' in run('0 C')\n"
    "print('ALL TESTS PASSED')\n"
)
v_ok = synthesizer._validate("celsius_to_fahrenheit", skill_code, good_test)
v_bad = synthesizer._validate("celsius_to_fahrenheit", skill_code, bad_test)
check("valid skill+test passes", v_ok.get("passed") is True)
check("wrong-assertion test fails", v_bad.get("passed") is False)


print("\n== 3. stage -> activate -> run via runner ==")
registry.discard_staged("celsius_to_fahrenheit")
registry.remove_skill("celsius_to_fahrenheit")
registry.stage("celsius_to_fahrenheit", skill_code, good_test,
               {"description": "Convert Celsius to Fahrenheit.",
                "examples": ["convert 30C to F"], "validation": v_ok})
staged_run = runner.run_staged("celsius_to_fahrenheit", "what is 100C in F")
check("staged skill runs", staged_run["ok"] and "212" in staged_run["answer"])
entry = synthesizer.approve_skill("celsius_to_fahrenheit")
check("approved into registry", registry.get_skill("celsius_to_fahrenheit") is not None)
check("staging cleared after approve", registry.get_staged("celsius_to_fahrenheit") is None)
active_run = runner.run_skill("celsius_to_fahrenheit", "0 C to F please")
check("active skill runs", active_run["ok"] and "32" in active_run["answer"])
# cleanup the test skill so it doesn't linger in the registry
registry.remove_skill("celsius_to_fahrenheit")
check("removed cleanly", registry.get_skill("celsius_to_fahrenheit") is None)


print("\n== 4. live synthesis (only if Ollama is up) ==")
ollama_up = False
try:
    requests.get(f"{synthesizer.OLLAMA_BASE_URL}/api/tags", timeout=2)
    ollama_up = True
except Exception:
    pass

if not ollama_up:
    print("  [SKIP] Ollama not reachable — skipping live synthesis test.")
else:
    print(f"  Ollama up. Synthesizing a real skill with {synthesizer.MODEL} ...")
    need = "convert a number of kilometers into miles"
    prop = synthesizer.propose_skill(need)
    check("live propose_skill passed validation", prop.get("passed") is True)
    if prop.get("passed"):
        nm = prop["name"]
        print(f"    -> learned skill: {nm} ({prop['description']})")
        r = runner.run_staged(nm, "how far is 10 km in miles")
        print(f"    -> run('10 km'): {r['answer']!r}")
        check("live skill produces an answer", r["ok"] and any(ch.isdigit() for ch in r["answer"]))
        registry.discard_staged(nm)  # don't leave the test skill staged


print("\n== summary ==")
n_pass = sum(1 for _, ok in results if ok)
print(f"  {n_pass}/{len(results)} checks passed")
sys.exit(0 if n_pass == len(results) else 1)
