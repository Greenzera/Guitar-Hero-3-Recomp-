// Leitura de imagens XDVDFS (os ISO de Xbox 360), sem nada de Electron -- assim
// testa-se com `node` sozinho.
//
// O formato: o descritor de volume esta no setor 32 a contar de uma base que
// varia com o tipo de disco. Dentro dele, a raiz do sistema de ficheiros e uma
// arvore binaria de entradas de tamanho variavel.

'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const SETOR = 2048;
const MAGIC = Buffer.from('MICROSOFT*XBOX*MEDIA', 'ascii');

// Bases conhecidas, por ordem de probabilidade. O Guitar Hero III e XGD2.
const BASES = [0x0fd90000, 0x00000000, 0x02080000, 0x18300000];
const NOMES_BASE = ['XGD2', 'XGD1', 'XGD3', 'XGD2b'];

// A versao do disco de que este jogo foi recompilado: Guitar Hero III Legends
// of Rock (USA) Rev 1. Com dados de outra versao o codigo recompilado nao bate
// e o jogo nao arranca, por isso o instalador recusa qualquer outro ISO.
// O hash e o SHA-256 do default.xex inteiro -- o mesmo que esta gravado em
// game/source-xex.sha256, escrito quando o jogo foi recompilado.
const XEX_TAMANHO = 11055104;
const XEX_HASH = '1d67d98fbb0e35ac086d6354f3e49985698c83298226eafdec756e2a9e799a14';

// O disco certo da 660 ficheiros e 3,36 GB. Guarda-se um minimo com folga, so
// para apanhar uma extracao interrompida a meio -- em que o default.xex ja la
// esta e bate certo, mas falta metade do jogo.
const FICHEIROS_MINIMOS = 600;
const BYTES_MINIMOS = 3.2 * 1024 * 1024 * 1024;

function lerExato(fd, buffer, posicao) {
  let lidos = 0;
  while (lidos < buffer.length) {
    const n = fs.readSync(fd, buffer, lidos, buffer.length - lidos, posicao + lidos);
    if (n <= 0) break;
    lidos += n;
  }
  return lidos;
}

// Devolve {base, tipo, setorRaiz, tamanhoRaiz} ou null.
function acharParticao(fd, tamanhoFicheiro) {
  const bloco = Buffer.alloc(SETOR);
  for (let i = 0; i < BASES.length; i++) {
    const b = BASES[i];
    if (b + 33 * SETOR > tamanhoFicheiro) continue;
    if (lerExato(fd, bloco, b + 32 * SETOR) < SETOR) continue;
    if (bloco.compare(MAGIC, 0, MAGIC.length, 0, MAGIC.length) !== 0) continue;
    // A assinatura repete-se no fim do setor. Sem essa segunda verificacao,
    // uma coincidencia de 20 bytes chegaria para aceitar lixo.
    if (bloco.compare(MAGIC, 0, MAGIC.length, 0x7ec, 0x7ec + MAGIC.length) !== 0) continue;
    return {
      base: b,
      tipo: NOMES_BASE[i],
      setorRaiz: bloco.readUInt32LE(0x14),
      tamanhoRaiz: bloco.readUInt32LE(0x18),
    };
  }
  return null;
}

function lerDiretorio(fd, base, setor, tamanho, prefixo) {
  const saida = [];
  if (tamanho <= 0 || tamanho > 32 * 1024 * 1024) return saida;

  const tabela = Buffer.alloc(tamanho);
  lerExato(fd, tabela, base + setor * SETOR);

  // Percurso iterativo com visitados: um ISO estragado pode ter ciclos, e uma
  // recursao ingenua ficaria presa.
  const porVer = [0];
  const vistos = new Set();
  while (porVer.length) {
    const off = porVer.pop();
    if (vistos.has(off)) continue;
    vistos.add(off);
    if (off < 0 || off + 14 > tabela.length) continue;

    const esq = tabela.readUInt16LE(off);
    const dir = tabela.readUInt16LE(off + 2);
    const inicio = tabela.readUInt32LE(off + 4);
    const comp = tabela.readUInt32LE(off + 8);
    const atributos = tabela[off + 12];
    const tamNome = tabela[off + 13];
    if (off + 14 + tamNome > tabela.length) continue;

    if (esq !== 0 && esq !== 0xffff) porVer.push(esq * 4);
    if (dir !== 0 && dir !== 0xffff) porVer.push(dir * 4);
    if (tamNome === 0) continue;

    saida.push({
      caminho: prefixo + tabela.toString('latin1', off + 14, off + 14 + tamNome),
      setor: inicio,
      tamanho: comp,
      diretorio: (atributos & 0x10) !== 0,
    });
  }
  return saida;
}

function percorrer(fd, base, setor, tamanho, prefixo, saida, profundidade) {
  if (profundidade > 24) return;
  for (const a of lerDiretorio(fd, base, setor, tamanho, prefixo)) {
    saida.push(a);
    if (a.diretorio) {
      percorrer(fd, base, a.setor, a.tamanho, a.caminho + '/', saida, profundidade + 1);
    }
  }
}

function hashDeRegiao(fd, posicao, tamanho) {
  const h = crypto.createHash('sha256');
  const buffer = Buffer.alloc(1024 * 1024);
  let restante = tamanho;
  let p = posicao;
  while (restante > 0) {
    const quanto = Math.min(restante, buffer.length);
    const lidos = lerExato(fd, buffer.subarray(0, quanto), p);
    if (lidos <= 0) break;
    h.update(buffer.subarray(0, lidos));
    p += lidos;
    restante -= lidos;
  }
  return h.digest('hex');
}

// Olha para o ISO sem extrair nada. Devolve o tipo de disco, quantos ficheiros
// tem, quantos bytes ocupam, e se o default.xex e o mesmo com que o jogo foi
// recompilado.
function inspecionar(caminhoIso) {
  let fd;
  try {
    fd = fs.openSync(caminhoIso, 'r');
    const tamanhoFicheiro = fs.fstatSync(fd).size;
    const p = acharParticao(fd, tamanhoFicheiro);
    if (!p) {
      return { valido: false, erro: 'Não parece um ISO de Xbox 360 — não achei a partição de jogo.' };
    }

    const tudo = [];
    percorrer(fd, p.base, p.setorRaiz, p.tamanhoRaiz, '', tudo, 0);

    let xex = null;
    let ficheiros = 0;
    let bytesTotais = 0;
    for (const a of tudo) {
      if (a.diretorio) continue;
      ficheiros++;
      bytesTotais += a.tamanho;
      if (a.caminho.toLowerCase() === 'default.xex') xex = a;
    }
    if (!xex) {
      return { valido: false, erro: 'O ISO não tem default.xex — não é um disco de jogo.' };
    }

    const hash = hashDeRegiao(fd, p.base + xex.setor * SETOR, xex.tamanho);

    return {
      valido: true,
      tipoDisco: p.tipo,
      ficheiros,
      bytesTotais,
      tamanhoXex: xex.tamanho,
      hashXex: hash,
      mesmaVersao: xex.tamanho === XEX_TAMANHO && hash === XEX_HASH,
    };
  } catch (e) {
    return { valido: false, erro: e.message };
  } finally {
    if (fd !== undefined) fs.closeSync(fd);
  }
}

// Extrai tudo para `pastaSaida`, chamando `aoProgresso({feitos, totais, ficheiro})`
// de vez em quando. Sincrono de proposito: corre num processo utilitario, nao
// no da interface.
function extrair(caminhoIso, pastaSaida, aoProgresso) {
  const fd = fs.openSync(caminhoIso, 'r');
  try {
    const tamanhoFicheiro = fs.fstatSync(fd).size;
    const p = acharParticao(fd, tamanhoFicheiro);
    if (!p) throw new Error('Partição de jogo não encontrada.');

    const tudo = [];
    percorrer(fd, p.base, p.setorRaiz, p.tamanhoRaiz, '', tudo, 0);
    const ficheiros = tudo.filter((a) => !a.diretorio);
    const totais = ficheiros.reduce((s, a) => s + a.tamanho, 0);

    // As pastas primeiro, senao a escrita do primeiro ficheiro de cada uma falha.
    fs.mkdirSync(pastaSaida, { recursive: true });
    for (const d of tudo.filter((a) => a.diretorio)) {
      fs.mkdirSync(path.join(pastaSaida, d.caminho), { recursive: true });
    }

    // 4 MB de cada vez: em blocos pequenos o custo por chamada domina, e em
    // blocos muito grandes a memoria salta sem se ganhar nada.
    const PEDACO = 4 * 1024 * 1024;
    const buffer = Buffer.alloc(PEDACO);
    let feitos = 0;
    let ultimoAviso = 0;

    for (const a of ficheiros) {
      const destino = path.join(pastaSaida, a.caminho);
      fs.mkdirSync(path.dirname(destino), { recursive: true });

      const saida = fs.openSync(destino, 'w');
      try {
        let restante = a.tamanho;
        let posicao = p.base + a.setor * SETOR;
        while (restante > 0) {
          const quanto = Math.min(restante, PEDACO);
          const lidos = lerExato(fd, buffer.subarray(0, quanto), posicao);
          if (lidos <= 0) break;
          fs.writeSync(saida, buffer, 0, lidos);
          posicao += lidos;
          restante -= lidos;
          feitos += lidos;

          const agora = Date.now();
          if (aoProgresso && agora - ultimoAviso > 120) {
            ultimoAviso = agora;
            aoProgresso({ feitos, totais, ficheiro: a.caminho });
          }
        }
      } finally {
        fs.closeSync(saida);
      }
    }
    if (aoProgresso) aoProgresso({ feitos, totais, ficheiro: '', terminou: true });
    return { ok: true, ficheiros: ficheiros.length, bytes: feitos };
  } finally {
    fs.closeSync(fd);
  }
}

function contar(pasta) {
  let ficheiros = 0;
  let bytes = 0;
  const andar = (d) => {
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      const f = path.join(d, e.name);
      if (e.isDirectory()) {
        andar(f);
      } else {
        ficheiros++;
        try {
          bytes += fs.statSync(f).size;
        } catch {
          /* ficheiro sumiu no meio da contagem; nao e fatal */
        }
      }
    }
  };
  andar(pasta);
  return { ficheiros, bytes };
}

// Confere o jogo JA EXTRAIDO, lendo o default.xex do disco.
//
// Porque nao um ficheiro-marcador com "ja verifiquei": um marcador e um
// ficheiro de texto que qualquer pessoa edita. Conferir os bytes reais custa
// uns milissegundos e nao se contorna sem ter mesmo o ficheiro certo.
function verificarJogoExtraido(pastaJogo) {
  const alvo = path.join(pastaJogo, 'default.xex');
  let st;
  try {
    st = fs.statSync(alvo);
  } catch {
    return { ok: false, motivo: 'O jogo ainda não foi instalado.' };
  }
  if (st.size !== XEX_TAMANHO) {
    return {
      ok: false,
      motivo: `O default.xex tem ${st.size} bytes e devia ter ${XEX_TAMANHO}. ` +
              'Provavelmente veio de uma versão diferente do disco.',
    };
  }
  const fd = fs.openSync(alvo, 'r');
  let hash;
  try {
    hash = hashDeRegiao(fd, 0, st.size);
  } finally {
    fs.closeSync(fd);
  }
  if (hash !== XEX_HASH) {
    return { ok: false, motivo: 'O default.xex não é a versão com que o jogo foi recompilado.' };
  }

  // O xex esta certo, mas isso nao diz que o resto veio todo: uma extracao
  // interrompida deixa os primeiros ficheiros e falta o resto. Conta-se DATA/,
  // que e onde esta praticamente tudo.
  let c;
  try {
    c = contar(path.join(pastaJogo, 'DATA'));
  } catch {
    return { ok: false, motivo: 'Não encontrei a pasta DATA do jogo.' };
  }
  if (c.ficheiros < FICHEIROS_MINIMOS || c.bytes < BYTES_MINIMOS) {
    const gb = (c.bytes / 1073741824).toFixed(1);
    return {
      ok: false,
      motivo: `A instalação ficou incompleta: ${c.ficheiros} ficheiros e ${gb} GB em DATA, ` +
              'quando deviam ser cerca de 658 e 3,3 GB. Ponha o ISO outra vez.',
    };
  }

  return { ok: true, ficheiros: c.ficheiros, bytes: c.bytes };
}

module.exports = { inspecionar, extrair, verificarJogoExtraido, XEX_TAMANHO, XEX_HASH };
