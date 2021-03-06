#!/usr/bin/env python
"""
Description
"""
import pandas as pd
from pkg_resources import resource_filename

from modesto import utils
from modesto.parameter import SeriesParameter


def test_extrapolate_down():
    param = set_up_series_param()
    assert param.v(-1) == -1


def test_extrapolate_up():
    param = set_up_series_param()
    assert param.v(1.5) == 1.5


def test_interpolate():
    param = set_up_series_param()
    assert param.v(0.5) == 0.5


def test_exact_index():
    param = set_up_series_param()
    assert param.v(1) == 1


def set_up_series_param():
    df = pd.Series(index=[0, 1], data=[0, 1], name='cost')
    param = SeriesParameter('cost', 'cost in function of volume', 'EUR', 'm3', val=df)
    return param


##################
# TEST WITH DATA #
##################


def set_up_cost_data_param():
    filepath = resource_filename('modesto', 'Data/Investment/Storage.xlsx')
    df = utils.read_xlsx_data(filepath, use_sheet='Pit')
    param = SeriesParameter('cost', 'cost in function of volume', 'EUR', 'm3', val=df['Cost'])

    return param


def test_cost_data_interp():
    param = set_up_cost_data_param()
    assert param.v(25000) == 1231250


def test_cost_data_extrap():
    param = set_up_cost_data_param()
    assert param.v(220000) == 5900000

def test_fixed_cost():
    param = SeriesParameter('cost', 'cost in function of volume', 'EUR', 'm3', val=10)
    assert param.v(1000) == 10000