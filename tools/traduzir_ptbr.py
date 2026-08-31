"""Traducao PT-BR, juntando as duas maneiras de encontrar texto no arquivo.

  ancora A -- os 12 bytes antes do texto comecam pelo checksum do ficheiro.
  ancora B -- ha' o marcador de tipo 00 84 00 00 dezasseis bytes antes.

Apanham conjuntos diferentes de frases; juntas cobrem muito mais. Em ambos os
casos o texto portugues e' escrito no espaco exacto do ingles e enchido com
espacos: o jogo percorre as entradas em sequencia e encurtar uma descarrila
tudo o que vem a seguir (testado -- e uma so' letra trocada nao lhe faz mossa).
"""
import collections
import difflib
import os
import re
import struct
import subprocess
import sys
import time
import zlib

import _arquivo_qb as arquivo

B = arquivo.BARRA
RX = re.compile(rb"(?:\x00[\x20-\xff]){2,}\x00\x00")
BOM = re.compile(r"^[\x20-\x7e\xa0-\xff]+$")
LETRA = re.compile(r"[A-Za-z]")
MARCA = bytes.fromhex("00840000")


def ficheiros_do_pak(pak):
    fora = set()
    for i in range(0, len(pak) - 31, 32):
        c = struct.unpack_from(">8I", pak, i)
        if c[0] == 0 and c[1] == 0 and c[2] == 0:
            break
        fora.add(c[4])
    return fora


def varrer(d, validos):
    """-> (lista A por ficheiro, lista B global)"""
    A, Bl = collections.OrderedDict(), []
    for m in RX.finditer(d):
        i = m.start()
        if i % 2 or i < 16:
            continue
        try:
            s = m.group(0)[:-2].decode("utf-16-be")
        except UnicodeDecodeError:
            continue
        if len(s) < 3 or not BOM.match(s) or len(LETRA.findall(s)) < 2:
            continue
        fim = m.end() - 2
        cs = struct.unpack_from(">I", d, i - 12)[0]
        if cs in validos:
            A.setdefault(cs, []).append((i, fim, s))
        elif d[i - 16:i - 12] == MARCA:
            Bl.append((i, fim, cs, s))
    return A, Bl


if "--restaurar" in sys.argv:
    import shutil
    n = 0
    for raiz, _, fs in os.walk(arquivo.BACKUP):
        for f in fs:
            g = os.path.join(raiz, f)
            shutil.copy2(g, os.path.join(arquivo.COMP, os.path.relpath(g, arquivo.BACKUP)))
            n += 1
    print("repostos %d ficheiros; o jogo voltou ao ingles." % n)
    raise SystemExit


pak_o = zlib.decompress(open(arquivo.BACKUP + B + "pak" + B + "qb.pak.xen", "rb").read(), -15)
pab_o = zlib.decompress(open(arquivo.BACKUP + B + "pak" + B + "qb.pab.xen", "rb").read(), -15)
pak_t = open(arquivo.FONTE + B + "PAK" + B + "qb.pak.xen", "rb").read()
pab_t = open(arquivo.FONTE + B + "PAK" + B + "qb.pab.xen", "rb").read()
Ao, Bo = varrer(pab_o, ficheiros_do_pak(pak_o))
At, Bt = varrer(pab_t, ficheiros_do_pak(pak_t))

trocas = {}   # posicao no pab do jogo -> texto portugues
for cs in Ao:
    if cs in At and len(Ao[cs]) == len(At[cs]):
        for n in range(len(Ao[cs])):
            ini, fim, en = Ao[cs][n]
            pt = At[cs][n][2]
            if pt != en and len(pt.encode("utf-16-be")) <= fim - ini:
                trocas[ini] = pt
print("ancora A: %d frases" % len(trocas))

n0 = len(trocas)
sa, sb = [x[3] for x in Bo], [x[3] for x in Bt]
for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, sa, sb, autojunk=False).get_opcodes():
    if tag != "replace" or (i2 - i1) != (j2 - j1):
        continue
    for k in range(i2 - i1):
        i, j = i1 + k, j1 + k
        if Bo[i][2] != Bt[j][2]:
            continue
        ini, fim = Bo[i][0], Bo[i][1]
        pt = sb[j]
        if pt != sa[i] and len(pt.encode("utf-16-be")) <= fim - ini:
            trocas.setdefault(ini, pt)
print("ancora B acrescentou: %d" % (len(trocas) - n0))
print("total: %d frases" % len(trocas))

orig = arquivo.ler_original()
CAUDA = arquivo.cauda_original()
limites, pos = [], 0
for k, (c, d) in enumerate(orig):
    limites.append((pos, pos + len(d), k))
    pos += len(d)
por_ficheiro = collections.OrderedDict()
for ini in sorted(trocas):
    for a, b_, k in limites:
        if a <= ini < b_:
            por_ficheiro.setdefault(k, []).append(ini)
            break
print("espalhadas por %d ficheiros" % len(por_ficheiro))


def instalar(chaves):
    novo = bytearray(pab_o)
    for k in chaves:
        for ini in por_ficheiro[k]:
            fim = ini
            while novo[fim:fim + 2] != bytes(2):
                fim += 2
            d = trocas[ini].encode("utf-16-be")
            d += (" " * ((fim - ini - len(d)) // 2)).encode("utf-16-be")
            novo[ini:fim] = d
    itens, p = [], 0
    for c, d in orig:
        itens.append((c, bytes(novo[p:p + len(d)])))
        p += len(d)
    pak, pab = arquivo.construir(itens, 16384, bytes(novo[p:]))
    arquivo.instalar(pak, pab)


todas = list(por_ficheiro)
instalar(todas)
print()
print("TRADUZIDO: %d frases em %d ficheiros."
      % (sum(len(por_ficheiro[k]) for k in todas), len(todas)))
print("Para voltar ao ingles: python tools/traduzir_ptbr.py --restaurar")
