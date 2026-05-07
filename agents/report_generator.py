"""
Report Generator - Haftalık rapor ve tez önerisi üretim ajanı.
Hocanın DOCX şablonuna uygun formatta rapor üretir.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from loguru import logger
from rich.console import Console

from agents.orchestrator import Orchestrator
from skills.fact_checker import FactChecker
from skills.credibility_scorer import CredibilityScorer

console = Console()


class ReportGenerator(Orchestrator):
    """Rapor üretim ajanı — DOCX formatında haftalık rapor ve tez önerisi üretir."""

    def __init__(self, config: dict, project_root: Path):
        super().__init__(config, project_root)
        self.reporting_config = config.get("reporting", {})
        self.template_path = project_root / self.reporting_config.get(
            "template_path", "templates/rapor_template.docx"
        )

    def generate_weekly_report(
        self,
        literature: Optional[List[Dict]] = None,
        patents: Optional[List[Dict]] = None,
        datasets: Optional[List[Dict]] = None,
        synthesis: Optional[Dict] = None,
    ) -> Path:
        """Haftalık ilerleme raporu üret."""
        self.start_time = datetime.now()
        week_number = datetime.now().isocalendar()[1]
        year = datetime.now().year
        
        # Veri yoksa diskten yükle
        if literature is None:
            literature = self._load_latest("papers/scholar_results")
        if patents is None:
            patents = self._load_latest("patents")
        if datasets is None:
            datasets = self._load_latest("datasets_catalog")
        if synthesis is None:
            synthesis = self._load_latest_synthesis()

        # Credibility Score hesapla
        credibility_scorer = CredibilityScorer(self.config)
        credibility = credibility_scorer.calculate_score(synthesis, literature)

        # LLM ile rapor içeriği üret
        report_content = self._generate_report_content(
            literature, patents, datasets, synthesis,
            week_number, year, credibility
        )

        # DOCX olarak kaydet
        output_path = self._save_as_docx(report_content, week_number, year)
        
        # Markdown kopya da kaydet (kolay okuma için)
        self._save_as_markdown(report_content, week_number, year)
        
        # HTML rapor oluştur (web görüntüleme için)
        html_content = self._generate_html_report(report_content, credibility, week_number, year)
        html_path = self._save_as_html(html_content, week_number, year)
        
        self.log_step("ReportGenerator", "generate", "success", str(output_path))
        console.print(f"  📄 Rapor kaydedildi: {output_path}")
        console.print(f"  🌐 HTML rapor: {html_path}")
        console.print(f"  🎯 Doğruluk Puanı: {credibility['overall_score']}/100 ({credibility['grade']})")
        
        return output_path

    def generate_thesis_proposal(self, synthesis: Optional[Dict] = None) -> Path:
        """Tez önerisi dokümanı üret."""
        if synthesis is None:
            synthesis = self._load_latest_synthesis()
        
        try:
            system_prompt = self.llm.load_system_prompt(
                "report_generator_system", self.project_root
            )
            
            prompt = f"""Aşağıdaki sentez verilerine dayanarak, Türkçe bir tez önerisi taslağı hazırla.

TEZ KONUSU: Multi-Agent Grid Load Negotiation for EV Charging
TÜRKÇE: Çoklu Ajan Şebeke Yük Pazarlığı

SENTEZ:
{json.dumps(synthesis, ensure_ascii=False, indent=2)}

Tez önerisi şu bölümleri içermeli:
1. Başlık ve Özet
2. Giriş ve Motivasyon
3. Literatür Özeti
4. Problem Tanımı
5. Önerilen Yöntem
6. Beklenen Katkılar
7. Zaman Planı
8. Kaynakça (en az 15 referans)

Markdown formatında yaz."""
            
            content = self.llm.generate(prompt, system_prompt)
        except Exception as e:
            logger.error(f"Tez önerisi üretim hatası: {e}")
            content = "# Tez Önerisi\n\nÜretim sırasında hata oluştu."
        
        # Kaydet
        output_dir = self.project_root / "reports" / "thesis_proposal"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d")
        md_path = output_dir / f"thesis_proposal_{timestamp}.md"
        md_path.write_text(content, encoding="utf-8")
        
        console.print(f"  📄 Tez önerisi kaydedildi: {md_path}")
        return md_path

    def _generate_report_content(
        self,
        literature: List[Dict],
        patents: List[Dict],
        datasets: List[Dict],
        synthesis: Dict,
        week_number: int,
        year: int,
        credibility: Optional[Dict] = None,
    ) -> str:
        """LLM ile rapor içeriğini üret ve kaynak referanslarını ekle."""
        try:
            system_prompt = self.llm.load_system_prompt(
                "report_generator_system", self.project_root
            )
            
            # Credibility badge (varsa)
            credibility_header = ""
            if credibility and isinstance(credibility, dict):
                overall_score = credibility.get("overall_score", 0)
                badge = CredibilityScorer().get_credibility_badge(overall_score)
                summary = credibility.get("summary", "Doğrulama bilgisi yok")
                credibility_header = f"""# 📊 Doğruluk Raporu

**{badge}**

{summary}

---

"""
            
            # Real papers table for context (hallücination prevention)
            top_papers = self._get_top_papers(literature, 5)
            papers_list = ""
            if top_papers:
                papers_list = "\n\nGERÇEK KİLİT MAKALELER (SADECE BUNLARı KULLAN - BAŞLIKLARI, YAZARLARI VE YILLARI EXACTLy):\n\n"
                papers_list += "| # | Başlık | Yazar | Yıl | Atıf |\n"
                papers_list += "|---|--------|-------|-----|-----|\n"
                for i, paper in enumerate(top_papers, 1):
                    title = paper.get('title', 'Başlık Yok')
                    author = paper.get('authors', 'Yazar Yok')
                    year = paper.get('year', 'N/A')
                    citations = paper.get('citation_count', 0)
                    papers_list += f"| [{i}] | {title} | {author} | {year} | {citations} |\n"
            
            prompt = f"""Haftalık İlerleme Raporu üret.

HAFTA: {year} - Hafta {week_number}
TARİH: {datetime.now().strftime('%d.%m.%Y')}
TEZ KONUSU: Çoklu Ajan Şebeke Yük Pazarlığı (Multi-Agent Grid Load Negotiation for EV Charging)

İSTATİSTİKLER:
- Taranan makale sayısı: {len(literature)}
- Taranan patent sayısı: {len(patents)}
- Bulunan veri seti sayısı: {len(datasets)}

SENTEZ SONUÇLARI:
{json.dumps(synthesis, ensure_ascii=False, indent=2)[:3000]}{papers_list}

Raporu şu bölümlerle Türkçe olarak yaz:
1. **Bu Hafta Yapılanlar**: Hangi aramalar yapıldı, kaç kaynak incelendi
2. **Bulgular Özeti**: En önemli bulgular (gap, trend, aktörler)
3. **Kilit Makaleler**: SADECE YUKARIDA LİSTELENEN gerçek makalelerden bir tablo oluştur. Başlık, Yazar, Yıl ve "Neden Önemli?" sütunları ekle.
4. **Patent Durumu**: Patent taraması sonuçları
5. **Veri Setleri**: Bulunan ilgili veri setleri
6. **Açık Sorular**: Danışmanla konuşulması gereken sorular
7. **Gelecek Hafta Planı**: Bir sonraki hafta yapılacaklar

Markdown formatında yaz. ÖNEMLI: Kilit Makaleler tablosunda SADECE gerçek makaleleri (yukarıda verilen liste) kullan. İcad et!"""
            
            report_content = credibility_header + self.llm.generate(prompt, system_prompt)
            
            # Kaynakça bölümü ekle
            references = self._build_bibliography(
                literature, patents, synthesis
            )
            
            if references:
                # Doğrulama özeti ekle (eğer credibility varsa)
                verification_section = ""
                if credibility and isinstance(credibility, dict):
                    stats = credibility.get("details", {})
                    if stats:
                        total_claims = stats.get('total_claims', 1)
                        verified = stats.get('verified', 0)
                        inference = stats.get('inference', 0)
                        hallucination = stats.get('hallucination', 0)
                        unverifiable = stats.get('unverifiable', 0)
                        
                        verification_section = f"""
## 📋 Doğrulama Detayları

- **Kontrol Edilen Bulgular**: {total_claims}
- **✅ Doğrulanmış**: {verified} ({verified / max(1, total_claims) * 100:.1f}%)
- **⚠️ Çıkartılabilir**: {inference} ({inference / max(1, total_claims) * 100:.1f}%)
- **❌ Hallüsinasyon**: {hallucination} ({hallucination / max(1, total_claims) * 100:.1f}%)
- **❓ Kontrol Edilemez**: {unverifiable}

"""
                
                report_content += verification_section + "\n\n---\n\n## Kaynaklar\n\n"
                report_content += references
            
            return report_content
        except Exception as e:
            logger.error(f"Rapor içeriği üretim hatası: {e}")
            return f"# Haftalık Rapor — Hafta {week_number}\n\nÜretim sırasında hata oluştu: {e}"

    def _get_top_papers(self, literature: List[Dict], count: int = 5) -> List[Dict]:
        """En ilgili makaleleri döndür (atıf sayısına göre)."""
        if not literature:
            return []
        
        # Citation count'a göre sırala
        sorted_papers = sorted(
            literature, 
            key=lambda x: x.get('citation_count', 0), 
            reverse=True
        )
        return sorted_papers[:count]

    def _save_as_docx(self, content: str, week_number: int, year: int) -> Path:
        """Raporu DOCX formatında kaydet."""
        output_dir = self.project_root / "reports" / "weekly"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d")
        output_path = output_dir / f"haftalik_rapor_W{week_number:02d}_{timestamp}.docx"
        
        try:
            from tools.docx_report import DocxReport
            docx_gen = DocxReport(self.template_path)
            docx_gen.generate_from_markdown(content, output_path)
            logger.info(f"DOCX rapor üretildi: {output_path}")
        except ImportError:
            logger.warning("docx_report modülü yüklenemedi, sadece markdown kaydedilecek")
            # Fallback: sadece txt kaydet
            txt_path = output_path.with_suffix(".txt")
            txt_path.write_text(content, encoding="utf-8")
            return txt_path
        except Exception as e:
            logger.error(f"DOCX üretim hatası: {e}")
            txt_path = output_path.with_suffix(".txt")
            txt_path.write_text(content, encoding="utf-8")
            return txt_path
        
        return output_path

    def _save_as_markdown(self, content: str, week_number: int, year: int) -> Path:
        """Raporu Markdown formatında kaydet."""
        output_dir = self.project_root / "reports" / "weekly"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d")
        md_path = output_dir / f"haftalik_rapor_W{week_number:02d}_{timestamp}.md"
        md_path.write_text(content, encoding="utf-8")
        
        return md_path
    
    def _generate_html_report(
        self, 
        markdown_content: str, 
        credibility: Optional[Dict],
        week_number: int, 
        year: int
    ) -> str:
        """Markdown raporunu HTML'e dönüştür (Doğruluk Badge ile)."""
        
        # Markdown -> HTML dönüştürme (basit regex)
        html_content = self._markdown_to_html(markdown_content)
        
        # Doğruluk badge'i oluştur (güvenli erişim)
        if not credibility or not isinstance(credibility, dict):
            credibility = {
                "overall_score": 0,
                "grade": "?",
                "summary": "Doğrulama bilgisi mevcut değil"
            }
        
        score = credibility.get("overall_score", 0)
        grade = credibility.get("grade", "?")
        summary = credibility.get("summary", "Doğrulama bilgisi mevcut değil")
        
        # Grade renkleri
        grade_colors = {
            "A": "#22c55e",  # Yeşil
            "B": "#3b82f6",  # Mavi
            "C": "#f59e0b",  # Turuncu
            "D": "#ef4444",  # Kırmızı
            "F": "#7f1d1d",  # Koyu kırmızı
        }
        
        badge_color = grade_colors.get(grade, "#6b7280")
        
        html = f"""<!DOCTYPE html>
<html lang="tr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Haftalık Rapor - W{week_number:02d} {year}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
            padding: 20px;
        }}
        
        .container {{
            max-width: 900px;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px 30px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 28px;
            margin-bottom: 10px;
        }}
        
        .header p {{
            opacity: 0.9;
            font-size: 14px;
        }}
        
        .credibility-badge {{
            background: {badge_color};
            color: white;
            padding: 20px;
            margin: 20px;
            border-radius: 8px;
            text-align: center;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }}
        
        .credibility-badge .score {{
            font-size: 40px;
            font-weight: bold;
            margin: 10px 0;
        }}
        
        .credibility-badge .grade {{
            font-size: 24px;
            font-weight: bold;
            margin: 5px 0;
        }}
        
        .credibility-badge .summary {{
            font-size: 12px;
            margin-top: 10px;
            opacity: 0.95;
            line-height: 1.4;
        }}
        
        .content {{
            padding: 40px 30px;
        }}
        
        h2 {{
            color: #667eea;
            margin-top: 30px;
            margin-bottom: 15px;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
            font-size: 20px;
        }}
        
        h3 {{
            color: #764ba2;
            margin-top: 20px;
            margin-bottom: 10px;
            font-size: 16px;
        }}
        
        p {{
            margin-bottom: 15px;
            text-align: justify;
        }}
        
        ul, ol {{
            margin-left: 20px;
            margin-bottom: 15px;
        }}
        
        li {{
            margin-bottom: 8px;
        }}
        
        strong {{
            color: #667eea;
        }}
        
        em {{
            font-style: italic;
            color: #666;
        }}
        
        .reference-section {{
            background: #f9fafb;
            padding: 20px;
            margin-top: 30px;
            border-left: 4px solid #667eea;
            border-radius: 4px;
        }}
        
        .reference-section h2 {{
            border-bottom: none;
            color: #333;
            font-size: 16px;
            margin-top: 0;
        }}
        
        .reference {{
            background: white;
            padding: 12px;
            margin: 10px 0;
            border-radius: 4px;
            border-left: 3px solid #667eea;
            font-size: 13px;
            line-height: 1.5;
        }}
        
        .footer {{
            background: #f9fafb;
            padding: 20px;
            text-align: center;
            color: #666;
            font-size: 12px;
            border-top: 1px solid #e5e7eb;
        }}
        
        code {{
            background: #f3f4f6;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Courier New', monospace;
            color: #d97706;
        }}
        
        blockquote {{
            border-left: 4px solid #667eea;
            padding-left: 20px;
            margin: 20px 0;
            color: #666;
            font-style: italic;
        }}
        
        a {{
            color: #667eea;
            text-decoration: none;
            border-bottom: 1px dotted #667eea;
        }}
        
        a:hover {{
            color: #764ba2;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        
        th {{
            background: #f3f4f6;
            padding: 12px;
            text-align: left;
            border-bottom: 2px solid #667eea;
        }}
        
        td {{
            padding: 12px;
            border-bottom: 1px solid #e5e7eb;
        }}
        
        tr:hover {{
            background: #f9fafb;
        }}
        
        @media (max-width: 600px) {{
            body {{
                padding: 10px;
            }}
            
            .header {{
                padding: 20px 15px;
            }}
            
            .header h1 {{
                font-size: 20px;
            }}
            
            .content {{
                padding: 20px 15px;
            }}
            
            .credibility-badge {{
                margin: 10px;
            }}
            
            .credibility-badge .score {{
                font-size: 32px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Haftalık İlerleme Raporu</h1>
            <p>Hafta {week_number} - {year} | Tez Konusu: Çoklu Ajan Şebeke Yük Pazarlığı</p>
        </div>
        
        <div class="credibility-badge">
            <div>📈 Doğruluk Değerlendirmesi</div>
            <div class="score">{score:.1f}</div>
            <div class="grade">Grade {grade}</div>
            <div class="summary">{summary.split(chr(10))[0]}</div>
        </div>
        
        <div class="content">
            {html_content}
        </div>
        
        <div class="footer">
            <p>Bu rapor otomatik olarak Thesis Research Agent tarafından oluşturulmuştur.</p>
            <p>Oluşturulma Tarihi: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}</p>
        </div>
    </div>
</body>
</html>"""
        
        return html
    
    def _markdown_to_html(self, markdown: str) -> str:
        """Basit Markdown -> HTML dönüştürücü."""
        import re
        
        html = markdown
        
        # Başlıklar
        html = re.sub(r'^### (.*?)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.*?)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.*?)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)
        
        # Listeler
        html = re.sub(r'^\- (.*?)$', r'<li>\1</li>', html, flags=re.MULTILINE)
        html = re.sub(r'((?:<li>.*?</li>\n?)+)', r'<ul>\1</ul>', html, flags=re.DOTALL)
        
        # Bold ve Italic
        html = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', html)
        html = re.sub(r'\*(.*?)\*', r'<em>\1</em>', html)
        html = re.sub(r'__(.*?)__', r'<strong>\1</strong>', html)
        html = re.sub(r'_(.*?)_', r'<em>\1</em>', html)
        
        # Paragraflar
        html = re.sub(r'\n\n', '</p><p>', html)
        html = '<p>' + html + '</p>'
        
        # Links
        html = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', html)
        
        # Code blocks
        html = re.sub(r'`(.*?)`', r'<code>\1</code>', html)
        
        # Horizontal rule
        html = re.sub(r'^---+$', r'<hr />', html, flags=re.MULTILINE)
        
        return html
    
    def _save_as_html(self, html_content: str, week_number: int, year: int) -> Path:
        """Raporu HTML formatında kaydet."""
        output_dir = self.project_root / "reports" / "weekly"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d")
        html_path = output_dir / f"haftalik_rapor_W{week_number:02d}_{timestamp}.html"
        html_path.write_text(html_content, encoding="utf-8")
        
        return html_path
    
    def _build_bibliography(
        self,
        literature: List[Dict],
        patents: List[Dict],
        synthesis: Dict
    ) -> str:
        """En ilgili kaynakları Markdown format'ta listele."""
        bibliography_footnotes = []
        
        # Synthesis'teki tüm source_indices'i topla
        referenced_indices = set()
        def extract_source_indices(obj):
            if isinstance(obj, dict):
                if "source_indices" in obj:
                    referenced_indices.update(obj["source_indices"])
                for value in obj.values():
                    extract_source_indices(value)
            elif isinstance(obj, list):
                for item in obj:
                    extract_source_indices(item)
        
        extract_source_indices(synthesis)
        
        # Eğer synthesis'te referans yoksa, en çok atıfı alan 10 makaleyi kullan
        if not referenced_indices:
            # Atıf sayısına göre sırala ve top 10'u seç
            sorted_literature = sorted(
                literature,
                key=lambda x: x.get('citation_count', 0),
                reverse=True
            )[:10]
            referenced_indices = set(range(min(10, len(sorted_literature))))
        
        # Kaynakları topla
        all_sources = literature + patents
        for ref_num, idx in enumerate(sorted(referenced_indices), 1):
            if idx < len(all_sources):
                source = all_sources[idx]
                title = source.get("title", "Başlık Bilinmiyor")
                authors = source.get("authors", "Yazarlar Bilinmiyor")
                year = source.get("year", "Yıl Bilinmiyor")
                venue = source.get("venue", "")
                
                # Markdown footnote format
                footnote = f"[^{ref_num}]: **{authors}** ({year}). {title}."
                if venue:
                    footnote += f" *{venue}*"
                
                bibliography_footnotes.append(footnote)
        
        # Kaynakça bölümü oluştur
        if bibliography_footnotes:
            return "\n\n".join(bibliography_footnotes)
        else:
            return "📚 **Kaynakça:** Bu rapor için en çok alıntı yapılan akademik kaynaklar listelenmiştir."


    def _load_latest(self, subdir: str) -> List[Dict]:
        """En son JSON dosyasını yükle."""
        data_dir = self.project_root / "data" / subdir
        if not data_dir.exists():
            return []
        
        json_files = sorted(data_dir.glob("*.json"), reverse=True)
        if not json_files:
            return []
        
        try:
            with open(json_files[0], "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception:
            return []

    def _load_latest_synthesis(self) -> Dict:
        """En son sentez dosyasını yükle."""
        summaries_dir = self.project_root / "data" / "summaries"
        if not summaries_dir.exists():
            return {}
        
        json_files = sorted(summaries_dir.glob("synthesis_*.json"), reverse=True)
        if not json_files:
            return {}
        
        try:
            with open(json_files[0], "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
