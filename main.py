#!/usr/bin/env python3
"""Entry point for the make.fun bounty news-image-20261118.

Reads nothing, fetches nothing, writes one file: <output_dir>/entry.png, the
front page of THE WORLD for Wednesday 18 November 2026.

    python3 main.py                 # writes /output/entry.png
    python3 main.py out             # writes out/entry.png
"""

import os
import sys

# The grader runs "python3 -P -s /bot/main.py": isolated mode, so the
# script's own directory is not on sys.path.  Put it there explicitly so
# the sibling modules (frontpage, textadapter, ...) import without relying
# on any site or user package.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import frontpage


def main(argv):
    out_dir = argv[1] if len(argv) > 1 else "/output"
    out_dir = os.path.abspath(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "entry.png")

    audit = []
    width, height = frontpage.save_page(path, audit=audit)

    print("wrote %s (%dx%d, %d bytes)"
          % (path, width, height, os.path.getsize(path)))

    bad = frontpage.overruns(audit)
    if bad:
        for label, used, limit in bad:
            print("OVERRUN %s: %.1f > %.1f px" % (label, used, limit),
                  file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
