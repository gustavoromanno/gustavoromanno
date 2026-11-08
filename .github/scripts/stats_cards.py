"""Gera os cartões de estatísticas do perfil (stats/*.svg).

Conta os commits de autoria do dono do token na branch principal de cada
repositório próprio (públicos e privados, sem forks), em vez de depender da
contagem de "contribuições" do GitHub. Só números agregados vão para os
cartões: nenhum nome de repositório privado é exibido.

Uso: GH_TOKEN=<token pessoal com escopo repo> python stats_cards.py [saida]
     python stats_cards.py --demo [saida]   (dados fictícios, para testar o visual)
"""

import json
import os
import sys
import urllib.request
from html import escape
from pathlib import Path

API = "https://api.github.com/graphql"

QUERY = """
query($after: String) {
  viewer {
    id
    login
    pullRequests { totalCount }
    repositories(first: 50, after: $after, ownerAffiliations: OWNER, isFork: false) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        isPrivate
        stargazerCount
        languages(first: 20, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
        defaultBranchRef {
          target { ... on Commit { history(author: {id: $authorId}) { totalCount } } }
        }
      }
    }
  }
}
"""


def graphql(token, query, variables):
    req = urllib.request.Request(
        API,
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "User-Agent": "profile-stats-cards"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.load(resp)
    if body.get("errors"):
        raise SystemExit(f"Erro da API do GitHub: {body['errors']}")
    return body["data"]


def collect(token):
    viewer_id = graphql(token, "{ viewer { id } }", {})["viewer"]["id"]
    query = QUERY.replace("query($after: String)", "query($after: String, $authorId: ID!)")
    stats = {"commits": 0, "stars": 0, "prs": 0, "repos": 0, "private": 0}
    languages = {}
    after = None
    while True:
        viewer = graphql(token, query, {"after": after, "authorId": viewer_id})["viewer"]
        repos = viewer["repositories"]
        stats["prs"] = viewer["pullRequests"]["totalCount"]
        stats["repos"] = repos["totalCount"]
        for repo in repos["nodes"]:
            stats["stars"] += repo["stargazerCount"]
            stats["private"] += repo["isPrivate"]
            ref = repo["defaultBranchRef"]
            if ref and ref["target"]:
                stats["commits"] += ref["target"]["history"]["totalCount"]
            for edge in repo["languages"]["edges"]:
                name = edge["node"]["name"]
                color = edge["node"]["color"] or "#8b949e"
                size, _ = languages.get(name, (0, color))
                languages[name] = (size + edge["size"], color)
        if not repos["pageInfo"]["hasNextPage"]:
            break
        after = repos["pageInfo"]["endCursor"]
    return stats, languages


# --- SVG ---------------------------------------------------------------------

W, H = 360, 190
BG, BORDER, TITLE, TEXT, MUTED = "#0d1117", "#30363d", "#58a6ff", "#c9d1d9", "#8b949e"
FONT = "font-family=\"'Segoe UI', Ubuntu, 'Helvetica Neue', Sans-Serif\""


def frame(title, body):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        f'role="img" aria-label="{escape(title)}">'
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="6" fill="{BG}" stroke="{BORDER}"/>'
        f'<text x="22" y="36" {FONT} font-size="17" font-weight="600" fill="{TITLE}">{escape(title)}</text>'
        f"{body}</svg>"
    )


def fmt(n):
    return f"{n:,}".replace(",", ".")


def stats_svg(s):
    rows = [
        ("Commits", fmt(s["commits"])),
        ("Pull requests", fmt(s["prs"])),
        ("Repositórios", f'{fmt(s["repos"])} ({fmt(s["private"])} privados)'),
        ("Estrelas", fmt(s["stars"])),
    ]
    body = ""
    for i, (label, value) in enumerate(rows):
        y = 74 + i * 29
        body += (
            f'<circle cx="28" cy="{y - 5}" r="4" fill="{TITLE}"/>'
            f'<text x="42" y="{y}" {FONT} font-size="14" fill="{TEXT}">{label}</text>'
            f'<text x="{W - 22}" y="{y}" {FONT} font-size="14" font-weight="600" fill="{TEXT}" '
            f'text-anchor="end">{value}</text>'
        )
    return frame("Estatísticas no GitHub", body)


def languages_svg(languages, top=6):
    ranked = sorted(languages.items(), key=lambda kv: kv[1][0], reverse=True)
    total = sum(size for size, _ in languages.values()) or 1
    shown = ranked[:top]
    rest = total - sum(size for _, (size, _) in shown)
    if rest > 0 and len(ranked) > top:
        shown.append(("Outras", (rest, MUTED)))

    bar_w, x, body = W - 44, 22.0, f'<clipPath id="bar"><rect x="22" y="54" width="{W - 44}" height="10" rx="5"/></clipPath><g clip-path="url(#bar)">'
    for _, (size, color) in shown:
        w = bar_w * size / total
        body += f'<rect x="{x:.2f}" y="54" width="{w + 0.5:.2f}" height="10" fill="{color}"/>'
        x += w
    body += "</g>"
    for i, (name, (size, color)) in enumerate(shown):
        col, row = i % 2, i // 2
        cx, cy = 22 + col * (W - 44) / 2, 92 + row * 26
        body += (
            f'<circle cx="{cx + 5}" cy="{cy - 5}" r="5" fill="{color}"/>'
            f'<text x="{cx + 16}" y="{cy}" {FONT} font-size="13" fill="{TEXT}">{escape(name)} '
            f'<tspan fill="{MUTED}">{100 * size / total:.1f}%</tspan></text>'
        )
    return frame("Linguagens mais usadas", body)


def main():
    args = [a for a in sys.argv[1:] if a != "--demo"]
    out = Path(args[0] if args else "stats")
    if "--demo" in sys.argv:
        stats = {"commits": 1234, "stars": 1, "prs": 113, "repos": 9, "private": 4}
        languages = {
            "Java": (900_000, "#b07219"), "HTML": (300_000, "#e34c26"),
            "JavaScript": (200_000, "#f1e05a"), "CSS": (120_000, "#663399"),
            "TypeScript": (80_000, "#3178c6"), "Python": (30_000, "#3572A5"),
            "PLpgSQL": (20_000, "#336790"), "Shell": (5_000, "#89e051"),
        }
    else:
        token = os.environ.get("GH_TOKEN")
        if not token:
            raise SystemExit("Defina GH_TOKEN com um token pessoal (escopo repo).")
        stats, languages = collect(token)
    out.mkdir(parents=True, exist_ok=True)
    (out / "stats.svg").write_text(stats_svg(stats), encoding="utf-8")
    (out / "languages.svg").write_text(languages_svg(languages), encoding="utf-8")
    print(json.dumps(stats))


if __name__ == "__main__":
    main()
