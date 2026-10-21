from datetime import datetime, timezone
from app.services import business_time as time


def test_business_clock_uses_nicaragua_even_when_host_is_utc(monkeypatch):
    class Clock:
        @staticmethod
        def now(zone):
            return datetime(2026,11,1,2,0,0,999999,tzinfo=timezone.utc).astimezone(zone)
    monkeypatch.setattr(time,'datetime',Clock)
    assert time.business_now() == datetime(2026,10,31,20,0)


def test_legacy_invoice_crosses_month_without_rewriting_original():
    recorded = datetime(2026,11,1,2,13,19)
    document = {'fecha':'31/10/2026','hora':'20:13:18'}
    evidence = time.invoice_time_evidence(recorded,document,datetime(2026,10,31,20,13,16))
    assert evidence['fecha'] == datetime(2026,10,31,20,13,18)
    assert evidence['fecha_bd'] == recorded and evidence['fecha_normalizada']


def test_no_evidence_does_not_guess_a_historical_timezone():
    original = datetime(2026,11,1,2)
    evidence = time.invoice_time_evidence(original,{'fecha':'31/10/2026','hora':'20:00:00'})
    assert evidence['fecha'] == original and evidence['fecha_por_revisar']
    assert not evidence['fecha_normalizada']


def test_broken_or_missing_receipt_retains_recorded_date():
    stamp = datetime(2026,10,31,20)
    for document in ({},None,[],{'fecha':'bad','hora':'bad'}):
        assert time.invoice_time_evidence(stamp,document)['fecha'] == stamp


def test_legacy_void_only_normalizes_with_corresponding_reversal():
    original = datetime(2026,11,1,2)
    reverse = datetime(2026,10,31,20)
    assert time.reversal_time_evidence(original,reverse) == reverse
    assert time.reversal_time_evidence(original,None) == original
