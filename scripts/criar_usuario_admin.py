"""Cria o primeiro usuário Admin do Painel Orçamento GGSP.

Roda uma única vez, depois que o schema (config/schema_postgres.sql) já
existir no Neon e .streamlit/secrets.toml já tiver `postgres_url`
preenchido. Da segunda vez em diante, a gestão de usuários deve ser feita
pela tela "Gestão de Usuários" (Camada 3), não por este script.

Uso (a partir da raiz do projeto):
    python -m scripts.criar_usuario_admin
"""
from __future__ import annotations

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.auth.queries import buscar_usuario_por_identificador, criar_usuario  # noqa: E402
from src.auth.senha import gerar_hash  # noqa: E402


def _validar_secrets_existe() -> None:
    # st.secrets carrega .streamlit/secrets.toml sozinho (relativo ao diretório
    # de onde o script roda) — só checamos aqui pra dar um erro claro em vez
    # de um traceback confuso caso o arquivo ainda não exista.
    caminho_secrets = Path(__file__).resolve().parent.parent / ".streamlit" / "secrets.toml"
    if not caminho_secrets.exists():
        raise SystemExit(
            f"Não achei {caminho_secrets}. Copie .streamlit/secrets.toml.example "
            f"para lá e preencha postgres_url antes de rodar este script."
        )


def main() -> None:
    _validar_secrets_existe()

    print("Criar primeiro usuário Admin — Painel Orçamento GGSP\n")
    matricula = input("Matrícula (Enter para pular, se for logar só por e-mail): ").strip() or None
    email = input("E-mail (Enter para pular, se for logar só por matrícula): ").strip() or None
    if not matricula and not email:
        raise SystemExit("Informe ao menos matrícula ou e-mail.")

    if buscar_usuario_por_identificador(matricula or email):
        raise SystemExit("Já existe um usuário com essa matrícula/e-mail.")

    nome_completo = input("Nome completo: ").strip()
    senha = getpass.getpass("Senha (não aparece na tela): ")
    senha_confirma = getpass.getpass("Confirme a senha: ")
    if senha != senha_confirma:
        raise SystemExit("Senhas não conferem.")
    if len(senha) < 8:
        raise SystemExit("Use uma senha com pelo menos 8 caracteres.")

    criar_usuario(
        nome_completo=nome_completo,
        papel="admin",
        senha_hash=gerar_hash(senha),
        matricula=matricula,
        email=email,
        permissao_upload=True,
        permissao_exportacao=True,
        permissao_justificativa_macro=True,
        permissao_justificativa_micro=True,
        # Esta pessoa já digitou a senha real dela agora (não é uma senha
        # temporária gerada pela Administração) — não força trocar de novo.
        precisa_trocar_senha=False,
    )
    print(f"\nUsuário Admin '{nome_completo}' criado com sucesso.")


if __name__ == "__main__":
    main()
