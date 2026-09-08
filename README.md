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

**Notion**
> red flags in a coworker: tracks tasks in a dead confluence page. pastes action items into slack and forgets them. has thirty-one browser tabs open every standup. emails you a doc titled "use this one". green flag: him quietly rebuilding the onboarding flow in notion before anyone asked

**Monzo**
> red flags in a housemate: splitting rent through a notes app. no idea what they spent last weekend. checks three banking apps to find a tenner. still uses their barclays because they never got around to it. green flag: caught her sorting her monzo pots at the kitchen table on payday

**Oura Ring**
> my roommate rebuilding her whole routine after having a baby. no whoop. no garmin. no sleep journal. no alarm-based guessing. just her and oura ring. logging her readiness score at 5am like a psychopath

**Linear**
> red flags in a product manager: sprint board lives in a jira ticket graveyard. pings six people in slack to find who owns a bug. roadmap is a google sheet with three broken formulas. marks everything priority one. green flag: seen letting linear sort the incoming bug queue while the standup is still loading
