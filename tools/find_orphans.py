#!/usr/bin/env python3
"""Procura funcoes orfas ANTES de o jogo bater nelas.

O problema: o rexglue so emite funcoes que a analise estatica alcanca. Rotinas
chamadas exclusivamente por ponteiro (vtables, tabelas de callbacks) nao sao
alcancadas, e o jogo so morre quando la chega:

    [FATAL] Call to invalid or unregistered function at guest address 0x...

Descobri-las uma a uma custa um ciclo completo de codegen + build + arranque
(~6 min cada). Este script tenta apanha-las todas de uma vez.

Como: varre as regioes de DADOS da imagem a procura de valores big-endian de 32
bits que apontem para dentro da regiao de codigo, e cruza-os com a lista de
funcoes que o codegen ja emitiu (PPCFuncMappings em generated/default/gh3_init.cpp).
O que sobra sao candidatos a orfa.

Nao varre a regiao de CODIGO de proposito: uma instrucao lwz codifica-se como
0x82.. e seria indistinguivel de um ponteiro, enchendo isto de falsos positivos.

Cada candidato passa ainda por dois filtros de plausibilidade:
  - a instrucao no alvo tem de descodificar para algo que nao seja lixo;
  - a palavra ANTERIOR ao alvo deve ser um terminador (blr/b/bctr) ou padding,
    que e o que se ve antes de um inicio de funcao a serio.

Os candidatos sao SUGESTOES. Confirma os que parecerem duvidosos com
    python tools/xex_image.py <xex> --disasm <addr>
antes de os meter no config.

Uso:
    python find_orphans.py <xex> [--init generated/default/gh3_init.cpp]
"""

import argparse
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from xex_image import XexImage, decode, sweep  # noqa: E402

MAPPING_RE = re.compile(r"\{\s*0x([0-9A-Fa-f]{8})\s*,")
HINT_RE = re.compile(r'"0x([0-9A-Fa-f]{8})"\s*=\s*\{\s*end\s*=\s*0x([0-9A-Fa-f]{8})')


def load_emitted(path):
    """Enderecos ja emitidos, lidos da tabela PPCFuncMappings."""
    with open(path, "r", errors="replace") as fh:
        return {int(m, 16) for m in MAPPING_RE.findall(fh.read())}


def load_denied(path):
    """Enderecos a excluir mesmo que parecam plausiveis.

    Sao os que partem a compilacao do codigo gerado ("use of undeclared label"):
    pontos de entrada secundarios cujo bloco tem saltos a atravessar a fronteira.
    """
    if not path or not os.path.exists(path):
        return set()
    out = set()
    with open(path, "r", errors="replace") as fh:
        for line in fh:
            line = line.split("#", 1)[0].strip()
            if line:
                out.add(int(line, 16))
    return out


def load_hints(path):
    """Fronteiras ja declaradas a mao, para nao colidir com elas."""
    if not path or not os.path.exists(path):
        return []
    with open(path, "r", errors="replace") as fh:
        return [(int(a, 16), int(b, 16)) for a, b in HINT_RE.findall(fh.read())]


def resolve_overlaps(candidates, existing):
    """Trunca cada candidato onde comeca a funcao seguinte.

    O rexglue recusa o manifest inteiro se duas fronteiras se sobrepuserem
    ("Overlapping boundaries"), e a varredura produz sobreposicoes de propria
    natureza: quando um bloco tem varios pontos de entrada, todos varrem ate ao
    mesmo terminador e os intervalos ficam encaixados uns nos outros.

    A resolucao e cortar o intervalo mais exterior no inicio do interior. O
    codigo do primeiro passa a cair no segundo, que e exatamente o que a
    maquina faz -- so que agora declarado como duas funcoes em vez de uma.

    Candidatos que comecem exatamente onde ja existe uma fronteira curada a mao
    sao descartados: essa ja esta tratada.
    """
    existing_starts = {start for start, _ in existing}
    kept = [c for c in candidates if c[0] not in existing_starts]

    starts = sorted({start for start, _ in existing} | {c[0] for c in kept})
    resolved, clamped = [], 0
    for start, end, meta in kept:
        nxt = next((s for s in starts if s > start), None)
        if nxt is not None and end > nxt:
            end = nxt
            clamped += 1
        if end > start:
            resolved.append((start, end, meta))
    return resolved, clamped


def plausible_start(image, addr, code_lo, code_hi):
    """Filtra candidatos que nao parecem inicio de funcao."""
    if addr % 4 or not (code_lo <= addr < code_hi):
        return None

    insn = image.word(addr)
    if insn in (0, 0xFFFFFFFF):
        return None
    text, kind, _ = decode(insn, addr)
    if text.startswith("<op"):
        return None  # opcode que nem sequer sabemos nomear

    # O que costuma estar imediatamente antes de uma funcao.
    if addr - 4 >= code_lo:
        prev = image.word(addr - 4)
        prev_text, prev_kind, _ = decode(prev, addr - 4)
        clean = prev_kind == "end" or prev == 0x60000000 or prev == 0
    else:
        clean = True
    return text, clean


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("xex")
    ap.add_argument("--init", default="generated/default/gh3_init.cpp")
    ap.add_argument("--hints", default="config/gh3_functions.toml",
                    help="fronteiras curadas a mao, para nao colidir com elas")
    ap.add_argument("--deny", default="config/gh3_orphans_denied.txt",
                    help="enderecos a excluir (partem a compilacao)")
    ap.add_argument("--code-base", type=lambda s: int(s, 0), default=0x820D0000)
    ap.add_argument("--code-size", type=lambda s: int(s, 0), default=0x7FF410)
    ap.add_argument("--all", action="store_true",
                    help="mostra tambem os candidatos sem terminador antes (mais ruido)")
    args = ap.parse_args()

    if not os.path.exists(args.init):
        raise SystemExit(f"[ERRO] nao encontrei {args.init} -- corre o codegen primeiro")

    emitted = load_emitted(args.init)
    denied = load_denied(args.deny)
    img = XexImage(args.xex)
    code_lo = args.code_base
    code_hi = args.code_base + args.code_size

    print(f"funcoes ja emitidas : {len(emitted):,}")
    print(f"regiao de codigo    : 0x{code_lo:08X}-0x{code_hi:08X}")

    regions = [
        (img.load_address, code_lo, "dados antes do codigo"),
        (code_hi, img.stored_end_va, "dados depois do codigo"),
    ]

    candidates = {}
    for lo, hi, label in regions:
        if hi <= lo:
            continue
        blob = img.read(lo, hi - lo)
        hits = 0
        for off in range(0, len(blob) - 3, 4):
            value = struct.unpack_from(">I", blob, off)[0]
            if code_lo <= value < code_hi and value not in emitted and value not in denied:
                candidates.setdefault(value, []).append(lo + off)
                hits += 1
        print(f"  {label}: 0x{lo:08X}-0x{hi:08X}  ->  {hits} referencias")

    print(f"\nenderecos distintos nao emitidos: {len(candidates)}")

    strong, weak = [], []
    for addr in sorted(candidates):
        checked = plausible_start(img, addr, code_lo, code_hi)
        if not checked:
            continue
        (strong if checked[1] else weak).append((addr, checked[0]))

    print(f"  plausiveis (terminador antes) : {len(strong)}")
    print(f"  duvidosos  (sem terminador)   : {len(weak)}")

    chosen = strong + (weak if args.all else [])
    if not chosen:
        print("\nNada a acrescentar.")
        return 0

    swept = []
    for addr, _first in sorted(chosen):
        end, listing = sweep(img, addr)
        if end is None:
            print(f'# "0x{addr:08X}" SEM terminador em 4 KB -- verificar a mao')
            continue
        swept.append((addr, end, (listing[-1][2], len(candidates[addr]))))

    existing = load_hints(args.hints)
    resolved, clamped = resolve_overlaps(swept, existing)
    print(f"  fronteiras curadas a mao lidas : {len(existing)}")
    print(f"  truncados por sobreposicao     : {clamped}")
    print(f"  a emitir                       : {len(resolved)}")

    print("\n# --- candidatos a orfa (confirmar antes de usar) ---")
    print("[functions]")
    for start, end, (term, refs) in resolved:
        print(f'"0x{start:08X}" = {{ end = 0x{end:08X} }}'
              f'  # {(end - start) // 4} instr, {term}, {refs} ref(s)')
    return 0


if __name__ == "__main__":
    sys.exit(main())
