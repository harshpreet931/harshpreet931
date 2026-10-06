# how this page is made

**`build_assets.py`** draws every SVG in `assets/`. The hero mirrors harshpreet.com:
GitHub's dark mode gets the Midnight theme (a drifting mesh gradient), light mode
gets the Handwritten theme (ruled paper, ballpoint blue). In both, my name is
written stroke by stroke along the pen centrelines of Harshpreet Hand, the font I
made from 120 pages of my computer networks notes. All other text is outlined to
paths, because an SVG shown through `<img>` can't load fonts.

```sh
pip install numpy fonttools uharfbuzz brotli pillow
python3 scripts/build_assets.py ../myHandwriting
```

**`update_notes.mjs`** fills the "recent notes" list from my YouTube channel and my
blog's RSS feed. `.github/workflows/notes.yml` runs it every morning and commits
only when something changed.

```sh
node scripts/update_notes.mjs
```
