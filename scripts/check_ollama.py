import requests

try:
    r = requests.get('http://localhost:11434/api/tags', timeout=5)
    data = r.json()
    models = data.get('models', [])
    print("Ollama is RUNNING")
    print(f"Models installed: {len(models)}")
    for m in models:
        name = m.get('name', '?')
        size_gb = round(m.get('size', 0) / 1e9, 1)
        print(f"  - {name}  ({size_gb} GB)")
    if not models:
        print("  (no models pulled yet)")
except Exception as e:
    print(f"Ollama NOT reachable: {e}")
