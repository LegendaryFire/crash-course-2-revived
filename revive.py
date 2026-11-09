#!/usr/bin/env python3
"""Build Doritos Crash Course 2 for a modded Xbox 360 (RGH/JTAG) as a freeboot folder.

Give it the game and the Title Update; the patched folder appears beside them.

`game` and `title update` are anything that holds the files: the extracted folder, a
LIVE or LiveContent package, or default.xex / default.xexp themselves. The out folder
is made if it does not exist.

The Title Update's default.xexp is merged into the game's default.xex (with
xexmerge), the console-relevant patches from the patch file are applied to the
merged image, and the result is repacked as an unencrypted, basic-compressed XEX
whose page hashes and header digest have been rebuilt for the patched image. Both
of those matter: the console verifies the two digests even when its kernel skips
the RSA signature, and it refuses compression type 0 outright, so the image goes in
as basic blocks the way xextool and the homebrew packers emit them.

data.pak then gets the Title Update's patch pak merged in, plus the mod's menu
fixes — the ones that matter offline — without the stand-in avatar work (a real
Xbox 360 draws Xbox avatars; only Xenia needed the stand-in).

The patches named in xexpatch.py are the offline fixes; the four "Avatar" and
"stand-in" patches in the Xenia file work around Xenia's renderer and are skipped.
"""
import argparse
import os
import shutil
import tempfile

import pakpatch                                               # noqa: E402
from xexpatch import (BASE, CONSOLE_PATCHES, OPTIONAL, PATCH_FILE, XENIA_ONLY,  # noqa: E402
                      apply_patches, check_hashes, file_format, find, merge_update,
                      patch_writes, repack_xex, verify_xex)

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("game", help="the game's default.xex, or the folder/package that holds it")
    ap.add_argument("update", help="the Title Update package that holds default.xexp")
    ap.add_argument("out", nargs="?", default="Doritos Crash Course 2",
                    help="the freeboot folder to write (default: ./Doritos Crash Course 2)")
    ap.add_argument("--patches", default=PATCH_FILE,
                    help="the patch file: the Xenia mod's TOML or the JSON a bundle "
                         "ships beside it (default %(default)s)")
    ap.add_argument("--exe-only", action="store_true",
                    help="write default.xex only, leaving data.pak as the game's own "
                         "(the post-boot Xbox Live gate comes back without it)")
    ap.add_argument("--unlock-all", action="store_true", help="every course unlocked, no stars")
    ap.add_argument("--race-solo", action="store_true", help="World Tour without the AI racers")
    ap.add_argument("--xexmerge", default=os.path.join(HERE, "xexmerge"),
                    help="the xexmerge binary (default: this folder)")
    ap.add_argument("--no-verify", action="store_true",
                    help="skip checking the built XEX against the patched image")
    ap.add_argument("--zero-signature", action="store_true",
                    help="clear the 256 byte RSA signature, as a homebrew title "
                         "leaves it; the digests are recomputed either way")
    ap.add_argument("--compression", choices=("zero-runs", "single", "none"),
                    default="zero-runs",
                    help="how to block the image: elide runs of zero pages (the "
                         "default), one block for the whole image, or the plain "
                         "form the console refuses")
    ap.add_argument("--no-patches", action="store_true",
                    help="diagnostic: merge and repack without any patch, to show "
                         "whether the console accepts the repacked XEX at all")
    a = ap.parse_args()

    enabled = [] if a.no_patches else list(CONSOLE_PATCHES)
    enabled += [name for name, on in zip(OPTIONAL, (a.unlock_all, a.race_solo)) if on]
    skipped = set(p for p in OPTIONAL if p not in enabled)
    if a.no_patches:
        print("Diagnostic build: the Title Update merged and the XEX made plain, "
              "but NO offline patches applied")
    else:
        print("Patches:", ", ".join(enabled))
    if skipped:
        print("Off (re-run with --unlock-all / --race-solo):", ", ".join(sorted(skipped)))
    print("Skipped (Xenia's avatar renderer, not needed on a console):",
          ", ".join(XENIA_ONLY))

    os.makedirs(a.out, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        xex = find(a.game, "default.xex", tmp)
        xexp = find(a.update, "default.xexp", tmp)
        game_dir = os.path.dirname(xex)

        print("\nMerging the Title Update into default.xex:")
        image, header = merge_update(a.xexmerge, xex, xexp, tmp)
        print("  base image merged:", f"{len(image):#x} bytes at {BASE:08X}")

        print("Applying the offline patches:")
        apply_patches(image, patch_writes(a.patches, enabled))

        print("Repacking default.xex:")
        out_xex = os.path.join(a.out, "default.xex")
        with open(out_xex, "wb") as f:
            f.write(repack_xex(header, image, a.zero_signature, a.compression))
        if not a.no_verify:
            verify_xex(out_xex, image)
        print(f"  default.xex written: {os.path.getsize(out_xex) / 1e6:.1f} MB")

        if a.exe_only:
            print("\n--exe-only: data.pak left alone")
            return

        print("Patching data.pak:")
        patch_pak = find(a.update, "patch_tu1.pak", tmp)
        game_pak = find(a.game, "data.pak", tmp)
        with open(patch_pak, "rb") as f:
            pakpatch.build_data_pak(game_pak, f.read(), os.path.join(a.out, "data.pak"))

        print("Copying the game's other files:")
        copied = 0
        for name in sorted(os.listdir(game_dir)):
            src = os.path.join(game_dir, name)
            if not os.path.isfile(src) or name in ("default.xex", "data.pak"):
                continue
            shutil.copy2(src, os.path.join(a.out, name))
            copied += 1
        print(f"  {copied} files, plus default.xex and data.pak -> {a.out}")

    print("\nDone. Copy the whole folder to the console's hard drive and start it from "
          "Aurora; the README has the console steps.")


if __name__ == "__main__":
    main()
