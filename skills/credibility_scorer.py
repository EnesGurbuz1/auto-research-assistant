"""
Credibility Scorer - Rapor doğruluk puanı hesaplayıcısı.
Çeşitli metriklere dayanarak raporun doğruluk ve güvenilirlik puanını hesaplar.

Puanlama Metrikleri:
- Doğrulanmış bulguların yüzdesi (% Verified)
- Hallüsinasyon cezası (her hallüsinasyon için -10)
- Kaynak çeşitliliği bonusu
- Alıntı derinliği (kaynakların ne kadar kullanıldığı)
"""

from typing import Dict, List, Any
from loguru import logger


class CredibilityScorer:
    """Rapor doğruluk puanı hesaplayıcısı."""

    def __init__(self, config: dict = None):
        self.config = config or {}

    def calculate_score(
        self, verified_synthesis: Dict[str, Any], literature: List[Dict]
    ) -> Dict[str, Any]:
        """
        Rapor doğruluk puanını hesapla (0-100).

        Metrikleri:
        1. Verification Status Distribution (Verified/Inference/Hallucination oranı)
        2. Source Diversity (Kaç farklı kaynaktan)
        3. Citation Depth (Ortalama kaynaklar per claim)
        4. Hallucination Penalty (Her hallüsinasyon için ceza)
        5. Source Authority (Makalelerin yıl/atıf sayısı)

        Returns:
            {
                "overall_score": 85.5,
                "components": {
                    "verification_score": 85,
                    "diversity_score": 90,
                    "citation_score": 75,
                    ...
                },
                "details": {...},
                "grade": "A" / "B" / "C" / "F",
                "summary": "..."
            }
        """
        stats = verified_synthesis.get("_verification_stats", {})
        
        if not stats or stats.get("total_claims", 0) == 0:
            return {
                "overall_score": 0.0,
                "components": {},
                "details": {
                    "total_claims": 0,
                    "verified": 0,
                    "inference": 0,
                    "hallucination": 0,
                    "unverifiable": 0,
                },
                "grade": "??",
                "summary": "⏳ Doğrulama Bekleniyor: Bu rapor henüz FactChecker ile doğrulanmamıştır. Gelecek full-scan'dan sonra güvenilirlik puanı güncellenecektir.",
            }

        # 1. Verification Score (0-100) - Doğrulanan bulguların oranı
        verification_score = self._calculate_verification_score(stats)

        # 2. Diversity Score (0-100) - Kaynak çeşitliliği
        diversity_score = self._calculate_diversity_score(
            verified_synthesis, literature
        )

        # 3. Citation Score (0-100) - Alıntı derinliği
        citation_score = self._calculate_citation_score(verified_synthesis)

        # 4. Consistency Score (0-100) - İddialar arasında tutarlılık
        consistency_score = self._calculate_consistency_score(verified_synthesis)

        # Ağırlıklı ortalama
        weights = {
            "verification": 0.40,  # En önemli
            "diversity": 0.25,
            "citation": 0.20,
            "consistency": 0.15,
        }

        overall_score = (
            verification_score * weights["verification"]
            + diversity_score * weights["diversity"]
            + citation_score * weights["citation"]
            + consistency_score * weights["consistency"]
        )

        # Grade'i belirle
        grade = self._get_grade(overall_score)

        return {
            "overall_score": round(overall_score, 1),
            "components": {
                "verification_score": round(verification_score, 1),
                "diversity_score": round(diversity_score, 1),
                "citation_score": round(citation_score, 1),
                "consistency_score": round(consistency_score, 1),
            },
            "weights": weights,
            "details": {
                "total_claims": stats.get("total_claims", 0),
                "verified": stats.get("verified", 0),
                "inference": stats.get("inference", 0),
                "hallucination": stats.get("hallucination", 0),
                "unverifiable": stats.get("unverifiable", 0),
            },
            "grade": grade,
            "summary": self._generate_summary(overall_score, stats, grade),
        }

    def _calculate_verification_score(self, stats: Dict[str, int]) -> float:
        """
        Doğrulama durum puanı.
        - Verified: 100 puan
        - Inference: 70 puan
        - Hallucination: 0 puan (ceza: -20)
        - Unverifiable: 40 puan
        """
        total = stats.get("total_claims", 0)
        if total == 0:
            return 0.0

        verified = stats.get("verified", 0)
        inference = stats.get("inference", 0)
        hallucination = stats.get("hallucination", 0)
        unverifiable = stats.get("unverifiable", 0)

        # Puan hesapla
        score = (
            (verified * 100 + inference * 70 + unverifiable * 40) / total
        ) - (hallucination * 20)

        # 0-100 aralığında sınırla
        return max(0.0, min(100.0, score))

    def _calculate_diversity_score(
        self, verified_synthesis: Dict[str, Any], literature: List[Dict]
    ) -> float:
        """
        Kaynak çeşitliliği puanı.
        
        Metrik:
        - Kullanılan benzersiz kaynakların sayısı
        - Kaynakların yıl aralığı
        - Yayın türü çeşitliliği (makale vs patent)
        """
        # Tüm source_indices'leri topla
        used_indices = set()

        def extract_indices(obj):
            if isinstance(obj, dict):
                if "source_indices" in obj:
                    used_indices.update(obj["source_indices"])
                for value in obj.values():
                    extract_indices(value)
            elif isinstance(obj, list):
                for item in obj:
                    extract_indices(item)

        extract_indices(verified_synthesis)

        if not used_indices or not literature:
            return 50.0

        # Kullanılan kaynakları al
        used_sources = [
            literature[i] for i in used_indices if i < len(literature)
        ]

        # Yıl aralığı (recent kaynaklar daha iyi)
        years = [src.get("year", 0) for src in used_sources if src.get("year")]
        year_range = (max(years) - min(years)) if len(years) > 1 else 0
        year_bonus = min(30, year_range * 2)  # Max 30 bonus

        # Kaynak çeşitliliği
        sources_set = set([src.get("source", "Unknown") for src in used_sources])
        diversity_bonus = min(25, len(sources_set) * 5)

        # Temel puan
        base_score = (len(used_indices) / max(len(literature), 10)) * 70

        diversity_score = min(100.0, base_score + year_bonus + diversity_bonus)
        return diversity_score

    def _calculate_citation_score(self, verified_synthesis: Dict[str, Any]) -> float:
        """
        Alıntı derinliği puanı.
        
        Metrik:
        - Ortalama kaynaklar per claim (ne kadar çok kaynak, daha iyi)
        - Hiçbir kaynaktan hiç gelmezse ceza
        """
        claim_sources = []

        def extract_source_counts(obj):
            if isinstance(obj, dict):
                if "source_indices" in obj:
                    count = len(obj["source_indices"])
                    if count > 0:
                        claim_sources.append(count)
                for value in obj.values():
                    extract_source_counts(value)
            elif isinstance(obj, list):
                for item in obj:
                    extract_source_counts(item)

        extract_source_counts(verified_synthesis)

        if not claim_sources:
            return 30.0  # Nothing cited

        avg_citations = sum(claim_sources) / len(claim_sources)

        # 0-5 kaynak aralığında: 80-100, 5+: 100
        # Ortalama: avg_citations / 5 * 80 + 20
        citation_score = min(100.0, (avg_citations / 5) * 80 + 20)

        return citation_score

    def _calculate_consistency_score(
        self, verified_synthesis: Dict[str, Any]
    ) -> float:
        """
        Tutarlılık puanı.
        
        Metrik:
        - Benzer kategorilerdeki iddialar tutarlı mı?
        - Çelişkili bulgular varsa ceza
        """
        # Basit tutarlılık: Hallüsinasyon sayısı kontrol
        stats = verified_synthesis.get("_verification_stats", {})
        hallucinations = stats.get("hallucination", 0)
        total = stats.get("total_claims", 1)

        # Eğer % 0-5 hallüsinasyon: 100
        # % 5-15 hallüsinasyon: 70
        # % 15+ hallüsinasyon: 30
        hallucination_ratio = (hallucinations / total) * 100

        if hallucination_ratio <= 5:
            return 100.0
        elif hallucination_ratio <= 15:
            return 70.0
        elif hallucination_ratio <= 25:
            return 50.0
        else:
            return 30.0

    def _get_grade(self, score: float) -> str:
        """Puan'ı harf notu'na çevir."""
        if score == 0.0:
            return "VERIFICATION_PENDING"
        elif score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        else:
            return "F"

    def _generate_summary(
        self, score: float, stats: Dict[str, int], grade: str
    ) -> str:
        """Doğruluk puanının insan-okunabilir özeti."""
        total = stats.get("total_claims", 0)
        verified = stats.get("verified", 0)
        hallucination = stats.get("hallucination", 0)

        grade_descriptions = {
            "A": "Mükemmel - Bu rapor yüksek düzeyde akademik standartları karşılamaktadır.",
            "B": "İyi - Rapor genel olarak güvenilirdir, bazı minör sorunlar olabilir.",
            "C": "Orta - Rapor kontrol edilebili ama dikkatli okuma gerekir.",
            "D": "Zayıf - Raporda önemli sorunlar bulunmaktadır.",
            "F": "Kabul Edilmez - Bu rapor güvenilir değildir.",
        }

        verified_pct = (verified / total * 100) if total > 0 else 0
        hallucination_pct = (hallucination / total * 100) if total > 0 else 0

        description = grade_descriptions.get(
            grade,
            "Bilinmeyen notu",
        )

        summary = f"""{grade} ({score}/100) - {description}

Detaylar:
- Doğrulanmış bulgular: {verified_pct:.0f}%
- Hallüsinasyon oranı: {hallucination_pct:.0f}%
- Kontrol edilen toplam iddia: {total}

Not: Bu puan, kaynaklar karşında doğru olduğu kanıtlanabilir iddiaların oranına dayanır."""

        return summary

    def get_credibility_badge(self, score: float) -> str:
        """HTML badge için renk ve simge."""
        grade = self._get_grade(score)
        emojis = {
            "A": "🟢",
            "B": "🟡",
            "C": "🟠",
            "D": "🔴",
            "F": "⛔",
            "VERIFICATION_PENDING": "⏳",
            "UNKNOWN": "❓",
        }
        labels = {
            "A": "Çok Güvenilir",
            "B": "Güvenilir",
            "C": "Kontrol Gerekli",
            "D": "Şüpheli",
            "F": "Güvenilmez",
            "VERIFICATION_PENDING": "Doğrulama Bekleniyor",
            "UNKNOWN": "Bikinmiyor",
        }
        return f"{emojis.get(grade, '?')} Grade {grade} - {labels.get(grade, '?')}"
