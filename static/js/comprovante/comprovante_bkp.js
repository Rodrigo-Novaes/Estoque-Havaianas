function imprimirComprovante(win, dados) {
    // FUNÇÃO PARA FORMATAR CPF/CNPJ
    const formatarDocumento = (doc) => {
        if (!doc) return '';
        
        const numeros = doc.replace(/\D/g, '');
        
        if (numeros.length === 11) {
            return numeros.replace(/^(\d{3})(\d{3})(\d{3})(\d{2})$/, '$1.$2.$3-$4');
        } else if (numeros.length === 14) {
            return numeros.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, '$1.$2.$3/$4-$5');
        }
        
        return doc;
    };
    
    // FORMATAR NÚMERO DA VENDA COM 3 DÍGITOS
    const formatarNumeroVenda = (numero) => {
        if (!numero) return '000';
        
        if (typeof numero === 'number') {
            return ('00' + numero).slice(-3);
        }
        
        if (typeof numero === 'string') {
            const numeros = numero.match(/\d+/g);
            if (numeros && numeros.length > 0) {
                const num = parseInt(numeros.join(''));
                return ('00' + num).slice(-3);
            }
        }
        
        return '000';
    };
    
    // Pegar configurações dos dados recebidos
    const config = dados.config_impressao || {
        tipo: 'dialogo',
        papel: '80mm',
        vias: 1,
        copiar: false,
        mensagem: 'Obrigado pela preferência!'
    };
    
    const vendaIdFormatado = formatarNumeroVenda(dados.venda_id);
    const documentoFormatado = formatarDocumento(dados.cpf);
    
    let itensHTML = '';
    dados.itens.forEach(i => {
        itensHTML += `
<div class="item">
  <span class="desc">${i.descricao}</span>
  <span class="qtd">${i.quantidade}x</span>
  <span class="valor">R$ ${(i.quantidade * i.preco).toFixed(2)}</span>
</div>
        `;
    });

    const cpfHTML = documentoFormatado ? `<div><span class="bold">CPF/CNPJ:</span> ${documentoFormatado}</div>` : '';
    
    const subtotalHTML = dados.subtotal ? `
<div class="subtotal">
  <span>Subtotal:</span>
  <span>R$ ${parseFloat(dados.subtotal).toFixed(2)}</span>
</div>
    ` : '';
    
    const descontoHTML = dados.desconto_valor > 0 ? `
<div class="desconto">
  <span>Desconto (${dados.desconto_percentual || 0}%):</span>
  <span>R$ ${parseFloat(dados.desconto_valor || 0).toFixed(2)}</span>
</div>
    ` : '';
    
    let pagamentoHTML = `<div>Forma de pagamento: ${dados.forma_pagamento}</div>`;
    
    if (dados.forma_pagamento === 'Dinheiro' && dados.valor_recebido) {
        pagamentoHTML += `
<div>Valor recebido: R$ ${parseFloat(dados.valor_recebido).toFixed(2)}</div>
<div>Troco: R$ ${parseFloat(dados.troco || 0).toFixed(2)}</div>
        `;
    }

    const empresa = dados.empresa || {
        razao_social: 'Lojas Havaianas',
        nome_fantasia: 'Lojas Havaianas',
        cnpj_formatado: '',
        endereco: '',
        contato: '',
        cabecalho: '',
        rodape: config.mensagem || 'Obrigado pela preferência!',
        mostrar_logo: true
    };

    // Determinar largura do papel
    let largura = '280px';
    if (config.papel === '58mm') {
        largura = '200px';
    } else if (config.papel === '80mm') {
        largura = '280px';
    } else if (config.papel === 'a4') {
        largura = '210mm';
    }

    // 🔥 CORREÇÃO: SEMPRE usar window.print() se não for 'visualizar'
    const onloadScript = config.tipo === 'visualizar' 
        ? 'setTimeout(() => window.close(), 1000);' 
        : 'window.print(); setTimeout(() => window.close(), 1);';

    // Determinar quantas vias imprimir (só se não for visualizar)
    let viasHTML = '';
    if (config.tipo !== 'visualizar' && config.vias > 1) {
        for (let i = 1; i < config.vias; i++) {
            viasHTML += `
                <div style="page-break-before: always;"></div>
                <div class="center bold" style="margin-top: 20px;">VIA ${i + 1}</div>
            `;
        }
    }

    // Mensagem de via do cliente se ativado (só se não for visualizar)
    const viaClienteHTML = config.tipo !== 'visualizar' && config.copiar ? `
        <div style="page-break-before: always;"></div>
        <div class="center bold" style="margin-top: 20px;">VIA DO CLIENTE</div>
    ` : '';

    let html = `
<html>
<head>
<title>Comprovante</title>
<style>
body {
    font-family: monospace;
    width: ${largura};
    margin: auto;
    padding: 10px;
    font-size: ${config.tipo === 'fiscal' ? '10px' : '12px'};
}
.center { text-align: center; }
.line { border-top: 1px dashed #000; margin: 6px 0; }
.item { display: flex; justify-content: space-between; margin: 4px 0; }
.desc { width: 60%; word-wrap: break-word; }
.qtd { width: 15%; text-align: center; }
.valor { width: 25%; text-align: right; }
.subtotal, .desconto { 
    display: flex; 
    justify-content: space-between;
    margin: 2px 0;
}
.total { 
    font-size: 14px; 
    font-weight: bold; 
    display: flex; 
    justify-content: space-between;
    margin-top: 8px;
    padding-top: 8px;
    border-top: 2px solid #000;
}
.small { font-size: 11px; }
.bold { font-weight: bold; }
.info-cliente { margin: 8px 0; }
.empresa-info { 
    font-size: 11px; 
    color: #333;
    margin: 4px 0;
}
.empresa-nome {
    font-size: 14px;
    font-weight: bold;
    margin-bottom: 2px;
}
.cabecalho {
    font-size: 11px;
    margin-bottom: 8px;
    font-style: italic;
}
.rodape {
    margin-top: 8px;
    font-size: 11px;
    font-style: italic;
}
</style>
</head>

<body onload="${onloadScript}">

<div class="center bold">
    <div class="empresa-nome">${empresa.nome_fantasia}</div>
    
    <!-- 🔥 MOSTRAR A IMPRESSORA SELECIONADA -->
    <div class="small text-muted" style="margin: 5px 0;">
        🖨️ ${dados.impressora_nome || 'Impressora não selecionada'}
    </div>
    
    ${empresa.cnpj_formatado ? `<div class="empresa-info">${empresa.cnpj_formatado}</div>` : ''}
    ${empresa.endereco ? `<div class="empresa-info">${empresa.endereco}</div>` : ''}
    ${empresa.contato ? `<div class="empresa-info">${empresa.contato}</div>` : ''}
</div>

${empresa.cabecalho ? `
<div class="center cabecalho">
    ${empresa.cabecalho}
</div>
` : ''}

<div class="line"></div>

<div class="info-cliente">
    <div><span class="bold">Venda:</span> #${vendaIdFormatado}</div>
    <div><span class="bold">Cliente:</span> ${dados.cliente || 'Consumidor'}</div>
    ${cpfHTML}
    <div><span class="bold">Vendedor:</span> ${dados.vendedor || 'Sistema'}</div>
    <div><span class="bold">Data:</span> ${dados.data || ''}</div>
</div>

<div class="line"></div>

<div class="item small bold">
  <span class="desc">PRODUTO</span>
  <span class="qtd">QTD</span>
  <span class="valor">TOTAL</span>
</div>

${itensHTML}

<div class="line"></div>

${subtotalHTML}
${descontoHTML}

<div class="total">
  <span>TOTAL</span>
  <span>R$ ${parseFloat(dados.total).toFixed(2)}</span>
</div>

<div class="line"></div>

${pagamentoHTML}

<div class="line"></div>

<div class="center small">
    ${config.mensagem}<br>
    ** COMPROVANTE NÃO FISCAL **<br>
    © ${new Date().getFullYear()} ${empresa.nome_fantasia}
</div>

${viaClienteHTML}
${viasHTML}

</body>
</html>
    `;

    win.document.open();
    win.document.write(html);
    win.document.close();
}