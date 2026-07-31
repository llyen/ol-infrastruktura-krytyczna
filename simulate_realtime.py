"""Symulator strumieni infrastruktury krytycznej do Microsoft Fabric Eventstream.

Tryb `--dry-run` dziala offline i nie wymaga pakietu `azure-eventhub`
ani zadnych poswiadczen — zapisuje zdarzenia do `datasets/derived/dry_run_*.jsonl`.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path

STREAM_FILES = {
    "ci_node_status": "ci_node_status.jsonl",
    "ci_operator_reports": "ci_operator_reports.jsonl",
    "hydro_readings": "hydro_readings.jsonl",
}
BASE = Path(__file__).resolve().parent
DATA = BASE / "datasets"
DERIVED = DATA / "derived"


def parse_time(value: str | None):
    return datetime.fromisoformat(value) if value else None


def iter_events(streams, start=None, end=None):
    for stream in streams:
        path = DATA / STREAM_FILES[stream]
        if not path.exists():
            raise SystemExit(f"Brak pliku {path}. Uruchom najpierw: python generate_datasets.py")
        with path.open(encoding="utf-8") as f:
            for line in f:
                event = json.loads(line)
                ts = parse_time(event["event_time"])
                if start and ts < start:
                    continue
                if end and ts > end:
                    continue
                event["_stream"] = stream
                event["_event_ts"] = ts
                yield event


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Wysylka strumieni IK (status wezlow, meldunki operatorow, hydrologia) do Eventstream/Event Hub.")
    parser.add_argument("--stream", action="append", choices=list(STREAM_FILES),
                        help="Nazwa strumienia, mozna powtorzyc. Domyslnie: wszystkie.")
    parser.add_argument("--speed", type=float, default=60.0,
                        help="Przyspieszenie czasu (60 = 1 minuta realna to 1 godzina scenariusza).")
    parser.add_argument("--from", dest="from_time", help="Poczatek okna ISO-8601, np. 2026-09-12T06:00+02:00")
    parser.add_argument("--to", dest="to_time", help="Koniec okna ISO-8601")
    parser.add_argument("--limit", type=int, help="Maksymalna liczba zdarzen.")
    parser.add_argument("--batch-size", type=int, default=250, help="Rozmiar paczki wysylanej do Event Hub.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Bez wysylki: zapis do datasets/derived/dry_run_<stream>.jsonl")
    args = parser.parse_args()

    streams = args.stream or list(STREAM_FILES)
    start, end = parse_time(args.from_time), parse_time(args.to_time)
    events = sorted(iter_events(streams, start, end), key=lambda e: e["_event_ts"])
    if args.limit:
        events = events[: args.limit]
    if not events:
        raise SystemExit("Brak zdarzen w podanym oknie czasowym.")
    print(f"Strumienie: {', '.join(streams)} | zdarzen: {len(events)} | "
          f"okno: {events[0]['_event_ts'].isoformat()} .. {events[-1]['_event_ts'].isoformat()}")

    if args.dry_run:
        DERIVED.mkdir(parents=True, exist_ok=True)
        handles = {s: (DERIVED / f"dry_run_{s}.jsonl").open("w", encoding="utf-8") for s in streams}
        try:
            for event in events:
                stream = event.pop("_stream")
                event.pop("_event_ts", None)
                handles[stream].write(json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n")
        finally:
            for h in handles.values():
                h.close()
        print(f"DRY-RUN: zapisano do {DERIVED}")
        return

    conn = os.environ.get("EVENTHUB_CONNECTION_STR")
    if not conn:
        raise SystemExit("Brak EVENTHUB_CONNECTION_STR. Uzyj --dry-run albo ustaw zmienna srodowiskowa.")
    from azure.eventhub import EventData, EventHubProducerClient  # import lokalny: dry-run bez zaleznosci

    producer = EventHubProducerClient.from_connection_string(
        conn, eventhub_name=os.environ.get("EVENTHUB_NAME"))
    sent, prev_ts = 0, None
    with producer:
        batch = producer.create_batch()
        for event in events:
            ts = event.pop("_event_ts")
            event.pop("_stream")
            if prev_ts is not None and args.speed > 0:
                delay = (ts - prev_ts).total_seconds() / args.speed
                if delay > 0:
                    time.sleep(min(delay, 5.0))
            prev_ts = ts
            data = EventData(json.dumps(event, ensure_ascii=False, separators=(",", ":")))
            try:
                batch.add(data)
            except ValueError:
                producer.send_batch(batch)
                batch = producer.create_batch()
                batch.add(data)
            sent += 1
            if len(batch) >= args.batch_size:
                producer.send_batch(batch)
                batch = producer.create_batch()
            if sent % 5000 == 0:
                print(f"wyslano {sent} zdarzen...")
        if len(batch):
            producer.send_batch(batch)
    print(f"Zakonczono. Wyslano {sent} zdarzen.")


if __name__ == "__main__":
    main()
