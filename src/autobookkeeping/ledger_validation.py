"""Financial links, immutable numbering and explicit cash events, in cents."""
from decimal import Decimal
from autobookkeeping.taxes import decimal_money


def validate(catalog):
    from autobookkeeping.homeoffice import validate as validate_homeoffice
    validate_homeoffice(catalog)
    from autobookkeeping.backups import validate as validate_backups
    from autobookkeeping.reconciliation import validate as validate_reconciliation
    validate_backups(catalog)
    validate_reconciliation(catalog)
    records = {key:value["current"] for key,value in catalog["records"].items()}
    numbers = set(); credits = {}
    for key,row in records.items():
        if row.get('kind') == 'expense_credit':
            original=records.get(row.get('original_id'),{})
            if original.get('kind') != 'expense' or original.get('number') != row.get('original_number'):
                raise ValueError('Lieferanten-Korrektur hat keinen eindeutigen Originalbezug')
            from autobookkeeping.receipts import normalized, supplier
            if not supplier(original) or normalized(supplier(original)) != normalized(supplier(row)):
                raise ValueError('Lieferanten-Korrektur hat einen anderen Lieferanten')
            amounts = [Decimal(row[f]) for f in ('gross','net','vat')]
            if (any(not a.is_finite() or a != a.quantize(Decimal('.01')) for a in amounts)
                or amounts[0] >= 0 or any(a > 0 for a in amounts) or amounts[0] != amounts[1]+amounts[2]
                or row.get('currency','EUR') != original.get('currency','EUR')
                or row['date'][:10] < original['date'][:10]):
                raise ValueError('Lieferanten-Korrektur hat ungültige Beträge, Währung oder Datum')
            for field in ('gross','net','vat'):
                total=credits.setdefault(('expense:'+row['original_id'],field),Decimal(0))+Decimal(row[field])
                credits[('expense:'+row['original_id'],field)]=total
                if not -Decimal(original[field])<=total<=0:
                    raise ValueError('Lieferanten-Minderung übersteigt Originalbetrag/Steuer')
            if original.get('vat_breakdown'):
                groups=row.get('vat_breakdown',[])
                if not groups or any(sum((Decimal(g[f]) for g in groups),Decimal(0)) != Decimal(row[f]) for f in ('gross','net','vat')):
                    raise ValueError('Steuergruppen der Lieferanten-Korrektur fehlen oder stimmen nicht')
                for group in groups:
                    for field in ('gross','net','vat'):
                        value=Decimal(group[field])
                        available=sum((Decimal(g[field]) for g in original['vat_breakdown'] if g['vat_rate']==group['vat_rate']),Decimal(0))
                        key=('expense-group:'+row['original_id'],group['vat_rate'],field)
                        total=credits.get(key,Decimal(0))+value;credits[key]=total
                        if value>0 or not -available<=total<=0:
                            raise ValueError('Steuergruppen-Minderung übersteigt Originalgruppe')
        if row.get("kind") in ("invoice", "credit_note") and row.get("number"):
            number = str(row["number"])
            if number in numbers:
                raise ValueError("Doppelte Rechnungs-/Stornonummer")
            numbers.add(number)
        if row.get("kind") in ("credit_note", "correction"):
            original = records.get(row.get("original_id"), {})
            if original.get("kind") != "invoice" or original.get("number") != row.get("original_number"):
                raise ValueError("Korrektur hat keinen eindeutigen Originalbezug")
            if row["kind"] == "credit_note":
                for field in ("gross", "net", "vat"):
                    total = credits.setdefault((row["original_id"],field), Decimal(0)) + Decimal(row[field])
                    credits[(row["original_id"],field)] = total
                    if not -Decimal(original[field]) <= total <= 0:
                        raise ValueError("Minderung übersteigt Originalbetrag/Steuer")
            elif any(Decimal(row[field]) for field in ("gross", "net", "vat")):
                raise ValueError("Formale Berichtigung darf keine Geldbeträge ändern")
        if row.get("source") == "local" and row.get("positions"):
            for field in ("gross", "net", "vat"):
                if sum((Decimal(p[field]) for p in row["positions"]), Decimal(0)) != Decimal(row[field]):
                    raise ValueError("Lokale Positionen stimmen nicht mit Gesamtsumme überein")
    events = catalog.get("cash_events", {}); voids = catalog.get("cash_event_voids", {})
    if not set(voids) <= set(events):
        raise ValueError("Zahlungsberichtigung verweist auf fehlenden Eintrag")
    totals = {}
    for eid,event in events.items():
        row = records.get(event["record_id"], {})
        if row.get("kind") not in ("invoice", "credit_note", "expense", "expense_credit"):
            raise ValueError("Zahlung verweist auf fehlenden Geldbeleg")
        if event["record_id"] not in catalog.get("cash_source_overrides", {}):
            raise ValueError("Manuelle Zahlungsquelle nicht eindeutig zugeordnet")
        expected_bucket = "expense" if row["kind"] in ("expense", "expense_credit") else "income"
        if event["bucket"] != expected_bucket:
            raise ValueError("Zahlungsart passt nicht zum Beleg")
        if row['kind']=='expense_credit' and decimal_money(event['amount'])<=0:
            raise ValueError('Lieferanten-Erstattung muss positiv sein')
        if eid not in voids:
            totals[event["record_id"]] = totals.get(event["record_id"],Decimal(0)) + decimal_money(event["amount"])
    for rid,total in totals.items():
        row = records[rid]; limit = abs(Decimal(row["gross"]))
        if (row["kind"] in ('invoice','expense_credit') and not 0 <= total <= limit) or (row["kind"] not in ('invoice','expense_credit') and not -limit <= total <= 0):
            raise ValueError("Zahlungssumme übersteigt Belegbetrag")
    if not set(catalog.get("cash_source_overrides", {})) <= set(records):
        raise ValueError("Zahlungsquelle verweist auf fehlenden Beleg")
