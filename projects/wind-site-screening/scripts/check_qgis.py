"""Reopen a moved project and render its saved layout with real PyQGIS."""

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.append(str(Path(sys.prefix) / "share/qgis/python"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qgis.core import (  # noqa: E402
    QgsApplication,
    QgsLayoutExporter,
    QgsLayoutItemMap,
    QgsProject,
)


def check(directory):
    # Copying catches accidentally absolute layer sources and layout references.
    with tempfile.TemporaryDirectory(prefix="wind-qgis-check-") as tmp:
        moved = Path(tmp) / "moved"
        shutil.copytree(directory, moved)
        project_file = moved / "wind-screening.qgs"
        text = project_file.read_text()
        assert "/Users/" not in text and "/home/runner/" not in text
        project = QgsProject.instance()
        assert project.read(str(project_file))
        layers = list(project.mapLayers().values())
        assert len(layers) == 8
        assert all(layer.isValid() for layer in layers)
        assert all(str(moved) in layer.source() for layer in layers)
        layout = project.layoutManager().layoutByName("A4 screening overview")
        assert layout and layout.pageCollection().pageCount() == 1
        maps = [item for item in layout.items() if isinstance(item, QgsLayoutItemMap)]
        assert len(maps) == 1 and len(maps[0].layers()) == 7
        assert maps[0].crs() == project.crs()
        pdf_path = moved / "reopened-map.pdf"
        exporter = QgsLayoutExporter(layout)
        assert exporter.exportToPdf(str(pdf_path), QgsLayoutExporter.PdfExportSettings()) == 0
        assert pdf_path.read_bytes().startswith(b"%PDF")
        assert pdf_path.stat().st_size > 10000
        project.clear()
        print(
            json.dumps(
                {
                    "portable_valid_layers": 8,
                    "reopened_layout_pages": 1,
                    "reexported_pdf_bytes": pdf_path.stat().st_size,
                }
            )
        )


if __name__ == "__main__":
    app = QgsApplication([], False)
    app.initQgis()
    try:
        check(Path(sys.argv[1]))
    finally:
        app.exitQgis()
