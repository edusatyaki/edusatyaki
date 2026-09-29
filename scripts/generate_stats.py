"""Generate the profile stat cards (assets/*.svg) from the GitHub GraphQL API.

Runs daily from .github/workflows/stats.yml. Locally: GITHUB_TOKEN=$(gh auth token) python3 scripts/generate_stats.py
"""
import json
import os
import urllib.request
from datetime import date
from html import escape
from pathlib import Path

LOGIN = "edusatyaki"
OUT = Path(__file__).resolve().parent.parent / "assets"

QUERY = """
query($login: String!) {
  user(login: $login) {
    followers { totalCount }
    repositories(ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false, first: 100) {
      totalCount
      nodes { stargazerCount primaryLanguage { name color } }
    }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { contributionCount date } }
      }
    }
  }
}
"""

THEMES = {
    "light": dict(bg="#ffffff", border="#d0d7de", title="#1f2328", text="#57606a",
                  value="#1f2328", accent="#0969da", track="#eaeef2",
                  heat=["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]),
    "dark": dict(bg="#0d1117", border="#30363d", title="#e6edf3", text="#8b949e",
                 value="#e6edf3", accent="#58a6ff", track="#21262d",
                 heat=["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]),
}
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"


def fetch():
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode(),
        headers={"Authorization": f"bearer {os.environ['GITHUB_TOKEN']}",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        body = json.load(r)
    if "errors" in body:
        raise SystemExit(body["errors"])
    return body["data"]["user"]


def card(w, h, t, title, inner):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'font-family="{FONT}" role="img" aria-label="{escape(title)}">'
            f'<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="10" fill="{t["bg"]}" stroke="{t["border"]}"/>'
            f'<text x="24" y="38" font-size="16" font-weight="600" fill="{t["title"]}">{escape(title)}</text>'
            f'{inner}</svg>')


def overview(u, t):
    repos = u["repositories"]
    cc = u["contributionsCollection"]
    rows = [
        ("Public repositories", repos["totalCount"]),
        ("Stars earned", sum(n["stargazerCount"] for n in repos["nodes"])),
        ("Commits (last 12 months)", cc["totalCommitContributions"]),
        ("Contributions (last 12 months)", cc["contributionCalendar"]["totalContributions"]),
        ("Followers", u["followers"]["totalCount"]),
    ]
    inner = ""
    for i, (label, val) in enumerate(rows):
        y = 78 + i * 30
        inner += (f'<circle cx="30" cy="{y-5}" r="4" fill="{t["accent"]}"/>'
                  f'<text x="44" y="{y}" font-size="14" fill="{t["text"]}">{label}</text>'
                  f'<text x="376" y="{y}" font-size="14" font-weight="600" text-anchor="end" fill="{t["value"]}">{val:,}</text>')
    return card(400, 220, t, "GitHub at a glance", inner)


def languages(u, t):
    counts = {}
    for n in u["repositories"]["nodes"]:
        lang = n["primaryLanguage"]
        if lang:
            c = counts.setdefault(lang["name"], [0, lang["color"] or "#8b949e"])
            c[0] += 1
    top = sorted(counts.items(), key=lambda kv: -kv[1][0])[:6]
    total = sum(c for _, (c, _) in top) or 1
    x, bar = 24, ""
    for name, (c, color) in top:
        w = 352 * c / total
        bar += f'<rect x="{x:.1f}" y="56" width="{w:.1f}" height="10" fill="{color}"/>'
        x += w
    inner = (f'<clipPath id="r"><rect x="24" y="56" width="352" height="10" rx="5"/></clipPath>'
             f'<g clip-path="url(#r)">{bar}</g>')
    for i, (name, (c, color)) in enumerate(top):
        cx, cy = 30 + (i % 2) * 180, 96 + (i // 2) * 28
        inner += (f'<circle cx="{cx}" cy="{cy-5}" r="5" fill="{color}"/>'
                  f'<text x="{cx+12}" y="{cy}" font-size="13" fill="{t["value"]}">{escape(name)}'
                  f'<tspan fill="{t["text"]}"> {c} repos</tspan></text>')
    return card(400, 220, t, "Languages by repository", inner)


def heatmap(u, t):
    weeks = u["contributionsCollection"]["contributionCalendar"]["weeks"]
    total = u["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    days = [d["contributionCount"] for w in weeks for d in w["contributionDays"]]
    peak = max(days) or 1
    cells = ""
    for wi, w in enumerate(weeks):
        for d in w["contributionDays"]:
            n = d["contributionCount"]
            lvl = 0 if n == 0 else min(4, 1 + int(3 * n / peak))
            dow = date.fromisoformat(d["date"]).isoweekday() % 7
            cells += (f'<rect x="{24 + wi*15}" y="{56 + dow*15}" width="12" height="12" rx="2" '
                      f'fill="{t["heat"][lvl]}"><title>{d["date"]}: {n}</title></rect>')
    w = 24 + len(weeks) * 15 + 21
    active = sum(1 for n in days if n)
    longest = run = 0
    for n in days:
        run = run + 1 if n else 0
        longest = max(longest, run)
    # Today may not have a contribution yet; don't let that break the current streak.
    tail = days[:-1] if days and days[-1] == 0 else days
    current = 0
    for n in reversed(tail):
        if not n:
            break
        current += 1

    def v(x):
        return f'<tspan font-weight="600" fill="{t["value"]}">{x}</tspan>'
    foot = (f'<text x="24" y="182" font-size="13" fill="{t["text"]}">'
            f'{v(f"{total:,}")} contributions · {v(active)} active days · '
            f'current streak {v(current)} days · longest streak {v(longest)} days</text>')
    return card(w, 200, t, "Contribution activity, last 12 months", cells + foot)


def main():
    u = fetch()
    OUT.mkdir(exist_ok=True)
    for name, t in THEMES.items():
        (OUT / f"overview-{name}.svg").write_text(overview(u, t))
        (OUT / f"languages-{name}.svg").write_text(languages(u, t))
        (OUT / f"activity-{name}.svg").write_text(heatmap(u, t))


if __name__ == "__main__":
    main()
