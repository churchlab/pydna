#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright 2013 by Björn Johansson.  All rights reserved.
# This code is part of the Python-dna distribution and governed by its
# license.  Please see the LICENSE.txt file that should have been included
# as part of this package.

'''Provides Dseqrecord, for handling double stranded
DNA sequences. Dseq and Dseqrecord are subclasses of Biopythons
Seq and SeqRecord classes, respectively. These classes support the
notion of circular and linear DNA.

'''
import copy     as _copy
import datetime as _datetime
import operator as _operator
import os       as _os
import re       as _re
import colorsys as _colorsys
from collections.abc import Iterable as _Iterable

from warnings import warn as _warn

import logging as _logging
_module_logger = _logging.getLogger("pydna."+__name__)

from prettytable import PrettyTable as _PrettyTable
from pydna.utils import identifier_from_string as _identifier_from_string

from Bio.Seq                import Seq as _Seq
from Bio.Seq                import translate as _translate
from itertools              import tee as _tee

from pydna.seqrecord        import SeqRecord  as _SeqRecord
from Bio.SeqFeature         import FeatureLocation as _FeatureLocation
from Bio.SeqFeature         import CompoundLocation as _CompoundLocation
from pydna.seqfeature       import SeqFeature as _SeqFeature
from Bio.SeqUtils           import GC as _GC
from Bio.Data.CodonTable    import TranslationError as _TranslationError

from pydna._sequencetrace     import SequenceTraceFactory as _SequenceTraceFactory
from pydna.common_sub_strings import common_sub_strings as _common_sub_strings
from pydna.utils  import seguid   as _seg
from pydna.utils  import cseguid  as _cseg
from pydna.utils  import rc       as _rc
from pydna.utils  import memorize as _memorize
from pydna.utils  import flatten     as _flatten

from pydna._pretty import pretty_str as _pretty_str
from pydna.dseq import Dseq as _Dseq

from Bio.Restriction import RestrictionBatch as _RestrictionBatch
from Bio.Restriction import CommOnly

try:
    from IPython.display import display as _display
except ImportError:
    def _display_html(item): return item
    def _HTML(item): return item
else:
    from IPython.display import display_html as _display_html
    from IPython.display import HTML         as _HTML

class Dseqrecord(_SeqRecord):
    '''Dseqrecord is a double stranded version of the Biopython SeqRecord [#]_ class.
    The Dseqrecord object holds a Dseq object describing the sequence.
    Additionally, Dseqrecord hold meta information about the sequence in the
    from of a list of SeqFeatures, in the same way as the SeqRecord does.
    The Dseqrecord can be initialized with a string, Seq, Dseq, SeqRecord
    or another Dseqrecord. The sequence information will be stored in a
    Dseq object in all cases. Dseqrecord objects can be read or parsed
    from sequences in Fasta, Embl or Genbank format.

    There is a short representation associated with the Dseqrecord.
    ``Dseqrecord(-3)`` represents a linear sequence of length 2
    while ``Dseqrecord(o7)``
    represents a circular sequence of length 7.

    Dseqrecord and Dseq share the same concept of length

    ::

        <-- length -->
        GATCCTTT
             AAAGCCTAG




    Parameters
    ----------
    record  : string, Seq, SeqRecord, Dseq or other Dseqrecord object
        This data will be used to form the seq property

    circular : bool, optional
        True or False reflecting the shape of the DNA molecule

    linear : bool, optional
        True or False reflecting the shape of the DNA molecule


    Examples
    --------

    >>> from pydna.dseqrecord import Dseqrecord
    >>> a=Dseqrecord("aaa")
    >>> a
    Dseqrecord(-3)
    >>> a.seq
    Dseq(-3)
    aaa
    ttt
    >>> from Bio.Seq import Seq
    >>> b=Dseqrecord(Seq("aaa"))
    >>> b
    Dseqrecord(-3)
    >>> b.seq
    Dseq(-3)
    aaa
    ttt
    >>> from Bio.SeqRecord import SeqRecord
    >>> c=Dseqrecord(SeqRecord(Seq("aaa")))
    >>> c
    Dseqrecord(-3)
    >>> c.seq
    Dseq(-3)
    aaa
    ttt
    >>> a.seq.alphabet
    IUPACAmbiguousDNA()
    >>> b.seq.alphabet
    IUPACAmbiguousDNA()
    >>> c.seq.alphabet
    IUPACAmbiguousDNA()
    >>>

    References
    ----------

    .. [#] http://biopython.org/wiki/SeqRecord

    '''

    def __init__(self, record,
                       *args,
                       linear                 = None,
                       circular               = None,
                       n                      = 5E-14, # mol ( = 0.05 pmol)
                       **kwargs):
        
        if not (linear is None and circular is None):
            circular = bool(circular) and bool(linear)^bool(circular) or linear==False and circular is None
            linear   = not circular
        
        if isinstance(record, str):
            super().__init__( _Dseq(record,
                                    linear=linear,
                                    circular=circular),
                              *args,
                              **kwargs )       
        # record is a Dseq object ?
        elif hasattr(record, "watson"):
            if record.circular and linear:
                record = record[:]
            elif record.linear and circular:
                record = record.looped()
            super().__init__(record, *args, **kwargs)
        # record is a Bio.Seq object ?
        elif hasattr(record, "alphabet"):
            super().__init__(_Dseq(str(record),
                                   linear=linear,
                                   circular=circular),
                             *args,
                             **kwargs)
        # record is a Bio.SeqRecord or Dseqrecord object ?
        elif hasattr(record, "features"):
            for key, value in list(record.__dict__.items()):
                setattr(self, key, value )
            record.letter_annotations = {}
            # record.seq is a Dseq object ?
            if hasattr(record.seq, "watson"):
                new_seq = _copy.copy(record.seq)
                if new_seq.circular and linear:
                    new_seq = new_seq[:]
                elif new_seq.linear and circular:
                    new_seq = new_seq.looped()
                self.seq=new_seq
            # record.seq is Bio.SeqRecord object ?
            else:
                self.seq=_Dseq(str(self.seq),
                               linear=linear,
                               circular=circular)
        else:
            raise ValueError("don't know what to do with {}".format(record))

        self.map_target = None
        self.n = n
        
        
    @property
    def linear(self):
        '''The linear property'''
        return self.seq.linear

    @property
    def circular(self):
        '''The circular property'''
        return self.seq.circular

    def m(self):
        return self.seq.mw() * self.n # Da(g/mol) * mol = g

    def extract_feature(self, n):
        '''Extracts a feature and creates a new Dseqrecord object.

        Parameters
        ----------
        n  : int
            Indicates the feature to extract

        Examples
        --------

        >>> from pydna.dseqrecord import Dseqrecord
        >>> a=Dseqrecord("atgtaa")
        >>> a.add_feature(2,4)
        >>> b=a.extract_feature(0)
        >>> b
        Dseqrecord(-2)
        >>> b.seq
        Dseq(-2)
        gt
        ca

        '''
        return super().extract_feature(n)



    def cseguid(self):
        '''Returns the url safe cSEGUID for the sequence.

        Only defined for circular sequences.

        The cSEGUID checksum uniquely identifies a circular
        sequence regardless of where the origin is set.
        The two Dseqrecord objects below are circular
        permutations.

        Examples
        --------

        >>> from pydna.dseqrecord import Dseqrecord
        >>> a=Dseqrecord("agtatcgtacatg", circular=True)
        >>> a.cseguid() # cseguid is CTJbs6Fat8kLQxHj+/SC0kGEiYs
        'CTJbs6Fat8kLQxHj-_SC0kGEiYs'

        >>> a=Dseqrecord("gagtatcgtacat", circular=True)
        >>> a.cseguid()
        'CTJbs6Fat8kLQxHj-_SC0kGEiYs'

       '''
        if self.linear:
            raise TypeError("cseguid is only defined for circular sequences.")
        return _cseg(str(self.seq))

    def lseguid(self):
        '''Returns the url safe lSEGUID for the sequence.

        Only defined for linear double stranded sequences.

        The lSEGUID checksum uniquely identifies a linear
        sequence independent of the direction.
        The two Dseqrecord objects below are each others
        reverse complements, so they do in fact refer to
        the same molecule.

        Examples
        --------

        >>> from pydna.dseqrecord import Dseqrecord
        >>> a=Dseqrecord("agtatcgtacatg")
        >>> a.lseguid()
        'DPshMN4KeAjMovEjGEV4Kzj18lU'

        >>> b=Dseqrecord("catgtacgatact")
        >>> a.lseguid()
        'DPshMN4KeAjMovEjGEV4Kzj18lU'

       '''
        if self.circular:
            raise TypeError("lseguid is only defined for linear sequences.")
        return self.seq.seguid()

    def stamp(self):
        '''Adds a SEGUID or cSEGUID checksum and a datestring to the description property.
        This will show in the genbank format.

        For linear sequences:

        ``SEGUID_<seguid>_<datestring>``

        For circular sequences:

        ``cSEGUID_<seguid>_<datestring>``


        Examples
        --------

        >>> from pydna.dseqrecord import Dseqrecord
        >>> a=Dseqrecord("aaa")
        >>> a.stamp()
        'SEGUID_YG7G6b2Kj_KtFOX63j8mRHHoIlE...'
        >>> a.description
        'SEGUID_YG7G6b2Kj_KtFOX63j8mRHHoIlE...'

        See also
        --------
        pydna.dseqrecord.Dseqrecord.verify_stamp
        '''

        return super().stamp()


    def looped(self):
        '''
        Returns a circular version of the Dseqrecord object. The
        underlying Dseq object has to have compatible ends.


        Examples
        --------
        >>> from pydna.dseqrecord import Dseqrecord
        >>> a=Dseqrecord("aaa")
        >>> a
        Dseqrecord(-3)
        >>> b=a.looped()
        >>> b
        Dseqrecord(o3)
        >>>

        See also
        --------
        pydna.dseq.Dseq.looped
        '''
        new = _copy.copy(self)
        for key, value in list(self.__dict__.items()):
            setattr(new, key, value )
        new._seq = self.seq.looped()
        for fn, fo in zip(new.features, self.features):
            fn.qualifiers = fo.qualifiers

        return new

    def tolinear(self): # pragma: no cover
        '''
        Returns a linear, blunt copy of a circular Dseqrecord object. The
        underlying Dseq object has to be circular.
        
        This method is deprecated, use slicing instead. See example below.

        Examples
        --------
        >>> from pydna.dseqrecord import Dseqrecord
        >>> a=Dseqrecord("aaa", circular = True)
        >>> a
        Dseqrecord(o3)
        >>> b=a[:]
        >>> b
        Dseqrecord(-3)
        >>>

        '''
        import warnings as _warnings
        from pydna import _PydnaDeprecationWarning
        _warnings.warn("tolinear method is obsolete; "
                       "please use obj[:] "
                       "instead of obj.tolinear().",
                       _PydnaDeprecationWarning)
        new = _copy.copy(self)
        for key, value in list(self.__dict__.items()):
            setattr(new, key, value )
        new._seq = self.seq.tolinear()
        for fn, fo in zip(new.features, self.features):
            fn.qualifiers = fo.qualifiers

        return new

    def format(self, f="gb"):
        '''Returns the sequence as a string using a format supported by Biopython
        SeqIO [#]_. Default is "gb" which is short for Genbank.

        Examples
        --------
        >>> from pydna.dseqrecord import Dseqrecord
        >>> x=Dseqrecord("aaa")
        >>> x.annotations['date'] = '02-FEB-2013'
        >>> x
        Dseqrecord(-3)
        >>> print(x.format("gb"))
        LOCUS       name                       3 bp    DNA     linear   UNK 02-FEB-2013
        DEFINITION  description.
        ACCESSION   id
        VERSION     id
        KEYWORDS    .
        SOURCE      .
          ORGANISM  .
                    .
        FEATURES             Location/Qualifiers
        ORIGIN
                1 aaa
        //


        References
        ----------

        .. [#] http://biopython.org/wiki/SeqIO


        '''

        s = super().format(f).strip()

        if f in ("genbank","gb"):
            if self.circular:
                return _pretty_str(s[:55]+"circular"+s[63:])
            else:
                return _pretty_str(s[:55]+"linear  "+s[63:])
        else:
            return _pretty_str(s).strip()

    def write(self, filename=None, f="gb"):
        '''Writes the Dseqrecord to a file using the format f, which must
        be a format supported by Biopython SeqIO for writing [#]_. Default
        is "gb" which is short for Genbank. Note that Biopython SeqIO reads
        more formats than it writes.

        Filename is the path to the file where the sequece is to be
        written. The filename is optional, if it is not given, the
        description property (string) is used together with the format.

        If obj is the Dseqrecord object, the default file name will be:

        ``<obj.locus>.<f>``

        Where <f> is "gb" by default. If the filename already exists and
        AND the sequence it contains is different, a new file name will be
        used so that the old file is not lost:

        ``<obj.locus>_NEW.<f>``

        References
        ----------
        .. [#] http://biopython.org/wiki/SeqIO

        '''
        msg=""
        if not filename:
            filename = "{name}.{type}".format(name=self.locus, type=f)
            # generate a name if no name was given
        if not isinstance(filename, str): # is filename a string???
            raise ValueError("filename has to be a string, got", type(filename))
        name, ext = _os.path.splitext(filename)
        msg = "<font face=monospace><a href='{filename}' target='_blank'>{filename}</a></font><br>".format(filename=filename)
        if not _os.path.isfile(filename):
            with open(filename, "w") as fp: fp.write(self.format(f))
        else:
            from pydna.readers import read
            old_file = read(filename)
            if self.seq != old_file.seq:
                # If new sequence is different, the old file is renamed with "OLD" suffix:
                # TODO: add this timestamp so that all old versions are stored
                # int(time.time() * 1000000)  = 1512035297658778
                old_filename = "{}_OLD{}".format(name, ext)
                _os.rename(filename, old_filename)
                msg = ("<font color='DarkOrange ' face=monospace>"
                       "Sequence changed.<br>"
                       "</font>"
                       "<font color='red' face=monospace>"
                       "new: <a href='{filename}' target='_blank'>{filename}</a> &nbsp&nbsp&nbsp size: {nlen}bp topology: {ntop} SEGUID: {ns}<br>"
                       "</font>"
                       "<font color='green' face=monospace>"
                       "old: <a href='{oldfname}' target='_blank'>{oldfname}</a> size: {olen}bp topology: {otop} SEGUID: {os}<br>"
                       "</font>").format(filename=filename,
                                         oldfname=old_filename,
                                         nlen=len(self),
                                         olen=len(old_file),
                                         ns=self.seguid(),
                                         os=old_file.seguid(),
                                         ntop={True:"-", False:"o"}[self.linear],
                                         otop={True:"-", False:"o"}[old_file.linear])
                with open(filename, "w") as fp: fp.write(self.format(f))
            elif "SEGUID" in old_file.description:
                pattern = "(lSEGUID|cSEGUID|SEGUID)_\s*(\S{27})_[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]{6}"
                oldstamp = _re.search(pattern, old_file.description)
                newstamp = _re.search(pattern, self.description)
                newdescription = self.description
                if oldstamp and newstamp:
                    if oldstamp.group(0)[:35] == newstamp.group(0)[:35]:
                        newdescription = newdescription.replace(newstamp.group(0), oldstamp.group(0))
                elif oldstamp:
                    newdescription+=" "+oldstamp.group(0)
                newobj = _copy.copy(self)
                newobj.description = newdescription
                with open(filename, "w") as fp: fp.write(newobj.format(f))
            else:
                with open(filename, "w") as fp: fp.write(self.format(f))
        return _display_html(_HTML(msg))

    def find(self, other):
        # TODO allow strings, seqs, seqrecords or Dseqrecords
        # TODO check for linearity of other, raise exception if not
        # TODO add tests and docstring for this method
        o = str(other.seq).upper()

        if self.linear:
            s = str(self.seq).upper()
        else:
            s = str(self.seq).upper()+str(self.seq).upper()[:len(other)-1] #allow wrapping around origin
        return s.find(o)


    def __str__(self):
        return ( "Dseqrecord\n"
                 "circular: {}\n"
                 "size: {}\n").format(self.circular, len(self))+_SeqRecord.__str__(self)
    def __contains__(self, other):
        if other.lower() in str(self.seq).lower():
            return True
        else:
            s = self.seq.watson.replace(" ","")
            ln  = len(s)
            spc = 3-ln%3 if ln%3 else 0
            s = "n" * spc + s + "nnn"
            for frame in range(3):
                if other.lower() in _translate(s[frame:frame+spc+ln]).lower():
                    return True
        return False

    def find_aa(self, other):
        return self.find_aminoacids(other)

    def find_aminoacids(self, other):
        '''
        >>> from pydna.dseqrecord import Dseqrecord
        >>> s=Dseqrecord("atgtacgatcgtatgctggttatattttag")
        >>> s.seq.translate()
        Seq('MYDRMLVIF*', HasStopCodon(ExtendedIUPACProtein(), '*'))
        >>> "RML" in s
        True
        >>> "MMM" in s
        False
        >>> s.seq.rc().translate()
        Seq('LKYNQHTIVH', ExtendedIUPACProtein())
        >>> "QHT" in s.rc()
        True
        >>> "QHT" in s
        False
        >>> slc = s.find_aa("RML")
        >>> slc
        slice(9, 18, None)
        >>> s[slc]
        Dseqrecord(-9)
        >>> code = s[slc].seq
        >>> code
        Dseq(-9)
        cgtatgctg
        gcatacgac
        >>> code.translate()
        Seq('RML', ExtendedIUPACProtein())
        '''
        other = str(other).lower()
        assert self.seq.watson == "".join(self.seq.watson.split())
        s = self.seq.watson
        ln  = len(s)
        spc = 3-ln%3 if ln%3 else 0
        s = s + "n"*spc + "nnn"
        start = None
        for frame in range(3):
            try:
                start = _translate(s[frame:frame+ln+spc]).lower().index(other)
                break
            except ValueError:
                pass
        oh = self.seq.ovhg if self.seq.ovhg>0 else 0
        if start == None:
            return None      #TODO return an emoty slice or False...?
        else:
            return slice(frame+start*3+oh, frame+(start+len(other))*3+oh)

    def map_trace_files(self, pth):  # TODO allow path-like objects
        import glob
        traces = []
        stf = _SequenceTraceFactory()
        for name in glob.glob(pth):
            traces.append( stf.loadTraceFile( name ))
            from Bio import SeqIO
            x=str(SeqIO.read(name, "abi").seq).lower()
            y=str(stf.loadTraceFile( name ).basecalls).lower()
            assert x==y
        if not traces:
            raise ValueError("No trace files found in {}".format(pth))
        if hasattr( self.map_target, "step" ):
            area = self.map_target
        elif hasattr( self.map_target, "extract" ):
            area = slice(self.map_target.location.start, self.map_target.location.end)
        else:
            area = None  # TODO allow other objects as well and do some checks on map target

        if area:
            self.matching_reads     = []
            self.not_matching_reads = []
            target    = str(self[area].seq).lower()
            target_rc = str(self[area].seq.rc()).lower()
            for trace in traces:
                if target in str(trace.basecalls).lower() or target_rc in str(trace.basecalls).lower():
                   self.matching_reads.append(trace)
                else:
                    self.not_matching_reads.append(trace)
            reads = self.matching_reads
        else:
            self.matching_reads     = None
            self.not_matching_reads = None
            reads = traces

        matching_reads = []

        for read_ in reads:

            matches = _common_sub_strings(str(self.seq).lower(), read_.basecalls.lower(), limit=25)
            
            if not matches:
                continue            
            
            if len(matches)>1:
                newmatches = [matches[0],]
                for i, x in enumerate(matches[1:]):
                    g,f,h = matches[i]
                    if g+h < x[0] and f+h < x[1]:
                        newmatches.append(x)
            else: #  len(matches)==1
                newmatches = matches

            matching_reads.append(read_)

            if len(newmatches)>1:
                ms = []
                for m in newmatches:
                    ms.append(_FeatureLocation(m[0], m[0]+m[2]))
                loc = _CompoundLocation(ms)
            else:
                a,b,c = newmatches[0]
                loc = _FeatureLocation(a,a+c)

            self.features.append( _SeqFeature(loc,
                                             qualifiers = {"label": [read_.getFileName()]},
                                                           type="trace") )

        return [x.getFileName() for x in matching_reads]

    def __repr__(self):
        return "Dseqrecord({}{})".format({True:"-", False:"o"}[self.linear],len(self))

    def _repr_pretty_(self, p, cycle):
            p.text("Dseqrecord({}{})".format({True:"-", False:"o"}[self.linear],len(self)))

    def __add__(self, other):
        if hasattr(other, "seq") and hasattr(other.seq, "watson"):
            other = _copy.deepcopy(other)
            for f in other.features: f.location=f.location+other.seq.ovhg
            answer = Dseqrecord(_SeqRecord.__add__(self, other))
            answer.n = min(self.n, other.n)
        else:
            answer = Dseqrecord(_SeqRecord.__add__(self, Dseqrecord(other)))
            answer.n = self.n
        return answer

    def __mul__(self, number):
        if not isinstance(number, int):
            raise TypeError("TypeError: can't multiply Dseqrecord by non-int of type {}".format(type(number)))
        if self.circular:
            raise TypeError("TypeError: can't multiply circular Dseqrecord.")
        if number>0:
            new = _copy.copy(self)
            for i in range(1, number):
                new += self
            return new
        else:
            return self.__class__("")

    def __getitem__(self, sl):
        answer = Dseqrecord(_copy.copy(self))
        answer.seq = self.seq.__getitem__(sl)
        answer.seq.alphabet = self.seq.alphabet

        sl_start = sl.start or 0
        sl_stop = sl.stop or len(answer.seq)

        if self.linear or sl_start<sl_stop:
            answer.features = super().__getitem__(sl).features
        else:
            answer.features = self.shifted(sl_stop).features
            answer.features = [f for f in answer.features if f.location.parts == sorted(f.location.parts)]
        identifier= f"part_{self.id}"
        if answer.features:
            sf = max(answer.features, key=len) # default
            if "label" in sf.qualifiers:
                identifier = " ".join(sf.qualifiers["label"])
            elif "note" in sf.qualifiers:
                identifier = " ".join(sf.qualifiers["note"])
        answer.id   = _identifier_from_string(identifier)[:16]
        answer.name = answer.id
        return answer

    def __eq__( self, other ):
        try:
            if self.seq == other.seq and str(self.__dict__) == str(other.__dict__):
                return True
        except AttributeError:
            pass
        return False

    def __ne__( self, other ):
        return not self.__eq__(other)

    def __hash__(self):
        """__hash__ must be based on __eq__"""
        return hash( (str(self.seq).lower(), str(tuple(sorted(self.__dict__.items())))))

    def linearize(self, *enzymes):
        '''This method is similar to :func:`cut` but throws an exception if there
        is not excactly one cut i.e. none or more than one digestion products.

        '''

        if self.seq._linear:
            raise TypeError("Can only linearize circular molecules!")
        fragments = self.cut(*enzymes)
        if len(fragments)>1:
            raise TypeError("More than one fragment is formed!")
        elif fragments[0].circular:
            raise TypeError("The enzyme(s) do not cut!")
        answer = fragments[0]
        answer.id = f"{self.name}_lin"
        answer.name = answer.id[:16]
        return fragments[0]

    def no_cutters(self, batch = CommOnly):
        return self.seq.no_cutters(batch=batch)
    def unique_cutters(self, batch = CommOnly):
        return self.seq.unique_cutters(batch=batch)
    def once_cutters(self, batch = CommOnly):
        return self.seq.once_cutters(batch=batch)
    def twice_cutters(self, batch = CommOnly):
        return self.seq.twice_cutters(batch=batch)
    def n_cutters(self, n=3, batch = CommOnly):
        return self.seq.n_cutters(n=n, batch=batch)
    def cutters(self, batch = CommOnly):
        return self.seq.cutters(batch=batch)

    def cut(self, *enzymes):
        '''Digest the Dseqrecord object with one or more restriction enzymes.
        returns a list of linear Dseqrecords. If there are no cuts, an empty
        list is returned.

        See also :func:`Dseq.cut`

        Parameters
        ----------

        enzymes : enzyme object or iterable of such objects
            A Bio.Restriction.XXX restriction object or iterable of such.

        Returns
        -------
        Dseqrecord_frags : list
            list of Dseqrecord objects formed by the digestion

        Examples
        --------
        >>> from pydna.dseqrecord import Dseqrecord
        >>> a=Dseqrecord("ggatcc")
        >>> from Bio.Restriction import BamHI
        >>> a.cut(BamHI)
        (Dseqrecord(-5), Dseqrecord(-5))
        >>> frag1, frag2 = a.cut(BamHI)
        >>> frag1.seq
        Dseq(-5)
        g
        cctag
        >>> frag2.seq
        Dseq(-5)
        gatcc
            g


        '''

        frags = self.seq.cut(enzymes)

        if frags[0].circular or frags[0]==self.seq: 
            return (self,)
       
        if self.linear:
            shift=0
            features = self.features
        else:
            shift = frags[0].pos            
            features = self.shifted(shift).features
            for fr in frags: fr.pos-=shift
        dsfs = []        
        for fr in frags:
            dsf = Dseqrecord(fr, linear=True, n=self.n)
            start = fr.pos #- shift
            end   = fr.pos + fr.length #- shift
            dsf.features = [_copy.copy(fe) for fe in features if start<=fe.location.start and end>=fe.location.end]
            for fe in dsf.features:  fe.location+= (-fr.pos)
            dsfs.append(dsf)
        return tuple(dsfs)

    def number_of_cuts(self, *enzymes):
        return sum([len(enzyme.search(self.seq)) for enzyme in _flatten(enzymes)]) # flatten

    def reverse_complement(self):
        '''Returns the reverse complement.

        Examples
        --------
        >>> from pydna.dseqrecord import Dseqrecord
        >>> a=Dseqrecord("ggaatt")
        >>> a
        Dseqrecord(-6)
        >>> a.seq
        Dseq(-6)
        ggaatt
        ccttaa
        >>> a.reverse_complement().seq
        Dseq(-6)
        aattcc
        ttaagg
        >>>

        See also
        --------
        pydna.dseq.Dseq.reverse_complement

        '''
        answer = type(self)(super().reverse_complement())
        answer.name       = "{}_rc".format(self.name[:13])
        answer.description= self.description+"_rc"
        answer.id         = self.id+"_rc"
        answer.seq._circular   = self.seq.circular
        answer.seq._linear     = self.seq.linear
        return answer
    
    rc = reverse_complement

    def shifted(self, shift):
        '''Returns a circular Dseqrecord with a new origin <shift>.
         This only works on circular Dseqrecords. If we consider the following
         circular sequence:


         | ``GAAAT   <-- watson strand``
         | ``CTTTA   <-- crick strand``

         The T and the G on the watson strand are linked together as well
         as the A and the C of the of the crick strand.

         if ``shift`` is 1, this indicates a new origin at position 1:

         |    new origin at the | symbol:
         |
         | ``G|AAAT``
         | ``C|TTTA``

         new sequence:

         | ``AAATG``
         | ``TTTAC``

         Examples
         --------

         >>> from pydna.dseqrecord import Dseqrecord
         >>> a=Dseqrecord("aaat",circular=True)
         >>> a
         Dseqrecord(o4)
         >>> a.seq
         Dseq(o4)
         aaat
         ttta
         >>> b=a.shifted(1)
         >>> b
         Dseqrecord(o4)
         >>> b.seq
         Dseq(o4)
         aata
         ttat

        '''
        if self.linear:
            raise TypeError("Sequence is linear, origin can only be shifted for circular sequences.\n")
            
        ln=len(self)
        
        if not shift%ln:
            return self   # shift is a multiple of ln or 0
        else:
            shift%=ln     # 0<=shift<=ln 
        
        newseq=(self.seq[shift:]+self.seq[:shift]).looped()
        shift = ln-shift
        newfeatures=[]
        for feature in self.features:
            shiftedparts    =   [featurelocation+shift for featurelocation in feature.location.parts]
            zero_length_parts = [featurelocation for featurelocation in shiftedparts if featurelocation.start==featurelocation.end]
            newparts = []
            for location in shiftedparts:
                newstart = location.start%ln
                newend   = location.end%ln
                if newstart<newend:
                    newparts.append(_FeatureLocation(newstart,newend,location.strand,location.ref,location.ref_db))
                elif newstart>newend:
                    if location.strand==1:
                        newparts.extend(  [_FeatureLocation(newstart, ln,     location.strand,location.ref,location.ref_db),
                                           _FeatureLocation(0,        newend, location.strand,location.ref,location.ref_db) ])
                    else:
                        newparts.extend(  [_FeatureLocation(0,        newend, location.strand,location.ref,location.ref_db),
                                           _FeatureLocation(newstart, ln,     location.strand,location.ref,location.ref_db) ])
            p=next((p for p in newparts if p.end==shift),   None)
            s=next((p for p in newparts if p.start==shift), None)
            if p and s:
                newparts.remove(p)
                newparts[newparts.index(s)]=_FeatureLocation(p.start,s.end,p.strand,p.ref,p.ref_db)
            newparts=[p for p in newparts if p]
            newparts.extend(zero_length_parts)
            if newparts:
                newfeatures.append(_SeqFeature(location   = sum(newparts),
                                               type       = feature.type,
                                               id         = feature.id,
                                               qualifiers = feature.qualifiers))
        newfeatures.sort(key = _operator.attrgetter('location.start'))
        answer=_copy.copy(self)
        answer.features = newfeatures
        answer.seq=newseq
        return answer

    #@_memorize("Dseqrecord_synced")
    def synced(self, ref, limit = 25):
        '''This function returns a new circular sequence (Dseqrecord object), which has been rotated
        in such a way that there is maximum overlap between the sequence and
        ref, which may be a string, Biopython Seq, SeqRecord object or
        another Dseqrecord object.

        The reason for using this could be to rotate a recombinant plasmid so
        that it starts at the same position after cloning. See the example below:


        Examples
        --------

        >>> from pydna.dseqrecord import Dseqrecord
        >>> a=Dseqrecord("gaat",circular=True)
        >>> a.seq
        Dseq(o4)
        gaat
        ctta
        >>> d = a[2:] + a[:2]
        >>> d.seq
        Dseq(-4)
        atga
        tact
        >>> insert=Dseqrecord("CCC")
        >>> recombinant = (d+insert).looped()
        >>> recombinant.seq
        Dseq(o7)
        atgaCCC
        tactGGG
        >>> recombinant.synced(a).seq
        Dseq(o7)
        gaCCCat
        ctGGGta

        '''

        if self.linear:
            raise TypeError("Only circular DNA can be synced!")

        newseq = _copy.copy(self)

        s    = str(self.seq.watson).lower()
        s_rc = str(self.seq.crick).lower()

        if hasattr(ref, "seq"):
            r=ref.seq
            if hasattr(r, "watson"):
                r = str(r.watson).lower()
            else:
                r = str(r).lower()
        else:
            r = str(ref.lower())

        lim = min(limit, limit*(len(s)//limit)+1)

        c = _common_sub_strings(s+s,       r, limit = lim)
        d = _common_sub_strings(s_rc+s_rc, r, limit = lim)

        c =  [(x[0],x[2]) for x in c if x[1]==0]
        d =  [(x[0],x[2]) for x in d if x[1]==0]

        if not c and not d:
            raise TypeError("There is no overlap between sequences!")

        if c:
            start, length = c.pop(0)
        else:
            start, length = 0,0

        if d:
            start_rc, length_rc = d.pop(0)
        else:
            start_rc, length_rc = 0,0

        if length_rc>length:
            start = start_rc
            newseq = newseq.rc()

        if start == 0:
            result = newseq
        else:
            result = newseq.shifted(start)
        _module_logger.info("synced")
        return result



if __name__=="__main__":
#    cache = _os.getenv("pydna_cache")
#    _os.environ["pydna_cache"]="nocache"
#    import doctest
#    doctest.testmod(verbose=True, optionflags=doctest.ELLIPSIS)
#    _os.environ["pydna_cache"]=cache
    
    from Bio.SeqFeature import SeqFeature, CompoundLocation, FeatureLocation, ExactPosition
    
    
    from Bio.Restriction import BamHI, EcoRI, EcoRV, BglII
    cs1=Dseqrecord("aaaGGATCCggg", circular=True)    
    cs1.features = [SeqFeature(CompoundLocation([FeatureLocation(ExactPosition(5), ExactPosition(12), strand=1), FeatureLocation(ExactPosition(0), ExactPosition(3), strand=1)], 'join'), type='misc_feature', location_operator='join')]
    (a,) = cs1.cut(BamHI, EcoRI+EcoRV+BglII+BamHI)
    assert a.looped().seq == Dseqrecord("GATCCgggaaaG", circular=True).seq
    assert str(a.features[0].extract(a).seq) == str(cs1.features[0].extract(cs1).seq)
    
    from Bio.Restriction import BamHI, EcoRI 
    ss1=Dseqrecord("aaaGGATCCnnngaattcGGG")
    ss1.features = [SeqFeature(FeatureLocation(ExactPosition(1), ExactPosition(3), strand=1), type='misc_feature'),
                    SeqFeature(FeatureLocation(ExactPosition(5), ExactPosition(12), strand=1), type='misc_feature'),
                    SeqFeature(FeatureLocation(ExactPosition(14), ExactPosition(20), strand=1), type='misc_feature')]
    b,c,d = ss1.cut(BamHI, EcoRI)
    assert  (b+c+d).seq == ss1.seq

 
    cs2=Dseqrecord("aaaGGATCCnnngaattcGGG", circular=True)
    cs2.features = [SeqFeature(FeatureLocation(ExactPosition(5), ExactPosition(11), strand=1), type='misc_feature'),
                    SeqFeature(FeatureLocation(ExactPosition(14), ExactPosition(17), strand=1), type='misc_feature'),
                    SeqFeature(CompoundLocation([FeatureLocation(ExactPosition(18), ExactPosition(21), strand=1), FeatureLocation(ExactPosition(0), ExactPosition(4), strand=1)], 'join'), type='misc_feature', location_operator='join')]
    e,f = cs2.cut(BamHI, EcoRI)
    assert str(e.features[0].extract(e).seq) == str(cs2.features[0].extract(cs2).seq)
    assert str(f.features[0].extract(f).seq) == str(cs2.features[1].extract(cs2).seq)
    assert str(f.features[1].extract(f).seq) == str(cs2.features[2].extract(cs2).seq)
    
    assert (e+f).looped().shifted(17).seq == cs2.seq

    from Bio.Restriction import BsaI  
    cs3 = Dseqrecord("gaaaaaggtctcaAAA",circular=True)
    cs3.features = [SeqFeature(CompoundLocation([FeatureLocation(ExactPosition(14), ExactPosition(16), strand=1), FeatureLocation(ExactPosition(0), ExactPosition(12), strand=1)], 'join'), type='misc_feature', location_operator='join')]
    g, = cs3.cut(BsaI)
    
    assert g.looped().shifted(3).seq == cs3.seq
    assert str(g.features[0].extract(g).seq) == str(cs3.features[0].extract(cs3).seq)
    
    from pydna.editor import ape
