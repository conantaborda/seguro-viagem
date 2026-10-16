"""Consulta de CEP em APIs públicas: ViaCEP (principal) e BrasilAPI (reserva)."""
from __future__ import annotations

import re

import requests

URL_VIACEP = "https://viacep.com.br/ws/{cep}/json/"
URL_BRASILAPI = "https://brasilapi.com.br/api/cep/v2/{cep}"


class ConsultaCepErro(Exception):
    """Nenhuma API respondeu (rede, timeout ou erro do servidor). Diferente de "CEP não existe"."""


def so_cep(valor) -> str | None:
    """Devolve os 8 dígitos do CEP ou None se o formato for inválido."""
    d = re.sub(r"\D", "", str(valor or ""))
    return d if len(d) == 8 else None


def _viacep(cep: str, timeout: float) -> dict | None:
    r = requests.get(URL_VIACEP.format(cep=cep), timeout=timeout)
    if r.status_code == 400:  # formato rejeitado pela API
        return None
    r.raise_for_status()
    j = r.json()
    if j.get("erro"):
        return None
    return {
        "cep": cep,
        "rua": j.get("logradouro", "") or "",
        "bairro": j.get("bairro", "") or "",
        "cidade": j.get("localidade", "") or "",
        "uf": j.get("uf", "") or "",
        "complemento": j.get("complemento", "") or "",
    }


def _brasilapi(cep: str, timeout: float) -> dict | None:
    r = requests.get(URL_BRASILAPI.format(cep=cep), timeout=timeout)
    if r.status_code in (400, 404):
        return None
    r.raise_for_status()
    j = r.json()
    return {
        "cep": cep,
        "rua": j.get("street", "") or "",
        "bairro": j.get("neighborhood", "") or "",
        "cidade": j.get("city", "") or "",
        "uf": j.get("state", "") or "",
        "complemento": "",
    }


def consultar_cep(cep, timeout: float = 6) -> dict | None:
    """Endereço do CEP: {cep, rua, bairro, cidade, uf, complemento}.

    - devolve None se o CEP tem formato inválido ou não existe em nenhuma API que respondeu;
    - levanta ConsultaCepErro se nenhuma API conseguiu responder.
    """
    d = so_cep(cep)
    if not d:
        return None
    erros, respondeu = [], False
    for consulta in (_viacep, _brasilapi):
        try:
            resultado = consulta(d, timeout)
        except (requests.RequestException, ValueError) as e:
            erros.append(f"{consulta.__name__}: {type(e).__name__}")
            continue
        respondeu = True
        if resultado:
            return resultado
    if respondeu:
        return None
    raise ConsultaCepErro("; ".join(erros))
