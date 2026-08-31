"""Le e reconstroi o arquivo qb (pak = indice, pab = dados).

Formato, confirmado nos 449 ficheiros do original:
  - registo de 32 bytes: +0x00 checksum da extensao, +0x04 offset, +0x08 tamanho,
    +0x10 checksum do nome; os offsets sao relativos ao inicio do PAK, porque o
    jogo carrega o pab imediatamente a seguir ao indice.
  - o tamanho declarado conta um cabecalho de 32 bytes que nao esta no pab, por
    isso os bytes guardados sao arredondar_para_cima(tamanho - 32, 32).
  - a base (= tamanho do pak) e' livre: confirmado com uma experiencia de
    controlo que deslocou o original 2048 bytes e o jogo aguentou.
"""
import os
import struct
import zlib

BARRA = chr(92)
RAIZ = "C:" + BARRA + "Users" + BARRA + "Luis" + BARRA + "Desktop" + BARRA + "GUITAR HERO 3 RECOMP"
COMP = RAIZ + BARRA + "game" + BARRA + "DATA" + BARRA + "COMPRESSED"
BACKUP = RAIZ + BARRA + "game" + BARRA + "DATA" + BARRA + "_originais-antes-da-traducao"
FONTE = RAIZ + BARRA + "Tradutor_Guitar_Hero_III_Legends_Of_Rock" + BARRA + "DATA"
SETOR = 2048


def guardados(tamanho):
    return (tamanho - 32 + 31) // 32 * 32


def ler(pak_bytes, pab_bytes):
    """-> lista de (registo, dados) por ordem de offset."""
    regs = []
    for i in range(0, len(pak_bytes) - 31, 32):
        c = list(struct.unpack_from(">8I", pak_bytes, i))
        if c[0] == 0 and c[1] == 0 and c[2] == 0:
            break
        regs.append(c)
    base = len(pak_bytes)
    fora = []
    for c in regs:
        ini = c[1] - base
        fora.append((c, pab_bytes[ini:ini + guardados(c[2])]))
    return fora


def ler_original():
    pak = zlib.decompress(open(os.path.join(BACKUP, "pak", "qb.pak.xen"), "rb").read(), -15)
    pab = zlib.decompress(open(os.path.join(BACKUP, "pak", "qb.pab.xen"), "rb").read(), -15)
    return ler(pak, pab)


def ler_traducao():
    pak = open(os.path.join(FONTE, "PAK", "qb.pak.xen"), "rb").read()
    pab = open(os.path.join(FONTE, "PAK", "qb.pab.xen"), "rb").read()
    return ler(pak, pab)


def cauda_original():
    """Bytes do pab a seguir ao ultimo ficheiro do indice.

    Nenhum registo aponta para eles, mas descartar esta cauda mata o jogo -- por
    isso vai sempre atras, intacta."""
    itens = ler_original()
    fim = sum(len(d) for _, d in itens)
    pab = zlib.decompress(open(os.path.join(BACKUP, "pak", "qb.pab.xen"), "rb").read(), -15)
    return pab[fim:]


def construir(itens, tamanho_pak, cauda=b""):
    """itens = [(registo, dados)] pela ordem que ficarao no arquivo."""
    if len(itens) * 32 > tamanho_pak:
        raise SystemExit("indice nao cabe em %d bytes" % tamanho_pak)
    pak = bytearray(tamanho_pak)
    pab = bytearray()
    off = tamanho_pak
    for k, (c, dados) in enumerate(itens):
        novo = list(c)
        novo[1] = off
        struct.pack_into(">8I", pak, k * 32, *novo)
        pab += dados
        off += len(dados)
    pab += cauda
    return bytes(pak), bytes(pab)


def instalar(pak, pab):
    if len(pab) % SETOR:
        pab += bytes(SETOR - len(pab) % SETOR)
    bruto = open(os.path.join(COMP, "compress.toc.lst.xen"), "rb").read().decode("latin-1")
    linhas = bruto.replace(chr(13) + chr(10), chr(10)).split(chr(10))
    pos, idx = {}, 0
    for i, l in enumerate(linhas):
        if l.startswith("Name: "):
            pos[l[6:].rsplit(" ", 2)[0].lower()] = (idx, i)
            idx += 1
    toc = bytearray(open(os.path.join(COMP, "compress.toc.xen"), "rb").read())
    _, _, inicio, _ = struct.unpack_from(">4sIII", toc, 0)
    for rel, cru in (("pak" + BARRA + "qb.pak.xen", pak), ("pak" + BARRA + "qb.pab.xen", pab)):
        j, li = pos[rel]
        off = inicio + j * 16
        h, _, _, fl = struct.unpack_from(">IIII", toc, off)
        c = zlib.compressobj(9, zlib.DEFLATED, -15)
        comp = c.compress(cru) + c.flush()
        open(os.path.join(COMP, rel), "wb").write(comp)
        struct.pack_into(">IIII", toc, off, h, len(cru), len(comp), fl)
        partes = linhas[li][6:].rsplit(" ", 2)
        linhas[li] = "Name: %s %d %s" % (partes[0], len(comp), partes[2])
    open(os.path.join(COMP, "compress.toc.xen"), "wb").write(bytes(toc))
    open(os.path.join(COMP, "compress.toc.lst.xen"), "wb").write((chr(13) + chr(10)).join(linhas).encode("latin-1"))
