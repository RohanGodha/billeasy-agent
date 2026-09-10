"""Security regressions for the shared-password gate.

These cover the three issues found when the documentation was generated from the code
rather than from the README — see WRITEUP.md. They are cheap to break by accident, so
they get a test rather than only a paragraph.
"""
from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from fastapi.testclient import TestClient

    from app.auth import throttle
    from app.db.sqlite_engine import bootstrap
    from app.main import app

    bootstrap()
    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        print(f"  [{'ok' if cond else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")
        if not cond:
            failures.append(name)

    client = TestClient(app)

    # --- 1. A credential must not be accepted from the query string ------------
    # Query strings land in proxy logs, browser history and Referer headers.
    throttle.reset("testclient")
    r = client.get("/meta/capabilities", params={"token": "shared"})
    check("query-param token is rejected", r.status_code == 401, f"got {r.status_code}")

    r = client.get("/meta/capabilities", headers={"X-Access-Token": "shared"})
    check("header token is accepted", r.status_code == 200, f"got {r.status_code}")

    r = client.get("/meta/capabilities")
    check("no token is rejected", r.status_code == 401, f"got {r.status_code}")

    # --- 2. Failed logins are throttled --------------------------------------
    # Constant-time comparison does nothing against someone guessing at network speed.
    throttle.reset("testclient")
    codes = [
        client.post("/auth/verify", json={"password": "wrong"}).status_code
        for _ in range(throttle.MAX_FAILURES + 2)
    ]
    check(
        "first attempts return 401",
        all(c == 401 for c in codes[: throttle.MAX_FAILURES]),
        str(codes),
    )
    check(
        "attempts past the threshold return 429",
        all(c == 429 for c in codes[throttle.MAX_FAILURES :]),
        str(codes),
    )

    locked = client.post("/auth/verify", json={"password": "wrong"})
    check(
        "lockout response carries Retry-After",
        "retry-after" in {k.lower() for k in locked.headers},
        str(dict(locked.headers)),
    )

    # A successful login clears the counter.
    throttle.reset("testclient")
    r = client.post("/auth/verify", json={"password": "shared"})
    check("correct password succeeds after reset", r.status_code == 200, f"got {r.status_code}")
    check("verify returns a token", bool(r.json().get("token")), str(r.json()))

    # --- 3. CORS must never be wildcard-with-credentials ----------------------
    from app.settings import get_settings

    origins = get_settings().cors_origins
    check("CORS origins are an explicit allowlist", "*" not in origins, str(origins))

    throttle.reset("testclient")

    if failures:
        print(f"\nSecurity test FAILED: {failures}")
        return 1
    print("\nSecurity tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
