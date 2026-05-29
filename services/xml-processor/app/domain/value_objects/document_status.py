class DocumentStatus:
    ERROR = 0
    PROCESADO = 100
    CAUSADO = 200
    APROBADO = 300
    CONTABILIZADA = 400

    NAMES = {
        0: "Error",
        100: "Procesado",
        200: "Causado",
        300: "Aprobado",
        400: "Contabilizada",
    }
