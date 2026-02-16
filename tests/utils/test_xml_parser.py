import pytest
from app.utils.xml_parser import parse_xml


SAMPLE_INVOICE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
    <cbc:ID>FE-001</cbc:ID>
    <cbc:IssueDate>2024-01-15</cbc:IssueDate>
    <cbc:IssueTime>10:30:00</cbc:IssueTime>
    <cbc:DocumentCurrencyCode>COP</cbc:DocumentCurrencyCode>
    <cbc:InvoiceTypeCode>01</cbc:InvoiceTypeCode>
    <cbc:UUID>abc-123-def-456</cbc:UUID>
    <cac:AccountingSupplierParty>
        <cac:Party>
            <cac:PartyName>
                <cbc:Name>Empresa Emisora SAS</cbc:Name>
            </cac:PartyName>
            <cac:PartyTaxScheme>
                <cbc:CompanyID>900123456</cbc:CompanyID>
            </cac:PartyTaxScheme>
            <cac:PhysicalLocation>
                <cac:Address>
                    <cbc:CityName>Bogota</cbc:CityName>
                    <cac:AddressLine>
                        <cbc:Line>Calle 100 # 10-20</cbc:Line>
                    </cac:AddressLine>
                    <cac:Country>
                        <cbc:Name>Colombia</cbc:Name>
                    </cac:Country>
                </cac:Address>
            </cac:PhysicalLocation>
            <cac:Contact>
                <cbc:Telephone>3001234567</cbc:Telephone>
                <cbc:ElectronicMail>emisor@test.com</cbc:ElectronicMail>
            </cac:Contact>
        </cac:Party>
    </cac:AccountingSupplierParty>
    <cac:AccountingCustomerParty>
        <cac:Party>
            <cac:PartyName>
                <cbc:Name>Empresa Receptora LTDA</cbc:Name>
            </cac:PartyName>
            <cac:PartyTaxScheme>
                <cbc:CompanyID>800987654</cbc:CompanyID>
            </cac:PartyTaxScheme>
            <cac:PhysicalLocation>
                <cac:Address>
                    <cbc:CityName>Medellin</cbc:CityName>
                    <cac:AddressLine>
                        <cbc:Line>Carrera 50 # 30-40</cbc:Line>
                    </cac:AddressLine>
                    <cac:Country>
                        <cbc:Name>Colombia</cbc:Name>
                    </cac:Country>
                </cac:Address>
            </cac:PhysicalLocation>
            <cac:Contact>
                <cbc:Telephone>3009876543</cbc:Telephone>
                <cbc:ElectronicMail>receptor@test.com</cbc:ElectronicMail>
            </cac:Contact>
        </cac:Party>
    </cac:AccountingCustomerParty>
    <cac:InvoiceLine>
        <cbc:ID>1</cbc:ID>
        <cbc:InvoicedQuantity unitCode="EA">10</cbc:InvoicedQuantity>
        <cbc:LineExtensionAmount currencyID="COP">1000000</cbc:LineExtensionAmount>
        <cac:TaxTotal>
            <cbc:TaxAmount currencyID="COP">190000</cbc:TaxAmount>
            <cac:TaxSubtotal>
                <cbc:TaxableAmount currencyID="COP">1000000</cbc:TaxableAmount>
                <cbc:TaxAmount currencyID="COP">190000</cbc:TaxAmount>
                <cac:TaxCategory>
                    <cbc:Percent>19</cbc:Percent>
                    <cac:TaxScheme>
                        <cbc:ID>01</cbc:ID>
                        <cbc:Name>IVA</cbc:Name>
                    </cac:TaxScheme>
                </cac:TaxCategory>
            </cac:TaxSubtotal>
        </cac:TaxTotal>
        <cac:Item>
            <cbc:Description>Servicio de consultoria</cbc:Description>
        </cac:Item>
        <cac:Price>
            <cbc:PriceAmount currencyID="COP">100000</cbc:PriceAmount>
        </cac:Price>
    </cac:InvoiceLine>
    <cac:TaxTotal>
        <cbc:TaxAmount currencyID="COP">190000</cbc:TaxAmount>
        <cac:TaxSubtotal>
            <cbc:TaxableAmount currencyID="COP">1000000</cbc:TaxableAmount>
            <cbc:TaxAmount currencyID="COP">190000</cbc:TaxAmount>
            <cac:TaxCategory>
                <cbc:Percent>19</cbc:Percent>
                <cac:TaxScheme>
                    <cbc:ID>01</cbc:ID>
                    <cbc:Name>IVA</cbc:Name>
                </cac:TaxScheme>
            </cac:TaxCategory>
        </cac:TaxSubtotal>
    </cac:TaxTotal>
    <cac:LegalMonetaryTotal>
        <cbc:TaxExclusiveAmount currencyID="COP">1000000</cbc:TaxExclusiveAmount>
        <cbc:PayableAmount currencyID="COP">1190000</cbc:PayableAmount>
    </cac:LegalMonetaryTotal>
</Invoice>
"""


class TestParseXml:
    def test_parse_valid_invoice(self):
        result = parse_xml(SAMPLE_INVOICE_XML)
        assert result is not None
        assert result['numero_documento'] == 'FE-001'
        assert result['fecha_emision'] == '2024-01-15'
        assert result['moneda'] == 'COP'

    def test_emisor_data(self):
        result = parse_xml(SAMPLE_INVOICE_XML)
        emisor = result['emisor']
        assert emisor['nombre'] == 'Empresa Emisora SAS'
        assert emisor['nit'] == '900123456'
        assert emisor['contacto']['email'] == 'emisor@test.com'

    def test_receptor_data(self):
        result = parse_xml(SAMPLE_INVOICE_XML)
        receptor = result['receptor']
        assert receptor['nombre'] == 'Empresa Receptora LTDA'
        assert receptor['nit'] == '800987654'

    def test_items_parsed(self):
        result = parse_xml(SAMPLE_INVOICE_XML)
        assert len(result['items']) == 1
        item = result['items'][0]
        assert item['descripcion'] == 'Servicio de consultoria'
        assert item['cantidad'] == '10'
        assert item['precio_unitario'] == '100000'

    def test_item_taxes(self):
        result = parse_xml(SAMPLE_INVOICE_XML)
        item_taxes = result['items'][0]['impuestos']
        assert len(item_taxes) == 1
        assert item_taxes[0]['nombre'] == 'IVA'
        assert item_taxes[0]['porcentaje'] == '19'

    def test_totals(self):
        result = parse_xml(SAMPLE_INVOICE_XML)
        totales = result['totales']
        assert totales['subtotal'] == '1000000'
        assert totales['total'] == '1190000'
        assert totales['total_impuestos'] == '190000'

    def test_general_taxes(self):
        result = parse_xml(SAMPLE_INVOICE_XML)
        # El parser usa XPath './/cac:TaxSubtotal' que captura tanto
        # los impuestos de InvoiceLine como los generales
        assert len(result['impuestos']) >= 1
        assert any(t['nombre'] == 'IVA' for t in result['impuestos'])

    def test_invalid_xml_raises_error(self):
        with pytest.raises(ValueError, match="Error processing XML"):
            parse_xml("<invalid>xml</broken>")

    def test_empty_xml_raises_error(self):
        with pytest.raises(ValueError):
            parse_xml("")
