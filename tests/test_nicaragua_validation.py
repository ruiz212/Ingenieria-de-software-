"""
Pruebas unitarias y de integración para validaciones y formatos de Nicaragua:
- Cédula de Identidad (###-######-####@) con fecha y letra Módulo 23 CSE.
- Teléfonos nacionales (####-####, prefijos válidos 2, 5, 7, 8 y soporte +505).
"""
import pytest
from app.services.validation import (
    validate_cedula_nicaragua,
    validate_telefono_nicaragua,
    calcular_letra_cedula_nicaragua,
    LETRAS_CEDULA_NICARAGUA,
)


def test_calcular_letra_cedula_cse():
    """Valida el algoritmo oficial Módulo 23 del Consejo Supremo Electoral."""
    assert len(LETRAS_CEDULA_NICARAGUA) == 23
    assert 'I' not in LETRAS_CEDULA_NICARAGUA
    assert 'O' not in LETRAS_CEDULA_NICARAGUA
    assert 'Z' not in LETRAS_CEDULA_NICARAGUA

    # Prueba con 13 dígitos conocidos
    # 0010101900001 % 23 = 10101900001 % 23 = 12 -> LETRAS[12] = 'N'
    letra = calcular_letra_cedula_nicaragua('0010101900001')
    assert letra == 'N'

    # Error si no son 13 dígitos
    with pytest.raises(ValueError):
        calcular_letra_cedula_nicaragua('123')


def test_cedula_formatos_validos():
    """Valida cédulas con guiones, sin guiones, minúsculas y espacios."""
    # Con guiones
    res1 = validate_cedula_nicaragua('001-010190-0001A')
    assert res1 == '001-010190-0001A'

    # Sin guiones
    res2 = validate_cedula_nicaragua('0010101900001a')
    assert res2 == '001-010190-0001A'

    # Con espacios y puntos
    res3 = validate_cedula_nicaragua(' 001.010190.0001b ')
    assert res3 == '001-010190-0001B'


def test_cedula_errores_formato():
    """Valida rechazo de cédulas con longitud o componentes inválidos."""
    # Longitud incorrecta
    with pytest.raises(ValueError, match="14 caracteres alfanuméricos"):
        validate_cedula_nicaragua('001-010190-001A')

    with pytest.raises(ValueError, match="14 caracteres alfanuméricos"):
        validate_cedula_nicaragua('001-010190-000001A')

    # No tiene números en los primeros 13 caracteres
    with pytest.raises(ValueError, match="primeros 13 caracteres deben ser números"):
        validate_cedula_nicaragua('00A-010190-0001A')

    # Último carácter no es letra
    with pytest.raises(ValueError, match="último carácter debe ser una letra válida"):
        validate_cedula_nicaragua('001-010190-00019')

    # Día de nacimiento inválido (> 31)
    with pytest.raises(ValueError, match="día de nacimiento"):
        validate_cedula_nicaragua('001-320190-0001A')

    # Día de nacimiento inválido (00)
    with pytest.raises(ValueError, match="día de nacimiento"):
        validate_cedula_nicaragua('001-000190-0001A')

    # Mes de nacimiento inválido (> 12)
    with pytest.raises(ValueError, match="mes de nacimiento"):
        validate_cedula_nicaragua('001-151390-0001A')

    # Mes de nacimiento inválido (00)
    with pytest.raises(ValueError, match="mes de nacimiento"):
        validate_cedula_nicaragua('001-150090-0001A')


def test_cedula_checksum_estricto():
    """Valida la verificación estricta de letra de cédula cuando verify_checksum=True."""
    # 0010101900001 tiene letra esperada 'N'
    cedula_correcta = '001-010190-0001N'
    assert validate_cedula_nicaragua(cedula_correcta, verify_checksum=True) == '001-010190-0001N'

    # Letra equivocada
    with pytest.raises(ValueError, match="no coincide con el dígito verificador oficial"):
        validate_cedula_nicaragua('001-010190-0001A', verify_checksum=True)


def test_telefono_formatos_validos():
    """Valida números telefónicos estándar de Nicaragua con prefijos 2, 5, 7, 8."""
    # Fijo (prefijo 2)
    assert validate_telefono_nicaragua('2255-8888') == '2255-8888'
    assert validate_telefono_nicaragua('22558888') == '2255-8888'

    # Celulares (prefijos 5, 7, 8)
    assert validate_telefono_nicaragua('5500-1122') == '5500-1122'
    assert validate_telefono_nicaragua('7799-3344') == '7799-3344'
    assert validate_telefono_nicaragua('8888-1234') == '8888-1234'

    # Con prefijo internacional +505
    assert validate_telefono_nicaragua('+505 8888-1234') == '8888-1234'
    assert validate_telefono_nicaragua('+50588881234') == '8888-1234'
    assert validate_telefono_nicaragua('505 2270-0000') == '2270-0000'

    # En modo as_digits=True
    assert validate_telefono_nicaragua('8888-1234', as_digits=True) == '88881234'
    assert validate_telefono_nicaragua('+505 2255-8888', as_digits=True) == '22558888'


def test_telefono_errores_formato():
    """Valida rechazo de números telefónicos con longitud o prefijo no nicaragüense."""
    # Prefijo inválido (no 2, 5, 7, 8)
    for invalid_prefix in ['1234-5678', '3344-5566', '4411-2233', '6600-1122', '9988-7766']:
        with pytest.raises(ValueError, match="prefijo no válido en Nicaragua"):
            validate_telefono_nicaragua(invalid_prefix)

    # Longitud incorrecta
    with pytest.raises(ValueError, match="exactamente 8 dígitos"):
        validate_telefono_nicaragua('888-1234')

    with pytest.raises(ValueError, match="exactamente 8 dígitos"):
        validate_telefono_nicaragua('88888-1234')


def test_campos_opcionales():
    """Valida que optional=True permita None o vacío."""
    assert validate_cedula_nicaragua(None, optional=True) is None
    assert validate_cedula_nicaragua('', optional=True) is None
    assert validate_telefono_nicaragua(None, optional=True) == ''
    assert validate_telefono_nicaragua('', optional=True) == ''
    assert validate_telefono_nicaragua(None, optional=True, as_digits=True) is None

    # Si optional=False, rechaza vacío
    with pytest.raises(ValueError, match="Cédula: es obligatoria"):
        validate_cedula_nicaragua('')

    with pytest.raises(ValueError, match="Teléfono: es obligatorio"):
        validate_telefono_nicaragua('')



def test_api_crear_empleado_validaciones(monkeypatch):
    """Verifica que el endpoint de creación de empleado rechace cédulas o teléfonos no nicaragüenses."""
    from app import create_app
    from app.models import User
    from app.admin import routes_hr
    from datetime import datetime

    monkeypatch.setattr(routes_hr, 'business_now', lambda: datetime(2026, 10, 25, 14, 0, 0))

    app = create_app()
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False

    admin_user = User(
        id=1,
        username='admin_test',
        nombre_completo='Administrador Test',
        rol_id=1,
        rol_nombre='SuperAdmin',
    )

    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess['_user_id'] = '1'
        monkeypatch.setattr('flask_login.utils._get_user', lambda: admin_user)

        # 1. Cédula inválida (longitud incorrecta o formato no nicaragüense)
        resp1 = client.post('/admin/api/rrhh/empleado', json={
            'nombre': 'Prueba Validacion',
            'cedula': '123456',  # Inválida
            'telefono': '8888-8888',
            'cargo': 'Panadero',
            'fecha_ingreso': '2026-10-01',
            'salario_base': 8000,
        })
        assert resp1.status_code == 400
        assert 'formato de Nicaragua' in resp1.get_json()['error']

        # 2. Cédula con día inválido
        resp2 = client.post('/admin/api/rrhh/empleado', json={
            'nombre': 'Prueba Validacion',
            'cedula': '001-350190-0001A',  # Día 35 inválido
            'telefono': '8888-8888',
            'cargo': 'Panadero',
            'fecha_ingreso': '2026-10-01',
            'salario_base': 8000,
        })
        assert resp2.status_code == 400
        assert 'día de nacimiento' in resp2.get_json()['error']

        # 3. Teléfono con prefijo inválido en Nicaragua
        resp3 = client.post('/admin/api/rrhh/empleado', json={
            'nombre': 'Prueba Validacion',
            'cedula': '001-010190-0001A',
            'telefono': '4444-5555',  # Inválido en Nicaragua
            'cargo': 'Panadero',
            'fecha_ingreso': '2026-10-01',
            'salario_base': 8000,
        })
        assert resp3.status_code == 400
        assert 'prefijo no válido en Nicaragua' in resp3.get_json()['error']
