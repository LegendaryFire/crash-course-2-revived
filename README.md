# Crash Course 2, revived

Doritos Crash Course 2 shipped as an Xbox Live Arcade title, and Live was shut down
for it, so the retail game sits at *"a connection to Xbox Live is required"* and never
reaches a menu. This patches the game's own files so it starts and plays **offline** on
a modded Xbox 360 — RGH or JTAG — launched from Aurora. No server, no proxy, no second
console.

## Run it

```sh
python3 revive.py <LIVE package> <title update package>
```

Two things in, both from the console's own hard drive or your backups:

| input | what it looks like |
|---|---|
| the game | its Xbox Live package, `000D0000\92EC7B55A94EF214…`, 333 MB |
| the Title Update | `TU_1C424IF_000000K000000.00000000000G5`, 1.4 MB |

Either can also be a folder holding the files. The result is a
`Doritos Crash Course 2/` folder in the current directory — 42 files, 356 MB — after a
minute or two. Needs Python 3.9 or newer and nothing else; `xexmerge`, which does the
unpacking, is already here for x86-64 Linux (see [Other machines](#other-machines)).

## Put it on the console

1. **Delete the installed Title Update**, under
   `Hdd:\Content\0000000000000000\5841124F\`. An installed `.xexp` on top of the merged
   `default.xex` here stops the title starting.
2. **Leave the installed game itself installed.** It is what holds the licence, and
   without it the dashboard refuses to launch. Aurora will list two Crash Course 2s —
   start yours from the file browser, not the games blade.
3. Copy the **whole output folder** to the internal drive,
   `Hdd:\Games\Doritos Crash Course 2\`, and start it from Aurora.

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

Two checks, if you want them:

```sh
./check_hashes.py "Doritos Crash Course 2/default.xex"      # would the loader take this?
./verify_build.py "Doritos Crash Course 2/default.xex" <LIVE> <TU>   # all 144 writes, nothing else
```

## If it does not start

| | |
|---|---|
| "The game could not start. Try downloading the game again later." | An installed Title Update that no longer matches the merged exe — delete it, keep the game. `./check_hashes.py` on your `default.xex` rules out the file itself. |
| "This game can't be started from this location" | The kernel is not patched. Patching the exe invalidates Microsoft's signature, so this needs an RGH/JTAG kernel. |
| Black screen after the dash | `default.xex` and `data.pak` need the other 40 files beside them. |

## Not included

Online play and marketplace content — that was the service, not the game. The Xenia
mod's stand-in avatar model is also left out, because a real console renders your own
avatar.

### Other machines

`xexmerge` here is built for x86-64 Linux. Anywhere else:

```sh
make -C tools/xexmerge_src        # needs gcc and g++; then --xexmerge tools/xexmerge
```

## How this folder is put together

`revive.py` merges, patches, rehashes and repacks; `xexpatch.py` is the XEX library
behind it, `pakpatch.py` and `pakedits.py` the menu edits, `patches/offline.patch.json`
every patch of the mod as addresses and bytes (a console build applies 9 of them, 144
writes), and `tools/` reads 360 packages, paks and templates.

It is assembled from the Xenia mod's repository by that repo's
`console/tools/make_bundle.py`, which is also what keeps the patch list here identical
to the one the emulator build uses:

```sh
python3 ../doritos-crash-course-2/console/tools/make_bundle.py \
    --name revive.py --no-readme .
```

Xenia-licensed and LGPL parts are credited in `tools/xexmerge_src/NOTICE`, alongside
their sources; everything else here is MIT, see `LICENSE`.
