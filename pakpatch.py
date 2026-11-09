"""Rebuild the game's data.pak for offline play on a modded console.

The Title Update ships a patch pak whose files override the game's own; the merged
data.pak the console runs has to carry those first, then the mod's template edits:

  splash        the start handler builds the course list instead of waiting for a
                LiveGamer profile the servers would never send
  menus         no Xbox LIVE banner, no coin balance (stars and rewind move up)
  shop          every course priced in stars only, since coins cannot be bought
  results       "Recommended Item" names a shop item rather than waiting on the
                network for one

The edits themselves are in pakedits.py, which make_bundle.py generates from the
Xenia mod's build_cc2.py so that both builds apply the same ones. This module and
that one need only the standard library: build_cc2.py imports numpy and PIL for the
avatar work a console does not need.
"""
import hashlib
import os

import pakedits                       # first: it puts the tools folder on sys.path
import tongaspak


def build_data_pak(pak_path, patch_pak_bytes, out_path):
    """The game's data.pak + the Title Update's patch pak merged + the menu fixes."""
    check_edits()
    print("  opening data.pak (about a minute to read and write)...")
    pak = tongaspak.Pak.load(pak_path)
    patch_pak = tongaspak.Pak(patch_pak_bytes)
    for name in patch_pak.index:
        pak.put(name, patch_pak.get(name))
    print(f"  merged the Title Update's patch pak: {len(patch_pak.index)} files")

    guigroup, unistrings = (pakedits.tpl(pak, "guigroup.wbr"),
                            pakedits.tpl(pak, "unistrings.wbr"))
    pakedits.skip_livegamer_wait(guigroup)
    pakedits.hide_live_tickers(guigroup)
    pakedits.hide_coins(guigroup)
    pakedits.random_recommendation(guigroup, unistrings)
    pakedits.put_tpl(pak, "guigroup.wbr", guigroup)
    pakedits.put_tpl(pak, "unistrings.wbr", unistrings)
    print("  splash: no LiveGamer wait (starts the course list offline); menus: no Xbox LIVE "
          "banner, no coin balance; results: Recommended Item from the shop's items")

    levelconfig = pakedits.tpl(pak, "levelconfig.wbr")
    print(f"  levelconfig: {pakedits.stars_only(levelconfig)} courses priced in stars only")
    pakedits.put_tpl(pak, "levelconfig.wbr", levelconfig)

    pak.save(out_path)
    print(f"  data.pak written: {os.path.getsize(out_path) / 1e6:.0f} MB")


def check_edits():
    """Stop if pakedits.py came from a different build_cc2.py than the one beside it.

    Only the repository has both, so in a bundle pakedits.EDITS_BUILD_CC2 points at
    nothing and this proves nothing and does nothing; here it keeps a hand-edited
    Xenia mod from being silently ignored by the console build.
    """
    path = pakedits.EDITS_BUILD_CC2
    if not path or not os.path.isfile(path):
        return
    with open(path, "rb") as f:
        digest = hashlib.sha256(f.read()).hexdigest()[:16]
    if digest != pakedits.EDITS_DIGEST:
        raise RuntimeError(
            f"pakedits.py was generated from {path} at {pakedits.EDITS_DIGEST}, but that "
            "file is now at " + digest + ", so this build would apply stale template "
            "edits. Run console/tools/make_bundle.py to regenerate it.")
