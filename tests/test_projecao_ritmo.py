import pandas as pd

def test_formula_media_realizada():
    realizado_ate_agora=600.0; ultimo_mes=3
    media=realizado_ate_agora/ultimo_mes
    fechamento=realizado_ate_agora+media*(12-ultimo_mes)
    assert fechamento == 2400.0
