// ========== COMPROVANTE.JS - VERSÃO FINAL INTEGRADA ==========
// Função principal de impressão de comprovantes
// Agora usando rota do próprio Flask (sem servidor externo)

// ===== FUNÇÃO DE IMPRESSÃO DIRETA VIA FLASK =====
async function imprimirDireto(html, impressoraNome) {
    try {
        console.log('📤 Enviando para impressão via Flask...');
        
        const response = await fetch('/imprimir-direto', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                html: html,
                impressora: impressoraNome
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            console.log('✅ Impressão enviada com sucesso!');
            mostrarMensagemFlash('success', '✅ Comprovante enviado para impressão!');
            return true;
        } else {
            console.error('❌ Erro no servidor:', data.error);
            mostrarMensagemFlash('danger', '❌ Erro ao imprimir: ' + data.error);
            return false;
        }
    } catch (err) {
        console.error('❌ Erro de conexão:', err);
        mostrarMensagemFlash('danger', '❌ Erro ao conectar com o servidor');
        return false;
    }
}

// ===== FUNÇÃO PRINCIPAL DE IMPRESSÃO =====
function imprimirComprovante(win, dados) {
    // ===== FUNÇÕES AUXILIARES =====
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
    
    // ===== PEGAR CONFIGURAÇÕES =====
    const config = dados.config_impressao || {
        tipo: 'dialogo',
        papel: '80mm',
        vias: 1,
        copiar: false,
        mensagem: 'Obrigado pela preferência!'
    };
    
    const vendaIdFormatado = formatarNumeroVenda(dados.venda_id);
    const documentoFormatado = formatarDocumento(dados.cpf);
    
    // ===== GERAR HTML DOS ITENS =====
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

    // ===== DETERMINAR LARGURA DO PAPEL =====
    let largura = '280px';
    if (config.papel === '58mm') {
        largura = '200px';
    } else if (config.papel === '80mm') {
        largura = '280px';
    } else if (config.papel === 'a4') {
        largura = '210mm';
    }

    // ===== GERAR HTML COMPLETO =====
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

<body>
<div class="center bold">
    <div class="empresa-nome">${empresa.nome_fantasia}</div>
    
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
</body>
</html>
    `;

    // ===== DECISÃO DE IMPRESSÃO =====
    const tipoImpressao = config.tipo?.toLowerCase() || '';
    const isAutomatico = tipoImpressao === 'auto' || tipoImpressao === 'automatico';
    
    console.log('🔍 Tipo de impressão:', config.tipo);
    console.log('🎯 É automático?', isAutomatico);
    
    if (isAutomatico) {
        // 🔥 MODO AUTOMÁTICO - USA ROTA DO FLASK
        console.log('🖨️ Modo automático - imprimindo via Flask...');
        
        // Fechar a janela que foi aberta
        if (win && !win.closed) {
            win.close();
        }
        
        // Enviar para a rota do Flask
        imprimirDireto(html, dados.impressora_nome);
        
    } else {
        // 🔥 MODO DIÁLOGO - Comportamento normal com janela
        console.log('🖨️ Modo diálogo - abrindo janela de impressão...');
        
        // Adicionar script de impressão automática
        const htmlComPrint = html.replace('</body>', `
<script>
    window.onload = function() {
        window.print();
        setTimeout(function() {
            window.close();
        }, 1000);
    };
</script>
</body>`);
        
        if (win && !win.closed) {
            win.document.open();
            win.document.write(htmlComPrint);
            win.document.close();
        } else {
            // Se a janela não abriu, tenta abrir novamente
            const novaJanela = window.open('', 'Comprovante', 
                'width=900,height=600,top=100,left=100,scrollbars=yes');
            if (novaJanela) {
                novaJanela.document.open();
                novaJanela.document.write(htmlComPrint);
                novaJanela.document.close();
            } else {
                mostrarMensagemFlash('warning', '⚠️ Permita popups para ver o comprovante!');
            }
        }
    }
}

// ===== FUNÇÃO AUXILIAR PARA MOSTRAR MENSAGENS =====
function mostrarMensagemFlash(tipo, mensagem) {
    // Usar a função global do sistema se existir
    if (typeof window.mostrarMensagem === 'function') {
        window.mostrarMensagem(mensagem, tipo);
    } else {
        // Fallback: criar mensagem manualmente
        const flashDiv = document.createElement('div');
        flashDiv.className = `alert alert-${tipo} alert-dismissible fade show position-fixed top-0 start-50 translate-middle-x mt-3`;
        flashDiv.style.zIndex = '9999';
        flashDiv.style.minWidth = '300px';
        flashDiv.innerHTML = `
            ${mensagem}
            <button type="button" class="btn-close" onclick="this.parentElement.remove()"></button>
        `;
        document.body.appendChild(flashDiv);
        setTimeout(() => flashDiv.remove(), 0);
    }
}

// ===== EXPORTAR FUNÇÕES =====
window.imprimirComprovante = imprimirComprovante;
window.imprimirDireto = imprimirDireto;