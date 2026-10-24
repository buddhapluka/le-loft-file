"""Publication des Reels d'essai Le Loft depuis une routine Claude (cloud), même PC éteint (22/10/2026).

Le PC (montage-ia/outils/file_cloud.py pousser) dépose ici les vidéos en attente (videos/) et la file (file.json :
[{"quand": "2026-10-22T13:00", "video": "videos/x.mp4", "legende", "essai": "manuel", "etiquette"}], heure de Paris).
La routine lance ce script à 9 h 02, 13 h 02 et 19 h 02 : il publie l'entrée prévue dans les 30 dernières minutes
(Instagram télécharge la vidéo par son lien raw.githubusercontent.com, dépôt public), puis note la publication dans
journal.jsonl sur la branche claude/journal, que le PC relit (file_cloud.py synchro). Passé 30 min, une entrée n'est
plus publiée ici : le PC prend le relais 40 min après l'heure prévue, sans risque de doublon.
Jeton Instagram : dépôt privé buddhapluka/le-loft-secrets (ig-token.json), cloné par la routine à côté de celui-ci.
Aucune dépendance hors bibliothèque standard.
"""
import datetime as dt, json, os, subprocess, sys, time, urllib.parse, urllib.request
from zoneinfo import ZoneInfo

IG = "https://graph.instagram.com/v23.0/"
RAW = "https://raw.githubusercontent.com/buddhapluka/le-loft-file/main/"
FENETRE = dt.timedelta(minutes=30)


def git(*a, cwd=None):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True)


def api(chemin, donnees=None, **params):
    url = IG + chemin + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, data=urllib.parse.urlencode(donnees).encode() if donnees else None)
    try:
        with urllib.request.urlopen(req, timeout=60) as r: return json.load(r)
    except urllib.error.HTTPError as e: return json.loads(e.read() or b"{}")


def journal_lu():
    if git("fetch", "-q", "origin", "claude/journal").returncode: return []
    r = git("show", "origin/claude/journal:journal.jsonl")
    return [json.loads(l) for l in r.stdout.splitlines() if l.strip()] if r.returncode == 0 else []


def journal_ecrit(entree):
    d = "/tmp/journal"
    git("worktree", "remove", "--force", d)
    if git("rev-parse", "-q", "--verify", "origin/claude/journal").returncode == 0:
        git("worktree", "add", "-q", "--detach", d, "origin/claude/journal")
    else:
        git("worktree", "add", "-q", "--detach", d)
        git("checkout", "-q", "--orphan", "claude/journal", cwd=d); git("rm", "-rfq", ".", cwd=d)
    with open(os.path.join(d, "journal.jsonl"), "a", encoding="utf-8") as f: f.write(json.dumps(entree, ensure_ascii=False) + "\n")
    git("add", "journal.jsonl", cwd=d)
    git("-c", "user.name=Routine Le Loft", "-c", "user.email=routine@le-loft.invalid", "commit", "-qm",
        f"Publié : {entree['etiquette']}", cwd=d)
    r = git("push", "-q", "origin", "HEAD:claude/journal", cwd=d)
    print("journal envoyé" if r.returncode == 0 else f"ATTENTION journal non envoyé : {r.stderr.strip()[:300]}")


def lire_jeton():
    """Variable IG_TOKEN, sinon ig-token.json du dépôt PRIVÉ buddhapluka/le-loft-secrets, cloné par la routine à côté
    de celui-ci (le PC y pousse le jeton à chaque renouvellement)."""
    if os.environ.get("IG_TOKEN"): return os.environ["IG_TOKEN"]
    ici = os.path.dirname(os.path.abspath(__file__))
    for p in (os.path.join(ici, "..", "le-loft-secrets", "ig-token.json"), "/home/user/le-loft-secrets/ig-token.json"):
        if os.path.exists(p): return json.load(open(p))["access_token"]
    sys.exit("ERREUR : jeton Instagram introuvable (ni IG_TOKEN, ni dépôt le-loft-secrets)")


def main():
    jeton = lire_jeton()
    moi = api("me", fields="username", access_token=jeton)
    if "username" not in moi: sys.exit(f"ERREUR jeton refusé par Instagram : {moi}")
    print("compte :", moi["username"])
    maintenant = dt.datetime.now(ZoneInfo("Europe/Paris")).replace(tzinfo=None)
    faites = {j["etiquette"] for j in journal_lu()}
    file = json.load(open("file.json", encoding="utf-8"))
    dues = [e for e in file if e["etiquette"] not in faites
            and dt.timedelta(0) <= maintenant - dt.datetime.fromisoformat(e["quand"]) <= FENETRE]
    if not dues: print(f"RIEN À PUBLIER ({maintenant:%d/%m %H:%M}, {len(file)} entrées dans la file)"); return
    e = sorted(dues, key=lambda x: x["quand"])[0]
    print(f"== {e['etiquette']} (prévu {e['quand']})", flush=True)
    url = RAW + urllib.parse.quote(e["video"])
    params = {"media_type": "REELS", "video_url": url, "caption": e["legende"], "access_token": jeton}
    if e.get("essai"): params["trial_params"] = json.dumps({"graduation_strategy": {"manuel": "MANUAL", "auto": "SS_PERFORMANCE"}[e["essai"]]})
    r = api("me/media", params)
    if "id" not in r: sys.exit(f"ERREUR conteneur refusé : {r}")
    for _ in range(90):  # jusqu'à 15 min
        s = api(r["id"], fields="status_code,status", access_token=jeton)
        if s.get("status_code") == "FINISHED": break
        if s.get("status_code") in ("ERROR", "EXPIRED"): sys.exit(f"ERREUR traitement refusé : {s}")
        time.sleep(10)
    else: sys.exit("ERREUR traitement trop long, rien n'est publié")
    p = api("me/media_publish", {"creation_id": r["id"], "access_token": jeton})
    if "id" not in p: sys.exit(f"ERREUR publication refusée : {p}")
    lien = api(p["id"], fields="permalink", access_token=jeton).get("permalink")
    print("PUBLIÉ :", lien, flush=True)
    journal_ecrit({"etiquette": e["etiquette"], "quand": e["quand"], "video": os.path.basename(e["video"]), "essai": e.get("essai"),
                   "id": p["id"], "lien": lien, "le": dt.datetime.now(ZoneInfo("Europe/Paris")).isoformat(timespec="seconds")})


if __name__ == "__main__":
    main()
