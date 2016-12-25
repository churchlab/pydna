#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import pytest
import pydna
import requests


def test_efetch_download_text():
    # see https://www.ncbi.nlm.nih.gov/books/NBK25499/#chapter4.EFetch
    url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=nuccore&id=AJ580804.1&strand=1&rettype=gb&retmode=gbwithparts"
    gbdata = pydna.download_text(url)
    with open("AJ580804.gb") as f:
        localdata = f.read().strip()
    assert localdata==gbdata

def test_biopython_download():
    from Bio import Entrez
    from Bio import SeqIO    
    Entrez.email = "bjornjobb@gmail.com"    
    handle = Entrez.efetch(db="nuccore",
                           id="AJ515744.1",
                           rettype="gb",
                           retmode="text")    
    result = SeqIO.read(handle, "genbank")    
    assert str(result.seq).lower() == "gcaatcctggtcatgatgtagtc"

def test_pydna_download_fresh():
    cachevar = os.environ["pydna_cache"]
    os.environ["pydna_cache"] = "nocache"
    gb = pydna.Genbank("bjornjobb@gmail.com")
    result = gb.nucleotide("AJ515746.1")
    assert str(result.seq).lower() == "cttcccctgtaagtgtatttg"
    os.environ["pydna_cache"] = cachevar
    
def test_pydna_download_cache():
    cachevar = os.environ["pydna_cache"]
    os.environ["pydna_cache"] = "cached"
    gb = pydna.Genbank("bjornjobb@gmail.com")
    result = gb.nucleotide("AJ580803.1")
    assert str(result.seq).lower() == "gcctgcccagatttcagtgt"
    result = gb.nucleotide("AJ580803.1")
    assert str(result.seq).lower() == "gcctgcccagatttcagtgt"    
    os.environ["pydna_cache"] = cachevar 
    

if __name__ == '__main__':
    pytest.cmdline.main([__file__, "-v", "-s"])
    

    
