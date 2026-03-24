# XML Sample Files — Parsing Reference

This document describes the 8 DIAN UBL 2.1 electronic invoice samples used to validate and adjust the XML parsing algorithm (`app/utils/xml_parser.py`).

---

## Document Structure (all files)

All files are `AttachedDocument` wrappers. The actual `Invoice` XML is embedded inside CDATA within `cbc:Description` under `cac:Attachment/cac:ExternalReference`. The parser must extract and parse the inner Invoice, not the outer AttachedDocument.

The DIAN validation response (`ApplicationResponse`) is embedded in a second `cac:ParentDocumentLineReference/cac:DocumentReference/cac:Attachment` block.

Key totals appear in a `<cbc:Note>` that begins with `NumFac:` — this is the QR code string containing:
`ValFac` (subtotal), `ValIva`, `ValOtroIm`, `ValTolFac` (total), `CUFE`

---

## Tax Scheme IDs

| ID  | Name          | Element used              |
|-----|---------------|---------------------------|
| 01  | IVA           | `cac:TaxTotal`            |
| 06  | ReteRenta     | `cac:WithholdingTaxTotal` |
| 07  | ReteICA       | `cac:WithholdingTaxTotal` |
| 22  | INC Bolsas    | `cac:TaxTotal`            |
| ZZ  | No aplica     | absent or empty           |

---

## Scenarios

### 1. `factura normal.xml` — Mixed IVA (taxed + exempt items)

- **Issuer:** D1 SAS (NIT 900276962)
- **Receiver:** IKBO S.A.S. (901031352)
- **Invoice:** G3Z8203074 — 2026-03-02
- **Lines:** 2
  - JUGO DE MANDARINA TR: $6,294.12 base → IVA 19% → $1,195.88
  - AGUA SIN GAS OMI 500: $3,400 — IVA exempt (TaxScheme ZZ, `cbc:Percent=0`)
- **Totals:** ValFac=$9,694.12, ValIva=$1,195.88, ValTolFac=$10,890
- **Payment:** `PaymentMeansCode=49` (tarjeta débito)
- **Parsing notes:**
  - Single `cac:TaxTotal` at document level for IVA only
  - Exempt line still has a `cac:TaxTotal` per-line with `Percent=0` and `TaxScheme/ID=ZZ`
  - POS-style: multiple `<cbc:Note>` fields encoded as `Nota1`, `Nota4`, etc.
  - `cbc:InvoicedQuantity unitCode="94"` (units)

---

### 2. `factura con descuento.xml` — Line-level discounts

- **Issuer:** EDITORIAL NUEVA LEGISLACION SAS (NIT 901760399)
- **Receiver:** IKBO S.A.S. (901031352)
- **Invoice:** FENL8534 — 2026-03-09
- **Lines:** 2 (SEMINARIO courses, each with 10% discount)
  - Line 1: list price $220,000, discount $22,000 → net $198,000 → IVA 19% $37,620
  - Line 2: list price $200,000, discount $20,000 → net $180,000 → IVA 19% $34,200
- **Totals:** ValFac=$378,000, ValIva=$71,820, ValTolFac=$449,820
- **Payment:** `PaymentMeansCode=10` (contado)
- **Parsing notes:**
  - Each line has `cac:AllowanceCharge` with `cbc:ChargeIndicator=false` (it's a discount, not a surcharge)
  - `cbc:MultiplierFactorNumeric=0.10` (10%), `cbc:Amount` = discount value
  - `cbc:LineExtensionAmount` already reflects the post-discount net amount
  - `cbc:BaseAmount` on `AllowanceCharge` = original list price before discount

---

### 3. `factura con impuesto de bolsa.xml` — Plastic bag tax (INC Bolsas)

- **Issuer:** CRIYA SAS (NIT 800200139)
- **Receiver:** IKBO S.A.S. (901031352)
- **Invoice:** SC242838 — 2026-02-25
- **Lines:** 4 (3 products + 1 plastic bag)
  - Products: IVA 19%, `LineExtensionAmount` > 0
  - Bag line (BMTB): `FreeOfChargeIndicator=true`, `LineExtensionAmount=0`, TaxScheme ID=22
- **Totals:** ValFac=base products, ValIva=$85,739.78, ValOtroIm=$146.00 (bag tax)
- **Parsing notes:**
  - Two separate `cac:TaxTotal` blocks at document level: one for IVA (ID=01), one for INC Bolsas (ID=22)
  - Bag tax uses `cbc:PerUnitAmount=73.00` and `cbc:BaseUnitMeasure` — **no `cbc:Percent`**
  - `cbc:PricingReference/cac:AlternativeConditionPrice` holds the reference price for free items
  - `cbc:FreeOfChargeIndicator=true` signals a $0 line that still has a tax

---

### 4. `factura con retenciones.xml` — Withholding taxes (no IVA)

- **Issuer:** PLANINCO COMERCIAL S.A.S. (NIT 900873779)
- **Receiver:** IKBO S.A.S. (901031352)
- **Invoice:** PLCO1353 — 2026-03-05
- **Lines:** 1 (CANON DE ARRENDAMIENTO PERSONA JURIDICA, $2,488,970)
- **Taxes:** No IVA — only `cac:WithholdingTaxTotal`:
  - ReteRenta (ID=06): 3.5% → $87,113.95
  - ReteICA (ID=07): 0.966% → $24,043.45
- **Totals:** ValFac=$2,488,970, ValIva=0, ValTolFac=$2,488,970 (retenciones reduce what debtor pays, not added to total)
- **Payment:** `PaymentMeansCode=31` (crédito), `DueDate=2026-03-06`
- **Parsing notes:**
  - `cac:TaxTotal` is **absent** — do not assume it always exists
  - `cac:WithholdingTaxTotal` (not `TaxTotal`) holds retention data
  - `TaxExclusiveAmount=0` and `TaxInclusiveAmount=TaxExclusiveAmount` when no IVA
  - Issuer `TaxLevelCode=O-13;O-23` (gran contribuyente + agente retenedor) — explains why retenciones appear

---

### 5. `factura de servicio de internet.xml` — Service invoice, credit billing

- **Issuer:** COMCEL S.A. (NIT 800153993)
- **Receiver:** IKBO S.A.S. (901031352)
- **Invoice:** R1143617915 — 2026-03-02
- **Lines:** 1 (INTERNET, $110,420 base → IVA 19% → $20,981)
- **Totals:** ValFac=$110,420, ValIva=$20,981, ValTolFac=$131,401
- **Payment:** `PaymentDueDate=2026-03-18` (billing cycle, credit)
- **Parsing notes:**
  - Invoice line has **no `cac:StandardItemIdentification`** — field is optional
  - `cac:TaxTotal` has `cbc:RoundingAmount` ($0.0008) — handle rounding field gracefully
  - Notes contain service details: `Referencia de pago`, `Deuda anterior`, `Retefuente=0`
  - Signed by CERTICAMARA (different CA than most other files)

---

### 6. `factura servicio publico.xml` — Public utility (gas), no IVA, non-standard units

- **Issuer:** ALCANOS DE COLOMBIA S.A. E.S.P. (NIT 891101577)
- **Receiver:** ALTIMA CAPITAL INVERSIONES S.A.S. (900221995) — *not IKBO*
- **Invoice:** FACT22284806 — 2026-03-10
- **Lines:** 1 (FE CONSUMO RANGO 1 — gas consumption)
  - Quantity: 2.84 `unitCode=MTQ` (cubic meters)
  - Unit price: $4,791.39/m³ → `LineExtensionAmount=$13,607.55`
- **Totals:** ValFac=$13,607.55, ValIva=0, ValTolFac=$13,608 (rounded up)
- **Parsing notes:**
  - **No `cac:TaxTotal`** element at all — TaxScheme ID=ZZ ("No aplica")
  - `cbc:PayableRoundingAmount=0.45` — rounding adjustment present at document level
  - `cbc:InvoicedQuantity unitCode="MTQ"` — cubic meters, not standard unit `94`
  - Note contains subsidy info as JSON-like string: `{ Name = Subsidio, PriceAmount = -1504.975352, ... }`
  - Contains `<sts:CustomTagGeneral/>` extension tag (ignore safely)
  - `cac:InformationContentProviderParty` inside `cac:Item` (non-standard, skip)
  - `cbc:AdditionalAccountID=1` for supplier (persona jurídica)

---

### 7. `factura sin iva.xml` — No IVA, natural person issuer

- **Issuer:** KAREN RINCON ACOSTA (cédula 1026288579) — trade name: Monster Cakes
- **Receiver:** IKBO S.A.S. (901031352)
- **Invoice:** FE7674 — 2026-03-05
- **Lines:** 2
  - Torta pie de limon: $37,900
  - Domicilio (delivery): $10,000
- **Totals:** ValFac=$47,900, ValIva=0, ValTolFac=$47,900
- **Payment:** `PaymentMeansCode=1` (crédito), DueDate=2026-03-20
- **Parsing notes:**
  - **No `cac:TaxTotal`** — TaxScheme ZZ on all lines
  - `cbc:AdditionalAccountID=2` on supplier — persona natural (individual, not company)
  - Supplier ID uses `schemeID="13"` (cédula de ciudadanía), not `schemeID="31"` (NIT)
  - No `cac:StandardItemIdentification` on any line
  - No trade name in `cac:PartyName` — look at `cac:PartyLegalEntity/cbc:RegistrationName` for trade name

---

### 8. `factura varios items iva.xml` — Multiple lines, all IVA 19%, prorated rental amounts

- **Issuer:** Milenio PC S.A. (NIT 830067005)
- **Receiver:** IKBO S.A.S. (901031352)
- **Invoice:** BO138423 — 2026-03-10
- **Lines:** 20 (laptop rental items — `cbc:LineCountNumeric=20`)
  - All items: laptop computers (`Computador Portatil/Portátil`)
  - All IVA 19%, `unitCode=NAR`
  - Some lines have prorated amounts (partial month): e.g., line 6 = 26 days, line 12 = 3 days
  - Line notes encode rental period: `ITE_10|2026-02-01|2026-02-28` and `NTI_1||30` (days)
- **Totals:** ValFac=$2,529,098, ValIva=$480,529, ValTolFac=$3,009,627
- **Payment:** `PaymentMeansCode=ZZZ`, DueDate=2026-04-09
- **Parsing notes:**
  - Each `InvoiceLine` has its own `cac:TaxTotal` — AND there is a single document-level `cac:TaxTotal`
  - Document-level `TaxTotal` aggregates all line taxes; do not double-count
  - `cac:StandardItemIdentification/cbc:ID` = `ALQ` with `schemeID=999` — non-standard product code (alquiler)
  - `cac:SellersItemIdentification` holds the internal product ID
  - File size is large (>25K tokens); the parser must handle long documents without truncation

---

## Edge Case Summary

| Scenario                  | `cac:TaxTotal` | `cac:WithholdingTaxTotal` | `AllowanceCharge` | `FreeOfChargeIndicator` | unitCode |
|---------------------------|:--------------:|:--------------------------:|:-----------------:|:-----------------------:|:--------:|
| factura normal            | ✓ (IVA)        | —                          | —                 | —                       | 94       |
| factura con descuento     | ✓ (IVA)        | —                          | ✓                 | —                       | 94       |
| factura con impuesto bolsa| ✓ (IVA + INC)  | —                          | —                 | ✓                       | 94       |
| factura con retenciones   | —              | ✓ (ReteRenta + ReteICA)    | —                 | —                       | 94       |
| factura internet          | ✓ (IVA)        | —                          | —                 | —                       | 94       |
| factura servicio publico  | —              | —                          | —                 | —                       | MTQ      |
| factura sin iva           | —              | —                          | —                 | —                       | 94       |
| factura varios items iva  | ✓ (IVA, x20+1) | —                          | —                 | —                       | NAR      |
