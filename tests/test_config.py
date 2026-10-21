"""Puente de configuracion: entorno/.env primero, luego secretos de Streamlit, luego el valor por defecto."""

import sys
import types

import config


class SecretosFalsos(dict):
    def load_if_toml_exists(self):
        return True


def _conSecretos(monkeypatch, secretos):
    falso = types.ModuleType("streamlit")
    falso.secrets = SecretosFalsos(secretos)
    monkeypatch.setattr(config, "_SECRETOS", None)
    monkeypatch.setitem(sys.modules, "streamlit", falso)


def test_secretos_de_streamlit_se_usan_si_no_hay_entorno(monkeypatch):
    monkeypatch.delenv("CLAVE_PRUEBA_FS", raising=False)
    monkeypatch.delenv("OTRA_CLAVE_FS", raising=False)
    _conSecretos(monkeypatch, {"CLAVE_PRUEBA_FS": "desde-secretos", "NUMERO_FS": 42,
                                "fundscope": {"OTRA_CLAVE_FS": "en-seccion", "CLAVE_PRUEBA_FS": "pierde"}})
    assert config.leerVariable("CLAVE_PRUEBA_FS") == "desde-secretos"   # nivel raiz gana a la seccion
    assert config.leerVariable("OTRA_CLAVE_FS") == "en-seccion"         # tambien dentro de una seccion
    assert config.leerEntero("NUMERO_FS", 1) == 42                      # numeros TOML -> texto -> entero
    assert config.leerVariable("NO_EXISTE_FS", "defecto") == "defecto"
    assert config.origenVariable("CLAVE_PRUEBA_FS") == "secretos de Streamlit"


def test_entorno_o_env_tiene_prioridad_sobre_secretos(monkeypatch):
    _conSecretos(monkeypatch, {"CLAVE_PRUEBA_FS": "desde-secretos"})
    monkeypatch.setenv("CLAVE_PRUEBA_FS", "desde-env")
    assert config.leerVariable("CLAVE_PRUEBA_FS") == "desde-env"
    assert config.origenVariable("CLAVE_PRUEBA_FS") == "entorno o .env"


def test_sin_streamlit_ni_secretos_no_falla(monkeypatch):
    monkeypatch.setattr(config, "_SECRETOS", None)
    monkeypatch.setitem(sys.modules, "streamlit", None)  # import streamlit -> ImportError
    monkeypatch.delenv("CLAVE_PRUEBA_FS", raising=False)
    assert config.leerVariable("CLAVE_PRUEBA_FS", "defecto") == "defecto"
    assert config._secretosStreamlit() == {}