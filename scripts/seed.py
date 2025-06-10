import sys
import os
from werkzeug.security import generate_password_hash

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app, db, Usuario, Peca, ItemGenerico

with app.app_context():
    # ✅ Admin
    if not Usuario.query.filter_by(email="admin@admin.com").first():
        admin = Usuario(
            nome="Admin",
            email="admin@admin.com",
            senha=generate_password_hash("admin123"),
            tipo="admin",
            categorias_permitidas="autopeca,cosmeticos"
        )
        db.session.add(admin)

    # ✅ Lojista
    if not Usuario.query.filter_by(email="lojista@teste.com").first():
        lojista = Usuario(
            nome="Lojista de Teste",
            email="lojista@teste.com",
            senha=generate_password_hash("lojista123"),
            tipo="lojista",
            categorias_permitidas="autopeca,cosmeticos"
        )
        db.session.add(lojista)

    # ✅ Fornecedores
    fornecedores = [
        ("Luporini", "luporini@lupodrop.com", "autopeca"),
        ("Isapa", "isapa@lupodrop.com", "autopeca"),
        ("Beleza Pura", "beleza@lupodrop.com", "cosmeticos"),
        ("Essencial Beauty", "essencial@lupodrop.com", "cosmeticos"),
    ]

    for nome, email, categorias in fornecedores:
        if not Usuario.query.filter_by(email=email).first():
            fornecedor = Usuario(
                nome=nome,
                email=email,
                senha=generate_password_hash("1234"),
                tipo="fornecedor",
                categorias_permitidas=categorias
            )
            db.session.add(fornecedor)

    db.session.commit()

    # ✅ Peças (autopeças)
    pecas = [
        ("B02G803", "Cilindro Mestre de Embreagem B02G803", "Luporini"),
        ("PFD1234", "Pastilha de Freio Dianteiro", "Luporini"),
        ("AT5678", "Amortecedor Traseiro Corolla", "Isapa"),
        ("FA9012", "Filtro de Ar Ford Ka", "Isapa")
    ]

    for codigo, nome, fornecedor in pecas:
        if not Peca.query.filter_by(codigo=codigo).first():
            nova = Peca(
                nome=nome,
                codigo=codigo,
                aplicacoes="Compatível com vários modelos",
                fornecedor=fornecedor,
                preco="100.00",
                marca="MarcaGenérica",
                montadora="MontadoraX",
                modelos="ModeloA, ModeloB",
                anos="2000 a 2020",
                motor="1.0 / 1.6",
                categoria="autopeca",
                imagem="https://via.placeholder.com/200",
                tipo_produto="autopeca"
            )
            db.session.add(nova)

    # ✅ Cosméticos (com tipo_produto="cosmetico")
    cosmeticos = [
        ("COSM1001", "Sabonete Facial Detox", "Beleza Pura"),
        ("COSM1002", "Hidratante Corporal Amêndoas", "Beleza Pura"),
        ("COSM2001", "Kit Shampoo + Condicionador", "Essencial Beauty"),
        ("COSM2002", "Creme Anti-idade FPS 30", "Essencial Beauty")
    ]

    for codigo, nome, fornecedor in cosmeticos:
        if not ItemGenerico.query.filter_by(codigo=codigo).first():
            novo = ItemGenerico(
                nome=nome,
                codigo=codigo,
                fornecedor=fornecedor,
                preco="49.90",
                marca="MarcaCosmético",
                descricao="Descrição genérica do produto.",
                categoria="cosmeticos",
                imagem="https://via.placeholder.com/200",
                tipo_produto="cosmetico"
            )
            db.session.add(novo)

    db.session.commit()
    print("🌱 Dados inseridos com sucesso (com tipo_produto).")


