# hardlaunch-engine

Turns a brand's website into a scored, ready-to-shoot short-form video ad script and creator brief.

## Running it

```
pip install -r requirements.txt
```

Create a `.env` file in the project root with:

```
ANTHROPIC_API_KEY=your-key-here
```

Then run:

```
python engine.py --url https://example.com
```

Output is printed to stdout and saved to `out/<brand>_profile.json` and `out/<brand>_copy.json`.

## Pipeline

- Fetch the brand's site (falling back to a JS-rendering proxy for thin pages) and extract a structured brand profile with Claude.
- Score every format in `formats/library.json` independently against that profile's core pain and hard way, and take the highest-scoring format.
- Adapt the winning format's skeleton into 3 script variants under a strict rule set: fixed word count, lowercase, no banned words, brand named exactly once as an observed action.
- Score the 3 variants on hook strength, specificity, and how human they sound, and pick a winner.
- Generate a creator brief for the winning script: on-screen text, base clip, audio mood and note, visual mechanic, and performance note.

## Brands tested

Different brands select different formats — the format isn't fixed, it's scored per brand each run.

**Notion** — format: `earned_not_gifted`
> realizing i'm organized but i'm leaving comments in slack, pasting the same brief into google docs every monday, missing standups, searching confluence for a link i already opened, rebuilding her team wiki in notion at midnight, and exhausted organized. not naturally organized

**Monzo** — format: `earned_not_gifted`
> realizing i'm alright with money but i'm logging into chase on my lunch break and building a spreadsheet i never finish, transferring twenty quid to savings by hand, forgetting and moving it back, watching monzo ping me every time i spend, and still quietly-stressed alright. not born alright

**Oura Ring** — format: `earned_not_gifted`
> realizing i'm healthy but i'm in bed before the group chat even slows down and turning down the late coffee and tracking my resting heart rate every morning, reading what oura ring flagged while i slept, and eating the same four things on rotation healthy. not accidentally healthy

**Linear** — format: `red_flag_checklist`
> red flags in a product manager: sprint board lives in a jira ticket graveyard. pings six people in slack to find who owns a bug. roadmap is a google sheet with three broken formulas. marks everything priority one. green flag: seen letting linear sort the incoming bug queue while the standup is still loading
