import json
import subprocess
import sys
from pathlib import Path

SRC = str(Path(__file__).parent / "int" / "keel" / "src")
code_hub_first = (
    "import sys; sys.path.insert(0, %r); "
    "import keel.backend_hub as h; "
    "print(len(h.function_schemas()), len(h.describe()['contracts'])); "
    "from keel import capabilities; "
    "print('schemas' in capabilities.get('backend.invoke').input_schema, "
    "len(capabilities.get('backend.describe').input_schema.get('x-module-schemas', {})))"
) % SRC
code_cap_first = (
    "import sys; sys.path.insert(0, %r); "
    "from keel import capabilities; "
    "print('schemas0' in capabilities.get('backend.invoke').input_schema); "
    "import keel.backend_hub as h; "
    "print(len(h.function_schemas()), "
    "'x-function-schemas' in capabilities.get('backend.invoke').input_schema)"
) % SRC
for label, code in (("hub-first", code_hub_first), ("cap-first", code_cap_first)):
    p = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    print(label, "rc=", p.returncode, "out=", p.stdout.strip(), "err=", p.stderr.strip()[:300])

sys.path.insert(0, SRC)
from keel import backend_hub as h
from keel import backend_contracts as c

# Check envelope coercion safety: a caller-controlled envelope cannot name an
# arbitrary class because coercion is annotation-directed.
print("sample schema:", json.dumps(h.function_schema("e3_backend", "check_route"))[:300])
for bad in (
    {"type": "os.system", "fields": {"x": 1}},
    {"type": "subprocess.Popen", "fields": {"args": ["calc.exe"]}},
):
    try:
        out = c.coerce_value(bad, str)
        print("coerce to str:", out)
    except Exception as exc:
        print("coerce error:", type(exc).__name__, exc)

# ModelId conversion probes
print("from_string:", c.from_string("anthropic/claude#fast").as_dict())
print("to_route discovery:", end=" ")
try:
    print(c.to_route(c.from_discovery("claude-sonnet")))
except Exception as exc:
    print(type(exc).__name__, exc)
print("normalize:", c.normalize_model_ids({"type": "ModelRoute", "fields": {"provider": "p", "model": "m", "extra": {"model": "x", "provider": "q"}}}))
