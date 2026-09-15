#!/usr/bin/env python3
"""Scellement herite indisponible : implementation historique conservee dans Git.

Le gardien isole et la transaction de scellement doivent etre qualifies avant
reintroduction. Ce module ne cherche aucune cle ni observation.
"""

def main() -> int:
    print('Scellement indisponible : gardien isole et transaction non qualifies.')
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
