"""Testes do envio de frequência pelo orientador (/enviarFrequencia e /cadastrarFrequencia), com o banco mockado.

Rodar a partir de app/: pytest test_frequencia_orientador.py -v
"""
from datetime import date, timedelta

import pytest
from flask.sessions import SecureCookieSessionInterface

import pesquisa as P

HOJE = date.today()


def mes_a_mes(d, n):
    """(mes, ano) n meses depois (n < 0: antes) do mês de d."""
    total = d.year * 12 + d.month - 1 + n
    return total % 12 + 1, total // 12


def form(mes, ano, **extra):
    dados = {'idAluno': '7', 'referencia': f'{mes}-{ano}', 's1': 'Leitura', 's2': 'Coleta', 's3': 'Análise',
             's4': 'Relatório', 'obs': '', 'confirmo': 'sim'}
    dados.update(extra)
    return dados


@pytest.fixture
def ambiente(monkeypatch):
    estado = {'dono': True, 'inicio': HOJE - timedelta(days=200), 'fim': HOJE + timedelta(days=165),
              'enviadas': [], 'inseridas': []}
    monkeypatch.setattr(P.app, 'session_interface', SecureCookieSessionInterface())
    monkeypatch.setattr(P.app, 'secret_key', 'teste-frequencia-orientador')
    monkeypatch.setitem(P.app.config, 'WTF_CSRF_ENABLED', False)
    monkeypatch.setattr(P.limiter, 'enabled', False)
    monkeypatch.setattr(P, 'carregar_mensagens', lambda: [])
    monkeypatch.setattr(P, 'verificarSiapeIndicacao', lambda siape, id_: estado['dono'])
    monkeypatch.setattr(P, 'consultar_dicts', lambda c, v=(): [{'inicio': estado['inicio'], 'fim': estado['fim']}])
    monkeypatch.setattr(P, 'obterColunaUnica', lambda *a: 'x')

    def executar_select(consulta, tipo=0, valores=()):
        if 'mes=%s' in consulta:
            achou = [v for v in estado['enviadas'] if (v[0], v[1]) == (int(valores[1]), int(valores[2]))]
            return achou, len(achou)
        return estado['enviadas'], len(estado['enviadas'])
    monkeypatch.setattr(P, 'executarSelect2', executar_select)
    monkeypatch.setattr(P, 'inserir', lambda consulta, valores: estado['inseridas'].append(valores))
    client = P.app.test_client()
    with client.session_transaction() as s:
        s.update({'username': '2', 'permissao': 1, 'roles': ['user'], 'edital': 0})
    return estado, client


# ----- regras -----

def test_meses_da_indicacao_vao_do_inicio_ao_fim():
    meses = P.meses_da_indicacao(date(2025, 8, 15), date(2026, 7, 31), date(2027, 1, 1))
    assert meses[0] == (8, 2025) and meses[-1] == (7, 2026) and len(meses) == 12


def test_meses_da_indicacao_param_no_mes_atual():
    assert P.meses_da_indicacao(date(2026, 11, 1), date(2027, 10, 31), date(2026, 12, 3)) == [(11, 2026), (12, 2026)]


def test_indicacao_que_ainda_nao_comecou(ambiente):
    estado, _ = ambiente
    estado['inicio'] = HOJE + timedelta(days=40)
    meses, erro = P.verificar_envio_frequencia('2', '7')
    assert meses == [] and 'só começa' in erro


def test_prazo_de_240_dias(ambiente):
    estado, _ = ambiente
    estado['inicio'], estado['fim'] = HOJE - timedelta(days=600), HOJE - timedelta(days=241)
    assert 'expirado' in P.verificar_envio_frequencia('2', '7')[1]
    estado['fim'] = HOJE - timedelta(days=240)
    meses, erro = P.verificar_envio_frequencia('2', '7')
    assert erro is None and meses[-1] == (estado['fim'].month, estado['fim'].year)


def test_indicacao_sem_datas(ambiente):
    estado, _ = ambiente
    estado['inicio'] = None
    assert 'início e fim' in P.verificar_envio_frequencia('2', '7')[1]


# ----- tela -----

def test_tela_lista_os_meses_do_periodo_e_marca_os_enviados(ambiente):
    estado, client = ambiente
    estado['enviadas'] = [mes_a_mes(HOJE, -2)]
    html = client.get('/enviarFrequencia?id=7').get_data(as_text=True)
    m, a = mes_a_mes(HOJE, -2)
    assert f'value="{m}-{a}" disabled' in html and '(já enviada)' in html
    m, a = mes_a_mes(HOJE, -1)
    assert f'value="{m}-{a}" selected' in html
    m, a = mes_a_mes(HOJE, 1)
    assert f'value="{m}-{a}"' not in html
    m, a = mes_a_mes(estado['inicio'], -1)
    assert f'value="{m}-{a}"' not in html


def test_tela_de_outro_orientador(ambiente):
    estado, client = ambiente
    estado['dono'] = False
    assert client.get('/enviarFrequencia?id=7').get_data(as_text=True) == 'Permissão negada!'


# ----- gravação -----

def test_grava_mes_antigo_dentro_do_periodo(ambiente):
    estado, client = ambiente
    m, a = estado['inicio'].month, estado['inicio'].year
    r = client.post('/cadastrarFrequencia', data=form(m, a))
    assert r.status_code == 302
    assert estado['inseridas'] == [('7', m, a, 'Leitura', 'Coleta', 'Análise', 'Relatório', '')]


def test_nao_grava_indicacao_de_outro_orientador(ambiente):
    estado, client = ambiente
    estado['dono'] = False
    r = client.post('/cadastrarFrequencia', data=form(*mes_a_mes(HOJE, -1)))
    assert r.status_code == 403 and estado['inseridas'] == []


def test_nao_grava_depois_do_prazo(ambiente):
    estado, client = ambiente
    estado['inicio'], estado['fim'] = HOJE - timedelta(days=700), HOJE - timedelta(days=300)
    r = client.post('/cadastrarFrequencia', data=form(estado['fim'].month, estado['fim'].year))
    assert r.status_code == 403 and estado['inseridas'] == []


@pytest.mark.parametrize('deslocamento', [1, 12])
def test_nao_grava_mes_futuro(ambiente, deslocamento):
    estado, client = ambiente
    r = client.post('/cadastrarFrequencia', data=form(*mes_a_mes(HOJE, deslocamento)))
    assert r.status_code == 400 and estado['inseridas'] == []


def test_nao_grava_mes_antes_do_inicio(ambiente):
    estado, client = ambiente
    r = client.post('/cadastrarFrequencia', data=form(*mes_a_mes(estado['inicio'], -1)))
    assert r.status_code == 400 and estado['inseridas'] == []


@pytest.mark.parametrize('extra', [{'referencia': '13-2026'}, {'referencia': 'x'}, {'referencia': ''},
                                   {'s2': ' '}, {'s1': 'a' * 301}])
def test_nao_grava_dados_invalidos(ambiente, extra):
    estado, client = ambiente
    r = client.post('/cadastrarFrequencia', data=form(*mes_a_mes(HOJE, -1), **extra))
    assert r.status_code == 400 and estado['inseridas'] == []


def test_nao_grava_mes_ja_enviado(ambiente):
    estado, client = ambiente
    estado['enviadas'] = [mes_a_mes(HOJE, -1)]
    r = client.post('/cadastrarFrequencia', data=form(*mes_a_mes(HOJE, -1)))
    assert r.status_code == 400 and estado['inseridas'] == []
