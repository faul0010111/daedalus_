# Tests

```bash
pytest                          # 44 tests over the cognitive core
npm install jsdom               # once, for the console test
node tests/console_render.js    # renders every console tab against a captured API state
```

`console_render.js` reads `/tmp/state.json` by default; capture a fresh one with:

```python
from fastapi.testclient import TestClient
from daedalus.api.server import create_app
import json
c = TestClient(create_app())
c.post("/api/control/step", json={"ticks": 500})
json.dump(c.get("/api/state").json(), open("/tmp/state.json", "w"))
```

The tests assert architectural properties rather than scores: evidence
accumulation, exclusivity constraints, contradiction thresholds, plan relaxation
revealing blockers, goal emergence and deduplication, attention responding to
drives, adaptation refusing locally-rewarding changes, unit lifecycle, determinism
under a fixed seed, and snapshot round-trips.
