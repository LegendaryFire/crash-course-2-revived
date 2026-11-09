#!/usr/bin/env python3
"""Check a built console default.xex against the patch file.

Rebuilds the merged-but-unpatched image, then compares it with the built one:
every byte that differs must be one of the enabled patches' writes, and every
enabled patch's writes must be present. That is the whole contract of the build.

  verify_build.py <built/default.xex> <game> <title update> [patch names...]
"""
import argparse
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import xexpatch as X                       # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("built", help="the built default.xex to check")
    ap.add_argument("game", nargs="?", help="the game's default.xex, or the folder/package "
                                            f"that holds it (default: game-data/{X.GAME_FILE})")
    ap.add_argument("update", nargs="?", help="the Title Update package that holds "
                                              f"default.xexp (default: game-data/{X.UPDATE_FILE})")
    ap.add_argument("names", nargs="*", help="patches to expect (default: the console set)")
    ap.add_argument("--patches", default=X.PATCH_FILE, help="the patch file to expect")
    ap.add_argument("--xexmerge", default=os.path.join(HERE, "xexmerge"),
                    help="the xexmerge binary (default: this folder)")
    a = ap.parse_args()

    a.game = a.game or X.in_game_data(X.GAME_FILE, "game (its Xbox Live package)")
    a.update = a.update or X.in_game_data(X.UPDATE_FILE, "Title Update")
    names = a.names or X.CONSOLE_PATCHES
    with tempfile.TemporaryDirectory() as tmp:
        with open(a.built, "rb") as f:
            data = f.read()
        built = X.built_image(data)         # expands the basic block table, as the loader does
        enc, comp, blocks = X.file_format(data)

        image, _ = X.merge_update(a.xexmerge, X.find(a.game, "default.xex", tmp),
                                  X.find(a.update, "default.xexp", tmp), tmp)
        base = bytes(image)
        if len(base) != len(built):
            raise SystemExit(f"image {len(built):#x}, merged {len(base):#x}")

        expect = {}     # image offset -> (patch name, bytes it holds)
        for name, addr, value in X.patch_writes(a.patches, names):
            off = addr - X.BASE
            if expect.get(off, value) != value:
                raise SystemExit(f"two patches disagree about {addr:08X}")
            expect[off] = (name, value)

        changed = (int.from_bytes(base, "big") ^ int.from_bytes(built, "big")) \
            .to_bytes(len(base), "big")
        groups = [m.span() for m in re.finditer(rb"[^\x00]+", changed)]
        n_changed = sum(e - s for s, e in groups)

        missing = [(name, f"{off + X.BASE:08X}") for off, (name, value) in expect.items()
                   if built[off:off + len(value)] != value]
        covered = {o for off, (_, value) in expect.items() for o in range(off, off + len(value))}
        unwanted = [f"{s + X.BASE:08X}-{e - 1 + X.BASE:08X}" for s, e in groups
                    if not all(o in covered for o in range(s, e))]

        enc, comp, _ = X.file_format(data)
        print(f"{len(base):#x} byte image: {n_changed} bytes changed in {len(groups)} places, "
              f"{len(expect)} writes expected from {len(names)} patches")
        print(f"  encryption {enc}, compression {comp}, "
              f"{len(built) // X.PAGE_BYTES} page hashes")
        print(f"  writes missing from the build: {len(missing)}"
              + ("" if not missing else f" {missing[:6]}"))
        print(f"  changes the patch file does not explain: {len(unwanted)}"
              + ("" if not unwanted else f" {unwanted[:6]}"))
        for name in names:
            done = sum(1 for off, (p, v) in expect.items()
                       if p == name and built[off:off + len(v)] == v)
            total = sum(1 for _, (p, _) in expect.items() if p == name)
            print(f"  {name}: {done}/{total}")
        sys.exit(1 if missing or unwanted else 0)


if __name__ == "__main__":
    main()
