import pytest

from conftest import make_archive, make_composite
from radolan import Composite, lonlat_to_grid, parse_composite, read_archive


@pytest.mark.parametrize(
    "name,lon,lat,col,row",
    [
        ("Bornheimer Strasse 144", 7.0822, 50.7377, 326.69, 625.29),
        ("Konrad-Zuse-Platz", 7.1544, 50.7179, 331.92, 627.87),
        ("Koeln", 6.960, 50.938, 318.87, 601.43),
        ("Hamburg", 9.993, 53.551, 542.72, 304.40),
        ("Muenchen", 11.575, 48.137, 668.53, 935.78),
    ],
)
def test_projection_matches_reference_points(name, lon, lat, col, row):
    got_col, got_row = lonlat_to_grid(lon, lat)
    assert got_col == pytest.approx(col, abs=0.01)
    assert got_row == pytest.approx(row, abs=0.01)


def test_row_axis_points_north():
    """Zeile 0 liegt im Norden - Hamburg muss eine kleinere Zeile haben als Muenchen."""
    _, hamburg = lonlat_to_grid(9.993, 53.551)
    _, munich = lonlat_to_grid(11.575, 48.137)
    assert hamburg < munich


def test_parse_reads_header_and_values():
    blob = make_composite({(625, 327): 0.42}, forecast_minutes=15)
    comp = parse_composite(blob)
    assert comp.forecast_minutes == 15
    assert comp.rows == 1200
    assert comp.cols == 1100
    assert comp.value_at(625, 327) == pytest.approx(0.42)


def test_missing_coverage_is_none_not_zero():
    """Ausserhalb der Radarabdeckung ist unbekannt, nicht trocken."""
    comp = parse_composite(make_composite({(625, 327): 0.42}))
    assert comp.value_at(0, 0) is None


def test_parse_rejects_truncated_payload():
    blob = make_composite({(625, 327): 0.1})
    with pytest.raises(ValueError, match="unvollstaendig"):
        parse_composite(blob[: len(blob) // 2])


def test_read_archive_returns_sorted_timesteps():
    blob = make_archive([make_composite(forecast_minutes=m) for m in (10, 0, 5)])
    comps = read_archive(blob)
    assert [c.forecast_minutes for c in comps] == [0, 5, 10]
    assert all(isinstance(c, Composite) for c in comps)


def test_crop_keeps_global_coordinates():
    """Der Ausschnitt muss unter denselben Koordinaten ansprechbar bleiben."""
    comp = parse_composite(make_composite({(625, 327): 0.42, (700, 700): 9.9}))
    small = comp.crop(620, 320, 20, 20)
    assert small.value_at(625, 327) == pytest.approx(0.42)
    assert small.value_at(700, 700) is None      # ausserhalb des Ausschnitts


def test_crop_is_small():
    """Ein voller Zeitschritt hat 1,32 Mio Werte, der Ausschnitt nur 400."""
    small = parse_composite(make_composite({})).crop(620, 320, 20, 20)
    assert small.rows * small.cols == 400


def test_crop_beyond_the_grid_is_missing_not_zero():
    small = parse_composite(make_composite({})).crop(-5, -5, 10, 10)
    assert small.value_at(-3, -3) is None


def test_read_archive_can_skip_the_forecast():
    """Fuer die Historie zaehlt nur der Nullschritt - der Rest waere verschenkte Zeit."""
    blob = make_archive([make_composite(forecast_minutes=m) for m in (0, 5, 10)])
    comps = read_archive(blob, only_first=True)
    assert [c.forecast_minutes for c in comps] == [0]


@pytest.mark.parametrize("lon,lat", [
    (7.0822, 50.7377), (6.960, 50.938), (9.993, 53.551),
    (11.575, 48.137), (13.405, 52.520), (8.682, 50.110),
])
def test_grid_roundtrip(lon, lat):
    """Die Umkehrung muss den Ausgangspunkt treffen, sonst sitzt die Historie schief."""
    from radolan import grid_to_lonlat
    col, row = lonlat_to_grid(lon, lat)
    back_lon, back_lat = grid_to_lonlat(col, row)
    assert back_lon == pytest.approx(lon, abs=1e-6)
    assert back_lat == pytest.approx(lat, abs=1e-6)


def test_yw_grid_matches_verified_reference_points():
    """Gegen die Gueltigkeitsmaske einer echten YW-Datei geprueft."""
    from radolan import lonlat_to_grid900
    for lon, lat, ecol, erow in [(9.993, 53.551, 522.48, 154.62),
                                 (6.960, 50.938, 299.35, 451.45),
                                 (11.575, 48.137, 647.93, 785.70),
                                 (7.0822, 50.7377, 307.14, 475.29)]:
        col, row = lonlat_to_grid900(lon, lat)
        assert col == pytest.approx(ecol, abs=0.02)
        assert row == pytest.approx(erow, abs=0.02)


def test_both_grids_agree_on_the_route():
    """Zwei unabhaengige Projektionen muessen dieselbe Geometrie ergeben."""
    from radolan import lonlat_to_grid900
    home, work = (7.0822, 50.7377), (7.1544, 50.7179)
    a = [lonlat_to_grid(*home), lonlat_to_grid(*work)]
    b = [lonlat_to_grid900(*home), lonlat_to_grid900(*work)]
    da = ((a[1][0] - a[0][0]) ** 2 + (a[1][1] - a[0][1]) ** 2) ** 0.5
    db = ((b[1][0] - b[0][0]) ** 2 + (b[1][1] - b[0][1]) ** 2) ** 0.5
    assert da == pytest.approx(db, abs=0.05)


def test_mapping_points_de1200_cells_at_their_yw_counterparts():
    """Bonn liegt im DE1200-Gitter bei (625, 327), im YW-Gitter bei (475, 307)."""
    from radolan import build_mapping
    mapping = build_mapping(620, 322, 12, 12)
    assert len(mapping) == 144
    r9, c9 = mapping[(625 - 620) * 12 + (327 - 322)]
    assert (r9, c9) == (475, 307)


def test_resampling_carries_values_into_the_de1200_window():
    """Ein Wert an der YW-Stelle muss an der DE1200-Stelle wieder auftauchen."""
    from radolan import build_mapping, resample_to_de1200
    mapping = build_mapping(620, 322, 12, 12)
    src = parse_composite(make_composite({(475, 307): 1.23}, rows=900, cols=900))
    out = resample_to_de1200(src, 620, 322, 12, 12, mapping)
    assert out.rows == 12 and out.cols == 12
    assert out.value_at(625, 327) == pytest.approx(1.23)
    assert out.value_at(620, 322) is None      # dort war im Original nichts


def test_measurement_without_vv_field_parses():
    """YW ist eine Messung und traegt kein VV-Feld - der Parser darf das nicht verlangen."""
    blob = make_composite({(475, 307): 0.3}, rows=900, cols=900)
    head, body = blob.split(b"\x03", 1)
    head = head.replace(b"VV 000", b"")           # Feld entfernen wie im Original
    comp = parse_composite(head + b"\x03" + body)
    assert comp.forecast_minutes == 0
    assert comp.rows == 900 and comp.cols == 900
    assert comp.value_at(475, 307) == pytest.approx(0.3)
