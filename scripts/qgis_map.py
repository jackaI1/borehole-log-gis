"""Render a QGIS project and map layout with QGIS's own Python interpreter.

Usage: QT_QPA_PLATFORM=offscreen /usr/bin/python3 scripts/qgis_map.py build/bc
The input folder must contain the validated boreholes.gpkg and validation.json.
"""

import argparse
import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def build_map(folder):
    from qgis.core import (
        QgsCategorizedSymbolRenderer,
        QgsLayoutExporter,
        QgsLayoutItemLabel,
        QgsLayoutItemLegend,
        QgsLayoutItemMap,
        QgsLayoutItemPage,
        QgsLayoutItemScaleBar,
        QgsLayoutPoint,
        QgsLayoutSize,
        QgsMarkerSymbol,
        QgsPalLayerSettings,
        QgsPrintLayout,
        QgsProject,
        QgsRectangle,
        QgsReferencedRectangle,
        QgsRendererCategory,
        QgsTextBufferSettings,
        QgsTextFormat,
        QgsUnitTypes,
        QgsVectorLayer,
        QgsVectorLayerSimpleLabeling,
    )
    from qgis.PyQt.QtGui import QColor, QFont

    if not (folder / "manifest.json").is_file():
        raise ValueError("Input folder has no completed export manifest")
    report = json.loads((folder / "validation.json").read_text())
    if report["errors"]:
        raise ValueError("Map generation is blocked by validation errors")
    project = QgsProject.instance()
    project.clear()
    layer = QgsVectorLayer(
        str(folder / "boreholes.gpkg") + "|layername=boreholes", "Borehole log coverage", "ogr"
    )
    if not layer.isValid() or layer.featureCount() == 0:
        raise ValueError("No valid boreholes layer")
    project.setCrs(layer.crs())
    project.addMapLayer(layer)
    categories = []
    for value, color, label in [(0, "#277773", "No flagged warnings"), (1, "#c66b32", "Review warnings")]:
        symbol = QgsMarkerSymbol.createSimple(
            {
                "name": "circle",
                "color": color,
                "size": "4",
                "outline_color": "#ffffff",
                "outline_width": "0.5",
            }
        )
        categories.append(QgsRendererCategory(value, symbol, label))
    layer.setRenderer(QgsCategorizedSymbolRenderer('CASE WHEN "warnings" > 0 THEN 1 ELSE 0 END', categories))
    settings = QgsPalLayerSettings()
    settings.fieldName = "hole_id"
    text_format = QgsTextFormat()
    text_format.setFont(QFont("DejaVu Sans", 9))
    text_format.setSize(9)
    buffer = QgsTextBufferSettings()
    buffer.setEnabled(True)
    buffer.setSize(0.8)
    buffer.setColor(QColor("white"))
    text_format.setBuffer(buffer)
    settings.setFormat(text_format)
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)

    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName("Borehole overview")
    layout.pageCollection().pages()[0].setPageSize("A4", QgsLayoutItemPage.Landscape)

    def label(text, x, y, width, height, size=10):
        item = QgsLayoutItemLabel(layout)
        item.setText(text)
        item.setFont(QFont("DejaVu Sans", size))
        layout.addLayoutItem(item)
        item.attemptMove(QgsLayoutPoint(x, y))
        item.attemptResize(QgsLayoutSize(width, height))
        return item

    label("BOREHOLE LOG OVERVIEW", 12, 8, 270, 12, 20)
    label(
        f"{report['holes']} boreholes | {report['intervals']} logged intervals | "
        f"{report['warnings']} warnings to review",
        12,
        23,
        270,
        10,
    )
    map_item = QgsLayoutItemMap(layout)
    layout.addLayoutItem(map_item)
    map_item.attemptMove(QgsLayoutPoint(12, 39))
    map_item.attemptResize(QgsLayoutSize(202, 145))
    map_item.setLayers([layer])
    map_item.setKeepLayerSet(True)
    map_item.setCrs(layer.crs())
    extent = QgsRectangle(layer.extent())
    # Give a single borehole a useful local extent, rather than a zero-sized map.
    if extent.width() < 100:
        extent.setXMinimum(extent.center().x() - 100)
        extent.setXMaximum(extent.xMinimum() + 200)
    if extent.height() < 100:
        extent.setYMinimum(extent.center().y() - 100)
        extent.setYMaximum(extent.yMinimum() + 200)
    extent.scale(1.25)
    map_item.zoomToExtent(extent)
    map_item.setFrameEnabled(True)
    project.viewSettings().setDefaultViewExtent(QgsReferencedRectangle(map_item.extent(), layer.crs()))

    legend = QgsLayoutItemLegend(layout)
    legend.setTitle("Data checks")
    layout.addLayoutItem(legend)
    legend.attemptMove(QgsLayoutPoint(221, 43))
    legend.setLinkedMap(map_item)
    legend.setAutoUpdateModel(False)
    legend.model().rootGroup().clear()
    legend.model().rootGroup().addLayer(layer)
    label("N\n^", 265, 79, 12, 20, 14)
    scale = QgsLayoutItemScaleBar(layout)
    scale.setStyle("Single Box")
    scale.setLinkedMap(map_item)
    scale.applyDefaultSize()
    scale.setUnits(QgsUnitTypes.DistanceMeters)
    scale.setUnitsPerSegment(max(1, round(map_item.extent().width() / 1000) * 100))
    scale.setNumberOfSegments(2)
    scale.setNumberOfSegmentsLeft(0)
    scale.setUnitLabel("m")
    layout.addLayoutItem(scale)
    scale.attemptMove(QgsLayoutPoint(221, 106))
    label(
        "Depths below ground, in metres.\nBlank log intervals remain unlogged.\nWarnings are in issues.csv.\nNo basemap or ground conditions inferred.",
        221,
        131,
        66,
        42,
        8,
    )
    label(
        f"Map CRS: {layer.crs().authid()} | Source: {Path(report['source']).name}\n"
        "Public source attribution and licences: samples/*.source.json | Check original records before use.",
        12,
        188,
        276,
        15,
        8,
    )
    project.layoutManager().addLayout(layout)
    project.setFileName(str(folder / "boreholes.qgz"))
    if not project.write():
        raise RuntimeError("Could not save QGIS project")
    exporter = QgsLayoutExporter(layout)
    pdf = QgsLayoutExporter.PdfExportSettings()
    pdf.dpi = 150
    if exporter.exportToPdf(str(folder / "map.pdf"), pdf) != QgsLayoutExporter.Success:
        raise RuntimeError("QGIS PDF export failed")
    png = QgsLayoutExporter.ImageExportSettings()
    png.dpi = 120
    if exporter.exportToImage(str(folder / "map.png"), png) != QgsLayoutExporter.Success:
        raise RuntimeError("QGIS PNG export failed")
    print(f"Saved styled project, PDF and PNG for {layer.featureCount()} boreholes in {folder}")


def main():
    from qgis.core import QgsApplication, QgsProject

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    args = parser.parse_args()
    app = QgsApplication([], False)
    app.initQgis()
    try:
        build_map(args.folder.resolve())
    finally:
        QgsProject.instance().clear()
        app.exitQgis()


if __name__ == "__main__":
    main()
