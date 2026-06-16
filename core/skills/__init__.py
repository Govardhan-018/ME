"""
JARVIS self-extension: the skill subsystem.

When the orchestrator hits a capability gap, it can write, test, and (after
approval) register a new *skill* for itself — a small, pure-Python module that
covers the gap so the gap never recurs.

  registry.py    persistence: active registry + staging area, name/path rules
  synthesizer.py the "synthesize + validate" stages (write code+test, run it)
  runner.py      execute a registered/staged skill module

A skill is a module exposing a single entry point:  def run(query: str) -> str
"""
