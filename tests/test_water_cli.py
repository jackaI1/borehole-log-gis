from pathlib import Path

from borehole_gis.water_cli import main


def test_pumping_cli_and_bad_metadata(tmp_path):
    assert main(['pumping', '--csv', 'samples/pumping/drawdown.csv', '--metadata',
                 'samples/pumping/pumping.json', '--out', str(tmp_path / 'pumping')]) == 0
    assert (tmp_path / 'pumping/report.json').is_file()
    bad = tmp_path / 'bad.json'
    bad.write_text('{}')
    assert main(['pumping', '--csv', 'samples/pumping/drawdown.csv', '--metadata',
                 str(bad), '--out', str(tmp_path / 'bad')]) == 2


def test_water_cli_and_preserves_input(tmp_path):
    inp = tmp_path / 'zone.inp'
    assert main(['water-demo', '--inp', str(inp)]) == 0
    original = inp.read_bytes()
    assert main(['water-demo', '--inp', str(inp)]) == 2
    assert inp.read_bytes() == original
    assert main(['water', '--inp', str(inp), '--out', str(tmp_path / 'results'), '--hydrants', 'B']) == 0
    assert Path(tmp_path / 'results/fire_flow.csv').is_file()
