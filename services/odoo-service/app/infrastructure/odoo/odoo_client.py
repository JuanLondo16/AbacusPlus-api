import logging
import socket
import xmlrpc.client

from app.domain.exceptions.base import OdooConnectionException
from app.domain.ports.services import OdooClientPort

logger = logging.getLogger(__name__)


class OdooXmlRpcClient(OdooClientPort):
    """
    Cliente XML-RPC para Odoo 17.
    Extrae facturas de compra publicadas (move_type = in_invoice).
    """

    def __init__(self, url: str, db: str, username: str, password: str, timeout: int = 1200):
        self._db = db
        self._password = password
        try:
            socket.setdefaulttimeout(timeout)
            common = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/common")
            self._uid = common.authenticate(db, username, password, {})
            if not self._uid:
                raise OdooConnectionException(
                    "Autenticación fallida. Verifique ODOO_USER y ODOO_PASSWORD."
                )
            self._models = xmlrpc.client.ServerProxy(f"{url}/xmlrpc/2/object")
            logger.info("Conexión Odoo XML-RPC establecida (uid=%s)", self._uid)
        except OdooConnectionException:
            raise
        except Exception as exc:
            raise OdooConnectionException(f"No se pudo conectar a Odoo: {exc}") from exc

    def _call(self, model: str, method: str, args, kwargs=None):
        return self._models.execute_kw(
            self._db,
            self._uid,
            self._password,
            model,
            method,
            args,
            kwargs or {},
        )

    def search_moves(self, date_from: str, date_to: str) -> list[dict]:
        """
        Busca facturas de compra publicadas en el rango de fechas dado.
        """
        domain = [
            ["state", "=", "posted"],
            ["move_type", "=", "in_invoice"],
            ["date", ">=", date_from],
            ["date", "<=", date_to],
        ]
        move_ids = self._call("account.move", "search", [domain])
        if not move_ids:
            return []

        moves = self._call(
            "account.move",
            "read",
            [move_ids],
            {
                "fields": [
                    "name",
                    "date",
                    "ref",
                    "move_type",
                    "state",
                    "journal_id",
                    "partner_id",
                    "currency_id",
                    "amount_untaxed",
                    "amount_tax",
                    "amount_total",
                    "narration",
                ]
            },
        )
        logger.info("Odoo: %d asientos encontrados (%s → %s)", len(moves), date_from, date_to)
        return moves

    def get_move_lines(self, move_ids: list[int]) -> list[dict]:
        """
        Retorna todas las líneas contables de los asientos indicados,
        excluyendo líneas de sección y nota (sin cuenta contable).
        """
        domain = [
            ["move_id", "in", move_ids],
            ["display_type", "not in", ["line_section", "line_note"]],
        ]
        line_ids = self._call("account.move.line", "search", [domain])
        if not line_ids:
            return []

        lines = self._call(
            "account.move.line",
            "read",
            [line_ids],
            {
                "fields": [
                    "move_id",
                    "sequence",
                    "account_id",
                    "partner_id",
                    "name",
                    "debit",
                    "credit",
                    "amount_currency",
                    "analytic_distribution",
                    "date_maturity",
                    "display_type",
                ]
            },
        )
        logger.info("Odoo: %d líneas obtenidas para %d asientos", len(lines), len(move_ids))
        return lines

    def get_partner_details(self, partner_ids: list[int]) -> dict[int, dict]:
        """Retorna nombre y VAT/NIT de los terceros indicados."""
        if not partner_ids:
            return {}
        partners = self._call(
            "res.partner",
            "read",
            [partner_ids],
            {"fields": ["name", "vat"]},
        )
        return {p["id"]: p for p in partners}

    def get_account_details(self, account_ids: list[int]) -> dict[int, dict]:
        """Retorna código y nombre de las cuentas contables."""
        if not account_ids:
            return {}
        accounts = self._call(
            "account.account",
            "read",
            [account_ids],
            {"fields": ["code", "name"]},
        )
        return {a["id"]: a for a in accounts}

    def get_analytic_account_details(self, analytic_ids: list[int]) -> dict[int, dict]:
        """Retorna nombre y plan de las cuentas analíticas (centros de costo) en Odoo 17."""
        if not analytic_ids:
            return {}
        accounts = self._call(
            "account.analytic.account",
            "read",
            [analytic_ids],
            {"fields": ["name", "plan_id"]},
        )
        return {a["id"]: a for a in accounts}
