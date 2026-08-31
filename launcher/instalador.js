// Transforma a pasta distribuivel num unico .exe de instalacao.
//
//     node empacotar.js && node instalador.js
//
// Usa o SFX do WinRAR: o utilizador recebe um ficheiro so', escolhe a pasta,
// e no fim o launcher abre sozinho. Nao ha nada de Electron nisto -- e' so'
// empacotamento.

'use strict';

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const RAIZ = path.resolve(__dirname, '..');
const PASTA = process.argv[2] || path.join(RAIZ, 'dist', 'Guitar Hero 3 Recomp');
const SAIDA = path.join(RAIZ, 'dist', 'Guitar Hero 3 Recomp - Instalador.exe');

const RAR = ['C:/Program Files/WinRAR/Rar.exe', 'C:/Program Files (x86)/WinRAR/Rar.exe']
  .find((p) => fs.existsSync(p));

if (!RAR) {
  console.error('Nao encontrei o Rar.exe do WinRAR. Sem ele nao da' + "'" + ' para fazer o .exe unico.');
  process.exit(1);
}
if (!fs.existsSync(PASTA)) {
  console.error('Falta a pasta ' + PASTA + ' -- corre primeiro: node empacotar.js');
  process.exit(1);
}

// Configuracao do SFX. Vai como comentario do arquivo; e' assim que o WinRAR
// sabe onde extrair e o que correr no fim.
const CONFIG = [
  'Path=Guitar Hero 3 Recomp',
  'Setup=Guitar Hero 3 Recomp.exe',
  'Silent=0',
  'Overwrite=1',
  'Title=Guitar Hero 3 Recomp',
  'Text',
  '{',
  'Guitar Hero III: Legends of Rock - Recomp',
  '',
  'Escolha a pasta e clique em Instalar.',
  '',
  'O jogo NAO vem incluido: depois de instalar, o launcher',
  'pede o ISO do seu disco (USA, Rev 1) e trata do resto.',
  '}',
  '',
].join('\r\n');

const comentario = path.join(RAIZ, 'dist', '_sfx.txt');
fs.writeFileSync(comentario, CONFIG, 'latin1');
fs.rmSync(SAIDA, { force: true });

console.log('a comprimir ' + PASTA);
console.log('(sao centenas de MB, demora)');
try {
  execFileSync(RAR, [
    'a',            // criar arquivo
    '-r',           // recursivo
    '-ep1',         // sem o nome da pasta de origem nos caminhos
    '-sfx',         // auto-extraivel
    '-m3',          // compressao normal: o bom compromisso para 400 MB
    '-z' + comentario,
    '-idq',         // calado
    SAIDA,
    path.join(PASTA, '*'),
  ], { stdio: 'inherit' });
} finally {
  fs.rmSync(comentario, { force: true });
}

const mb = fs.statSync(SAIDA).size / 1048576;
console.log('\npronto: ' + SAIDA);
console.log('tamanho: ' + mb.toFixed(0) + ' MB');
