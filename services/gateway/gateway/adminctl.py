"""Bootstrap admin CLI. Run with `kubectl exec`, not from the web.

    python -m gateway.adminctl invite admin@example.com admin

Exists because the first admin has to come from somewhere, and the two
obvious alternatives are both worse:

  * Seeding a default password would ship a known credential.
  * Logging an invite link at startup would write a bearer token into the
    pod log, which SEC-8 forbids.

So the token is printed to stdout, once, only when a human runs this.
"""

from __future__ import annotations

import asyncio
import sys

from . import accounts
from .config import Config
from .db import Db


async def _invite(email: str, role: str) -> int:
    if role not in accounts.ROLES:
        print("role must be one of %s" % ", ".join(accounts.ROLES), file=sys.stderr)
        return 2
    cfg = Config.from_env()
    db = Db(cfg.database_url)
    await db.open()
    try:
        raw, h = accounts.new_token()
        await db.create_invite(email.lower().strip(), role, h, None,
                               accounts.expiry(accounts.INVITE_TTL))
        print("invite created for %s as %s" % (email, role))
        print("accept path (valid %d days, single use):" % accounts.INVITE_TTL.days)
        print("  /accept?token=%s" % raw)
    finally:
        await db.close()
    return 0


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] != "invite" or len(sys.argv) < 3:
        print(__doc__ or "", file=sys.stderr)
        print("usage: python -m gateway.adminctl invite <email> [admin|member]",
              file=sys.stderr)
        return 2
    email = sys.argv[2]
    role = sys.argv[3] if len(sys.argv) > 3 else accounts.ROLE_MEMBER
    return asyncio.run(_invite(email, role))


if __name__ == "__main__":
    raise SystemExit(main())
