"""Run with QGIS's Python: python qgis_export.py results-directory.

Uses the real PyQGIS API to style, save, reopen and render the project. No XML templates.
"""

import json
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

# Conda QGIS puts its Python bindings here, unlike Debian's system Python.
sys.path.append(str(Path(sys.prefix) / "share/qgis/python"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from qgis.core import (  # noqa: E402
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsFillSymbol,
    QgsLayoutExporter,
    QgsLayoutItemLabel,
    QgsLayoutItemLegend,
    QgsLayoutItemMap,
    QgsLayoutItemPage,
    QgsLayoutItemScaleBar,
    QgsLayoutPoint,
    QgsLayoutSize,
    QgsLineSymbol,
    QgsPalLayerSettings,
    QgsPrintLayout,
    QgsProject,
    QgsRasterLayer,
    QgsReferencedRectangle,
    QgsRuleBasedRenderer,
    QgsTextFormat,
    QgsVectorLayer,
    QgsVectorLayerSimpleLabeling,
)
from qgis.PyQt.QtGui import QColor, QFont  # noqa: E402


def label(layout, text, x, y, width, height, size=10, bold=False):
    item = QgsLayoutItemLabel(layout)
    item.setText(text)
    font = QFont("DejaVu Sans", size)
    font.setBold(bold)
    # QGIS 4 uses text formats; 3.x also supports these since 3.24.
    fmt = QgsTextFormat()
    fmt.setFont(font)
    fmt.setSize(size)
    fmt.setColor(QColor("#16343b"))
    item.setTextFormat(fmt)
    layout.addLayoutItem(item)
    item.attemptMove(QgsLayoutPoint(x, y))
    item.attemptResize(QgsLayoutSize(width, height))
    return item


def build(directory):
    directory = Path(directory).resolve()
    run = json.loads((directory / "run.json").read_text())
    config = run["config"]
    project = QgsProject.instance()
    project.clear()
    project.setFileName(str(directory / "wind-screening.qgs"))
    project.setCrs(QgsCoordinateReferenceSystem(config["analysis_crs"]))
    project.setFilePathStorage(Qgis.FilePathType.Relative)
    project.setTitle(config["name"])
    top = config["top_sites"]
    raster = QgsRasterLayer(str(directory / "wind_100m.tif"), "Wind at 100 m (m/s)")
    if not raster.isValid():
        raise ValueError("QGIS cannot read the wind raster")
    raster.setOpacity(0.45)
    project.addMapLayer(raster)
    layer_names = [
        "water",
        "protected",
        "setbacks",
        "roads",
        "transmission",
        "usable_land",
        "candidates",
    ]
    colors = {
        "water": "#aedce6",
        "protected": "#83b791",
        "setbacks": "#e0bba4",
        "usable_land": "#d5e7c4",
    }
    layers = {}
    for name in layer_names:
        layer = QgsVectorLayer(f"{directory / 'screening.gpkg'}|layername={name}", name, "ogr")
        if not layer.isValid():
            raise ValueError(f"QGIS cannot read {name}")
        if name in {"roads", "transmission"}:
            layer.renderer().setSymbol(
                QgsLineSymbol.createSimple(
                    {
                        "line_color": "#b4662b" if name == "transmission" else "#737d80",
                        "line_width": "0.65" if name == "transmission" else "0.2",
                    }
                )
            )
        elif name == "candidates":
            root = QgsRuleBasedRenderer.Rule(None)
            for expression, color, title in [
                (f'"rank" <= {top}', "#17645b", f"Top {top} eligible areas"),
                (f'"eligible" = 1 AND "rank" > {top}', "#c4d9ad", "Other eligible areas"),
                ('"eligible" = 0', "#c8c8c8", "Excluded areas"),
            ]:
                symbol = QgsFillSymbol.createSimple(
                    {
                        "color": color,
                        "outline_color": "#ffffff",
                        "outline_width": "0.18",
                    }
                )
                symbol.setOpacity(0.62)
                root.appendChild(QgsRuleBasedRenderer.Rule(symbol, 0, 0, expression, title))
            layer.setRenderer(QgsRuleBasedRenderer(root))
            settings = QgsPalLayerSettings()
            settings.fieldName = f'CASE WHEN "rank" <= {top} THEN "site_id" END'
            settings.isExpression = True
            fmt = QgsTextFormat()
            fmt.setFont(QFont("DejaVu Sans", 9))
            fmt.setSize(9)
            fmt.setColor(QColor("#113c35"))
            settings.setFormat(fmt)
            layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
            layer.setLabelsEnabled(True)
        else:
            layer.renderer().setSymbol(
                QgsFillSymbol.createSimple(
                    {
                        "color": colors[name],
                        "outline_style": "no",
                    }
                )
            )
        layer.setName(
            {
                "transmission": "Mapped hydro lines (voltage unknown)",
                "roads": "Ontario roads",
                "water": "Water bodies",
                "protected": "Regulated provincial parks",
                "setbacks": "Scenario setbacks",
                "usable_land": "Land outside setbacks",
                "candidates": "Candidate areas",
            }[name]
        )
        project.addMapLayer(layer)
        layers[name] = layer
    # Candidate fills are below roads and constraints so those remain inspectable on paper.
    order = [
        layers[n]
        for n in [
            "transmission",
            "roads",
            "protected",
            "water",
            "setbacks",
            "candidates",
            "usable_land",
        ]
    ] + [raster]
    project.layerTreeRoot().setHasCustomLayerOrder(True)
    project.layerTreeRoot().setCustomLayerOrder(order)
    project.layerTreeRoot().findLayer(layers["usable_land"].id()).setItemVisibilityChecked(False)
    visible = [lyr for lyr in order if lyr != layers["usable_land"]]
    extent = layers["candidates"].extent()
    extent.scale(1.06)
    project.viewSettings().setDefaultViewExtent(
        # ReferencedRectangle is needed for saved default canvas extents.
        QgsReferencedRectangle(extent, project.crs())
    )
    layout = QgsPrintLayout(project)
    layout.initializeDefaults()
    layout.setName("A4 screening overview")
    layout.pageCollection().pages()[0].setPageSize("A4", QgsLayoutItemPage.Landscape)
    layout.renderContext().setDpi(150)
    project.layoutManager().addLayout(layout)
    label(layout, "WIND SITE SCREENING", 10, 7, 200, 10, 18, True)
    label(layout, config["name"] + " | desktop comparison", 10, 19, 210, 7, 10)
    map_item = QgsLayoutItemMap(layout)
    layout.addLayoutItem(map_item)
    map_item.attemptMove(QgsLayoutPoint(10, 31))
    map_item.attemptResize(QgsLayoutSize(185, 158))
    map_item.setCrs(project.crs())
    map_item.setLayers(visible)
    map_item.setKeepLayerSet(True)
    map_item.zoomToExtent(extent)
    map_item.setFrameEnabled(True)
    legend = QgsLayoutItemLegend(layout)
    legend.setTitle("Map key")
    legend.setLinkedMap(map_item)
    legend.setAutoUpdateModel(False)
    root = legend.model().rootGroup()
    root.clear()
    for name in ["candidates", "transmission", "roads", "setbacks", "water", "protected"]:
        root.addLayer(layers[name])
    layout.addLayoutItem(legend)
    legend.attemptMove(QgsLayoutPoint(202, 30))
    legend.attemptResize(QgsLayoutSize(84, 69))
    label(
        layout,
        f"{run['eligible_count']} of {run['candidate_count']} areas pass\n"
        "the selected screening assumptions.\n\n"
        "Score / 100\n"
        f"{config['weights']['wind']:.0%} wind + {config['weights']['grid']:.0%} grid distance\n"
        f"+ {config['weights']['usable']:.0%} land outside setbacks.\n\n"
        "Setbacks (m)\n" + "\n".join(f"{k}: {v}" for k, v in config["setbacks_m"].items()),
        202,
        103,
        85,
        62,
        9,
    )
    scale = QgsLayoutItemScaleBar(layout)
    scale.setStyle("Single Box")
    scale.setLinkedMap(map_item)
    scale.applyDefaultSize()
    scale.setUnits(Qgis.DistanceUnit.Kilometers)
    scale.setUnitsPerSegment(2)
    scale.setNumberOfSegments(2)
    scale.setNumberOfSegmentsLeft(0)
    scale.setUnitLabel("km")
    layout.addLayoutItem(scale)
    scale.attemptMove(QgsLayoutPoint(13, 176))
    label(layout, "Grid north is up | " + config["analysis_crs"] + " (metres)", 10, 190, 187, 6, 8)
    label(
        layout,
        "Study cells are not legal parcels. No grid capacity or approval implied.\n"
        "Data: Ontario open data (OGL Ontario); "
        "GWA 4.0, DTU / World Bank / Vortex / ESMAP (CC BY 4.0).",
        10,
        197,
        280,
        10,
        7,
    )
    if not project.write():
        raise ValueError("QGIS project write failed")
    # Layout items retain absolute fallback sources even with relative storage.
    # Make those portable and omit workstation identity from the public project.
    path = directory / "wind-screening.qgs"
    tree = ET.parse(path)
    for key in ("saveUser", "saveUserFull"):
        tree.getroot().attrib.pop(key, None)
    for element in tree.iter():
        for key, value in element.attrib.items():
            if value.startswith(str(directory) + "/"):
                element.set(key, "." + value[len(str(directory)) :])
        if element.text and element.text.startswith(str(directory) + "/"):
            element.text = "." + element.text[len(str(directory)) :]
    tree.write(path, encoding="utf-8", xml_declaration=True)
    # Reopen from disk before exporting; this catches missing providers and broken paths.
    project.clear()
    if not project.read(str(directory / "wind-screening.qgs")):
        raise ValueError("Saved QGIS project cannot be reopened")
    if not all(layer.isValid() for layer in project.mapLayers().values()):
        raise ValueError("Saved project has invalid layers")
    saved = project.layoutManager().layoutByName("A4 screening overview")
    exporter = QgsLayoutExporter(saved)
    pdf = QgsLayoutExporter.PdfExportSettings()
    pdf.dpi = 150
    if exporter.exportToPdf(str(directory / "screening-map.pdf"), pdf) != QgsLayoutExporter.Success:
        raise ValueError("QGIS PDF export failed")
    png = QgsLayoutExporter.ImageExportSettings()
    png.dpi = 110
    png.generateWorldFile = False
    if (
        exporter.exportToImage(str(directory / "screening-map.png"), png)
        != QgsLayoutExporter.Success
    ):
        raise ValueError("QGIS PNG export failed")
    print(
        json.dumps(
            {
                "qgis": Qgis.QGIS_VERSION,
                "valid_layers": len(project.mapLayers()),
                "layout": saved.name(),
                "project": "wind-screening.qgs",
            }
        )
    )
    project.clear()


if __name__ == "__main__":
    application = QgsApplication([], False)
    application.initQgis()
    try:
        build(sys.argv[1])
    finally:
        application.exitQgis()
