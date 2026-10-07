"""Local EN16931 XML reading/generation. No network, customer mail or finalization."""
from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from threading import Lock
import hashlib
import json

from lxml import etree as ET

UBL = 'urn:oasis:names:specification:ubl:schema:xsd:Invoice-2'
CREDIT = 'urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2'
CBC = 'urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2'
CAC = 'urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2'
CII = 'urn:un:unece:uncefact:data:standard:CrossIndustryInvoice:100'
RAM = 'urn:un:unece:uncefact:data:standard:ReusableAggregateBusinessInformationEntity:100'
UDT = 'urn:un:unece:uncefact:data:standard:UnqualifiedDataType:100'
NS = {'cbc': CBC, 'cac': CAC, 'rsm': CII, 'ram': RAM, 'udt': UDT,
      'svrl': 'http://purl.oclc.org/dsdl/svrl'}
MAX_XML_BYTES = 5_000_000
LOCK = Lock()


def xml_tree(data: bytes):
    if not data or len(data) > MAX_XML_BYTES:
        raise ValueError('XML leer oder zu umfangreich; gezielte Prüfung erforderlich')
    try:
        root = ET.fromstring(data, ET.XMLParser(resolve_entities=False, load_dtd=False,
                            no_network=True, huge_tree=False))
    except ET.XMLSyntaxError:
        raise ValueError('Ungültige XML-Syntax') from None
    if root.getroottree().docinfo.doctype or any(isinstance(n, ET._Entity) for n in root.iter()):
        raise ValueError('DTD und Entities sind in Rechnungs-XML nicht erlaubt')
    if len(list(root.iter())) > 50000:
        raise ValueError('XML zu umfangreich')
    return root


def syntax(root):
    return {f'{{{UBL}}}Invoice': 'ubl-invoice', f'{{{CREDIT}}}CreditNote': 'ubl-creditnote',
            f'{{{CII}}}CrossIndustryInvoice': 'cii'}.get(root.tag)


@lru_cache(maxsize=3)
def schema(kind):
    # Use pinned, packaged official schemas without the library's error logger,
    # which would expose invoice contents. Never use its HTTP schematron helper.
    from facturx.facturx import UBL_21_xsd, FACTURX_LEVEL2xsd
    name = FACTURX_LEVEL2xsd['en16931'] if kind == 'cii' else UBL_21_xsd[
        'ubl-2.1-invoice' if kind == 'ubl-invoice' else 'ubl-2.1-creditnote']
    return ET.XMLSchema(file=str(files('facturx').joinpath('xsd_and_schematron', name)))


@lru_cache(maxsize=2)
def schematron(kind):
    from saxonche import PySaxonProcessor
    directory = Path(__file__).parent / 'validation'
    name = f"EN16931-{'CII' if kind == 'cii' else 'UBL'}-validation.xslt"
    manifest = json.loads((directory/'sources.json').read_bytes())
    if hashlib.sha256((directory/name).read_bytes()).hexdigest() != manifest['files'][name]:
        raise ValueError('Validierungsregeln wurden verändert')
    processor = PySaxonProcessor(license=False)
    executable = processor.new_xslt30_processor().compile_stylesheet(stylesheet_file=str(directory/name))
    return processor, executable


def validate_xml(data: bytes):
    root = xml_tree(data); kind = syntax(root)
    result = {'syntax': kind, 'rules': 'CEN EN16931 1.3.16', 'xsd_valid': False,
              'en16931_valid': False, 'errors': [], 'cius_validated': False}
    if not kind:
        result['errors'] = ['UNSUPPORTED-SYNTAX']; return result
    if not schema(kind).validate(root):
        result['errors'] = ['XSD-INVALID']; return result
    result['xsd_valid'] = True
    with LOCK:
        processor, executable = schematron('cii' if kind == 'cii' else 'ubl')
        node = processor.parse_xml(xml_text=ET.tostring(root, encoding='unicode'))
        output = executable.transform_to_string(xdm_node=node)
    svrl = xml_tree(output.encode())
    failures = svrl.xpath('//svrl:failed-assert', namespaces=NS)
    result['errors'] = sorted({n.get('id', 'EN16931-ASSERTION') for n in failures})
    result['en16931_valid'] = not failures
    return result


def text(root, path):
    if root is None: return None
    values = root.xpath(path, namespaces=NS)
    if not values: return None
    value = values[0]
    return ''.join(value.itertext()).strip() if hasattr(value, 'itertext') else str(value).strip()


def inspect_xml(data: bytes):
    root = xml_tree(data); validation = validate_xml(data); kind = syntax(root)
    if not kind or not validation['en16931_valid']:
        return {'validation': validation, 'metadata': None}
    if kind.startswith('ubl'):
        supplier = root.find('cac:AccountingSupplierParty/cac:Party', NS)
        totals = root.find('cac:LegalMonetaryTotal', NS)
        tax = root.find('cac:TaxTotal', NS)
        groups = []
        for g in root.findall('cac:TaxTotal/cac:TaxSubtotal', NS):
            net = text(g, 'cbc:TaxableAmount'); vat = text(g, 'cbc:TaxAmount')
            groups.append({'net': net, 'vat': vat, 'vat_rate': text(g, 'cac:TaxCategory/cbc:Percent'),
                           'category': text(g, 'cac:TaxCategory/cbc:ID')})
        values = {'payee': text(supplier, 'cac:PartyLegalEntity/cbc:RegistrationName') or text(supplier,'cac:PartyName/cbc:Name'),
                  'number': text(root, 'cbc:ID'), 'date': text(root, 'cbc:IssueDate'),
                  'currency': text(root, 'cbc:DocumentCurrencyCode'), 'gross': text(totals, 'cbc:TaxInclusiveAmount'),
                  'net': text(totals, 'cbc:TaxExclusiveAmount'), 'vat': text(tax, 'cbc:TaxAmount'),
                  'supplier_country': text(supplier, 'cac:PostalAddress/cac:Country/cbc:IdentificationCode')}
        names = root.xpath('//cac:Item/cbc:Name/text()', namespaces=NS)
        document_type = 'credit_note' if kind == 'ubl-creditnote' else 'invoice'
        original_numbers = root.xpath('cac:BillingReference/cac:InvoiceDocumentReference/cbc:ID/text()', namespaces=NS)
    else:
        trade = root.find('rsm:SupplyChainTradeTransaction', NS)
        supplier = trade.find('ram:ApplicableHeaderTradeAgreement/ram:SellerTradeParty', NS)
        settlement = trade.find('ram:ApplicableHeaderTradeSettlement', NS)
        totals = settlement.find('ram:SpecifiedTradeSettlementHeaderMonetarySummation', NS)
        groups = [{'net': text(g, 'ram:BasisAmount'), 'vat': text(g, 'ram:CalculatedAmount'),
                   'vat_rate': text(g, 'ram:RateApplicablePercent'), 'category': text(g, 'ram:CategoryCode')}
                  for g in settlement.findall('ram:ApplicableTradeTax', NS)]
        raw_date = text(root,'rsm:ExchangedDocument/ram:IssueDateTime/udt:DateTimeString')
        values = {'payee': text(supplier,'ram:Name'), 'number': text(root,'rsm:ExchangedDocument/ram:ID'),
                  'date': f'{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}' if raw_date and len(raw_date)==8 else raw_date,
                  'currency': text(settlement,'ram:InvoiceCurrencyCode'), 'gross': text(totals,'ram:GrandTotalAmount'),
                  'net': text(totals,'ram:TaxBasisTotalAmount'), 'vat': text(totals,'ram:TaxTotalAmount'),
                  'supplier_country': text(supplier,'ram:PostalTradeAddress/ram:CountryID')}
        names = root.xpath('//ram:SpecifiedTradeProduct/ram:Name/text()',namespaces=NS)
        document_type = 'credit_note' if text(root,'rsm:ExchangedDocument/ram:TypeCode')=='381' else 'invoice'
        original_numbers = settlement.xpath('ram:InvoiceReferencedDocument/ram:IssuerAssignedID/text()', namespaces=NS)
    if not validation['en16931_valid']:
        return {'validation': validation, 'metadata': None, 'document_type': document_type}
    for g in groups:
        g['gross'] = str(Decimal(g['net'])+Decimal(g['vat']))
        g['vat_rate'] = float(g['vat_rate']) if g['vat_rate'] is not None else None
    unknown = any(g['vat_rate'] is None or g['category'] not in ('S','E','Z') for g in groups)
    special = values['supplier_country'] != 'DE' or unknown or document_type != 'invoice'
    rates = sorted({g['vat_rate'] for g in groups if g['vat_rate'] is not None})
    values.update(vat_rate=rates[0] if len(rates)==1 else None,
        vat_breakdown=[{k:g[k] for k in ('net','vat','gross','vat_rate')} for g in groups] if not unknown else [],
        tax_treatment='special_review' if special else 'mixed' if len(groups)>1 else 'as_documented',
        tax_review_required=special, tax_review_note='Sonderfall/Importzuordnung konkret prüfen' if special else None,
        description=' · '.join(names)[:1000] or 'Strukturierter Rechnungsbeleg', category=None, business_use=None,
        pay_date=None, verification_basis=None)
    return {'validation': validation, 'metadata': values, 'document_type': document_type,
            'original_numbers': original_numbers,
            'tax_categories': sorted({g['category'] for g in groups})}


def embedded_xml(pdf: bytes):
    import pymupdf
    found=[]
    with pymupdf.open(stream=pdf,filetype='pdf') as doc:
        for name in doc.embfile_names():
            if name.lower().endswith('.xml'):
                data=doc.embfile_get(name)
                if syntax(xml_tree(data)): found.append(data)
    if len(found)>1: raise ValueError('Mehrere Rechnungs-XMLs im PDF; eindeutige Quelle erforderlich')
    return found[0] if found else None


def generate_xml(invoice: dict, draft=False):
    """Generate a standalone EN16931 UBL 2.1 document, not a claimed hybrid PDF."""
    credit=invoice.get('kind')=='credit_note'; ns=CREDIT if credit else UBL
    root=ET.Element(f'{{{ns}}}'+('CreditNote' if credit else 'Invoice'),nsmap={None:ns,'cbc':CBC,'cac':CAC})
    def b(parent,name,value,**attrs):
        e=ET.SubElement(parent,f'{{{CBC}}}'+name,**attrs);e.text=str(value);return e
    def a(parent,name):return ET.SubElement(parent,f'{{{CAC}}}'+name)
    def money(parent,name,value):return b(parent,name,f'{abs(Decimal(str(value))):.2f}',currencyID='EUR')
    number=invoice.get('number')
    if not number:
        if not draft:raise ValueError('Ausgestellte E-Rechnung benötigt endgültige Nummer')
        number='TEST-'+invoice['id'].split(':')[-1]
    b(root,'UBLVersionID','2.1');b(root,'CustomizationID','urn:cen.eu:en16931:2017')
    b(root,'ID',number);b(root,'IssueDate',invoice['date'])
    b(root,'CreditNoteTypeCode' if credit else 'InvoiceTypeCode','381' if credit else '380')
    if draft:b(root,'Note','TESTENTWURF: keine ausgestellte Rechnung; keine Nummer reserviert.')
    if invoice.get('reason'):b(root,'Note',invoice['reason'])
    b(root,'DocumentCurrencyCode','EUR')
    if invoice.get('original_number'):
        reference=a(a(root,'BillingReference'),'InvoiceDocumentReference');b(reference,'ID',invoice['original_number'])
        b(reference,'IssueDate',invoice['original_date'])
    for key,role in (('seller','AccountingSupplierParty'),('buyer','AccountingCustomerParty')):
        party=a(a(root,role),'Party');person=invoice[key]
        if key=='seller':b(a(party,'PartyIdentification'),'ID',person['tax_number'])
        address=a(party,'PostalAddress')
        b(address,'StreetName',person['street']);b(address,'CityName',person['city']);b(address,'PostalZone',person['postal_code'])
        b(a(address,'Country'),'IdentificationCode',person['country_iso'])
        if key=='seller':
            tax=a(party,'PartyTaxScheme');b(tax,'CompanyID',person['tax_number']);b(a(tax,'TaxScheme'),'ID','TAX')
            if person.get('vat_id'):
                tax=a(party,'PartyTaxScheme');b(tax,'CompanyID',person['vat_id']);b(a(tax,'TaxScheme'),'ID','VAT')
        b(a(party,'PartyLegalEntity'),'RegistrationName',person['name'])
    if invoice.get('delivery_date'):b(a(root,'Delivery'),'ActualDeliveryDate',invoice['delivery_date'])
    if not credit:
        b(a(root,'PaymentMeans'),'PaymentMeansCode','1')
        b(a(root,'PaymentTerms'),'Note','Bereits bezahlt; kein erneuter Zahlungsauftrag.')
    tax=a(root,'TaxTotal');money(tax,'TaxAmount',invoice['vat'])
    for group in invoice['vat_breakdown']:
        sub=a(tax,'TaxSubtotal');money(sub,'TaxableAmount',group['net']);money(sub,'TaxAmount',group['vat'])
        category=a(sub,'TaxCategory');b(category,'ID','E' if invoice.get('small_business',True) else 'S')
        b(category,'Percent',group['vat_rate'])
        if invoice.get('small_business',True):b(category,'TaxExemptionReason',invoice['seller']['tax_note'])
        b(a(category,'TaxScheme'),'ID','VAT')
    total=a(root,'LegalMonetaryTotal')
    for name,key in (('LineExtensionAmount','net'),('TaxExclusiveAmount','net'),('TaxInclusiveAmount','gross')):money(total,name,invoice[key])
    if not credit:money(total,'PrepaidAmount',invoice['gross'])
    money(total,'PayableAmount',invoice['gross'] if credit else '0.00')
    for index,p in enumerate(invoice['positions'],1):
        line=a(root,'CreditNoteLine' if credit else 'InvoiceLine');b(line,'ID',index)
        quantity=Decimal(str(p['quantity']))
        if quantity<=0:raise ValueError('E-Rechnung benötigt positive Mengen')
        b(line,'CreditedQuantity' if credit else 'InvoicedQuantity',quantity,unitCode='C62')
        money(line,'LineExtensionAmount',p['net'])
        item=a(line,'Item');b(item,'Name',p['title']);category=a(item,'ClassifiedTaxCategory')
        b(category,'ID','E' if invoice.get('small_business',True) else 'S');b(category,'Percent',p['vat_rate']);b(a(category,'TaxScheme'),'ID','VAT')
        price=a(line,'Price')
        # Exact line/base pair avoids unit-price rounding changing invoice totals.
        money(price,'PriceAmount',p['net']);b(price,'BaseQuantity',quantity,unitCode='C62')
    data=ET.tostring(root,encoding='UTF-8',xml_declaration=True,pretty_print=True)
    validation=validate_xml(data)
    if not validation['en16931_valid']:raise ValueError('E-Rechnung ungültig: '+', '.join(validation['errors']))
    return data,validation


def archive_xml(invoice, catalog, documents):
    """Bind original XML and validation evidence to the issued immutable record."""
    from autobookkeeping.archive import encoded, sha
    data, validation = generate_xml(invoice)
    base = f"{invoice['year']}/Rechnungen/{sha((invoice['id']+':'+sha(data)).encode())}"
    for suffix, payload, role in (('.xml', data, 'e_invoice_xml'),
                                  ('.validation.json', encoded(validation), 'e_invoice_validation')):
        name = base + suffix + '.enc'
        documents[name] = payload
        invoice['documents'].append(name)
        catalog['documents'][name] = {'record_id': invoice['id'], 'role': role,
                                      'sha256_plaintext': sha(payload), 'bytes_plaintext': len(payload)}
    invoice['e_invoice'] = dict(validation, format='EN16931 UBL 2.1', xml_sha256=sha(data))
