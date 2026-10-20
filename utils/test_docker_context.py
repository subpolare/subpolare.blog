"""Run with `python3 utils/test_docker_context.py`; requires local Docker.

Builds only synthetic fixtures using FROM scratch, without pulling images or
copying the repository's actual environment files into Docker.
"""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class DockerContextTests(unittest.TestCase):
    def test_environment_files_are_excluded_but_examples_remain(self):
        root = Path(__file__).resolve().parents[1]
        secret_names = (".env", ".env.local", ".env.production", ".env.backup")
        directories = (Path("."), Path("nested"), Path("nested/deeper"))
        with tempfile.TemporaryDirectory(
            prefix="docker-context-", dir=os.environ.get("DOCKER_TEST_TMPDIR")
        ) as temporary:
            context = Path(temporary) / "context"
            output = Path(temporary) / "output"
            context.mkdir()
            shutil.copyfile(root / ".dockerignore", context / ".dockerignore")
            (context / "Dockerfile").write_text("FROM scratch\nCOPY . /app\n")
            for directory in directories:
                target = context / directory
                target.mkdir(parents=True, exist_ok=True)
                for name in secret_names:
                    (target / name).write_text("SYNTHETIC_SECRET=test-only\n")
                (target / ".env.example").write_text("SYNTHETIC_SECRET=\n")
            (context / "application.py").write_text("# Ordinary application source\n")

            subprocess.run(
                [
                    os.environ.get("DOCKER_BIN", "docker"),
                    "build", "--network=none", "--no-cache",
                    "--output", f"type=local,dest={output}", str(context),
                ],
                check=True,
            )

            for directory in directories:
                for name in secret_names:
                    with self.subTest(path=str(directory / name)):
                        self.assertFalse((output / "app" / directory / name).exists())
                with self.subTest(example=str(directory / ".env.example")):
                    self.assertEqual(
                        (output / "app" / directory / ".env.example").read_text(),
                        "SYNTHETIC_SECRET=\n",
                    )
            self.assertEqual(
                (output / "app/application.py").read_text(),
                "# Ordinary application source\n",
            )


if __name__ == "__main__":
    unittest.main()
