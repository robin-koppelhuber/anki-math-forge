---
description: Place what is waiting in a project's inbox, one note-sorter agent per dump
argument-hint: --project NAME [--write | --both] [notes to add first]
---

Place the notes waiting in a project's inbox.

Arguments: `$ARGUMENTS`

- **`--project NAME`**: which project. **Ask if it is not given.**
- **`--write`** or **`--both`**: how the notes given after it are
  placed. Modifying existing cards, or both piece by piece; without either,
  proposed.
  It applies to those notes only; every dump already in the inbox says on
  its own heading how it is placed.
- **notes after it**, optionally: text to add to the inbox before sorting,
  the same as typing it into the inbox on the setup stage.

## What this is

The inbox is `projects/<name>/inbox.md`: things the human learned about the
project's subject and wants in the deck without knowing where. Each dump is
a `## <stamp>` heading with text under it. The words after the stamp, each
after a ` · `, say what it is:

- No mode word: proposed. `@me` notes on cards and new units waiting in
  triage, for the human to act on.
- ` · write`: modify existing cards. The cards a piece bears on are edited, and a unit
  is queued for anything new.
- ` · both`: the agent chooses for each piece, editing what it can
  confirm and what leaves a card asking the same question, proposing the
  rest.
- ` · sorted`: an agent placed it and wrote where each piece went.
  Neither: waiting. The page shows them as two lists, unsorted and sorted;
  an older ` · done` is read as sorted.

Each waiting dump goes to a **note-sorter** agent, which places each piece
by the dump's mode and writes the brief under it. Dumps are independent, so
dispatch them **in parallel**: several `Agent` calls in one message.

No mode reaches Anki. An edited card is a draft again until the human
approves it on the review page.

## Steps

1. If notes were given after the project, append them as a new dump at the
   end of `inbox.md`: a `## <YYYY-MM-DD HH:MM>` heading, with ` · write` or
   ` · both` after the stamp when `--write` or `--both` was given, then
   the text. Create the file with
   an `# Inbox` heading if it is not there.

2. Read `projects/<name>/inbox.md` and list the waiting dumps: headings with
   no ` · sorted`. Note which say ` · write` or ` · both`.

3. Dispatch one `note-sorter` per waiting dump. A dump that modifies
   cards can edit cards, so give its agent `model: "opus"`; a proposed one
   keeps the agent's own model.

   > Place the dump headed `## <the heading as it stands>` in
   > `projects/<name>/inbox.md`, for project `<name>`. Its heading says how:
   > follow your instructions for that mode, then write the brief under the
   > dump and add ` · sorted` to its heading. Report the ids of any units you
   > queued.

4. **Card the units the modifying and both dumps queued.** Collect the ids the
   agents reported, and check each against its brief line, the one reading
   "new unit ..., queued for a card". Dispatch one `card-writer` for all of
   them:

   > Write a stub card for each of these queued units of project `<name>`,
   > and no others: `<ids>`. Each came from the project's inbox and carries
   > an `@claude` brief saying what was asked; read it before anything
   > else. Their entries are in
   > `uv run --no-sync forge units --project <name> --state queued --json`.
   > Follow your instructions exactly: check the mathematics yourself,
   > write stubs only, approve nothing.

   When it reports, add the card it wrote to the end of that unit's brief
   line, so the page links both:

   ```
   - new unit `stats:conditional-jensen`, queued for a card: Jensen for conditional expectations → card `7d1e02`
   ```

   A unit it declined to card keeps its line, with the reason after it.

5. Check the file: every dispatched dump now has ` · sorted` and a
   `### where it went` list. Then check nothing broke:

   ```
   uv run --no-sync forge check
   uv run --no-sync forge todo --audience me --project <name>
   uv run --no-sync forge cards --project <name> --changes
   ```

   The last lists what moved on each card since its last review decision,
   which for a dump that modifies cards is what the agent changed.

6. **Report** per dump: how it was placed, where each piece went, the cards
   written for queued units, and anything an agent was unsure of. Say that
   the briefs are in the **inbox** on the setup stage, where each dump is
   in the sorted list, and that every card a dump changed is listed under
   "changed since decided" in review, which names the dump it came from.
