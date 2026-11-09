"""Merge a title update into a XEX2, patch it, and repack it for a modded console.

    merge     xexmerge unpacks the retail xex and applies the update's .xexp, giving
              the updated image and header (it checks Microsoft's own block hashes
              and the update's key chain as it goes).
    patch     equal-length writes at fixed addresses, from a patch file.
    rehash    the page hashes and the header digest are rebuilt for the patched
              image. The console verifies both even when its kernel skips the RSA
              signature, so a rebuilt xex that leaves them stale gets "the game
              could not start".
    repack    unencrypted and *basic* compressed (type 1). The kernel refuses type
              0, which is why xextool's decompress and the homebrew packers all
              produce basic blocks rather than a flat image.

Only the standard library, plus xexmerge for the merge and stfs.py for reading a
360 package. Nothing here touches the game's pak files.
"""

import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import tomllib
import zipfile

TITLE_ID = "5841124F"

HERE = os.path.dirname(os.path.abspath(__file__))

# stfs, tongaspak, wbr and lua51 come from a tools folder beside the module (a
# bundle) or from the Xenia mod's tools in this project (the repository).
for _folder in (os.path.join(HERE, "tools"),
                os.path.join(HERE, "..", "..", "doritos-crash-course-xenia", "tools")):
    if os.path.isdir(_folder):
        sys.path.append(os.path.abspath(_folder))

# the patch file beside the module (a bundle exports one) or the Xenia mod's own
PATCH_FILE = os.path.join(HERE, "patches", "offline.patch.json")
if not os.path.isfile(PATCH_FILE):
    PATCH_FILE = os.path.join(HERE, "..", "..", "doritos-crash-course-xenia", "patches",
                              "5841124F - Doritos Crash Course 2 (offline).patch.toml")

# the two folders a bundle uses: the inputs in, the patched game out
GAME_DATA = os.path.join(HERE, "game-data")
OUTPUT = os.path.join(HERE, "output")
GAME_FOLDER = "Doritos Crash Course 2"

# and the two inputs under their own names, which are not names anyone chooses: the
# first is the game's Xbox Live package on the hard drive, at
# Content\0000000000000000\5841124F\000D0000\, and the second the Title Update in the
# live cache. Copying them off the console keeps both.
GAME_FILE = "92EC7B55A94EF2145A233412B18261DEA2BAE65858"
UPDATE_FILE = "TU_1C424IF_000000K000000.00000000000G5"


BASE = 0x82000000

CONSOLE_PATCHES = [
    "Accept a local profile instead of Xbox LIVE",
    "Hide the Beta build label",
    "Create the shop (course list) without LiveGamer",
    "No 'service not available' kick",
    "Keep the players in the race",
    "Local multiplayer lobby without LiveGamer",
    "World Tour adds the player",
    "Save progress in the Xbox profile",
    "Earn and spend stars offline",
]

OPTIONAL = ["Unlock all courses", "Race solo (no AI racers)"]

XENIA_ONLY = [
    "Avatar previewer works with the stand-in model",
    "Avatar asset refresh skips the stand-in model",
    "Players race as the stand-in model",
    "Stand-in model: no writes to avatar-only fields",
]

PAGE_BYTES = 0x10000          # a XEX image page, and one page descriptor each

BASIC_GRANULE = 0x1000        # the unit a basic-compressed xex stores and elides in

COMPRESSION_BASIC = 1

HEADER_ALIGN = 0x1000


def be32(d, p):
    return struct.unpack_from(">I", d, p)[0]


def in_game_data(name, what, folder=None):
    """`name` in the game-data folder, matched ignoring case because Windows may.

    Only this exact name, never a guess: the two input files are named by the Xbox
    itself, so a folder that does not hold them holds something we should not
    silently pick for someone. What it prints says which file is wanted and where.
    """
    folder = folder or GAME_DATA
    run = os.path.basename(sys.argv[0]) if sys.argv else "revive.py"
    unless = f"or name the two files on the command line: {run} <game> <update> [out]"
    if not os.path.isdir(folder):
        raise SystemExit(f"there is no game-data folder at {folder}\n  {unless}")
    for entry in sorted(os.listdir(folder)):
        if entry.lower() == name.lower():
            return os.path.join(folder, entry)
    raise SystemExit(f"put the {what} in {folder} as {name}\n  {unless}")


def find(path, name, tmp=None):
    """`name` inside a folder, a file, or a 360 package, extracted if need be.

    Every input to the tool is treated as a place to look: the extracted game
    folder, a LIVE or LiveContent package, the title update package, or the file
    itself. The answer is always a path on disk, so no caller has to care where
    the file came from.
    """
    tmp = tmp or tempfile.gettempdir()
    found = _locate(path, name, tmp)
    if found:
        return found
    raise RuntimeError(f"{name} not found in {path}"
                       + ("" if _stfs() else " (a 360 package needs stfs.py in a tools folder)"))


def _locate(path, name, tmp):
    """One step of find(): the path itself, or a file under it, or inside its package."""
    if os.path.isdir(path):
        for root, _, files in os.walk(path):
            if name in files:
                return os.path.join(root, name)
        for root, _, files in os.walk(path):        # the file may be inside a package here
            for entry in files:
                found = _locate(os.path.join(root, entry), name, tmp)
                if found:
                    return found
        return None
    if os.path.basename(path).lower() == name.lower():
        return path
    stfs = _stfs()
    if stfs is None:
        return None
    try:
        if not stfs.packages(path):
            return None
    except Exception:
        return None
    folder = os.path.join(tmp, "pak-" + os.path.basename(path)[:16])
    os.makedirs(folder, exist_ok=True)
    with stfs.Stfs(path) as pkg:
        pkg.extract_all(folder)
    return _locate(folder, name, tmp)


def _stfs():
    """The repo's or the bundle's stfs module, or None where neither is installed."""
    try:
        import stfs                                            # noqa: PLC0415
    except ImportError:
        return None
    return stfs


def merge_update(xexmerge, game_xex, tu_xexp, workdir=None):
    """Run xexmerge: base default.xex + the update's default.xexp.

    The merged image and header are written to `workdir` (a temporary folder by
    default -- never next to the game, or they end up copied into the build).
    """
    workdir = workdir or tempfile.mkdtemp(prefix="xexmerge-")
    image_p = os.path.join(workdir, "merged_image.bin")
    header_p = os.path.join(workdir, "merged_header.bin")
    r = subprocess.run([xexmerge, game_xex, tu_xexp, image_p, header_p],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError(f"xexmerge failed:\n{r.stderr}")
    for line in r.stderr.splitlines():
        if line.startswith(("update:", "the update is", "header patched", "delta image key",
                            "warning", "error")):
            print("   ", line.strip())
    with open(image_p, "rb") as f:
        image = bytearray(f.read())
    with open(header_p, "rb") as f:
        header = bytearray(f.read())
    return image, header


def patch_writes(patch_file, enabled):
    """[(name, address, bytes)] for the named patches, from a TOML or a JSON file.

    The Xenia mod's TOML is the source of truth; the JSON form, which make_bundle
    exports from it, carries the same writes so a bundle needs nothing from that
    repository.
    """
    data = read_patch_file(patch_file)
    names = [p["name"] for p in data["patch"]]
    for name in enabled:
        if name not in names:
            raise RuntimeError(f"patch '{name}' is not in {patch_file}")
    out = []
    for patch in data["patch"]:
        if patch["name"] not in enabled:
            continue
        for write in patch["writes"]:
            out.append((patch["name"], write["address"], write["bytes"]))
    return out


def read_patch_file(patch_file):
    """A patch file as {title_id, patch: [{name, writes: [{address, bytes}]}]}.

    TOML nests its writes under be32/be16/be8, one key per width, as Xenia's own
    patch format has them; the JSON a bundle carries has them flattened to bytes.
    That JSON also names which patches a console build applies, but only as a note
    for its README: the two forms come out of here identical.
    """
    with open(patch_file, "rb") as f:
        raw = f.read()
    if raw[:1] == b"{":
        loaded = json.loads(raw)
        title = loaded.get("title_id")
        patches = [{"name": p["name"],
                    "writes": [{"address": int(w["address"], 16),
                                "bytes": bytes.fromhex(w["bytes"])} for w in p["writes"]]}
                   for p in loaded["patch"]]
    else:
        toml = tomllib.loads(raw.decode())
        title = toml.get("title_id")
        patches = [{"name": p["name"],
                    "writes": [{"address": e["address"],
                                "bytes": int(e["value"]).to_bytes(size, "big")}
                               for key, size in (("be32", 4), ("be16", 2), ("be8", 1))
                               for e in p.get(key, [])]}
                   for p in toml["patch"]]
    if title != TITLE_ID:
        raise RuntimeError(f"{patch_file} is not the Crash Course 2 patch file "
                           f"(title_id {title!r})")
    return {"title_id": title, "patch": patches}


def apply_patches(image, writes):
    """Apply the patch writes to the merged image; sanity-check the result."""
    applied = {}
    for name, addr, data in writes:
        if addr < BASE or addr + len(data) > BASE + len(image):
            raise RuntimeError(f"{name}: {addr:08X} outside the image")
        for i, byte in enumerate(data):
            if applied.get(addr + i, byte) != byte:
                raise RuntimeError(f"patches overlap with conflicting bytes at {addr + i:08X}")
            applied[addr + i] = byte
        image[addr - BASE:addr - BASE + len(data)] = data

    # sanity: the repacked branch/jump instructions must stay inside the image
    for name, addr, data in writes:
        if len(data) == 4:
            value = struct.unpack(">I", data)[0]
            if value >> 26 == 18:                       # b / bl
                offset = value & 0x03FFFF
                if offset & 0x20000:
                    offset -= 0x40000
                target = addr + offset
                if not BASE <= target < BASE + len(image):
                    raise RuntimeError(f"{name}: {addr:08X} jumps to {target:08X}, "
                                       "outside the image")
    patches = len({name for name, _, _ in writes})
    print(f"  {len(writes)} writes from {patches} patches applied")


def page_chain(values, image):
    """(one digest per image page, the chain head), the way Microsoft builds them.

    Each descriptor holds (1 page << 4 | section type) followed by the digest of
    *the next* page together with that page's own descriptor, so the chain runs
    back to front from twenty zero bytes. Its head covers page 0 and is what the
    security info's image digest holds.
    """
    digest, digests = bytes(20), [bytes(20)] * len(values)
    for page in range(len(values) - 1, -1, -1):
        digests[page] = digest
        page_bytes = bytes(image[page * PAGE_BYTES:(page + 1) * PAGE_BYTES])
        digest = hashlib.sha1(page_bytes + struct.pack(">I", values[page]) + digest).digest()
    return digests, digest


def header_digest(header):
    """SHA1 over everything the RSA signature does not cover: the header from its
    media types onwards, then its first bytes up to and including the image size."""
    sec = be32(header, 0x10)
    return hashlib.sha1(bytes(header[sec + 0x17C:be32(header, 8)]
                               + bytes(header[:sec + 8]))).digest()


def descriptors(header):
    """(count, table offset, per page (1 << 4 | section type) values)."""
    sec = be32(header, 0x10)
    count = be32(header, sec + 0x180)
    table = sec + 0x184
    values = [struct.unpack_from(">I", header, table + i * 24)[0] for i in range(count)]
    return count, table, values


def file_format(data):
    """(encryption, compression, blocks) from any xex's FILE_FORMAT_INFO."""
    count = be32(data, 0x14)
    ffi = next((v for k, v in (struct.unpack_from(">II", data, 0x18 + i * 8)
                               for i in range(count)) if k == 0x000003FF), None)
    if ffi is None:
        raise RuntimeError("no FILE_FORMAT_INFO")
    size, enc, comp = struct.unpack_from(">IHH", data, ffi)
    blocks = [tuple(struct.unpack_from(">II", data, ffi + 8 + i * 8))
              for i in range((size - 8) // 8)] if comp == COMPRESSION_BASIC else []
    return enc, comp, blocks


def built_image(data):
    """The image a built xex carries, expanding the basic block table if it has one."""
    enc, comp, blocks = file_format(data)
    if enc:
        raise RuntimeError("this xex is still encrypted")
    if comp == 0:
        return data[be32(data, 8):]
    if comp == COMPRESSION_BASIC:
        return expand_basic(blocks, data[be32(data, 8):],
                            be32(data, be32(data, 0x10) + 4))
    raise RuntimeError(f"compression type {comp} is not what this build writes")


def check_hashes(data, image):
    """Raise unless the page hashes and the header digest in `data` describe `image`.

    This is exactly what the console verifies besides the RSA signature, which a
    modded kernel skips - so a rebuilt xex that passes here gives the loader no
    hash complaint. It verifies the retail and updated xex too, which is how both
    rules were confirmed before being used here.
    """
    header_size, sec = be32(data, 8), be32(data, 0x10)
    count, table, values = descriptors(data)
    if count * PAGE_BYTES != len(image):
        raise RuntimeError(f"{count} page descriptors cover {count * PAGE_BYTES:#x} bytes, "
                           f"the image is {len(image):#x}")
    digests, head = page_chain(values, image)
    for page, want in enumerate(digests):
        stored = bytes(data[table + page * 24 + 4: table + page * 24 + 24])
        if stored != want:
            raise RuntimeError(f"page {page} ({page * PAGE_BYTES:#x} of the image): stored "
                               f"{stored.hex()}, the chain gives {want.hex()}")
    if bytes(data[sec + 0x114:sec + 0x128]) != head:
        raise RuntimeError("the security info's image digest is not the page chain's head")
    want = header_digest(data)
    if bytes(data[sec + 0x164:sec + 0x178]) != want:
        raise RuntimeError(f"header digest is {bytes(data[sec + 0x164:sec + 0x178]).hex()}, "
                           f"should be {want.hex()}")
    return head


def rehash(header, image, log=print):
    """Rebuild in place the digests that patching the image invalidates.

    The console verifies the page hashes and the header digest even when its
    kernel skips the RSA signature, which is why homebrew titles - whose packer
    computes these same two digests - boot while a rebuilt xex carrying stale
    ones is refused as "the game could not start".
    """
    count, table, values = descriptors(header)
    sec = be32(header, 0x10)
    if count * PAGE_BYTES != len(image):
        raise RuntimeError(f"{count} page descriptors cover {count * PAGE_BYTES:#x} bytes, "
                           f"the image is {len(image):#x}")
    digests, head = page_chain(values, image)
    for page, digest in enumerate(digests):
        struct.pack_into(">20s", header, table + page * 24 + 4, digest)
    struct.pack_into(">20s", header, sec + 0x114, head)
    top = header_digest(header)
    struct.pack_into(">20s", header, sec + 0x164, top)
    log(f"  rehashed: {count} page hashes, image digest {head.hex()[:12]}..., "
        f"header digest {top.hex()[:12]}...")


def basic_blocks(image, elide_zeros=True):
    """Cut the image into [data bytes, zeros left out] blocks, as xextool does.

    A basic-compressed xex stores the image in 4 KiB granules, runs of all-zero
    granules named by a count instead of stored, and each block is (data, zeros).
    The console will not start a title whose last block ends in zeros, so the tail
    run is stored instead of elided.

    `elide_zeros=False` gives the whole image as one block: the same format with
    nothing left out, which is the smaller change to the header.
    """
    if not elide_zeros:
        return [(len(image), 0)]
    zero = bytes(BASIC_GRANULE)
    blocks = []
    for offset in range(0, len(image), BASIC_GRANULE):
        if image[offset:offset + BASIC_GRANULE] == zero and blocks:
            blocks[-1][1] += BASIC_GRANULE
        elif blocks and not blocks[-1][1]:
            blocks[-1][0] += BASIC_GRANULE
        else:
            blocks.append([BASIC_GRANULE, 0])
    blocks[-1][1] = 0
    return [tuple(block) for block in blocks]


def basic_data(blocks, image):
    """The bytes a basic-compressed file stores for these blocks."""
    out, offset = bytearray(), 0
    for data_bytes, zeros in blocks:
        out += image[offset:offset + data_bytes]
        offset += data_bytes + zeros
    return bytes(out)


def expand_basic(blocks, data, image_size):
    """The inverse, the way the loader fills the image: data, then skipped zeros."""
    out, offset = bytearray(), 0
    for data_bytes, zeros in blocks:
        out += data[offset:offset + data_bytes] + bytes(zeros)
        offset += data_bytes
    return bytes(out) + bytes(image_size - len(out))


def align(value, bytes_):
    return (value + bytes_ - 1) // bytes_ * bytes_


def repack_xex(header, image, zero_signature=False, compression="zero-runs"):
    """The merged header, made plain and rehashed, followed by its data area.

    Encryption goes to 0. Compression goes to 1, *basic*: the console refuses a
    title whose FILE_FORMAT_INFO says 0, uncompressed, which is why xextool's
    "decompress" and every homebrew packer produce basic instead. The blocks name
    the image in 4 KiB granules with runs of zeros left out (`compression` picks
    whether they are: "zero-runs", "single", or "none" for the refused form, kept
    for experiments). When the block table is too big for the 36 bytes Microsoft
    left for it, it goes past the old end of the header and the header grows -
    which homebrew does freely, and the header digest then covers the whole thing.

    The RSA signature is Microsoft's and no longer describes this file. A modded
    kernel skips that check - homebrew titles ship with the field empty - so it is
    normally left alone, and `zero_signature` clears it for the case where a
    kernel treats a stale Microsoft signature differently from an absent one.
    """
    count = be32(header, 0x14)
    entry, ffi = None, None
    for i in range(count):
        key, value = struct.unpack_from(">II", header, 0x18 + i * 8)
        if key == 0x000003FF:
            entry, ffi = 0x18 + i * 8, value
    if ffi is None:
        raise RuntimeError("merged header has no FILE_FORMAT_INFO")
    size = be32(header, ffi)
    if size < 8 or ffi + size > len(header):
        raise RuntimeError("the FILE_FORMAT_INFO block is damaged")
    if len(header) != be32(header, 8):
        raise RuntimeError(f"the header buffer is {len(header):#x} bytes but says "
                           f"{be32(header, 8):#x}")

    sec = be32(header, 0x10)
    if be32(header, sec + 4) != len(image):
        raise RuntimeError(f"security info says {be32(header, sec + 4):#x}, "
                           f"image is {len(image):#x}")
    if not be32(header, sec) or sec + be32(header, sec) > len(header):
        raise RuntimeError("the security info runs past the header")

    if compression == "none":
        struct.pack_into(">IHH", header, ffi, size, 0, 0)       # what the console refuses
        header[ffi + 8:ffi + size] = bytes(size - 8)            # no window, no first block
        data = bytes(image)
    else:
        blocks = basic_blocks(image, elide_zeros=compression == "zero-runs")
        block_table = b"".join(struct.pack(">II", stored, skipped) for stored, skipped in blocks)
        want = 8 + len(block_table)
        if want <= size:                                # room where it already is
            struct.pack_into(">IHH", header, ffi, want, 0, COMPRESSION_BASIC)
            header[ffi + 8:ffi + size] = block_table + bytes(size - want)
        else:                                           # past the end, and grow
            at = len(header)
            grown = align(at + want, HEADER_ALIGN)
            header.extend(bytes(grown - len(header)))
            header[at:at + want] = struct.pack(">IHH", want, 0, COMPRESSION_BASIC) + block_table
            struct.pack_into(">I", header, 8, grown)              # the header is bigger now
            struct.pack_into(">I", header, entry + 4, at)         # the entry's value points at it
        data = basic_data(blocks, image)
        if expand_basic(blocks, data, len(image)) != bytes(image):
            raise RuntimeError("the basic blocks do not rebuild the image")
        print(f"  basic: {len(blocks)} blocks, {len(data):#x} bytes stored for "
              f"{len(image):#x} of image, header {be32(header, 8):#x}")

    if zero_signature:
        # The signature sits in the one region the header digest does not cover,
        # so clearing it needs no rehash of its own.
        header[sec + 0x8:sec + 0x108] = bytes(0x100)
    rehash(header, image)                       # after any growth of the header
    return bytes(header) + data


def verify_xex(path, image):
    """Re-read the built XEX the way the kernel does (plain data at header_size)."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"XEX2":
        raise RuntimeError("built xex: bad magic")
    header_size, security_off = be32(data, 8), be32(data, 0x10)
    enc, comp, blocks = file_format(data)
    if enc:
        raise RuntimeError("built xex: still marked encrypted")
    if comp not in (0, COMPRESSION_BASIC):
        raise RuntimeError(f"built xex: compression {comp}")
    if built_image(data) != bytes(image):
        raise RuntimeError("built xex: its data does not rebuild the patched image")
    image_size = be32(data, security_off + 4)
    if len(image) != image_size:
        raise RuntimeError(f"built xex: image {len(image):#x}, security info says {image_size:#x}")
    check_hashes(data, bytes(image))
    count, _, _ = descriptors(data)
    how = f"basic in {len(blocks)} blocks" if comp == COMPRESSION_BASIC else "uncompressed"
    print(f"  verified: image of {len(image):#x} bytes stored {how} ({len(data) - header_size:#x} "
          f"bytes at {header_size:#x}), {count} page hashes and the header digest consistent")
