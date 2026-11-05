"""Run with QGIS Python after rendering, to check the saved project and layout."""

import sys
from pathlib import Path

from PIL import Image, ImageStat
from qgis.core import QgsApplication, QgsProject


def verify(folder):
    project = QgsProject.instance()
    assert project.read(str(folder / "boreholes.qgz"))
    layers = list(project.mapLayers().values())
    assert len(layers) == 1 and layers[0].isValid()
    assert layers[0].featureCount() == 4
    assert layers[0].crs().authid() == "EPSG:3005"
    assert layers[0].labelsEnabled()
    assert len(layers[0].renderer().categories()) == 2
    layout = project.layoutManager().layoutByName("Borehole overview")
    assert layout is not None and len(layout.items()) >= 10
    assert (folder / "map.pdf").read_bytes().startswith(b"%PDF-")
    assert (folder / "map.pdf").stat().st_size > 10000
    with Image.open(folder / "map.png") as image:
        assert image.width > 1000 and image.height > 800
        assert max(ImageStat.Stat(image.convert("RGB")).stddev) > 10, "Blank map"
    print("QGIS integration passed: valid saved layer, CRS, labels, categories, layout, PDF and nonblank PNG")


app = QgsApplication([], False)
app.initQgis()
try:
    verify(Path(sys.argv[1]).resolve())
finally:
    QgsProject.instance().clear()
    app.exitQgis()
