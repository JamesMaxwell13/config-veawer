from __future__ import annotations

import hashlib

from ..models import UMLConfiguration


class UMLConfigurationService:
    @staticmethod
    def calculate_checksum(source_text: str) -> str:
        return hashlib.sha256(source_text.encode("utf-8")).hexdigest()

    @classmethod
    def save_with_checksum(cls, uml: UMLConfiguration) -> UMLConfiguration:
        uml.checksum = cls.calculate_checksum(uml.source_text)
        uml.save()
        return uml

    @staticmethod
    def render_preview(uml: UMLConfiguration) -> str:
        if uml.diagram_type == UMLConfiguration.TYPE_PLANTUML:
            return (
                "<svg xmlns='http://www.w3.org/2000/svg' width='1200' height='120'>"
                "<rect x='1' y='1' width='1198' height='118' fill='#f8fafc' stroke='#94a3b8'/>"
                "<text x='20' y='35' font-size='18' fill='#0f172a'>PlantUML source stored</text>"
                "<text x='20' y='65' font-size='14' fill='#334155'>Use external PlantUML renderer for full output.</text>"
                "</svg>"
            )
        escaped = uml.source_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        title = "Mermaid source preview" if uml.diagram_type == UMLConfiguration.TYPE_MERMAID else "JSON source preview"
        return (
            "<svg xmlns='http://www.w3.org/2000/svg' width='1200' height='320'>"
            "<rect x='1' y='1' width='1198' height='318' fill='#f8fafc' stroke='#94a3b8'/>"
            f"<text x='20' y='30' font-size='16' fill='#0f172a'>{title}</text>"
            "<foreignObject x='20' y='45' width='1160' height='250'>"
            "<div xmlns='http://www.w3.org/1999/xhtml' style='font-family:monospace;white-space:pre-wrap;color:#334155'>"
            f"{escaped}</div></foreignObject></svg>"
        )
