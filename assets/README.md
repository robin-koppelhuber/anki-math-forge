# assets

Images the top-level README points at. All of them are generated:

```
uv run python assets/make_assets.py            # all three
uv run python assets/make_assets.py triage     # just one
```

| | what it shows | how it is made |
|---|---|---|
| `triage.png` | a queued unit: the crop with its box drawn on the page, the transcription beside it, the brief | a headless Chrome against `forge serve` on a spare port |
| `review.png` | an approved card: front, conditions, back, proof, and the notes that decided it | the same |
| `states.png` | the state machine — units on top, cards below, and which arrows are yours | the app's own `_fsm.html`, rendered into a bare page. No server, no data |
| `demo.mp4` | *not generated.* Record it by hand | see below |

The screenshots use `matrix-cookbook`, which is the source with something in
every state. `FORGE_ASSET_SOURCE=<name>` picks another one. Crops render from
the PDF, which is gitignored, so the source document has to be present locally
or the panes come out empty.

Chrome is found in the usual install locations; `CHROME=<path>` overrides.

## These can go stale, and nothing will tell you

Committed images are a snapshot of a UI that keeps changing, and no test
compares them. That was the trade: the alternative is a live demo to host, or
a README with no picture in it. Re-run the script after a visible change to
the app — it takes about a minute.

## The demo recording

By hand, because the interesting part is the pace of triage and no script
knows how long to pause. Roughly 45 seconds:

1. `forge serve`, the units view, one source.
2. Triage six or seven units — `q`, `q`, `s`, `Q` with a brief typed into the
   prompt. The point is that a decision costs one keystroke.
3. `f` for the rail, copy the `/extract-cards` line.
4. Cut to the review view with cards in it: `a` on one, then an edit in the
   editor, then back to show it has dropped to draft.

Export at 1600×1000 to match the screenshots.
