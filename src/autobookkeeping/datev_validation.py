"""Independent parser checks for the restricted EXTF 700/13 profile we produce."""
from __future__ import annotations
import csv
import io
import re
from datetime import datetime


def validate(data):
    text = data.decode('cp1252', errors='strict')
    if not text.endswith('\r\n') or '\n' in text.replace('\r\n', '') or '\r' in text.replace('\r\n', ''):
        raise ValueError('DATEV benötigt CR/LF-Zeilenenden')
    if any(ord(c) < 32 and c not in '\r\n' or ord(c) == 127 for c in text): raise ValueError('DATEV-Steuerzeichen')
    rows = list(csv.reader(io.StringIO(text, newline=''), delimiter=';', strict=True))
    if any(any(ord(char) < 32 or ord(char) == 127 for char in field) for row in rows for field in row):
        raise ValueError('Steuerzeichen innerhalb eines DATEV-Felds')
    if len(rows) < 3: raise ValueError('DATEV-Stapel enthält keine Buchung')
    head, columns, *bookings = rows
    if (len(head) != 31 or head[:5] != ['EXTF','700','21','Buchungsstapel','13']
        or len(columns) != 125 or not 1 <= len(bookings) <= 99999): raise ValueError('DATEV-Version oder Feldanzahl falsch')
    if not re.fullmatch(r'20[0-9]{15}', head[5]): raise ValueError('DATEV-Exportzeitpunkt falsch')
    datetime.strptime(head[5][:14], '%Y%m%d%H%M%S')
    if not re.fullmatch(r'[1-9][0-9]{3,6}', head[10]) or not 1001 <= int(head[10]) <= 9999999:
        raise ValueError('DATEV-Beraternummer falsch')
    if not re.fullmatch(r'[1-9][0-9]{0,4}', head[11]): raise ValueError('DATEV-Mandantennummer falsch')
    year = head[12][:4]
    if (head[12] != year+'0101' or head[13] != '4' or head[14] != year+'0101' or head[15] != year+'1231'
        or head[18] not in ('1','2') or head[19:22] != ['30','0','EUR'] or head[26] != '03'):
        raise ValueError('DATEV-Kalenderjahr, SKR03 oder Importoptionen falsch')
    # Our profile has no foreign-currency, VAT, OPOS, bank or external-document fields.
    allowed = {0,1,2,6,7,9,10,13,20,21,22,23,24,25,41,113}
    refs = set()
    for fields in bookings:
        if len(fields) != 125: raise ValueError('DATEV-Buchungszeile braucht 125 Felder')
        if any(value for index,value in enumerate(fields) if index not in allowed): raise ValueError('Nicht unterstütztes DATEV-Feld befüllt')
        if not re.fullmatch(r'[0-9]{1,10},[0-9]{2}', fields[0]) or fields[0].strip('0,') == '': raise ValueError('DATEV-Umsatz muss positiv sein')
        if fields[1] not in ('S','H') or fields[2] != 'EUR' or fields[41] != 'K' or fields[113] != '0': raise ValueError('DATEV-Soll/Haben, Steuer- oder Festschreibungskennzeichen falsch')
        if not all(re.fullmatch(r'[1-9][0-9]{3}', fields[i]) for i in (6,7)) or fields[6] == fields[7]: raise ValueError('DATEV-Konto/Gegenkonto falsch')
        if not re.fullmatch(r'[0-9]{4}', fields[9]): raise ValueError('DATEV-Datum muss TTMM sein')
        datetime.strptime(year+fields[9][2:4]+fields[9][:2], '%Y%m%d')
        if not re.fullmatch(r'[A-Za-z0-9$&%*+\-/]{1,36}', fields[10]) or len(fields[13]) > 60:
            raise ValueError('DATEV-Belegnummer oder Buchungstext unzulässig')
        if fields[20] != 'Archiv-Referenz' or not re.fullmatch(r'[a-f0-9]{20}', fields[21]) or fields[21] in refs:
            raise ValueError('DATEV-Archivbezug fehlt oder ist doppelt')
        for index, label in ((22, 'Geschäftspartner'), (24, 'Original-Belegnummer')):
            if fields[index] or fields[index+1]:
                if fields[index] != label or not 1 <= len(fields[index+1]) <= 210:
                    raise ValueError('DATEV-Beleginformation unzulässig')
        refs.add(fields[21])
    return {'ok': True, 'format': 'EXTF 700/13', 'rows': len(bookings), 'encoding': 'Windows-1252', 'year': int(year)}
