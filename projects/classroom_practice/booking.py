"""Equipment reservations: intervals, transactions, idempotency and ownership.

Local teaching service only. A student string is NOT authenticated identity.
An actual web deployment must derive identity server-side, never trust a form.
"""
from __future__ import annotations
from datetime import datetime, timezone
import re
import sqlite3


def identifier(value: str) -> str:
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',value):
        raise ValueError('invalid identifier')
    return value


def timestamp(value: str) -> int:
    if not isinstance(value,str) or len(value)>40:
        raise ValueError('invalid timestamp')
    try:
        parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
        if parsed.utcoffset() is None or parsed.microsecond:
            raise ValueError('explicit timezone and whole seconds required')
        return int(parsed.astimezone(timezone.utc).timestamp())
    except (ValueError,OverflowError,OSError) as exc:
        raise ValueError('timestamp must be ISO 8601 with explicit timezone') from exc


class BookingStore:
    def __init__(self,path=':memory:'):
        self.db=sqlite3.connect(path,timeout=5,isolation_level=None)
        self.db.row_factory=sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS equipment(id TEXT PRIMARY KEY, name TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS bookings(
            request_id TEXT PRIMARY KEY, student TEXT NOT NULL,
            equipment TEXT NOT NULL REFERENCES equipment(id), start INTEGER NOT NULL,
            end INTEGER NOT NULL CHECK(end>start),
            status TEXT NOT NULL CHECK(status IN ('confirmed','cancelled')));
        CREATE INDEX IF NOT EXISTS booking_intervals ON bookings(equipment,status,start,end);
        ''')

    def seed(self):
        self.db.executemany('INSERT OR IGNORE INTO equipment VALUES(?,?)',
                           [('camera-01','教学摄像头'),('robot-01','教学机器人套件')])

    def close(self): self.db.close()

    def list_bookings(self):
        return [dict(row) for row in self.db.execute('SELECT * FROM bookings ORDER BY start,request_id')]

    def reserve(self,request_id,student,equipment,start,end):
        request_id,student,equipment=map(identifier,(request_id,student,equipment))
        start,end=timestamp(start),timestamp(end)
        if not 0<end-start<=8*3600:
            raise ValueError('reservation must last more than zero and at most eight hours')
        self.db.execute('BEGIN IMMEDIATE')
        try:
            previous=self.db.execute('SELECT * FROM bookings WHERE request_id=?',(request_id,)).fetchone()
            if previous:
                if (previous['student'],previous['equipment'],previous['start'],previous['end'])!=(student,equipment,start,end):
                    raise ValueError('request id already used with a different payload')
                self.db.commit()
                return dict(previous)  # A cancelled request is not silently reactivated.
            if not self.db.execute('SELECT 1 FROM equipment WHERE id=?',(equipment,)).fetchone():
                raise ValueError('unknown equipment')
            # Half-open intervals [start,end): adjacent reservations are valid.
            conflict=self.db.execute('''SELECT 1 FROM bookings WHERE equipment=?
                AND status='confirmed' AND start < ? AND end > ? LIMIT 1''',(equipment,end,start)).fetchone()
            if conflict: raise ValueError('reservation conflict')
            self.db.execute("INSERT INTO bookings VALUES(?,?,?,?,?,'confirmed')",(request_id,student,equipment,start,end))
            result=dict(self.db.execute('SELECT * FROM bookings WHERE request_id=?',(request_id,)).fetchone())
            self.db.commit()
            return result
        except Exception:
            self.db.rollback()
            raise

    def cancel(self,request_id,student,*,confirmed):
        if confirmed is not True: raise ValueError('explicit boolean confirmation required')
        request_id,student=map(identifier,(request_id,student))
        self.db.execute('BEGIN IMMEDIATE')
        try:
            row=self.db.execute('SELECT * FROM bookings WHERE request_id=? AND student=?',(request_id,student)).fetchone()
            if row is None: raise ValueError('reservation not found for this student')
            self.db.execute("UPDATE bookings SET status='cancelled' WHERE request_id=?",(request_id,))
            result=dict(self.db.execute('SELECT * FROM bookings WHERE request_id=?',(request_id,)).fetchone())
            self.db.commit()
            return result
        except Exception:
            self.db.rollback()
            raise
