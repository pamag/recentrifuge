"""
Taxonomy class, currently representing the NCBI taxonomy.

"""
import re
import sys
from typing import Set, Counter, Iterable, Tuple

from recentrifuge.config import Filename, TaxId, Parents, Names, Children
from recentrifuge.config import ROOT, CELLULAR_ORGANISMS
from recentrifuge.rank import Ranks, Rank, UnsupportedTaxLevelError


class Taxonomy:
    """Taxonomy related data and methods."""

    def __init__(self,
                 nodes_file: Filename,
                 names_file: Filename,
                 plasmid_file: Filename,
                 collapse: bool = True,
                 excluding: Set[TaxId] = None,
                 including: Set[TaxId] = None,
                 debug: bool = False,
                 ) -> None:

        # Type data declaration and initialization
        self.parents: Parents = Parents({})
        self.ranks: Ranks = Ranks({})
        self.names: Names = Names({})
        self.children: Children = Children({})
        self.collapse: bool = collapse
        self.debug: bool = debug

        # Initialization methods
        self.read_nodes(nodes_file)
        self.read_names(names_file)
        if plasmid_file:
            self.read_plasmids(plasmid_file)
        self.build_children()

        # Show explicitly included and excluded taxa
        if including:
            print('List of taxa (and below) to be explicitly included:')
            print('\t\tTaxId\tScientific Name')
            for taxid in including:
                print(f'\t\t{taxid}\t{self.names[taxid]}')
        else:
            # To excluding to operate not on single taxa but on subtrees
            including = {ROOT}
        self.including: Set[TaxId] = including
        if excluding:
            print('List of taxa (and below) to be excluded:')
            print('\t\tTaxId\tScientific Name')
            for taxid in excluding:
                print(f'\t\t{taxid}\t{self.names[taxid]}')
        self.excluding: Set[TaxId] = excluding

    def read_nodes(self, nodes_file: Filename) -> None:
        """Build dicts of parent and rank for a given taxid (key)"""
        print('\033[90mLoading NCBI nodes...\033[0m', end='')
        sys.stdout.flush()
        try:
            with open(nodes_file, 'r') as file:
                for line in file:
                    _tid, _parent, _rank, *_ = line.split('\t|\t')
                    tid = TaxId(_tid)
                    parent = TaxId(_parent)
                    if self.collapse and parent == CELLULAR_ORGANISMS:
                        self.parents[tid] = ROOT
                    else:
                        self.parents[tid] = parent
                    rank: Rank
                    try:
                        rank = Rank[_rank.upper().replace(" ", "_")]
                    except KeyError:
                        raise UnsupportedTaxLevelError(
                            f'Unknown tax level {_rank}')
                    self.ranks[tid] = rank

        except OSError:
            print(f'\n\033[91mERROR!\033[0m Cannot read {nodes_file}')
            raise
        else:
            print('\033[92m OK! \033[0m')

    def read_names(self, names_file: Filename) -> None:
        """Build dict with name for a given taxid (key)."""
        print('\033[90mLoading NCBI names...\033[0m', end='')
        sys.stdout.flush()
        try:
            with open(names_file, 'r') as file:
                for line in file:
                    if 'scientific name' in line:
                        tid, scientific_name, *_ = line.split('\t|\t')
                        self.names[TaxId(tid)] = scientific_name
        except OSError:
            raise Exception('\n\033[91mERROR!\033[0m Cannot read "' +
                            names_file + '"')
        else:
            print('\033[92m OK! \033[0m')

    def read_plasmids(self, plasmid_file: Filename) -> None:
        """Read, check and include plasmid data"""
        print('\033[90mLoading LMAT plasmids...\033[0m', end='')
        sys.stdout.flush()
        pattern1 = re.compile(
            r"""((?:"([\w\-\.\(\)/+=':,%\*\s]*)"$)|(?:^([\w\-\.\(\)/+=':\*\s]*(?:, (?:strain|isolate|plasmid) [\w\-/\.]*)*(?:, fragment \w*)?(?:, contig \w)?)(?:, a cloning vector)?(?=(?=(?:, (?:complete|partial) (?:plasmid |genomic )*(?:sequence|genome|cds|replicon))(?:\[sequence_id)*)|(?:, complete sequence)*, whole genome shotgun sequence|\[sequence_id)))"""  # pylint: disable=line-too-long
        )
        pattern2 = re.compile(
            r"""(^(?:[A-Za-z0-9/=\-\.{},]*(?: |.)){1,8})"""
        )
        match: Counter = Counter()
        try:
            with open(plasmid_file, 'r') as file:
                for line in file:
                    _tid, _parent, *_, last = line.rstrip('\n').split('\t')
                    last = last.split(r'|')[-1]
                    tid = TaxId(_tid)
                    parent = TaxId(_parent)
                    # Plasmids sanity checks
                    if tid in self.parents:  # if plasmid tid already in NCBI
                        match['ERR1'] += 1
                        if self.debug:
                            print(f'\033[93mPlasmid taxid ERROR!\033[0m'
                                  f' Taxid={tid} already a NCBI taxid. '
                                  f'Declared parent is {parent} but '
                                  f'NCBI parent is {self.parents[tid]}.')
                            print('\tPlasmid details: ', last)
                        continue
                    elif tid == parent:  # if plasmid and parent tids are equal
                        match['ERR2'] += 1
                        if self.debug:
                            print(f'\033[93mPlasmid parent taxid ERROR!\033[0m'
                                  f' Taxid={tid} and parent={parent}.')
                            print('\t\t   Plasmid details: ', last)
                        continue
                    else:  # No problem, go ahead and add the plasmid!
                        self.parents[tid] = parent
                    # Plasmid name extraction by regular expressions
                    name: str
                    try:
                        name = pattern1.search(last).group(1)
                        name = 'Plasmid ' + name.strip(r'"').strip(',')
                    except AttributeError:
                        try:
                            name = pattern2.search(last).group(1).strip()
                            name = 'Plasmid ' + name
                        except AttributeError:
                            name = 'Plasmid ' + tid
                            match['FAIL'] += 1
                        else:
                            match['PAT2'] += 1
                    else:
                        match['PAT1'] += 1
                    self.names[tid] = name
        except OSError:
            print('\033[93mWARNING\033[0m: Cannot read "' +
                        plasmid_file + '". Plasmid taxids not loaded!')
        else:  # Statistics about plasmids
            print('\033[92m OK! \033[0m\n',
                  '\033[90mPlasmid sanity check:\033[0m',
                  f'\033[93m rejected\033[0m (taxid error) = {match["ERR1"]}',
                  f'\033[93m rejected\033[0m (parent error) = {match["ERR2"]}')
            print('\033[90m Plasmid pattern matching:\033[0m',
                  f'\033[90m 1st type =\033[0m {match["PAT1"]} ',
                  f'\033[90m 2nd type =\033[0m {match["PAT2"]} ',
                  f'\033[90m other =\033[0m {match["FAIL"]}')


    def build_children(self) -> None:
        """Build dict of children for a given parent taxid (key)."""
        print('\033[90mBuilding dict of parent to children taxa...\033[0m',
              end='')
        sys.stdout.flush()
        self.children: Children = Children({})
        for tid in self.parents:
            if self.parents[tid] not in self.children:
                self.children[self.parents[tid]] = {}
            self.children[self.parents[tid]][tid] = 0
        print('\033[92m OK! \033[0m')

    def get_rank(self, taxid: TaxId) -> Rank:
        """Retrieve the rank for a TaxId."""
        return self.ranks.get(taxid, Rank.UNCLASSIFIED)

    def get_name(self, taxid: TaxId) -> str:
        """Retrieve the name for a TaxId."""
        return self.names.get(taxid, 'Unnamed')

    def get_ancestors(self, leaves: Iterable[TaxId]
                      ) -> Tuple[Set[TaxId], Set[TaxId]]:
        """Return the taxids entered with all their ancestors"""
        ancestors: Set[TaxId] = set(leaves)
        orphans: Set[TaxId] = set()
        for leaf in leaves:
            tid: TaxId = leaf
            while tid != ROOT:
                try:
                    tid = self.parents[tid]
                except KeyError:
                    orphans.add(tid)
                    break
                else:
                    ancestors.add(tid)
        return ancestors, orphans
