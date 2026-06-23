import sqlite3
import os

DB_PATH = os.path.join("relatorios", "historico.db")


def get_connection():
    os.makedirs("relatorios", exist_ok=True)
    return sqlite3.connect(DB_PATH)


def criar_tabela():

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS noshow (
            id TEXT PRIMARY KEY,
            unidade TEXT,
            cancelado_em TEXT,
            tipo_noshow TEXT,
            motivo TEXT,
            tipo_frete TEXT,
            agendado TEXT,
            cliente TEXT,
            periodo TEXT,
            codigo TEXT,
            descricao TEXT,
            cpf TEXT,
            nome TEXT,
            placas TEXT,
            data_execucao TEXT
        )
    """)

    conn.commit()
    conn.close()


def inserir_noshow(registro):

    conn = get_connection()
    cur = conn.cursor()

    try:

        cur.execute("""
            INSERT INTO noshow VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            registro.get("ID"),
            registro.get("Unidade"),
            registro.get("CanceladoEm"),
            registro.get("TipoNoShow"),
            registro.get("Motivo"),
            registro.get("Tipo Frete"),
            registro.get("Agendado"),
            registro.get("Cliente"),
            registro.get("Periodo"),
            registro.get("Codigo"),
            registro.get("Descricao"),
            registro.get("Cpf"),
            registro.get("Nome"),
            registro.get("Placas"),
            registro.get("DataExecucao"),
        ))

        conn.commit()

    except sqlite3.IntegrityError:
        pass

    conn.close()