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
const { execFile } = require('child_process');

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

// Traz um mod de fora para a pasta de mods. Aceita uma pasta ou um .zip; o zip
// e' aberto com o tar do Windows, que existe desde o Windows 10 e poupa uma
// dependencia so' para isto.
async function importarMod(pastaMods, origem) {
  const st = await fsp.stat(origem);
  const base = path.basename(origem).replace(/\.zip$/i, '');
  let destino = path.join(pastaMods, base);
  let n = 2;
  while (await existe(destino)) destino = path.join(pastaMods, base + ' (' + n++ + ')');

  if (st.isDirectory()) {
    await fsp.cp(origem, destino, { recursive: true });
  } else {
    await fsp.mkdir(destino, { recursive: true });
    await new Promise((ok, falha) => {
      execFile('tar', ['-xf', origem, '-C', destino], (e) =>
        e ? falha(new Error('Nao consegui abrir o zip: ' + e.message)) : ok());
    });
    // se o zip trazia tudo dentro de uma pasta, sobe-se um nivel
    const dentro = await fsp.readdir(destino, { withFileTypes: true });
    if (dentro.length === 1 && dentro[0].isDirectory()) {
      const meio = path.join(destino, dentro[0].name);
      for (const e of await fsp.readdir(meio)) {
        await fsp.rename(path.join(meio, e), path.join(destino, e));
      }
      await fsp.rmdir(meio);
    }
  }

  // Um mod tem de trazer alguma coisa que o jogo reconheca.
  const temXex = await existe(path.join(destino, 'default.xex'));
  const temDados = await existe(path.join(destino, 'DATA'));
  if (!temXex && !temDados) {
    await fsp.rm(destino, { recursive: true, force: true });
    throw new Error('Isso nao parece um mod: nao tem default.xex nem uma pasta DATA.');
  }
  return { nome: path.basename(destino), codigo: temXex };
}

module.exports = { listarMods, listarBuilds, escolherBuild, ligarMod, importarMod, sha256 };
