"""
Citation Network - Atıf ağı analizi ve görselleştirme.
Makaleler arası atıf ilişkilerini haritalandırır.
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from loguru import logger

try:
    import networkx as nx
except ImportError:
    nx = None

try:
    from pyvis.network import Network
except ImportError:
    Network = None


class CitationNetwork:
    """Atıf ağı analizi ve görselleştirme aracı."""

    def __init__(self, config: dict, project_root: Optional[Path] = None):
        self.config = config
        self.project_root = project_root
        
        if nx is None:
            logger.warning("networkx yüklü değil: pip install networkx")

    def build_network(self, papers: List[Dict]) -> Optional[Any]:
        """Makale listesinden atıf ağı oluştur."""
        if nx is None:
            return None

        G = nx.DiGraph()

        for paper in papers:
            paper_id = paper.get("paper_id") or paper.get("title", "")
            G.add_node(paper_id, **{
                "title": paper.get("title", ""),
                "year": paper.get("year", ""),
                "citations": paper.get("citation_count", 0),
                "source": paper.get("source", ""),
            })

        logger.info(f"Atıf ağı oluşturuldu: {G.number_of_nodes()} düğüm, {G.number_of_edges()} kenar")
        return G

    def analyze_network(self, G) -> Dict[str, Any]:
        """Ağ analizleri yap (merkezilik, topluluk tespiti vb.)."""
        if nx is None or G is None:
            return {}

        analysis = {
            "node_count": G.number_of_nodes(),
            "edge_count": G.number_of_edges(),
        }

        if G.number_of_nodes() > 0:
            # Degree centrality
            degree_cent = nx.degree_centrality(G)
            top_by_degree = sorted(degree_cent.items(), key=lambda x: x[1], reverse=True)[:10]
            analysis["top_by_centrality"] = [
                {"id": k, "centrality": round(v, 4)} for k, v in top_by_degree
            ]

            # PageRank (eğer yeterli kenar varsa)
            if G.number_of_edges() > 0:
                try:
                    pagerank = nx.pagerank(G)
                    top_by_pr = sorted(pagerank.items(), key=lambda x: x[1], reverse=True)[:10]
                    analysis["top_by_pagerank"] = [
                        {"id": k, "pagerank": round(v, 4)} for k, v in top_by_pr
                    ]
                except Exception:
                    pass

        return analysis

    def visualize(self, G, output_path: Optional[Path] = None) -> Optional[Path]:
        """Ağı interaktif HTML olarak görselleştir."""
        if Network is None or G is None:
            logger.warning("pyvis yüklü değil, görselleştirme atlanıyor")
            return None

        if output_path is None and self.project_root:
            output_path = self.project_root / "reports" / "literature_review" / "citation_network.html"
        
        if output_path is None:
            return None

        try:
            net = Network(height="750px", width="100%", directed=True)
            net.from_nx(G)
            
            output_path.parent.mkdir(parents=True, exist_ok=True)
            net.save_graph(str(output_path))
            logger.info(f"Atıf ağı görselleştirmesi kaydedildi: {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Görselleştirme hatası: {e}")
            return None
