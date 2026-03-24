def dv_calculate(nit: str) -> int:
    """
    Calcula el dígito de verificación (DV) de un NIT según las reglas de la DIAN en Colombia.
    
    :param nit: NIT como cadena de dígitos, sin el dígito de verificación.
    :return: Dígito de verificación (0-9)
    """
    pesos = [71, 67, 59, 53, 47, 43, 41, 37, 29, 23, 19, 17, 13, 7, 3]
    nit = ''.join(filter(str.isdigit, nit))
    suma = 0

    # Aplicar los pesos desde la derecha del NIT hacia la izquierda
    for i, digito in enumerate(reversed(nit)):
        peso = pesos[-(i+1)]
        suma += int(digito) * peso

    residuo = suma % 11
    return 0 if residuo < 2 else 11 - residuo
