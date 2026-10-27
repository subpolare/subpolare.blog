"""Build the bounded, tested Pepic variant without modifying its source checkout."""
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path("/srv/subpolare.blog")
if Path.cwd().resolve() != ROOT:
    raise SystemExit("Run only from /srv/subpolare.blog")
source = Path("/srv/pepic")
with tempfile.TemporaryDirectory(prefix="pepic-build-", dir=ROOT / "runtime") as temporary:
    target = Path(temporary)
    # Explicit source-only inventory: never copy .env, Git, uploads or keys.
    for name in ("go.mod", "go.sum", "main.go", "Dockerfile", "pepic", "html", "static", "etc/pepic"):
        src, dst = source / name, target / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
    subprocess.run(["git", "apply", "--check", str(ROOT / "etc/pepic/security.patch")], cwd=target, check=True)
    subprocess.run(["git", "apply", str(ROOT / "etc/pepic/security.patch")], cwd=target, check=True)
    for package in ("storage", "handler"):
        test = "storage_security_test.go" if package == "storage" else "proxy_security_test.go"
        shutil.copy2(ROOT / "etc/pepic" / test, target / "pepic" / package / test)
    dockerfile = target / "Dockerfile"
    content = dockerfile.read_text()
    if "RUN go get\n" not in content:
        raise SystemExit("Unexpected Pepic Dockerfile; review before building")
    dockerfile.write_text(content.replace("RUN go get\n", "RUN go mod download\nRUN go test -v ./pepic/storage ./pepic/handler\n"))
    subprocess.run(["docker", "build", "-t", "pepic-hardened:1", str(target)], check=True)
