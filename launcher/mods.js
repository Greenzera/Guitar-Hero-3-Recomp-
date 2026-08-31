// Mods e escolha de executavel, sem nada de Electron -- assim testa-se com
// `node` sozinho.
//
// O problema que isto resolve: um recomp e' codigo compilado de UM xex. Um mod
// que altere o executavel do jogo (o GH3 Deluxe) traz o seu proprio default.xex
// e precisa do build recompilado a partir DESSE xex; nao ha um exe que sirva os
// dois. Cada build guarda um source-xex.sha256 a dizer de que xex nasceu, e e'
// por aí que se emparelham.

'use strict';

const fs = require('fs');
const fsp = require('fs/promises');
const path = require('path');
const crypto = require('crypto');

async function existe(p) {
  try {
    await fsp.access(p);
    return true;
  } catch {
    return false;
  }
}

async function sha256(caminho) {
  const h = crypto.createHash('sha256');
  h.update(await fsp.readFile(caminho));
  return h.digest('hex').toUpperCase();
}

// Um mod desliga-se pondo um ficheiro vazio .disabled dentro da pasta dele --
// e' essa a convencao do runtime, e nao um registo a parte.
async function listarMods(pastaMods) {
  if (!(await existe(pastaMods))) return [];
  const fora = [];
  for (const e of await fsp.readdir(pastaMods, { withFileTypes: true })) {
    if (!e.isDirectory()) continue;
    const xex = path.join(pastaMods, e.name, 'default.xex');
    let hashXex = null;
    if (await existe(xex)) {
      try {
        hashXex = await sha256(xex);
      } catch {}
    }
    fora.push({
      nome: e.name,
      ativo: !(await existe(path.join(pastaMods, e.name, '.disabled'))),
      codigo: hashXex !== null,
      hashXex,
    });
  }
  return fora.sort((a, b) => a.nome.localeCompare(b.nome, 'pt'));
}

// `principal` e' o executavel que vive ao lado dos dados; `raizes` sao pastas
// onde cada subpasta pode ser um build alternativo.
async function listarBuilds(principal, pastaJogo, raizes) {
  const fora = [];
  const marcaBase = path.join(pastaJogo, 'source-xex.sha256');
  if ((await existe(principal)) && (await existe(marcaBase))) {
    try {
      const h = (await fsp.readFile(marcaBase, 'utf8')).trim().toUpperCase();
      fora.push({ nome: 'base', exe: principal, hash: h, proprio: true });
    } catch {}
  }
  for (const raiz of raizes) {
    if (!(await existe(raiz))) continue;
    for (const e of await fsp.readdir(raiz, { withFileTypes: true })) {
      if (!e.isDirectory()) continue;
      const pasta = path.join(raiz, e.name);
      const marca = path.join(pasta, 'source-xex.sha256');
      if (!(await existe(marca))) continue;
      let exe = path.join(pasta, 'gh3.exe');
      if (!(await existe(exe))) {
        exe = path.join(pasta, 'Guitar Hero 3 Recomp.exe');
        if (!(await existe(exe))) continue;
      }
      const h = (await fsp.readFile(marca, 'utf8')).trim().toUpperCase();
      if (fora.some((b) => b.hash === h)) continue; // o que vive em game\ manda
      fora.push({ nome: e.name, exe, hash: h, proprio: false });
    }
  }
  return fora;
}

// Decide que executavel lancar, com a mesma regra do launcher antigo.
function escolherBuild(builds, mods) {
  const base = builds.find((b) => b.proprio) || null;
  const codigo = mods.filter((m) => m.ativo && m.codigo);
  const hashes = [...new Set(codigo.map((m) => m.hashXex))];

  if (hashes.length === 0) {
    return { build: base, nota: 'jogo base', aviso: null };
  }
  if (hashes.length > 1) {
    return {
      build: null,
      nota: null,
      aviso: 'Há mais do que um mod a alterar o executável do jogo (' +
             codigo.map((m) => m.nome).join(', ') +
             '). Dois xex diferentes não se combinam num só jogo — deixe só um ligado.',
    };
  }
  const nomes = codigo.map((m) => m.nome).join(', ');
  const alvo = builds.find((b) => b.hash === hashes[0]);
  if (alvo) return { build: alvo, nota: nomes, aviso: null };
  return {
    build: base,
    nota: nomes + ' (só os dados)',
    aviso: `O mod ${nomes} altera o executável do jogo, mas ainda não foi ` +
           'recompilado. Vou abrir o jogo base, com os dados dele apenas.',
  };
}

async function ligarMod(pastaMods, nome, ativo) {
  const marca = path.join(pastaMods, nome, '.disabled');
  if (ativo) {
    if (await existe(marca)) await fsp.unlink(marca);
  } else {
    await fs.promises.writeFile(marca, '');
  }
}

module.exports = { listarMods, listarBuilds, escolherBuild, ligarMod, sha256 };
