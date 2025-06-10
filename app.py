from flask import Flask, render_template, request, redirect, url_for, flash, abort, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import or_, and_
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from urllib.parse import urlparse, urljoin
from werkzeug.utils import secure_filename
from flask_migrate import Migrate
import os
from datetime import datetime

from dotenv import load_dotenv  
load_dotenv()

app = Flask(__name__)
app.jinja_env.add_extension('jinja2.ext.do')
app.secret_key = 'segredo-lupodrop'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///lupodrop.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)
migrate = Migrate(app, db)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# MODELOS
class Usuario(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True)
    senha = db.Column(db.String(200))
    tipo = db.Column(db.String(20))  # admin, lojista, fornecedor
    categorias_permitidas = db.Column(db.String(200))  # exemplo: "autopeca,cosmetico"

class ItemGenerico(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100))
    codigo = db.Column(db.String(50))
    fornecedor = db.Column(db.String(100))
    preco = db.Column(db.String(20))
    marca = db.Column(db.String(50))
    descricao = db.Column(db.String(300))
    categoria = db.Column(db.String(50))  # Ex: "cosmeticos", "moda", etc.
    imagem = db.Column(db.String(300))  # Pode manter por compatibilidade, mas não é mais obrigatório
    imagens = db.Column(db.Text)        # ✅ Novo campo para múltiplas imagens
    tipo_produto = db.Column(db.String(50))


class Peca(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100))
    codigo = db.Column(db.String(50))
    aplicacoes = db.Column(db.String(2000))  # aumentei limite para textos longos
    fornecedor = db.Column(db.String(100))
    preco = db.Column(db.String(20))
    marca = db.Column(db.String(50))
    montadora = db.Column(db.String(50))
    categoria = db.Column(db.String(50))
    imagens = db.Column(db.Text)  # múltiplas URLs separadas por vírgula
    tipo_produto = db.Column(db.String(50), default='autopeca')



class Pedido(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuario.id'), nullable=False)
    data_pedido = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(50), default='Pendente')
    tipo_produto = db.Column(db.String(50))
    pagamento_confirmado = db.Column(db.Boolean, default=False)
    valor_total = db.Column(db.Float, default=0.0)
    pagamento_id = db.Column(db.String(100)) 

    # 👇 relacionamento com os itens do pedido
    itens = db.relationship('ItemPedido', backref='pedido', lazy=True)

    # 👇 usado no template: p.itens_detalhados
    @property
    def itens_detalhados(self):
        return self.itens

    
    # Notas fiscais
    nf_fornecedor_pdf = db.Column(db.String(200))
    nf_fornecedor_xml = db.Column(db.String(200))
    nf_lojista_pdf = db.Column(db.String(200))
    nf_lojista_xml = db.Column(db.String(200))

    # Endereço
    endereco_nome = db.Column(db.String(100))
    endereco_rua = db.Column(db.String(100))
    endereco_numero = db.Column(db.String(20))
    endereco_complemento = db.Column(db.String(100))
    endereco_bairro = db.Column(db.String(50))
    endereco_cidade = db.Column(db.String(50))
    endereco_estado = db.Column(db.String(20))
    endereco_cep = db.Column(db.String(20))
    telefone = db.Column(db.String(50))  # ← este campo está sendo usado na rota


    # Relacionamentos
    usuario = db.relationship('Usuario', backref='pedidos')
    itens = db.relationship('ItemPedido', backref='pedido', cascade='all, delete-orphan')

class ItemPedido(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedido.id'), nullable=False)
    peca_id = db.Column(db.Integer, db.ForeignKey('peca.id'), nullable=True)
    item_generico_id = db.Column(db.Integer, db.ForeignKey('item_generico.id'), nullable=True)
    quantidade = db.Column(db.Integer, nullable=False)

    peca = db.relationship('Peca')
    item_generico = db.relationship('ItemGenerico')

with app.app_context():
    db.create_all()

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.get(int(user_id))

def is_safe_url(target):
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc

# ROTAS
@app.route('/')
@login_required
def home():
    return redirect(url_for('categorias'))

@app.route('/catalogo/<tipo_produto>')
@login_required
def catalogo_por_tipo(tipo_produto):
    busca = request.args.get('busca', '')

    if tipo_produto == 'autopeca':
        query = Peca.query.filter_by(tipo_produto=tipo_produto)

        if busca:
            query = query.filter(
                (Peca.nome.ilike(f'%{busca}%')) |
                (Peca.codigo.ilike(f'%{busca}%'))
            )

        if current_user.tipo == 'fornecedor':
            categorias = current_user.categorias_permitidas.split(',') if current_user.categorias_permitidas else []
            categorias = [c.strip().lower() for c in categorias]

            if tipo_produto not in categorias:
                flash('Você não tem permissão para acessar esta categoria.', 'danger')
                return redirect(url_for('categorias'))

            query = query.filter(db.func.lower(Peca.fornecedor) == current_user.nome.strip().lower())

        itens = query.all()

    else:
        query = ItemGenerico.query.filter_by(tipo_produto=tipo_produto)

        if busca:
            query = query.filter(
                (ItemGenerico.nome.ilike(f'%{busca}%')) |
                (ItemGenerico.codigo.ilike(f'%{busca}%'))
            )

        if current_user.tipo == 'fornecedor':
            categorias = current_user.categorias_permitidas.split(',') if current_user.categorias_permitidas else []
            categorias = [c.strip().lower() for c in categorias]

            if tipo_produto not in categorias:
                flash('Você não tem permissão para acessar esta categoria.', 'danger')
                return redirect(url_for('categorias'))

            query = query.filter(db.func.lower(ItemGenerico.fornecedor) == current_user.nome.strip().lower())

        itens = query.all()

    return render_template('catalogo.html', catalogo=itens, tipo_produto=tipo_produto, busca=busca)



@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        senha = request.form.get('senha')
        usuario = Usuario.query.filter_by(email=email).first()

        if usuario and check_password_hash(usuario.senha, senha):
            login_user(usuario)
            return redirect(url_for('categorias'))  # redireciona todos para categorias
        else:
            flash('Login inválido', 'danger')

    return render_template('login.html')

@app.route('/buscar_pecas')
@login_required
def buscar_pecas():
    termo = request.args.get('q', '')
    tipo_produto = request.args.get('tipo_produto', '')

    resultados = []

    try:
        if tipo_produto == 'autopeca':
            query = Peca.query
            if termo:
                query = query.filter(
                    (Peca.nome.ilike(f'%{termo}%')) |
                    (Peca.codigo.ilike(f'%{termo}%'))
                )
            pecas = query.all()
            for p in pecas:
                resultados.append({
                    'id': p.id,
                    'nome': p.nome,
                    'codigo': p.codigo,
                    'aplicacoes': p.aplicacoes,
                    'fornecedor': p.fornecedor,
                    'preco': p.preco,
                    'marca': p.marca,
                    'montadora': p.montadora,
                    'modelos': p.modelos,
                    'anos': p.anos,
                    'motor': p.motor,
                    'categoria': p.categoria,
                    'imagens': p.imagens
                })

        else:
            query = ItemGenerico.query
            if termo:
                query = query.filter(
                    (ItemGenerico.nome.ilike(f'%{termo}%')) |
                    (ItemGenerico.codigo.ilike(f'%{termo}%'))
                )
            itens = query.all()
            for i in itens:
                resultados.append({
                    'id': i.id,
                    'nome': i.nome,
                    'codigo': i.codigo,
                    'fornecedor': i.fornecedor,
                    'preco': i.preco,
                    'marca': i.marca,
                    'categoria': i.categoria,
                    'imagem': i.imagem
                })

        return jsonify(resultados)

    except Exception as e:
        print("❌ ERRO NA BUSCA:", str(e))
        return jsonify({'erro': 'Erro interno no servidor.'}), 500
    

@app.route('/webhook_mercado_pago', methods=['POST'])
def webhook_mercado_pago():
    import requests

    data = request.get_json()
    print("🔔 Webhook recebido:", data)

    if not data:
        return '', 400

    if data.get("type") == "payment":
        payment_id = data.get("data", {}).get("id")

        if payment_id:
            access_token = os.getenv("MP_ACCESS_TOKEN")
            url = f"https://api.mercadopago.com/v1/payments/{payment_id}"
            headers = {
                "Authorization": f"Bearer {access_token}"
            }

            try:
                response = requests.get(url, headers=headers)
                pagamento = response.json()
                print("📦 Detalhes do pagamento:", pagamento)

                if pagamento.get("status") == "approved":
                    pedido_id = pagamento.get("external_reference")

                    from models import Pedido  # ou ajuste se necessário
                    pedido = Pedido.query.filter_by(id=pedido_id).first()
                    if pedido:
                        pedido.pagamento_confirmado = True
                        pedido.status = "Pagamento Confirmado"
                        db.session.commit()
                        print(f"✅ Pagamento confirmado para o pedido {pedido.id}")
                    else:
                        print(f"❌ Pedido {pedido_id} não encontrado.")

            except Exception as e:
                print("❌ Erro ao consultar pagamento:", e)

    return '', 200




@app.route('/editar/<tipo>/<int:item_id>', methods=['GET', 'POST'])
@login_required
def editar_item(tipo, item_id):
    if tipo == 'autopeca':
        item = Peca.query.get_or_404(item_id)
    else:
        item = ItemGenerico.query.get_or_404(item_id)

    if request.method == 'POST':
        item.nome = request.form.get('nome', '').strip()
        item.codigo = request.form.get('codigo', '').strip()
        item.fornecedor = request.form.get('fornecedor', '').strip()
        item.marca = request.form.get('marca', '').strip()
        item.categoria = request.form.get('categoria', '').strip()
        item.imagens = request.form.get('imagens', '').strip()

        preco_raw = request.form.get('preco', '').strip().replace(',', '.')
        try:
            item.preco = float(preco_raw) if preco_raw else 0.0
        except ValueError:
            flash('Preço inválido.', 'danger')
            return redirect(request.url)

        if tipo == 'autopeca':
            item.aplicacoes = request.form.get('aplicacoes', '').strip()
            item.montadora = request.form.get('montadora', '').strip()

        db.session.commit()
        flash('Item atualizado com sucesso!', 'success')
        return redirect(url_for('catalogo_por_tipo', tipo_produto=tipo))

    return render_template('editar.html', item=item, tipo=tipo)




@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/pedidos')
@login_required
def pedidos():
    pagina = request.args.get('pagina', 1, type=int)
    status_filtro = request.args.get('status')
    categoria_filtro = request.args.get('categoria')

    query = Pedido.query

    # 🔒 Filtro por tipo de usuário
    if current_user.tipo == 'lojista':
        query = query.filter_by(usuario_id=current_user.id)

    elif current_user.tipo == 'fornecedor':
        categorias = [c.strip().lower() for c in current_user.categorias_permitidas.split(',')] if current_user.categorias_permitidas else []
        nome_fornecedor = current_user.nome.strip().lower()
        query = (
            query.join(Pedido.itens)
                 .outerjoin(ItemPedido.peca)
                 .outerjoin(ItemPedido.item_generico)
                 .filter(
                     or_(
                         and_(
                             db.func.lower(db.func.trim(Peca.fornecedor)) == nome_fornecedor,
                             db.func.lower(Peca.tipo_produto).in_(categorias)
                         ),
                         and_(
                             db.func.lower(db.func.trim(ItemGenerico.fornecedor)) == nome_fornecedor,
                             db.func.lower(ItemGenerico.tipo_produto).in_(categorias)
                         )
                     )
                 )
                 .distinct()
        )

    # 🎯 Filtro por status
    if status_filtro:
        query = query.filter(Pedido.status == status_filtro)

    # 🗂️ Filtro por tipo_produto
    if categoria_filtro and categoria_filtro != 'todas':
        query = (
            query.join(Pedido.itens)
                 .outerjoin(ItemPedido.peca)
                 .outerjoin(ItemPedido.item_generico)
                 .filter(
                     or_(
                         Peca.tipo_produto == categoria_filtro,
                         ItemGenerico.tipo_produto == categoria_filtro
                     )
                 )
        )

    pedidos_paginados = query.order_by(Pedido.data_pedido.desc()).paginate(page=pagina, per_page=5)

    for pedido in pedidos_paginados.items:
        pedido.itens_processados = []
        total = 0

        for item in pedido.itens:
            if item.peca_id:
                peca = Peca.query.get(item.peca_id)
            elif item.item_generico_id:
                peca = ItemGenerico.query.get(item.item_generico_id)
            else:
                peca = None

            if peca:
                try:
                    preco = float(str(peca.preco).replace(',', '.'))
                except:
                    preco = 0
                subtotal = preco * item.quantidade
                total += subtotal

                pedido.itens_processados.append({
                    'nome': peca.nome,
                    'codigo': peca.codigo,
                    'quantidade': item.quantidade,
                    'subtotal': subtotal,
                    'fornecedor': getattr(peca, 'fornecedor', 'N/A')
                })

        pedido.valor_total = round(total, 2)

    categorias_disponiveis = ['autopeca', 'cosmetico', 'moda', 'eletronico']

    return render_template(
        'pedidos.html',
        pedidos=pedidos_paginados.items,
        pagina=pagina,
        total_paginas=pedidos_paginados.pages,
        categorias=categorias_disponiveis
    )



@app.route('/adicionar_pedido/<int:peca_id>', methods=['POST'])
@login_required
def adicionar_pedido(peca_id):
    peca = Peca.query.get_or_404(peca_id)
    quantidade = int(request.form.get('quantidade', 1))
    novo_pedido = Pedido(
        usuario_id=current_user.id,
        peca_id=peca.id,
        quantidade=quantidade,
        status='Pendente'
    )
    db.session.add(novo_pedido)
    db.session.commit()
    flash('Pedido realizado com sucesso!', 'success')
    return redirect(url_for('catalogo_view'))

# ✅ Adicione esta rota que estava faltando:
@app.route('/pedido_multiplo_form')
@login_required
def pedido_multiplo_form():
    pedido = session.get('pedido_multiplo')
    if not pedido or 'itens' not in pedido:
        flash("Nenhum pedido encontrado na sessão.")
        return redirect(url_for('catalogo_por_tipo', tipo_produto='autopeca'))  # Corrigido

    tipo_produto = pedido.get('tipo_produto')
    ids = [int(i["id"]) for i in pedido["itens"]]
    pecas_base = Peca.query.filter(Peca.id.in_(ids)).all()

    pecas = []
    total = 0
    for peca in pecas_base:
        qtd = next((int(i["quantidade"]) for i in pedido["itens"] if int(i["id"]) == peca.id), 1)
        preco = float(peca.preco)
        subtotal = preco * qtd
        total += subtotal
        pecas.append({
            "id": peca.id,
            "nome": peca.nome,
            "codigo": peca.codigo,
            "quantidade": qtd,
            "preco_unitario": preco,
            "subtotal": subtotal
        })

    return render_template(
        "pedido_multiplo_form.html",
        pecas=pecas,
        total=round(total, 2),
        tipo_produto=tipo_produto
    )

@app.route('/confirmar_pagamento/<int:pedido_id>', methods=['POST'])
@login_required
def confirmar_pagamento(pedido_id):
    if current_user.tipo != 'fornecedor':
        abort(403)
    pedido = Pedido.query.get_or_404(pedido_id)
    pedido.pagamento_confirmado = True
    pedido.status = 'Pagamento Confirmado'
    db.session.commit()
    flash('Pagamento confirmado.')
    return redirect(url_for('pedidos'))

@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    if current_user.tipo != 'lojista':
        abort(403)

    dados_pedido = session.get('pedido_multiplo')
    if not dados_pedido:
        flash('Pedido não encontrado.', 'warning')
        return redirect(url_for('catalogo_por_tipo', tipo_produto='autopeca'))

    tipo_produto = dados_pedido.get('tipo_produto')
    itens_selecionados = dados_pedido.get('itens', [])
    endereco = dados_pedido.get('endereco', {})

    pecas = Peca.query.filter(Peca.id.in_([int(i['id']) for i in itens_selecionados])).all()
    itens_detalhados = []

    for peca in pecas:
        qtd = next((int(i['quantidade']) for i in itens_selecionados if int(i['id']) == peca.id), 1)
        subtotal = qtd * float(peca.preco)
        itens_detalhados.append({'peca': peca, 'quantidade': qtd, 'subtotal': subtotal})

    total = sum(i['subtotal'] for i in itens_detalhados)
    boleto_url = None

    if request.method == 'POST':
        novo = Pedido(
            usuario_id=current_user.id,
            status='Aguardando Pagamento',
            tipo_produto=tipo_produto,
            endereco_nome=endereco.get('nome'),
            telefone=endereco.get('telefone'),
            endereco_rua=endereco.get('rua'),
            endereco_numero=endereco.get('numero'),
            endereco_complemento=endereco.get('complemento'),
            endereco_bairro=endereco.get('bairro'),
            endereco_cidade=endereco.get('cidade'),
            endereco_estado=endereco.get('uf'),
            endereco_cep=endereco.get('cep'),
            valor_total=total,
            pagamento_confirmado=False
        )
        db.session.add(novo)
        db.session.flush()

        for item in itens_detalhados:
            db.session.add(ItemPedido(
                pedido_id=novo.id,
                peca_id=item['peca'].id,
                quantidade=item['quantidade']
            ))

        # Integração Mercado Pago (boleto)
        import requests
        access_token = os.getenv("MP_ACCESS_TOKEN")
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        # 🔧 Monta os itens
        items_mercado_pago = []
        for item in itens_detalhados:
            if item['peca'].nome and item['peca'].preco and item['quantidade'] > 0:
                items_mercado_pago.append({
                    "title": item['peca'].nome,
                    "quantity": item['quantidade'],
                    "unit_price": float(item['peca'].preco),
                    "currency_id": "BRL"
                })

        print("🔧 DEBUG Mercado Pago - Itens:")
        for i in items_mercado_pago:
            print(i)

        pagamento_payload = {
            "transaction_amount": total,
            "description": f"Pedido #{novo.id} - LupoDrop",
            "payment_method_id": "bolbradesco",
            "payer": {
                "email": current_user.email,
                "first_name": current_user.nome.split()[0],
                "last_name": current_user.nome.split()[-1] if len(current_user.nome.split()) > 1 else "Lupo",
                "identification": {
                    "type": "CPF",
                    "number": "12345678909"
                },
                "address": {
                    "zip_code": endereco.get("cep", "00000000"),
                    "street_name": endereco.get("rua", "Rua Exemplo"),
                    "street_number": endereco.get("numero", "123"),
                    "neighborhood": endereco.get("bairro", "Centro"),
                    "city": endereco.get("cidade", "São Paulo"),
                    "federal_unit": endereco.get("uf", "SP")
                }
            },
            "notification_url": os.getenv("MP_WEBHOOK_URL"),
            "external_reference": str(novo.id),
            "additional_info": {
                "items": items_mercado_pago
            }
        }

        response = requests.post("https://api.mercadopago.com/v1/payments", headers=headers, json=pagamento_payload)
        print("🔎 Mercado Pago Response:", response.text)
        result = response.json()
        print("🧾 Status Code:", response.status_code)
        print("🔍 Resposta Mercado Pago:", result)

        if response.status_code == 201:
            boleto_url = result.get("transaction_details", {}).get("external_resource_url")
            payment_id = result.get("id")
            novo.pagamento_id = payment_id
        else:
            flash("Erro ao gerar boleto. Tente novamente mais tarde.", "danger")
            db.session.rollback()
            return redirect(url_for('catalogo_por_tipo', tipo_produto=tipo_produto))

        db.session.commit()
        session.pop('pedido_multiplo', None)

        return render_template(
            "checkout.html",
            itens=itens_detalhados,
            total=total,
            endereco=endereco,
            boleto_url=boleto_url,
            pedido_id=novo.id
        )

    return render_template(
        "checkout.html",
        itens=itens_detalhados,
        total=total,
        endereco=endereco,
        boleto_url=boleto_url,
        pedido_id=None
    )


@app.route('/verificar_pagamento/<int:pedido_id>', methods=['POST'])
@login_required
def verificar_pagamento(pedido_id):
    pedido = Pedido.query.get_or_404(pedido_id)

    # 🔒 Verifica se o pedido pertence ao usuário logado (lojista)
    if current_user.tipo != 'lojista' or pedido.usuario_id != current_user.id:
        abort(403)

    # ❗ Impede verificação se não houver payment_id
    if not pedido.pagamento_id:
        flash('Este pedido ainda não possui um ID de pagamento vinculado.', 'danger')
        return redirect(url_for('pedidos'))

    if pedido.pagamento_confirmado:
        flash('✅ Pagamento já confirmado anteriormente.', 'success')
        return redirect(url_for('pedidos'))

    # 🔄 Verificação via API Mercado Pago
    import requests
    access_token = os.getenv("MP_ACCESS_TOKEN")
    url = f"https://api.mercadopago.com/v1/payments/{pedido.pagamento_id}"
    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    try:
        response = requests.get(url, headers=headers)
        pagamento = response.json()

        if pagamento.get("status") == "approved":
            pedido.pagamento_confirmado = True
            pedido.status = "Pagamento Confirmado"
            db.session.commit()
            flash('✅ Pagamento confirmado com sucesso!', 'success')
        else:
            flash(f'Pagamento ainda não aprovado (status: {pagamento.get("status")}).', 'warning')

    except Exception as e:
        print("❌ Erro ao verificar pagamento:", str(e))
        flash('Erro ao verificar o status do pagamento.', 'danger')

    return redirect(url_for('pedidos'))



@app.route('/upload_nf_fornecedor/<int:pedido_id>', methods=['POST'])
@login_required
def upload_nf_fornecedor(pedido_id):
    if current_user.tipo != 'fornecedor':
        abort(403)
    pedido = Pedido.query.get_or_404(pedido_id)
    if not pedido.pagamento_confirmado:
        abort(403)

    pdf = request.files['pdf']
    xml = request.files['xml']

    pdf_filename = secure_filename(f'forn_{pedido_id}_nf.pdf')
    xml_filename = secure_filename(f'forn_{pedido_id}_nf.xml')

    pdf.save(os.path.join(app.config['UPLOAD_FOLDER'], pdf_filename))
    xml.save(os.path.join(app.config['UPLOAD_FOLDER'], xml_filename))

    pedido.nf_fornecedor_pdf = pdf_filename
    pedido.nf_fornecedor_xml = xml_filename
    pedido.status = 'NF do Fornecedor Enviada'
    db.session.commit()
    flash('NF enviada com sucesso.')
    return redirect(url_for('pedidos'))

@app.route('/upload_nf_lojista/<int:pedido_id>', methods=['POST'])
@login_required
def upload_nf_lojista(pedido_id):
    if current_user.tipo != 'lojista':
        abort(403)
    pedido = Pedido.query.get_or_404(pedido_id)
    if not pedido.nf_fornecedor_pdf:
        abort(403)

    pdf = request.files.get('pdf')
    xml = request.files.get('xml')

    if not pdf or not xml:
        flash('Por favor, envie ambos os arquivos: PDF e XML.', 'warning')
        return redirect(url_for('pedidos'))

    pdf_filename = secure_filename(f'loj_{pedido_id}_nf.pdf')
    xml_filename = secure_filename(f'loj_{pedido_id}_nf.xml')

    pdf.save(os.path.join(app.config['UPLOAD_FOLDER'], pdf_filename))
    xml.save(os.path.join(app.config['UPLOAD_FOLDER'], xml_filename))

    pedido.nf_lojista_pdf = pdf_filename
    pedido.nf_lojista_xml = xml_filename
    pedido.status = 'NF do Lojista Enviada'
    db.session.commit()

    flash('NF do lojista enviada com sucesso.', 'success')
    return redirect(url_for('pedidos'))

@app.route('/confirmar_envio/<int:pedido_id>', methods=['POST'])
@login_required
def confirmar_envio(pedido_id):
    if current_user.tipo != 'fornecedor':
        abort(403)
    pedido = Pedido.query.get_or_404(pedido_id)
    if not pedido.nf_lojista_pdf:
        abort(403)
    pedido.status = 'Pedido Enviado'
    db.session.commit()
    flash('Pedido enviado com sucesso.')
    return redirect(url_for('pedidos'))

@app.route('/formulario_autopeca', methods=['GET', 'POST'])
@login_required
def formulario_autopeca():
    if current_user.tipo != 'admin':
        abort(403)

    if request.method == 'POST':
        nova_peca = Peca(
            nome=request.form.get('nome'),
            codigo=request.form.get('codigo'),
            aplicacoes=request.form.get('aplicacoes'),
            fornecedor=request.form.get('fornecedor'),
            preco=request.form.get('preco'),
            marca=request.form.get('marca'),
            montadora=request.form.get('montadora'),
            modelos=request.form.get('modelos'),
            anos=request.form.get('anos'),
            motor=request.form.get('motor'),
            categoria=request.form.get('categoria'),
            imagens=request.form.get('imagens', ''),  # ← substitui imagem por imagens
            tipo_produto='autopeca'
        )
        db.session.add(nova_peca)
        db.session.commit()
        flash('Peça cadastrada com sucesso!', 'success')
        return redirect(url_for('catalogo_por_tipo', tipo_produto='autopeca'))

    return render_template('formulario_autopeca.html')


@app.route('/importar-planilha-autopeca', methods=['GET', 'POST'])
@login_required
def importar_planilha_autopeca():
    if current_user.tipo != 'admin':
        abort(403)

    if request.method == 'POST':
        file = request.files.get('planilha')
        if not file:
            flash('Nenhum arquivo enviado.', 'danger')
            return redirect(request.url)

        import pandas as pd

        try:
            df = pd.read_excel(file)
        except Exception as e:
            flash(f'Erro ao ler a planilha: {e}', 'danger')
            return redirect(request.url)

        erros = 0
        for _, row in df.iterrows():
            try:
                preco_raw = row.get('preco', '')
                try:
                    preco = float(str(preco_raw).replace(',', '.').strip())
                except:
                    preco = 0.0

                nova = Peca(
    nome=str(row.get('nome', '')).strip(),
    codigo=str(row.get('codigo', '')).strip(),
    fornecedor=str(row.get('fornecedor', '')).strip(),
    preco=preco,
    marca=str(row.get('marca', '')).strip(),
    categoria=str(row.get('categoria', '')).strip(),
    imagens=str(row.get('imagens', '')).strip(),
    aplicacoes=str(row.get('aplicacoes', '')).strip(),
    montadora=str(row.get('montadora', '')).strip(),
    tipo_produto='autopeca'
)
                db.session.add(nova)
            except Exception as e:
                print(f"Erro na linha: {row.to_dict()} | Erro: {e}")
                erros += 1

        db.session.commit()
        flash(f'Planilha importada com sucesso! Linhas com erro: {erros}', 'success')
        return redirect(url_for('catalogo_por_tipo', tipo_produto='autopeca'))

    return render_template('importar_planilha.html')



@app.route('/usuarios')
@login_required
def usuarios():
    if current_user.tipo != 'admin':
        abort(403)
    usuarios = Usuario.query.all()
    return render_template('usuarios.html', usuarios=usuarios)

@app.route('/criar-usuario', methods=['GET', 'POST'])
@login_required
def criar_usuario():
    if current_user.tipo != 'admin':
        abort(403)
    if request.method == 'POST':
        nome = request.form['nome']
        email = request.form['email']
        senha = request.form['senha']
        tipo = request.form['tipo']
        categorias = request.form.getlist('categorias') if tipo == 'fornecedor' else []

        if Usuario.query.filter_by(email=email).first():
            flash('E-mail já cadastrado.', 'danger')
            return redirect(url_for('criar_usuario'))

        usuario = Usuario(
            nome=nome,
            email=email,
            senha=generate_password_hash(senha),
            tipo=tipo,
            categorias_permitidas=','.join(categorias) if categorias else None
        )
        db.session.add(usuario)
        db.session.commit()
        flash('Usuário criado com sucesso!', 'success')
        return redirect(url_for('usuarios'))

    categorias_disponiveis = ['autopeca', 'cosmetico', 'moda', 'eletronico']
    return render_template('criar_usuario.html', categorias_disponiveis=categorias_disponiveis)

@app.route('/editar-usuario/<int:usuario_id>', methods=['GET', 'POST'])
@login_required
def editar_usuario(usuario_id):
    if current_user.tipo != 'admin':
        abort(403)
    usuario = Usuario.query.get_or_404(usuario_id)
    if request.method == 'POST':
        nova_senha = request.form['nova_senha']
        categorias = request.form.getlist('categorias') if usuario.tipo == 'fornecedor' else []
        usuario.senha = generate_password_hash(nova_senha)
        usuario.categorias_permitidas = ','.join(categorias) if categorias else None
        db.session.commit()
        flash('Senha e categorias atualizadas com sucesso!', 'success')
        return redirect(url_for('usuarios'))
    categorias_disponiveis = ['autopeca', 'cosmetico', 'moda', 'eletronico']
    return render_template('editar_usuario.html', usuario=usuario, categorias_disponiveis=categorias_disponiveis)

@app.route('/excluir-usuario/<int:usuario_id>', methods=['POST'])
@login_required
def excluir_usuario(usuario_id):
    if current_user.tipo != 'admin':
        abort(403)

    usuario = Usuario.query.get_or_404(usuario_id)

    # Verifica se o usuário possui pedidos associados
    pedidos_relacionados = Pedido.query.filter_by(usuario_id=usuario.id).first()
    if pedidos_relacionados:
        flash('Erro: não é possível excluir um usuário que possui pedidos vinculados.', 'danger')
        return redirect(url_for('usuarios'))

    db.session.delete(usuario)
    db.session.commit()
    flash('Usuário excluído com sucesso.', 'success')
    return redirect(url_for('usuarios'))


@app.route('/pedido_form/<int:peca_id>', methods=['GET', 'POST'], endpoint='pedido_form')
@login_required
def pedido_form(peca_id):
    if current_user.tipo != 'lojista':
        abort(403)

    peca = Peca.query.get_or_404(peca_id)

    if request.method == 'POST':
        quantidade = request.form.get('quantidade', type=int)
        endereco_nome = request.form.get('endereco_nome')
        endereco_rua = request.form.get('endereco_rua')
        endereco_numero = request.form.get('endereco_numero')
        endereco_complemento = request.form.get('endereco_complemento')  # <- faltava esse
        endereco_bairro = request.form.get('endereco_bairro')
        endereco_cidade = request.form.get('endereco_cidade')
        endereco_estado = request.form.get('endereco_estado')
        endereco_cep = request.form.get('endereco_cep')

        if quantidade < 1:
            flash('Quantidade inválida.', 'danger')
            return redirect(request.url)

        novo_pedido = Pedido(
            peca_id=peca_id,
            usuario_id=current_user.id,
            quantidade=quantidade,
            endereco_nome=endereco_nome,
            endereco_rua=endereco_rua,
            endereco_numero=endereco_numero,
            endereco_complemento=endereco_complemento,  # <- inclui no objeto
            endereco_bairro=endereco_bairro,
            endereco_cidade=endereco_cidade,
            endereco_estado=endereco_estado,
            endereco_cep=endereco_cep
        )
        db.session.add(novo_pedido)
        db.session.commit()
        flash('Pedido realizado com sucesso!', 'pedido')
        return redirect(url_for('pedidos'))

    return render_template('pedido_form.html', peca=peca)

@app.route('/excluir_pedido/<int:pedido_id>', methods=['POST'])
@login_required
def excluir_pedido(pedido_id):
    if current_user.tipo != 'admin':
        abort(403)
    pedido = Pedido.query.get_or_404(pedido_id)
    db.session.delete(pedido)
    db.session.commit()
    flash('Pedido excluído com sucesso.', 'pedido')
    return redirect(url_for('pedidos'))

@app.route('/cancelar_pedido/<int:pedido_id>', methods=['POST'])
@login_required
def cancelar_pedido(pedido_id):
    pedido = Pedido.query.get_or_404(pedido_id)

    if current_user.tipo not in ['lojista', 'fornecedor', 'admin']:
        abort(403)

    if pedido.status in ['Pedido Enviado', 'Cancelado']:
        flash('Este pedido não pode mais ser cancelado.', 'warning')
        return redirect(url_for('pedidos'))

    pedido.status = 'Cancelado'
    db.session.commit()
    flash('Pedido cancelado com sucesso.', 'info')
    return redirect(url_for('pedidos'))

@app.route('/editar/<int:peca_id>', methods=['GET', 'POST'])
@login_required
def editar(peca_id):
    if current_user.tipo != 'admin':
        abort(403)

    peca = Peca.query.get_or_404(peca_id)

    if request.method == 'POST':
        peca.nome = request.form.get('nome', '').strip()
        peca.codigo = request.form.get('codigo', '').strip()
        peca.fornecedor = request.form.get('fornecedor', '').strip()

        preco_raw = request.form.get('preco', '').strip().replace(',', '.')
        try:
            peca.preco = float(preco_raw) if preco_raw else 0.0
        except ValueError:
            flash('Preço inválido.', 'danger')
            return redirect(request.url)

        peca.marca = request.form.get('marca', '').strip()
        peca.categoria = request.form.get('categoria', '').strip()
        peca.imagens = request.form.get('imagens', '').strip()  # ← campo múltiplas imagens

        if peca.tipo_produto == 'autopeca':
            peca.aplicacoes = request.form.get('aplicacoes', '').strip()
            peca.montadora = request.form.get('montadora', '').strip()
            

        db.session.commit()
        flash('Peça atualizada com sucesso!', 'success')
        return redirect(url_for('catalogo_por_tipo', tipo_produto=peca.tipo_produto))

    return render_template('editar.html', item=peca, tipo=peca.tipo_produto)






@app.route('/pedido_multiplo_endereco', methods=['POST'])
@login_required
def pedido_multiplo_endereco():
    if current_user.tipo != 'lojista':
        abort(403)

    data = request.get_json()
    tipo_produto = data.get("tipo_produto")
    itens_recebidos = data.get("itens", [])

    itens = []
    total = 0
    fornecedores = set()

    for item in itens_recebidos:
        item_id = int(item.get("id"))
        quantidade = int(item.get("quantidade"))

        if tipo_produto == "autopeca":
            peca = Peca.query.get(item_id)
        else:
            peca = ItemGenerico.query.get(item_id)

        if peca and quantidade > 0:
            fornecedor = getattr(peca, 'fornecedor', '').strip().lower()
            fornecedores.add(fornecedor)
            try:
                preco_float = float(str(peca.preco).replace(',', '.'))
            except:
                preco_float = 0
            subtotal = preco_float * quantidade
            total += subtotal
            itens.append({
                'id': peca.id,
                'nome': peca.nome,
                'quantidade': quantidade,
                'preco_unitario': preco_float,
                'subtotal': subtotal,
                'codigo': peca.codigo
            })

    if not itens:
        return jsonify({'erro': 'Nenhum item válido foi enviado.'}), 400

    if len(fornecedores) > 1:
        return jsonify({'erro': 'Itens de mais de um fornecedor não são permitidos.'}), 400

    # ✅ Salva na sessão
    session['pedido_multiplo'] = {
    'itens': itens,
    'total': round(total, 2),
    'tipo_produto': tipo_produto,
    'endereco': {}  # adiciona isso para evitar erro futuro no checkout
}

    # ✅ Responde para o JS com redirecionamento
    return jsonify({'redirect': url_for('pedido_multiplo_form')})



@app.route('/salvar_pedido_multiplo', methods=['POST'])
@login_required
def salvar_pedido_multiplo():
    if current_user.tipo != 'lojista':
        abort(403)

    tipo_produto = request.form.get("tipo_produto")

    # Coleta os dados do endereço
    endereco = {
        "nome": request.form.get("nome"),
        "telefone": request.form.get("telefone"),
        "cep": request.form.get("cep"),
        "rua": request.form.get("rua"),
        "numero": request.form.get("numero"),
        "complemento": request.form.get("complemento"),
        "bairro": request.form.get("bairro"),
        "cidade": request.form.get("cidade"),
        "uf": request.form.get("uf")
    }

    # Coleta os itens
    itens = []
    for key, value in request.form.items():
        if key.startswith("quantidade_autopeca_") or key.startswith("quantidade_generico_"):
            try:
                item_id = int(key.split("_")[-1])
                quantidade = int(value)
                if quantidade > 0:
                    itens.append({"id": item_id, "quantidade": quantidade})
            except:
                continue

    if not itens:
        flash("Nenhum item válido informado.", "warning")
        return redirect(url_for("catalogo_por_tipo", tipo_produto=tipo_produto))

    # Salva tudo na sessão
    session["pedido_multiplo"] = {
        "tipo_produto": tipo_produto,
        "itens": itens,
        "endereco": endereco
    }

    return redirect(url_for("checkout"))


@app.route('/categorias')
@login_required
def categorias():
    todos_os_tipos = [
        {'id': 'autopeca', 'nome': 'Autopeças'},
        {'id': 'cosmetico', 'nome': 'Cosméticos'},
        {'id': 'moda', 'nome': 'Moda'},
        {'id': 'eletronico', 'nome': 'Eletrônicos'}
    ]

    # Se for fornecedor, filtra pelas categorias permitidas
    if current_user.tipo == 'fornecedor':
        categorias_permitidas = current_user.categorias_permitidas.split(',') if current_user.categorias_permitidas else []
        categorias_permitidas = [c.strip().lower() for c in categorias_permitidas]

        tipos = [cat for cat in todos_os_tipos if cat['id'] in categorias_permitidas]
    else:
        tipos = todos_os_tipos

    return render_template('categorias.html', tipos=tipos)


@app.route('/formulario_generico/<tipo_produto>', methods=['GET', 'POST'])
@login_required
def formulario_generico(tipo_produto):
    if current_user.tipo != 'admin':
        abort(403)

    if request.method == 'POST':
        nome = request.form.get('nome')
        preco = request.form.get('preco')
        imagens = request.form.get('imagens', 'sem imagem')  # ← atualizado
        descricao = request.form.get('descricao')
        fornecedor = request.form.get('fornecedor') or 'Genérico'
        marca = request.form.get('marca') or 'Genérica'
        codigo = request.form.get('codigo') or 'GEN-' + nome[:3].upper()

        novo = ItemGenerico(
            nome=nome,
            preco=preco,
            imagens=imagens,  # ← atualizado
            categoria=tipo_produto,
            tipo_produto=tipo_produto,
            descricao=descricao,
            fornecedor=fornecedor,
            marca=marca,
            codigo=codigo
        )

        db.session.add(novo)
        db.session.commit()
        flash('Item genérico adicionado com sucesso!', 'success')
        return redirect(url_for('catalogo_por_tipo', tipo_produto=tipo_produto))

    return render_template('formulario_generico.html', tipo_produto=tipo_produto)

@app.route('/cancelar_checkout')
@login_required
def cancelar_checkout():
    session.pop('pedido_multiplo', None)
    flash('Pedido cancelado.', 'warning')
    return redirect(url_for('catalogo_por_tipo', tipo_produto='autopeca'))


@app.route('/excluir/<int:peca_id>', methods=['POST'])
@login_required
def excluir_peca(peca_id):
    peca = Peca.query.get_or_404(peca_id)
    db.session.delete(peca)
    db.session.commit()
    flash('Peça excluída com sucesso!', 'success')
    return redirect(request.referrer or url_for('categorias'))

@app.route('/excluir-generico/<int:item_id>', methods=['POST'])
@login_required
def excluir_item_generico(item_id):
    item = ItemGenerico.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    flash('Item excluído com sucesso!', 'success')
    return redirect(request.referrer or url_for('categorias'))


if __name__ == '__main__':
    print("🔐 Webhook configurado para:", os.getenv("MP_WEBHOOK_URL"))
    app.run(debug=True, port=5000)
