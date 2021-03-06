#!/usr/bin/env python3
"""
Generate mock samples for Recentrifuge testing
"""

import argparse
import collections as col
import os
import random
import sys
from typing import Counter

from recentrifuge.centrifuge import select_centrifuge_inputs
from recentrifuge.config import Filename, TaxId
from recentrifuge.config import NODES_FILE, NAMES_FILE
from recentrifuge.config import TAXDUMP_PATH
from recentrifuge.config import gray, red, green, yellow, blue, cyan
from recentrifuge.taxonomy import Taxonomy

# optional package pandas (to read Excel with mock layout)
_USE_PANDAS = True
try:
    import pandas as pd
except ImportError:
    pd = None
    _USE_PANDAS = False

__version__ = '0.2.0'
__author__ = 'Jose Manuel Marti'
__date__ = 'Jan 2018'

MAX_HIT_LENGTH: int = 200  # Max hit length for random score generation


def main():
    """Main entry point to recentrifuge."""

    def vprint(*args):
        """Print only if verbose/debug mode is enabled"""
        if debug:
            print(*args, end='')
            sys.stdout.flush()

    def configure_parser():
        """Argument Parser Configuration"""
        parser = argparse.ArgumentParser(
            description='Generate mock samples for Recentrifuge testing',
            epilog=f'%(prog)s  - {__author__} - {__date__}',
            formatter_class=argparse.ArgumentDefaultsHelpFormatter
        )
        parser_mode = parser.add_mutually_exclusive_group(required=True)
        parser_mode.add_argument(
            '-f', '--file',
            action='store',
            metavar='FILE',
            type=Filename,
            help='Explicit source: Centrifuge output file as source'
        )
        parser_mode.add_argument(
            '-r', '--random',
            action='store',
            metavar='MHL',
            type=int,
            default=15,
            help=('Random score generated. Please provide the minimum hit '
                  'length (mhl) of the classification; 15 by default')
        )
        parser.add_argument(
            '-g', '--debug',
            action='store_true',
            help='increase output verbosity and perform additional checks'
        )
        parser_input = parser.add_mutually_exclusive_group(required=True)
        parser_input.add_argument(
            '-m', '--mock',
            action='append',
            metavar='FILE',
            type=Filename,
            help=('Mock files to be read for mock Centrifuge sequences layout.'
                  ' If a single directory is entered, every .out file inside '
                  'will be taken as a different sample. '
                  'Multiple -f is available to include several samples.')
        )
        if _USE_PANDAS:
            parser_input.add_argument(
                '-x', '--xcel',
                action='store',
                metavar='FILE',
                type=Filename,
                help='Excel file with the mock layout.'
            )
        parser.add_argument(
            '-n', '--nodespath',
            action='store',
            metavar='PATH',
            default=TAXDUMP_PATH,
            help=('path for the nodes information files '
                  '(nodes.dmp and names.dmp from NCBI)')
        )
        parser.add_argument(
            '-V', '--version',
            action='version',
            version=f'%(prog)s release {__version__} ({__date__})'
        )
        return parser

    def check_debug():
        """Check debugging mode"""
        if args.debug:
            print(gray('INFO: Debugging mode activated\n'))

    def read_mock_files(mock: Filename) -> Counter[TaxId]:
        """Read a mock layout (.mck) file"""
        mock_layout: Counter[TaxId] = col.Counter()
        with open(mock, 'r') as file:
            vprint(gray('\nProcessing'), blue(mock), gray('file:\n'))
            for line in file:
                if line.startswith('#'):
                    continue
                _tid, _num = line.split('\t')
                tid = TaxId(_tid)
                num = int(_num)
                mock_layout[tid] = num
                vprint(num, gray('\treads for taxid\t'), tid, '\t(',
                       cyan(ncbi.get_name(tid)), ')\n')
        return mock_layout

    def mock_from_source(out: Filename, mock_layout: Counter[TaxId]) -> None:
        """Generate a mock Centrifuge output file from source file"""
        with open(out, 'w') as fout, open(args.file) as fcfg:
            vprint(gray('Generating'), blue(out), gray('file... '))
            fout.write(fcfg.readline())  # copy cfg output file header
            reads_writen: int = 0
            for line in fcfg:
                tid = TaxId(line.split('\t')[2])
                if mock_layout[tid]:
                    fout.write(line)
                    mock_layout[tid] -= 1
                    reads_writen += 1
                    if not sum(mock_layout.values()):
                        vprint(reads_writen, 'reads', green('OK!\n'))
                        break
        if sum(mock_layout.values()):
            print(red('ERROR!\n'))
            print(gray('Incomplete read copy by taxid:'))
            mock_layout = +mock_layout  # Delete zero counts elements
            for tid in mock_layout:
                print(yellow(mock_layout[tid]), gray('reads missing for tid'),
                      tid, '(', cyan(ncbi.get_name(tid)), ')\n')

    def mock_from_scratch(out: Filename, mock_layout: Counter[TaxId]) -> None:
        """Generate a mock Centrifuge output file from scratch"""
        with open(out, 'w') as fout:
            vprint(gray('Generating'), blue(out), gray('file... '))
            fout.write('readID\tseqID\ttaxID\tscore\t2ndBestScore\t'
                       'hitLength\tqueryLength\tnumMatches\n')
            reads_writen: int = 0
            for tid in mock_layout:
                maxhl: int = random.randint(args.random + 1, MAX_HIT_LENGTH)
                rank: str = str(ncbi.get_rank(tid)).lower()
                for _ in range(mock_layout[tid]):
                    hit_length = random.randint(args.random + 1, maxhl)
                    fout.write(f'test{reads_writen}\t{rank}\t'
                               f'{tid}\t{(hit_length-15)**2}\t'
                               f'0\t{hit_length}\t{MAX_HIT_LENGTH}\t1\n')
                    reads_writen += 1
            vprint(reads_writen, 'reads', green('OK!\n'))

    def by_mock_files() -> None:
        """Do the job in case of mock files"""
        if len(args.mock) == 1 and os.path.isdir(args.mock[0]):
            select_centrifuge_inputs(args.mock, ext='.mck')
        for mock in args.mock:
            mock_layout: Counter[TaxId] = read_mock_files(mock)
            test: Filename = Filename(mock.split('.mck')[0] + '.out')
            if args.file:
                mock_from_source(test, mock_layout)
            else:
                mock_from_scratch(test, mock_layout)

    def by_excel_file() -> None:
        """Do the job in case of Excel file with all the details"""
        dirname = os.path.dirname(args.xcel)
        # Expected index (taxids) in column after taxa name, and last row will
        #  be removed (reserved for sum of reads in Excel file)
        mock_df = pd.read_excel(args.xcel, index_col=1, skip_footer=1)
        del mock_df['RECENTRIFUGE MOCK']
        vprint(gray('Layout to generate the mock files:\n'), mock_df, '\n')
        for name, series in mock_df.iteritems():
            mock_layout: Counter[TaxId] = col.Counter(series.to_dict(dict))
            # In prev, series.to_dict(col.Counter) fails, so this is workaround
            test: Filename = Filename(os.path.join(dirname, name + '.out'))
            if args.file:
                mock_from_source(test, mock_layout)
            else:
                mock_from_scratch(test, mock_layout)

    # Program header
    print(f'\n=-= {sys.argv[0]} =-= v{__version__} =-= {__date__} =-=\n')
    sys.stdout.flush()

    # Parse arguments
    argparser = configure_parser()
    args = argparser.parse_args()
    nodesfile: Filename = Filename(os.path.join(args.nodespath, NODES_FILE))
    namesfile: Filename = Filename(os.path.join(args.nodespath, NAMES_FILE))
    debug: bool = args.debug

    check_debug()

    # Load NCBI nodes, names and build children
    ncbi: Taxonomy = Taxonomy(nodesfile, namesfile, None, False)

    if args.mock:
        by_mock_files()
    elif args.xcel:
        by_excel_file()


if __name__ == '__main__':
    main()
