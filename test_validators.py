from datetime import date

from validators import validar_cpf, validar_data_nascimento, validar_nome


def test_cpf():
    assert validar_cpf("529.982.247-25")[0]
    assert validar_cpf("52998224725")[0]
    assert validar_cpf(52998224725.0)[0]  # número lido do Excel como float
    assert not validar_cpf("111.111.111-11")[0]
    assert not validar_cpf("529.982.247-24")[0]
    assert not validar_cpf("123")[0]
    assert not validar_cpf("")[0]


def test_cpf_zeros_excel():
    # CPF 012.345.678-90 (válido) -> Excel guarda 1234567890 (perde o zero inicial)
    assert validar_cpf(1234567890)[0]
    assert validar_cpf("1234567890")[0]
    ok, erro = validar_cpf(1234567890, completar_zeros=False)
    assert not ok and erro.startswith("CPF com 10")


def test_nome():
    assert validar_nome("Maria da Silva")[0]
    assert validar_nome("José D'Ávila Júnior")[0]
    assert not validar_nome("Maria")[0]
    assert validar_nome("Maria", exigir_sobrenome=False)[0]
    assert not validar_nome("Maria 2 Silva")[0]
    assert not validar_nome("")[0]
    assert not validar_nome(None)[0]
    assert not validar_nome("Aaaaa Silva")[0]


def test_data():
    hoje = date(2026, 10, 15)
    assert validar_data_nascimento("15/03/1990", hoje=hoje)[0]
    assert validar_data_nascimento("1990-03-15", hoje=hoje)[0]
    assert validar_data_nascimento(date(1990, 3, 15), hoje=hoje)[0]
    assert not validar_data_nascimento("32/01/1990", hoje=hoje)[0]
    assert not validar_data_nascimento("15/03/2030", hoje=hoje)[0]
    assert not validar_data_nascimento("15/03/1800", hoje=hoje)[0]
    assert not validar_data_nascimento("", hoje=hoje)[0]
