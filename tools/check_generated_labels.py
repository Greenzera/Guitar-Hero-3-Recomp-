#!/usr/bin/env python3
"""
Find function-boundary hints that split an existing function.

If a hint declares a function start at an address that is really just a branch
target inside another function, codegen emits the containing function with a
`goto loc_<addr>` whose label now lives in a different function -- the build
then fails with "use of undeclared label". One failing file per build makes that
a very slow way to find them, so this checks every generated function at once.

Reports each referenced-but-undefined label; those addresses are bad hints and
should be removed from config/gh3_orphans_denied.txt.
"""
import re
import sys
from pathlib import Path

GEN = Path(__file__).resolve().parent.parent / "generated" / "default"

FUNC_RE = re.compile(r"^DEFINE_REX_FUNC\((\w+)\)")
LABEL_DEF_RE = re.compile(r"^(loc_[0-9A-Fa-f]+):")
LABEL_USE_RE = re.compile(r"goto (loc_[0-9A-Fa-f]+);")


def main():
    bad = {}          # label -> set of enclosing functions
    files = sorted(GEN.glob("*.cpp"))
    if not files:
        sys.exit(f"[ERRO] sem ficheiros gerados em {GEN}")

    for f in files:
        cur = None
        defined = set()
        used = []
        for line in f.read_text(errors="replace").splitlines():
            m = FUNC_RE.match(line)
            if m:
                # flush previous function
                if cur:
                    for lbl in used:
                        if lbl not in defined:
                            bad.setdefault(lbl, set()).add(cur)
                cur = m.group(1)
                defined, used = set(), []
                continue
            m = LABEL_DEF_RE.match(line)
            if m:
                defined.add(m.group(1))
                continue
            m = LABEL_USE_RE.search(line)
            if m:
                used.append(m.group(1))
        if cur:
            for lbl in used:
                if lbl not in defined:
                    bad.setdefault(lbl, set()).add(cur)

    print(f"[i] ficheiros analisados : {len(files)}")
    print(f"[i] labels em falta      : {len(bad)}")
    print()
    if not bad:
        print("nenhum hint parte funcoes - tudo consistente")
        return

    print("=== hints a REMOVER (o endereco e um label interno, nao uma funcao) ===")
    for lbl in sorted(bad):
        addr = lbl.replace("loc_", "0x")
        users = ", ".join(sorted(bad[lbl])[:3])
        print(f'  "{addr}"   usado por {users}')

    print()
    print("=== enderecos, um por linha ===")
    for lbl in sorted(bad):
        print(lbl.replace("loc_", "0x"))


if __name__ == "__main__":
    main()
