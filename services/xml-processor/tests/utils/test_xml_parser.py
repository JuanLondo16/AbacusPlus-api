"""Tests for app/utils/xml_parser.py.

Each fixture XML mirrors a real scenario documented in samples/xml/README.md.
"""

import pytest
from app.utils.xml_parser import parse_xml

# ---------------------------------------------------------------------------
# Fixture XMLs
# ---------------------------------------------------------------------------

# Base invoice: IVA 19%, one line, CUFE, payment means
_BASE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
    <cbc:ID>FE-001</cbc:ID>
    <cbc:UUID schemeName="CUFE-SHA384">cufe-abc-123</cbc:UUID>
    <cbc:IssueDate>2024-01-15</cbc:IssueDate>
    <cbc:IssueTime>10:30:00</cbc:IssueTime>
    <cbc:DueDate>2024-02-15</cbc:DueDate>
    <cbc:DocumentCurrencyCode>COP</cbc:DocumentCurrencyCode>
    <cbc:InvoiceTypeCode>01</cbc:InvoiceTypeCode>
    <cbc:Note>Nota de prueba</cbc:Note>
    <cac:AccountingSupplierParty>
        <cbc:AdditionalAccountID>1</cbc:AdditionalAccountID>
        <cac:Party>
            <cac:PartyName><cbc:Name>Empresa Emisora SAS</cbc:Name></cac:PartyName>
            <cac:PartyTaxScheme>
                <cbc:CompanyID schemeID="31">900123456</cbc:CompanyID>
                <cbc:TaxLevelCode>R-99-PN</cbc:TaxLevelCode>
                <cac:TaxScheme><cbc:ID>01</cbc:ID><cbc:Name>IVA</cbc:Name></cac:TaxScheme>
            </cac:PartyTaxScheme>
            <cac:PhysicalLocation>
                <cac:Address>
                    <cbc:CityName>Bogota</cbc:CityName>
                    <cbc:CountrySubentity>Cundinamarca</cbc:CountrySubentity>
                    <cac:AddressLine><cbc:Line>Calle 100 # 10-20</cbc:Line></cac:AddressLine>
                    <cac:Country><cbc:Name>Colombia</cbc:Name></cac:Country>
                </cac:Address>
            </cac:PhysicalLocation>
            <cac:Contact>
                <cbc:Telephone>3001234567</cbc:Telephone>
                <cbc:ElectronicMail>emisor@test.com</cbc:ElectronicMail>
            </cac:Contact>
        </cac:Party>
    </cac:AccountingSupplierParty>
    <cac:AccountingCustomerParty>
        <cbc:AdditionalAccountID>1</cbc:AdditionalAccountID>
        <cac:Party>
            <cac:PartyName><cbc:Name>Empresa Receptora LTDA</cbc:Name></cac:PartyName>
            <cac:PartyTaxScheme>
                <cbc:CompanyID schemeID="31">800987654</cbc:CompanyID>
                <cac:TaxScheme><cbc:ID>01</cbc:ID><cbc:Name>IVA</cbc:Name></cac:TaxScheme>
            </cac:PartyTaxScheme>
            <cac:PhysicalLocation>
                <cac:Address>
                    <cbc:CityName>Medellin</cbc:CityName>
                    <cac:AddressLine><cbc:Line>Carrera 50 # 30-40</cbc:Line></cac:AddressLine>
                    <cac:Country><cbc:Name>Colombia</cbc:Name></cac:Country>
                </cac:Address>
            </cac:PhysicalLocation>
            <cac:Contact>
                <cbc:Telephone>3009876543</cbc:Telephone>
                <cbc:ElectronicMail>receptor@test.com</cbc:ElectronicMail>
            </cac:Contact>
        </cac:Party>
    </cac:AccountingCustomerParty>
    <cac:PaymentMeans>
        <cbc:PaymentMeansCode>49</cbc:PaymentMeansCode>
        <cbc:PaymentDueDate>2024-02-15</cbc:PaymentDueDate>
    </cac:PaymentMeans>
    <cac:InvoiceLine>
        <cbc:ID>1</cbc:ID>
        <cbc:InvoicedQuantity unitCode="94">10</cbc:InvoicedQuantity>
        <cbc:LineExtensionAmount currencyID="COP">1000000</cbc:LineExtensionAmount>
        <cac:TaxTotal>
            <cbc:TaxAmount currencyID="COP">190000</cbc:TaxAmount>
            <cac:TaxSubtotal>
                <cbc:TaxableAmount currencyID="COP">1000000</cbc:TaxableAmount>
                <cbc:TaxAmount currencyID="COP">190000</cbc:TaxAmount>
                <cac:TaxCategory>
                    <cbc:Percent>19</cbc:Percent>
                    <cac:TaxScheme><cbc:ID>01</cbc:ID><cbc:Name>IVA</cbc:Name></cac:TaxScheme>
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
                <cac:TaxScheme><cbc:ID>01</cbc:ID><cbc:Name>IVA</cbc:Name></cac:TaxScheme>
            </cac:TaxCategory>
        </cac:TaxSubtotal>
    </cac:TaxTotal>
    <cac:LegalMonetaryTotal>
        <cbc:LineExtensionAmount currencyID="COP">1000000</cbc:LineExtensionAmount>
        <cbc:TaxExclusiveAmount currencyID="COP">1000000</cbc:TaxExclusiveAmount>
        <cbc:TaxInclusiveAmount currencyID="COP">1190000</cbc:TaxInclusiveAmount>
        <cbc:PayableAmount currencyID="COP">1190000</cbc:PayableAmount>
    </cac:LegalMonetaryTotal>
</Invoice>"""


# No-IVA invoice: cac:TaxTotal absent, TaxScheme ZZ (factura sin iva / servicio publico)
_NO_IVA_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
    <cbc:ID>FE-002</cbc:ID>
    <cbc:UUID schemeName="CUFE-SHA384">cufe-no-iva-456</cbc:UUID>
    <cbc:IssueDate>2024-01-20</cbc:IssueDate>
    <cbc:IssueTime>09:00:00</cbc:IssueTime>
    <cbc:DocumentCurrencyCode>COP</cbc:DocumentCurrencyCode>
    <cbc:InvoiceTypeCode>01</cbc:InvoiceTypeCode>
    <cac:AccountingSupplierParty>
        <cbc:AdditionalAccountID>2</cbc:AdditionalAccountID>
        <cac:Party>
            <cac:PartyTaxScheme>
                <cbc:RegistrationName>Karen Rincon Acosta</cbc:RegistrationName>
                <cbc:CompanyID schemeID="13">1026288579</cbc:CompanyID>
                <cac:TaxScheme><cbc:ID>ZZ</cbc:ID><cbc:Name>No aplica</cbc:Name></cac:TaxScheme>
            </cac:PartyTaxScheme>
        </cac:Party>
    </cac:AccountingSupplierParty>
    <cac:AccountingCustomerParty>
        <cbc:AdditionalAccountID>1</cbc:AdditionalAccountID>
        <cac:Party>
            <cac:PartyTaxScheme>
                <cbc:RegistrationName>IKBO S.A.S.</cbc:RegistrationName>
                <cbc:CompanyID schemeID="31">901031352</cbc:CompanyID>
                <cac:TaxScheme><cbc:ID>01</cbc:ID><cbc:Name>IVA</cbc:Name></cac:TaxScheme>
            </cac:PartyTaxScheme>
        </cac:Party>
    </cac:AccountingCustomerParty>
    <cac:InvoiceLine>
        <cbc:ID>1</cbc:ID>
        <cbc:InvoicedQuantity unitCode="94">1</cbc:InvoicedQuantity>
        <cbc:LineExtensionAmount currencyID="COP">37900</cbc:LineExtensionAmount>
        <cac:Item><cbc:Description>Torta pie de limon</cbc:Description></cac:Item>
        <cac:Price><cbc:PriceAmount currencyID="COP">37900</cbc:PriceAmount></cac:Price>
    </cac:InvoiceLine>
    <cac:LegalMonetaryTotal>
        <cbc:LineExtensionAmount currencyID="COP">37900</cbc:LineExtensionAmount>
        <cbc:TaxExclusiveAmount currencyID="COP">0</cbc:TaxExclusiveAmount>
        <cbc:TaxInclusiveAmount currencyID="COP">37900</cbc:TaxInclusiveAmount>
        <cbc:PayableAmount currencyID="COP">37900</cbc:PayableAmount>
    </cac:LegalMonetaryTotal>
</Invoice>"""


# Withholding taxes: cac:WithholdingTaxTotal with ReteRenta + ReteICA, no cac:TaxTotal
_WITHHOLDING_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
    <cbc:ID>PLCO-001</cbc:ID>
    <cbc:UUID schemeName="CUFE-SHA384">cufe-ret-789</cbc:UUID>
    <cbc:IssueDate>2024-03-05</cbc:IssueDate>
    <cbc:IssueTime>08:00:00</cbc:IssueTime>
    <cbc:DocumentCurrencyCode>COP</cbc:DocumentCurrencyCode>
    <cbc:InvoiceTypeCode>01</cbc:InvoiceTypeCode>
    <cac:AccountingSupplierParty>
        <cbc:AdditionalAccountID>1</cbc:AdditionalAccountID>
        <cac:Party>
            <cac:PartyTaxScheme>
                <cbc:RegistrationName>Arrendador SAS</cbc:RegistrationName>
                <cbc:CompanyID schemeID="31">900873779</cbc:CompanyID>
                <cac:TaxScheme><cbc:ID>ZZ</cbc:ID><cbc:Name>No aplica</cbc:Name></cac:TaxScheme>
            </cac:PartyTaxScheme>
        </cac:Party>
    </cac:AccountingSupplierParty>
    <cac:AccountingCustomerParty>
        <cbc:AdditionalAccountID>1</cbc:AdditionalAccountID>
        <cac:Party>
            <cac:PartyTaxScheme>
                <cbc:RegistrationName>IKBO S.A.S.</cbc:RegistrationName>
                <cbc:CompanyID schemeID="31">901031352</cbc:CompanyID>
                <cac:TaxScheme><cbc:ID>01</cbc:ID><cbc:Name>IVA</cbc:Name></cac:TaxScheme>
            </cac:PartyTaxScheme>
        </cac:Party>
    </cac:AccountingCustomerParty>
    <cac:WithholdingTaxTotal>
        <cbc:TaxAmount currencyID="COP">87113.95</cbc:TaxAmount>
        <cac:TaxSubtotal>
            <cbc:TaxableAmount currencyID="COP">2488970</cbc:TaxableAmount>
            <cbc:TaxAmount currencyID="COP">87113.95</cbc:TaxAmount>
            <cac:TaxCategory>
                <cbc:Percent>3.5</cbc:Percent>
                <cac:TaxScheme><cbc:ID>06</cbc:ID><cbc:Name>ReteRenta</cbc:Name></cac:TaxScheme>
            </cac:TaxCategory>
        </cac:TaxSubtotal>
    </cac:WithholdingTaxTotal>
    <cac:WithholdingTaxTotal>
        <cbc:TaxAmount currencyID="COP">24043.45</cbc:TaxAmount>
        <cac:TaxSubtotal>
            <cbc:TaxableAmount currencyID="COP">2488970</cbc:TaxableAmount>
            <cbc:TaxAmount currencyID="COP">24043.45</cbc:TaxAmount>
            <cac:TaxCategory>
                <cbc:Percent>0.966</cbc:Percent>
                <cac:TaxScheme><cbc:ID>07</cbc:ID><cbc:Name>ReteICA</cbc:Name></cac:TaxScheme>
            </cac:TaxCategory>
        </cac:TaxSubtotal>
    </cac:WithholdingTaxTotal>
    <cac:InvoiceLine>
        <cbc:ID>1</cbc:ID>
        <cbc:InvoicedQuantity unitCode="94">1</cbc:InvoicedQuantity>
        <cbc:LineExtensionAmount currencyID="COP">2488970</cbc:LineExtensionAmount>
        <cac:Item><cbc:Description>Canon de arrendamiento</cbc:Description></cac:Item>
        <cac:Price><cbc:PriceAmount currencyID="COP">2488970</cbc:PriceAmount></cac:Price>
    </cac:InvoiceLine>
    <cac:LegalMonetaryTotal>
        <cbc:LineExtensionAmount currencyID="COP">2488970</cbc:LineExtensionAmount>
        <cbc:TaxExclusiveAmount currencyID="COP">0</cbc:TaxExclusiveAmount>
        <cbc:TaxInclusiveAmount currencyID="COP">2488970</cbc:TaxInclusiveAmount>
        <cbc:PayableAmount currencyID="COP">2488970</cbc:PayableAmount>
    </cac:LegalMonetaryTotal>
</Invoice>"""


# Discount invoice: AllowanceCharge per line (ChargeIndicator=false)
_DISCOUNT_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
    <cbc:ID>FENL-001</cbc:ID>
    <cbc:UUID schemeName="CUFE-SHA384">cufe-desc-abc</cbc:UUID>
    <cbc:IssueDate>2024-03-09</cbc:IssueDate>
    <cbc:IssueTime>12:00:00</cbc:IssueTime>
    <cbc:DocumentCurrencyCode>COP</cbc:DocumentCurrencyCode>
    <cbc:InvoiceTypeCode>01</cbc:InvoiceTypeCode>
    <cac:AccountingSupplierParty>
        <cbc:AdditionalAccountID>1</cbc:AdditionalAccountID>
        <cac:Party>
            <cac:PartyTaxScheme>
                <cbc:RegistrationName>Editorial SAS</cbc:RegistrationName>
                <cbc:CompanyID schemeID="31">901760399</cbc:CompanyID>
                <cac:TaxScheme><cbc:ID>01</cbc:ID><cbc:Name>IVA</cbc:Name></cac:TaxScheme>
            </cac:PartyTaxScheme>
        </cac:Party>
    </cac:AccountingSupplierParty>
    <cac:AccountingCustomerParty>
        <cbc:AdditionalAccountID>1</cbc:AdditionalAccountID>
        <cac:Party>
            <cac:PartyTaxScheme>
                <cbc:RegistrationName>IKBO S.A.S.</cbc:RegistrationName>
                <cbc:CompanyID schemeID="31">901031352</cbc:CompanyID>
                <cac:TaxScheme><cbc:ID>01</cbc:ID><cbc:Name>IVA</cbc:Name></cac:TaxScheme>
            </cac:PartyTaxScheme>
        </cac:Party>
    </cac:AccountingCustomerParty>
    <cac:InvoiceLine>
        <cbc:ID>1</cbc:ID>
        <cbc:InvoicedQuantity unitCode="94">1</cbc:InvoicedQuantity>
        <cbc:LineExtensionAmount currencyID="COP">198000</cbc:LineExtensionAmount>
        <cac:AllowanceCharge>
            <cbc:ChargeIndicator>false</cbc:ChargeIndicator>
            <cbc:AllowanceChargeReason>Descuento comercial</cbc:AllowanceChargeReason>
            <cbc:MultiplierFactorNumeric>0.10</cbc:MultiplierFactorNumeric>
            <cbc:Amount currencyID="COP">22000</cbc:Amount>
            <cbc:BaseAmount currencyID="COP">220000</cbc:BaseAmount>
        </cac:AllowanceCharge>
        <cac:TaxTotal>
            <cbc:TaxAmount currencyID="COP">37620</cbc:TaxAmount>
            <cac:TaxSubtotal>
                <cbc:TaxableAmount currencyID="COP">198000</cbc:TaxableAmount>
                <cbc:TaxAmount currencyID="COP">37620</cbc:TaxAmount>
                <cac:TaxCategory>
                    <cbc:Percent>19</cbc:Percent>
                    <cac:TaxScheme><cbc:ID>01</cbc:ID><cbc:Name>IVA</cbc:Name></cac:TaxScheme>
                </cac:TaxCategory>
            </cac:TaxSubtotal>
        </cac:TaxTotal>
        <cac:Item><cbc:Description>Seminario juridico</cbc:Description></cac:Item>
        <cac:Price>
            <cbc:PriceAmount currencyID="COP">220000</cbc:PriceAmount>
        </cac:Price>
    </cac:InvoiceLine>
    <cac:TaxTotal>
        <cbc:TaxAmount currencyID="COP">37620</cbc:TaxAmount>
        <cac:TaxSubtotal>
            <cbc:TaxableAmount currencyID="COP">198000</cbc:TaxableAmount>
            <cbc:TaxAmount currencyID="COP">37620</cbc:TaxAmount>
            <cac:TaxCategory>
                <cbc:Percent>19</cbc:Percent>
                <cac:TaxScheme><cbc:ID>01</cbc:ID><cbc:Name>IVA</cbc:Name></cac:TaxScheme>
            </cac:TaxCategory>
        </cac:TaxSubtotal>
    </cac:TaxTotal>
    <cac:LegalMonetaryTotal>
        <cbc:LineExtensionAmount currencyID="COP">198000</cbc:LineExtensionAmount>
        <cbc:TaxExclusiveAmount currencyID="COP">198000</cbc:TaxExclusiveAmount>
        <cbc:TaxInclusiveAmount currencyID="COP">235620</cbc:TaxInclusiveAmount>
        <cbc:PayableAmount currencyID="COP">235620</cbc:PayableAmount>
    </cac:LegalMonetaryTotal>
</Invoice>"""


# INC Bolsas: FreeOfChargeIndicator=true, PerUnitAmount, no Percent, TaxScheme 22
_INC_BOLSAS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
    <cbc:ID>SC-001</cbc:ID>
    <cbc:UUID schemeName="CUFE-SHA384">cufe-bolsa-xyz</cbc:UUID>
    <cbc:IssueDate>2024-02-25</cbc:IssueDate>
    <cbc:IssueTime>11:00:00</cbc:IssueTime>
    <cbc:DocumentCurrencyCode>COP</cbc:DocumentCurrencyCode>
    <cbc:InvoiceTypeCode>01</cbc:InvoiceTypeCode>
    <cac:AccountingSupplierParty>
        <cbc:AdditionalAccountID>1</cbc:AdditionalAccountID>
        <cac:Party>
            <cac:PartyTaxScheme>
                <cbc:RegistrationName>Supermercado SAS</cbc:RegistrationName>
                <cbc:CompanyID schemeID="31">800200139</cbc:CompanyID>
                <cac:TaxScheme><cbc:ID>01</cbc:ID><cbc:Name>IVA</cbc:Name></cac:TaxScheme>
            </cac:PartyTaxScheme>
        </cac:Party>
    </cac:AccountingSupplierParty>
    <cac:AccountingCustomerParty>
        <cbc:AdditionalAccountID>1</cbc:AdditionalAccountID>
        <cac:Party>
            <cac:PartyTaxScheme>
                <cbc:RegistrationName>IKBO S.A.S.</cbc:RegistrationName>
                <cbc:CompanyID schemeID="31">901031352</cbc:CompanyID>
                <cac:TaxScheme><cbc:ID>01</cbc:ID><cbc:Name>IVA</cbc:Name></cac:TaxScheme>
            </cac:PartyTaxScheme>
        </cac:Party>
    </cac:AccountingCustomerParty>
    <cac:InvoiceLine>
        <cbc:ID>1</cbc:ID>
        <cbc:InvoicedQuantity unitCode="94">2</cbc:InvoicedQuantity>
        <cbc:LineExtensionAmount currencyID="COP">10000</cbc:LineExtensionAmount>
        <cac:TaxTotal>
            <cbc:TaxAmount currencyID="COP">1900</cbc:TaxAmount>
            <cac:TaxSubtotal>
                <cbc:TaxableAmount currencyID="COP">10000</cbc:TaxableAmount>
                <cbc:TaxAmount currencyID="COP">1900</cbc:TaxAmount>
                <cac:TaxCategory>
                    <cbc:Percent>19</cbc:Percent>
                    <cac:TaxScheme><cbc:ID>01</cbc:ID><cbc:Name>IVA</cbc:Name></cac:TaxScheme>
                </cac:TaxCategory>
            </cac:TaxSubtotal>
        </cac:TaxTotal>
        <cac:Item><cbc:Description>Producto normal</cbc:Description></cac:Item>
        <cac:Price><cbc:PriceAmount currencyID="COP">5000</cbc:PriceAmount></cac:Price>
    </cac:InvoiceLine>
    <cac:InvoiceLine>
        <cbc:ID>2</cbc:ID>
        <cbc:FreeOfChargeIndicator>true</cbc:FreeOfChargeIndicator>
        <cbc:InvoicedQuantity unitCode="94">2</cbc:InvoicedQuantity>
        <cbc:LineExtensionAmount currencyID="COP">0</cbc:LineExtensionAmount>
        <cac:TaxTotal>
            <cbc:TaxAmount currencyID="COP">146</cbc:TaxAmount>
            <cac:TaxSubtotal>
                <cbc:TaxableAmount currencyID="COP">0</cbc:TaxableAmount>
                <cbc:TaxAmount currencyID="COP">146</cbc:TaxAmount>
                <cbc:PerUnitAmount currencyID="COP">73.00</cbc:PerUnitAmount>
                <cac:TaxCategory>
                    <cac:TaxScheme><cbc:ID>22</cbc:ID><cbc:Name>INC Bolsas</cbc:Name></cac:TaxScheme>
                </cac:TaxCategory>
            </cac:TaxSubtotal>
        </cac:TaxTotal>
        <cac:Item><cbc:Description>Bolsa plastica BMTB</cbc:Description></cac:Item>
        <cac:Price><cbc:PriceAmount currencyID="COP">0</cbc:PriceAmount></cac:Price>
    </cac:InvoiceLine>
    <cac:TaxTotal>
        <cbc:TaxAmount currencyID="COP">1900</cbc:TaxAmount>
        <cac:TaxSubtotal>
            <cbc:TaxableAmount currencyID="COP">10000</cbc:TaxableAmount>
            <cbc:TaxAmount currencyID="COP">1900</cbc:TaxAmount>
            <cac:TaxCategory>
                <cbc:Percent>19</cbc:Percent>
                <cac:TaxScheme><cbc:ID>01</cbc:ID><cbc:Name>IVA</cbc:Name></cac:TaxScheme>
            </cac:TaxCategory>
        </cac:TaxSubtotal>
    </cac:TaxTotal>
    <cac:TaxTotal>
        <cbc:TaxAmount currencyID="COP">146</cbc:TaxAmount>
        <cac:TaxSubtotal>
            <cbc:TaxableAmount currencyID="COP">0</cbc:TaxableAmount>
            <cbc:TaxAmount currencyID="COP">146</cbc:TaxAmount>
            <cbc:PerUnitAmount currencyID="COP">73.00</cbc:PerUnitAmount>
            <cac:TaxCategory>
                <cac:TaxScheme><cbc:ID>22</cbc:ID><cbc:Name>INC Bolsas</cbc:Name></cac:TaxScheme>
            </cac:TaxCategory>
        </cac:TaxSubtotal>
    </cac:TaxTotal>
    <cac:LegalMonetaryTotal>
        <cbc:LineExtensionAmount currencyID="COP">10000</cbc:LineExtensionAmount>
        <cbc:TaxExclusiveAmount currencyID="COP">10000</cbc:TaxExclusiveAmount>
        <cbc:TaxInclusiveAmount currencyID="COP">12046</cbc:TaxInclusiveAmount>
        <cbc:PayableAmount currencyID="COP">12046</cbc:PayableAmount>
    </cac:LegalMonetaryTotal>
</Invoice>"""


# AttachedDocument wrapping an Invoice in CDATA
_ATTACHED_DOC_XML = """<?xml version="1.0" encoding="UTF-8"?>
<AttachedDocument xmlns="urn:oasis:names:specification:ubl:schema:xsd:AttachedDocument-2"
                  xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
                  xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
    <cbc:ID>AD-001</cbc:ID>
    <cac:Attachment>
        <cac:ExternalReference>
            <cbc:Description><![CDATA[<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
    <cbc:ID>FE-INNER</cbc:ID>
    <cbc:UUID schemeName="CUFE-SHA384">cufe-inner-001</cbc:UUID>
    <cbc:IssueDate>2024-05-01</cbc:IssueDate>
    <cbc:IssueTime>08:00:00</cbc:IssueTime>
    <cbc:DocumentCurrencyCode>COP</cbc:DocumentCurrencyCode>
    <cbc:InvoiceTypeCode>01</cbc:InvoiceTypeCode>
    <cac:AccountingSupplierParty>
        <cbc:AdditionalAccountID>1</cbc:AdditionalAccountID>
        <cac:Party>
            <cac:PartyTaxScheme>
                <cbc:RegistrationName>Emisor Interno SAS</cbc:RegistrationName>
                <cbc:CompanyID schemeID="31">999000001</cbc:CompanyID>
                <cac:TaxScheme><cbc:ID>01</cbc:ID><cbc:Name>IVA</cbc:Name></cac:TaxScheme>
            </cac:PartyTaxScheme>
        </cac:Party>
    </cac:AccountingSupplierParty>
    <cac:AccountingCustomerParty>
        <cbc:AdditionalAccountID>1</cbc:AdditionalAccountID>
        <cac:Party>
            <cac:PartyTaxScheme>
                <cbc:RegistrationName>Receptor Interno LTDA</cbc:RegistrationName>
                <cbc:CompanyID schemeID="31">999000002</cbc:CompanyID>
                <cac:TaxScheme><cbc:ID>01</cbc:ID><cbc:Name>IVA</cbc:Name></cac:TaxScheme>
            </cac:PartyTaxScheme>
        </cac:Party>
    </cac:AccountingCustomerParty>
    <cac:InvoiceLine>
        <cbc:ID>1</cbc:ID>
        <cbc:InvoicedQuantity unitCode="94">1</cbc:InvoicedQuantity>
        <cbc:LineExtensionAmount currencyID="COP">500000</cbc:LineExtensionAmount>
        <cac:Item><cbc:Description>Producto adjunto</cbc:Description></cac:Item>
        <cac:Price><cbc:PriceAmount currencyID="COP">500000</cbc:PriceAmount></cac:Price>
    </cac:InvoiceLine>
    <cac:LegalMonetaryTotal>
        <cbc:LineExtensionAmount currencyID="COP">500000</cbc:LineExtensionAmount>
        <cbc:TaxExclusiveAmount currencyID="COP">0</cbc:TaxExclusiveAmount>
        <cbc:TaxInclusiveAmount currencyID="COP">500000</cbc:TaxInclusiveAmount>
        <cbc:PayableAmount currencyID="COP">500000</cbc:PayableAmount>
    </cac:LegalMonetaryTotal>
</Invoice>]]></cbc:Description>
        </cac:ExternalReference>
    </cac:Attachment>
</AttachedDocument>"""


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestHeaderFields:
    def test_numero_documento(self):
        result = parse_xml(_BASE_XML)
        assert result["numero_documento"] == "FE-001"

    def test_fechas(self):
        result = parse_xml(_BASE_XML)
        assert result["fecha_emision"] == "2024-01-15"
        assert result["hora_emision"] == "10:30:00"
        assert result["fecha_vencimiento"] == "2024-02-15"

    def test_moneda(self):
        result = parse_xml(_BASE_XML)
        assert result["moneda"] == "COP"

    def test_cufe(self):
        result = parse_xml(_BASE_XML)
        assert result["cufe"] == "cufe-abc-123"

    def test_tipo_documento_es_dict(self):
        result = parse_xml(_BASE_XML)
        assert result["tipo_documento"]["codigo"] == "01"
        assert result["tipo_documento"]["nombre"] == "Factura de venta"

    def test_notas(self):
        result = parse_xml(_BASE_XML)
        assert isinstance(result["notas"], list)
        assert "Nota de prueba" in result["notas"]


class TestParties:
    def test_emisor_nombre_y_nit(self):
        result = parse_xml(_BASE_XML)
        emisor = result["emisor"]
        assert emisor["nombre"] == "Empresa Emisora SAS"
        assert emisor["nit"] == "900123456"

    def test_emisor_tipo_identificacion(self):
        result = parse_xml(_BASE_XML)
        assert result["emisor"]["tipo_identificacion"] == "NIT"

    def test_emisor_tipo_persona_juridica(self):
        result = parse_xml(_BASE_XML)
        assert result["emisor"]["tipo_persona"] == "Persona jurídica"

    def test_emisor_tipo_persona_natural(self):
        result = parse_xml(_NO_IVA_XML)
        assert result["emisor"]["tipo_persona"] == "Persona natural"

    def test_emisor_cedula(self):
        result = parse_xml(_NO_IVA_XML)
        assert result["emisor"]["tipo_identificacion"] == "Cédula de ciudadanía"

    def test_emisor_regimen(self):
        result = parse_xml(_BASE_XML)
        assert result["emisor"]["regimen"] == "R-99-PN"

    def test_emisor_direccion(self):
        result = parse_xml(_BASE_XML)
        direccion = result["emisor"]["direccion"]
        assert direccion["ciudad"] == "Bogota"
        assert direccion["departamento"] == "Cundinamarca"

    def test_emisor_contacto(self):
        result = parse_xml(_BASE_XML)
        assert result["emisor"]["contacto"]["email"] == "emisor@test.com"

    def test_receptor_nombre_y_nit(self):
        result = parse_xml(_BASE_XML)
        receptor = result["receptor"]
        assert receptor["nombre"] == "Empresa Receptora LTDA"
        assert receptor["nit"] == "800987654"


class TestPayment:
    def test_pago_presente(self):
        result = parse_xml(_BASE_XML)
        assert result["pago"] is not None

    def test_pago_codigo_y_nombre(self):
        result = parse_xml(_BASE_XML)
        assert result["pago"]["codigo"] == "49"
        assert result["pago"]["medio_pago"] == "Tarjeta débito"

    def test_pago_fecha_vencimiento(self):
        result = parse_xml(_BASE_XML)
        assert result["pago"]["fecha_vencimiento"] == "2024-02-15"

    def test_pago_none_si_ausente(self):
        result = parse_xml(_NO_IVA_XML)
        assert result["pago"] is None


class TestItems:
    def test_cantidad_items(self):
        result = parse_xml(_BASE_XML)
        assert len(result["items"]) == 1

    def test_item_campos_base(self):
        item = parse_xml(_BASE_XML)["items"][0]
        assert item["id"] == "1"
        assert item["descripcion"] == "Servicio de consultoria"
        assert item["cantidad"] == "10"
        assert item["unidad_medida"] == "94"
        assert item["precio_unitario"] == "100000"
        assert item["valor_total"] == "1000000"

    def test_item_gratis_false_por_defecto(self):
        item = parse_xml(_BASE_XML)["items"][0]
        assert item["gratis"] is False

    def test_item_sin_descuentos_es_none(self):
        item = parse_xml(_BASE_XML)["items"][0]
        assert item["descuentos_cargos"] is None

    def test_item_impuesto_iva(self):
        impuesto = parse_xml(_BASE_XML)["items"][0]["impuestos"][0]
        assert impuesto["codigo"] == "01"
        assert impuesto["nombre"] == "IVA"
        assert impuesto["porcentaje"] == "19"
        assert impuesto["valor"] == "190000"
        assert impuesto["base_imponible"] == "1000000"


class TestTotals:
    def test_totales_presentes(self):
        totales = parse_xml(_BASE_XML)["totales"]
        assert totales["valor_lineas"] == "1000000"
        assert totales["subtotal"] == "1000000"
        assert totales["total_impuestos"] == "190000"
        assert totales["total_con_impuestos"] == "1190000"
        assert totales["total"] == "1190000"
        assert totales["redondeo"] is None

    def test_total_impuestos_cero_cuando_sin_iva(self):
        totales = parse_xml(_NO_IVA_XML)["totales"]
        assert totales["total_impuestos"] == "0"

    def test_retenciones_vacias_en_factura_normal(self):
        assert parse_xml(_BASE_XML)["retenciones"] == []

    def test_impuestos_vacios_cuando_sin_iva(self):
        assert parse_xml(_NO_IVA_XML)["impuestos"] == []


class TestDocumentTaxes:
    def test_impuestos_documento(self):
        impuestos = parse_xml(_BASE_XML)["impuestos"]
        assert len(impuestos) == 1
        assert impuestos[0]["codigo"] == "01"
        assert impuestos[0]["nombre"] == "IVA"
        assert impuestos[0]["porcentaje"] == "19"

    def test_impuestos_no_duplica_lineas(self):
        # Document-level TaxTotal only — must not include per-line TaxTotals
        impuestos = parse_xml(_BASE_XML)["impuestos"]
        assert len(impuestos) == 1


class TestNoIvaInvoice:
    """factura sin iva / factura servicio publico scenarios."""

    def test_parse_sin_error(self):
        result = parse_xml(_NO_IVA_XML)
        assert result["numero_documento"] == "FE-002"

    def test_impuestos_lista_vacia(self):
        assert parse_xml(_NO_IVA_XML)["impuestos"] == []

    def test_retenciones_lista_vacia(self):
        assert parse_xml(_NO_IVA_XML)["retenciones"] == []

    def test_total_igual_a_subtotal(self):
        totales = parse_xml(_NO_IVA_XML)["totales"]
        assert totales["total"] == totales["total_con_impuestos"]


class TestWithholdingTaxes:
    """factura con retenciones scenario."""

    def test_retenciones_parse_sin_error(self):
        result = parse_xml(_WITHHOLDING_XML)
        assert result["numero_documento"] == "PLCO-001"

    def test_retenciones_count(self):
        retenciones = parse_xml(_WITHHOLDING_XML)["retenciones"]
        assert len(retenciones) == 2

    def test_rete_renta(self):
        ret = parse_xml(_WITHHOLDING_XML)["retenciones"]
        renta = next(r for r in ret if r["codigo"] == "06")
        assert renta["nombre"] == "ReteRenta"
        assert renta["porcentaje"] == "3.5"
        assert renta["valor"] == "87113.95"

    def test_rete_ica(self):
        ret = parse_xml(_WITHHOLDING_XML)["retenciones"]
        ica = next(r for r in ret if r["codigo"] == "07")
        assert ica["nombre"] == "ReteICA"
        assert ica["porcentaje"] == "0.966"

    def test_no_hay_impuestos_iva(self):
        assert parse_xml(_WITHHOLDING_XML)["impuestos"] == []


class TestDiscounts:
    """factura con descuento scenario."""

    def test_descuento_presente_en_item(self):
        item = parse_xml(_DISCOUNT_XML)["items"][0]
        assert item["descuentos_cargos"] is not None
        assert len(item["descuentos_cargos"]) == 1

    def test_descuento_tipo_y_valores(self):
        dc = parse_xml(_DISCOUNT_XML)["items"][0]["descuentos_cargos"][0]
        assert dc["tipo"] == "descuento"
        assert dc["porcentaje"] == "0.10"
        assert dc["valor"] == "22000"
        assert dc["base"] == "220000"

    def test_valor_total_linea_es_neto(self):
        # LineExtensionAmount must already reflect post-discount amount
        item = parse_xml(_DISCOUNT_XML)["items"][0]
        assert item["valor_total"] == "198000"


class TestIncBolsas:
    """factura con impuesto de bolsa scenario."""

    def test_item_gratis_true(self):
        items = parse_xml(_INC_BOLSAS_XML)["items"]
        bolsa = next(i for i in items if i["descripcion"] == "Bolsa plastica BMTB")
        assert bolsa["gratis"] is True
        assert bolsa["valor_total"] == "0"

    def test_bolsa_tax_per_unit_sin_percent(self):
        items = parse_xml(_INC_BOLSAS_XML)["items"]
        bolsa = next(i for i in items if i["descripcion"] == "Bolsa plastica BMTB")
        tax = bolsa["impuestos"][0]
        assert tax["codigo"] == "22"
        assert tax["nombre"] == "INC Bolsas"
        assert tax["porcentaje"] is None
        assert tax["valor_por_unidad"] == "73.00"

    def test_dos_bloques_taxTotal_documento(self):
        impuestos = parse_xml(_INC_BOLSAS_XML)["impuestos"]
        codigos = {t["codigo"] for t in impuestos}
        assert "01" in codigos
        assert "22" in codigos

    def test_item_normal_no_es_gratis(self):
        items = parse_xml(_INC_BOLSAS_XML)["items"]
        normal = next(i for i in items if i["descripcion"] == "Producto normal")
        assert normal["gratis"] is False


class TestAttachedDocument:
    """AttachedDocument unwrapping scenario (all real DIAN files use this wrapper)."""

    def test_unwrap_attached_document(self):
        result = parse_xml(_ATTACHED_DOC_XML)
        assert result["numero_documento"] == "FE-INNER"

    def test_cufe_del_invoice_interno(self):
        result = parse_xml(_ATTACHED_DOC_XML)
        assert result["cufe"] == "cufe-inner-001"

    def test_emisor_del_invoice_interno(self):
        result = parse_xml(_ATTACHED_DOC_XML)
        assert result["emisor"]["nit"] == "999000001"

    def test_items_del_invoice_interno(self):
        items = parse_xml(_ATTACHED_DOC_XML)["items"]
        assert len(items) == 1
        assert items[0]["descripcion"] == "Producto adjunto"


class TestErrors:
    def test_xml_malformado(self):
        with pytest.raises(ValueError, match="XML malformado"):
            parse_xml("<invalid>xml</broken>")

    def test_xml_vacio(self):
        with pytest.raises(ValueError):
            parse_xml("")
