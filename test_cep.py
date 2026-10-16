"""Testes da consulta de CEP com as APIs simuladas (sem acesso à rede)."""
from unittest.mock import patch

import requests

import cep as modulo_cep
from cep import ConsultaCepErro, consultar_cep, so_cep


class Resp:
    def __init__(self, status=200, corpo=None):
        self.status_code, self._corpo = status, corpo or {}

    def json(self):
        return self._corpo

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


VIACEP_OK = {"cep": "01001-000", "logradouro": "Praça da Sé", "complemento": "lado ímpar",
             "bairro": "Sé", "localidade": "São Paulo", "uf": "SP"}
BRASILAPI_OK = {"cep": "01001000", "state": "SP", "city": "São Paulo", "neighborhood": "Sé",
                "street": "Praça da Sé"}


def simular(viacep, brasilapi):
    """Cada argumento: Resp ou Exception levantada pela chamada."""
    def get(url, timeout=None):
        r = viacep if "viacep" in url else brasilapi
        if isinstance(r, Exception):
            raise r
        return r
    return patch.object(modulo_cep.requests, "get", side_effect=get)


def test_so_cep():
    assert so_cep("01001-000") == "01001000"
    assert so_cep("123") is None and so_cep(None) is None


def test_viacep_ok():
    with simular(Resp(200, VIACEP_OK), Exception("não deveria chamar")):
        r = consultar_cep("01001-000")
    assert r == {"cep": "01001000", "rua": "Praça da Sé", "bairro": "Sé", "cidade": "São Paulo",
                 "uf": "SP", "complemento": "lado ímpar"}


def test_viacep_nao_acha_brasilapi_acha():
    with simular(Resp(200, {"erro": True}), Resp(200, BRASILAPI_OK)):
        r = consultar_cep("01001000")
    assert r["rua"] == "Praça da Sé" and r["uf"] == "SP"


def test_cep_inexistente_nas_duas_apis():
    with simular(Resp(200, {"erro": True}), Resp(404)):
        assert consultar_cep("99999999") is None


def test_uma_api_cai_outra_diz_que_nao_existe():
    with simular(requests.ConnectionError("fora do ar"), Resp(404)):
        assert consultar_cep("99999999") is None


def test_as_duas_apis_fora_do_ar():
    with simular(requests.Timeout("lenta"), requests.ConnectionError("fora")):
        try:
            consultar_cep("01001000")
        except ConsultaCepErro:
            return
    raise AssertionError("deveria levantar ConsultaCepErro")


def test_formato_invalido_nao_chama_a_api():
    with patch.object(modulo_cep.requests, "get") as get:
        assert consultar_cep("123") is None
        get.assert_not_called()
