from casadi import *
from modesto.component import BuildingFixed, ProducerVariable, Substation
from modesto.pipe import SimplePipe, FiniteVolumePipe
import pandas as pd
import modesto.utils as ut
from pkg_resources import resource_filename
import matplotlib.pyplot as plt

start_time = pd.Timestamp('20140101')
horizon = 3*24*3600
time_step = 3600

heat_profile = ut.read_time_data(resource_filename(
    'modesto', 'Data/HeatDemand/Old'), name='HeatDemandFiltered.csv')

c_f = ut.read_time_data(path=resource_filename('modesto', 'Data/ElectricityPrices'),
                        name='DAM_electricity_prices-2014_BE.csv')['price_BE']

"""

Test separate components 

"""

def test_fixed_profile_not_temp_driven():
    opti = Opti()
    building_params = {'delta_T': 20,
                       'mult': 500,
                       'heat_profile': heat_profile['ZwartbergNEast'],
                       'time_step': time_step,
                       'horizon': horizon}

    building = BuildingFixed('building', temperature_driven=False)

    for param in building_params:
        building.change_param(param, building_params[param])

    building.compile(opti, start_time)


def test_fixed_profile_temp_driven():
    opti = Opti()
    building_params = {'delta_T': 20,
                       'mult': 500,
                       'heat_profile': heat_profile['ZwartbergNEast'],
                       'temperature_return': 323.15,
                       'temperature_supply': 303.15,
                       'temperature_max': 363.15,
                       'temperature_min': 283.15,
                       'time_step': time_step,
                       'horizon': horizon}

    building = BuildingFixed('building', temperature_driven=True)

    for param in building_params:
        building.change_param(param, building_params[param])

    building.compile(opti, start_time)

    opti.minimize(sum2(building.opti_vars['temperatures'][0, :]) + 1e5*(
                  sum1(building.get_slack('temperature_max_slack')) +
                  sum1(building.get_slack('temperature_min_slack')))
                  )

    options = {'ipopt': {'print_level': 0}}
    opti.solver('ipopt', options)
    building.set_parameters()
    sol=opti.solve()
    temps = sol.value(building.opti_vars['temperatures'])

    flag = True

    for t in building.TIME[1:]:
        if not (abs(temps[0, t] - 283.15) <= 0.001 and abs(temps[1, t] - 263.15) <= 0.001):
            flag = False

    assert flag, 'The solution of the optimization problem is not correct'


def test_producer_variable_not_temp_driven():
    opti = Opti()
    plant = ProducerVariable('plant', False)

    prod_params = {'delta_T': 20,
                   'efficiency': 0.95,
                   'PEF': 1,
                   'CO2': 0.178,  # based on HHV of CH4 (kg/KWh CH4)
                   'fuel_cost': c_f,
                   # http://ec.europa.eu/eurostat/statistics-explained/index.php/Energy_price_statistics (euro/kWh CH4)
                   'Qmax': 1.5e8,
                   'ramp_cost': 0,
                   'ramp': 2e8,
                   'horizon': horizon,
                   'time_step': time_step}

    for param in prod_params:
        plant.change_param(param, prod_params[param])

    plant.compile(opti, start_time)

    opti.subject_to(plant.get_var('mass_flow_tot') >= 1)

    opti.minimize(plant.obj_energy())

    options = {'ipopt': {'print_level': 0}}
    opti.solver('ipopt', options)
    plant.set_parameters()
    sol=opti.solve()
    # temps = sol.value(plant.opti_vars['temperatures'])
    hf = sol.value(plant.opti_vars['heat_flow_tot'])
    mf = sol.value(plant.opti_vars['mass_flow_tot'])

    flag = True

    for t in plant.TIME[1:]:
        if not (abs(hf[t] - 83599.9991) <= 0.001 and abs(mf[t] - 1) <= 0.001):
            flag = False

    assert flag, 'The solution of the optimization problem is not correct'


def test_producer_variable_temp_driven():
    opti = Opti()
    plant = ProducerVariable('plant', True)

    prod_params = {'efficiency': 3.5,
                   'PEF': 1,
                   'CO2': 0.178,  # based on HHV of CH4 (kg/KWh CH4)
                   'fuel_cost': c_f,
                   'Qmax': 2e6,
                   'temperature_supply': 323.15,
                   'temperature_return': 303.15,
                   'temperature_max': 363.15,
                   'temperature_min': 323.15,
                   'ramp': 1e6 / 3600,
                   'ramp_cost': 0.01,
                   'mass_flow': pd.Series(1, index=heat_profile['ZwartbergNEast'].index),
                   'horizon': horizon,
                   'time_step': time_step}

    for param in prod_params:
        plant.change_param(param, prod_params[param])

    plant.compile(opti, start_time)

    opti.minimize(plant.obj_energy())

    options = {'ipopt': {'print_level': 0}}
    opti.solver('ipopt', options)
    plant.set_parameters()
    sol = opti.solve()
    temps = sol.value(plant.opti_vars['temperatures'])
    hf = sol.value(plant.opti_vars['heat_flow_tot'])

    flag = True

    for t in plant.TIME[1:]:
        if not (abs(hf[t] - 0) <= 0.001 and abs(temps[1, t] - 343.15) <= 0.001 and abs(temps[0, t] - 343.15) <= 0.001):
            flag = False

    assert flag, 'The solution of the optimization problem is not correct'


def test_simple_pipe():
    opti = Opti()
    pipe = SimplePipe('pipe', 'start_node', 'end_node', 5)

    pipe_params = {'diameter': 500,
                   'horizon': horizon,
                   'time_step': time_step}

    for param in pipe_params:
        pipe.change_param(param, pipe_params[param])

    pipe.compile(opti, start_time)
    opti.subject_to(pipe.get_var('heat_flow_in') == 1)
    opti.subject_to(pipe.get_var('mass_flow') == 1)
    opti.minimize(sum1(pipe.get_var('heat_flow_out')))

    options = {'ipopt': {'print_level': 0}}
    opti.solver('ipopt', options)
    pipe.set_parameters()
    sol = opti.solve()
    hf = sol.value(pipe.opti_vars['heat_flow_out'])
    mf = sol.value(pipe.opti_vars['mass_flow'])

    flag = True

    for t in pipe.TIME[1:]:
        if not (abs(hf[t] - 1) <= 0.001 and abs(mf[t] - 1) <= 0.001):
            flag = False

    assert flag, 'The solution of the optimization problem is not correct'


def test_substation():
    opti = Opti()
    ss = Substation('substation')

    ss_params = {
            'mult': 350,
            'heat_flow': heat_profile['ZwartbergNEast']/350,
            'temperature_radiator_in': 47 + 273.15,
            'temperature_radiator_out': 35 + 273.15,
            'temperature_supply_0': 60 + 273.15,
            'temperature_return_0': 40 + 273.15,
            'temperature_max': 70 + 273.15,
            'temperature_min': 40 + 273.15,
            'lines': ['supply', 'return'],
            'thermal_size_HEx': 15000,
            'exponential_HEx': 0.7,
            'horizon': horizon,
            'time_step': time_step}

    for param in ss_params:
        ss.change_param(param, ss_params[param])

    ss.compile(opti, start_time)

    # Limitations to keep DTlm solvable
    opti.subject_to(ss.get_var('Tpsup') >= ss_params['temperature_radiator_in'] + 1)
    opti.subject_to(ss.get_var('Tpret') >= ss_params['temperature_radiator_out'] + 1)
    opti.subject_to(ss.get_var('Tpsup') - ss_params['temperature_radiator_in'] >=
                    ss.get_var('Tpret') - ss_params['temperature_radiator_out'] + 0.1)

    # Limitations to keep mf_prim solvable
    opti.subject_to(ss.get_var('mf_prim') >= 0.01)
    opti.set_initial(ss.get_var('mf_prim'), 1)

    opti.minimize(sum1(ss.get_var('Tpret')))

    options = {'ipopt': {'print_level': 0}}
    opti.solver('ipopt', options)
    ss.set_parameters()
    try:
        sol = opti.solve()
    except:
        raise Exception('Optimization failed')
        # print(opti.debug.g_describe(6))
        # print(opti.debug.x_describe(0))
        # print(ss.opti_vars)

    hf = sol.value(ss.opti_params['heat_flow'])
    mf_sec = sol.value(ss.opti_params['mf_sec'])
    mf_prim = sol.value(ss.opti_vars['mf_prim'])
    Tpsup = sol.value(ss.opti_vars['Tpsup'])
    Tpret = sol.value(ss.opti_vars['Tpret'])
    DTlm = sol.value(ss.opti_vars['DTlm'])

    fig1, axarr1 = plt.subplots()
    axarr1.plot([ss_params['thermal_size_HEx'] / (mf_prim[t]**-0.7 + mf_sec[t]**-0.7) for t in ss.TIME]) # TODO ))

    fig, axarr = plt.subplots(4, 1)
    axarr[0].plot(hf)
    axarr[0].set_title('Heat flow')
    axarr[1].plot(mf_prim, label='Primary')
    axarr[1].plot(mf_sec, label='Secondary')
    axarr[1].set_title('Mass flow')
    axarr[1].legend()
    axarr[2].plot(Tpsup, label='Primary, supply')
    axarr[2].plot(Tpret, label='Primary, return')
    axarr[2].legend()
    axarr[2].set_title('Temperatures')
    axarr[3].plot(DTlm, label='$DT_{lm}$')
    axarr[3].plot(Tpsup - ss_params['temperature_radiator_in'], label='DTa')
    axarr[3].plot(Tpret - ss_params['temperature_radiator_out'], label='DTb')
    axarr[3].legend()
    axarr[3].set_title('Temperature differences')

    plt.show()


def test_finite_volume_pipe():
    time_step = 20
    horizon = 0.5*3600
    opti = Opti()
    pipe = FiniteVolumePipe('pipe', 'start_node', 'end_node', 200)

    pipe_params = {'diameter': 20,
                   'max_speed': 3,
                   'Courant': 1,
                   'Tg': pd.Series(12 + 273.15, index=heat_profile['ZwartbergNEast'].index),
                   'horizon': horizon,
                   'time_step': time_step
                   }
    for param in pipe_params:
        pipe.change_param(param, pipe_params[param])

    import random

    pipe.compile(opti, start_time)

    # Possible imput profiles
    step_up = [50+273.15] * int(pipe.n_steps / 2) + [70+273.15] * (pipe.n_steps - int(pipe.n_steps / 2))
    random_prof = [random.random()*50 + 20+273.15 for i in range(pipe.n_steps)]
    step_mf = [1] * int(pipe.n_steps / 2) + [2] * (pipe.n_steps - int(pipe.n_steps / 2))

    # Extra constraints
    opti.subject_to(pipe.get_var('Tsup_in') == step_up)
    opti.subject_to((pipe.get_var('Tsup_out')[1:] - pipe.get_var('Tret_in')[1:]) == 4000/pipe.get_var('mass_flow')[1:])
    opti.subject_to(pipe.get_var('Tsup_out')[1:]/pipe.get_var('Tret_in')[1:] == 1.116)
    opti.subject_to(pipe.get_var('Tret_in')[1:] >= 0)
    opti.set_initial(pipe.get_var('Tret_in'), 30+273.15)
    # opti.subject_to(pipe.get_var('mass_flow') == step_mf)

    # Objective
    opti.minimize(sum1(pipe.get_var('Tsup_in')))

    # Initial guess
    opti.set_initial(pipe.get_var('mass_flow'), 1)

    options = {'ipopt': {'print_level': 0}}
    opti.solver('ipopt')
    pipe.set_parameters()
    try:
        sol = opti.solve()
    except:
        print(opti.debug.g_describe(1702))
        print(opti.debug.x_describe(0))
        raise Exception('Optimization failed')
    for name, var in pipe.opti_vars.items():
        print('\npipe', name, '\n------------------\n')
        print(opti.debug.value(var))
    Tso = sol.value(pipe.opti_vars['Tsup_out'])-273.15
    Tro = sol.value(pipe.opti_vars['Tret_out'])-273.15
    Ts = sol.value(pipe.opti_vars['Tsup'])-273.15
    Tr = sol.value(pipe.opti_vars['Tret'])-273.15
    Qls = sol.value(pipe.opti_vars['Qloss_sup'])
    Qlr = sol.value(pipe.opti_vars['Qloss_ret'])
    mf = sol.value(pipe.opti_vars['mass_flow'])

    flag = True

    fig, axarr = plt.subplots(2, 1)
    axarr[0].plot(Tso)
    axarr[0].plot(Tro)
    axarr[1].plot(mf)
    fig1, axarr = plt.subplots(2, 1)
    for i in range(Ts.shape[0]):
        axarr[0].plot(Ts[i, :], label=i)
        axarr[1].plot(Tr[i, :], label=i,)
    axarr[0].legend()
    fig1, axarr = plt.subplots(2, 1)
    for i in range(Ts.shape[0]):
        axarr[0].plot(Qls[i, :], label=i)
        axarr[1].plot(Qlr[i, :], label=i)
    axarr[0].legend()

    plt.show()

    # TODO Set up assert
    assert flag, 'The solution of the optimization problem is not correct'


def test_pipe_and_substation():
    time_step = 20
    horizon = 5 * 3600
    opti = Opti()

    """
    Pipe
    """
    pipe = FiniteVolumePipe('pipe', 'start_node', 'end_node', 200)

    pipe_params = {'diameter': 200,
                   'max_speed': 3,
                   'Courant': 1,
                   'Tg': pd.Series(12 + 273.15, index=heat_profile['ZwartbergNEast'].index),
                   'horizon': horizon,
                   'time_step': time_step
                   }
    for param in pipe_params:
        pipe.change_param(param, pipe_params[param])

    pipe.compile(opti, start_time)


    """
    Substation    
    """

    ss = Substation('substation')

    ss_params = {
        'mult': 350,
        'heat_flow': heat_profile['ZwartbergNEast'] / 350,
        'temperature_radiator_in': 47 + 273.15,
        'temperature_radiator_out': 35 + 273.15,
        'temperature_supply_0': 60 + 273.15,
        'temperature_return_0': 40 + 273.15,
        'temperature_max': 70 + 273.15,
        'temperature_min': 40 + 273.15,
        'lines': ['supply', 'return'],
        'thermal_size_HEx': 15000,
        'exponential_HEx': 0.7,
        'horizon': horizon,
        'time_step': time_step}

    for param in ss_params:
        ss.change_param(param, ss_params[param])

    ss.compile(opti, start_time)

    """
    Other constraints
    """

    step_mf = [5] * int(pipe.n_steps / 2) + [12] * (pipe.n_steps - int(pipe.n_steps / 2))
    # opti.subject_to(pipe.get_var('mass_flow') == step_mf)

    opti.subject_to(pipe.get_var('mass_flow') == ss.get_var('mf_prim')*350)
    opti.subject_to(pipe.get_var('Tsup_out') == ss.get_var('Tpsup'))
    opti.subject_to(pipe.get_var('Tret_in') == ss.get_var('Tpret'))

    opti.subject_to(pipe.get_var('Tsup_in') <= 80+273.15)
    opti.subject_to(pipe.get_var('Tsup_in') >= 47+273.15 + 5)
    opti.subject_to(pipe.get_var('mass_flow') >= 1)
    opti.subject_to(pipe.get_var('Tret_out') >= 35+273.15)

    opti.set_initial(pipe.get_var('mass_flow'), 1)

    # opti.set_initial(pipe.get_var('mass_flow'), 350)
    # opti.set_initial(pipe.get_var('Tsup_in'), 55+273.15)
    # opti.set_initial(pipe.get_var('Tret_out'), 35+273.15)

    # opti.subject_to(pipe.get_var('Tret_in') == 50+273.15)
    # opti.subject_to(pipe.get_var('Tsup_in') == 50+273.15)
    # opti.subject_to(pipe.get_var('Tsup_out') - pipe.get_var('Tret_in') == 20)


    """
    Objective
    """

    opti.minimize(sum1(pipe.get_var('Tret_out'))) #

    options = {'ipopt': {'print_level': 0}}
    opti.solver('ipopt')
    pipe.set_parameters()
    ss.set_parameters()
    try:
        sol = opti.solve()
    except:
        # print(opti.debug.g_describe(2064))
        # print(opti.debug.x_describe(0))
        pass
    for name, var in pipe.opti_vars.items():
        print('\npipe', name, '\n------------------\n')
        print(opti.debug.value(var))
    for name, var in ss.opti_vars.items():
        print('\nsubstation', name, '\n----------------------\n')
        print(opti.debug.value(var))
    Tsi = sol.value(pipe.opti_vars['Tsup_in']) - 273.15
    Tri = sol.value(pipe.opti_vars['Tret_in']) - 273.15
    Tso = sol.value(pipe.opti_vars['Tsup_out']) - 273.15
    Tro = sol.value(pipe.opti_vars['Tret_out']) - 273.15
    Ts = sol.value(pipe.opti_vars['Tsup']) - 273.15
    Tr = sol.value(pipe.opti_vars['Tret']) - 273.15
    Qls = sol.value(pipe.opti_vars['Qloss_sup'])
    Qlr = sol.value(pipe.opti_vars['Qloss_ret'])
    mf = sol.value(pipe.opti_vars['mass_flow'])

    flag = True

    fig, axarr = plt.subplots(2, 1)
    axarr[0].plot(Tsi, label='in, supply', color ='r')
    axarr[0].plot(Tso, label='out, supply', color='b')
    axarr[0].plot(Tri, label='in, return', color='r', linestyle=':')
    axarr[0].plot(Tro, label='out, return', color='b', linestyle=':')
    axarr[0].plot(Tro, label='in')
    axarr[1].plot(mf)
    axarr[0].set_title('In- and Outgoing temperatures pipes')
    axarr[0].legend()
    axarr[1].set_title('Mass flow rate pipes')
    fig1, axarr = plt.subplots(2, 1)
    for i in range(Ts.shape[0]):
        axarr[0].plot(Ts[i, :], label=i)
        axarr[1].plot(Tr[i, :], label=i, )
    axarr[0].legend()
    axarr[0].set_title('Pipe volumes supply temperatures')
    axarr[1].set_title('Pipe volumes return temperatures')
    fig1, axarr = plt.subplots(2, 1)
    for i in range(Ts.shape[0]):
        axarr[0].plot(Qls[i, :], label=i)
        axarr[1].plot(Qlr[i, :], label=i)
    axarr[0].legend()
    axarr[0].set_title('Pipe volumes supply heat losses')
    axarr[1].set_title('Pipe volumes return heat losses')

    plt.show()

    assert flag, 'The solution of the optimization problem is not correct'
    # flag = True
    #
    # for t in pipe.TIME[1:]:
    #     if not (abs(hf[t] - 1) <= 0.001 and abs(mf[t] - 1) <= 0.001):
    #         flag = False
    #
    # assert flag, 'The solution of the optimization problem is not correct'

if __name__ == '__main__':
    # test_fixed_profile_not_temp_driven()
    # test_fixed_profile_temp_driven()
    # test_producer_variable_not_temp_driven()
    # test_producer_variable_temp_driven()
    # test_simple_pipe()
    # test_substation()
    # test_finite_volume_pipe()
    test_pipe_and_substation()

