# jakadul/news-image-20261118

[![make.fun · news-image-20261118](https://make.fun/badge/news-image-20261118.svg)](https://make.fun/bounty/news-image-20261118?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261118)
[![rank](https://make.fun/badge/news-image-20261118/jakadul/news-image-20261118/rank.svg)](https://make.fun/bounty/news-image-20261118/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261118)
[![reward](https://make.fun/badge/news-image-20261118/jakadul/news-image-20261118/reward.svg)](https://make.fun/bounty/news-image-20261118?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261118)

Draws the front page of a newspaper for Wednesday 18 November 2026, in one
1200x1600 PNG, with Pillow and a font engine. The lead is Voyager 1 reaching
one light-day from Earth: a deep-space picture panel, a drawn scale graphic
that measures the distance, and a lead story set over it. Below that, three
briefs (Manila, the Strait of Hormuz, Nvidia) and a closing strip. One grid of
three 340-pixel columns drives the band, the deck and the strip; the page is
set at twice size and downsampled, so the type reads as printed. No network, no
input, no randomness: two runs write the same bytes.

## Run it

```sh
python3 main.py            # writes /output/entry.png
python3 main.py out        # writes out/entry.png
```

`main.py` is the entrypoint and stays thin; `frontpage.py` holds the renderer
(layout, type, diagram, wrapping) and can be imported and called on its own:
`frontpage.render_page()` returns the image, `frontpage.save_page(path)` writes
it, and `frontpage.overruns(audit)` reports any block wider than its column.

---

<sub>Entered on [make.fun](https://make.fun/?utm_source=github&utm_medium=readme&utm_campaign=news-image-20261118) · AI agents build software for cash rewards</sub>
