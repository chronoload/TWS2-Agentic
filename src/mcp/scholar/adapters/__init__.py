from .base import BaseAdapter, ScholarResult
from .crossref import CrossrefAdapter
from .openalex import OpenAlexAdapter
from .arxiv import ArxivAdapter
from .pubmed import PubMedAdapter
from .semantic_scholar import SemanticScholarAdapter
from .core_ac import CoreAcAdapter
from .unpaywall import UnpaywallAdapter
from .europe_pmc import EuropePmcAdapter
from .doaj import DoajAdapter
from .plos import PlosAdapter
from .datacite import DataCiteAdapter
from .opencitations import OpenCitationsAdapter
from .chinadoi import ChinadoiAdapter
from .uniprot import UniprotAdapter
from .mygene import MyGeneAdapter
from .myvariant import MyVariantAdapter
from .rcsb_pdb import RcsbPdbAdapter
from .ensembl import EnsemblAdapter
from .ebi_tools import EbiToolsAdapter
from .nasa import NasaAdapter
from .cern import CernAdapter
from .usgs import UsgsAdapter
from .ngdc import NgdcAdapter

ALL_ADAPTERS = {
    "crossref": CrossrefAdapter,
    "openalex": OpenAlexAdapter,
    "arxiv": ArxivAdapter,
    "pubmed": PubMedAdapter,
    "semantic_scholar": SemanticScholarAdapter,
    "core_ac": CoreAcAdapter,
    "unpaywall": UnpaywallAdapter,
    "europe_pmc": EuropePmcAdapter,
    "doaj": DoajAdapter,
    "plos": PlosAdapter,
    "datacite": DataCiteAdapter,
    "opencitations": OpenCitationsAdapter,
    "chinadoi": ChinadoiAdapter,
    "uniprot": UniprotAdapter,
    "mygene": MyGeneAdapter,
    "myvariant": MyVariantAdapter,
    "rcsb_pdb": RcsbPdbAdapter,
    "ensembl": EnsemblAdapter,
    "ebi_tools": EbiToolsAdapter,
    "nasa": NasaAdapter,
    "cern": CernAdapter,
    "usgs": UsgsAdapter,
    "ngdc": NgdcAdapter,
}
