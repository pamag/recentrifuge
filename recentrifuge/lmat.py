"""
Functions directly related with LMAT
(Livermore Metagenomics Analysis Toolkit).

"""

import io
import os
from enum import Enum
from statistics import mean
from typing import Tuple, Counter, Dict, List

from Bio import SeqIO

from recentrifuge.config import TaxId, Score, Scoring, Filename, SampleStats
from recentrifuge.config import TAXDUMP_PATH, gray, red, green


class UnsupportedMatchingError(Exception):
    """Raised if a unsupported DB matching is found."""


class Match(Enum):
    """Enumeration with LMAT DB matching types.
    """
    # pylint: disable=invalid-name
    NOMATCH = ()  # No database match
    NoMatch = 'NOMATCH'
    NO = 'NOMATCH'
    MULTIMATCH = ()  # lowest common ancestor (LCA)
    MultiMatch = 'MULTIMATCH'
    MULTI = 'MULTIMATCH'
    DIRECTMATCH = ()  # best match
    DirectMatch = 'DIRECTMATCH'
    DIRECT = 'DIRECTMATCH'
    NODBHITS = ()
    NoDbHits = 'NODBHITS'
    READTOOSHORT = ()
    ReadTooShort = 'READTOOSHORT'
    LOWSCORE = ()
    LowScore = "LOWSCORE"

    # pylint: enable=invalid-name

    @classmethod
    def lmat(cls, matching: str) -> 'Match':
        """Transforms LMAT codes for DB matching types"""
        match: Match
        try:
            match = cls[matching]
        except KeyError:
            raise UnsupportedMatchingError(
                f'Unknown LMAT DB matching {matching}')
        return match

    def __new__(cls, init=None):
        _value: int
        if isinstance(init, int):
            _value = init
        elif isinstance(init, str):
            _value = cls[init].value
        else:
            _value = 9 - len(cls.__members__)  # Give decreasing values < 10
        obj = object.__new__(cls)
        obj._value_ = _value  # pylint: disable=protected-access
        return obj

    def __repr__(self):
        return f'{self.name}'


def read_lmat_output(output_file: Filename,
                     scoring: Scoring = Scoring.LMAT,
                     minscore: Score = None,
                     ) -> Tuple[str, SampleStats,
                                Counter[TaxId], Dict[TaxId, Score]]:
    """
    Read LMAT output (iterate over all the output files)

    Args:
        output_file: output file name (prefix)
        scoring: type of scoring to be applied (see Scoring class)
        minscore: minimum confidence level for the classification

    Returns:
        log string, abundances counter, scores dict

    """
    output: io.StringIO = io.StringIO(newline='')
    all_scores: Dict[TaxId, List[Score]] = {}
    all_length: Dict[TaxId, List[int]] = {}
    nt_read: int = 0
    matchings: Counter[Match] = Counter()
    output_files: List[Filename] = []
    # Select files to process depending on if the output files are explicitly
    #  given or directory name is provided (all the output files there)
    if os.path.isdir(output_file):  # Just the directory name is provided
        dirname = os.path.normpath(output_file)
        for file in os.listdir(dirname):  # Add all LMAT output files in dir
            if ('_output' in file and file.endswith('.out') and
                    'canVfin' not in file and 'pyLCA' not in file):
                output_files.append(Filename(file))
    else:  # Explicit path and file name prefix is given
        dirname, basename = os.path.split(output_file)
        for file in os.listdir(dirname):  # Add selected output files in dir
            if (file.startswith(basename) and file.endswith('.out') and
                    'canVfin' not in file and 'pyLCA' not in file):
                output_files.append(Filename(file))
    if not output_files:
        raise Exception(
            f'\n\033[91mERROR!\033[0m Cannot read from "{output_file}"')
    # Read LMAT output files
    for output_name in output_files:
        path: Filename = Filename(os.path.join(dirname, output_name))
        output.write(f'\033[90mLoading output file {path}...\033[0m')
        try:
            with open(path, 'r') as io_file:
                for seq in SeqIO.parse(io_file, "lmat"):
                    tid: TaxId = seq.annotations['final_taxid']
                    score: Score = seq.annotations['final_score']
                    match: Match = Match.lmat(seq.annotations['final_match'])
                    matchings[match] += 1
                    length: int = len(seq)
                    nt_read += length
                    if minscore is not None:
                        if score < minscore:  # Ignore read if low score
                            continue
                    if match in [Match.DIRECTMATCH, Match.MULTIMATCH]:
                        try:
                            all_scores[tid].append(score)
                        except KeyError:
                            all_scores[tid] = [score, ]
                        try:
                            all_length[tid].append(length)
                        except KeyError:
                            all_length[tid] = [length, ]
        except FileNotFoundError:
            raise Exception(red('\nERROR!') + f'Cannot read "{path}"')
        output.write(green('OK!\n'))
    abundances: Counter[TaxId] = Counter({tid: len(all_scores[tid])
                                          for tid in all_scores})
    # Basic output statistics
    read_seqs: int = sum(matchings.values())
    if read_seqs == 0:
        raise Exception(red('\nERROR! ')
                        + f'Cannot read any sequence from"{output_file}"')
    filt_seqs: int = sum([len(scores) for scores in all_scores.values()])
    if filt_seqs == 0:
        raise Exception(red('\nERROR! ') + 'No sequence passed the filter!')
    stat: SampleStats = SampleStats(
        minscore=minscore, nt_read=nt_read, scores=all_scores, lens=all_length,
        seq_read=read_seqs, seq_filt=filt_seqs,
        seq_clas=matchings[Match.DIRECT] + matchings[Match.MULTI]
    )
    output.write(gray('  Seqs read: ') + f'{stat.seq.read:_d}\t' + gray('[')
                 + f'{stat.nt_read}' + gray(']\n'))
    output.write(gray('  Seqs clas: ') + f'{stat.seq.clas:_d}\t' + gray('(') +
                 f'{stat.get_unclas_ratio():.2%}' + gray(' unclassified)\n'))
    output.write(gray('  Seqs pass: ') + f'{stat.seq.filt:_d}\t' + gray('(') +
                 f'{stat.get_reject_ratio():.2%}' + gray(' rejected)\n'))
    multi_rel: float = matchings[Match.MULTI] / read_seqs
    direct_rel: float = matchings[Match.DIRECT] / read_seqs
    nodbhits_rel: float = matchings[Match.NODBHITS] / read_seqs
    tooshort_rel: float = matchings[Match.READTOOSHORT] / read_seqs
    lowscore_rel: float = matchings[Match.LOWSCORE] / read_seqs
    output.write(f'\033[90m  DB Matching: '
                 f'Multi =\033[0m {multi_rel:.1%}\033[90m  '
                 f'Direct =\033[0m {direct_rel:.1%}\033[90m  '
                 f'ReadTooShort =\033[0m {tooshort_rel:.1%}\033[90m  '
                 f'LowScore =\033[0m {lowscore_rel:.1%}\033[90m  '
                 f'NoDbHits =\033[0m {nodbhits_rel:.1%}\033[90m\n')
    output.write(gray('  Scores: min = ') + f'{stat.sco.mini:.1f},' +
                 gray(' max = ') + f'{stat.sco.maxi:.1f},' +
                 gray(' avr = ') + f'{stat.sco.mean:.1f}\n')
    output.write(gray('  Length: min = ') + f'{stat.len.mini},' +
                 gray(' max = ') + f'{stat.len.maxi},' +
                 gray(' avr = ') + f'{stat.len.mean}\n')
    output.write(f'  {stat.num_taxa}' + gray(f' taxa with assigned reads\n'))
    # Select score output
    out_scores: Dict[TaxId, Score]
    if scoring is Scoring.LMAT:
        out_scores = {tid: Score(mean(all_scores[tid])) for tid in all_scores}
    else:
        raise Exception(f'\n\033[91mERROR!\033[0m Unknown Scoring "{scoring}"')
    # Return
    return output.getvalue(), stat, abundances, out_scores


def select_lmat_inputs(lmats: List[Filename]) -> None:
    """"LMAT files processing specific stuff"""
    if lmats == ['.']:
        lmats.clear()
        with os.scandir() as dir_entry:
            for entry in dir_entry:
                if not entry.name.startswith('.') and entry.is_dir():
                    if entry.name != os.path.basename(TAXDUMP_PATH):
                        lmats.append(Filename(entry.name))
        lmats.sort()
    print(gray('LMAT subdirs to analyze:'), lmats)
