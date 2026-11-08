"""Batch C: each stockbee bundle drives its own generated client in isolation (#495).

Every standalone bundle vendors a generated ``fmp_client.py`` under the same file
name. The adapters load their sibling by path under a skill-unique module name,
so a fresh interpreter importing one bundle must route HTTP through that bundle's
own client, stay on /stable, and never fall back to /api/v3.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TARGETS = {
    "stockbee-20pct-study": "run_20pct_study",
    "stockbee-episodic-pivot-analyzer": "analyze_ep",
    "stockbee-exhaustion-hammer-screener": "screen_exhaustion_hammer",
    "stockbee-momentum-burst-screener": "screen_momentum_burst",
    "stockbee-setup-fluency-trainer": "build_model_book",
}

SCENARIO = r"""
import importlib.util
import sys
from pathlib import Path

scripts_dir = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("bundle_main", scripts_dir / f"{sys.argv[2]}.py")
module = importlib.util.module_from_spec(spec)
sys.modules["bundle_main"] = module
spec.loader.exec_module(module)


class Response:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.text = ""

    def json(self):
        return self._payload


class Session:
    def __init__(self):
        self.headers = {}
        self.urls = []
        self.answers = [Response(402, None), Response(200, [])]

    def get(self, url, params=None, timeout=None):
        self.urls.append(url)
        return self.answers.pop(0) if self.answers else Response(200, [])


client = module.FMPClient(api_key="dummy-key", max_api_calls=10)  # pragma: allowlist secret
shared = sys.modules[module._SHARED_FMP_MODULE]
assert Path(shared.__file__).resolve() == (scripts_dir / "fmp_client.py").resolve(), shared.__file__
assert "fmp_client" not in sys.modules, "bundle must not import the bare fmp_client name"
session = Session()
client.session = session
client.get_historical_prices("AAA", days=5)
client.get_historical_prices("BBB", days=5)
assert session.urls, "no request reached the fake transport"
assert all("/stable/" in url for url in session.urls), session.urls
assert not any("/api/v3/" in url for url in session.urls), session.urls
print("BATCH_C_TRANSPORT_OK")
"""


@pytest.mark.parametrize("skill,module_name", TARGETS.items())
def test_bundle_uses_its_own_stable_only_client(skill: str, module_name: str):
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            SCENARIO,
            str(ROOT / "skills" / skill / "scripts"),
            module_name,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "BATCH_C_TRANSPORT_OK" in result.stdout
