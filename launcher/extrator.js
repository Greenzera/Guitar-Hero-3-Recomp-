// Processo de extracao. Corre separado do da interface porque a leitura dos
// 3,4 GB e sincrona -- feita no processo principal, a janela congelava.

'use strict';

const xiso = require('./xiso.js');

const [, , caminhoIso, pastaSaida] = process.argv;

try {
  const r = xiso.extrair(caminhoIso, pastaSaida, (p) => {
    process.send({ tipo: 'progresso', ...p });
  });
  process.send({ tipo: 'fim', ok: true, ...r });
} catch (e) {
  process.send({ tipo: 'fim', ok: false, erro: e.message });
}
process.exit(0);
