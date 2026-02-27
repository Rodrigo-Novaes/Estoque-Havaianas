"""
SISTEMA DE CONTROLE DE ESTOQUE PARA LOJA DE HAVAIANAS
Autor: Sistema Havaianas
Versão: 2.0 - com Configurações Profissionais de Impressão
"""

from flask import Flask, render_template, request, jsonify, flash, redirect, url_for, send_file, session
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
from sqlalchemy import func
from sqlalchemy.sql import case  
from werkzeug.utils import secure_filename
from flask import send_from_directory
from PIL import Image
import os
import json
import time 
import shutil
import humanize
import subprocess  # ← Este é necessário
import re  # ← Este é necessário
# ========== CORREÇÃO ULTRA ROBUSTA PARA EMOJIS ==========
import sys
import io
import os
import warnings
import win32print  # ← Adicione esta linha com os outros imports

# Suprime warnings de encoding
warnings.filterwarnings('ignore', category=UnicodeWarning)

# Configuração segura - só tenta se o stream estiver aberto
def setup_encoding():
    try:
        if sys.stdout is not None and hasattr(sys.stdout, 'buffer'):
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except:
        pass
    
    try:
        if sys.stderr is not None and hasattr(sys.stderr, 'buffer'):
            sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except:
        pass

# Tenta configurar, mas não quebra se falhar
try:
    setup_encoding()
except:
    pass

# Força variáveis de ambiente
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["PYTHONUTF8"] = "1"
# ========================================================

# ========== FUNÇÃO fuso horário de Brasília (UTC-3)==========
def hora_brasil():
    """Retorna a hora atual no fuso horário de Brasília (UTC-3)"""
    utc_now = datetime.utcnow()
    hora_br = utc_now - timedelta(hours=3)
    return hora_br
# ===============================================

# ========== CONFIGURAÇÃO COM DETECÇÃO DE CAMINHO ==========
import sys
import os

# ===== DETECTAR ONDE O PROGRAMA ESTÁ RODANDO =====
if getattr(sys, 'frozen', False):
    # Rodando como executável
    BASE_DIR = os.path.dirname(sys.executable)
    print(f"📦 Modo Executável - Pasta base: {BASE_DIR}")
else:
    # Rodando em desenvolvimento
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    print(f"💻 Modo Desenvolvimento - Pasta: {BASE_DIR}")

app = Flask(__name__)
app.config['SECRET_KEY'] = 'havaianas-secret-key-2024'

# Configurar caminhos ABSOLUTOS
instance_path = os.path.join(BASE_DIR, 'instance')
db_path = os.path.join(instance_path, 'database.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Pastas de upload
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'uploads')
app.config['BACKUP_FOLDER'] = os.path.join(instance_path, 'backups')

# Configurações para upload
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2MB
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ===== CRIAR TODAS AS PASTAS NECESSÁRIAS =====
print("\n🔧 CRIANDO PASTAS DO SISTEMA...")

pastas = [
    instance_path,
    app.config['BACKUP_FOLDER'],
    app.config['UPLOAD_FOLDER'],
    os.path.join(app.config['UPLOAD_FOLDER'], 'produtos'),
    os.path.join(app.config['UPLOAD_FOLDER'], 'logo'),
]

for pasta in pastas:
    try:
        os.makedirs(pasta, exist_ok=True)
        print(f"✅ Pasta criada/verificada: {os.path.basename(pasta)}")
    except Exception as e:
        print(f"⚠️ Erro ao criar pasta {pasta}: {e}")

print("="*50)

db = SQLAlchemy(app)
# ================================================

# ===== FUNÇÃO PARA CRIAR THUMBNAIL =====
def criar_thumbnail(caminho_original, nome_arquivo):
    """Cria uma versão menor da imagem (100x100) para listas"""
    try:
        img = Image.open(caminho_original)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        img.thumbnail((100, 100))
        nome_thumbnail = 'thumb_' + nome_arquivo
        caminho_thumbnail = os.path.join(app.config['UPLOAD_FOLDER'], 'produtos', nome_thumbnail)
        img.save(caminho_thumbnail, 'JPEG', quality=85)
        print(f"✅ Thumbnail criado: {nome_thumbnail}")
        return nome_thumbnail
    except Exception as e:
        print(f"❌ Erro ao criar thumbnail: {e}")
        return None
# ========================================

# ========== MODELOS DO BANCO ==========
class Produto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(50), unique=True, nullable=False)
    descricao = db.Column(db.String(200))
    modelo = db.Column(db.String(50))
    colecao = db.Column(db.String(100))
    genero = db.Column(db.String(20))
    tipo = db.Column(db.String(20))
    preco_venda = db.Column(db.Float, default=29.90)
    custo = db.Column(db.Float, default=15.00)
    ativo = db.Column(db.Boolean, default=True)
    data_cadastro = db.Column(db.DateTime, default=datetime.utcnow)
    imagem = db.Column(db.String(200), nullable=True)
    grades = db.relationship('Grade', backref='produto', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Produto {self.sku}>'

class Grade(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    produto_id = db.Column(db.Integer, db.ForeignKey('produto.id'), nullable=False)
    cor = db.Column(db.String(50))
    tamanho = db.Column(db.String(10))
    estoque_atual = db.Column(db.Integer, default=0)
    estoque_minimo = db.Column(db.Integer, default=5)
    estoque_maximo = db.Column(db.Integer, default=50)
    sku_grade = db.Column(db.String(100), unique=True)
    localizacao = db.Column(db.String(50), default='PRATELEIRA-A')
    
    __table_args__ = (db.UniqueConstraint('produto_id', 'cor', 'tamanho'),)
    
    def atualizar_estoque(self, quantidade, tipo):
        if tipo == 'ENTRADA':
            self.estoque_atual += quantidade
        elif tipo == 'SAIDA':
            self.estoque_atual -= quantidade
        
        mov = Movimentacao(
            tipo=tipo,
            grade_id=self.id,
            quantidade=quantidade,
            origem='SISTEMA',
            observacao=f'Ajuste automático: {tipo}'
        )
        db.session.add(mov)
        return self

class Movimentacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(10))
    grade_id = db.Column(db.Integer, db.ForeignKey('grade.id'))
    quantidade = db.Column(db.Integer)
    data = db.Column(db.DateTime, default=hora_brasil)
    origem = db.Column(db.String(100))
    documento = db.Column(db.String(100))
    observacao = db.Column(db.Text)
    usuario = db.Column(db.String(100), default='Sistema')
    
    grade = db.relationship('Grade', backref='movimentacoes')

class Venda(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data = db.Column(db.DateTime, default=hora_brasil)
    total = db.Column(db.Float)
    forma_pagamento = db.Column(db.String(50))
    vendedor = db.Column(db.String(100), default='Sistema')
    cliente = db.Column(db.String(200))
    cliente_cpf = db.Column(db.String(20), nullable=True)
    desconto = db.Column(db.Float, default=0)
    status = db.Column(db.String(20), default='FINALIZADA')
    subtotal = db.Column(db.Float, default=0)
    desconto_percentual = db.Column(db.Float, default=0)
    itens = db.relationship('ItemVenda', backref='venda', lazy=True, cascade='all, delete-orphan')

class ItemVenda(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    venda_id = db.Column(db.Integer, db.ForeignKey('venda.id'))
    grade_id = db.Column(db.Integer, db.ForeignKey('grade.id'))
    quantidade = db.Column(db.Integer)
    preco_unitario = db.Column(db.Float)
    
    grade = db.relationship('Grade')

# ========== MODELOS PARA CONFIGURAÇÕES ==========
class Empresa(db.Model):
    """Dados da empresa para configurações"""
    id = db.Column(db.Integer, primary_key=True)
    razao_social = db.Column(db.String(200))
    nome_fantasia = db.Column(db.String(200))
    cnpj = db.Column(db.String(18))
    ie = db.Column(db.String(20))
    im = db.Column(db.String(20))
    endereco = db.Column(db.String(200))
    numero = db.Column(db.String(20))
    complemento = db.Column(db.String(100))
    bairro = db.Column(db.String(100))
    cidade = db.Column(db.String(100))
    uf = db.Column(db.String(2))
    cep = db.Column(db.String(10))
    telefone = db.Column(db.String(20))
    celular = db.Column(db.String(20))
    email = db.Column(db.String(100))
    website = db.Column(db.String(100))
    logo = db.Column(db.String(255))
    logo_login = db.Column(db.String(255))
    cor_primaria = db.Column(db.String(7), default='#0d6efd')
    cor_secundaria = db.Column(db.String(7), default='#6c757d')
    cor_sucesso = db.Column(db.String(7), default='#198754')
    data_atualizacao = db.Column(db.DateTime, default=hora_brasil, onupdate=hora_brasil)

    # CAMPOS PARA FONTE DA NAVBAR
    fonte_navbar_familia = db.Column(db.String(50), default='Segoe UI')
    fonte_navbar_tamanho = db.Column(db.Integer, default=18)
    fonte_navbar_cor = db.Column(db.String(7), default='#ffffff')
    
    # CAMPOS PARA FONTE DO LOGIN
    fonte_login_familia = db.Column(db.String(50), default='Segoe UI')
    fonte_login_tamanho = db.Column(db.Integer, default=28)
    fonte_login_cor = db.Column(db.String(7), default='#ffffff')

    # ===== NOVOS CAMPOS PARA CONFIGURAÇÃO DE IMPRESSÃO PROFISSIONAL =====
    impressao_tipo = db.Column(db.String(20), default='dialogo')  # dialogo, auto, visualizar
    impressao_papel = db.Column(db.String(10), default='80mm')    # 58mm, 80mm, a4
    impressao_vias = db.Column(db.Integer, default=1)             # Número de vias
    impressao_copiar = db.Column(db.Boolean, default=False)       # Copiar via para cliente
    impressao_mensagem = db.Column(db.Text, default='Obrigado pela preferência!')
    # =======================================================
    # 🔥 NOVO: Campo para impressora padrão
    impressora_padrao_id = db.Column(db.Integer, default=1)        # ID da impressora padrão
    impressora_padrao_nome = db.Column(db.String(100), default='Microsoft Print to PDF')  # Nome da impressora
    # =======================================================


    def __repr__(self):
        return f'<Empresa {self.nome_fantasia}>'

class ConfigComprovante(db.Model):
    """Configurações do comprovante de venda"""
    id = db.Column(db.Integer, primary_key=True)
    cabecalho = db.Column(db.Text, default='')
    rodape = db.Column(db.Text, default='Obrigado pela preferência!')
    mostrar_cnpj = db.Column(db.Boolean, default=True)
    mostrar_endereco = db.Column(db.Boolean, default=True)
    mostrar_telefone = db.Column(db.Boolean, default=True)
    mostrar_mensagem = db.Column(db.Boolean, default=True)
    mostrar_logo = db.Column(db.Boolean, default=True)
    tamanho_papel = db.Column(db.String(20), default='80mm')
    fonte_tamanho = db.Column(db.Integer, default=12)
    data_atualizacao = db.Column(db.DateTime, default=hora_brasil, onupdate=hora_brasil)

# ========== MODELOS PARA CLIENTES ==========
class Cliente(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    tipo = db.Column(db.String(10), default='FISICA')
    cpf_cnpj = db.Column(db.String(20), unique=True)
    rg = db.Column(db.String(20))
    email = db.Column(db.String(100))
    telefone = db.Column(db.String(20))
    celular = db.Column(db.String(20), nullable=False)
    whatsapp = db.Column(db.Boolean, default=False)
    logradouro = db.Column(db.String(200))
    numero = db.Column(db.String(10))
    bairro = db.Column(db.String(100))
    complemento = db.Column(db.String(100))
    cidade = db.Column(db.String(100))
    estado = db.Column(db.String(2))
    cep = db.Column(db.String(10))
    observacoes = db.Column(db.Text)
    ativo = db.Column(db.Boolean, default=True)
    data_cadastro = db.Column(db.DateTime, default=hora_brasil)
    total_vendas = db.Column(db.Integer, default=0)
    total_gasto = db.Column(db.Float, default=0.0)

class Fornecedor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    razao_social = db.Column(db.String(200), nullable=False)
    nome_fantasia = db.Column(db.String(200))
    cnpj = db.Column(db.String(20), unique=True, nullable=False)
    inscricao_estadual = db.Column(db.String(20))
    email = db.Column(db.String(100))
    telefone = db.Column(db.String(20))
    celular = db.Column(db.String(20))
    responsavel = db.Column(db.String(100))
    logradouro = db.Column(db.String(200))
    numero = db.Column(db.String(10))
    bairro = db.Column(db.String(100))
    complemento = db.Column(db.String(100))
    cidade = db.Column(db.String(100))
    estado = db.Column(db.String(2))
    cep = db.Column(db.String(10))
    observacoes = db.Column(db.Text)
    ativo = db.Column(db.Boolean, default=True)
    data_cadastro = db.Column(db.DateTime, default=hora_brasil)
    total_compras = db.Column(db.Integer, default=0)
    valor_total_compras = db.Column(db.Float, default=0.0)

# ========== MODELO DE USUÁRIO PARA LOGIN ==========
class Usuario(db.Model):
    """Modelo para autenticação de usuários no sistema"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    nome = db.Column(db.String(100))
    email = db.Column(db.String(100))
    telefone = db.Column(db.String(20))
    admin = db.Column(db.Boolean, default=False)
    ativo = db.Column(db.Boolean, default=True)
    ultimo_acesso = db.Column(db.DateTime)
    data_cadastro = db.Column(db.DateTime, default=hora_brasil)
    # ===== PERMISSÕES DE BACKUP =====
    backup_visualizar = db.Column(db.Boolean, default=False)
    backup_criar = db.Column(db.Boolean, default=False)
    backup_baixar = db.Column(db.Boolean, default=False)
    backup_restaurar = db.Column(db.Boolean, default=False)
    backup_excluir = db.Column(db.Boolean, default=False)
    # =================================

    def __repr__(self):
        return f'<Usuario {self.username}>'
    
# ========== MODELOS PARA CATÁLOGO DINÂMICO ==========
class Modelo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), unique=True, nullable=False)
    codigo = db.Column(db.String(10), unique=True)
    ativo = db.Column(db.Boolean, default=True)
    data_cadastro = db.Column(db.DateTime, default=hora_brasil)

class Cor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), unique=True, nullable=False)
    hex = db.Column(db.String(7), default='#6c757d')
    ativo = db.Column(db.Boolean, default=True)
    data_cadastro = db.Column(db.DateTime, default=hora_brasil)

class Tamanho(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    valor = db.Column(db.String(10), unique=True, nullable=False)
    categoria = db.Column(db.String(20), default='Adulto')
    ordem = db.Column(db.Integer, default=0)
    ativo = db.Column(db.Boolean, default=True)
    data_cadastro = db.Column(db.DateTime, default=hora_brasil)

class Localizacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), unique=True, nullable=False)
    descricao = db.Column(db.String(100))
    tipo = db.Column(db.String(20), default='PRATELEIRA')
    ativo = db.Column(db.Boolean, default=True)
    data_cadastro = db.Column(db.DateTime, default=hora_brasil)

# ========== MODELO PARA INVENTÁRIO ==========
class Inventario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data_inicio = db.Column(db.DateTime, default=hora_brasil)
    data_fim = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='EM_ANDAMENTO')
    tipo = db.Column(db.String(20), default='COMPLETO')
    observacao = db.Column(db.Text)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    usuario = db.relationship('Usuario')
    
    contagens = db.relationship('InventarioItem', backref='inventario', lazy=True, cascade='all, delete-orphan')

class InventarioItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    inventario_id = db.Column(db.Integer, db.ForeignKey('inventario.id'))
    grade_id = db.Column(db.Integer, db.ForeignKey('grade.id'))
    quantidade_sistema = db.Column(db.Integer, default=0)
    quantidade_contada = db.Column(db.Integer, default=0)
    quantidade_ajuste = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='PENDENTE')
    observacao = db.Column(db.Text)
    data_contagem = db.Column(db.DateTime)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    usuario = db.relationship('Usuario', foreign_keys=[usuario_id])
    
    grade = db.relationship('Grade')
    
    def calcular_diferenca(self):
        self.quantidade_ajuste = self.quantidade_contada - self.quantidade_sistema
        return self.quantidade_ajuste

# ========== MODELO PARA IMPRESSORAS (NOVO) ==========
class Impressora(db.Model):
    """Modelo para gerenciar múltiplas impressoras"""
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    modelo = db.Column(db.String(100))
    tipo = db.Column(db.String(20), default='nao_fiscal')  # fiscal, nao_fiscal, etiqueta, relatorio
    porta = db.Column(db.String(50))  # USB, COM1, TCP/IP
    endereco = db.Column(db.String(100))  # IP ou caminho
    padrao = db.Column(db.Boolean, default=False)
    ativo = db.Column(db.Boolean, default=True)
    data_cadastro = db.Column(db.DateTime, default=hora_brasil)

# ========== FUNÇÕES PARA TEMPLATES ==========  
def cor_para_hex(cor_nome):
    """Converte nome de cor para código hexadecimal"""
    if not cor_nome:
        return '#cccccc'
    
    cores_map = {
        'azul': '#0066cc', 'vermelho': '#dc3545', 'verde': '#28a745',
        'amarelo': '#ffc107', 'preto': '#000000', 'branco': '#ffffff',
        'rosa': '#e83e8c', 'roxo': '#6f42c1', 'laranja': '#fd7e14',
        'marrom': '#8b4513', 'cinza': '#6c757d'
    }
    
    cor_lower = cor_nome.lower()
    for chave, valor in cores_map.items():
        if chave in cor_lower:
            return valor
    
    import hashlib
    hash_obj = hashlib.md5(cor_nome.encode())
    return f'#{hash_obj.hexdigest()[:6]}'

# ========== Formata valor para moeda brasileira ==========
def format_currency(value):
    """Formata valor para moeda brasileira"""
    if value is None:
        return "R$ 0,00"
    
    try:
        if isinstance(value, str):
            value = value.replace('R$', '').replace(' ', '').strip()
            if ',' in value and '.' in value:
                value = value.replace('.', '').replace(',', '.')
            elif ',' in value:
                value = value.replace(',', '.')
        
        valor = float(value)
        valor_str = f"{valor:,.2f}"
        valor_str = valor_str.replace(",", "X").replace(".", ",").replace("X", ".")
        
        return f"R$ {valor_str}"
    except (ValueError, TypeError) as e:
        print(f"Erro ao formatar valor '{value}': {e}")
        return "R$ 0,00"

def format_number(value):
    """Formata número com separador de milhar e decimal brasileiro"""
    if value is None:
        return "0,00"
    
    try:
        valor = float(value)
        valor_str = f"{valor:,.2f}"
        valor_str = valor_str.replace(",", "X").replace(".", ",").replace("X", ".")
        return valor_str
    except:
        return "0,00"

# ========== ADICIONE ESTAS 3 LINHAS CRÍTICAS ==========
app.jinja_env.filters['format_currency'] = format_currency
app.jinja_env.filters['format_number'] = format_number
app.jinja_env.filters['cor_para_hex'] = cor_para_hex

# ========== FILTROS PARA TEMPLATES ==========
def format_cpf(cpf):
    """Formata CPF: 000.000.000-00"""
    if not cpf:
        return ""
    cpf = str(cpf).replace(".", "").replace("-", "")
    if len(cpf) == 11:
        return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
    return cpf

def format_cnpj(cnpj):
    """Formata CNPJ: 00.000.000/0000-00"""
    if not cnpj:
        return ""
    cnpj = str(cnpj).replace(".", "").replace("-", "").replace("/", "")
    if len(cnpj) == 14:
        return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
    return cnpj

app.jinja_env.filters['format_cpf'] = format_cpf
app.jinja_env.filters['format_cnpj'] = format_cnpj

@app.context_processor
def utility_processor():
    def get_now():
        return datetime.utcnow()
    
    def get_today():
        return datetime.utcnow().date()
    
    empresa = Empresa.query.first()
    
    return dict(
        now=get_now,
        hoje=get_today,
        cor_para_hex=cor_para_hex,
        empresa=empresa
    )

# ========== ROTAS PRINCIPAIS ==========
@app.route('/')
def dashboard():
    # ===== PROTEÇÃO DE LOGIN =====
    if 'usuario_id' not in session:
        flash('Faça login para acessar o sistema!', 'error')
        return redirect(url_for('login'))
    # ==============================
    
    total_produtos = Produto.query.filter_by(ativo=True).count()
    total_grades = Grade.query.count()
    
    estoque_result = db.session.query(func.sum(Grade.estoque_atual)).scalar()
    total_estoque = int(estoque_result) if estoque_result else 0
    
    estoque_baixo = Grade.query.filter(Grade.estoque_atual < Grade.estoque_minimo).count()
    estoque_zero = Grade.query.filter(Grade.estoque_atual == 0).count()
    
    hoje = datetime.utcnow().date()
    vendas_hoje = Venda.query.filter(func.date(Venda.data) == hoje).count()
    
    ultima_venda_obj = Venda.query.filter(
        func.date(Venda.data) == hoje
    ).order_by(Venda.data.desc()).first()
    ultima_venda_hora = ultima_venda_obj.data.strftime('%H:%M') if ultima_venda_obj else '--:--'
    
    ultimas_mov = Movimentacao.query.order_by(Movimentacao.data.desc()).limit(10).all()
    
    modelos_query = db.session.query(
        Produto.modelo,
        func.sum(Grade.estoque_atual).label('total')
    ).join(Grade).filter(Produto.modelo.isnot(None)).group_by(Produto.modelo).all()
    
    modelos = []
    estoque_por_modelo = []
    
    for modelo in modelos_query:
        if modelo.modelo and modelo.total:
            modelos.append(modelo.modelo)
            estoque_por_modelo.append(modelo.total)
    
    try:
        sete_dias_atras = datetime.utcnow() - timedelta(days=7)
        top_produtos = db.session.query(
            Produto,
            func.sum(ItemVenda.quantidade).label('total_vendido'),
            func.sum(ItemVenda.quantidade * ItemVenda.preco_unitario).label('valor_total')
        ).join(Grade, Produto.id == Grade.produto_id)\
         .join(ItemVenda, Grade.id == ItemVenda.grade_id)\
         .join(Venda, ItemVenda.venda_id == Venda.id)\
         .filter(Venda.data >= sete_dias_atras)\
         .group_by(Produto.id)\
         .order_by(func.sum(ItemVenda.quantidade).desc())\
         .limit(5).all()
    except:
        top_produtos = db.session.query(
            Produto,
            func.sum(Grade.estoque_atual).label('total_estoque')
        ).join(Grade).group_by(Produto.id)\
         .order_by(func.sum(Grade.estoque_atual).desc())\
         .limit(5).all()
        top_produtos = [(p, e, 0) for p, e in top_produtos]
    
    return render_template('pages/dashboard.html',
                         total_produtos=total_produtos,
                         total_grades=total_grades,
                         total_estoque=total_estoque,
                         estoque_baixo=estoque_baixo,
                         estoque_zero=estoque_zero,
                         vendas_hoje=vendas_hoje,
                         ultimas_mov=ultimas_mov,
                         ultima_venda_hora=ultima_venda_hora,
                         modelos=modelos,
                         estoque_normal=estoque_por_modelo,
                         estoque_baixo_list=[0] * len(modelos) if modelos else [],
                         estoque_critico=[0] * len(modelos) if modelos else [],
                         top_produtos=top_produtos)

# ========== ROTAS DE LOGIN ==========
@app.route('/login', methods=['GET', 'POST'])
def login():
    """Página de login do sistema"""
    if session.get('usuario_id'):
        return redirect(url_for('dashboard'))
    
    empresa = Empresa.query.first()
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        if not username or not password:
            flash('Preencha usuário e senha!', 'error')
            return redirect(url_for('login'))
        
        usuario = Usuario.query.filter_by(username=username, ativo=True).first()
        
        if usuario and usuario.password == password:
            session['usuario_id'] = usuario.id
            session['usuario_nome'] = usuario.nome or usuario.username
            session['usuario_username'] = usuario.username
            session['usuario_admin'] = usuario.admin
            
            # ===== PERMISSÕES DE BACKUP NA SESSÃO =====
            session['backup_visualizar'] = usuario.admin or usuario.backup_visualizar
            session['backup_criar'] = usuario.admin or usuario.backup_criar
            session['backup_baixar'] = usuario.admin or usuario.backup_baixar
            session['backup_restaurar'] = usuario.admin or usuario.backup_restaurar
            session['backup_excluir'] = usuario.admin or usuario.backup_excluir
            # =========================================
            
            usuario.ultimo_acesso = hora_brasil()
            db.session.commit()
            
            flash(f'🔔 Bem-vindo, {usuario.nome or usuario.username}!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Usuário ou senha inválidos!', 'error')
            return redirect(url_for('login'))
    
    return render_template('login/login.html', empresa=empresa)

@app.route('/logout')
def logout():
    session.clear()
    flash('👋 Logout realizado com sucesso!', 'success')
    return redirect(url_for('login'))

def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario_id' not in session:
            flash('Faça login para acessar esta página!', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator para exigir privilégios de administrador"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario_id' not in session:
            flash('Faça login para acessar esta página!', 'error')
            return redirect(url_for('login'))
        if not session.get('usuario_admin'):
            flash('Acesso restrito a administradores!', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# ========== ROTAS PARA GESTÃO DE USUÁRIOS ==========
@app.route('/usuarios')
@login_required
@admin_required
def listar_usuarios():
    """Lista todos os usuários do sistema"""
    busca = request.args.get('q', '')
    status = request.args.get('status', 'ativos')
    ordenar = request.args.get('ordenar', 'id')
    
    query = Usuario.query
    
    if busca:
        query = query.filter(
            (Usuario.username.contains(busca)) |
            (Usuario.nome.contains(busca)) |
            (Usuario.email.contains(busca))
        )
    
    if status == 'ativos':
        query = query.filter_by(ativo=True)
    elif status == 'inativos':
        query = query.filter_by(ativo=False)
    elif status == 'admins':
        query = query.filter_by(admin=True)
    elif status == 'operadores':
        query = query.filter_by(admin=False)
    
    if ordenar == 'username':
        query = query.order_by(Usuario.username.asc())
    elif ordenar == 'username_desc':
        query = query.order_by(Usuario.username.desc())
    elif ordenar == 'nome':
        query = query.order_by(Usuario.nome.asc().nulls_last())
    elif ordenar == 'nome_desc':
        query = query.order_by(Usuario.nome.desc().nulls_last())
    elif ordenar == 'data':
        query = query.order_by(Usuario.data_cadastro.asc())
    elif ordenar == 'data_desc':
        query = query.order_by(Usuario.data_cadastro.desc())
    elif ordenar == 'acesso':
        query = query.order_by(Usuario.ultimo_acesso.desc().nulls_last())
    else:
        query = query.order_by(Usuario.id.asc())
    
    usuarios = query.all()
    
    total_usuarios = Usuario.query.count()
    usuarios_ativos = Usuario.query.filter_by(ativo=True).count()
    usuarios_inativos = Usuario.query.filter_by(ativo=False).count()
    administradores = Usuario.query.filter_by(admin=True).count()
    
    return render_template('usuarios/lista.html',
                         usuarios=usuarios,
                         busca=busca,
                         status=status,
                         ordenar=ordenar,
                         total_usuarios=total_usuarios,
                         usuarios_ativos=usuarios_ativos,
                         usuarios_inativos=usuarios_inativos,
                         administradores=administradores)

@app.route('/usuario/novo', methods=['GET', 'POST'])
@login_required
@admin_required
def novo_usuario():
    """Criar novo usuário"""
    form_data = {}
    
    if request.method == 'POST':
        try:
            username = request.form['username'].strip()
            password = request.form['password'].strip()
            
            form_data = {
                'username': username,
                'nome': request.form.get('nome', '').strip(),
                'email': request.form.get('email', '').strip().lower(),
                'telefone': request.form.get('telefone', '').strip(),
                'admin': request.form.get('admin', '0'),
                'ativo': request.form.get('ativo', '1')
            }
            
            if not username or not password:
                flash('Usuário e senha são obrigatórios!', 'error')
                return render_template('usuarios/novo.html', form_data=form_data)
            
            if len(password) < 6:
                flash('A senha deve ter no mínimo 6 caracteres!', 'error')
                return render_template('usuarios/novo.html', form_data=form_data)
            
            if Usuario.query.filter_by(username=username).first():
                flash(f'Usuário "{username}" já existe!', 'error')
                return render_template('usuarios/novo.html', form_data=form_data)
            
            admin_value = True if request.form.get('admin') == '1' else False
            ativo_value = True if request.form.get('ativo') == '1' else True
            
            usuario = Usuario(
                username=username,
                password=password,
                nome=request.form.get('nome', '').strip(),
                email=request.form.get('email', '').strip().lower(),
                telefone=request.form.get('telefone', '').strip(),
                admin=admin_value,
                ativo=ativo_value
            )
            
            db.session.add(usuario)
            db.session.commit()
            
            flash(f'✅ Usuário "{username}" criado com sucesso!', 'success')
            return redirect(url_for('listar_usuarios'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Erro ao criar usuário: {str(e)}', 'error')
            return render_template('usuarios/novo.html', form_data=form_data)
    
    return render_template('usuarios/novo.html', form_data={})

@app.route('/usuario/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@admin_required
def editar_usuario(id):
    """Editar usuário existente"""
    usuario = Usuario.query.get_or_404(id)
    form_data = {}
    
    if id == session['usuario_id']:
        flash('Você não pode editar seu próprio usuário nesta tela!', 'warning')
        return redirect(url_for('listar_usuarios'))
    
    if request.method == 'POST':
        try:
            username = request.form['username'].strip()
            
            form_data = {
                'username': username,
                'nome': request.form.get('nome', '').strip(),
                'email': request.form.get('email', '').strip().lower(),
                'telefone': request.form.get('telefone', '').strip(),
                'admin': request.form.get('admin', '0' if not usuario.admin else '1'),
                'ativo': request.form.get('ativo', '1' if usuario.ativo else '0')
            }
            
            existente = Usuario.query.filter_by(username=username).first()
            if existente and existente.id != id:
                flash(f'Usuário "{username}" já existe!', 'error')
                return render_template('usuarios/editar.html', usuario=usuario, form_data=form_data)
            
            admin_value = True if request.form.get('admin') == '1' else False
            ativo_value = True if request.form.get('ativo') == '1' else False
            
            usuario.username = username
            usuario.nome = request.form.get('nome', '').strip()
            usuario.email = request.form.get('email', '').strip().lower()
            usuario.telefone = request.form.get('telefone', '').strip()
            usuario.admin = admin_value
            usuario.ativo = ativo_value
            
            nova_senha = request.form.get('password', '').strip()
            if nova_senha:
                if len(nova_senha) < 6:
                    flash('A senha deve ter no mínimo 6 caracteres!', 'error')
                    return render_template('usuarios/editar.html', usuario=usuario, form_data=form_data)
                usuario.password = nova_senha
            
            db.session.commit()
            
            flash(f'✅ Usuário "{username}" atualizado!', 'success')
            return redirect(url_for('listar_usuarios'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Erro ao atualizar: {str(e)}', 'error')
            return render_template('usuarios/editar.html', usuario=usuario, form_data=form_data)
    
    return render_template('usuarios/editar.html', usuario=usuario, form_data={})

@app.route('/usuario/toggle/<int:id>', methods=['POST'])
@login_required
@admin_required
def toggle_usuario(id):
    """Ativar/desativar usuário"""
    if id == session['usuario_id']:
        flash('Você não pode desativar seu próprio usuário!', 'error')
        return redirect(url_for('listar_usuarios'))
    
    usuario = Usuario.query.get_or_404(id)
    usuario.ativo = not usuario.ativo
    db.session.commit()
    
    status = "ativado" if usuario.ativo else "desativado"
    flash(f'✅ Usuário "{usuario.username}" {status}!', 'success')
    return redirect(url_for('listar_usuarios'))

@app.route('/usuario/reset-senha/<int:id>', methods=['POST'])
@login_required
@admin_required
def resetar_senha_usuario(id):
    """Resetar senha para 123456"""
    usuario = Usuario.query.get_or_404(id)
    usuario.password = '123456'
    db.session.commit()
    
    flash(f'✅ Senha do usuário "{usuario.username}" resetada para 123456', 'success')
    return redirect(url_for('listar_usuarios'))

@app.route('/usuario/excluir/<int:id>', methods=['POST'])
@login_required
@admin_required
def excluir_usuario(id):
    """Excluir um usuário permanentemente"""
    if id == session['usuario_id']:
        flash('Você não pode excluir seu próprio usuário!', 'error')
        return redirect(url_for('listar_usuarios'))
    
    usuario = Usuario.query.get_or_404(id)
    
    try:
        nome = usuario.nome or usuario.username
        username = usuario.username
        
        db.session.delete(usuario)
        db.session.commit()
        
        flash(f'✅ Usuário "{nome}" excluído com sucesso!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Erro ao excluir usuário: {str(e)}', 'error')
    
    return redirect(url_for('listar_usuarios'))

@app.route('/api/usuarios/permissoes', methods=['POST'])
@login_required
@admin_required
def api_alterar_permissao():
    """API para alterar uma permissão específica"""
    try:
        dados = request.json
        usuario_id = dados.get('usuario_id')
        permissao = dados.get('permissao')
        valor = dados.get('valor')
        
        permissoes_validas = ['backup_visualizar', 'backup_criar', 'backup_baixar', 
                              'backup_restaurar', 'backup_excluir']
        
        if permissao not in permissoes_validas:
            return jsonify({'success': False, 'error': 'Permissão inválida'}), 400
        
        usuario = Usuario.query.get(usuario_id)
        if not usuario:
            return jsonify({'success': False, 'error': 'Usuário não encontrado'}), 404
        
        if usuario.admin:
            return jsonify({'success': False, 'error': 'Administradores sempre têm todas as permissões'}), 400
        
        # Salva a permissão no banco de dados
        setattr(usuario, permissao, valor)
        db.session.commit()
        
        # Retorna a MESMA mensagem para TODAS as permissões
        return jsonify({
            'success': True,
            'mensagem': '✅  Permissão atualizada com sucesso!'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/usuarios/<int:id>')
@login_required
def api_usuario_detalhes(id):
    """API para obter detalhes de um usuário"""
    usuario = Usuario.query.get_or_404(id)
    
    return jsonify({
        'id': usuario.id,
        'username': usuario.username,
        'nome': usuario.nome,
        'email': usuario.email,
        'telefone': usuario.telefone,
        'admin': usuario.admin,
        'ativo': usuario.ativo,
        'ultimo_acesso': usuario.ultimo_acesso.strftime('%d/%m/%Y %H:%M') if usuario.ultimo_acesso else None,
        'data_cadastro': usuario.data_cadastro.strftime('%d/%m/%Y %H:%M') if usuario.data_cadastro else None
    })

# ========== ROTAS PARA PERFIL DO USUÁRIO ==========
@app.route('/perfil')
@login_required
def perfil():
    """Página de perfil do usuário logado"""
    usuario = Usuario.query.get(session['usuario_id'])
    return render_template('usuarios/perfil.html', usuario=usuario)

@app.route('/perfil/atualizar', methods=['POST'])
@login_required
def perfil_atualizar():
    """Atualizar dados do perfil"""
    usuario = Usuario.query.get(session['usuario_id'])
    
    try:
        usuario.nome = request.form.get('nome', '').strip()
        usuario.email = request.form.get('email', '').strip().lower()
        usuario.telefone = request.form.get('telefone', '').strip()
        
        session['usuario_nome'] = usuario.nome or usuario.username
        
        db.session.commit()
        flash('✅ Perfil atualizado com sucesso!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Erro ao atualizar perfil: {str(e)}', 'error')
    
    return redirect(url_for('perfil'))

@app.route('/perfil/alterar-senha', methods=['POST'])
@login_required
def perfil_alterar_senha():
    """Alterar senha do usuário"""
    usuario = Usuario.query.get(session['usuario_id'])
    
    senha_atual = request.form.get('senha_atual', '')
    nova_senha = request.form.get('nova_senha', '')
    confirmar_senha = request.form.get('confirmar_senha', '')
    
    if not senha_atual or not nova_senha or not confirmar_senha:
        flash('❌ Preencha todos os campos!', 'error')
        return redirect(url_for('perfil'))
    
    if usuario.password != senha_atual:
        flash('❌ Senha atual incorreta!', 'error')
        return redirect(url_for('perfil'))
    
    if len(nova_senha) < 6:
        flash('❌ A nova senha deve ter no mínimo 6 caracteres!', 'error')
        return redirect(url_for('perfil'))
    
    if nova_senha != confirmar_senha:
        flash('❌ As senhas não conferem!', 'error')
        return redirect(url_for('perfil'))
    
    try:
        usuario.password = nova_senha
        db.session.commit()
        flash('✅ Senha alterada com sucesso!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Erro ao alterar senha: {str(e)}', 'error')
    
    return redirect(url_for('perfil'))

# ========== ROTAS DE PRODUTOS ==========
@app.route('/produtos')
def produtos():
    filtro = request.args.get('filtro', 'ativos')
    busca = request.args.get('q', '')
    
    if filtro == 'todos':
        query = Produto.query
    elif filtro == 'inativos':
        query = Produto.query.filter_by(ativo=False)
    else:
        query = Produto.query.filter_by(ativo=True)
    
    if busca:
        query = query.filter(
            (Produto.sku.contains(busca)) |
            (Produto.descricao.contains(busca)) |
            (Produto.modelo.contains(busca)) |
            (Produto.colecao.contains(busca))
        )
    
    if filtro == 'inativos':
        produtos_list = query.order_by(
            Produto.ativo.desc(),
            Produto.id.asc()
        ).all()
    else:
        produtos_list = query.order_by(Produto.id.asc()).all()
    
    return render_template('produtos/lista.html', 
                         produtos=produtos_list,
                         filtro=filtro,
                         busca=busca)

@app.route('/produto/novo', methods=['GET', 'POST'])
def novo_produto():
    if request.method == 'POST':
        try:
            codigo_base = request.form['codigo_base'].upper().strip()
            
            produto_existente = Produto.query.filter_by(sku=codigo_base).first()
            if produto_existente:
                flash(f'❌ Produto com SKU "{codigo_base}" já existe no sistema!', 'danger')
                modelos = ['Slim', 'Top', 'Eco', 'Flash', 'Sprint', 'Tradiçao', 'Classic', 'Brasil']
                return render_template('produtos/novo.html', modelos=modelos)
            
            descricao = request.form['descricao']
            modelo = request.form['modelo']
            genero = request.form['genero']
            tipo = request.form['tipo']
            preco_venda = float(request.form['preco'])
            colecao = request.form.get('colecao', '')
            custo = float(request.form['custo'])
            
            imagem_nome = None
            if 'imagem' in request.files:
                file = request.files['imagem']
                if file and file.filename != '' and allowed_file(file.filename):
                    filename = secure_filename(file.filename)
                    import time
                    nome_arquivo = f"{int(time.time())}_{filename}"
                    
                    caminho_completo = os.path.join(app.config['UPLOAD_FOLDER'], 'produtos', nome_arquivo)
                    
                    file.save(caminho_completo)
                    imagem_nome = nome_arquivo
                    print(f"✅ Imagem original salva: {nome_arquivo}")
                    
                    try:
                        img = Image.open(caminho_completo)
                        if img.mode in ('RGBA', 'P'):
                            img = img.convert('RGB')
                        img.thumbnail((100, 100))
                        nome_thumbnail = 'thumb_' + nome_arquivo
                        caminho_thumbnail = os.path.join(app.config['UPLOAD_FOLDER'], 'produtos', nome_thumbnail)
                        img.save(caminho_thumbnail, 'JPEG', quality=85)
                        print(f"✅ Thumbnail criado: {nome_thumbnail}")
                    except Exception as e:
                        print(f"❌ Erro ao criar thumbnail: {e}")
            
            produto = Produto(
                sku=codigo_base,
                descricao=descricao,
                modelo=modelo,
                colecao=colecao,
                genero=genero,
                tipo=tipo,
                preco_venda=preco_venda,
                custo=custo,
                imagem=imagem_nome
            )
            db.session.add(produto)
            db.session.flush()
            
            cores = request.form.getlist('cor[]')
            tamanhos = request.form.getlist('tamanho[]')
            estoques = request.form.getlist('estoque[]')
            minimos = request.form.getlist('estoque_minimo[]')
            maximos = request.form.getlist('estoque_maximo[]')
            localizacoes = request.form.getlist('localizacao[]')
            
            grades_criadas = 0
            
            for i in range(len(cores)):
                if cores[i] and tamanhos[i]:
                    sku_grade = f"{codigo_base}-{cores[i].upper()}-{tamanhos[i]}"
                    
                    grade = Grade(
                        produto_id=produto.id,
                        cor=cores[i],
                        tamanho=tamanhos[i],
                        estoque_atual=int(estoques[i]) if i < len(estoques) else 0,
                        estoque_minimo=int(minimos[i]) if i < len(minimos) else 5,
                        estoque_maximo=int(maximos[i]) if i < len(maximos) else 50,
                        sku_grade=sku_grade,
                        localizacao=localizacoes[i] if i < len(localizacoes) else 'PRATELEIRA-A'
                    )
                    db.session.add(grade)
                    grades_criadas += 1
            
            db.session.commit()
            flash(f'✅ Produto cadastrado com {grades_criadas} grade(s)!', 'success')
            return redirect(url_for('produtos'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Erro ao cadastrar: {str(e)}', 'danger')
    
    modelos = ['Slim', 'Top', 'Eco', 'Flash', 'Sprint', 'Tradiçao', 'Classic', 'Brasil']
    return render_template('produtos/novo.html', modelos=modelos)

@app.route('/produto/<int:id>')
def detalhe_produto(id):
    produto = Produto.query.get_or_404(id)
    return render_template('produtos/detalhes.html', produto=produto)

@app.route('/produto/editar/<int:id>', methods=['GET', 'POST'])
def editar_produto(id):
    produto = Produto.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            def converter_preco_brasileiro(valor_str):
                if not valor_str:
                    return 0.0
                valor_str = valor_str.strip()
                if '.' in valor_str and ',' in valor_str:
                    valor_str = valor_str.replace('.', '').replace(',', '.')
                elif ',' in valor_str and '.' not in valor_str:
                    valor_str = valor_str.replace(',', '.')
                try:
                    return float(valor_str)
                except ValueError:
                    valor_str = ''.join(c for c in valor_str if c.isdigit() or c in '.,')
                    if ',' in valor_str:
                        valor_str = valor_str.replace(',', '.', 1)
                    return float(valor_str) if valor_str else 0.0
            
            produto.sku = request.form['codigo_base'].upper()
            produto.descricao = request.form['descricao']
            produto.modelo = request.form['modelo']
            produto.genero = request.form['genero']
            produto.tipo = request.form['tipo']
            
            preco_str = request.form['preco']
            produto.preco_venda = converter_preco_brasileiro(preco_str)
            
            custo_str = request.form.get('custo', '0')
            produto.custo = converter_preco_brasileiro(custo_str)
            
            produto.colecao = request.form.get('colecao', '')
            
            if request.form.get('remover_imagem') == '1':
                if produto.imagem:
                    try:
                        caminho_imagem = os.path.join(app.config['UPLOAD_FOLDER'], 'produtos', produto.imagem)
                        if os.path.exists(caminho_imagem):
                            os.remove(caminho_imagem)
                            print(f"🗑️ Imagem removida: {produto.imagem}")
                        
                        caminho_thumb = os.path.join(app.config['UPLOAD_FOLDER'], 'produtos', 'thumb_' + produto.imagem)
                        if os.path.exists(caminho_thumb):
                            os.remove(caminho_thumb)
                            print(f"🗑️ Thumbnail removido: thumb_{produto.imagem}")
                    except Exception as e:
                        print(f"⚠️ Erro ao remover imagens: {e}")
                produto.imagem = None
            
            if 'imagem' in request.files:
                file = request.files['imagem']
                if file and file.filename != '' and allowed_file(file.filename):
                    if produto.imagem:
                        try:
                            caminho_imagem_antiga = os.path.join(app.config['UPLOAD_FOLDER'], 'produtos', produto.imagem)
                            if os.path.exists(caminho_imagem_antiga):
                                os.remove(caminho_imagem_antiga)
                                print(f"🗑️ Imagem antiga removida: {produto.imagem}")
                            
                            caminho_thumb_antigo = os.path.join(app.config['UPLOAD_FOLDER'], 'produtos', 'thumb_' + produto.imagem)
                            if os.path.exists(caminho_thumb_antigo):
                                os.remove(caminho_thumb_antigo)
                                print(f"🗑️ Thumbnail antigo removido: thumb_{produto.imagem}")
                        except Exception as e:
                            print(f"⚠️ Erro ao remover arquivos antigos: {e}")
                    
                    filename = secure_filename(file.filename)
                    import time
                    nome_arquivo = f"{int(time.time())}_{filename}"
                    
                    caminho_completo = os.path.join(app.config['UPLOAD_FOLDER'], 'produtos', nome_arquivo)
                    
                    file.save(caminho_completo)
                    produto.imagem = nome_arquivo
                    print(f"✅ Nova imagem salva: {nome_arquivo}")
                    
                    try:
                        img = Image.open(caminho_completo)
                        if img.mode in ('RGBA', 'P'):
                            img = img.convert('RGB')
                        img.thumbnail((100, 100))
                        nome_thumbnail = 'thumb_' + nome_arquivo
                        caminho_thumbnail = os.path.join(app.config['UPLOAD_FOLDER'], 'produtos', nome_thumbnail)
                        img.save(caminho_thumbnail, 'JPEG', quality=85)
                        print(f"✅ Thumbnail criado: {nome_thumbnail}")
                    except Exception as e:
                        print(f"❌ Erro ao criar thumbnail: {e}")
            
            grade_ids = request.form.getlist('grade_id[]')
            cores = request.form.getlist('cor[]')
            tamanhos = request.form.getlist('tamanho[]')
            estoques = request.form.getlist('estoque[]')
            minimos = request.form.getlist('estoque_minimo[]')
            maximos = request.form.getlist('estoque_maximo[]')
            localizacoes = request.form.getlist('localizacao[]')
            grades_remover = request.form.getlist('grade_remover[]')
            
            for grade_id_str in grades_remover:
                if grade_id_str and grade_id_str.isdigit():
                    grade_id = int(grade_id_str)
                    grade = Grade.query.get(grade_id)
                    if grade and grade.produto_id == produto.id:
                        db.session.delete(grade)
            
            for i in range(len(cores)):
                if cores[i] and tamanhos[i]:
                    sku_grade = f"{produto.sku}-{cores[i].upper()}-{tamanhos[i]}"
                    
                    if i < len(grade_ids) and grade_ids[i]:
                        grade = Grade.query.get(grade_ids[i])
                        if grade and grade.produto_id == produto.id:
                            if grade_ids[i] not in grades_remover:
                                grade.cor = cores[i]
                                grade.tamanho = tamanhos[i]
                                grade.estoque_atual = int(estoques[i]) if i < len(estoques) and estoques[i] else 0
                                grade.estoque_minimo = int(minimos[i]) if i < len(minimos) and minimos[i] else 5
                                grade.estoque_maximo = int(maximos[i]) if i < len(maximos) and maximos[i] else 50
                                grade.sku_grade = sku_grade
                                grade.localizacao = localizacoes[i] if i < len(localizacoes) else 'PRATELEIRA-A'
                    else:
                        grade = Grade(
                            produto_id=produto.id,
                            cor=cores[i],
                            tamanho=tamanhos[i],
                            estoque_atual=int(estoques[i]) if i < len(estoques) and estoques[i] else 0,
                            estoque_minimo=int(minimos[i]) if i < len(minimos) and minimos[i] else 5,
                            estoque_maximo=int(maximos[i]) if i < len(maximos) and maximos[i] else 50,
                            sku_grade=sku_grade,
                            localizacao=localizacoes[i] if i < len(localizacoes) else 'PRATELEIRA-A'
                        )
                        db.session.add(grade)
            
            db.session.commit()
            flash('✅ Produto atualizado com sucesso!', 'success')
            return redirect(url_for('produtos', id=produto.id))
            
        except Exception as e:
            db.session.rollback()
            import traceback
            print(f"DEBUG: Erro: {str(e)}")
            print(traceback.format_exc())
            flash(f'❌ Erro ao atualizar: {str(e)}', 'danger')
    
    modelos = ['Slim', 'Top', 'Eco', 'Flash', 'Sprint', 'Tradiçao', 'Classic', 'Brasil']
    
    def formatar_preco_brasileiro(valor_float):
        try:
            valor = float(valor_float)
            valor_str = f"{valor:,.2f}"
            valor_str = valor_str.replace(",", "X").replace(".", ",").replace("X", ".")
            return valor_str
        except (ValueError, TypeError):
            return "0,00"
    
    produto.preco_formatado = formatar_preco_brasileiro(produto.preco_venda)
    produto.custo_formatado = formatar_preco_brasileiro(produto.custo)
    
    return render_template('produtos/editar.html', 
                         produto=produto, 
                         modelos=modelos)

@app.route('/produto/excluir/<int:id>', methods=['POST'])
def excluir_produto(id):
    print(f"\n🚨 TENTANDO EXCLUIR PRODUTO ID: {id}")
    
    try:
        produto = Produto.query.get(id)
        if not produto:
            flash('❌ Produto não encontrado', 'danger')
            return redirect(url_for('produtos'))
        
        print(f"📦 Produto encontrado: {produto.descricao}")
        produto_nome = produto.descricao
        
        db.session.delete(produto)
        db.session.commit()
        
        print(f"✅ SUCESSO: Produto excluído!")
        flash(f'🗑️ Produto "{produto_nome}" excluído com sucesso!', 'success')
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ ERRO: {str(e)}")
        flash(f'❌ Erro ao excluir: {str(e)}', 'danger')
    
    return redirect(url_for('produtos'))

@app.route('/produto/toggle/<int:id>', methods=['POST'])
def toggle_produto_status(id):
    produto = Produto.query.get_or_404(id)
    
    try:
        produto.ativo = not produto.ativo
        db.session.commit()
        
        status = "ativado" if produto.ativo else "desativado"
        flash(f'✅ Produto {status} com sucesso!', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Erro ao alterar status: {str(e)}', 'danger')
    
    return redirect(url_for('produtos'))

@app.route('/api/produto/<int:produto_id>/grades')
def api_grades_produto(produto_id):
    grades = Grade.query.filter_by(produto_id=produto_id).all()
    
    resultado = []
    for grade in grades:
        resultado.append({
            'id': grade.id,
            'cor': grade.cor,
            'tamanho': grade.tamanho,
            'estoque_atual': grade.estoque_atual,
            'estoque_minimo': grade.estoque_minimo,
            'localizacao': grade.localizacao
        })
    
    return jsonify(resultado)

@app.route('/api/produto/<codigo>/grades')
@login_required
def api_produto_grades_por_codigo(codigo):
    try:
        print(f"🔍 Buscando grades para código SKU: {codigo}")
        
        produto = Produto.query.filter_by(sku=codigo.upper()).first()
        
        if not produto:
            print(f"❌ Produto não encontrado com SKU: {codigo}")
            return jsonify([])
        
        print(f"✅ Produto encontrado: {produto.descricao} (ID: {produto.id})")
        
        grades = Grade.query.filter_by(produto_id=produto.id).all()
        
        resultados = []
        for grade in grades:
            imagem = grade.imagem if grade.imagem else produto.imagem
            
            resultados.append({
                'id': grade.id,
                'sku_grade': grade.sku_grade,
                'produto': produto.descricao,
                'cor': grade.cor,
                'tamanho': grade.tamanho,
                'estoque_atual': grade.estoque_atual,
                'localizacao': grade.localizacao,
                'imagem': imagem,
                'produto_imagem': produto.imagem
            })
            print(f"   Grade {grade.sku_grade}: imagem={imagem}")
        
        print(f"📦 Encontradas {len(resultados)} grades")
        return jsonify(resultados)
        
    except Exception as e:
        print(f"❌ Erro ao buscar grades: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@app.route('/api/buscar-produtos/<termo>')
def buscar_produtos(termo):
    try:
        print(f"🔍 Buscando produtos para: '{termo}'")
        
        if not termo or len(termo) < 2:
            return jsonify([])
        
        termo_busca = f"%{termo.upper()}%"
        
        produtos_por_sku = Produto.query.filter(
            Produto.sku.ilike(termo_busca),
            Produto.ativo == True
        ).limit(10).all()
        
        produtos_por_descricao = Produto.query.filter(
            Produto.descricao.ilike(f"%{termo}%"),
            Produto.ativo == True
        ).limit(10).all()
        
        grades_por_sku = Grade.query.join(Produto).filter(
            Grade.sku_grade.ilike(termo_busca)
        ).limit(10).all()
        
        todos_produtos = {}
        
        for produto in produtos_por_sku:
            if produto.sku not in todos_produtos:
                todos_produtos[produto.sku] = {
                    'codigo': produto.sku,
                    'descricao': produto.descricao,
                    'modelo': produto.modelo,
                    'preco': produto.preco_venda
                }
        
        for produto in produtos_por_descricao:
            if produto.sku not in todos_produtos:
                todos_produtos[produto.sku] = {
                    'codigo': produto.sku,
                    'descricao': produto.descricao,
                    'modelo': produto.modelo,
                    'preco': produto.preco_venda
                }
        
        for grade in grades_por_sku:
            produto = grade.produto
            if produto.sku not in todos_produtos:
                todos_produtos[produto.sku] = {
                    'codigo': produto.sku,
                    'descricao': produto.descricao,
                    'modelo': produto.modelo,
                    'preco': produto.preco_venda,
                    'cor': grade.cor,
                    'tamanho': grade.tamanho
                }
        
        resultados = list(todos_produtos.values())
        resultados = resultados[:10]
        
        print(f"✅ Encontrados {len(resultados)} produtos")
        
        return jsonify(resultados)
        
    except Exception as e:
        print(f"❌ Erro na busca: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify([])

@app.route('/api/verificar-codigo/<codigo>')
def verificar_codigo(codigo):
    try:
        if not codigo:
            return jsonify({'existe': False})
        
        produto = Produto.query.filter_by(sku=codigo.upper()).first()
        
        if produto:
            return jsonify({
                'existe': True,
                'mensagem': f'Produto "{produto.descricao}" já está cadastrado'
            })
        else:
            return jsonify({'existe': False})
            
    except Exception as e:
        print(f"❌ Erro ao verificar código: {str(e)}")
        return jsonify({'existe': False})

@app.route('/api/produto/imagem/<int:produto_id>')
def api_produto_imagem(produto_id):
    try:
        produto = db.session.get(Produto, produto_id)
        if produto and produto.imagem:
            caminho_imagem = os.path.join('uploads/produtos', produto.imagem)
            if os.path.exists(caminho_imagem):
                return jsonify({'imagem': produto.imagem})
        return jsonify({'imagem': None})
    except Exception as e:
        print(f"❌ Erro ao buscar imagem: {str(e)}")
        return jsonify({'imagem': None}), 500

# ========== ROTAS DE ESTOQUE ==========
@app.route('/estoque')
def estoque():
    busca = request.args.get('q', '')
    
    query = Grade.query.join(Produto)
    
    if busca:
        query = query.filter(
            (Produto.descricao.contains(busca)) |
            (Produto.sku.contains(busca)) |
            (Grade.cor.contains(busca)) |
            (Grade.tamanho.contains(busca))
        )
    
    grades = query.order_by(Produto.descricao, Grade.cor, Grade.tamanho).all()
    
    estoque_baixo = 0
    for grade in grades:
        estoque = grade.estoque_atual if isinstance(grade.estoque_atual, (int, float)) else 0
        minimo = grade.estoque_minimo if isinstance(grade.estoque_minimo, (int, float)) else 0
        
        if estoque > 0 and estoque < minimo:
            estoque_baixo += 1
    
    return render_template('estoque/consulta.html', 
                         grades=grades, 
                         busca=busca,
                         estoque_baixo=estoque_baixo)

@app.route('/estoque/matriz/<int:produto_id>')
def matriz_estoque(produto_id):
    produto = Produto.query.get_or_404(produto_id)
    
    cores = sorted(set(g.cor for g in produto.grades))
    tamanhos = sorted(set(g.tamanho for g in produto.grades), key=lambda x: int(x) if x.isdigit() else x)
    
    matriz = {}
    for grade in produto.grades:
        if grade.cor not in matriz:
            matriz[grade.cor] = {}
        matriz[grade.cor][grade.tamanho] = grade.estoque_atual
    
    return render_template('estoque/matriz.html',
                         produto=produto,
                         cores=cores,
                         tamanhos=tamanhos,
                         matriz=matriz)

@app.route('/estoque/entrada', methods=['GET', 'POST'])
def entrada_estoque():
    if request.method == 'POST':
        try:
            if 'dados' not in request.form:
                flash('❌ Nenhum dado recebido!', 'danger')
                return redirect(url_for('entrada_estoque'))
            
            dados = json.loads(request.form['dados'])
            fornecedor = request.form.get('fornecedor', '').strip()
            nota_fiscal = request.form.get('nota_fiscal', '').strip()
            observacao = request.form.get('observacao', '').strip()
            
            if not dados:
                flash('❌ Nenhum produto selecionado!', 'danger')
                return redirect(url_for('entrada_estoque'))
            
            if not fornecedor:
                flash('❌ Informe o fornecedor!', 'danger')
                return redirect(url_for('entrada_estoque'))
            
            total_itens = 0
            grades_processadas = []
            
            for item in dados:
                produto_id = item.get('produto_id')
                cor = item.get('cor', '').strip()
                tamanho = str(item.get('tamanho', '')).strip()
                quantidade = int(item.get('quantidade', 0))
                
                if not all([produto_id, cor, tamanho, quantidade > 0]):
                    continue
                
                cor_normalizada = cor.title()
                
                produto = Produto.query.get(produto_id)
                if not produto:
                    continue
                
                sku_grade = f"{produto.sku}-{cor_normalizada}-{tamanho}"
                
                print(f"\n[ENTRADA] Processando: {produto.sku} {cor_normalizada} T{tamanho}")
                
                grade = None
                
                grade = Grade.query.filter_by(sku_grade=sku_grade).first()
                
                if not grade:
                    from sqlalchemy import func
                    grade = Grade.query.filter(
                        Grade.produto_id == produto_id,
                        func.lower(Grade.cor) == func.lower(cor_normalizada),
                        Grade.tamanho == tamanho
                    ).first()
                
                if not grade:
                    todas_grades_produto = Grade.query.filter_by(produto_id=produto_id).all()
                    for g in todas_grades_produto:
                        if g.cor.lower() == cor_normalizada.lower() and str(g.tamanho) == str(tamanho):
                            grade = g
                            break
                
                if grade:
                    print(f"[ENTRADA] Grade encontrada: {grade.sku_grade} (ID: {grade.id})")
                    
                    estoque_anterior = int(grade.estoque_atual) if grade.estoque_atual else 0
                    grade.estoque_atual = estoque_anterior + quantidade
                    
                    print(f"[ENTRADA] Estoque atualizado: {estoque_anterior} → {grade.estoque_atual}")
                    
                    total_itens += quantidade
                    grades_processadas.append(f"{produto.sku} {cor_normalizada} T{tamanho}")
                    
                    mov = Movimentacao(
                        tipo='ENTRADA',
                        grade_id=grade.id,
                        quantidade=quantidade,
                        origem='FORNECEDOR',
                        documento=nota_fiscal,
                        observacao=f"Entrada: {quantidade} un. Fornecedor: {fornecedor}",
                        usuario='Sistema'
                    )
                    db.session.add(mov)
                    
                else:
                    print(f"[ENTRADA] Criando nova grade: {sku_grade}")
                    
                    grade = Grade(
                        produto_id=produto_id,
                        cor=cor_normalizada,
                        tamanho=tamanho,
                        estoque_atual=quantidade,
                        estoque_minimo=5,
                        estoque_maximo=50,
                        sku_grade=sku_grade,
                        localizacao='PRATELEIRA-A'
                    )
                    db.session.add(grade)
                    db.session.flush()
                    
                    total_itens += quantidade
                    grades_processadas.append(f"{produto.sku} {cor_normalizada} T{tamanho} (NOVA)")
                    
                    mov = Movimentacao(
                        tipo='ENTRADA',
                        grade_id=grade.id,
                        quantidade=quantidade,
                        origem='FORNECEDOR',
                        documento=nota_fiscal,
                        observacao=f"Nova grade criada: {quantidade} un. Fornecedor: {fornecedor}",
                        usuario='Sistema'
                    )
                    db.session.add(mov)
            
            db.session.commit()
            
            if total_itens > 0:
                flash(f'✅ {total_itens} itens adicionados ao estoque!', 'success')
                print(f"[ENTRADA] Sucesso: {total_itens} itens processados")
            else:
                flash('⚠️ Nenhum item foi processado', 'warning')
            
            return redirect(url_for('estoque'))
            
        except json.JSONDecodeError:
            flash('❌ Erro no formato dos dados!', 'danger')
            return redirect(url_for('entrada_estoque'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Erro: {str(e)}', 'danger')
            print(f"[ENTRADA] ERRO: {str(e)}")
            import traceback
            traceback.print_exc()
            return redirect(url_for('entrada_estoque'))
    
    produtos = Produto.query.filter_by(ativo=True)\
        .order_by(Produto.descricao)\
        .all()
    
    hoje = datetime.now().strftime('%Y-%m-%d')
    return render_template('estoque/entrada.html', produtos=produtos, hoje=hoje)

# ========== ROTAS PDV ==========
@app.route('/pdv')
def pdv():
    venda_id = request.args.get('id')
    mensagem = request.args.get('mensagem')
    
    if mensagem == 'venda_sucesso' and venda_id:
        venda_id_formatado = f"{int(venda_id):03d}"
        flash(f'✅ Venda #{venda_id_formatado} finalizada com sucesso!', 'success')
    elif mensagem == 'cancelada':
        flash('⚠️ Venda cancelada!', 'warning')
    elif mensagem == 'item_removido':
        flash('✅ Item removido do carrinho!', 'success')
    elif mensagem == 'erro':
        flash('❌ Erro ao finalizar venda!', 'danger')
    
    return render_template('pdv/index.html')

@app.route('/api/pdv/buscar', methods=['GET'])
def pdv_buscar():
    termo = request.args.get('q', '').upper()
    
    if not termo or len(termo) < 2:
        return jsonify([])
    
    grades = Grade.query.join(Produto).filter(
        (Grade.sku_grade.contains(termo)) |
        (Produto.descricao.contains(termo)) |
        (Grade.cor.contains(termo)) |
        (Produto.sku.contains(termo))
    ).filter(Grade.estoque_atual > 0).limit(20).all()
    
    resultados = []
    for grade in grades:
        resultados.append({
            'id': grade.id,
            'sku': grade.sku_grade,
            'descricao': f"{grade.produto.descricao} {grade.cor} T{grade.tamanho}",
            'preco': grade.produto.preco_venda,
            'estoque': grade.estoque_atual,
            'produto_id': grade.produto_id,
            'cor': grade.cor,
            'tamanho': grade.tamanho,
            'localizacao': grade.localizacao
        })
    
    return jsonify(resultados)

@app.route('/api/pdv/venda', methods=['POST'])
def pdv_venda():
    try:
        data = request.json
        itens = data['itens']
        
        print("📥 DADOS RECEBIDOS DA VENDA:", {
            'cliente': data.get('cliente'),
            'cpf': data.get('cpf'),
            'cliente_nome': data.get('cliente_nome'),
            'cliente_cpf': data.get('cliente_cpf'),
            'total_itens': len(itens)
        })
        
        subtotal = sum(item['quantidade'] * item['preco'] for item in itens)
        desconto_percentual = float(data.get('desconto', 0))
        desconto_valor = subtotal * (desconto_percentual / 100)
        total = subtotal - desconto_valor
        
        venda = Venda(
            total=total,
            forma_pagamento=data['forma_pagamento'],
            cliente=data.get('cliente', ''),
            cliente_cpf=data.get('cpf', data.get('cliente_cpf', '')),
            desconto=desconto_valor,
            vendedor=data.get('vendedor', 'PDV'),
            subtotal=subtotal,
            desconto_percentual=desconto_percentual
        )
        db.session.add(venda)
        db.session.flush()
        
        for item in itens:
            grade = Grade.query.get(item['grade_id'])
            if grade:
                if grade.estoque_atual < item['quantidade']:
                    raise Exception(f'Estoque insuficiente para {grade.sku_grade}')
                
                grade.estoque_atual -= item['quantidade']
                
                item_venda = ItemVenda(
                    venda_id=venda.id,
                    grade_id=grade.id,
                    quantidade=item['quantidade'],
                    preco_unitario=item['preco']
                )
                db.session.add(item_venda)
                
                mov = Movimentacao(
                    tipo='SAIDA',
                    grade_id=grade.id,
                    quantidade=item['quantidade'],
                    origem='VENDA',
                    documento=f'V-{venda.id}',
                    observacao='Venda no PDV',
                    usuario=data.get('vendedor', 'PDV')
                )
                db.session.add(mov)
        
        db.session.commit()
        
        print(f"✅ VENDA #{venda.id} SALVA:")
        print(f"   Cliente: {venda.cliente}")
        print(f"   CPF: {venda.cliente_cpf}")
        print(f"   Total: R$ {venda.total:.2f}")
        
        return jsonify({
            'success': True,
            'venda_id': venda.id,
            'total': venda.total,
            'data': venda.data.strftime('%d/%m/%Y %H:%M'),
            'cliente': venda.cliente,
            'cliente_cpf': venda.cliente_cpf
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ ERRO AO SALVAR VENDA: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 400

@app.route('/api/pdv/vendas', methods=['GET'])
def pdv_vendas():
    try:
        numero = request.args.get('numero')
        data_str = request.args.get('data')
        
        print(f"🔍 BUSCANDO VENDAS - Número: {numero}, Data: {data_str}")
        
        query = Venda.query
        
        if numero and numero.strip():
            try:
                venda_id = int(numero)
                venda = Venda.query.get(venda_id)
                if venda:
                    vendas = [venda]
                else:
                    vendas = []
                    print(f"⚠️ Venda #{venda_id} não encontrada")
            except ValueError:
                vendas = []
                print(f"⚠️ Número de venda inválido: {numero}")
        
        elif data_str and data_str.strip():
            try:
                data_inicio = datetime.strptime(data_str, '%Y-%m-%d')
                data_fim = data_inicio + timedelta(days=1)
                vendas = Venda.query.filter(
                    Venda.data >= data_inicio,
                    Venda.data < data_fim
                ).order_by(Venda.data.desc()).limit(50).all()
                print(f"📅 Encontradas {len(vendas)} vendas na data {data_str}")
            except ValueError as e:
                vendas = []
                print(f"❌ Data inválida: {data_str} - {str(e)}")
        
        else:
            vendas = Venda.query.order_by(Venda.data.desc()).limit(20).all()
            print(f"📊 Últimas {len(vendas)} vendas")
        
        resultados = []
        for venda in vendas:
            try:
                venda_data = {
                    'id': venda.id,
                    'venda_id': venda.id,
                    'id_formatado': f"{venda.id:03d}",
                    'data_criacao': venda.data.isoformat() if venda.data else '',
                    'cliente_nome': str(venda.cliente) if venda.cliente else '---',
                    'cliente_cpf': str(venda.cliente_cpf) if hasattr(venda, 'cliente_cpf') and venda.cliente_cpf else '',
                    'vendedor': str(venda.vendedor) if venda.vendedor else 'Sistema',
                    'total': float(venda.total) if venda.total else 0.0,
                    'forma_pagamento': str(venda.forma_pagamento) if venda.forma_pagamento else ''
                }
                
                if hasattr(venda, 'subtotal') and venda.subtotal:
                    venda_data['subtotal'] = float(venda.subtotal)
                else:
                    venda_data['subtotal'] = float(venda.total + venda.desconto) if venda.desconto else float(venda.total)
                
                if hasattr(venda, 'desconto'):
                    venda_data['desconto_valor'] = float(venda.desconto)
                else:
                    venda_data['desconto_valor'] = 0.0
                
                resultados.append(venda_data)
                
            except Exception as e:
                print(f"⚠️ Erro ao processar venda #{venda.id}: {str(e)}")
                resultados.append({
                    'id': venda.id,
                    'venda_id': venda.id,
                    'data_criacao': '',
                    'cliente_nome': '---',
                    'cliente_cpf': '',
                    'vendedor': 'Sistema',
                    'total': 0.0,
                    'forma_pagamento': ''
                })
        
        print(f"✅ Retornando {len(resultados)} vendas")
        return jsonify(resultados)
        
    except Exception as e:
        print(f"❌ ERRO CRÍTICO em /api/pdv/vendas: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e), 'details': 'Erro interno no servidor'}), 500

@app.route('/api/pdv/venda/<int:venda_id>/comprovante', methods=['GET'])
def pdv_comprovante(venda_id):
    try:
        venda = Venda.query.get_or_404(venda_id)
        
        print(f"📄 GERANDO COMPROVANTE VENDA #{venda_id}:")
        venda_id_formatado = f"{venda.id:03d}"
        print(f"   Cliente: {venda.cliente}")
        print(f"   CPF: {venda.cliente_cpf}")
        
        empresa = Empresa.query.first()
        config_comprovante = ConfigComprovante.query.first()
        
        if not empresa:
            empresa = Empresa(
                razao_social='Havaianas Store',
                nome_fantasia='Havaianas',
                logo=None,
                logo_login=None
            )
        
        if not config_comprovante:
            config_comprovante = ConfigComprovante()
        
        config_impressao = {
            'tipo': empresa.impressao_tipo or 'dialogo',
            'papel': empresa.impressao_papel or '80mm',
            'vias': empresa.impressao_vias or 1,
            'copiar': empresa.impressao_copiar or False,
            'mensagem': empresa.impressao_mensagem or config_comprovante.rodape or 'Obrigado pela preferência!'
        }
        
        print(f"📋 CONFIGURAÇÃO DE IMPRESSÃO: {config_impressao}")
        
        itens_detalhes = []
        for item in venda.itens:
            grade = Grade.query.get(item.grade_id)
            if grade:
                produto = Produto.query.get(grade.produto_id)
                descricao = f"{produto.descricao} {grade.cor}" if produto else f"Produto #{grade.id}"
                sku = grade.sku_grade if grade else f"GRADE-{item.grade_id}"
                cor = grade.cor if grade else ''
                tamanho = grade.tamanho if grade else ''
            else:
                descricao = f"Produto #{item.grade_id}"
                sku = f"GRADE-{item.grade_id}"
                cor = ''
                tamanho = ''
            
            itens_detalhes.append({
                'descricao': descricao,
                'sku': sku,
                'cor': cor,
                'tamanho': tamanho,
                'quantidade': item.quantidade,
                'preco': float(item.preco_unitario),
                'subtotal': float(item.quantidade * item.preco_unitario)
            })
        
        if hasattr(venda, 'subtotal') and venda.subtotal:
            subtotal = float(venda.subtotal)
        else:
            subtotal = sum(item['quantidade'] * item['preco'] for item in itens_detalhes)
        
        if hasattr(venda, 'desconto_percentual') and venda.desconto_percentual:
            desconto_percentual = float(venda.desconto_percentual)
        else:
            desconto_percentual = (float(venda.desconto) / subtotal * 100) if subtotal > 0 else 0.0
        
        endereco_completo = ''
        if empresa and config_comprovante.mostrar_endereco:
            endereco_parts = []
            if empresa.endereco:
                endereco_parts.append(empresa.endereco)
            if empresa.numero:
                endereco_parts.append(f"nº {empresa.numero}")
            if empresa.bairro:
                endereco_parts.append(empresa.bairro)
            if empresa.cidade and empresa.uf:
                endereco_parts.append(f"{empresa.cidade}/{empresa.uf}")
            if empresa.cep:
                endereco_parts.append(f"CEP: {empresa.cep}")
            endereco_completo = ' - '.join(endereco_parts)
        
        contato = []
        if empresa and config_comprovante.mostrar_telefone:
            if empresa.telefone:
                contato.append(f"Tel: {empresa.telefone}")
            if empresa.celular:
                contato.append(f"Cel: {empresa.celular}")
        contato_texto = ' | '.join(contato)
        
        cnpj_formatado = ''
        if empresa and empresa.cnpj and config_comprovante.mostrar_cnpj:
            cnpj = empresa.cnpj.replace('.', '').replace('-', '').replace('/', '')
            if len(cnpj) == 14:
                cnpj_formatado = f"CNPJ: {cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
        
        comprovante = {
            'success': True,
            'comprovante': {
                'id': venda.id,
                'venda_id': venda.id,
                'venda_id_formatado': venda_id_formatado,
                'data_criacao': venda.data.isoformat(),
                'cliente_nome': venda.cliente or 'CONSUMIDOR',
                'cliente_cpf': venda.cliente_cpf or '',
                'vendedor': venda.vendedor,
                'itens': itens_detalhes,
                'subtotal': subtotal,
                'desconto_percentual': desconto_percentual,
                'desconto_valor': float(venda.desconto),
                'total': float(venda.total),
                'forma_pagamento': venda.forma_pagamento,
                
                'empresa': {
                    'razao_social': empresa.razao_social or 'Havaianas Store',
                    'nome_fantasia': empresa.nome_fantasia or 'Havaianas',
                    'logo': empresa.logo,
                    'logo_login': empresa.logo_login,
                    'cnpj_formatado': cnpj_formatado,
                    'endereco': endereco_completo,
                    'contato': contato_texto,
                    'cabecalho': config_comprovante.cabecalho if config_comprovante else '',
                    'rodape': config_comprovante.rodape if config_comprovante else 'Obrigado pela preferência!',
                    'mostrar_logo': config_comprovante.mostrar_logo if config_comprovante else True
                },
                
                'config_impressao': config_impressao
            }
        }
        
        return jsonify(comprovante)
        
    except Exception as e:
        print(f"❌ ERRO AO GERAR COMPROVANTE: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 404

@app.route('/api/pdv/venda/<int:venda_id>/reimprimir', methods=['POST'])
def reimprimir_venda(venda_id):
    try:
        venda = Venda.query.get(venda_id)
        if not venda:
            return jsonify({'success': False, 'error': 'Venda não encontrada'}), 404
        
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'acao': 'reimpressao',
            'venda_id': venda_id,
            'vendedor': venda.vendedor,
            'total': float(venda.total),
            'ip': request.remote_addr
        }
        
        with open('reimpressoes.log', 'a') as f:
            f.write(json.dumps(log_entry) + '\n')
        
        print(f"=== VENDA #{venda_id} REIMPRESSA ===")
        print(f"Data: {datetime.now()}")
        print(f"Vendedor: {venda.vendedor}")
        print(f"Total: R$ {venda.total:.2f}")
        print("=" * 40)
        
        return jsonify({
            'success': True,
            'message': f'Venda #{venda_id} enviada para impressão',
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/pdv/venda/<int:venda_id>', methods=['DELETE'])
def excluir_venda_pdv(venda_id):
    try:
        print(f"🗑️  ====== EXCLUSÃO DE VENDA #{venda_id} INICIADA =====")
        print(f"📤 Método: DELETE")
        print(f"🕐 Data/Hora: {datetime.now()}")
        
        venda = Venda.query.get(venda_id)
        if not venda:
            print(f"❌ VENDA #{venda_id} NÃO ENCONTRADA NO BANCO")
            return jsonify({
                'success': False,
                'message': f'Venda #{venda_id} não encontrada'
            }), 404
        
        print(f"📋 DADOS DA VENDA #{venda_id}:")
        print(f"   Cliente: {venda.cliente}")
        print(f"   Total: R$ {venda.total:.2f}")
        print(f"   Itens: {len(venda.itens)}")
        print(f"   Vendedor: {venda.vendedor}")
        
        for item in venda.itens:
            grade = Grade.query.get(item.grade_id)
            if grade:
                print(f"   ↪️ {grade.sku_grade}: +{item.quantidade} unidades")
                grade.estoque_atual += item.quantidade
            else:
                print(f"   ⚠️ Grade {item.grade_id} não encontrada")
        
        movimentacoes = Movimentacao.query.filter_by(documento=f'V-{venda_id}').all()
        print(f"🗑️ REMOVENDO {len(movimentacoes)} MOVIMENTAÇÕES")
        for mov in movimentacoes:
            db.session.delete(mov)
        
        itens_count = ItemVenda.query.filter_by(venda_id=venda_id).count()
        print(f"🗑️ REMOVENDO {itens_count} ITENS DA VENDA")
        ItemVenda.query.filter_by(venda_id=venda_id).delete()
        
        db.session.delete(venda)
        db.session.commit()
        
        print(f"✅ VENDA #{venda_id} EXCLUÍDA COM SUCESSO")
        print("=========================================")
        
        return jsonify({
            'success': True,
            'message': f'Venda #{venda_id} excluída com sucesso',
            'venda_id': venda_id,
            'cliente': venda.cliente,
            'total': float(venda.total)
        }), 200
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ ERRO CRÍTICO AO EXCLUIR VENDA #{venda_id}:")
        print(f"   Tipo: {type(e).__name__}")
        print(f"   Mensagem: {str(e)}")
        import traceback
        traceback.print_exc()
        print("=========================================")
        return jsonify({
            'success': False,
            'message': f'Erro ao excluir venda: {str(e)}'
        }), 500

# ========== ROTAS DE RELATÓRIOS ==========
@app.route('/relatorios/estoque-baixo')
def relatorio_estoque_baixo():
    grades = Grade.query.join(Produto).filter(
        Grade.estoque_atual < Grade.estoque_minimo,
        Produto.ativo == True
    ).order_by(
        (Grade.estoque_minimo - Grade.estoque_atual).desc()
    ).all()
    
    total_itens_baixo = sum(g.estoque_atual for g in grades)
    total_faltante = sum(g.estoque_minimo - g.estoque_atual for g in grades)
    produtos_afetados = len(set(g.produto_id for g in grades))
    
    modelos_unicos = db.session.query(Produto.modelo)\
        .distinct()\
        .filter(Produto.modelo.isnot(None))\
        .filter(Produto.modelo != '')\
        .order_by(Produto.modelo)\
        .all()
    
    modelos = [m[0] for m in modelos_unicos if m[0]]
    
    return render_template('relatorios/estoque_baixo.html',
                         grades=grades,
                         total_itens_baixo=total_itens_baixo,
                         total_faltante=total_faltante,
                         produtos_afetados=produtos_afetados,
                         modelos=modelos)

@app.route('/relatorios/vendas')
def relatorio_vendas():
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    forma_pagamento = request.args.get('forma_pagamento')
    
    mensagem = request.args.get('mensagem')
    venda_id = request.args.get('id')
    
    if mensagem == 'excluida' and venda_id:
        venda_id_formatado = f"{int(venda_id):03d}"
        flash(f'🗑️ Venda #{venda_id_formatado} excluída com sucesso!', 'success')

    query = Venda.query
    
    if data_inicio:
        query = query.filter(Venda.data >= datetime.strptime(data_inicio, '%Y-%m-%d'))
    if data_fim:
        query = query.filter(Venda.data <= datetime.strptime(data_fim + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))
    if forma_pagamento and forma_pagamento != 'TODAS':
        query = query.filter(Venda.forma_pagamento == forma_pagamento)
    
    vendas = query.order_by(Venda.data.desc()).limit(100).all()
    
    total_vendas = sum(v.total for v in vendas)
    total_itens = sum(sum(i.quantidade for i in v.itens) for v in vendas)
    
    formas_pagamento = db.session.query(
        Venda.forma_pagamento,
        func.count(Venda.id).label('quantidade'),
        func.sum(Venda.total).label('total')
    ).group_by(Venda.forma_pagamento).all()
    
    sete_dias_atras = datetime.utcnow() - timedelta(days=7)
    vendas_por_dia = db.session.query(
        func.date(Venda.data).label('data'),
        func.count(Venda.id).label('quantidade'),
        func.sum(Venda.total).label('total')
    ).filter(Venda.data >= sete_dias_atras)\
     .group_by(func.date(Venda.data))\
     .order_by(func.date(Venda.data).desc()).all()
    
    return render_template('relatorios/vendas.html',
                         vendas=vendas,
                         total_vendas=total_vendas,
                         total_itens=total_itens,
                         formas_pagamento=formas_pagamento,
                         vendas_por_dia=vendas_por_dia,
                         data_inicio=data_inicio,
                         data_fim=data_fim,
                         forma_pagamento=forma_pagamento)

@app.route('/relatorios/produtos-parados')
def relatorio_produtos_parados():
    trinta_dias_atras = datetime.utcnow() - timedelta(days=30)
    
    produtos_com_estoque = Produto.query.join(Grade).filter(
        Grade.estoque_atual > 0,
        Produto.ativo == True
    ).all()
    
    produtos_parados = []
    valor_total_parado = 0
    
    for produto in produtos_com_estoque:
        venda_recente = False
        for grade in produto.grades:
            if grade.estoque_atual > 0:
                mov_saida = Movimentacao.query.filter(
                    Movimentacao.grade_id == grade.id,
                    Movimentacao.tipo == 'SAIDA',
                    Movimentacao.data >= trinta_dias_atras
                ).first()
                if mov_saida:
                    venda_recente = True
                    break
        
        if not venda_recente:
            total_estoque = sum(g.estoque_atual for g in produto.grades)
            custo_total = total_estoque * (produto.custo or 15.00)
            valor_total_parado += custo_total
            
            ultima_mov = Movimentacao.query.join(Grade).filter(
                Grade.produto_id == produto.id,
                Movimentacao.tipo == 'SAIDA'
            ).order_by(Movimentacao.data.desc()).first()
            
            dias_sem_venda = 30
            if ultima_mov:
                dias_sem_venda = (datetime.utcnow() - ultima_mov.data).days
            
            produtos_parados.append({
                'produto': produto,
                'total_estoque': total_estoque,
                'custo_total': custo_total,
                'dias_sem_venda': dias_sem_venda,
                'valor_estoque': total_estoque * (produto.custo or 15.00)
            })
    
    produtos_parados.sort(key=lambda x: x['dias_sem_venda'], reverse=True)
    
    total_produtos_parados = len(produtos_parados)
    total_estoque_parado = sum(p['total_estoque'] for p in produtos_parados)
    
    return render_template('relatorios/produtos_parados.html',
                         produtos_parados=produtos_parados,
                         total_produtos_parados=total_produtos_parados,
                         total_estoque_parado=total_estoque_parado,
                         valor_total_parado=valor_total_parado,
                         trinta_dias_atras=trinta_dias_atras)

@app.route('/movimentacoes')
def relatorio_movimentacoes():
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    tipo = request.args.get('tipo')
    
    query = Movimentacao.query.join(Grade).join(Produto).order_by(Movimentacao.data.desc())
    
    if data_inicio:
        query = query.filter(Movimentacao.data >= datetime.strptime(data_inicio, '%Y-%m-%d'))
    if data_fim:
        query = query.filter(Movimentacao.data <= datetime.strptime(data_fim + ' 23:59:59', '%Y-%m-%d %H:%M:%S'))
    if tipo and tipo != 'TODOS':
        query = query.filter(Movimentacao.tipo == tipo)
    
    movimentacoes = query.limit(200).all()
    
    total_entradas = sum(m.quantidade for m in movimentacoes if m.tipo == 'ENTRADA')
    total_saidas = sum(m.quantidade for m in movimentacoes if m.tipo == 'SAIDA')
    saldo = total_entradas - total_saidas
    
    return render_template('relatorios/movimentacoes.html',
                         movimentacoes=movimentacoes,
                         total_entradas=total_entradas,
                         total_saidas=total_saidas,
                         saldo=saldo,
                         data_inicio=data_inicio,
                         data_fim=data_fim,
                         tipo=tipo)

# ========== ROTAS PARA CLIENTES ==========
@app.route('/clientes')
def listar_clientes():
    busca = request.args.get('q', '')
    tipo_pessoa = request.args.get('tipo_pessoa', 'TODOS')
    status = request.args.get('status', 'ATIVOS')
    ordenar = request.args.get('ordenar', 'id')
    
    query = Cliente.query
    
    if busca:
        query = query.filter(
            (Cliente.nome.contains(busca)) |
            (Cliente.cpf_cnpj.contains(busca)) |
            (Cliente.email.contains(busca)) |
            (Cliente.celular.contains(busca)) |
            (Cliente.telefone.contains(busca)) |
            (Cliente.logradouro.contains(busca)) |
            (Cliente.bairro.contains(busca)) |
            (Cliente.cidade.contains(busca)) |
            (Cliente.estado.contains(busca)) |
            (Cliente.cep.contains(busca))
        )
    
    if tipo_pessoa in ['FISICA', 'JURIDICA']:
        query = query.filter_by(tipo=tipo_pessoa)
    
    if status == 'ATIVOS':
        query = query.filter_by(ativo=True)
    elif status == 'INATIVOS':
        query = query.filter_by(ativo=False)
    elif status == 'WHATSAPP':
        query = query.filter_by(whatsapp=True, ativo=True)
    
    if ordenar == 'id':
        query = query.order_by(Cliente.id.asc())
    elif ordenar == 'id_desc':
        query = query.order_by(Cliente.id.desc())
    elif ordenar == 'nome':
        query = query.order_by(Cliente.nome.asc())
    elif ordenar == 'nome_desc':
        query = query.order_by(Cliente.nome.desc())
    elif ordenar == 'documento':
        query = query.order_by(Cliente.cpf_cnpj.asc())
    elif ordenar == 'documento_desc':
        query = query.order_by(Cliente.cpf_cnpj.desc())
    elif ordenar == 'contato':
        query = query.order_by(Cliente.email.asc(), Cliente.celular.asc())
    elif ordenar == 'contato_desc':
        query = query.order_by(Cliente.email.desc(), Cliente.celular.desc())
    elif ordenar == 'localizacao':
        query = query.order_by(Cliente.cidade.asc(), Cliente.estado.asc(), Cliente.bairro.asc())
    elif ordenar == 'localizacao_desc':
        query = query.order_by(Cliente.cidade.desc(), Cliente.estado.desc(), Cliente.bairro.desc())
    elif ordenar == 'status':
        query = query.order_by(Cliente.ativo.desc())
    elif ordenar == 'status_desc':
        query = query.order_by(Cliente.ativo.asc())
    else:
        query = query.order_by(Cliente.id.asc())
    
    clientes = query.all()
    
    total_clientes = Cliente.query.count()
    clientes_ativos = Cliente.query.filter_by(ativo=True).count()
    clientes_inativos = Cliente.query.filter_by(ativo=False).count()
    clientes_whatsapp = Cliente.query.filter_by(whatsapp=True, ativo=True).count()
    
    inicio_mes = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    novos_mes = Cliente.query.filter(Cliente.data_cadastro >= inicio_mes).count()
    
    top_clientes = Cliente.query.filter_by(ativo=True)\
        .order_by(Cliente.total_gasto.desc())\
        .limit(5).all()
    
    total_vendas = db.session.query(db.func.sum(Cliente.total_vendas)).scalar() or 0
    total_gasto = db.session.query(db.func.sum(Cliente.total_gasto)).scalar() or 0
    ticket_medio = total_gasto / total_vendas if total_vendas > 0 else 0
    
    percentual_whatsapp = (clientes_whatsapp / clientes_ativos * 100) if clientes_ativos > 0 else 0
    percentual_clientes = (clientes_ativos / total_clientes * 100) if total_clientes > 0 else 0
    
    return render_template('cadastros/clientes/lista.html',
                         clientes=clientes,
                         busca=busca,
                         tipo_pessoa=tipo_pessoa,
                         status=status,
                         ordenar=ordenar,
                         total_clientes=total_clientes,
                         clientes_ativos=clientes_ativos,
                         clientes_inativos=clientes_inativos,
                         clientes_whatsapp=clientes_whatsapp,
                         novos_mes=novos_mes,
                         top_clientes=top_clientes,
                         ticket_medio=format_number(ticket_medio),
                         percentual_whatsapp=round(percentual_whatsapp, 1),
                         percentual_clientes=round(percentual_clientes, 1),
                         mes_atual=datetime.utcnow().strftime('%m/%Y'),
                         variacao_ticket=5.2)

@app.route('/cliente/novo', methods=['GET', 'POST'])
def novo_cliente():
    if request.method == 'POST':
        try:
            dados = {
                'nome': request.form['nome'].strip(),
                'tipo': request.form['tipo'],
                'cpf_cnpj': request.form['cpf_cnpj'].replace('.', '').replace('-', '').replace('/', ''),
                'rg': request.form.get('rg', '').strip(),
                'email': request.form.get('email', '').strip().lower(),
                'telefone': request.form.get('telefone', '').replace('(', '').replace(')', '').replace(' ', '').replace('-', ''),
                'celular': request.form.get('celular', '').replace('(', '').replace(')', '').replace(' ', '').replace('-', ''),
                'whatsapp': 'whatsapp' in request.form,
                'logradouro': request.form.get('logradouro', '').strip(),
                'numero': request.form.get('numero', '').strip(),
                'bairro': request.form.get('bairro', '').strip(),
                'complemento': request.form.get('complemento', '').strip(),
                'cidade': request.form.get('cidade', '').strip(),
                'estado': request.form.get('estado', '').strip(),
                'cep': request.form.get('cep', '').replace('-', ''),
                'observacoes': request.form.get('observacoes', '').strip(),
            }
            
            if dados['cpf_cnpj']:
                cliente_existente = Cliente.query.filter_by(cpf_cnpj=dados['cpf_cnpj']).first()
                if cliente_existente:
                    flash(f'❌ Já existe um cliente cadastrado com este documento!', 'danger')
                    return redirect(url_for('novo_cliente'))
            
            if not dados['celular']:
                flash('❌ O celular é obrigatório!', 'danger')
                return redirect(url_for('novo_cliente'))
            
            cliente = Cliente(**dados)
            db.session.add(cliente)
            db.session.commit()
            
            flash(f'✅ Cliente "{cliente.nome}" cadastrado com sucesso!', 'success')
            return redirect(url_for('listar_clientes'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Erro ao cadastrar cliente: {str(e)}', 'danger')
    
    return render_template('cadastros/clientes/novo.html')

@app.route('/cliente/editar/<int:id>', methods=['GET', 'POST'])
def editar_cliente(id):
    cliente = Cliente.query.get_or_404(id)
    
    if request.method == 'POST':
        try:
            cliente.nome = request.form['nome'].strip()
            cliente.tipo = request.form['tipo']
            
            novo_cpf_cnpj = request.form['cpf_cnpj'].replace('.', '').replace('-', '').replace('/', '')
            if novo_cpf_cnpj != cliente.cpf_cnpj:
                cliente_existente = Cliente.query.filter_by(cpf_cnpj=novo_cpf_cnpj).first()
                if cliente_existente and cliente_existente.id != cliente.id:
                    flash(f'❌ Já existe outro cliente com este documento!', 'danger')
                    return redirect(url_for('editar_cliente', id=id))
                cliente.cpf_cnpj = novo_cpf_cnpj
            
            cliente.rg = request.form.get('rg', '').strip()
            cliente.email = request.form.get('email', '').strip().lower()
            cliente.telefone = request.form.get('telefone', '').replace('(', '').replace(')', '').replace(' ', '').replace('-', '')
            cliente.celular = request.form.get('celular', '').replace('(', '').replace(')', '').replace(' ', '').replace('-', '')
            cliente.whatsapp = 'whatsapp' in request.form
            cliente.logradouro = request.form.get('logradouro', '').strip()
            cliente.numero = request.form.get('numero', '').strip()
            cliente.bairro = request.form.get('bairro', '').strip()
            cliente.complemento = request.form.get('complemento', '').strip()
            cliente.cidade = request.form.get('cidade', '').strip()
            cliente.estado = request.form.get('estado', '').strip()
            cliente.cep = request.form.get('cep', '').replace('-', '')
            cliente.observacoes = request.form.get('observacoes', '').strip()
            
            db.session.commit()
            flash(f'✅ Cliente "{cliente.nome}" atualizado com sucesso!', 'success')
            return redirect(url_for('listar_clientes'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Erro ao atualizar cliente: {str(e)}', 'danger')
    
    return render_template('cadastros/clientes/editar.html', cliente=cliente)

@app.route('/cliente/toggle/<int:id>', methods=['POST'])
def toggle_cliente(id):
    cliente = Cliente.query.get_or_404(id)
    try:
        cliente.ativo = not cliente.ativo
        db.session.commit()
        status = "ativado" if cliente.ativo else "desativado"
        flash(f'✅ Cliente "{cliente.nome}" {status} com sucesso!', 'success')
        return redirect(url_for('listar_clientes'))
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Erro: {str(e)}', 'danger')
        return redirect(url_for('listar_clientes'))

@app.route('/cliente/excluir/<int:id>', methods=['POST'])
def excluir_cliente(id):
    cliente = Cliente.query.get_or_404(id)
    try:
        nome = cliente.nome
        if cliente.total_vendas > 0:
            flash(f'❌ Cliente "{nome}" possui vendas e não pode ser excluído', 'danger')
            return redirect(url_for('listar_clientes'))
        db.session.delete(cliente)
        db.session.commit()
        flash(f'✅ Cliente "{nome}" excluído com sucesso!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Erro: {str(e)}', 'danger')
    return redirect(url_for('listar_clientes'))

@app.route('/api/clientes/<int:id>')
def api_cliente_detalhes(id):
    cliente = Cliente.query.get_or_404(id)

    return jsonify({
        "id": cliente.id,
        "nome": cliente.nome,
        "tipo": cliente.tipo,
        "cpf_cnpj": cliente.cpf_cnpj,
        "rg": cliente.rg,
        "email": cliente.email,
        "telefone": cliente.telefone,
        "celular": cliente.celular,
        "whatsapp": cliente.whatsapp,
        "logradouro": cliente.logradouro,
        "numero": cliente.numero,
        "complemento": cliente.complemento,
        "bairro": cliente.bairro,
        "cidade": cliente.cidade,
        "estado": cliente.estado,
        "cep": cliente.cep,
        "observacoes": cliente.observacoes,
        "ativo": cliente.ativo
    })

@app.route('/api/clientes/buscar', methods=['GET'])
def api_buscar_clientes():
    try:
        termo = request.args.get('q', '').strip()
        
        query = Cliente.query.filter_by(ativo=True)
        
        if termo:
            termo_busca = f'%{termo}%'
            query = query.filter(
                db.or_(
                    Cliente.nome.ilike(termo_busca),
                    Cliente.cpf_cnpj.ilike(termo_busca)
                )
            )
        
        clientes = query.order_by(Cliente.nome).limit(100).all()
        
        resultados = []
        for c in clientes:
            resultados.append({
                'id': c.id,
                'nome': c.nome,
                'cpf_cnpj': c.cpf_cnpj or '',
                'celular': c.celular or '',
                'email': c.email or '',
                'endereco': f"{c.logradouro or ''}, {c.numero or ''} {c.bairro or ''}".strip()
            })
        
        print(f"✅ Clientes encontrados: {len(resultados)}")
        return jsonify(resultados)
        
    except Exception as e:
        print(f"❌ Erro ao buscar clientes: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

# ========== ROTAS PARA FORNECEDORES ==========
@app.route('/fornecedores')
def lista_fornecedores():
    busca = request.args.get('q', '')
    status = request.args.get('status', 'ativos')
    ordenar = request.args.get('ordenar', 'razao_social')
    
    if status == 'todos':
        query = Fornecedor.query
    elif status == 'inativos':
        query = Fornecedor.query.filter_by(ativo=False)
    else:
        query = Fornecedor.query.filter_by(ativo=True)
    
    if busca:
        query = query.filter(
            (Fornecedor.razao_social.contains(busca)) |
            (Fornecedor.nome_fantasia.contains(busca)) |
            (Fornecedor.cnpj.contains(busca)) |
            (Fornecedor.cidade.contains(busca)) |
            (Fornecedor.responsavel.contains(busca)) |
            (Fornecedor.email.contains(busca)) |
            (Fornecedor.telefone.contains(busca)) |
            (Fornecedor.celular.contains(busca))
        )
    
    if ordenar == 'id':
        query = query.order_by(Fornecedor.id.asc())
    elif ordenar == 'id_desc':
        query = query.order_by(Fornecedor.id.desc())
    elif ordenar == 'razao_social':
        query = query.order_by(Fornecedor.razao_social.asc())
    elif ordenar == 'razao_social_desc':
        query = query.order_by(Fornecedor.razao_social.desc())
    elif ordenar == 'cnpj':
        query = query.order_by(Fornecedor.cnpj.asc())
    elif ordenar == 'cnpj_desc':
        query = query.order_by(Fornecedor.cnpj.desc())
    elif ordenar == 'contato':
        query = query.order_by(Fornecedor.email.asc(), Fornecedor.telefone.asc())
    elif ordenar == 'contato_desc':
        query = query.order_by(Fornecedor.email.desc(), Fornecedor.telefone.desc())
    elif ordenar == 'localizacao':
        query = query.order_by(Fornecedor.cidade.asc(), Fornecedor.estado.asc())
    elif ordenar == 'localizacao_desc':
        query = query.order_by(Fornecedor.cidade.desc(), Fornecedor.estado.desc())
    elif ordenar == 'status':
        query = query.order_by(Fornecedor.ativo.desc())
    elif ordenar == 'status_desc':
        query = query.order_by(Fornecedor.ativo.asc())
    else:
        query = query.order_by(Fornecedor.razao_social.asc())
    
    fornecedores = query.all()
    
    total_fornecedores = Fornecedor.query.count()
    ativos = Fornecedor.query.filter_by(ativo=True).count()
    inativos = Fornecedor.query.filter_by(ativo=False).count()
    
    return render_template('cadastros/fornecedores/lista.html',
                         fornecedores=fornecedores,
                         total_fornecedores=total_fornecedores,
                         ativos=ativos,
                         inativos=inativos,
                         busca=busca,
                         status=status,
                         ordenar=ordenar)

@app.route('/fornecedor/novo', methods=['GET', 'POST'])
@login_required
def novo_fornecedor():
    form_data = {}
    
    if request.method == 'POST':
        try:
            form_data = {
                'razao_social': request.form.get('razao_social', '').strip(),
                'nome_fantasia': request.form.get('nome_fantasia', '').strip(),
                'cnpj': request.form.get('cnpj', '').replace('.', '').replace('-', '').replace('/', ''),
                'inscricao_estadual': request.form.get('inscricao_estadual', '').strip(),
                'responsavel': request.form.get('responsavel', '').strip(),
                'email': request.form.get('email', '').strip().lower(),
                'telefone': request.form.get('telefone', '').strip(),
                'celular': request.form.get('celular', '').strip(),
                'logradouro': request.form.get('logradouro', '').strip(),
                'numero': request.form.get('numero', '').strip(),
                'bairro': request.form.get('bairro', '').strip(),
                'complemento': request.form.get('complemento', '').strip(),
                'cidade': request.form.get('cidade', '').strip(),
                'estado': request.form.get('estado', '').strip().upper(),
                'cep': request.form.get('cep', '').replace('-', ''),
                'observacoes': request.form.get('observacoes', '').strip()
            }
            
            if not request.form.get('razao_social'):
                flash('❌ Razão Social é obrigatória!', 'danger')
                return render_template('cadastros/fornecedores/novo.html', form_data=form_data)
            
            if form_data['cnpj']:
                existente = Fornecedor.query.filter_by(cnpj=form_data['cnpj']).first()
                if existente:
                    flash(f'❌ CNPJ já cadastrado para {existente.razao_social}', 'danger')
                    return render_template('cadastros/fornecedores/novo.html', form_data=form_data)
            
            fornecedor = Fornecedor(
                razao_social=form_data['razao_social'],
                nome_fantasia=form_data['nome_fantasia'],
                cnpj=form_data['cnpj'],
                inscricao_estadual=form_data['inscricao_estadual'],
                email=form_data['email'],
                telefone=form_data['telefone'],
                celular=form_data['celular'],
                responsavel=form_data['responsavel'],
                logradouro=form_data['logradouro'],
                numero=form_data['numero'],
                bairro=form_data['bairro'],
                complemento=form_data['complemento'],
                cidade=form_data['cidade'],
                estado=form_data['estado'],
                cep=form_data['cep'],
                observacoes=form_data['observacoes'],
                ativo=True,
                data_cadastro=datetime.utcnow()
            )
            
            db.session.add(fornecedor)
            db.session.commit()
            
            flash(f'✅ Fornecedor "{form_data["razao_social"]}" cadastrado com sucesso!', 'success')
            return redirect(url_for('lista_fornecedores'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Erro ao cadastrar: {str(e)}', 'danger')
            return render_template('cadastros/fornecedores/novo.html', form_data=form_data)
    
    return render_template('cadastros/fornecedores/novo.html', form_data={})

@app.route('/fornecedor/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_fornecedor(id):
    fornecedor = Fornecedor.query.get_or_404(id)
    form_data = {}
    
    if request.method == 'POST':
        try:
            form_data = {
                'razao_social': request.form.get('razao_social', '').strip(),
                'nome_fantasia': request.form.get('nome_fantasia', '').strip(),
                'cnpj': request.form.get('cnpj', '').replace('.', '').replace('-', '').replace('/', ''),
                'inscricao_estadual': request.form.get('inscricao_estadual', '').strip(),
                'responsavel': request.form.get('responsavel', '').strip(),
                'email': request.form.get('email', '').strip().lower(),
                'telefone': request.form.get('telefone', '').strip(),
                'celular': request.form.get('celular', '').strip(),
                'logradouro': request.form.get('logradouro', '').strip(),
                'numero': request.form.get('numero', '').strip(),
                'bairro': request.form.get('bairro', '').strip(),
                'complemento': request.form.get('complemento', '').strip(),
                'cidade': request.form.get('cidade', '').strip(),
                'estado': request.form.get('estado', '').strip().upper(),
                'cep': request.form.get('cep', '').replace('-', ''),
                'observacoes': request.form.get('observacoes', '').strip(),
                'ativo': 'ativo' in request.form
            }
            
            if form_data['cnpj'] and form_data['cnpj'] != fornecedor.cnpj:
                existente = Fornecedor.query.filter_by(cnpj=form_data['cnpj']).first()
                if existente:
                    flash(f'❌ CNPJ já cadastrado para {existente.razao_social}', 'danger')
                    return render_template('cadastros/fornecedores/editar.html', 
                                         fornecedor=fornecedor, 
                                         form_data=form_data)
            
            fornecedor.razao_social = form_data['razao_social']
            fornecedor.nome_fantasia = form_data['nome_fantasia']
            fornecedor.cnpj = form_data['cnpj']
            fornecedor.inscricao_estadual = form_data['inscricao_estadual']
            fornecedor.email = form_data['email']
            fornecedor.telefone = form_data['telefone']
            fornecedor.celular = form_data['celular']
            fornecedor.responsavel = form_data['responsavel']
            fornecedor.logradouro = form_data['logradouro']
            fornecedor.numero = form_data['numero']
            fornecedor.bairro = form_data['bairro']
            fornecedor.complemento = form_data['complemento']
            fornecedor.cidade = form_data['cidade']
            fornecedor.estado = form_data['estado']
            fornecedor.cep = form_data['cep']
            fornecedor.observacoes = form_data['observacoes']
            fornecedor.ativo = form_data['ativo']
            
            db.session.commit()
            
            flash(f'✅ Fornecedor "{form_data["razao_social"]}" atualizado!', 'success')
            return redirect(url_for('lista_fornecedores'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Erro ao atualizar: {str(e)}', 'danger')
            return render_template('cadastros/fornecedores/editar.html', 
                                 fornecedor=fornecedor, 
                                 form_data=form_data)
    
    return render_template('cadastros/fornecedores/editar.html', 
                         fornecedor=fornecedor, 
                         form_data={})

@app.route('/fornecedor/toggle/<int:id>', methods=['POST'])
def toggle_fornecedor(id):
    fornecedor = Fornecedor.query.get_or_404(id)
    fornecedor.ativo = not fornecedor.ativo
    db.session.commit()
    
    status = "ativado" if fornecedor.ativo else "desativado"
    flash(f'✅ Fornecedor "{fornecedor.razao_social}" {status}!', 'success')
    return redirect(url_for('lista_fornecedores'))

@app.route('/fornecedor/excluir/<int:id>', methods=['POST'])
def excluir_fornecedor(id):
    fornecedor = Fornecedor.query.get_or_404(id)
    nome = fornecedor.razao_social
    db.session.delete(fornecedor)
    db.session.commit()
    
    flash(f'✅ Fornecedor "{nome}" excluído!', 'success')
    return redirect(url_for('lista_fornecedores'))

@app.route('/api/fornecedores/buscar')
def api_buscar_fornecedores():
    termo = request.args.get('q', '')
    if len(termo) < 2:
        return jsonify([])
    
    fornecedores = Fornecedor.query.filter(
        (Fornecedor.razao_social.contains(termo)) |
        (Fornecedor.cnpj.contains(termo))
    ).filter_by(ativo=True).limit(10).all()
    
    resultados = []
    for f in fornecedores:
        resultados.append({
            'id': f.id,
            'razao_social': f.razao_social,
            'cnpj': f.cnpj,
            'cidade': f.cidade,
            'display': f"{f.razao_social} - {f.cnpj or ''}"
        })
    
    return jsonify(resultados)

@app.route('/api/fornecedores/<int:id>')
def api_fornecedor_detalhes(id):
    fornecedor = Fornecedor.query.get_or_404(id)
    
    return jsonify({
        'id': fornecedor.id,
        'razao_social': fornecedor.razao_social,
        'nome_fantasia': fornecedor.nome_fantasia,
        'cnpj': fornecedor.cnpj,
        'inscricao_estadual': fornecedor.inscricao_estadual,
        'email': fornecedor.email,
        'telefone': fornecedor.telefone,
        'celular': fornecedor.celular,
        'responsavel': fornecedor.responsavel,
        'logradouro': fornecedor.logradouro,
        'numero': fornecedor.numero,
        'bairro': fornecedor.bairro,
        'complemento': fornecedor.complemento,
        'cidade': fornecedor.cidade,
        'estado': fornecedor.estado,
        'cep': fornecedor.cep,
        'observacoes': fornecedor.observacoes,
        'ativo': fornecedor.ativo
    })

# ========== ROTAS PARA INVENTÁRIO ==========
@app.route('/inventario')
@login_required
def inventario():
    status = request.args.get('status', 'todos')
    data_inicio = request.args.get('data_inicio')
    data_fim = request.args.get('data_fim')
    
    query = Inventario.query
    
    if status != 'todos':
        query = query.filter_by(status=status)
    
    if data_inicio:
        try:
            data_inicio_dt = datetime.strptime(data_inicio, '%Y-%m-%d')
            query = query.filter(Inventario.data_inicio >= data_inicio_dt)
        except ValueError:
            flash('⚠️ Formato de data inválido para data inicial', 'warning')
    
    if data_fim:
        try:
            data_fim_dt = datetime.strptime(data_fim + ' 23:59:59', '%Y-%m-%d %H:%M:%S')
            query = query.filter(Inventario.data_inicio <= data_fim_dt)
        except ValueError:
            flash('⚠️ Formato de data inválido para data final', 'warning')
    
    inventarios = query.order_by(Inventario.data_inicio.desc()).all()
    
    total_contagens = Inventario.query.count()
    em_andamento = Inventario.query.filter_by(status='EM_ANDAMENTO').count()
    finalizadas = Inventario.query.filter_by(status='FINALIZADO').count()
    total_ajustes = db.session.query(InventarioItem).filter(InventarioItem.quantidade_ajuste != 0).count()
    
    return render_template('utilidades/inventario/lista.html',
                         inventarios=inventarios,
                         status=status,
                         data_inicio=data_inicio,
                         data_fim=data_fim,
                         total_contagens=total_contagens,
                         em_andamento=em_andamento,
                         finalizadas=finalizadas,
                         total_ajustes=total_ajustes)

@app.route('/inventario/novo', methods=['GET', 'POST'])
@login_required
def novo_inventario():
    if request.method == 'GET':
        total_produtos = Produto.query.filter_by(ativo=True).count()
        total_grades = Grade.query.count()
        total_estoque = db.session.query(func.sum(Grade.estoque_atual)).scalar() or 0
        
        produtos = Produto.query.filter_by(ativo=True).order_by(Produto.sku).all()
        
        return render_template('utilidades/inventario/novo.html',
                             total_produtos=total_produtos,
                             total_grades=total_grades,
                             total_estoque=total_estoque,
                             produtos=produtos)
    
    if request.method == 'POST':
        try:
            if 'tipo' not in request.form:
                flash('❌ Tipo de inventário é obrigatório!', 'danger')
                return redirect(url_for('novo_inventario'))
            
            tipo = request.form['tipo']
            
            inventario = Inventario(
                tipo=tipo,
                observacao=request.form.get('observacao', '').strip(),
                usuario_id=session['usuario_id'],
                status='EM_ANDAMENTO',
                data_inicio=hora_brasil()
            )
            db.session.add(inventario)
            db.session.flush()
            
            if tipo == 'COMPLETO':
                grades = Grade.query.all()
                if not grades:
                    flash('⚠️ Nenhum produto encontrado no sistema!', 'warning')
                
                for grade in grades:
                    item = InventarioItem(
                        inventario_id=inventario.id,
                        grade_id=grade.id,
                        quantidade_sistema=grade.estoque_atual,
                        quantidade_contada=0,
                        status='PENDENTE',
                        usuario_id=session['usuario_id']
                    )
                    db.session.add(item)
                
                db.session.commit()
                flash(f'✅ Inventário #{inventario.id} criado com sucesso!', 'success')
                return redirect(url_for('continuar_inventario', id=inventario.id))
            
            elif tipo == 'PARCIAL':
                produtos_selecionados = request.form.get('produtos_selecionados', '[]')
                
                if produtos_selecionados == '[]' and request.form.getlist('produtos'):
                    produto_ids = [int(id) for id in request.form.getlist('produtos')]
                else:
                    import json
                    try:
                        produto_ids = json.loads(produtos_selecionados)
                    except:
                        produto_ids = []
                
                if not produto_ids:
                    flash('❌ Selecione pelo menos um produto para inventário parcial!', 'danger')
                    db.session.rollback()
                    return redirect(url_for('novo_inventario'))
                
                grades = Grade.query.filter(Grade.produto_id.in_(produto_ids)).all()
                
                if not grades:
                    flash('⚠️ Nenhuma grade encontrada para os produtos selecionados!', 'warning')
                
                for grade in grades:
                    item = InventarioItem(
                        inventario_id=inventario.id,
                        grade_id=grade.id,
                        quantidade_sistema=grade.estoque_atual,
                        quantidade_contada=0,
                        status='PENDENTE',
                        usuario_id=session['usuario_id']
                    )
                    db.session.add(item)
                
                db.session.commit()
                flash(f'✅ Inventário parcial #{inventario.id} criado com {len(grades)} itens!', 'success')
                return redirect(url_for('continuar_inventario', id=inventario.id))
            
            elif tipo == 'AJUSTE':
                db.session.commit()
                flash(f'✅ Ajuste #{inventario.id} criado!', 'success')
                return redirect(url_for('continuar_inventario', id=inventario.id))
            
            else:
                flash('❌ Tipo de inventário inválido!', 'danger')
                db.session.rollback()
                return redirect(url_for('novo_inventario'))
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Erro ao criar inventário: {str(e)}")
            import traceback
            traceback.print_exc()
            flash(f'❌ Erro ao criar inventário: {str(e)}', 'danger')
            return redirect(url_for('novo_inventario'))

@app.route('/inventario/<int:id>')
@login_required
def ver_inventario(id):
    inventario = Inventario.query.get_or_404(id)
    return render_template('utilidades/inventario/detalhes.html', inventario=inventario)

@app.route('/inventario/<int:id>/continuar')
@login_required
def continuar_inventario(id):
    inventario = Inventario.query.get_or_404(id)
    
    if inventario.status != 'EM_ANDAMENTO':
        flash('❌ Esta contagem não está em andamento!', 'danger')
        return redirect(url_for('ver_inventario', id=id))
    
    print("\n" + "="*50)
    print(f"🔍 INVENTÁRIO #{id} - Tipo: {inventario.tipo}")
    print("="*50)
    
    if inventario.tipo == 'AJUSTE':
        print("📌 Usando template de AJUSTE (com busca de produtos)")
        print(f"📊 Itens já ajustados: {len(inventario.contagens)}")
        
        return render_template('utilidades/inventario/ajuste.html',
                             inventario=inventario)
    
    todos_itens = list(inventario.contagens)
    
    print(f"📦 Total de itens no inventário: {len(todos_itens)}")
    for i, item in enumerate(todos_itens[:5]):
        print(f"   Item {i+1}: {item.grade.sku_grade} - {item.grade.produto.descricao} (Sistema: {item.quantidade_sistema})")
    
    busca = request.args.get('q', '').strip()
    status_filtro = request.args.get('status', 'todos')
    
    itens_filtrados = todos_itens.copy()
    
    if status_filtro != 'todos':
        print(f"📌 Filtrando por status: {status_filtro}")
        if status_filtro == 'conferido':
            itens_filtrados = [item for item in itens_filtrados if item.quantidade_contada > 0]
        elif status_filtro == 'pendente':
            itens_filtrados = [item for item in itens_filtrados if item.quantidade_contada == 0]
        print(f"   → {len(itens_filtrados)} itens após filtro de status")
    
    if busca:
        print(f"🔎 Buscando por: '{busca}'")
        busca_lower = busca.lower()
        itens_filtrados = [
            item for item in itens_filtrados 
            if (item.grade.sku_grade and busca_lower in item.grade.sku_grade.lower()) or
               (item.grade.produto.descricao and busca_lower in item.grade.produto.descricao.lower()) or
               (item.grade.cor and busca_lower in item.grade.cor.lower()) or
               (item.grade.tamanho and busca_lower in str(item.grade.tamanho).lower())
        ]
        print(f"   → {len(itens_filtrados)} itens após busca")
    
    total = len(todos_itens)
    conferidos = len([i for i in todos_itens if i.quantidade_contada > 0])
    percentual = (conferidos / total * 100) if total > 0 else 0
    
    divergencias = 0
    for item in todos_itens:
        if item.quantidade_contada > 0 and item.quantidade_contada != item.quantidade_sistema:
            divergencias += 1
    
    print(f"📊 Estatísticas: Total={total}, Conferidos={conferidos}, Divergências={divergencias}")
    print(f"🎯 Enviando {len(itens_filtrados)} itens para o template")
    print("="*50 + "\n")
    
    return render_template('utilidades/inventario/contagem.html',
                         inventario=inventario,
                         todos_itens=todos_itens,
                         itens_filtrados=itens_filtrados,
                         total=total,
                         conferidos=conferidos,
                         percentual=percentual,
                         divergencias=divergencias,
                         busca=busca,
                         status_filtro=status_filtro)

@app.route('/inventario/item/<int:id>/atualizar', methods=['POST'])
@login_required
def atualizar_item_inventario(id):
    try:
        item = InventarioItem.query.get_or_404(id)
        
        if request.is_json:
            dados = request.json
        else:
            dados = request.form
        
        quantidade = int(dados.get('quantidade', 0))
        
        if item.inventario.status != 'EM_ANDAMENTO':
            return jsonify({
                'success': False, 
                'error': 'Inventário não está em andamento',
                'status_code': 400
            }), 400
        
        item.quantidade_contada = quantidade
        item.calcular_diferenca()
        item.data_contagem = hora_brasil()
        item.usuario_id = session['usuario_id']
        
        if quantidade > 0:
            item.status = 'CONFERIDO'
        else:
            item.status = 'PENDENTE'
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'diferenca': item.quantidade_ajuste,
            'status': item.status,
            'item_id': item.id,
            'mensagem': 'Item atualizado com sucesso'
        })
        
    except ValueError as e:
        return jsonify({
            'success': False, 
            'error': 'Quantidade inválida',
            'status_code': 400
        }), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False, 
            'error': str(e),
            'status_code': 500
        }), 500

@app.route('/inventario/<int:id>/finalizar', methods=['POST'])
@login_required
def finalizar_inventario(id):
    inventario = Inventario.query.get_or_404(id)
    
    id_formatado = f"#{str(id).zfill(3)}"
    
    if inventario.usuario_id != session['usuario_id'] and not session.get('usuario_admin', False):
        flash('❌ Você não tem permissão para finalizar este inventário!', 'danger')
        return redirect(url_for('ver_inventario', id=id))
    
    if inventario.status == 'FINALIZADO':
        flash('❌ Esta contagem já foi finalizada!', 'danger')
        return redirect(url_for('ver_inventario', id=id))
    
    if inventario.status != 'EM_ANDAMENTO':
        flash('❌ Esta contagem não pode ser finalizada!', 'danger')
        return redirect(url_for('ver_inventario', id=id))
    
    try:
        inventario.status = 'FINALIZADO'
        inventario.data_fim = hora_brasil()
        
        ajustes_realizados = 0
        for item in inventario.contagens:
            if item.quantidade_ajuste != 0:
                grade = item.grade
                diferenca = item.quantidade_ajuste
                
                grade.estoque_atual = item.quantidade_contada
                
                mov = Movimentacao(
                    tipo='AJUSTE',
                    grade_id=grade.id,
                    quantidade=abs(diferenca),
                    origem='INVENTARIO',
                    documento=f'INV-{inventario.id}',
                    observacao=f'Ajuste de inventário #{inventario.id}: {diferenca:+,} unidades',
                    usuario=session.get('usuario_nome', 'Sistema')
                )
                db.session.add(mov)
                item.status = 'AJUSTADO'
                ajustes_realizados += 1
        
        db.session.commit()
        
        if ajustes_realizados > 0:
            flash(f'✅ Inventário {id_formatado} finalizado com {ajustes_realizados} ajuste(s) aplicado(s)!', 'success')
        else:
            flash(f'✅ Inventário {id_formatado} finalizado sem ajustes!', 'success')
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erro ao finalizar inventário: {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f'❌ Erro ao finalizar inventário: {str(e)}', 'danger')
    
    return redirect(url_for('ver_inventario', id=id))

@app.route('/inventario/<int:id>/cancelar', methods=['POST'])
@login_required
def cancelar_inventario(id):
    print(f"🔴 ROTA CANCELAR INICIADA para ID: {id}")
    print(f"📌 Método: {request.method}")
    print(f"📌 Form data: {dict(request.form)}")
    
    id_formatado = f"#{str(id).zfill(3)}"
    
    try:
        inventario = Inventario.query.get(id)
        
        if not inventario:
            print(f"❌ Inventário ID {id} não encontrado no banco!")
            flash(f'❌ Inventário #{id} não encontrado!', 'danger')
            return redirect(url_for('inventario'))
        
        print(f"📌 Inventário encontrado: ID={inventario.id}, Status={inventario.status}")
        
        if inventario.usuario_id != session['usuario_id'] and not session.get('is_admin', False):
            print(f"❌ Usuário {session['usuario_id']} não tem permissão")
            flash('❌ Você não tem permissão para cancelar este inventário!', 'danger')
            return redirect(url_for('ver_inventario', id=id))
        
        if inventario.status != 'EM_ANDAMENTO':
            print(f"❌ Inventário não pode ser cancelado. Status atual: {inventario.status}")
            flash(f'❌ Esta contagem não pode ser cancelada (status: {inventario.status})!', 'danger')
            return redirect(url_for('ver_inventario', id=id))
        
        inventario.status = 'CANCELADO'
        inventario.data_fim = hora_brasil()
        
        observacao = request.form.get('observacao', '').strip()
        if observacao:
            inventario.observacao = (inventario.observacao or '') + f"\nCancelado: {observacao}"
        
        db.session.commit()
        
        print(f"✅ Inventário #{id} cancelado com sucesso!")
        flash(f'⚠️ Inventário {id_formatado} cancelado com sucesso.', 'warning')
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erro ao cancelar: {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f'❌ Erro ao cancelar inventário: {str(e)}', 'danger')
    
    return redirect(url_for('inventario'))

@app.route('/inventario/<int:id>/excluir', methods=['POST'])
@login_required
def excluir_inventario(id):
    print("="*50)
    print(f"🗑️ ROTA EXCLUIR para ID: {id}")
    print(f"📌 Usuário: {session.get('usuario_id')}")
    print(f"📌 usuario_admin: {session.get('usuario_admin', False)}")
    print("="*50)
    
    id_formatado = f"#{str(id).zfill(3)}"
    
    if not session.get('usuario_admin', False):
        print(f"❌ Acesso negado! Usuário não é administrador")
        flash('❌ Apenas administradores podem excluir inventários!', 'danger')
        return redirect(url_for('inventario'))
    
    try:
        inventario = Inventario.query.get(id)
        
        if not inventario:
            print(f"❌ Inventário ID {id} não encontrado!")
            flash(f'❌ Inventário #{id} não encontrado!', 'danger')
            return redirect(url_for('inventario'))
        
        print(f"✅ Inventário encontrado: ID={inventario.id}, Status={inventario.status}")
        
        if inventario.status == 'EM_ANDAMENTO':
            print(f"⚠️ Admin excluindo inventário EM ANDAMENTO!")
            flash(f'⚠️ Atenção: Inventário em andamento foi excluído!', 'warning')
        
        movimentacoes = 0
        try:
            movimentacoes = Movimentacao.query.filter_by(documento=f'INV-{inventario.id}').count()
            if movimentacoes > 0:
                print(f"⚠️ Inventário tem {movimentacoes} movimentações associadas!")
        except:
            pass
        
        itens_excluidos = InventarioItem.query.filter_by(inventario_id=id).delete()
        print(f"📌 {itens_excluidos} itens excluídos")
        
        db.session.delete(inventario)
        db.session.commit()
        
        print(f"✅ Inventário #{id} EXCLUÍDO PERMANENTEMENTE por ADMIN!")
        
        if movimentacoes > 0:
            flash(f'🗑️ Inventário {id_formatado} excluído! (Possui {movimentacoes} movimentações no estoque)', 'success')
        else:
            flash(f'🗑️ Inventário {id_formatado} excluído com sucesso!', 'success')
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erro ao excluir: {str(e)}")
        import traceback
        traceback.print_exc()
        flash(f'❌ Erro ao excluir inventário: {str(e)}', 'danger')
    
    return redirect(url_for('inventario'))

@app.route('/inventario/<int:id>/itens-pendentes')
@login_required
def itens_pendentes_inventario(id):
    try:
        inventario = Inventario.query.get_or_404(id)
        
        itens = []
        for item in inventario.contagens:
            if item.status == 'PENDENTE':
                itens.append({
                    'id': item.id,
                    'sku': item.grade.sku_grade,
                    'produto': item.grade.produto.descricao,
                    'cor': item.grade.cor,
                    'tamanho': item.grade.tamanho,
                    'quantidade_sistema': item.quantidade_sistema
                })
        
        return jsonify({
            'success': True,
            'itens': itens,
            'total': len(itens)
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/inventario/<int:id>/adicionar-ajuste', methods=['POST'])
@login_required
def adicionar_ajuste_inventario(id):
    try:
        dados = request.json
        grade_id = dados.get('grade_id')
        quantidade = int(dados.get('quantidade', 0))
        
        print(f"\n🔧 ADICIONANDO AJUSTE - Inventário: {id}, Grade: {grade_id}, Quantidade: {quantidade}")
        
        inventario = Inventario.query.get_or_404(id)
        
        if inventario.status != 'EM_ANDAMENTO':
            return jsonify({'success': False, 'error': 'Inventário não está em andamento'}), 400
        
        grade = Grade.query.get_or_404(grade_id)
        
        item_existente = InventarioItem.query.filter_by(
            inventario_id=id,
            grade_id=grade_id
        ).first()
        
        if item_existente:
            item_existente.quantidade_contada = quantidade
            item_existente.calcular_diferenca()
            item_existente.data_contagem = hora_brasil()
            item_existente.usuario_id = session['usuario_id']
            
            if quantidade > 0:
                item_existente.status = 'CONFERIDO'
            else:
                item_existente.status = 'PENDENTE'
            
            print(f"✅ Item existente atualizado: ID {item_existente.id}")
            
        else:
            item = InventarioItem(
                inventario_id=id,
                grade_id=grade_id,
                quantidade_sistema=grade.estoque_atual,
                quantidade_contada=quantidade,
                status='CONFERIDO' if quantidade > 0 else 'PENDENTE',
                usuario_id=session['usuario_id'],
                data_contagem=hora_brasil()
            )
            item.calcular_diferenca()
            db.session.add(item)
            print(f"✅ Novo item criado para grade {grade.sku_grade}")
        
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erro ao adicionar ajuste: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/inventario/debug/<int:id>/status')
@login_required
def debug_inventario_status(id):
    if not app.debug:
        return jsonify({'error': 'Acesso negado'}), 403
    
    inventario = Inventario.query.get(id)
    if not inventario:
        return jsonify({'error': 'Inventário não encontrado'}), 404
    
    return jsonify({
        'id': inventario.id,
        'status': inventario.status,
        'data_inicio': inventario.data_inicio.isoformat() if inventario.data_inicio else None,
        'data_fim': inventario.data_fim.isoformat() if inventario.data_fim else None,
        'usuario_id': inventario.usuario_id,
        'total_itens': len(inventario.contagens),
        'itens_conferidos': sum(1 for i in inventario.contagens if i.status == 'CONFERIDO'),
        'itens_ajustados': sum(1 for i in inventario.contagens if i.status == 'AJUSTADO'),
        'itens_pendentes': sum(1 for i in inventario.contagens if i.status == 'PENDENTE')
    })

@app.route('/inventario/exportar-csv')
@login_required
def exportar_inventario_csv():
    import csv
    from io import StringIO
    from flask import make_response
    
    try:
        status = request.args.get('status', 'todos')
        data_inicio = request.args.get('data_inicio')
        data_fim = request.args.get('data_fim')
        
        query = Inventario.query
        
        if status != 'todos':
            query = query.filter_by(status=status)
        
        if data_inicio:
            try:
                data_inicio_dt = datetime.strptime(data_inicio, '%Y-%m-%d')
                query = query.filter(Inventario.data_inicio >= data_inicio_dt)
            except ValueError:
                pass
        
        if data_fim:
            try:
                data_fim_dt = datetime.strptime(data_fim + ' 23:59:59', '%Y-%m-%d %H:%M:%S')
                query = query.filter(Inventario.data_inicio <= data_fim_dt)
            except ValueError:
                pass
        
        inventarios = query.order_by(Inventario.data_inicio.desc()).all()
        
        si = StringIO()
        cw = csv.writer(si, delimiter=';', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        
        cw.writerow(['ID', 'Data Início', 'Data Fim', 'Tipo', 'Status', 'Total Itens', 'Itens com Ajuste', 'Responsável', 'Observação'])
        
        for inv in inventarios:
            data_inicio_str = inv.data_inicio.strftime('%d/%m/%Y %H:%M') if inv.data_inicio else ''
            data_fim_str = inv.data_fim.strftime('%d/%m/%Y %H:%M') if inv.data_fim else ''
            
            tipo_map = {
                'COMPLETO': 'Completo',
                'PARCIAL': 'Parcial',
                'AJUSTE': 'Ajuste'
            }
            tipo = tipo_map.get(inv.tipo, inv.tipo)
            
            status_map = {
                'EM_ANDAMENTO': 'Em Andamento',
                'FINALIZADO': 'Finalizado',
                'CANCELADO': 'Cancelado'
            }
            status_str = status_map.get(inv.status, inv.status)
            
            total_itens = len(inv.contagens)
            itens_ajustados = sum(1 for i in inv.contagens if i.quantidade_ajuste != 0)
            
            if inv.usuario:
                responsavel = inv.usuario.nome or inv.usuario.username
            else:
                responsavel = 'N/A'
            
            observacao = inv.observacao.replace('\n', ' ').replace('\r', '') if inv.observacao else ''
            
            cw.writerow([
                inv.id,
                data_inicio_str,
                data_fim_str,
                tipo,
                status_str,
                total_itens,
                itens_ajustados,
                responsavel,
                observacao
            ])
        
        output = make_response(si.getvalue())
        output.headers["Content-Disposition"] = f"attachment; filename=inventarios_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        output.headers["Content-type"] = "text/csv; charset=utf-8"
        
        return output
        
    except Exception as e:
        flash(f'❌ Erro ao exportar CSV: {str(e)}', 'danger')
        return redirect(url_for('inventario'))

# ========== ROTAS PARA BACKUP ==========
@app.route('/backup')
@login_required
def pagina_backup():
    usuario = Usuario.query.get(session['usuario_id'])
    
    if not usuario.admin and not usuario.backup_visualizar:
        flash('❌ Você não tem permissão para acessar a área de backup.', 'danger')
        return redirect(url_for('dashboard'))
    
    pasta_backup = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'backups')
    
    os.makedirs(pasta_backup, exist_ok=True)
    
    backups = []
    if os.path.exists(pasta_backup):
        for arquivo in os.listdir(pasta_backup):
            if arquivo.endswith('.db') and (arquivo.startswith('backup_') or arquivo.startswith('auto_pre_')):
                caminho = os.path.join(pasta_backup, arquivo)
                stats = os.stat(caminho)
                data_criacao = datetime.fromtimestamp(stats.st_mtime)
                dias = (datetime.now() - data_criacao).days
                
                backups.append({
                    'nome': arquivo,
                    'data_criacao': data_criacao,
                    'data_formatada': data_criacao.strftime('%d/%m/%Y %H:%M'),
                    'tamanho': stats.st_size,
                    'tamanho_formatado': humanize.naturalsize(stats.st_size),
                    'dias': dias
                })
        
        backups.sort(key=lambda x: x['data_criacao'], reverse=True)
    
    tamanho_total = sum(b['tamanho'] for b in backups)
    backups_7dias = sum(1 for b in backups if b['dias'] < 7)
    
    try:
        uso_disco = shutil.disk_usage(pasta_backup)
        espaco_livre = humanize.naturalsize(uso_disco.free)
        espaco_total = humanize.naturalsize(uso_disco.total)
        espaco_disco = f"Livre: {espaco_livre} de {espaco_total}"
    except:
        espaco_disco = "Não disponível"
    
    return render_template('utilidades/backup/backup.html',
                         backups=backups,
                         tamanho_total=humanize.naturalsize(tamanho_total) if tamanho_total > 0 else "0 bytes",
                         backups_7dias=backups_7dias,
                         pasta_backup=pasta_backup,
                         espaco_disco=espaco_disco)

@app.route('/backup/novo', methods=['POST'])
@login_required
@admin_required
def criar_backup():
    usuario = Usuario.query.get(session['usuario_id'])
    
    if not usuario.admin and not usuario.backup_criar:
        return jsonify({
            'success': False, 
            'error': 'Você não tem permissão para criar backups'
        }), 403
    
    try:
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'database.db')
        
        if not os.path.exists(db_path):
            return jsonify({
                'success': False,
                'error': f'Arquivo do banco não encontrado em: {db_path}'
            }), 500
        
        pasta_backup = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'backups')
        os.makedirs(pasta_backup, exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        nome_arquivo = f"backup_{timestamp}.db"
        caminho_backup = os.path.join(pasta_backup, nome_arquivo)
        
        shutil.copy2(db_path, caminho_backup)
        
        print(f"✅ Backup criado: {nome_arquivo}")
        
        return jsonify({
            'success': True,
            'arquivo': nome_arquivo,
            'mensagem': 'Backup criado com sucesso!'
        })
        
    except Exception as e:
        print(f"❌ Erro ao criar backup: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/backup/baixar/<nome_arquivo>')
@login_required
def baixar_backup(nome_arquivo):
    usuario = Usuario.query.get(session['usuario_id'])
    
    if not usuario.admin and not usuario.backup_baixar:
        flash('❌ Você não tem permissão para baixar backups.', 'danger')
        return redirect(url_for('pagina_backup'))
    
    try:
        if '..' in nome_arquivo or '/' in nome_arquivo or '\\' in nome_arquivo:
            flash('❌ Nome de arquivo inválido!', 'danger')
            return redirect(url_for('pagina_backup'))
        
        pasta_backup = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'backups')
        caminho = os.path.join(pasta_backup, nome_arquivo)
        
        if not os.path.exists(caminho):
            flash('❌ Arquivo não encontrado!', 'danger')
            return redirect(url_for('pagina_backup'))
        
        return send_file(caminho, as_attachment=True, download_name=nome_arquivo)
        
    except Exception as e:
        flash(f'❌ Erro ao baixar: {str(e)}', 'danger')
        return redirect(url_for('pagina_backup'))

@app.route('/backup/restaurar', methods=['POST'])
@login_required
@admin_required
def restaurar_backup():
    usuario = Usuario.query.get(session['usuario_id'])
    
    if not usuario.admin and not usuario.backup_restaurar:
        return jsonify({
            'success': False, 
            'error': 'Você não tem permissão para restaurar backups'
        }), 403
    
    try:
        dados = request.json
        nome_arquivo = dados.get('arquivo')
        
        if not nome_arquivo or '..' in nome_arquivo or '/' in nome_arquivo or '\\' in nome_arquivo:
            return jsonify({'success': False, 'error': 'Nome de arquivo inválido'}), 400
        
        pasta_backup = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'backups')
        caminho_backup = os.path.join(pasta_backup, nome_arquivo)
        
        if not os.path.exists(caminho_backup):
            return jsonify({'success': False, 'error': 'Arquivo não encontrado'}), 404
        
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'database.db')
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_auto = os.path.join(pasta_backup, f"auto_pre_restauracao_{timestamp}.db")
        shutil.copy2(db_path, backup_auto)
        
        db.session.remove()
        
        shutil.copy2(caminho_backup, db_path)
        
        print(f"✅ Backup restaurado: {nome_arquivo}")
        print(f"📦 Backup automático criado: {backup_auto}")
        
        return jsonify({
            'success': True,
            'mensagem': 'Backup restaurado com sucesso! O sistema será reiniciado.'
        })
        
    except Exception as e:
        print(f"❌ Erro ao restaurar backup: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/backup/excluir', methods=['POST'])
@login_required
@admin_required
def excluir_backup():
    usuario = Usuario.query.get(session['usuario_id'])
    
    if not usuario.admin and not usuario.backup_excluir:
        return jsonify({
            'success': False, 
            'error': 'Você não tem permissão para excluir backups'
        }), 403
    
    try:
        dados = request.json
        nome_arquivo = dados.get('arquivo')
        
        if not nome_arquivo or '..' in nome_arquivo or '/' in nome_arquivo or '\\' in nome_arquivo:
            return jsonify({'success': False, 'error': 'Nome de arquivo inválido'}), 400
        
        pasta_backup = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance', 'backups')
        caminho = os.path.join(pasta_backup, nome_arquivo)
        
        if not os.path.exists(caminho):
            return jsonify({'success': False, 'error': 'Arquivo não encontrado'}), 404
        
        if nome_arquivo.startswith('auto_pre_'):
            return jsonify({'success': False, 'error': 'Não é possível excluir backups automáticos de segurança'}), 400
        
        os.remove(caminho)
        
        print(f"🗑️ Backup excluído: {nome_arquivo}")
        
        return jsonify({
            'success': True,
            'mensagem': 'Backup excluído com sucesso!'
        })
        
    except Exception as e:
        print(f"❌ Erro ao excluir backup: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ========== ROTAS PARA CONFIGURAÇÕES ==========
@app.route('/config')
@login_required
@admin_required
def config_index():
    empresa = Empresa.query.first()
    if not empresa:
        empresa = Empresa(
            razao_social='Havaianas Store',
            nome_fantasia='Havaianas',
            cor_primaria='#0d6efd',
            cor_secundaria='#6c757d',
            cor_sucesso='#198754'
        )
        db.session.add(empresa)
        db.session.commit()
        flash('✅ Configurações iniciais criadas com sucesso!', 'success')
    
    config_comprovante = ConfigComprovante.query.first()
    if not config_comprovante:
        config_comprovante = ConfigComprovante()
        db.session.add(config_comprovante)
        db.session.commit()
        flash('✅ Configurações de comprovante criadas!', 'success')
    
    usuarios = Usuario.query.order_by(Usuario.admin.desc(), Usuario.username).all()
    
    # ===== DETECÇÃO DE IMPRESSORAS COM WIN32PRINT (SEM POWERSHELL) =====
    impressoras = []
    try:
        import win32print
        print("🔍 Detectando impressoras com win32print...")
        
        # Listar todas as impressoras locais e de rede
        impressoras_lista = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
        
        for i, printer in enumerate(impressoras_lista):
            # Extrair nome da impressora
            if isinstance(printer, tuple) and len(printer) > 2:
                nome = printer[2]  # Nome da impressora
            else:
                nome = str(printer)
            
            # Detectar tipo baseado no nome
            tipo = 'nao_fiscal'
            nome_lower = nome.lower()
            if 'pdf' in nome_lower:
                tipo = 'relatorio'
            elif 'zebra' in nome_lower or 'etiqueta' in nome_lower:
                tipo = 'etiqueta'
            elif 'fiscal' in nome_lower or 'sat' in nome_lower:
                tipo = 'fiscal'
            
            # Definir Microsoft Print to PDF como padrão se existir
            padrao = (nome == "Microsoft Print to PDF" and i == 0)
            
            impressoras.append({
                'id': i + 1,
                'nome': nome,
                'modelo': 'Impressora Windows',
                'tipo': tipo,
                'porta': 'USB',
                'padrao': padrao,
                'ativo': True
            })
            print(f"   ✅ {i+1}. {nome}")
            
        if not impressoras:
            print("⚠️ Nenhuma impressora encontrada")
            impressoras = [
                {'id': 1, 'nome': 'Microsoft Print to PDF', 'tipo': 'relatorio', 'padrao': True, 'ativo': True}
            ]
            
    except ImportError:
        print("⚠️ win32print não instalado. Instale com: pip install pywin32")
        impressoras = [
            {'id': 1, 'nome': 'Microsoft Print to PDF', 'tipo': 'relatorio', 'padrao': True, 'ativo': True},
            {'id': 2, 'nome': 'Microsoft XPS Document Writer', 'tipo': 'relatorio', 'padrao': False, 'ativo': True}
        ]
    except Exception as e:
        print(f"❌ Erro ao detectar impressoras: {e}")
        impressoras = [
            {'id': 1, 'nome': 'Microsoft Print to PDF', 'tipo': 'relatorio', 'padrao': True, 'ativo': True}
        ]
    # ================================================================
    
    ufs = ['AC', 'AL', 'AP', 'AM', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MT', 'MS', 
           'MG', 'PA', 'PB', 'PR', 'PE', 'PI', 'RJ', 'RN', 'RS', 'RO', 'RR', 'SC', 
           'SP', 'SE', 'TO']
    
    return render_template('config/configuracoes.html', 
                         empresa=empresa, 
                         config=config_comprovante,
                         ufs=ufs,
                         usuarios=usuarios,
                         impressoras=impressoras)

@app.route('/api/config/empresa', methods=['POST'])
@login_required
@admin_required
def api_salvar_empresa():
    try:
        empresa = Empresa.query.first()
        if not empresa:
            empresa = Empresa()
            db.session.add(empresa)
        
        campos = [
            'razao_social', 'nome_fantasia', 'cnpj', 'ie', 'im',
            'endereco', 'numero', 'complemento', 'bairro', 'cidade',
            'uf', 'cep', 'telefone', 'celular', 'email', 'website',
            'cor_primaria', 'cor_secundaria', 'cor_sucesso',
            'fonte_navbar_familia', 'fonte_navbar_tamanho', 'fonte_navbar_cor',
            'fonte_login_familia', 'fonte_login_tamanho', 'fonte_login_cor'
        ]
        
        for campo in campos:
            if campo in request.form:
                valor = request.form[campo].strip()
                if campo in ['fonte_navbar_tamanho', 'fonte_login_tamanho']:
                    valor = int(valor)
                setattr(empresa, campo, valor)
        
        db.session.commit()
        
        flash('✅ Dados da empresa salvos com sucesso!', 'success')
        
        return jsonify({
            'success': True,
            'message': 'Dados da empresa salvos com sucesso!'
        })
        
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Erro ao salvar dados da empresa: {str(e)}', 'danger')
        
        return jsonify({
            'success': False,
            'message': f'Erro ao salvar: {str(e)}'
        }), 500

@app.route('/api/config/comprovante', methods=['POST'])
@login_required
@admin_required
def api_salvar_comprovante():
    try:
        config = ConfigComprovante.query.first()
        if not config:
            config = ConfigComprovante()
            db.session.add(config)
        
        config.cabecalho = request.form.get('cabecalho', '')
        config.rodape = request.form.get('rodape', '')
        config.tamanho_papel = request.form.get('tamanho_papel', '80mm')
        config.fonte_tamanho = int(request.form.get('fonte_tamanho', 12))
        
        config.mostrar_cnpj = 'mostrar_cnpj' in request.form
        config.mostrar_endereco = 'mostrar_endereco' in request.form
        config.mostrar_telefone = 'mostrar_telefone' in request.form
        config.mostrar_mensagem = 'mostrar_mensagem' in request.form
        config.mostrar_logo = 'mostrar_logo' in request.form
        
        db.session.commit()
        
        flash('✅ Configurações do comprovante salvas com sucesso!', 'success')
        
        return jsonify({
            'success': True,
            'message': 'Configurações do comprovante salvas!'
        })
        
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Erro ao salvar configurações do comprovante: {str(e)}', 'danger')
        
        return jsonify({
            'success': False,
            'message': f'Erro ao salvar: {str(e)}'
        }), 500

# ========== NOVAS ROTAS PROFISSIONAIS DE IMPRESSÃO ==========
@app.route('/api/config/impressao', methods=['POST'])
@login_required
@admin_required
def api_salvar_impressao():
    """Salvar configurações de impressão"""
    try:
        empresa = Empresa.query.first()
        if not empresa:
            empresa = Empresa()
            db.session.add(empresa)
        
        # Salvar configurações básicas
        empresa.impressao_tipo = request.form.get('impressao_tipo', 'dialogo')
        empresa.impressao_vias = int(request.form.get('impressao_vias', 1))
        empresa.impressao_mensagem = request.form.get('impressao_mensagem', 'Obrigado pela preferência!')
        empresa.impressao_copiar = 'impressao_copiar' in request.form
        
        # 🔥 IMPRESSORA PADRÃO
        impressora_id = request.form.get('impressora_padrao_id')
        impressora_nome = request.form.get('impressora_padrao_nome')
        
        if impressora_id:
            empresa.impressora_padrao_id = int(impressora_id)
            print(f"📥 ID da impressora recebido: {impressora_id}")
        if impressora_nome:
            empresa.impressora_padrao_nome = impressora_nome
            print(f"📥 Nome da impressora recebido: {impressora_nome}")
        
        db.session.commit()
        
        print(f"✅ Configurações salvas: tipo={empresa.impressao_tipo}, vias={empresa.impressao_vias}, impressora_id={empresa.impressora_padrao_id}")
        
        return jsonify({
            'success': True,
            'message': 'Configurações de impressão salvas!'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erro ao salvar: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Erro ao salvar: {str(e)}'
        }), 500
    
@app.route('/api/config/impressao/dados', methods=['GET'])
@login_required
def api_get_config_impressao():
    """Buscar configurações de impressão"""
    try:
        empresa = Empresa.query.first()
        if not empresa:
            return jsonify({
                'success': True,
                'config': {
                    'tipo': 'dialogo',
                    'papel': '80mm',
                    'vias': 1,
                    'copiar': False,  # ← Padrão desativado
                    'mensagem': 'Obrigado pela preferência!',
                    'impressora_id': 1,
                    'impressora_nome': 'Microsoft Print to PDF'
                }
            })
        
        print(f"📤 Enviando via_cliente: {empresa.impressao_copiar}")
        
        return jsonify({
            'success': True,
            'config': {
                'tipo': empresa.impressao_tipo or 'dialogo',
                'papel': empresa.impressao_papel or '80mm',
                'vias': empresa.impressao_vias or 1,
                'copiar': empresa.impressao_copiar or False,  # ← Valor do banco
                'mensagem': empresa.impressao_mensagem or 'Obrigado pela preferência!',
                'impressora_id': empresa.impressora_padrao_id or 1,
                'impressora_nome': empresa.impressora_padrao_nome or 'Microsoft Print to PDF'
            }
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/impressoras', methods=['GET'])
@login_required
@admin_required
def api_listar_impressoras():
    """Listar impressoras REAIS instaladas no Windows"""
    try:
        import subprocess
        import json
        
        print("="*50)
        print("🔍 INICIANDO DETECÇÃO DE IMPRESSORAS")
        print("="*50)
        
        # Verificar se o usuário está logado
        print(f"👤 Usuário ID: {session.get('usuario_id')}")
        print(f"👤 Admin: {session.get('usuario_admin')}")
        
        # Comando PowerShell
        comando = [
            "powershell", 
            "-Command", 
            "Get-Printer | Select-Object Name, DriverName, PortName | ConvertTo-Json"
        ]
        
        print(f"📋 Executando comando: {' '.join(comando)}")
        
        resultado = subprocess.run(
            comando, 
            capture_output=True, 
            text=True, 
            encoding='utf-8'
        )
        
        print(f"📊 Código de retorno: {resultado.returncode}")
        print(f"📄 STDOUT (primeiros 200 chars): {resultado.stdout[:200]}")
        print(f"⚠️ STDERR: {resultado.stderr}")
        
        impressoras = []
        
        if resultado.returncode == 0 and resultado.stdout.strip():
            try:
                dados = json.loads(resultado.stdout)
                print(f"✅ JSON carregado. Tipo: {type(dados)}")
                
                if isinstance(dados, dict):
                    dados = [dados]
                    print("📌 Convertido dict para lista")
                
                print(f"📊 Total de impressoras no JSON: {len(dados)}")
                
                for i, printer in enumerate(dados):
                    nome = printer.get('Name', 'Desconhecida')
                    print(f"  {i+1}. {nome}")
                    
                    # Detectar tipo
                    tipo = 'nao_fiscal'
                    nome_lower = nome.lower()
                    
                    if any(x in nome_lower for x in ['fiscal', 'sat', 'ecf']):
                        tipo = 'fiscal'
                    elif any(x in nome_lower for x in ['zebra', 'etiqueta', 'label']):
                        tipo = 'etiqueta'
                    elif any(x in nome_lower for x in ['pdf', 'laser', 'a4', 'hp', 'canon', 'brother', 'epson']):
                        tipo = 'relatorio'
                    
                    impressoras.append({
                        'id': i + 1,
                        'nome': nome,
                        'modelo': printer.get('DriverName', 'Driver Padrão'),
                        'tipo': tipo,
                        'porta': printer.get('PortName', 'USB'),
                        'padrao': (i == 0),
                        'ativo': True
                    })
            except json.JSONDecodeError as e:
                print(f"❌ Erro ao decodificar JSON: {e}")
        else:
            print("⚠️ PowerShell não retornou dados válidos")
            
            # Tenta com wmic
            print("📋 Tentando com WMIC...")
            comando2 = ["wmic", "printer", "get", "name", "/format:csv"]
            resultado2 = subprocess.run(comando2, capture_output=True, text=True, encoding='utf-8')
            
            print(f"📊 WMIC retorno: {resultado2.returncode}")
            print(f"📄 WMIC stdout: {resultado2.stdout[:200]}")
            
            linhas = resultado2.stdout.strip().split('\n')
            if len(linhas) > 1:
                for i, linha in enumerate(linhas[1:]):
                    if linha.strip() and ',' in linha:
                        nome = linha.split(',')[1].strip() if len(linha.split(',')) > 1 else ''
                        if nome and nome.lower() != 'name':
                            impressoras.append({
                                'id': i + 1,
                                'nome': nome,
                                'modelo': 'Impressora Windows',
                                'tipo': 'nao_fiscal',
                                'porta': 'USB',
                                'padrao': (i == 0),
                                'ativo': True
                            })
        
        # Se não encontrou, lista padrão
        if not impressoras:
            print("📋 Usando lista padrão de impressoras")
            impressoras = [
                {
                    'id': 1,
                    'nome': 'Microsoft Print to PDF',
                    'modelo': 'PDF Virtual',
                    'tipo': 'relatorio',
                    'porta': 'Virtual',
                    'padrao': True,
                    'ativo': True
                }
            ]
        
        print(f"✅ Total final: {len(impressoras)} impressoras")
        for imp in impressoras:
            print(f"   - {imp['nome']}")
        
        return jsonify(impressoras)
        
    except Exception as e:
        print(f"❌ Erro geral: {e}")
        import traceback
        traceback.print_exc()
        return jsonify([
            {
                'id': 1,
                'nome': 'Microsoft Print to PDF',
                'modelo': 'PDF Virtual',
                'tipo': 'relatorio',
                'porta': 'Virtual',
                'padrao': True,
                'ativo': True
            }
        ])

@app.route('/api/impressoras/<int:id>/testar', methods=['GET'])
@login_required
def testar_impressora(id):
    """Testar impressora enviando comando direto"""
    try:
        import subprocess
        
        # Primeiro, lista as impressoras
        comando_lista = [
            "powershell", 
            "-Command", 
            "Get-Printer | Select-Object Name | ConvertTo-Json"
        ]
        
        resultado = subprocess.run(comando_lista, capture_output=True, text=True, encoding='utf-8')
        
        import json
        dados = json.loads(resultado.stdout) if resultado.stdout.strip() else []
        if isinstance(dados, dict):
            dados = [dados]
        
        if id < 1 or id > len(dados):
            return jsonify({'success': False, 'error': 'Impressora não encontrada'}), 404
        
        nome_impressora = dados[id-1].get('Name', '')
        
        # Criar HTML de teste
        html_teste = f"""
        <html>
        <head>
            <title>Teste de Impressão - Havaianas</title>
            <style>
                body {{ font-family: Arial; padding: 20px; }}
                h1 {{ color: #0066cc; }}
                .box {{ border: 2px solid #0066cc; padding: 20px; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <h1>🩴 SISTEMA HAVAIANAS - TESTE DE IMPRESSÃO</h1>
            <div class="box">
                <p><strong>Impressora:</strong> {nome_impressora}</p>
                <p><strong>Data:</strong> {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</p>
                <p><strong>Status:</strong> ✅ Funcionando corretamente!</p>
            </div>
            <p>Este é um teste de impressão do sistema Havaianas.</p>
            <p>Se você está vendo esta página, a impressora está configurada corretamente.</p>
        </body>
        </html>
        """
        
        # Salvar arquivo temporário
        arquivo_html = "teste_impressao.html"
        with open(arquivo_html, 'w', encoding='utf-8') as f:
            f.write(html_teste)
        
        # Abrir no navegador para impressão manual
        import webbrowser
        webbrowser.open(arquivo_html)
        
        return jsonify({
            'success': True,
            'message': f'✅ Página de teste aberta no navegador para {nome_impressora}!'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
    
@app.route('/api/impressao/resetar', methods=['POST'])
@login_required
@admin_required
def resetar_configuracoes_impressao():
    """Restaurar configurações padrão de impressão"""
    try:
        empresa = Empresa.query.first()
        if empresa:
            empresa.impressao_tipo = 'dialogo'
            empresa.impressao_papel = '80mm'
            empresa.impressao_vias = 1
            empresa.impressao_copiar = False
            empresa.impressao_mensagem = 'Obrigado pela preferência!'
            db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Configurações restauradas para o padrão!'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
#===========================================================
# ========== ROTA PARA IMPRESSÃO DIRETA ==========
@app.route('/imprimir-direto', methods=['POST'])
@login_required
def imprimir_direto():
    """Rota para imprimir comprovante sem servidor externo"""
    try:
        dados = request.json
        html = dados.get('html', '')
        impressora = dados.get('impressora', 'Microsoft Print to PDF')
        
        print(f"\n📥 Impressão direta solicitada às {time.strftime('%H:%M:%S')}")
        
        # Criar pasta temporária se não existir
        pasta_temp = os.path.join(os.path.dirname(__file__), 'temp_prints')
        os.makedirs(pasta_temp, exist_ok=True)
        
        # Gerar nome único para o arquivo
        nome_arquivo = f"comprovante_{int(time.time())}.html"
        caminho_completo = os.path.join(pasta_temp, nome_arquivo)
        
        # Adicionar CSS e script de impressão automática
        html_completo = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Comprovante de Venda</title>
    <style>
        body {{ font-family: 'Courier New', monospace; width: 80mm; margin: 0 auto; padding: 5px; }}
        @media print {{
            body {{ width: 80mm; }}
        }}
    </style>
</head>
<body>
    {html}
    <script>
        window.onload = function() {{
            setTimeout(function() {{
                window.print();
                setTimeout(function() {{
                    window.close();
                }}, 1000);
            }}, 500);
        }};
    </script>
</body>
</html>"""
        
        # Salvar arquivo
        with open(caminho_completo, 'w', encoding='utf-8') as f:
            f.write(html_completo)
        
        print(f"📄 Arquivo salvo: {caminho_completo}")
        
        # Abrir no navegador padrão
        import webbrowser
        webbrowser.open(f'file://{caminho_completo}')
        
        # Agendar limpeza do arquivo após 10 segundos
        def limpar_arquivo():
            time.sleep(10)
            try:
                os.unlink(caminho_completo)
                print(f"🗑️ Arquivo temporário removido: {nome_arquivo}")
            except:
                pass
        
        import threading
        threading.Thread(target=limpar_arquivo, daemon=True).start()
        
        return jsonify({
            'success': True,
            'message': 'Comprovante enviado para impressão'
        })
        
    except Exception as e:
        print(f"❌ Erro na impressão direta: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

#============================================================
@app.route('/api/config/logo', methods=['POST'])
@login_required
@admin_required
def api_upload_logo():
    """Upload de logos"""
    try:
        empresa = Empresa.query.first()
        if not empresa:
            empresa = Empresa()
            db.session.add(empresa)
        
        logos_alteradas = []
        
        if 'logo' in request.files:
            file = request.files['logo']
            if file and file.filename and allowed_file(file.filename):
                ext = file.filename.rsplit('.', 1)[1].lower()
                nome_arquivo = f"logo_{int(time.time())}.{ext}"
                
                caminho = os.path.join(app.config['UPLOAD_FOLDER'], 'logo', nome_arquivo)
                file.save(caminho)
                
                if empresa.logo:
                    caminho_antigo = os.path.join(app.config['UPLOAD_FOLDER'], 'logo', empresa.logo)
                    if os.path.exists(caminho_antigo):
                        os.remove(caminho_antigo)
                
                empresa.logo = nome_arquivo
                logos_alteradas.append('Logo Principal')
        
        if 'logo_login' in request.files:
            file = request.files['logo_login']
            if file and file.filename and allowed_file(file.filename):
                ext = file.filename.rsplit('.', 1)[1].lower()
                nome_arquivo = f"login_{int(time.time())}.{ext}"
                
                caminho = os.path.join(app.config['UPLOAD_FOLDER'], 'logo', nome_arquivo)
                file.save(caminho)
                
                if empresa.logo_login:
                    caminho_antigo = os.path.join(app.config['UPLOAD_FOLDER'], 'logo', empresa.logo_login)
                    if os.path.exists(caminho_antigo):
                        os.remove(caminho_antigo)
                
                empresa.logo_login = nome_arquivo
                logos_alteradas.append('Logo de Login')
        
        db.session.commit()
        
        if logos_alteradas:
            logos_str = ', '.join(logos_alteradas)
            flash(f'✅ {logos_str} atualizada(s) com sucesso!', 'success')
        else:
            flash('⚠️ Nenhuma logo foi selecionada para upload!', 'warning')
        
        return jsonify({
            'success': True,
            'message': 'Logos atualizadas com sucesso!'
        })
        
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Erro ao fazer upload das logos: {str(e)}', 'danger')
        
        return jsonify({
            'success': False,
            'message': f'Erro ao salvar logos: {str(e)}'
        }), 500

# Criar pasta para logos
os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'logo'), exist_ok=True)

# ========== ROTA SOBRE ==========
@app.route('/sobre')
@login_required
def sobre():
    total_produtos = Produto.query.count()
    total_grades = Grade.query.count()
    total_clientes = Cliente.query.count()
    total_fornecedores = Fornecedor.query.count()
    total_vendas = Venda.query.count()
    total_movimentacoes = Movimentacao.query.count()
    total_inventarios = Inventario.query.count()
    
    return render_template('utilidades/sobre.html',
                         total_produtos=total_produtos,
                         total_grades=total_grades,
                         total_clientes=total_clientes,
                         total_fornecedores=total_fornecedores,
                         total_vendas=total_vendas,
                         total_movimentacoes=total_movimentacoes,
                         total_inventarios=total_inventarios)

@app.route('/api/banco/status')
def verificar_banco_status():
    try:
        count = Produto.query.count()
        return jsonify({
            'existe': True,
            'total': count,
            'vazio': count == 0
        })
    except Exception as e:
        print(f"❌ ERRO: Banco não existe - {str(e)}")
        return jsonify({
            'existe': False,
            'total': 0,
            'vazio': True,
            'erro': str(e)
        }), 500

# ========== ROTAS PARA API DE CATÁLOGO ==========
@app.route('/api/modelos', methods=['GET'])
@login_required
def api_listar_modelos():
    modelos = Modelo.query.filter_by(ativo=True).order_by(Modelo.nome).all()
    return jsonify([{
        'id': m.id,
        'nome': m.nome,
        'codigo': m.codigo,
        'data_cadastro': m.data_cadastro.strftime('%d/%m/%Y %H:%M') if m.data_cadastro else None
    } for m in modelos])

@app.route('/api/modelos', methods=['POST'])
@login_required
def api_criar_modelo():
    try:
        dados = request.json
        nome = dados.get('nome', '').strip()
        codigo = dados.get('codigo', '').strip().upper()
        
        if not nome:
            return jsonify({'success': False, 'error': 'Nome é obrigatório'}), 400
        
        if Modelo.query.filter_by(nome=nome).first():
            return jsonify({'success': False, 'error': 'Modelo já existe'}), 400
        
        if codigo and Modelo.query.filter_by(codigo=codigo).first():
            return jsonify({'success': False, 'error': 'Código já existe'}), 400
        
        modelo = Modelo(
            nome=nome,
            codigo=codigo or nome[:3].upper(),
            ativo=True
        )
        db.session.add(modelo)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'id': modelo.id,
            'nome': modelo.nome,
            'codigo': modelo.codigo
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/modelos/<int:id>', methods=['PUT'])
@login_required
def api_atualizar_modelo(id):
    try:
        modelo = Modelo.query.get_or_404(id)
        dados = request.json
        nome = dados.get('nome', '').strip()
        codigo = dados.get('codigo', '').strip().upper()
        
        if not nome:
            return jsonify({'success': False, 'error': 'Nome é obrigatório'}), 400
        
        existente = Modelo.query.filter(Modelo.nome == nome, Modelo.id != id).first()
        if existente:
            return jsonify({'success': False, 'error': 'Nome já existe'}), 400
        
        if codigo:
            existente_codigo = Modelo.query.filter(Modelo.codigo == codigo, Modelo.id != id).first()
            if existente_codigo:
                return jsonify({'success': False, 'error': 'Código já existe'}), 400
        
        modelo.nome = nome
        modelo.codigo = codigo or nome[:3].upper()
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/modelos/<int:id>', methods=['DELETE'])
@login_required
def api_excluir_modelo(id):
    try:
        modelo = Modelo.query.get_or_404(id)
        
        em_uso = Produto.query.filter_by(modelo=modelo.nome).first()
        if em_uso:
            return jsonify({
                'success': False, 
                'error': f'Modelo está sendo usado no produto {em_uso.sku}'
            }), 400
        
        db.session.delete(modelo)
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/cores', methods=['GET'])
@login_required
def api_listar_cores():
    cores = Cor.query.filter_by(ativo=True).order_by(Cor.nome).all()
    return jsonify([{
        'id': c.id,
        'nome': c.nome,
        'hex': c.hex,
        'data_cadastro': c.data_cadastro.strftime('%d/%m/%Y %H:%M') if c.data_cadastro else None
    } for c in cores])

@app.route('/api/cores', methods=['POST'])
@login_required
def api_criar_cor():
    try:
        dados = request.json
        nome = dados.get('nome', '').strip()
        hex = dados.get('hex', '#6c757d').strip()
        
        if not nome:
            return jsonify({'success': False, 'error': 'Nome é obrigatório'}), 400
        
        if Cor.query.filter_by(nome=nome).first():
            return jsonify({'success': False, 'error': 'Cor já existe'}), 400
        
        if not hex.startswith('#') or len(hex) != 7:
            hex = '#6c757d'
        
        cor = Cor(
            nome=nome,
            hex=hex,
            ativo=True
        )
        db.session.add(cor)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'id': cor.id,
            'nome': cor.nome,
            'hex': cor.hex
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/cores/<int:id>', methods=['PUT'])
@login_required
def api_atualizar_cor(id):
    try:
        cor = Cor.query.get_or_404(id)
        dados = request.json
        nome = dados.get('nome', '').strip()
        hex = dados.get('hex', '#6c757d').strip()
        
        if not nome:
            return jsonify({'success': False, 'error': 'Nome é obrigatório'}), 400
        
        existente = Cor.query.filter(Cor.nome == nome, Cor.id != id).first()
        if existente:
            return jsonify({'success': False, 'error': 'Nome já existe'}), 400
        
        if not hex.startswith('#') or len(hex) != 7:
            hex = '#6c757d'
        
        cor.nome = nome
        cor.hex = hex
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/cores/<int:id>', methods=['DELETE'])
@login_required
def api_excluir_cor(id):
    try:
        cor = Cor.query.get_or_404(id)
        
        em_uso = Grade.query.filter_by(cor=cor.nome).first()
        if em_uso:
            produto = Produto.query.get(em_uso.produto_id)
            return jsonify({
                'success': False, 
                'error': f'Cor está sendo usada no produto {produto.sku if produto else "desconhecido"}'
            }), 400
        
        db.session.delete(cor)
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/tamanhos', methods=['GET'])
@login_required
def api_listar_tamanhos():
    tamanhos = Tamanho.query.filter_by(ativo=True).order_by(Tamanho.ordem, Tamanho.valor).all()
    return jsonify([{
        'id': t.id,
        'valor': t.valor,
        'categoria': t.categoria,
        'ordem': t.ordem,
        'data_cadastro': t.data_cadastro.strftime('%d/%m/%Y %H:%M') if t.data_cadastro else None
    } for t in tamanhos])

@app.route('/api/tamanhos', methods=['POST'])
@login_required
def api_criar_tamanho():
    try:
        dados = request.json
        valor = dados.get('valor', '').strip()
        categoria = dados.get('categoria', 'Adulto')
        
        if not valor:
            return jsonify({'success': False, 'error': 'Tamanho é obrigatório'}), 400
        
        if Tamanho.query.filter_by(valor=valor).first():
            return jsonify({'success': False, 'error': 'Tamanho já existe'}), 400
        
        tamanho = Tamanho(
            valor=valor,
            categoria=categoria,
            ordem=dados.get('ordem', 0),
            ativo=True
        )
        db.session.add(tamanho)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'id': tamanho.id,
            'valor': tamanho.valor,
            'categoria': tamanho.categoria
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/tamanhos/<int:id>', methods=['PUT'])
@login_required
def api_atualizar_tamanho(id):
    try:
        tamanho = Tamanho.query.get_or_404(id)
        dados = request.json
        valor = dados.get('valor', '').strip()
        categoria = dados.get('categoria', 'Adulto')
        
        if not valor:
            return jsonify({'success': False, 'error': 'Tamanho é obrigatório'}), 400
        
        existente = Tamanho.query.filter(Tamanho.valor == valor, Tamanho.id != id).first()
        if existente:
            return jsonify({'success': False, 'error': 'Tamanho já existe'}), 400
        
        tamanho.valor = valor
        tamanho.categoria = categoria
        tamanho.ordem = dados.get('ordem', tamanho.ordem)
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/tamanhos/<int:id>', methods=['DELETE'])
@login_required
def api_excluir_tamanho(id):
    try:
        tamanho = Tamanho.query.get_or_404(id)
        
        em_uso = Grade.query.filter_by(tamanho=tamanho.valor).first()
        if em_uso:
            produto = Produto.query.get(em_uso.produto_id)
            return jsonify({
                'success': False, 
                'error': f'Tamanho está sendo usado no produto {produto.sku if produto else "desconhecido"}'
            }), 400
        
        db.session.delete(tamanho)
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/localizacoes', methods=['GET'])
@login_required
def api_listar_localizacoes():
    locs = Localizacao.query.filter_by(ativo=True).order_by(Localizacao.codigo).all()
    return jsonify([{
        'id': l.id,
        'codigo': l.codigo,
        'descricao': l.descricao,
        'tipo': l.tipo,
        'data_cadastro': l.data_cadastro.strftime('%d/%m/%Y %H:%M') if l.data_cadastro else None
    } for l in locs])

@app.route('/api/localizacoes', methods=['POST'])
@login_required
def api_criar_localizacao():
    try:
        dados = request.json
        codigo = dados.get('codigo', '').strip().upper()
        descricao = dados.get('descricao', '').strip()
        tipo = dados.get('tipo', 'PRATELEIRA')
        
        if not codigo:
            return jsonify({'success': False, 'error': 'Código é obrigatório'}), 400
        
        if Localizacao.query.filter_by(codigo=codigo).first():
            return jsonify({'success': False, 'error': 'Código já existe'}), 400
        
        loc = Localizacao(
            codigo=codigo,
            descricao=descricao or codigo,
            tipo=tipo,
            ativo=True
        )
        db.session.add(loc)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'id': loc.id,
            'codigo': loc.codigo,
            'descricao': loc.descricao,
            'tipo': loc.tipo
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/localizacoes/<int:id>', methods=['PUT'])
@login_required
def api_atualizar_localizacao(id):
    try:
        loc = Localizacao.query.get_or_404(id)
        dados = request.json
        codigo = dados.get('codigo', '').strip().upper()
        descricao = dados.get('descricao', '').strip()
        tipo = dados.get('tipo', loc.tipo)
        
        if not codigo:
            return jsonify({'success': False, 'error': 'Código é obrigatório'}), 400
        
        existente = Localizacao.query.filter(Localizacao.codigo == codigo, Localizacao.id != id).first()
        if existente:
            return jsonify({'success': False, 'error': 'Código já existe'}), 400
        
        loc.codigo = codigo
        loc.descricao = descricao or codigo
        loc.tipo = tipo
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/localizacoes/<int:id>', methods=['DELETE'])
@login_required
def api_excluir_localizacao(id):
    try:
        loc = Localizacao.query.get_or_404(id)
        
        em_uso = Grade.query.filter_by(localizacao=loc.codigo).first()
        if em_uso:
            return jsonify({
                'success': False, 
                'error': f'Localização está sendo usada em uma grade'
            }), 400
        
        db.session.delete(loc)
        db.session.commit()
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# ========== ROTA PARA SERVIR IMAGENS ==========
@app.route('/uploads/produtos/<filename>')
def uploaded_file(filename):
    return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], 'produtos'), filename)

@app.route('/uploads/logo/<filename>')
def uploaded_logo(filename):
    return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], 'logo'), filename)

# =====================
# INICIALIZAÇÃO DO SISTEMA 
# =====================
with app.app_context():
    import os
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DB_PATH = os.path.join(BASE_DIR, 'instance', 'database.db')
    
    print("\n" + "="*70)
    print("⚙️ SISTEMA HAVAIANAS - INICIALIZAÇÃO")
    print("="*70)
    
    os.makedirs(os.path.join(BASE_DIR, 'instance'), exist_ok=True)
    
    banco_existia = os.path.exists(DB_PATH)
    print(f"📁 Banco de dados: {DB_PATH}")
    print(f"📊 Banco existia? {banco_existia}")
    
    db.create_all()
    
    is_main_process = os.environ.get('WERKZEUG_RUN_MAIN') != 'true'
    
    if is_main_process:
        if not banco_existia:
            print("\n🆕 NOVO BANCO DE DADOS CRIADO!")
            
            print("\n📁 Verificando pastas de upload...")
            
            pastas_necessarias = [
                ('uploads/produtos', '📦 Imagens de produtos'),
                ('uploads/logo', '🖼️ Logos da empresa'),
                ('instance/backups', '💾 Backups'),
            ]
            
            for pasta, desc in pastas_necessarias:
                caminho_completo = os.path.join(BASE_DIR, pasta)
                os.makedirs(caminho_completo, exist_ok=True)
                print(f"{desc}: ✅ Pasta criada/verificada")
            
            if not Usuario.query.filter_by(username='admin').first():
                admin = Usuario(
                    username='admin',
                    password='admin',
                    nome='Administrador do Sistema',
                    email='admin@havaianas.com',
                    admin=True,
                    ativo=True
                )
                db.session.add(admin)
                db.session.commit()
                print("\n👤 Usuário admin criado:")
                print("   👤 Usuário: admin")
                print("   🔑 Senha: admin")
            else:
                print("\n👤 Usuário admin já existe")
            
            if not Empresa.query.first():
                empresa = Empresa(
                    razao_social='Havaianas Store',
                    nome_fantasia='Havaianas',
                    cor_primaria='#0d6efd',
                    cor_secundaria='#6c757d',
                    cor_sucesso='#198754',
                    fonte_navbar_familia='Segoe UI',
                    fonte_navbar_tamanho=18,
                    fonte_navbar_cor='#ffffff',
                    fonte_login_familia='Segoe UI',
                    fonte_login_tamanho=28,
                    fonte_login_cor='#ffffff',
                    impressao_tipo='dialogo',
                    impressao_papel='80mm',
                    impressao_vias=1,
                    impressao_copiar=False,
                    impressao_mensagem='Obrigado pela preferência!'
                )
                db.session.add(empresa)
                db.session.commit()
                print("\n🏢 Empresa padrão criada: Havaianas Store")
            
            if not ConfigComprovante.query.first():
                config = ConfigComprovante(
                    cabecalho='',
                    rodape='Obrigado pela preferência!',
                    mostrar_cnpj=True,
                    mostrar_endereco=True,
                    mostrar_telefone=True,
                    mostrar_mensagem=True,
                    mostrar_logo=True,
                    tamanho_papel='80mm',
                    fonte_tamanho=12
                )
                db.session.add(config)
                db.session.commit()
                print("📄 Configurações de comprovante criadas")
            
            print("\n" + "="*70)
            print("✅ SISTEMA INSTALADO COM SUCESSO!")
            print("="*70)
        
        else:
            print("\n✅ Banco de dados existente carregado")
            print("📁 Pastas de upload MANTIDAS (nada foi apagado)")
        
        from sqlalchemy import inspect
        inspector = inspect(db.engine)
        tabelas = inspector.get_table_names()
        
        if tabelas:
            print(f"\n📊 Tabelas disponíveis ({len(tabelas)}):")
            for tabela in sorted(tabelas)[:10]:
                colunas = inspector.get_columns(tabela)
                print(f"   • {tabela} ({len(colunas)} colunas)")
            if len(tabelas) > 10:
                print(f"   ... e mais {len(tabelas) - 10} tabelas")
        else:
            print("⚠️  Nenhuma tabela encontrada!")
    else:
        print("\n🔄 Processo filho do reloader - ignorando inicialização")
    
    print("="*70)
# ========== ROTA PARA HTML DO COMPROVANTE ==========
@app.route('/comprovante-html/<int:venda_id>', methods=['GET'])
@login_required
def comprovante_html(venda_id):
    """Retorna HTML do comprovante para impressão"""
    try:
        venda = Venda.query.get_or_404(venda_id)
        empresa = Empresa.query.first()
        config = ConfigComprovante.query.first()
        
        # Buscar itens da venda
        itens = []
        for item in venda.itens:
            grade = Grade.query.get(item.grade_id)
            if grade:
                produto = Produto.query.get(grade.produto_id)
                descricao = f"{produto.descricao} {grade.cor} T{grade.tamanho}"
            else:
                descricao = f"Item #{item.id}"
            
            itens.append({
                'descricao': descricao,
                'quantidade': item.quantidade,
                'preco': item.preco_unitario,
                'subtotal': item.quantidade * item.preco_unitario
            })
        
        # Calcular totais
        subtotal = sum(i['subtotal'] for i in itens)
        desconto = venda.desconto or 0
        total = venda.total or (subtotal - desconto)
        
        # Formatar CPF
        cpf_formatado = ''
        if venda.cliente_cpf:
            cpf = venda.cliente_cpf.replace('.', '').replace('-', '')
            if len(cpf) == 11:
                cpf_formatado = f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"
            else:
                cpf_formatado = venda.cliente_cpf
        
        # Gerar HTML
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Comprovante #{venda.id:03d}</title>
    <style>
        body {{ 
            font-family: 'Courier New', monospace; 
            width: 300px; 
            margin: 20px auto; 
            padding: 10px;
        }}
        .header {{ text-align: center; margin-bottom: 15px; }}
        .header h3 {{ margin: 0; }}
        .info {{ margin: 10px 0; }}
        table {{ width: 100%; border-collapse: collapse; }}
        td {{ padding: 3px 0; }}
        .total {{ font-weight: bold; margin-top: 10px; }}
        .footer {{ text-align: center; margin-top: 15px; }}
        hr {{ border: none; border-top: 1px dashed #000; margin: 8px 0; }}
        button {{ 
            padding: 10px 20px; 
            background: #0d6efd; 
            color: white; 
            border: none; 
            border-radius: 5px; 
            cursor: pointer;
            margin: 5px;
        }}
        @media print {{
            button {{ display: none; }}
        }}
    </style>
</head>
<body>
    <div class="header">
        <h3>{empresa.nome_fantasia or 'Havaianas Store'}</h3>
        <p>{empresa.cnpj or '00.000.000/0000-00'}</p>
        <p>{empresa.endereco or ''} {empresa.numero or ''}</p>
    </div>
    
    <hr>
    
    <div class="info">
        <p><strong>COMPROVANTE #{venda.id:03d}</strong></p>
        <p>Data: {venda.data.strftime('%d/%m/%Y %H:%M')}</p>
        <p>Vendedor: {venda.vendedor or 'Sistema'}</p>
        <p>Cliente: {venda.cliente or 'CONSUMIDOR'}</p>
        {f'<p>CPF: {cpf_formatado}</p>' if cpf_formatado else ''}
    </div>
    
    <hr>
    
    <table>
"""
        for item in itens:
            html += f"""
        <tr>
            <td>{item['descricao'][:25]}</td>
            <td align="center">{item['quantidade']}x</td>
            <td align="right">R$ {item['preco']:.2f}</td>
            <td align="right">R$ {item['subtotal']:.2f}</td>
        </tr>"""
        
        html += f"""
    </table>
    
    <hr>
    
    <div class="total">
        <p style="display: flex; justify-content: space-between;">
            <span>Subtotal:</span>
            <span>R$ {subtotal:.2f}</span>
        </p>
        {f'<p style="display: flex; justify-content: space-between;"><span>Desconto:</span><span>- R$ {desconto:.2f}</span></p>' if desconto > 0 else ''}
        <p style="display: flex; justify-content: space-between; font-weight: bold; font-size: 1.1em;">
            <span>TOTAL:</span>
            <span>R$ {total:.2f}</span>
        </p>
    </div>
    
    <hr>
    
    <div class="info">
        <p>Forma de pagamento: {venda.forma_pagamento}</p>
    </div>
    
    <div class="footer">
        <p>{config.rodape if config else 'Obrigado pela preferência!'}</p>
    </div>
    
    <div style="text-align: center; margin-top: 20px;">
        <button onclick="window.print()">🖨️ Imprimir</button>
        <button onclick="window.close()">❌ Fechar</button>
    </div>
    
    <script>
        // Impressão automática após 1 segundo
        window.onload = function() {{
            setTimeout(function() {{
                window.print();
            }}, 1000);
        }};
    </script>
</body>
</html>"""
        
        return html
        
    except Exception as e:
        print(f"❌ Erro ao gerar comprovante: {e}")
        return f"Erro ao gerar comprovante: {str(e)}", 500
        
# ========== EXECUTAR APLICAÇÃO ================
if __name__ == '__main__':
    print("\n" + "="*50)
    print("SISTEMA DE ESTOQUE HAVAIANAS")
    print("="*50)
    print("\n✅ Sistema iniciado com sucesso!")
    print("🌐 Acesse: http://localhost:5000")
    print("🛑 Para parar: Ctrl+C")
    print("="*50)
    
    app.run(debug=True, host='0.0.0.0', port=5000)