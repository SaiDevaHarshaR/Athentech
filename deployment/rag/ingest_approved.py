"""Offline approved knowledge importer. Run only under restricted admin access.

Usage:
  python -m deployment.rag.ingest_approved --institution KLIS --audience b2c \
    --title 'Approved FAQ' --file approved_faq.txt --approver 'admin'

B2B requires --organization. No patient reports, private LIS or PHI ingestion.
"""
import argparse
from pathlib import Path
from rag.store import ingest_approved_text


def main():
    p = argparse.ArgumentParser(description='Ingest manually approved plain-text knowledge')
    p.add_argument('--institution', required=True)
    p.add_argument('--audience', choices=['b2c', 'b2b'], required=True)
    p.add_argument('--organization')
    p.add_argument('--file', required=True)
    p.add_argument('--title', required=True)
    p.add_argument('--approver', required=True)
    p.add_argument('--replace', action='store_true')
    args = p.parse_args()
    path = Path(args.file).resolve(strict=True)
    if path.suffix.lower() not in ('.txt', '.md'):
        p.error('Only reviewed .txt and .md documents are supported')
    if path.stat().st_size > 500_000:
        p.error('Document is too large')
    if args.audience == 'b2b' and not args.organization:
        p.error('B2B requires --organization')
    print(ingest_approved_text(institution=args.institution, audience=args.audience,
          organization=args.organization, title=args.title,
          text=path.read_text(encoding='utf-8'), approver=args.approver, replace=args.replace))


if __name__ == '__main__':
    main()
