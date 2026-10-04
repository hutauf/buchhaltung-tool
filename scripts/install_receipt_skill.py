"""Keep the checked-in receipt skill discoverable in this user's Codex skills."""
import os
import argparse
from pathlib import Path
import shutil
ROOT=Path(__file__).resolve().parents[1]

if __name__=="__main__":
    parser=argparse.ArgumentParser(description="Beleg-Skill installieren oder aus dem bisherigen Toolworkspace übernehmen")
    parser.add_argument("--migrate-from",type=Path)
    args=parser.parse_args()
    source=ROOT/"skills/beleg-import"
    codex_base=Path(os.environ.get("CODEX_HOME") or Path.home()/".codex").resolve()
    target=codex_base/"skills/beleg-import"
    marker=target/".bookkeeping-skill-source"
    previous=marker.read_text(encoding="utf8").strip() if marker.is_file() else None
    allowed={str(source)}
    if args.migrate_from:
        old=(args.migrate_from.resolve()/"skills/beleg-import")
        if not (old/"SKILL.md").is_file(): raise SystemExit("Bisherige Skillquelle fehlt")
        allowed.add(str(old))
    if target.exists() and previous not in allowed:
        raise SystemExit("Vorhandener fremder Skill beleg-import bleibt unverändert; Namen/Pfad zuerst klären.")
    target.mkdir(parents=True,exist_ok=True)
    for relative in ("SKILL.md","agents/openai.yaml"):
        destination=target/relative;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source/relative,destination)
    marker.write_text(str(source)+"\n",encoding="utf8")
    print("Skill installiert: "+str(target/"SKILL.md"))
