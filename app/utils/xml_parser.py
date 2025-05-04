from lxml import etree
import xml.etree.ElementTree as ET

def parse_xml(xml_content: str) -> dict:
    """
    Parsea un XML de factura electrónica DIAN (Colombia) y extrae los datos principales.
    
    Args:
        xml_content: Contenido XML en bytes
        
    Returns:
        Diccionario con los datos estructurados de la factura
    """
    try:
        # Parsear el XML
        namespaces = {
            'ext': 'urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2',
            'cac': 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2',
            'cbc': 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2',
            'sts': 'dian:gov:co:facturaelectronica:Structures-2-1',
            '': 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2'
        }
        
        # Buscar el XML interno (invoice) dentro del AttachedDocument
        root = ET.fromstring(xml_content)
        
        # Si es un AttachedDocument, extraemos el Invoice interno
        if root.tag.endswith('AttachedDocument'):
            attachment = root.find('.//cac:Attachment/cac:ExternalReference/cbc:Description', namespaces)
            if attachment is not None and attachment.text:
                invoice_xml = attachment.text
                root = ET.fromstring(invoice_xml)
        
        # Registrar los namespaces
        for prefix, uri in namespaces.items():
            ET.register_namespace(prefix, uri)
            
        # Extraer datos básicos
        invoice_data = {
            'numero_documento': root.find('.//cbc:ID', namespaces).text,
            'fecha_emision': root.find('.//cbc:IssueDate', namespaces).text,
            'hora_emision': root.find('.//cbc:IssueTime', namespaces).text if root.find('.//cbc:IssueTime', namespaces) is not None else None,
            'moneda': root.find('.//cbc:DocumentCurrencyCode', namespaces).text,
            'tipo_documento': root.find('.//cbc:InvoiceTypeCode', namespaces).text if root.find('.//cbc:InvoiceTypeCode', namespaces) is not None else None,
            'uuid': root.find('.//cbc:UUID', namespaces).text if root.find('.//cbc:UUID', namespaces) is not None else None
        }
        
        # Extraer datos del emisor
        supplier_party = root.find('.//cac:AccountingSupplierParty/cac:Party', namespaces)
        invoice_data['emisor'] = {
            'nombre': supplier_party.find('.//cac:PartyName/cbc:Name', namespaces).text,
            'nit': supplier_party.find('.//cac:PartyTaxScheme/cbc:CompanyID', namespaces).text,
            'direccion': {
                'ciudad': supplier_party.find('.//cac:PhysicalLocation/cac:Address/cbc:CityName', namespaces).text,
                'direccion': supplier_party.find('.//cac:PhysicalLocation/cac:Address/cac:AddressLine/cbc:Line', namespaces).text,
                'pais': supplier_party.find('.//cac:PhysicalLocation/cac:Address/cac:Country/cbc:Name', namespaces).text
            },
            'contacto': {
                'telefono': supplier_party.find('.//cac:Contact/cbc:Telephone', namespaces).text if supplier_party.find('.//cac:Contact/cbc:Telephone', namespaces) is not None else None,
                'email': supplier_party.find('.//cac:Contact/cbc:ElectronicMail', namespaces).text if supplier_party.find('.//cac:Contact/cbc:ElectronicMail', namespaces) is not None else None
            }
        }
        
        # Extraer datos del receptor
        customer_party = root.find('.//cac:AccountingCustomerParty/cac:Party', namespaces)
        invoice_data['receptor'] = {
            'nombre': customer_party.find('.//cac:PartyName/cbc:Name', namespaces).text,
            'nit': customer_party.find('.//cac:PartyTaxScheme/cbc:CompanyID', namespaces).text,
            'tipo_identificacion': customer_party.find('.//cac:PartyIdentification/cbc:ID', namespaces).attrib.get('schemeName') if customer_party.find('.//cac:PartyIdentification/cbc:ID', namespaces) is not None else None,
            'direccion': {
                'ciudad': customer_party.find('.//cac:PhysicalLocation/cac:Address/cbc:CityName', namespaces).text,
                'direccion': customer_party.find('.//cac:PhysicalLocation/cac:Address/cac:AddressLine/cbc:Line', namespaces).text,
                'pais': customer_party.find('.//cac:PhysicalLocation/cac:Address/cac:Country/cbc:Name', namespaces).text
            },
            'contacto': {
                'telefono': customer_party.find('.//cac:Contact/cbc:Telephone', namespaces).text if customer_party.find('.//cac:Contact/cbc:Telephone', namespaces) is not None else None,
                'email': customer_party.find('.//cac:Contact/cbc:ElectronicMail', namespaces).text if customer_party.find('.//cac:Contact/cbc:ElectronicMail', namespaces) is not None else None
            }
        }
        
        # Extraer items (líneas de factura)
        invoice_data['items'] = []
        for line in root.findall('.//cac:InvoiceLine', namespaces):
            item = {
                'id': line.find('.//cbc:ID', namespaces).text,
                'descripcion': line.find('.//cac:Item/cbc:Description', namespaces).text,
                'cantidad': line.find('.//cbc:InvoicedQuantity', namespaces).text,
                'unidad_medida': line.find('.//cbc:InvoicedQuantity', namespaces).attrib.get('unitCode'),
                'precio_unitario': line.find('.//cac:Price/cbc:PriceAmount', namespaces).text,
                'valor_total': line.find('.//cbc:LineExtensionAmount', namespaces).text,
                'impuestos': []
            }
            
            # Extraer impuestos por item
            for tax in line.findall('.//cac:TaxSubtotal', namespaces):
                item['impuestos'].append({
                    'codigo': tax.find('.//cac:TaxCategory/cac:TaxScheme/cbc:ID', namespaces).text,
                    'nombre': tax.find('.//cac:TaxCategory/cac:TaxScheme/cbc:Name', namespaces).text,
                    'porcentaje': tax.find('.//cac:TaxCategory/cbc:Percent', namespaces).text,
                    'valor': tax.find('.//cbc:TaxAmount', namespaces).text,
                    'base_imponible': tax.find('.//cbc:TaxableAmount', namespaces).text
                })
            
            invoice_data['items'].append(item)
        
        # Extraer totales
        legal_total = root.find('.//cac:LegalMonetaryTotal', namespaces)
        invoice_data['totales'] = {
            'subtotal': legal_total.find('.//cbc:TaxExclusiveAmount', namespaces).text,
            'total_impuestos': root.find('.//cac:TaxTotal/cbc:TaxAmount', namespaces).text,
            'total': legal_total.find('.//cbc:PayableAmount', namespaces).text
        }
        
        # Extraer información de impuestos generales
        invoice_data['impuestos'] = []
        for tax in root.findall('.//cac:TaxTotal/cac:TaxSubtotal', namespaces):
            invoice_data['impuestos'].append({
                'codigo': tax.find('.//cac:TaxCategory/cac:TaxScheme/cbc:ID', namespaces).text,
                'nombre': tax.find('.//cac:TaxCategory/cac:TaxScheme/cbc:Name', namespaces).text,
                'porcentaje': tax.find('.//cac:TaxCategory/cbc:Percent', namespaces).text,
                'valor': tax.find('.//cbc:TaxAmount', namespaces).text,
                'base_imponible': tax.find('.//cbc:TaxableAmount', namespaces).text
            })
        
        # Extraer información de pagos si existe
        payment_means = root.find('.//cac:PaymentMeans', namespaces)
        if payment_means is not None:
            invoice_data['pago'] = {
                'medio_pago': payment_means.find('.//cbc:PaymentMeansCode', namespaces).text,
                'fecha_vencimiento': payment_means.find('.//cbc:PaymentDueDate', namespaces).text if payment_means.find('.//cbc:PaymentDueDate', namespaces) is not None else None
            }
        
        return invoice_data
    
    except Exception as e:
        raise ValueError(f"Error al procesar el XML: {str(e)}")

