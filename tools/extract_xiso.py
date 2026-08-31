#!/usr/bin/env python3
"""Extrai ficheiros de um ISO Xbox 360 (XDVDFS / GDF).

O rexglue 0.9.0 nao extrai ISOs (so tem codegen/init/recompile-tests), por isso
fazemos a leitura do filesystem aqui.

Um ISO do 360 tem duas particoes: video (no inicio, sem interesse) e jogo. O
descritor de volume da particao de jogo esta no setor 32 a contar da base da
particao, e a base depende do tipo de disco:

    XGD1   0x00000000   (2005-2006)
    XGD2   0x0FD90000   (2006-2011)   <- Guitar Hero III
    XGD3   0x02080000   (2011+)
    XGD2b  0x18300000   (algumas redumps)

Em vez de assumir, procuramos a assinatura em todas as bases conhecidas.

Uso:
    python extract_xiso.py <iso> --list
    python extract_xiso.py <iso> --extract default.xex --out ../extracted
    python extract_xiso.py <iso> --extract-all --out ../extracted
"""

import argparse
import os
import struct
import sys

SECTOR = 2048
MAGIC = b"MICROSOFT*XBOX*MEDIA"

# Bases de particao conhecidas, por ordem de probabilidade para um disco de 2007.
KNOWN_BASES = [
    (0x0FD90000, "XGD2"),
    (0x00000000, "XGD1"),
    (0x02080000, "XGD3"),
    (0x18300000, "XGD2b"),
]

ATTR_DIRECTORY = 0x10


class Entry:
    __slots__ = ("name", "sector", "size", "attributes")

    def __init__(self, name, sector, size, attributes):
        self.name = name
        self.sector = sector
        self.size = size
        self.attributes = attributes

    @property
    def is_dir(self):
        return bool(self.attributes & ATTR_DIRECTORY)


def find_partition(fh):
    """Devolve (base, rotulo, root_sector, root_size) da particao de jogo."""
    for base, label in KNOWN_BASES:
        fh.seek(base + 32 * SECTOR)
        block = fh.read(SECTOR)
        if len(block) < SECTOR or not block.startswith(MAGIC):
            continue
        # A assinatura repete-se no fim do setor; se nao repetir, e coincidencia.
        if block[0x7EC:0x7EC + len(MAGIC)] != MAGIC:
            continue
        root_sector, root_size = struct.unpack_from("<II", block, 0x14)
        return base, label, root_sector, root_size
    return None


def read_directory(fh, base, sector, size):
    """Le uma tabela de diretorio e devolve as suas entradas.

    A tabela e uma arvore binaria achatada: cada entrada guarda o offset dos
    filhos esquerdo/direito em unidades de 4 bytes a contar do inicio da tabela.
    Percorremos iterativamente com um conjunto de visitados, porque um ISO
    corrompido pode ter ciclos e nao queremos recursao infinita.
    """
    if size == 0:
        return []
    fh.seek(base + sector * SECTOR)
    table = fh.read(size)

    entries = []
    pending = [0]
    seen = set()

    while pending:
        offset = pending.pop()
        if offset in seen:
            continue
        seen.add(offset)
        if offset + 14 > len(table):
            continue

        left, right, start, length, attributes, name_len = struct.unpack_from(
            "<HHIIBB", table, offset
        )
        name_end = offset + 14 + name_len
        if name_end > len(table):
            continue
        name = table[offset + 14:name_end].decode("latin-1")

        # 0xFFFF e o terminador habitual; 0 tambem aparece em algumas imagens
        # (excepto na raiz, cujo offset legitimo e 0 e ja esta em `seen`).
        for child in (left, right):
            if child not in (0, 0xFFFF):
                pending.append(child * 4)

        if name:
            entries.append(Entry(name, start, length, attributes))

    entries.sort(key=lambda e: e.name.lower())
    return entries


def walk(fh, base, sector, size, prefix=""):
    """Percorre a arvore de diretorios e produz (caminho, entrada)."""
    for entry in read_directory(fh, base, sector, size):
        path = prefix + entry.name
        if entry.is_dir:
            yield path + "/", entry
            yield from walk(fh, base, entry.sector, entry.size, path + "/")
        else:
            yield path, entry


def human(size):
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:,.0f} {unit}" if unit == "B" else f"{size:,.1f} {unit}"
        size /= 1024


def extract_one(fh, base, entry, dest):
    os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
    fh.seek(base + entry.sector * SECTOR)
    remaining = entry.size
    with open(dest, "wb") as out:
        while remaining > 0:
            chunk = fh.read(min(8 * 1024 * 1024, remaining))
            if not chunk:
                raise IOError(
                    f"ISO acabou a meio de {entry.name}: faltam {remaining} bytes"
                )
            out.write(chunk)
            remaining -= len(chunk)
    return entry.size


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("iso")
    parser.add_argument("--list", action="store_true", help="lista o conteudo")
    parser.add_argument("--extract", action="append", default=[],
                        help="nome de ficheiro a extrair (repetivel, sem distincao de maiusculas)")
    parser.add_argument("--extract-all", action="store_true")
    parser.add_argument("--out", default="extracted")
    args = parser.parse_args()

    if not os.path.isfile(args.iso):
        print(f"[ERRO] ISO nao encontrado: {args.iso}", file=sys.stderr)
        return 1

    with open(args.iso, "rb") as fh:
        found = find_partition(fh)
        if not found:
            print("[ERRO] Assinatura MICROSOFT*XBOX*MEDIA nao encontrada em nenhuma "
                  "base conhecida. O ficheiro e mesmo um ISO do Xbox 360?",
                  file=sys.stderr)
            return 1

        base, label, root_sector, root_size = found
        iso_size = os.path.getsize(args.iso)
        print(f"ISO       : {os.path.basename(args.iso)}")
        print(f"Tamanho   : {iso_size:,} bytes ({human(iso_size)})")
        print(f"Tipo      : {label} (base 0x{base:08X})")
        print(f"Raiz      : setor {root_sector}, {root_size:,} bytes")
        print()

        items = list(walk(fh, base, root_sector, root_size))
        files = [(p, e) for p, e in items if not e.is_dir]
        dirs = [(p, e) for p, e in items if e.is_dir]
        print(f"{len(files)} ficheiros, {len(dirs)} diretorios")
        print()

        if args.list:
            for path, entry in sorted(items, key=lambda x: x[0].lower()):
                if entry.is_dir:
                    print(f"  {'<DIR>':>14}  {path}")
                else:
                    print(f"  {entry.size:>14,}  {path}")
            print()

        targets = []
        if args.extract_all:
            targets = files
        elif args.extract:
            wanted = {name.lower() for name in args.extract}
            for path, entry in files:
                if path.lower() in wanted or os.path.basename(path).lower() in wanted:
                    targets.append((path, entry))
            missing = wanted - {os.path.basename(p).lower() for p, _ in targets}
            if missing:
                print(f"[ERRO] nao encontrado no ISO: {', '.join(sorted(missing))}",
                      file=sys.stderr)
                return 1

        for path, entry in targets:
            dest = os.path.join(args.out, path.replace("/", os.sep))
            written = extract_one(fh, base, entry, dest)
            print(f"  extraido  {path}  ->  {dest}  ({human(written)})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
