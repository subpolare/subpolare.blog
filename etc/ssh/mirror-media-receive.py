#!/usr/bin/python3
"""Forced SSH command: select a data-only root, then let rrsync validate its protocol."""
import os
import sys

ROOTS = {
    "uploads": "/srv/pepic/uploads",
    "legacy-images": "/srv/pepic/legacy/images",
    "legacy-videos": "/srv/pepic/legacy/videos",
}


def receive(original_command):
    selector, separator, arguments = original_command.partition(" ")
    root = ROOTS.get(selector)
    if not root or not separator or not arguments.startswith("--server "):
        raise ValueError("Only media transfers are permitted")
    if os.path.realpath(root) != root or not os.path.isdir(root):
        raise ValueError("Media root must be an existing real directory")
    environment = dict(os.environ, SSH_ORIGINAL_COMMAND="rsync " + arguments)
    os.execve("/usr/bin/rrsync", ["rrsync", "-wo", "-no-del", "-munge", root], environment)


if __name__ == "__main__":
    try:
        receive(os.environ.get("SSH_ORIGINAL_COMMAND", ""))
    except ValueError as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
