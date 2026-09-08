#!/usr/bin/env python3
import argparse
import dataclasses
import json
import os
import sys
from dataclasses import dataclass, asdict

import anthropic
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# Claude's output is UTF-8 and can contain characters (em dashes, arrows,
# smart quotes) that the default Windows console codepage can't encode.
# Reconfigure stdout/stderr so printing never crashes on them.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

MODEL = "claude-sonnet-4-6"

MIN_BODY_TEXT_LENGTH = 500

SYSTEM_PROMPT = """You are a brand analysis engine. Given raw page text and \
metadata scraped from a company's website, extract a structured brand profile.

These fields feed short-form video scripts, so every value must sound like one \
person describing another person out loud. Plain spoken English, no marketing \
copy.

Output ONLY raw JSON. No markdown code fences, no ```json, no preamble, no \
explanation, no trailing commentary. The first character of your response must \
be `{` and the last character must be `}`.

Return a JSON object with exactly these keys:
- brand_name: string, the company/product name
- one_liner: string, a single sentence describing what the product does
- niche: string, the specific market segment or category
- icp: string, the ideal customer profile (who this is for)
- core_pain: string, max 12 words, phrased as the feeling, not the business \
problem. Good: "never sure if she actually replied to anyone". Bad: \
"inefficient customer communication across fragmented channels"
- the_hard_way: string, max 8 words, what someone does instead of using this \
product. It must be something you could physically watch a person do - a \
visible behaviour, not a business outcome. Good: "with 40 tabs open", "typing \
notes into her phone at the gym". Bad: "manually switches between disconnected \
tools while spending hours on repetitive tasks"
- alternatives: array of exactly 3 strings, max 4 words each. Concrete objects, \
apps or habits a real person would name out loud. Never include the brand \
itself. Good: "a notes app", "sticky notes", "her memory". Bad: "Google Docs \
combined with Jira and Slack"
- named_competitors: array of at most 4 strings, only products a normal user \
would recognise by name. Fewer is better than padding the list. Use an empty \
array if none qualify.
- tone: array of exactly 3 strings, adjectives describing the brand's tone/voice
- banned_claims: array of strings, claims this brand should NOT make \
(overpromises or claims unsupported by the page content)

Never use corporate vocabulary anywhere in your output. Banned words include \
"leverage", "streamline", "unified", "solution", "workflow" and \
"institutional", along with anything else that reads like a B2B landing page.

Return valid JSON only."""

FORMAT_SCORE_SYSTEM_PROMPT = """You are scoring how well a single \
short-form video ad format's mechanic fits a specific brand. You will be \
given a brand profile and one format's hook_archetype, why_it_works \
explanation, and text_skeleton.

Score 1-10 how well this format's underlying mechanic (why it works, not \
just its surface topic) transfers to this brand's core_pain and \
the_hard_way specifically - not just whether the format is generically \
good.

Use this scale:
- 10: the mechanic fits this brand almost unchanged - the pain slots in \
naturally, the emotional register is right.
- 7: works, but the format has to be bent slightly to fit.
- 4: it can be made to work, but you'd have to force it.
- 1: wrong emotional register entirely - the mechanic and this brand don't \
belong together.

Use the full range. Most formats will not land at a 7 - reserve the middle \
for genuine "needs slight bending" cases and actually use 10s, 8s, 3s, and \
2s when the fit calls for them. Do not cluster every score around 6-7 out \
of caution.

Output ONLY raw JSON. No markdown code fences, no preamble, no explanation \
outside the JSON. The first character of your response must be `{` and the \
last character must be `}`.

Return exactly:
{"score": <int 1-10>, "reason": "<one sentence explaining the score>"}"""

ADAPTATION_SYSTEM_PROMPT = """You write short-form video ad scripts by \
adapting a proven text skeleton to a specific brand. Follow every rule \
exactly.

RULES:
1. Fill every {SLOT} in the skeleton with brand-specific content. If the \
same {SLOT} name appears more than once in the skeleton, reuse the exact \
same word or phrase, verbatim, at every occurrence - do not add or drop an \
article, change its number, or otherwise alter its grammatical form between \
occurrences. Pick a form for that word that reads correctly in every \
sentence position the skeleton uses it in.
2. Keep the skeleton's rhythm and line structure.
3. HARD LIMIT: stay within +/-15% of the target word count given below. \
These scripts are read on screen in under 8 seconds - going over the \
ceiling is a failure, not a style choice. The skeleton's fixed words plus \
each {SLOT} fill all count toward the total, so budget roughly \
(target word count / number of slots) words per slot before you write - a \
skeleton with 5 slots and a target of 34 words gets about 5-7 words per \
slot, not a full sentence each. After drafting, count every word in each \
variant. If any variant is over the ceiling, cut words from its longest \
slots (shorter concrete nouns, not longer descriptions) until it fits \
before you respond. When in doubt, cut a clause rather than add one.
4. All lowercase. No emojis, no exclamation marks, no em dashes.
5. Never use these words: revolutionary, game-changer, seamless, \
effortless, unlock, supercharge, elevate, streamline, leverage, solution, \
empower.
6. Every slot must be filled with something physically observable or \
nameable - a concrete action, object, or named thing. No abstractions. \
Good: "with 40 tabs open". Bad: "struggling with disorganisation". A slot \
whose name contains HABIT (e.g. {UNCOOL_HABIT_1}) must always be a \
concrete action or behavior - a short clause describing something someone \
does - never a single adjective or trait word, even when it sits right \
next to a trait slot like {POSITIVE_ADJECTIVE}. Good: "eating the same \
four things on rotation". Bad: "boring" (that's a trait, not a habit).
7. The brand name appears exactly once, as a specific action a specific \
person is caught doing in the middle of their own life - never as a \
recommendation, a conclusion, or the moral of the story. It must read like \
"she does X", not "the fix is X" or "just use X". This holds even when the \
skeleton's brand slot sits in the payoff/last line (e.g. a "green flag" or \
punchline) - phrase that slot as one more observed moment, not a summary of \
the brand's value. Good: "speedrunning flashcards on youlearn", "watching \
him rebuild the onboarding doc in notion at 1am the night before it's due". \
Bad: "building the whole thing inside notion", "just use notion for \
everything" - both read as an ad's conclusion, not an observed action. \
Never in the first line.
8. Name at least one real competitor or one concrete physical object.
9. You may invent a vivid phrase that isn't in the skeleton if it makes a \
line land harder - the skeleton is a rhythm guide, not a fill-in-the-blank \
form.
10. It must sound like something a person said out loud, never like \
something a brand wrote.

You will be asked for one variant at a time, across 3 separate requests. \
Each variant must independently satisfy every rule above, and must differ \
meaningfully in wording and specific details from any variants already \
shown to you in this request.

Output ONLY raw JSON. No markdown code fences, no preamble, no explanation \
outside the JSON. The first character of your response must be `{` and the \
last character must be `}`.

Return exactly:
{"variant": "<the single variant text>"}"""

SCORING_SYSTEM_PROMPT = """You are a strict short-form video ad copy judge. \
You will be given 3 script variants adapted from the same skeleton for the \
same brand.

Score each variant 1-10 (integers) on:
- hook_strength: does the opening line grab attention and create curiosity
- specificity: are the details concrete, nameable, and physically \
observable rather than vague
- sounds_human: does it read like something a real person said out loud, \
not brand copy

Then pick the single strongest variant overall and explain why in 1-2 \
sentences.

Output ONLY raw JSON. No markdown code fences, no preamble, no explanation \
outside the JSON. The first character of your response must be `{` and the \
last character must be `}`.

Return exactly:
{"scores": [
  {"variant_index": 0, "hook_strength": <int>, "specificity": <int>, "sounds_human": <int>},
  {"variant_index": 1, "hook_strength": <int>, "specificity": <int>, "sounds_human": <int>},
  {"variant_index": 2, "hook_strength": <int>, "specificity": <int>, "sounds_human": <int>}
], "winner_index": <int>, "winner_reasoning": "<1-2 sentence explanation>"}"""

CREATIVE_BRIEF_SYSTEM_PROMPT = """You are writing a short creator brief for \
a single short-form video ad. You will be given the winning script, this \
format's default audio_mood and its visual_mechanic, and the brand profile.

The default audio_mood is a starting point, not a fixed rule. Keep it \
unless the brand's tone clearly calls for something else - override it only \
when justified, and always say in audio_note whether you kept the default \
or changed it, and why.

audio_mood must be exactly one of these four values: meme_chaotic, \
sad_reflective, chill_aspirational, tense_build.

Write:
- audio_mood: one of the four values above.
- audio_note: one line describing what kind of sound fits this specific \
brand given the chosen audio_mood - a genre, an instrument/tempo/key \
description, or the style of a trending sound. Concrete enough that an \
editor could go pick a real track. Never name a specific copyrighted song \
or artist. State whether this is the format's default mood or an override, \
and if it's an override, why the brand's tone demanded the change.
- performance_note: one line naming the specific emotion the on-screen \
person should be playing while delivering this script (e.g. "quiet envy", \
"secondhand embarrassment", "flat disapproval") and, briefly, how it shows \
on their face or body.

Output ONLY raw JSON. No markdown code fences, no preamble, no explanation \
outside the JSON. The first character of your response must be `{` and the \
last character must be `}`.

Return exactly:
{"audio_mood": "<one of the four values>", "audio_note": "<one line>", \
"performance_note": "<one line>"}"""


@dataclass
class BrandProfile:
    brand_name: str
    one_liner: str
    niche: str
    icp: str
    core_pain: str
    the_hard_way: str
    alternatives: list
    named_competitors: list
    tone: list
    banned_claims: list


REQUIRED_KEYS = [f.name for f in dataclasses.fields(BrandProfile)]


def fetch_page(url: str) -> requests.Response:
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    return resp


def extract_body_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    body = soup.find("body") or soup
    return " ".join(body.get_text(separator=" ").split())


def extract_meta(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    def meta_content(attrs):
        tag = soup.find("meta", attrs=attrs)
        return tag["content"].strip() if tag and tag.get("content") else ""

    return {
        "og_title": meta_content({"property": "og:title"}),
        "og_description": meta_content({"property": "og:description"}),
        "meta_description": meta_content({"name": "description"}),
    }


def fetch_jina_markdown(url: str) -> str:
    jina_url = f"https://r.jina.ai/{url}"
    resp = requests.get(jina_url, headers={"User-Agent": USER_AGENT}, timeout=60)
    resp.raise_for_status()
    return resp.text.strip()


def build_user_content(url: str, body_text: str, meta: dict) -> str:
    return (
        f"URL: {url}\n"
        f"og:title: {meta['og_title']}\n"
        f"og:description: {meta['og_description']}\n"
        f"meta description: {meta['meta_description']}\n\n"
        f"PAGE TEXT:\n{body_text}"
    )


def call_claude(client: anthropic.Anthropic, system_prompt: str, content: str) -> str:
    response = client.messages.create(
        model=MODEL,
        max_tokens=4096,
        system=system_prompt,
        messages=[{"role": "user", "content": content}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def call_claude_json(client, system_prompt: str, content: str, validate_fn, max_attempts: int = 2) -> dict:
    """Call Claude, parse the response as JSON, and validate it. Retries
    (each time feeding the validation error back to the model) up to
    max_attempts times; raises the last error if none pass validation."""
    current_content = content
    last_error = None
    for _ in range(max_attempts):
        raw = call_claude(client, system_prompt, current_content)
        try:
            data = json.loads(raw)
            validate_fn(data)
            return data
        except (json.JSONDecodeError, ValueError, TypeError) as e:
            last_error = e
            current_content = (
                content
                + "\n\nYour previous output was invalid (" + str(e) + "). "
                "Return ONLY valid raw JSON, no other text, no markdown fences."
            )
    raise last_error


def validate_brand_profile(data: dict) -> None:
    missing = [k for k in REQUIRED_KEYS if k not in data]
    if missing:
        raise ValueError(f"Missing required keys: {missing}")


def get_brand_profile(client: anthropic.Anthropic, content: str) -> BrandProfile:
    data = call_claude_json(client, SYSTEM_PROMPT, content, validate_brand_profile)
    return BrandProfile(**{k: data[k] for k in REQUIRED_KEYS})


# --- Stage two: format selection, adaptation, scoring ---

def load_formats(path: str = os.path.join("formats", "library.json")) -> list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_format_score_content(profile: BrandProfile, fmt: dict) -> str:
    format_summary = {
        "id": fmt["id"],
        "hook_archetype": fmt["hook_archetype"],
        "why_it_works": fmt["why_it_works"],
        "text_skeleton": fmt["text_skeleton"],
    }
    return (
        "BRAND PROFILE:\n" + json.dumps(asdict(profile), indent=2) + "\n\n"
        "FORMAT:\n" + json.dumps(format_summary, indent=2)
    )


def validate_format_score(data: dict) -> None:
    if "score" not in data or "reason" not in data:
        raise ValueError("Missing score or reason")
    if not isinstance(data["score"], int) or not (1 <= data["score"] <= 10):
        raise ValueError("score must be an integer from 1 to 10")
    if not isinstance(data["reason"], str) or not data["reason"].strip():
        raise ValueError("reason must be a non-empty string")


def score_format(client: anthropic.Anthropic, profile: BrandProfile, fmt: dict) -> dict:
    content = build_format_score_content(profile, fmt)
    data = call_claude_json(client, FORMAT_SCORE_SYSTEM_PROMPT, content, validate_format_score)
    return {"id": fmt["id"], "score": data["score"], "reason": data["reason"]}


def select_format(client: anthropic.Anthropic, profile: BrandProfile, formats: list):
    """Score every format independently against the brand, then take the
    highest score. Because each call only ever returns a score for the one
    format it was given, there is no id for the model to invent."""
    scores = []
    for fmt in formats:
        print(f"scoring format: {fmt['id']}", file=sys.stderr)
        scores.append(score_format(client, profile, fmt))

    ranked = sorted(scores, key=lambda s: s["score"], reverse=True)
    top = ranked[0]
    chosen = next(f for f in formats if f["id"] == top["id"])
    return chosen, top["reason"], ranked


def print_format_scores(ranked_scores: list) -> None:
    print("\n--- FORMAT SCORES ---")
    for i, s in enumerate(ranked_scores):
        marker = "  <-- chosen" if i == 0 else ""
        print(f"{s['score']:>2}/10  {s['id']}{marker}")
        print(f"       {s['reason']}")


def build_adaptation_content(
    chosen_format: dict, profile: BrandProfile, variant_number: int, previous_variants: list
) -> str:
    content = (
        f"TEXT SKELETON:\n{chosen_format['text_skeleton']}\n\n"
        f"WHY IT WORKS:\n{chosen_format['why_it_works']}\n\n"
        f"TARGET WORD COUNT: {chosen_format['word_count']} "
        "(hard limit: +/-15%)\n\n"
        f"BRAND PROFILE:\n{json.dumps(asdict(profile), indent=2)}\n\n"
        f"This is variant {variant_number} of 3."
    )
    if previous_variants:
        content += (
            "\n\nALREADY GENERATED VARIANTS (this new one must differ "
            "meaningfully in wording and specific details from each of "
            "these):\n" + "\n".join(f"- {v}" for v in previous_variants)
        )
    return content


def validate_single_variant(data: dict) -> None:
    if "variant" not in data:
        raise ValueError("Missing variant")
    if not isinstance(data["variant"], str) or not data["variant"].strip():
        raise ValueError("variant must be a non-empty string")


def generate_single_variant(
    client: anthropic.Anthropic,
    chosen_format: dict,
    profile: BrandProfile,
    variant_number: int,
    previous_variants: list,
    max_word_attempts: int = 2,
) -> dict:
    """Generate one variant. Retries the word-count constraint at most
    max_word_attempts times; if it still isn't within +/-15% of the target,
    keeps the closest attempt and flags it instead of looping further."""
    target = chosen_format["word_count"]
    lower = target * 0.85
    upper = target * 1.15
    base_content = build_adaptation_content(
        chosen_format, profile, variant_number, previous_variants
    )

    attempts = []  # (text, word_count)
    content = base_content
    for _ in range(max_word_attempts):
        data = call_claude_json(client, ADAPTATION_SYSTEM_PROMPT, content, validate_single_variant)
        text = data["variant"]
        word_count = len(text.split())
        attempts.append((text, word_count))

        if lower <= word_count <= upper:
            return {"text": text, "word_count": word_count, "length_flagged": False}

        content = (
            base_content
            + f"\n\nYour previous attempt was {word_count} words. It must be "
            f"between {lower:.0f} and {upper:.0f} words. Rewrite it to fit "
            "while still following every rule."
        )

    closest_text, closest_word_count = min(attempts, key=lambda t: abs(t[1] - target))
    return {
        "text": closest_text,
        "word_count": closest_word_count,
        "length_flagged": True,
        "length_flag_reason": (
            f"{closest_word_count} words vs target {target} (+/-15% band: "
            f"{lower:.0f}-{upper:.0f}); closest of {max_word_attempts} attempts, "
            "kept rather than looping further"
        ),
    }


def generate_variants(client: anthropic.Anthropic, chosen_format: dict, profile: BrandProfile) -> list:
    variants = []
    previous_texts = []
    for i in range(1, 4):
        print(f"generating variant {i}/3", file=sys.stderr)
        result = generate_single_variant(client, chosen_format, profile, i, previous_texts)
        variants.append(result)
        previous_texts.append(result["text"])
    return variants


def build_scoring_content(variants: list) -> str:
    return "\n\n".join(f"VARIANT {i}:\n{v['text']}" for i, v in enumerate(variants))


def validate_scoring(data: dict) -> None:
    required = ("scores", "winner_index", "winner_reasoning")
    missing = [k for k in required if k not in data]
    if missing:
        raise ValueError(f"Missing required keys: {missing}")
    scores = data["scores"]
    if not isinstance(scores, list) or len(scores) != 3:
        raise ValueError("scores must be a list of exactly 3 entries")
    for s in scores:
        for key in ("hook_strength", "specificity", "sounds_human"):
            if key not in s:
                raise ValueError(f"score entry missing {key}")
    if not isinstance(data["winner_index"], int) or not (0 <= data["winner_index"] < 3):
        raise ValueError("winner_index must be an integer in range 0-2")


def score_variants(client: anthropic.Anthropic, variants: list) -> dict:
    content = build_scoring_content(variants)
    return call_claude_json(client, SCORING_SYSTEM_PROMPT, content, validate_scoring)


VALID_AUDIO_MOODS = {"meme_chaotic", "sad_reflective", "chill_aspirational", "tense_build"}


def build_creative_brief_content(chosen_format: dict, profile: BrandProfile, winner_text: str) -> str:
    return (
        f"DEFAULT AUDIO MOOD (starting point, override only if the brand's "
        f"tone clearly calls for it): {chosen_format['audio_mood']}\n"
        f"VISUAL MECHANIC: {chosen_format['visual_mechanic']}\n\n"
        f"WINNING SCRIPT:\n{winner_text}\n\n"
        f"BRAND PROFILE:\n{json.dumps(asdict(profile), indent=2)}"
    )


def validate_creative_brief(data: dict) -> None:
    for key in ("audio_mood", "audio_note", "performance_note"):
        if key not in data or not isinstance(data[key], str) or not data[key].strip():
            raise ValueError(f"Missing or empty {key}")
    if data["audio_mood"] not in VALID_AUDIO_MOODS:
        raise ValueError(
            f"audio_mood {data['audio_mood']!r} is not one of {sorted(VALID_AUDIO_MOODS)}"
        )


def generate_creative_brief(
    client: anthropic.Anthropic, chosen_format: dict, profile: BrandProfile, winner_text: str
) -> dict:
    content = build_creative_brief_content(chosen_format, profile, winner_text)
    return call_claude_json(client, CREATIVE_BRIEF_SYSTEM_PROMPT, content, validate_creative_brief)


def main():
    parser = argparse.ArgumentParser(description="Stage one: brand ingestion")
    parser.add_argument("--url", required=True, help="Brand's website URL")
    args = parser.parse_args()
    url = args.url

    print("fetching", file=sys.stderr)
    resp = fetch_page(url)
    meta = extract_meta(resp.text)
    body_text = extract_body_text(resp.text)

    if len(body_text) < MIN_BODY_TEXT_LENGTH:
        body_text = fetch_jina_markdown(url)

    content = build_user_content(url, body_text, meta)

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=60.0)

    print("extracting profile", file=sys.stderr)
    profile = get_brand_profile(client, content)

    os.makedirs("out", exist_ok=True)
    safe_name = "".join(
        c if c.isalnum() or c in ("-", "_") else "_" for c in profile.brand_name
    ).strip("_") or "brand"
    out_path = os.path.join("out", f"{safe_name}_profile.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(asdict(profile), f, indent=2, ensure_ascii=False)

    print(json.dumps(asdict(profile), indent=2, ensure_ascii=False))
    print(f"\nSaved profile to {out_path}", file=sys.stderr)

    # --- Stage two: format selection, adaptation, scoring ---

    formats = load_formats()

    chosen_format, selection_reason, format_scores = select_format(client, profile, formats)
    print_format_scores(format_scores)

    variants = generate_variants(client, chosen_format, profile)

    print("scoring", file=sys.stderr)
    scoring = score_variants(client, variants)
    winner_index = scoring["winner_index"]
    winner = variants[winner_index]["text"]

    print("writing creator brief", file=sys.stderr)
    brief_data = generate_creative_brief(client, chosen_format, profile, winner)

    creator_brief = {
        "on_screen_text": winner,
        "base_clip": chosen_format["base_clip"],
        "audio_mood": brief_data["audio_mood"],
        "audio_note": brief_data["audio_note"],
        "visual_mechanic": chosen_format["visual_mechanic"],
        "performance_note": brief_data["performance_note"],
        "format_reason": selection_reason,
    }

    copy_output = {
        "brand_name": profile.brand_name,
        "chosen_format": chosen_format,
        "format_scores": format_scores,
        "selection_reason": selection_reason,
        "variants": variants,
        "scores": scoring["scores"],
        "winner_index": winner_index,
        "winner_reasoning": scoring["winner_reasoning"],
        "winner": winner,
        "creator_brief": creator_brief,
    }

    copy_path = os.path.join("out", f"{safe_name}_copy.json")
    with open(copy_path, "w", encoding="utf-8") as f:
        json.dump(copy_output, f, indent=2, ensure_ascii=False)

    print("\n--- WINNING COPY ---")
    print(winner)
    print("\n--- CREATOR BRIEF ---")
    print(json.dumps(creator_brief, indent=2, ensure_ascii=False))
    print(f"\nSaved copy to {copy_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
