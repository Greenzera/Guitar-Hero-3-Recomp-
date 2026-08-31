#!/usr/bin/env python3
"""Descobre que shaders sao exclusivos de um momento do jogo.

Porque existe: o GH3 usa ~145 shaders so nos menus. Para escrever um renderer
nativo da autoestrada e preciso saber QUAIS desenham a autoestrada -- e a unica
forma barata de os isolar e por diferenca: despejar num momento, despejar
noutro, e ficar com o que so aparece no segundo.

Fluxo:
    1. dump_shaders ligado, chegar ao menu, fechar  -> snapshot "menu"
    2. apagar a pasta, jogar uma musica, fechar     -> snapshot "gameplay"
    3. python shader_diff.py menu.txt gameplay.txt

O que sobra sao candidatos: autoestrada, notas, HUD, banda e palco. Cruzar
depois com os hashes que o log escreve em "Creating graphics pipeline with
VS <hash> PS <hash>" para saber quais sao mesmo usados a desenhar.

Uso:
    python shader_diff.py <base.txt> <novo.txt> [--dump-dir <pasta>]
"""

import argparse
import os
import sys


def load(path):
    entries = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            parts = line.split()
            if len(parts) == 2:
                entries[parts[0]] = parts[1]
    return entries


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base")
    ap.add_argument("novo")
    ap.add_argument("--dump-dir", default=None,
                    help="pasta dos .ucode para reportar o tamanho de cada candidato")
    args = ap.parse_args()

    base = load(args.base)
    novo = load(args.novo)
    so_novos = {h: t for h, t in novo.items() if h not in base}

    print(f"base     : {len(base)} shaders")
    print(f"novo     : {len(novo)} shaders")
    print(f"exclusivos do novo: {len(so_novos)}")
    if not so_novos:
        print("\nNada exclusivo -- os dois momentos usam os mesmos shaders.")
        return 0

    # Shaders maiores tendem a ser os interessantes (material da autoestrada,
    # iluminacao do palco); os de 2-3 instrucoes sao quase sempre blits e copias.
    rows = []
    for h, t in so_novos.items():
        size = 0
        if args.dump_dir:
            p = os.path.join(args.dump_dir, f"shader_{h}.ucode.bin.{t}")
            if os.path.exists(p):
                size = os.path.getsize(p)
        rows.append((size, h, t))
    rows.sort(reverse=True)

    print("\n  bytes  tipo  hash                (maiores primeiro)")
    for size, h, t in rows:
        print(f"  {size:6d}  {t:4}  {h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
