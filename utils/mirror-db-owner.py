"""Apply explicit mirror migrations using an owner secret, never print it."""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path("/srv/subpolare.blog")
if Path.cwd().resolve() != ROOT:
    raise SystemExit("Run only from /srv/subpolare.blog")
allowed = (["migrate", "--noinput"], ["configure_mirror_database", "--target"])
if sys.argv[1:] not in allowed:
    raise SystemExit("Only migrate --noinput or configure_mirror_database --target is supported")
credentials = dict(line.split("=", 1) for line in (ROOT / "secrets/database.env").read_text().splitlines() if "=" in line)
environment = os.environ.copy()
environment.update({name: credentials[name] for name in ("POSTGRES_USER", "POSTGRES_PASSWORD")})
subprocess.run([
    "docker", "compose", "-p", "subpolareblog", "-f", "docker-compose.mirror.yml",
    "run", "--rm", "--no-deps", "-e", "POSTGRES_USER", "-e", "POSTGRES_PASSWORD",
    "-v", str(ROOT / "secrets") + ":/bootstrap:ro", "blog_app",
    "python3", "manage.py", *sys.argv[1:],
], env=environment, check=True)
