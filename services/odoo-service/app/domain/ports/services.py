from abc import ABC, abstractmethod
from typing import List, Dict


class OdooClientPort(ABC):

    @abstractmethod
    def search_moves(self, date_from: str, date_to: str) -> List[dict]:
        """Busca todos los asientos contables en el rango de fechas dado."""

    @abstractmethod
    def get_move_lines(self, move_ids: List[int]) -> List[dict]:
        """Retorna las líneas contables de los asientos indicados."""

    @abstractmethod
    def get_partner_details(self, partner_ids: List[int]) -> Dict[int, dict]:
        """Retorna información del tercero incluyendo NIT/VAT."""

    @abstractmethod
    def get_account_details(self, account_ids: List[int]) -> Dict[int, dict]:
        """Retorna código y nombre de las cuentas contables."""

    @abstractmethod
    def get_analytic_account_details(self, analytic_ids: List[int]) -> Dict[int, dict]:
        """Retorna nombre de las cuentas analíticas (centros de costo)."""
