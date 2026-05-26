import json
from typing import Dict, List, Any, Optional

from ..tools import Tool, ToolResult
from .adapters.crossref import CrossrefAdapter
from .adapters.openalex import OpenAlexAdapter
from .adapters.arxiv import ArxivAdapter
from .adapters.semantic_scholar import SemanticScholarAdapter
from .adapters.core_ac import CoreAcAdapter
from .adapters.unpaywall import UnpaywallAdapter
from .adapters.opencitations import OpenCitationsAdapter
from .adapters.chinadoi import ChinadoiAdapter
from .adapters.mygene import MyGeneAdapter
from .adapters.myvariant import MyVariantAdapter
from .adapters.rcsb_pdb import RcsbPdbAdapter
from .adapters.ebi_tools import EbiToolsAdapter
from .adapters.ensembl import EnsemblAdapter
from .adapters.ngdc import NgdcAdapter
from .adapters.usgs import UsgsAdapter
from .adapters.datacite import DataCiteAdapter
from .adapters.base import ScholarResult


def _scholar_to_str(results: List[ScholarResult]) -> str:
    parts = []
    for r in results:
        if r.success:
            parts.append(json.dumps(r.data, ensure_ascii=False, indent=2) if r.data else "No data")
        else:
            parts.append(f"[{r.source_api}] Error: {r.error}")
    return "\n\n---\n\n".join(parts)


class SearchPapersTool(Tool):
    name = "search_papers"
    description = "Search academic papers across OpenAlex, Crossref, and CORE databases"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query for papers"},
            "max_results": {"type": "integer", "description": "Maximum results per source (default 10)"},
        },
        "required": ["query"],
    }

    def __init__(self):
        self._openalex = OpenAlexAdapter()
        self._crossref = CrossrefAdapter()
        self._core = CoreAcAdapter()

    def execute(self, query: str, max_results: int = 10) -> str:
        results = []
        r1 = self._openalex.search(query, per_page=max_results)
        results.append(r1)
        r2 = self._crossref.search(query, rows=max_results)
        results.append(r2)
        r3 = self._core.search(query, limit=max_results)
        results.append(r3)
        return _scholar_to_str(results)


class GetPaperByDoiTool(Tool):
    name = "get_paper_by_doi"
    description = "Get paper metadata by DOI from Crossref and Semantic Scholar"
    parameters = {
        "type": "object",
        "properties": {
            "doi": {"type": "string", "description": "DOI identifier (e.g. 10.1038/nature12373)"},
        },
        "required": ["doi"],
    }

    def __init__(self):
        self._crossref = CrossrefAdapter()
        self._semantic_scholar = SemanticScholarAdapter()

    def execute(self, doi: str) -> str:
        results = []
        r1 = self._crossref.get_by_doi(doi)
        results.append(r1)
        r2 = self._semantic_scholar.get_by_doi(doi)
        results.append(r2)
        return _scholar_to_str(results)


class GetOaFulltextTool(Tool):
    name = "get_oa_fulltext"
    description = "Get open access fulltext availability for a paper by DOI via Unpaywall"
    parameters = {
        "type": "object",
        "properties": {
            "doi": {"type": "string", "description": "DOI identifier"},
        },
        "required": ["doi"],
    }

    def __init__(self):
        self._unpaywall = UnpaywallAdapter()

    def execute(self, doi: str) -> str:
        result = self._unpaywall.get_oa_status(doi)
        if result.success:
            return json.dumps(result.data, ensure_ascii=False, indent=2)
        return f"Error: {result.error}"


class SearchBiorxivTool(Tool):
    name = "search_biorxiv"
    description = "Search bioRxiv preprints by query"
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query for bioRxiv preprints"},
        },
        "required": ["query"],
    }

    def execute(self, query: str) -> str:
        import urllib.request
        import urllib.parse
        try:
            url = f"https://api.biorxiv.org/details/biorxiv/{urllib.parse.quote(query)}/0/10"
            req = urllib.request.Request(url, headers={
                "User-Agent": "ScholarMCP/1.0",
                "Accept": "application/json",
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return json.dumps(data, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"Error searching bioRxiv: {e}"


class GetGeneInfoTool(Tool):
    name = "get_gene_info"
    description = "Get gene information from MyGene.info"
    parameters = {
        "type": "object",
        "properties": {
            "gene_symbol": {"type": "string", "description": "Gene symbol (e.g. BRCA1, TP53)"},
        },
        "required": ["gene_symbol"],
    }

    def __init__(self):
        self._mygene = MyGeneAdapter()

    def execute(self, gene_symbol: str) -> str:
        result = self._mygene.query(q=gene_symbol, size=5)
        if result.success:
            return json.dumps(result.data, ensure_ascii=False, indent=2)
        return f"Error: {result.error}"


class GetVariantAnnotationTool(Tool):
    name = "get_variant_annotation"
    description = "Get variant annotation from MyVariant.info"
    parameters = {
        "type": "object",
        "properties": {
            "variant_id": {"type": "string", "description": "Variant ID (e.g. rs587782422, chr7:140453136-140453136:A:T)"},
        },
        "required": ["variant_id"],
    }

    def __init__(self):
        self._myvariant = MyVariantAdapter()

    def execute(self, variant_id: str) -> str:
        result = self._myvariant.get_variant(variant_id)
        if not result.success:
            result = self._myvariant.query(q=variant_id, size=5)
        if result.success:
            return json.dumps(result.data, ensure_ascii=False, indent=2)
        return f"Error: {result.error}"


class GetProteinStructureTool(Tool):
    name = "get_protein_structure"
    description = "Get protein structure information from RCSB PDB"
    parameters = {
        "type": "object",
        "properties": {
            "pdb_id": {"type": "string", "description": "PDB identifier (e.g. 1TUP, 7BV2)"},
        },
        "required": ["pdb_id"],
    }

    def __init__(self):
        self._rcsb = RcsbPdbAdapter()

    def execute(self, pdb_id: str) -> str:
        result = self._rcsb.get_entry(pdb_id)
        if result.success:
            return json.dumps(result.data, ensure_ascii=False, indent=2)
        return f"Error: {result.error}"


class AlignSequencesTool(Tool):
    name = "align_sequences"
    description = "Submit sequences for multiple sequence alignment using EBI Clustal Omega"
    parameters = {
        "type": "object",
        "properties": {
            "sequences": {"type": "string", "description": "Sequences in FASTA format"},
        },
        "required": ["sequences"],
    }

    def __init__(self):
        self._ebi = EbiToolsAdapter()

    def execute(self, sequences: str) -> str:
        result = self._ebi.submit_alignment(sequences)
        if result.success:
            data = result.data
            if isinstance(data, dict) and "raw" in data:
                job_id = data["raw"].strip()
                return json.dumps({
                    "job_id": job_id,
                    "status": "submitted",
                    "message": f"Alignment job submitted. Job ID: {job_id}. Use the job ID to check status and retrieve results.",
                }, ensure_ascii=False, indent=2)
            return json.dumps(data, ensure_ascii=False, indent=2)
        return f"Error: {result.error}"


class GetCitationsTool(Tool):
    name = "get_citations"
    description = "Get citations for a paper by DOI from OpenCitations COCI"
    parameters = {
        "type": "object",
        "properties": {
            "doi": {"type": "string", "description": "DOI identifier"},
        },
        "required": ["doi"],
    }

    def __init__(self):
        self._opencitations = OpenCitationsAdapter()

    def execute(self, doi: str) -> str:
        result = self._opencitations.get_citations(doi)
        if result.success:
            return json.dumps(result.data, ensure_ascii=False, indent=2)
        return f"Error: {result.error}"


class ListChinadoiTool(Tool):
    name = "list_chinadoi"
    description = "Resolve Chinese DOI via ChinaDOI"
    parameters = {
        "type": "object",
        "properties": {
            "doi": {"type": "string", "description": "DOI identifier (Chinese DOI supported)"},
        },
        "required": ["doi"],
    }

    def __init__(self):
        self._chinadoi = ChinadoiAdapter()

    def execute(self, doi: str) -> str:
        result = self._chinadoi.resolve(doi)
        if result.success:
            return json.dumps(result.data, ensure_ascii=False, indent=2)
        return f"Error: {result.error}"


class GetGenomeRegionTool(Tool):
    name = "get_genome_region"
    description = "Get genomic features in a region from Ensembl REST API"
    parameters = {
        "type": "object",
        "properties": {
            "chr": {"type": "string", "description": "Chromosome (e.g. 7, X)"},
            "start": {"type": "integer", "description": "Start position"},
            "end": {"type": "integer", "description": "End position"},
        },
        "required": ["chr", "start", "end"],
    }

    def __init__(self):
        self._ensembl = EnsemblAdapter()

    def execute(self, chr: str, start: int, end: int) -> str:
        result = self._ensembl.get_overlap_region("human", chr, start, end)
        if result.success:
            return json.dumps(result.data, ensure_ascii=False, indent=2)
        return f"Error: {result.error}"


class SearchNgdcTool(Tool):
    name = "search_ngdc"
    description = "Search CNCB-NGDC (National Genomics Data Center) databases"
    parameters = {
        "type": "object",
        "properties": {
            "database": {"type": "string", "description": "Database name (e.g. gsa, gwh, biosample)"},
            "query": {"type": "string", "description": "Search query"},
        },
        "required": ["database", "query"],
    }

    def __init__(self):
        self._ngdc = NgdcAdapter()

    def execute(self, database: str, query: str) -> str:
        result = self._ngdc.search(database, query)
        if result.success:
            return json.dumps(result.data, ensure_ascii=False, indent=2)
        return f"Error: {result.error}"


class GetEarthquakeEventsTool(Tool):
    name = "get_earthquake_events"
    description = "Get earthquake events from USGS Earthquake Hazards Program"
    parameters = {
        "type": "object",
        "properties": {
            "min_magnitude": {"type": "number", "description": "Minimum magnitude filter (default 2.5)"},
        },
    }

    def __init__(self):
        self._usgs = UsgsAdapter()

    def execute(self, min_magnitude: float = 2.5) -> str:
        result = self._usgs.get_earthquakes(min_magnitude=min_magnitude)
        if result.success:
            return json.dumps(result.data, ensure_ascii=False, indent=2)
        return f"Error: {result.error}"


class FetchArxivTool(Tool):
    name = "fetch_arxiv"
    description = "Fetch recent papers from arXiv by category"
    parameters = {
        "type": "object",
        "properties": {
            "category": {"type": "string", "description": "arXiv category (e.g. cs.AI, physics.hep-th, q-bio.QM)"},
            "limit": {"type": "integer", "description": "Number of results (default 5)"},
        },
        "required": ["category"],
    }

    def __init__(self):
        self._arxiv = ArxivAdapter()

    def execute(self, category: str, limit: int = 5) -> str:
        result = self._arxiv.fetch_by_category(category, limit)
        if result.success:
            return json.dumps(result.data, ensure_ascii=False, indent=2)
        return f"Error: {result.error}"


class ResolveDataciteTool(Tool):
    name = "resolve_datacite"
    description = "Resolve a DataCite DOI to get dataset metadata"
    parameters = {
        "type": "object",
        "properties": {
            "doi": {"type": "string", "description": "DataCite DOI identifier"},
        },
        "required": ["doi"],
    }

    def __init__(self):
        self._datacite = DataCiteAdapter()

    def execute(self, doi: str) -> str:
        result = self._datacite.resolve(doi)
        if result.success:
            return json.dumps(result.data, ensure_ascii=False, indent=2)
        return f"Error: {result.error}"


SCHOLAR_TOOLS = [
    SearchPapersTool,
    GetPaperByDoiTool,
    GetOaFulltextTool,
    SearchBiorxivTool,
    GetGeneInfoTool,
    GetVariantAnnotationTool,
    GetProteinStructureTool,
    AlignSequencesTool,
    GetCitationsTool,
    ListChinadoiTool,
    GetGenomeRegionTool,
    SearchNgdcTool,
    GetEarthquakeEventsTool,
    FetchArxivTool,
    ResolveDataciteTool,
]
