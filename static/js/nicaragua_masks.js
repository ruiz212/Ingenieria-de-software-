/**
 * nicaragua_masks.js
 * Máscaras interactivas y validaciones oficiales para Nicaragua.
 * - Cédula de Identidad: 000-000000-0000A (16 caracteres, letra oficial Módulo 23 del CSE).
 * - Teléfono Nacional: 0000-0000 (8 dígitos, prefijos válidos 2 para fijos, 5/7/8 para celulares).
 */

(function (window, document) {
    'use strict';

    const LETRAS_CEDULA = 'ABCDEFGHJKLMNPQRSTUVWXY';

    /**
     * Calcula la letra oficial de control de una cédula de Nicaragua (algoritmo CSE Módulo 23).
     * @param {string} digitos13 - Los primeros 13 dígitos numéricos.
     * @returns {string|null} - Letra verificadora en mayúscula o null si no son 13 dígitos.
     */
    function calcularLetraCedula(digitos13) {
        const clean = String(digitos13 || '').replace(/\D/g, '');
        if (clean.length !== 13) return null;
        try {
            const residuo = Number(BigInt(clean) % 23n);
            return LETRAS_CEDULA[residuo] || null;
        } catch (_) {
            return null;
        }
    }

    /**
     * Valida una cédula completa de Nicaragua.
     * @param {string} val
     * @returns {{valido: boolean, mensaje: string, letraEsperada: string|null, formateado: string}}
     */
    function validarCedula(val) {
        if (!val || typeof val !== 'string') {
            return { valido: false, mensaje: 'La cédula es obligatoria.', letraEsperada: null, formateado: '' };
        }
        const clean = val.replace(/[\s.-]/g, '').toUpperCase();
        if (clean.length !== 14) {
            return {
                valido: false,
                mensaje: 'La cédula debe tener 14 caracteres alfanuméricos (000-000000-0000A).',
                letraEsperada: null,
                formateado: val
            };
        }

        const digitos = clean.slice(0, 13);
        const letra = clean.slice(13);

        if (!/^\d{13}$/.test(digitos)) {
            return {
                valido: false,
                mensaje: 'Los primeros 13 caracteres deben ser números (municipio + fecha DDMMAA + serie).',
                letraEsperada: null,
                formateado: val
            };
        }

        const dia = parseInt(digitos.slice(3, 5), 10);
        const mes = parseInt(digitos.slice(5, 7), 10);

        if (dia < 1 || dia > 31) {
            return {
                valido: false,
                mensaje: `El día de nacimiento (${dia.toString().padStart(2, '0')}) en la cédula no es válido (01-31).`,
                letraEsperada: null,
                formateado: val
            };
        }

        if (mes < 1 || mes > 12) {
            return {
                valido: false,
                mensaje: `El mes de nacimiento (${mes.toString().padStart(2, '0')}) en la cédula no es válido (01-12).`,
                letraEsperada: null,
                formateado: val
            };
        }

        const letraEsperada = calcularLetraCedula(digitos);
        const formateado = `${digitos.slice(0, 3)}-${digitos.slice(3, 9)}-${digitos.slice(9, 13)}${letra}`;

        if (letra !== letraEsperada) {
            return {
                valido: false,
                mensaje: `Letra verificadora '${letra}' no coincide. Para estos dígitos corresponde la letra '${letraEsperada}'.`,
                letraEsperada,
                formateado
            };
        }

        return { valido: true, mensaje: '', letraEsperada, formateado };
    }

    /**
     * Valida un número telefónico de Nicaragua.
     * @param {string} val
     * @returns {{valido: boolean, mensaje: string, formateado: string, digitos: string}}
     */
    function validarTelefono(val) {
        if (!val || typeof val !== 'string') {
            return { valido: false, mensaje: 'El teléfono es obligatorio.', formateado: '', digitos: '' };
        }
        let digits = val.replace(/\D/g, '');
        if (digits.length === 11 && digits.startsWith('505')) {
            digits = digits.slice(3);
        } else if (digits.length === 10 && digits.startsWith('05')) {
            digits = digits.slice(2);
        }

        if (digits.length !== 8) {
            return {
                valido: false,
                mensaje: 'El teléfono debe tener exactamente 8 dígitos (formato 0000-0000).',
                formateado: val,
                digitos: digits
            };
        }

        const primerDigito = digits[0];
        if (!['2', '5', '7', '8'].includes(primerDigito)) {
            return {
                valido: false,
                mensaje: 'Número no válido en Nicaragua (debe iniciar con 2 para convencional, o 5, 7, 8 para celular).',
                formateado: val,
                digitos: digits
            };
        }

        const formateado = `${digits.slice(0, 4)}-${digits.slice(4, 8)}`;
        return { valido: true, mensaje: '', formateado, digitos };
    }

    /**
     * Aplica máscara de Cédula a un input HTML.
     */
    function attachCedulaMask(input) {
        if (!input || input.__nicaraguaCedulaMaskAttached) return;
        input.__nicaraguaCedulaMaskAttached = true;

        input.setAttribute('placeholder', '001-000000-0000A');
        input.setAttribute('maxlength', '16');
        input.setAttribute('autocomplete', 'off');
        input.setAttribute('autocapitalize', 'characters');
        input.setAttribute('spellcheck', 'false');

        // Formatea el valor actual si ya contiene datos
        function formatCedulaValue(raw) {
            const clean = String(raw || '').replace(/[\s.-]/g, '');
            const digitsOnly = clean.replace(/[^0-9]/g, '').slice(0, 13);
            let letter = clean.slice(digitsOnly.length).replace(/[^a-zA-Z]/g, '').slice(0, 1).toUpperCase();

            let result = '';
            if (digitsOnly.length > 0) {
                result += digitsOnly.slice(0, 3);
            }
            if (digitsOnly.length >= 3) {
                const middle = digitsOnly.slice(3, 9);
                if (middle.length > 0 || digitsOnly.length > 3) {
                    result += '-' + middle;
                }
            }
            if (digitsOnly.length >= 9) {
                const end = digitsOnly.slice(9, 13);
                if (end.length > 0 || digitsOnly.length > 9) {
                    result += '-' + end;
                }
            }

            // Si ya tiene los 13 dígitos y no hay letra, sugerir/calcular la letra oficial
            if (digitsOnly.length === 13) {
                if (!letter) {
                    letter = calcularLetraCedula(digitsOnly) || '';
                }
                result += letter;
            } else if (letter) {
                result += letter;
            }

            return result;
        }

        function validateInputState() {
            const val = input.value.trim();
            if (!val) {
                input.setCustomValidity(input.required ? 'La cédula es requerida.' : '');
                input.classList.remove('is-invalid', 'is-valid');
                return;
            }
            const res = validarCedula(val);
            if (res.valido) {
                input.setCustomValidity('');
                input.classList.remove('is-invalid');
                input.classList.add('is-valid');
                input.title = 'Cédula de identidad válida (CSE)';
            } else {
                // Solo marcar como inválido si el usuario ya escribió los 16 caracteres o perdió el foco
                if (val.length >= 16) {
                    input.setCustomValidity(res.mensaje);
                    input.classList.add('is-invalid');
                    input.classList.remove('is-valid');
                    input.title = res.mensaje;
                } else {
                    input.setCustomValidity('Complete la cédula (16 caracteres: 000-000000-0000A).');
                    input.classList.remove('is-valid');
                }
            }
        }

        input.addEventListener('input', function (e) {
            const start = input.selectionStart;
            const prevLen = input.value.length;
            const formatted = formatCedulaValue(input.value);
            input.value = formatted;

            // Mantener cursor en una posición intuitiva
            const newLen = formatted.length;
            if (start !== null) {
                const diff = newLen - prevLen;
                const newPos = Math.max(0, Math.min(newLen, start + diff));
                input.setSelectionRange(newPos, newPos);
            }

            validateInputState();
        });

        input.addEventListener('blur', function () {
            if (input.value.trim()) {
                input.value = formatCedulaValue(input.value);
                const res = validarCedula(input.value);
                if (!res.valido) {
                    input.setCustomValidity(res.mensaje);
                    input.classList.add('is-invalid');
                    input.classList.remove('is-valid');
                    input.title = res.mensaje;
                } else {
                    input.setCustomValidity('');
                    input.classList.remove('is-invalid');
                    input.classList.add('is-valid');
                }
            } else {
                input.classList.remove('is-invalid', 'is-valid');
                input.setCustomValidity(input.required ? 'La cédula es obligatoria.' : '');
            }
        });

        // Formatear si ya tiene valor inicial
        if (input.value.trim()) {
            input.value = formatCedulaValue(input.value);
            validateInputState();
        }
    }

    /**
     * Aplica máscara de Teléfono (Nicaragua: 0000-0000) a un input HTML.
     */
    function attachTelefonoMask(input) {
        if (!input || input.__nicaraguaTelefonoMaskAttached) return;
        input.__nicaraguaTelefonoMaskAttached = true;

        input.setAttribute('placeholder', '8888-8888');
        input.setAttribute('maxlength', '9');
        input.setAttribute('type', 'tel');
        input.setAttribute('inputmode', 'numeric');
        input.setAttribute('autocomplete', 'tel');

        function formatTelefonoValue(raw) {
            let digits = String(raw || '').replace(/\D/g, '');
            // Si el usuario pegó con prefijo internacional +505 o 505
            if (digits.length >= 10 && digits.startsWith('505')) {
                digits = digits.slice(3);
            }
            digits = digits.slice(0, 8);

            if (digits.length <= 4) {
                return digits;
            }
            return `${digits.slice(0, 4)}-${digits.slice(4, 8)}`;
        }

        function validateTelefonoState() {
            const val = input.value.trim();
            if (!val) {
                input.setCustomValidity(input.required ? 'El teléfono es requerido.' : '');
                input.classList.remove('is-invalid', 'is-valid');
                return;
            }
            const res = validarTelefono(val);
            if (res.valido) {
                input.setCustomValidity('');
                input.classList.remove('is-invalid');
                input.classList.add('is-valid');
                input.title = 'Número telefónico de Nicaragua válido';
            } else {
                if (val.length >= 9) {
                    input.setCustomValidity(res.mensaje);
                    input.classList.add('is-invalid');
                    input.classList.remove('is-valid');
                    input.title = res.mensaje;
                } else {
                    input.setCustomValidity('Complete los 8 dígitos del teléfono (0000-0000).');
                    input.classList.remove('is-valid');
                }
            }
        }

        input.addEventListener('input', function () {
            const start = input.selectionStart;
            const prevLen = input.value.length;
            const formatted = formatTelefonoValue(input.value);
            input.value = formatted;

            const newLen = formatted.length;
            if (start !== null) {
                const diff = newLen - prevLen;
                const newPos = Math.max(0, Math.min(newLen, start + diff));
                input.setSelectionRange(newPos, newPos);
            }

            validateTelefonoState();
        });

        input.addEventListener('blur', function () {
            if (input.value.trim()) {
                input.value = formatTelefonoValue(input.value);
                const res = validarTelefono(input.value);
                if (!res.valido) {
                    input.setCustomValidity(res.mensaje);
                    input.classList.add('is-invalid');
                    input.classList.remove('is-valid');
                    input.title = res.mensaje;
                } else {
                    input.setCustomValidity('');
                    input.classList.remove('is-invalid');
                    input.classList.add('is-valid');
                }
            } else {
                input.classList.remove('is-invalid', 'is-valid');
                input.setCustomValidity(input.required ? 'El teléfono es requerido.' : '');
            }
        });

        // Formatear si ya tiene valor inicial
        if (input.value.trim()) {
            input.value = formatTelefonoValue(input.value);
            validateTelefonoState();
        }
    }

    /**
     * Escanea el contenedor y aplica las máscaras correspondientes.
     */
    function scanAndApply(root) {
        const container = root || document;

        // Cédulas: inputs marcados explícitamente o por id/name (excluyendo filtros/búsqueda)
        const cedulaInputs = container.querySelectorAll(
            'input[data-mask="cedula"], input.mask-cedula, ' +
            'input#ne-cedula, input[name="cedula"]:not([type="search"])'
        );
        cedulaInputs.forEach(input => {
            const id = (input.id || '').toLowerCase();
            const name = (input.name || '').toLowerCase();
            if (id.includes('search') || id.includes('filtro') || id.includes('busqueda') ||
                name.includes('search') || name.includes('filtro')) {
                return;
            }
            attachCedulaMask(input);
        });

        // Teléfonos: inputs marcados explícitamente o por id/name/type (excluyendo filtros/búsqueda)
        const telefonoInputs = container.querySelectorAll(
            'input[data-mask="telefono"], input.mask-telefono, input[type="tel"], ' +
            'input#ne-telefono, input#cliente-telefono, input#prov_telefono, ' +
            'input#cfg-telefono_negocio, input#modal-telefono-cliente, input#pastel-telefono, ' +
            'input[name="telefono"], input[name="fiscal_telefono"]'
        );
        telefonoInputs.forEach(input => {
            const id = (input.id || '').toLowerCase();
            const name = (input.name || '').toLowerCase();
            if (id.includes('search') || id.includes('filtro') || id.includes('busqueda') || id.includes('buscador') ||
                name.includes('search') || name.includes('filtro') || name.includes('buscador')) {
                return;
            }
            attachTelefonoMask(input);
        });
    }

    // Inicialización automática
    function init() {
        scanAndApply(document);

        // Observer para detectar modales o inputs dinámicos en el DOM
        if (window.MutationObserver) {
            const observer = new MutationObserver(mutations => {
                for (const mutation of mutations) {
                    if (mutation.addedNodes.length > 0) {
                        for (const node of mutation.addedNodes) {
                            if (node.nodeType === 1) { // ELEMENT_NODE
                                scanAndApply(node);
                            }
                        }
                    }
                }
            });
            observer.observe(document.body, { childList: true, subtree: true });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Exportar API global
    window.NicaraguaMasks = {
        calcularLetraCedula,
        validarCedula,
        validarTelefono,
        attachCedulaMask,
        attachTelefonoMask,
        scan: scanAndApply,
        init
    };

})(window, document);
