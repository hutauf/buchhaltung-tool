"""Conservative eleven-year review policy. Never delete originals or Git history."""
from datetime import date
import hashlib

YEARS = 11
DATE_FIELDS = {'date', 'pay_date', 'issued_at', 'recorded_at', 'booked_at', 'discarded_at',
               'created_at', 'updated_at', 'at', 'delivery_date', 'service_period_end'}


def dates(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in DATE_FIELDS and isinstance(item, str):
                try: yield date.fromisoformat(item[:10])
                except ValueError: pass
            elif isinstance(item, (dict, list)):yield from dates(item)
    elif isinstance(value, list):
        for item in value:yield from dates(item)


def report(catalog, as_of=None):
    """Review horizon only: statutory extensions/holds require separate review."""
    as_of = date.fromisoformat(as_of) if as_of else date.today()
    rows=[]
    by_document={name:[] for name in catalog.get('documents',{})}
    by_record={}
    def collect(value):
        if isinstance(value,dict):
            names=value.get('documents',[])
            if isinstance(names,list):
                for name in names:
                    if name in by_document:by_document[name].extend(dates(value))
                if value.get('id'):by_record.setdefault(value['id'],set()).update(names)
            receipt=value.get('receipt_candidate')
            if isinstance(receipt,dict) and receipt.get('document') in by_document:
                by_document[receipt['document']].extend(dates(value))
            for child in value.values():
                if isinstance(child,(dict,list)):collect(child)
        elif isinstance(value,list):
            for child in value:collect(child)
    collect(catalog)
    # Payments/corrections can extend retention of their referenced original.
    def references(value):
        if isinstance(value,dict):
            for key in ('record_id','original_id','invoice_id'):
                for name in by_record.get(value.get(key),()):
                    if name in by_document:by_document[name].extend(dates(value))
            for child in value.values():
                if isinstance(child,(dict,list)):references(child)
        elif isinstance(value,list):
            for child in value:references(child)
    references(catalog)
    for event_id, correction in catalog.get('cash_event_voids',{}).items():
        record_id=catalog.get('cash_events',{}).get(event_id,{}).get('record_id')
        for name in by_record.get(record_id,()):
            if name in by_document:by_document[name].extend(dates(correction))
    for name in sorted(catalog.get('documents',{})):
        latest=max(by_document[name],default=None)
        horizon=date(latest.year+YEARS+1,1,1) if latest and latest.year+YEARS+1<=9999 else None
        rows.append({'document_ref':hashlib.sha256(name.encode()).hexdigest(),
                     'earliest_review':horizon.isoformat() if horizon else None,
                     'review_possible':bool(horizon and as_of>=horizon),
                     'deletion_authorized':False})
    return {'retention_years':YEARS,'as_of':as_of.isoformat(),'automatic_deletion':False,
            'policy':'At least eleven complete calendar years after the latest relevant document event; holds extend retention. Review is not deletion approval.',
            'documents':rows}
