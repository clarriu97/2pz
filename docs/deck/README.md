# Case presentation

Open `index.html` in any browser. No build, no dependencies, works offline.

- `←` `→` or click — next / previous (stepped slides advance one beat at a time)
- `↑` `↓` — jump a whole slide, skipping the beats
- `N` — what to say · `F` — fullscreen · `Home` / `End` — first / last

15 slides, then 8 more to answer from rather than present. The spoken script is in
[`script.md`](script.md) and behind the `N` key.

`Cmd+P` → *Save as PDF* exports one slide per page with every beat revealed.

## Figures

`img/*.svg` are generated from the committed dataset and pasted inline into the deck, so a figure on
a slide cannot drift from the numbers the product renders:

```bash
uv run python docs/deck/build_figures.py
```
