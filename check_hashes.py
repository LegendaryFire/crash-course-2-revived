#!/usr/bin/env python3
"""Check the page hashes and header digest of a default.xex.

These are the two things the console verifies about a XEX besides the RSA
signature, so this answers "would the loader refuse this file?" without needing
a console. A plain (uncompressed) xex carries its own image; a compressed one
needs the image extracted separately, e.g. from xexmerge.

    ./check_hashes.py "Doritos Crash Course 2/default.xex"
    ./check_hashes.py default.xex --image /tmp/base_image.bin
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import xexpatch as X                                             # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("xex")
    ap.add_argument("--image", help="the image for a LZX-compressed xex")
    a = ap.parse_args()

    data = open(a.xex, "rb").read()
    header_size, sec = X.be32(data, 8), X.be32(data, 0x10)
    enc, comp, blocks = X.file_format(data)
    if a.image:
        image = open(a.image, "rb").read()
    elif (enc, comp) in ((0, 0), (0, X.COMPRESSION_BASIC)):
        image = X.built_image(data)      # expands a basic block table, as the loader does
    else:
        raise SystemExit(f"{a.xex}: encryption {enc}, compression {comp}: pass --image with "
                         "the unpacked image (xexmerge writes one)")

    pages = X.be32(data, sec + 0x180)
    how = {0: "uncompressed", X.COMPRESSION_BASIC: f"basic in {len(blocks)} blocks"} \
        .get(comp, f"compression {comp}")
    head = X.check_hashes(data, image)
    print(f"{os.path.basename(a.xex)}: {pages} page hashes over {len(image):#x} bytes, "
          f"header {header_size:#x}, {how}: the digests match"
          f"\n  image digest {head.hex()}\n"
          f"  header digest  {data[sec + 0x164:sec + 0x178].hex()}")


if __name__ == "__main__":
    main()
