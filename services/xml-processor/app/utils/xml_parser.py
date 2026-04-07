from typing import Optional
import xml.etree.ElementTree as ET


# UBL 2.1 DIAN namespaces
_NS = {
    'ext': 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2',
    'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
    'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
    'sts': 'dian:gov:co:facturaelectronica:Structures-2-1',
    '': 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2',
}

_PAYMENT_MEANS = {
    '1': 'Instrumento no definido',
    '10': 'Efectivo',
    '20': 'Cheque',
    '21': 'Cheque certificado',
    '31': 'Transferencia crédito bancaria',
    '42': 'Pago por compensación de deudas',
    '47': 'Transferencia bancaria débito',
    '48': 'Tarjeta de crédito',
    '49': 'Tarjeta débito',
    'ZZZ': 'Acuerdo mutuo',
}

_SCHEME_ID = {
    '11': 'Registro civil',
    '12': 'Tarjeta de identidad',
    '13': 'Cédula de ciudadanía',
    '21': 'Tarjeta de extranjería',
    '22': 'Cédula de extranjería',
    '31': 'NIT',
    '41': 'Pasaporte',
    '50': 'NIT de otro país',
    '91': 'NUIP',
}

_TAX_SCHEME = {
    '01': 'IVA',
    '04': 'INC',
    '06': 'ReteRenta',
    '07': 'ReteICA',
    '08': 'ReteIVA',
    '22': 'INC Bolsas',
    'ZZ': 'No aplica',
}

_INVOICE_TYPE = {
    '01': 'Factura de venta',
    '02': 'Factura de exportación',
    '03': 'Factura por contingencia facturador',
}

_PERSON_TYPE = {
    '1': 'Persona jurídica',
    '2': 'Persona natural',
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _text(node, xpath: str) -> Optional[str]:
    """Return stripped text of the first element matched by xpath, or None."""
    if node is None:
        return None
    el = node.find(xpath, _NS)
    return el.text.strip() if el is not None and el.text else None


def _parse_party(party_node, additional_account_id: Optional[str]) -> dict:
    """Build a party dict from a cac:Party node (emisor or receptor)."""
    if party_node is None:
        return {}

    # Name: try multiple locations in priority order
    nombre = None
    for path in (
        './/cac:PartyName/cbc:Name',
        './/cac:PartyTaxScheme/cbc:RegistrationName',
        './/cac:PartyLegalEntity/cbc:RegistrationName',
    ):
        nombre = _text(party_node, path)
        if nombre:
            break

    # Company/person ID — prefer PartyTaxScheme/CompanyID, fallback to PartyIdentification/ID
    id_el = party_node.find('.//cac:PartyTaxScheme/cbc:CompanyID', _NS)
    if id_el is None or not (id_el.text or '').strip():
        id_el = party_node.find('.//cac:PartyIdentification/cbc:ID', _NS)

    nit = id_el.text.strip() if id_el is not None and id_el.text else None
    scheme_id = id_el.attrib.get('schemeID') if id_el is not None else None

    return {
        'nombre': nombre,
        'nit': nit,
        'tipo_identificacion': _SCHEME_ID.get(scheme_id, scheme_id),
        'tipo_persona': _PERSON_TYPE.get(additional_account_id, additional_account_id),
        'regimen': _text(party_node, './/cac:PartyTaxScheme/cbc:TaxLevelCode'),
        'direccion': {
            'ciudad': _text(party_node, './/cac:PhysicalLocation/cac:Address/cbc:CityName'),
            'departamento': _text(party_node, './/cac:PhysicalLocation/cac:Address/cbc:CountrySubentity'),
            'linea': _text(party_node, './/cac:PhysicalLocation/cac:Address/cac:AddressLine/cbc:Line'),
            'pais': _text(party_node, './/cac:PhysicalLocation/cac:Address/cac:Country/cbc:Name'),
        },
        'contacto': {
            'nombre': _text(party_node, './/cac:Contact/cbc:Name'),
            'telefono': _text(party_node, './/cac:Contact/cbc:Telephone'),
            'email': _text(party_node, './/cac:Contact/cbc:ElectronicMail'),
        },
    }


def _parse_tax_subtotals(tax_total_node) -> list:
    """
    Extract tax subtotals from a TaxTotal or WithholdingTaxTotal node.

    Handles both percentage-based taxes (IVA, ReteRenta, ReteICA) and
    per-unit taxes (INC Bolsas / TaxScheme 22) where cbc:Percent is absent.
    """
    taxes = []
    for sub in tax_total_node.findall('cac:TaxSubtotal', _NS):
        scheme_id = _text(sub, 'cac:TaxCategory/cac:TaxScheme/cbc:ID')
        percent_el = sub.find('cac:TaxCategory/cbc:Percent', _NS)
        per_unit_el = sub.find('cbc:PerUnitAmount', _NS)
        taxes.append({
            'codigo': scheme_id,
            'nombre': _text(sub, 'cac:TaxCategory/cac:TaxScheme/cbc:Name') or _TAX_SCHEME.get(scheme_id),
            'porcentaje': percent_el.text.strip() if percent_el is not None and percent_el.text else None,
            'valor_por_unidad': per_unit_el.text.strip() if per_unit_el is not None and per_unit_el.text else None,
            'base_imponible': _text(sub, 'cbc:TaxableAmount'),
            'valor': _text(sub, 'cbc:TaxAmount'),
        })
    return taxes


def _parse_allowance_charges(node) -> list:
    """
    Extract AllowanceCharge entries (descuentos / cargos) from a node.

    ChargeIndicator=false → descuento
    ChargeIndicator=true  → cargo adicional
    """
    result = []
    for ac in node.findall('cac:AllowanceCharge', _NS):
        charge_el = ac.find('cbc:ChargeIndicator', _NS)
        is_charge = charge_el is not None and (charge_el.text or '').strip().lower() == 'true'
        result.append({
            'tipo': 'cargo' if is_charge else 'descuento',
            'razon': _text(ac, 'cbc:AllowanceChargeReason'),
            'porcentaje': _text(ac, 'cbc:MultiplierFactorNumeric'),
            'valor': _text(ac, 'cbc:Amount'),
            'base': _text(ac, 'cbc:BaseAmount'),
        })
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_xml(xml_content: str) -> dict:
    """Parse a DIAN UBL 2.1 electronic invoice XML and return structured data.

    Handles all known DIAN invoice variants documented in samples/xml/README.md:
      - Standard invoice with IVA
      - Mixed IVA (taxed + exempt lines on the same invoice)
      - Line-level discounts (cac:AllowanceCharge, ChargeIndicator=false)
      - Plastic bag tax / INC Bolsas (TaxScheme 22, PerUnitAmount, no Percent)
      - Withholding taxes (cac:WithholdingTaxTotal: ReteRenta ID=06, ReteICA ID=07)
      - No-IVA invoices (cac:TaxTotal absent)
      - Public utility invoices (unitCode=MTQ, PayableRoundingAmount)
      - Invoices with many lines (20+)

    Args:
        xml_content: Raw XML content as str or bytes.

    Returns:
        Dictionary with keys: cufe, numero_documento, fecha_emision, hora_emision,
        fecha_vencimiento, moneda, tipo_documento, notas, emisor, receptor,
        pago, items, impuestos, retenciones, totales.

    Raises:
        ValueError: If the XML is malformed or required fields are missing.
    """
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as exc:
        raise ValueError(f"XML malformado: {exc}") from exc

    try:
        # Unwrap AttachedDocument → extract inner Invoice from CDATA
        if root.tag.endswith('AttachedDocument'):
            attachment = root.find(
                './/cac:Attachment/cac:ExternalReference/cbc:Description', _NS
            )
            if attachment is not None and attachment.text:
                try:
                    root = ET.fromstring(attachment.text.strip())
                except ET.ParseError as exc:
                    raise ValueError(f"XML interno (Invoice) malformado: {exc}") from exc

        for prefix, uri in _NS.items():
            ET.register_namespace(prefix, uri)

        # --- CUFE ---
        # Prefer UUID with schemeName starting with "CUFE"; fall back to first UUID.
        cufe = None
        for uuid_el in root.iter('{urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2}UUID'):
            if uuid_el.attrib.get('schemeName', '').upper().startswith('CUFE'):
                cufe = (uuid_el.text or '').strip() or None
                break
        if cufe is None:
            uuid_el = root.find('.//cbc:UUID', _NS)
            cufe = (uuid_el.text or '').strip() or None if uuid_el is not None else None

        # --- Header ---
        invoice_type_code = _text(root, 'cbc:InvoiceTypeCode')

        data: dict = {
            'cufe': cufe,
            'numero_documento': _text(root, 'cbc:ID'),
            'fecha_emision': _text(root, 'cbc:IssueDate'),
            'hora_emision': _text(root, 'cbc:IssueTime'),
            'fecha_vencimiento': _text(root, 'cbc:DueDate'),
            'moneda': _text(root, 'cbc:DocumentCurrencyCode'),
            'tipo_documento': {
                'codigo': invoice_type_code,
                'nombre': _INVOICE_TYPE.get(invoice_type_code, invoice_type_code),
            },
            'notas': [
                el.text.strip()
                for el in root.findall('cbc:Note', _NS)
                if el.text and el.text.strip()
            ],
        }

        # --- Parties ---
        supplier_node = root.find('cac:AccountingSupplierParty', _NS)
        customer_node = root.find('cac:AccountingCustomerParty', _NS)

        data['emisor'] = _parse_party(
            supplier_node.find('cac:Party', _NS) if supplier_node is not None else None,
            _text(supplier_node, 'cbc:AdditionalAccountID') if supplier_node is not None else None,
        )
        data['receptor'] = _parse_party(
            customer_node.find('cac:Party', _NS) if customer_node is not None else None,
            _text(customer_node, 'cbc:AdditionalAccountID') if customer_node is not None else None,
        )

        # --- Payment ---
        pm = root.find('cac:PaymentMeans', _NS)
        if pm is not None:
            code = _text(pm, 'cbc:PaymentMeansCode')
            due = _text(pm, 'cbc:PaymentDueDate') or data['fecha_vencimiento']
            data['pago'] = {
                'codigo': code,
                'medio_pago': _PAYMENT_MEANS.get(code, code),
                'fecha_vencimiento': due,
            }
        else:
            data['pago'] = None

        # --- Invoice Lines ---
        data['items'] = []
        for line in root.findall('cac:InvoiceLine', _NS):
            qty_el = line.find('cbc:InvoicedQuantity', _NS)
            price_el = line.find('cac:Price/cbc:PriceAmount', _NS)
            free_el = line.find('cbc:FreeOfChargeIndicator', _NS)
            is_free = free_el is not None and (free_el.text or '').strip().lower() == 'true'

            # Per-line taxes: only from direct cac:TaxTotal children of this line
            line_taxes = []
            for tax_total in line.findall('cac:TaxTotal', _NS):
                line_taxes.extend(_parse_tax_subtotals(tax_total))

            # Per-line discounts / surcharges
            line_charges = _parse_allowance_charges(line)

            data['items'].append({
                'id': _text(line, 'cbc:ID'),
                'descripcion': _text(line, 'cac:Item/cbc:Description'),
                'cantidad': qty_el.text.strip() if qty_el is not None and qty_el.text else None,
                'unidad_medida': qty_el.attrib.get('unitCode') if qty_el is not None else None,
                'precio_unitario': price_el.text.strip() if price_el is not None and price_el.text else None,
                'valor_total': _text(line, 'cbc:LineExtensionAmount'),
                'gratis': is_free,
                'impuestos': line_taxes,
                'descuentos_cargos': line_charges or None,
            })

        # --- Document-level taxes: IVA, INC Bolsas (cac:TaxTotal) ---
        # Use direct children only to avoid picking up per-line TaxTotals.
        data['impuestos'] = []
        for tax_total in root.findall('cac:TaxTotal', _NS):
            data['impuestos'].extend(_parse_tax_subtotals(tax_total))

        # --- Document-level withholding taxes: ReteRenta, ReteICA ---
        data['retenciones'] = []
        for wh_total in root.findall('cac:WithholdingTaxTotal', _NS):
            data['retenciones'].extend(_parse_tax_subtotals(wh_total))

        # --- Totals ---
        lt = root.find('cac:LegalMonetaryTotal', _NS)
        # Sumar TaxAmount de todos los TaxTotal a nivel de documento (ej. IVA + INC Bolsas)
        total_impuestos = sum(
            float(tt.findtext('cbc:TaxAmount', '0', _NS) or 0)
            for tt in root.findall('cac:TaxTotal', _NS)
        )
        rounding_el = lt.find('cbc:PayableRoundingAmount', _NS) if lt is not None else None

        data['totales'] = {
            'valor_lineas': _text(lt, 'cbc:LineExtensionAmount'),
            'subtotal': _text(lt, 'cbc:TaxExclusiveAmount'),
            'total_impuestos': str(total_impuestos) if total_impuestos else '0',
            'total_con_impuestos': _text(lt, 'cbc:TaxInclusiveAmount'),
            'redondeo': rounding_el.text.strip() if rounding_el is not None and rounding_el.text else None,
            'total': _text(lt, 'cbc:PayableAmount'),
        }

        return data

    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Error procesando XML: {exc}") from exc
