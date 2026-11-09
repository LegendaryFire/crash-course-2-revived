# Crash Course 2, revived

Doritos Crash Course 2 shipped as an Xbox Live Arcade title, and Live was shut down
for it, so the retail game sits at *"a connection to Xbox Live is required"* and never
reaches a menu. This patches the game's own files so it starts and plays **offline** on
a modded Xbox 360 — RGH or JTAG — launched from Aurora. No server, no proxy, no second
console.

## Run it

Two commands. First build the one program here that needs compiling — a small XEX
unpacker, from `tools/xexmerge_src`, and `make` puts the result beside `revive.py`:

```sh
make
```

That needs a C and a C++ compiler (gcc and g++, or clang) and nothing else; see
[Compiling xexmerge](#compiling-xexmerge) if you have neither. Then put the two files
from your console in `game-data/`, under the names the Xbox gave them:

```
game-data/92EC7B55A94EF2145A233412B18261DEA2BAE65858   the game's LIVE package, 333 MB
game-data/TU_1C424IF_000000K000000.00000000000G5       the Title Update, 1.4 MB
```

Then:

```sh
python3 revive.py
```

The patched game appears in **`output/Doritos Crash Course 2/`** — 42 files, 356 MB —
after a minute or two. Nothing is uploaded anywhere, and git commits neither folder.

Those two names are what the console itself calls them, the first under
`Hdd:\Content\0000000000000000\5841124F\000D0000\` and the second in the live cache, so
copying them across keeps them. Something else — a renamed dump, an extracted folder —
goes on the command line instead, where a path may be the package or any folder holding
`default.xex` and `default.xexp`:

```sh
python3 revive.py <game> <title update> [out]
```

Needs Python 3.9 or newer besides the compiler `make` already used.

If `game-data/` is missing one of the two files, the run stops before it starts work and
prints which one and where it goes: the names are matched exactly, never guessed at.

## Put it on the console

1. **Remove the Title Update** — turn it off in Aurora's Title Update manager, or delete
   it under `Hdd:\Content\0000000000000000\5841124F\`. Aurora applies an enabled update to
   `default.xex` as it launches, and this exe has that update merged already; running the
   `.xexp` over an image it was not written for is what stops the title starting.
2. Copy **`output/Doritos Crash Course 2`** to the internal drive,
   `Hdd:\Games\Doritos Crash Course 2\`, and start it from Aurora.

Whether the installed game stays installed is your call, and it is not what makes the
title start. A licence is not in the exe and cannot be: it lives in the LIVE package's
licence stub, which is why unlock tools rewrite packages rather than executables, while
`default.xex`'s headers hold its entry point, imports, version and ratings and say nothing
about who owns the game. What lets an extracted XBLA title boot unlicensed is a *licence
patch*: DashLaunch's `xblapatch` and `licpatch`, both on in a standard install, or
Aurora's per-game **Settings → License Patching**. What deleting the installed copy costs
you is the licence and the retail files, which Live will not hand back now that this title
is off the store — the package you put in `game-data/` is your only copy of those. Leave
it installed and Aurora lists two Crash Course 2s: start the one under `Hdd:\Games\`, not
the installed entry.

First screen is the course list. You race as your own avatar.

## What changes

In `default.xex` — the Title Update merged in (`0.0.0.5` → `0.0.2.5`), then 144 machine
code writes from 9 patches: no Xbox Live log-in required, the shop and course list
built without a LiveGamer object, no "service not available" kick, World Tour adds you
to the race and keeps you in it, the local split-screen lobby works, progress and
unlocks save to the local profile, stars are earned and spent offline, and the "Beta"
label from the preview build is hidden.

In `data.pak` — the Title Update's own files merged in, the splash screen no longer
waiting on a LiveGamer profile, the Xbox LIVE banner and coin balance gone from the
menus, all 28 courses priced in stars only, and the results screen's "Recommended
Item" taken from the local shop instead of a marketplace query.

The header's page hashes and digest are rebuilt for the patched image, which is what
lets a modded kernel load the file at all.

## Options

| | |
|---|---|
| `--unlock-all` | every course unlocked, nothing to buy |
| `--race-solo` | World Tour races without the AI racers |
| `--exe-only` | just `default.xex`, leaving `data.pak` as the game's own |
| `--help` | the diagnostics: `--patches FILE`, `--xexmerge PATH`, `--zero-signature`, `--compression`, `--no-verify`, `--no-patches` |

Two checks, if you want them (both read the inputs from `game-data/`, like the build
does):

```sh
./check_hashes.py output/"Doritos Crash Course 2"/default.xex    # would the loader take this?
./verify_build.py output/"Doritos Crash Course 2"/default.xex    # all 144 writes, nothing else
```

## Compiling xexmerge

`xexmerge` unpacks the retail XEX and applies the Title Update's `.xexp`, checking
Microsoft's own block hashes as it goes; it's the one part that isn't Python, so nothing
here runs until `make` has built it. Sources are in `tools/xexmerge_src` (C and C++,
with libmspack's LZX decompressor vendored — see its `NOTICE`).

| | |
|---|---|
| Linux, macOS | `make`, with gcc or clang. `make CC=clang CXX=clang++` if you prefer. |
| Windows | in an MSYS2 / MinGW-w64 shell: `pacman -S mingw-w64-ucrt-x86_64-toolchain make`, then `make` |
| WSL | `sudo apt install build-essential`, then `make` |
| cross-build for Windows, from Linux | `make CROSS=x86_64-w64-mingw32-` gives `xexmerge.exe`, linked static so no runtime DLLs are needed beside it |

`make clean` removes the binary and the objects. `make doritos` does both steps in
`Run it` in one go, and `make check` runs the two verifications on whatever is in
`output/`.

## If it does not start

| | |
|---|---|
| `xexmerge is not there. — build it first: make` | You ran the script before building it. `make`, then run it again; `make doritos` does both. |
| "The game could not start. Try downloading the game again later." | Three things say this. An enabled Title Update, applied over the merged exe again — remove it. Licence patching off, which any extracted XBLA title needs — DashLaunch's `xblapatch` and `licpatch`, or Aurora's per-game **License Patching**. Or a file the kernel will not load, which `./check_hashes.py` on your `default.xex` rules out. |
| Aurora lists Crash Course 2 twice | The installed copy, which still wants Xbox Live. Yours is the one under `Hdd:\Games\`; rename it in Aurora if the two are hard to tell apart. |
| "This game can't be started from this location" | The kernel is not patched. Patching the exe invalidates Microsoft's signature, so this needs an RGH/JTAG kernel. |
| Black screen after the dash | `default.xex` and `data.pak` need the other 40 files beside them. |

## Not included

Online play and marketplace content — that was the service, not the game. The Xenia
mod's stand-in avatar model is also left out, because a real console renders your own
avatar.


## How this folder is put together

`revive.py` merges, patches, rehashes and repacks; `xexpatch.py` is the XEX library
behind it, `pakpatch.py` and `pakedits.py` the menu edits, `patches/offline.patch.json`
every patch of the mod as addresses and bytes (a console build applies 9 of them, 144
writes), and `tools/` reads 360 packages, paks and templates. The `Makefile` builds
`xexmerge` out of `tools/xexmerge_src` and has a `doritos` and a `check` target for the
two things you would otherwise type by hand.

It is assembled from the Xenia mod's repository by that repo's
`console/tools/make_bundle.py`, which is also what keeps the patch list here identical
to the one the emulator build uses:

```sh
python3 ../doritos-crash-course-2/console/tools/make_bundle.py \
    --name revive.py --no-readme .
```

Xenia-licensed and LGPL parts are credited in `tools/xexmerge_src/NOTICE`, alongside
their sources; everything else here is MIT, see `LICENSE`.
