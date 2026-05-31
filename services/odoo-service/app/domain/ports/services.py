from abc import ABC, abstractmethod


class OdooClientPort(ABC):
    @abstractmethod
    def search_moves(self, date_from: str, date_to: str) -> list[dict]:
        """Busca todos los asientos contables en el rango de fechas dado."""

    @abstractmethod
    def get_move_lines(self, move_ids: list[int]) -> list[dict]:
        """Retorna las líneas contables de los asientos indicados."""

    @abstractmethod
    def get_partner_details(self, partner_ids: list[int]) -> dict[int, dict]:
        """Retorna información del tercero incluyendo NIT/VAT."""

    @abstractmethod
    def get_account_details(self, account_ids: list[int]) -> dict[int, dict]:
        """Retorna código y nombre de las cuentas contables."""

    @abstractmethod
    def get_analytic_account_details(self, analytic_ids: list[int]) -> dict[int, dict]:
        """Retorna nombre de las cuentas analíticas (centros de costo)."""
