"""Acceptance smoke tests (auto-generated)."""
import importlib

def test_smoke_imports_0():
    mod = importlib.import_module('sympy.polys.series')

def test_smoke_imports_1():
    mod = importlib.import_module('sympy.polys.series.base')
    assert hasattr(mod, 'PowerSeriesRingProto')
    assert hasattr(mod, 'series_pprint')

def test_smoke_imports_2():
    mod = importlib.import_module('sympy.polys.series.ring')
    assert hasattr(mod, 'PowerSeriesRingQQ')
    assert hasattr(mod, 'PowerSeriesRingZZ')
    assert hasattr(mod, 'TSeries')
    assert hasattr(mod, 'power_series_ring')

def test_smoke_imports_3():
    mod = importlib.import_module('sympy.polys.series.ringflint')
    assert hasattr(mod, 'FlintPowerSeriesRingQQ')
    assert hasattr(mod, 'FlintPowerSeriesRingZZ')
    assert hasattr(mod, '_get_series_precision')
    assert hasattr(mod, '_global_cap')

def test_smoke_imports_4():
    mod = importlib.import_module('sympy.polys.series.ringpython')
    assert hasattr(mod, 'PythonPowerSeriesRingQQ')
    assert hasattr(mod, 'PythonPowerSeriesRingZZ')
    assert hasattr(mod, '_unify_prec')
    assert hasattr(mod, '_useries')
    assert hasattr(mod, '_useries_add')
