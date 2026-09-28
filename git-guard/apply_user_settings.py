#!/usr/bin/env python3
"""Loosen the per-user git rules in every Claude profile (~/.claude*/settings.json).
Run by install.sh only after the installed guard passes its self-test.

Everyday git becomes allowed; the push asks and the branch -D deny go, since
the root-owned guard handles those now. gh asks and destructive denies stay.
Backs each file up as settings.json.bak-git-guard first.
"""
import glob
import json
import os
import shutil

GIT_PREFIXES = ("Bash(git ", "Bash(/usr/bin/git ", "Bash(/usr/local/bin/git ",
                "Bash(/opt/homebrew/bin/git ", "Bash(env * git ")
BRANCH_D = {"Bash(git branch -D*)", "Bash(git -C * branch -D*)"}
ALSO_UNASK = {"Bash(gh auth switch*)"}

for path in sorted(glob.glob(os.path.expanduser("~/.claude*/settings.json"))):
    with open(path) as f:
        data = json.load(f)
    perms = data.get("permissions")
    if not perms:
        continue
    backup = path + ".bak-git-guard"
    if not os.path.exists(backup):
        shutil.copy2(path, backup)
    perms["ask"] = [r for r in perms.get("ask", []) if not r.startswith(GIT_PREFIXES)
                    and r not in ALSO_UNASK]
    perms["deny"] = [r for r in perms.get("deny", []) if r not in BRANCH_D]
    allow = perms.setdefault("allow", [])
    if "Bash(git *)" not in allow:
        allow.append("Bash(git *)")
    tmp = path + ".tmp-git-guard"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    print(f"updated {path}")
