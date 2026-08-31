#!/usr/bin/env python3
"""Desencripta a imagem de um XEX2 e varre fronteiras de funcao em PowerPC.

Porque existe: o codegen do rexglue falha com "target not in any function" em
rotinas que so sao alcancadas por tail call e nao aparecem no PDATA. Para as
declarar em config/gh3_functions.toml e preciso saber onde cada uma acaba, e
para isso e preciso desmontar a imagem -- que esta encriptada.

O rexglue 0.9.0 nao tem comando de dump e nao ha bibliotecas AES instaladas,
por isso o AES-128 esta implementado aqui (so desencriptacao).

O GH3 tem compression=1 (NENHUMA), portanto o mapeamento e linear:
    offset_ficheiro = pe_data_offset + (VA - load_address)
Se algum dia isto for usado num XEX com compressao basic/LZX, o mapeamento tem
de mudar -- o script recusa-se a adivinhar e aborta.

Como o modo CBC so precisa do bloco cifrado anterior para desencriptar um
bloco, conseguimos abrir janelas isoladas da imagem sem processar os 15 MB.

Uso:
    python xex_image.py <xex> --info
    python xex_image.py <xex> --disasm 0x82118F94 --count 40
    python xex_image.py <xex> --sweep 0x82118F94 [0x8232FDB0 ...]
    python xex_image.py <xex> --dump-full --out ../extracted/xexdump
"""

import argparse
import os
import struct
import sys

# Chave retail do XEX2, publica desde 2007 (esta em qualquer ferramenta de
# homebrew do 360). Nao abre nada que o utilizador ja nao possua: serve apenas
# para ler um disco do proprio.
RETAIL_KEY = bytes.fromhex("20B185A59D28FDC340583FBB0896BF91")

XEX_COMPRESSION = {1: "nenhuma", 2: "basic", 3: "normal (LZX)", 4: "delta"}


# --------------------------------------------------------------------------
# AES-128 (apenas desencriptacao)
# --------------------------------------------------------------------------

def _gmul(a, b):
    result = 0
    for _ in range(8):
        if b & 1:
            result ^= a
        high = a & 0x80
        a = (a << 1) & 0xFF
        if high:
            a ^= 0x1B
        b >>= 1
    return result


def _build_tables():
    """Gera S-box e inversa em vez de as escrever a mao (menos margem para erro)."""
    inverse = [0] * 256
    for a in range(1, 256):
        for b in range(1, 256):
            if _gmul(a, b) == 1:
                inverse[a] = b
                break

    sbox = [0] * 256
    for a in range(256):
        x = inverse[a]
        y = x
        for _ in range(4):
            x = ((x << 1) | (x >> 7)) & 0xFF
            y ^= x
        sbox[a] = y ^ 0x63

    inv_sbox = [0] * 256
    for i, v in enumerate(sbox):
        inv_sbox[v] = i
    return sbox, inv_sbox


SBOX, INV_SBOX = _build_tables()
MUL = {n: [_gmul(x, n) for x in range(256)] for n in (9, 11, 13, 14)}
RCON = [0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36]


class AES128:
    def __init__(self, key):
        assert len(key) == 16
        w = [list(key[i * 4:i * 4 + 4]) for i in range(4)]
        for i in range(4, 44):
            t = list(w[i - 1])
            if i % 4 == 0:
                t = t[1:] + t[:1]
                t = [SBOX[b] for b in t]
                t[0] ^= RCON[i // 4 - 1]
            w.append([w[i - 4][j] ^ t[j] for j in range(4)])
        self.round_keys = [
            bytes(b for word in w[r * 4:r * 4 + 4] for b in word) for r in range(11)
        ]

    def decrypt_block(self, block):
        s = [block[i] ^ self.round_keys[10][i] for i in range(16)]
        for rnd in range(9, 0, -1):
            s = self._inv_shift_rows(s)
            s = [INV_SBOX[b] for b in s]
            rk = self.round_keys[rnd]
            s = [s[i] ^ rk[i] for i in range(16)]
            s = self._inv_mix_columns(s)
        s = self._inv_shift_rows(s)
        s = [INV_SBOX[b] for b in s]
        rk = self.round_keys[0]
        return bytes(s[i] ^ rk[i] for i in range(16))

    @staticmethod
    def _inv_shift_rows(s):
        return [
            s[0], s[13], s[10], s[7],
            s[4], s[1], s[14], s[11],
            s[8], s[5], s[2], s[15],
            s[12], s[9], s[6], s[3],
        ]

    @staticmethod
    def _inv_mix_columns(s):
        m9, m11, m13, m14 = MUL[9], MUL[11], MUL[13], MUL[14]
        out = []
        for c in range(4):
            a0, a1, a2, a3 = s[c * 4:c * 4 + 4]
            out += [
                m14[a0] ^ m11[a1] ^ m13[a2] ^ m9[a3],
                m9[a0] ^ m14[a1] ^ m11[a2] ^ m13[a3],
                m13[a0] ^ m9[a1] ^ m14[a2] ^ m11[a3],
                m11[a0] ^ m13[a1] ^ m9[a2] ^ m14[a3],
            ]
        return out


def _self_test():
    """Vector do FIPS-197 apendice B. Se isto passar, o AES esta correto."""
    key = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
    ct = bytes.fromhex("69c4e0d86a7b0430d8cdb78070b4c55a")
    pt = bytes.fromhex("00112233445566778899aabbccddeeff")
    if AES128(key).decrypt_block(ct) != pt:
        raise SystemExit("[ERRO] auto-teste do AES falhou -- nao confies no resultado")


# --------------------------------------------------------------------------
# XEX
# --------------------------------------------------------------------------

class XexImage:
    def __init__(self, path):
        with open(path, "rb") as fh:
            self.raw = fh.read()
        if self.raw[:4] != b"XEX2":
            raise SystemExit("[ERRO] nao e um XEX2")

        (self.module_flags, self.pe_offset, _res, self.sec_offset,
         hdr_count) = struct.unpack_from(">IIIII", self.raw, 4)

        headers = {}
        for i in range(hdr_count):
            k, v = struct.unpack_from(">II", self.raw, 24 + i * 8)
            headers[k] = v
        self.headers = headers

        fmt_off = headers[0x000003FF]
        _size, self.encryption, self.compression = struct.unpack_from(">IHH", self.raw, fmt_off)

        info = self.sec_offset + 8
        self.image_size = struct.unpack_from(">I", self.raw, self.sec_offset + 4)[0]
        self.load_address = struct.unpack_from(">I", self.raw, info + 0x108)[0]
        image_key = self.raw[info + 0x148: info + 0x158]

        self.entry_point = headers.get(0x00010100, 0)
        self.title_id = struct.unpack_from(">I", self.raw, headers[0x00040006] + 12)[0]

        if self.compression != 1:
            raise SystemExit(
                f"[ERRO] compressao {self.compression} "
                f"({XEX_COMPRESSION.get(self.compression, '?')}): este script so "
                f"trata imagens sem compressao, onde o mapeamento VA->ficheiro e "
                f"linear. Seria preciso implementar o descompressor.")

        self.session_key = AES128(RETAIL_KEY).decrypt_block(image_key) if self.encryption else None
        self._cache = {}

        # image_size conta a imagem carregada INTEIRA, incluindo a cauda nao
        # inicializada (estilo BSS) que nao e guardada no ficheiro. So se pode
        # ler ate onde o ficheiro chega. No GH3 sao 11,04 MB de 15,86 MB -- o
        # codigo (0x820D0000-0x828CF410) cabe todo na parte legivel.
        self.stored_size = len(self.raw) - self.pe_offset
        self.stored_end_va = self.load_address + self.stored_size

    def file_offset(self, va):
        return self.pe_offset + (va - self.load_address)

    def read(self, va, length):
        """Le `length` bytes desencriptados a partir do endereco virtual `va`."""
        start = self.file_offset(va)
        end = start + length
        if start < self.pe_offset or end > len(self.raw):
            raise SystemExit(f"[ERRO] 0x{va:08X}+{length} fora da imagem")
        if not self.encryption:
            return self.raw[start:end]

        # CBC: alinhar para tras ate ao limite de bloco e usar o bloco cifrado
        # anterior como IV (zeros se estivermos no primeiro bloco).
        rel = start - self.pe_offset
        first = (rel // 16) * 16
        last = ((end - self.pe_offset + 15) // 16) * 16
        aes = AES128(self.session_key)

        out = bytearray()
        prev = (self.raw[self.pe_offset + first - 16: self.pe_offset + first]
                if first >= 16 else b"\x00" * 16)
        for off in range(first, last, 16):
            key = off
            if key in self._cache:
                plain, prev = self._cache[key]
            else:
                cipher = self.raw[self.pe_offset + off: self.pe_offset + off + 16]
                plain = bytes(a ^ b for a, b in zip(aes.decrypt_block(cipher), prev))
                self._cache[key] = (plain, cipher)
                prev = cipher
            out += plain
        skip = rel - first
        return bytes(out[skip:skip + length])

    def word(self, va):
        return struct.unpack(">I", self.read(va, 4))[0]


# --------------------------------------------------------------------------
# PowerPC: so o suficiente para achar o fim de uma funcao
# --------------------------------------------------------------------------

def _sext(value, bits):
    sign = 1 << (bits - 1)
    return (value ^ sign) - sign


def decode(insn, pc):
    """Devolve (texto, tipo, alvo). tipo: 'end' | 'cond' | 'call' | ''."""
    op = (insn >> 26) & 0x3F

    if op == 18:  # b / bl / ba / bla
        target = _sext(insn & 0x03FFFFFC, 26)
        aa, lk = insn & 2, insn & 1
        dest = target if aa else (pc + target) & 0xFFFFFFFF
        if lk:
            return (f"bl      0x{dest:08X}", "call", dest)
        return (f"b       0x{dest:08X}", "end", dest)

    if op == 16:  # bc / bcl
        bo = (insn >> 21) & 0x1F
        bd = _sext(insn & 0xFFFC, 16)
        aa, lk = insn & 2, insn & 1
        dest = bd if aa else (pc + bd) & 0xFFFFFFFF
        kind = "call" if lk else "cond"
        # BO com bit 4 (0x10) ligado e sem contador = ramo incondicional
        if (bo & 0x14) == 0x14 and not lk:
            return (f"b(cond-always) 0x{dest:08X}", "end", dest)
        return (f"bc      0x{dest:08X}", kind, dest)

    if op == 19:
        xo = (insn >> 1) & 0x3FF
        bo = (insn >> 21) & 0x1F
        lk = insn & 1
        if xo == 16:
            name = "blr" if (bo & 0x14) == 0x14 else "bclr"
            if lk:
                return (f"{name}l", "call", None)
            return (name, "end" if (bo & 0x14) == 0x14 else "cond", None)
        if xo == 528:
            name = "bctr" if (bo & 0x14) == 0x14 else "bcctr"
            if lk:
                return (f"{name}l", "call", None)
            return (name, "end" if (bo & 0x14) == 0x14 else "cond", None)
        return (f"<19:{xo}>", "", None)

    if insn == 0x4C000064:
        return ("rfid", "end", None)
    if op == 17:
        return ("sc", "", None)
    if insn == 0x60000000:
        return ("nop", "", None)

    mnem = {
        14: "addi", 15: "addis", 24: "ori", 25: "oris", 26: "xori", 27: "xoris",
        28: "andi.", 29: "andis.", 32: "lwz", 33: "lwzu", 34: "lbz", 36: "stw",
        37: "stwu", 38: "stb", 40: "lhz", 44: "sth", 48: "lfs", 50: "lfd",
        52: "stfs", 54: "stfd", 58: "ld/lwa", 62: "std/stdu", 11: "cmpi",
        10: "cmpli", 7: "mulli", 31: "<ext31>", 21: "rlwinm", 20: "rlwimi",
        30: "<ext30>", 63: "<fp>", 59: "<fp-s>",
    }.get(op, f"<op{op}>")
    return (mnem, "", None)


def sweep(image, start, limit=4096):
    """Varre de `start` ate ao terminador e devolve (end_exclusivo, listagem).

    Um terminador so conta se nenhum ramo condicional anterior saltar por cima
    dele -- caso contrario a funcao continua depois do salto.
    """
    furthest = start
    listing = []
    pc = start
    while pc < start + limit:
        insn = image.word(pc)
        text, kind, dest = decode(insn, pc)
        note = ""

        if kind == "cond" and dest is not None and dest > furthest:
            furthest = dest
            note = "  <- salta para a frente"
        if kind == "end" and dest is not None and dest > furthest and start < dest:
            # tail call para dentro do proprio corpo continua a funcao
            if dest < start + limit:
                furthest = max(furthest, dest)

        listing.append((pc, insn, text, note))

        if kind == "end" and pc >= furthest:
            return pc + 4, listing
        pc += 4

    return None, listing


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("xex")
    ap.add_argument("--info", action="store_true")
    ap.add_argument("--disasm", type=lambda s: int(s, 0))
    ap.add_argument("--count", type=int, default=32)
    ap.add_argument("--sweep", nargs="+", type=lambda s: int(s, 0), default=[])
    ap.add_argument("--dump-full", action="store_true")
    ap.add_argument("--out", default="../extracted/xexdump")
    args = ap.parse_args()

    _self_test()
    img = XexImage(args.xex)

    if args.info or not (args.disasm or args.sweep or args.dump_full):
        print(f"load address : 0x{img.load_address:08X}")
        print(f"image size   : 0x{img.image_size:08X}")
        print(f"entry point  : 0x{img.entry_point:08X}")
        print(f"title id     : 0x{img.title_id:08X}")
        print(f"encriptacao  : {img.encryption}")
        print(f"compressao   : {img.compression} "
              f"({XEX_COMPRESSION.get(img.compression, '?')})")
        if img.session_key:
            print(f"chave sessao : {img.session_key.hex()}")
        print()
        print("verificacao (primeiros 8 words no entry point):")
        for i in range(8):
            pc = img.entry_point + i * 4
            insn = img.word(pc)
            print(f"  0x{pc:08X}  {insn:08X}  {decode(insn, pc)[0]}")

    if args.disasm:
        print()
        for i in range(args.count):
            pc = args.disasm + i * 4
            insn = img.word(pc)
            text, kind, _ = decode(insn, pc)
            print(f"  0x{pc:08X}  {insn:08X}  {text}"
                  + (f"   [{kind}]" if kind else ""))

    if args.sweep:
        print()
        print("[functions]")
        for start in args.sweep:
            end, listing = sweep(img, start)
            if end is None:
                print(f'# 0x{start:08X}: SEM terminador em 4 KB -- verificar a mao')
                continue
            last = listing[-1]
            size = end - start
            print(f'"0x{start:08X}" = {{ end = 0x{end:08X} }}'
                  f'  # {size // 4} instrucoes, termina em {last[2]}')

    if args.dump_full:
        os.makedirs(args.out, exist_ok=True)
        # Despeja so a parte guardada no ficheiro; a cauda BSS nao existe aqui.
        name = f"default_{img.load_address:08X}_{img.stored_size:08X}"
        print(f"imagem carregada : 0x{img.image_size:08X}")
        print(f"guardada no XEX  : 0x{img.stored_size:08X} "
              f"(ate VA 0x{img.stored_end_va:08X}; o resto e BSS)")
        data = img.read(img.load_address, img.stored_size)
        with open(os.path.join(args.out, name + ".bin"), "wb") as fh:
            fh.write(data)
        with open(os.path.join(args.out, name + ".txt"), "w") as fh:
            fh.write(f"name=default\nbase=0x{img.load_address:08X}\n"
                     f"size=0x{img.image_size:08X}\nentry=0x{img.entry_point:08X}\n")
        print(f"escrito {args.out}/{name}.bin ({len(data):,} bytes)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
