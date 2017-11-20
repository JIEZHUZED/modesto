import logging

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import pandas as pd
from pyomo.core.base import value
import pyomo.environ

from modesto.main import Modesto

logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s %(name)-36s %(levelname)-8s %(message)s',
                    datefmt='%m-%d %H:%M')
logger = logging.getLogger('Main.py')


###########################
# Set up Graph of network #
###########################

def construct_model():
    G = nx.DiGraph()

    G.add_node('ThorPark', x=4000, y=4000, z=0,
               comps={'thorPark': 'ProducerVariable'})
    G.add_node('p1', x=2600, y=5000, z=0,
               comps={})
    G.add_node('waterscheiGarden', x=2500, y=4600, z=0,
               comps={'waterscheiGarden.buildingD': 'BuildingFixed',
                      # 'waterscheiGarden.storage': 'StorageVariable'
                      }
               )
    G.add_node('zwartbergNE', x=2000, y=5500, z=0,
               comps={'zwartbergNE.buildingD': 'BuildingFixed'})

    G.add_edge('ThorPark', 'p1', name='bbThor')
    G.add_edge('p1', 'waterscheiGarden', name='spWaterschei')
    G.add_edge('p1', 'zwartbergNE', name='spZwartbergNE')

    # nx.draw(G, with_labels=True, font_weight='bold')
    # plt.show()

    ###################################
    # Set up the optimization problem #
    ###################################

    n_steps = 5
    time_steps = 3600

    optmodel = Modesto(n_steps * time_steps, time_steps, 'NodeMethod', G)

    ##################################
    # Fill in the parameters         #
    ##################################

    heat_profile = pd.DataFrame([1000] * n_steps, index=range(n_steps))
    mf_profile = pd.DataFrame([1000/4186/20] * n_steps, index=range(n_steps))
    mf_profile_prod = pd.DataFrame([1000*2020/4186/20] * n_steps, index=range(n_steps))
    t_amb = pd.DataFrame([20 + 273.15] * n_steps, index=range(n_steps))

    optmodel.opt_settings(allow_flow_reversal=False)
    optmodel.change_general_param('Te', t_amb)

    optmodel.change_param('zwartbergNE.buildingD', 'delta_T', 20)
    optmodel.change_param('zwartbergNE.buildingD', 'mult', 2000)
    optmodel.change_param('zwartbergNE.buildingD', 'heat_profile', heat_profile)
    optmodel.change_param('zwartbergNE.buildingD', 'mass_flow', mf_profile)
    optmodel.change_param('waterscheiGarden.buildingD', 'delta_T', 20)
    optmodel.change_param('waterscheiGarden.buildingD', 'mult', 20)
    optmodel.change_param('waterscheiGarden.buildingD', 'heat_profile', heat_profile)
    optmodel.change_param('waterscheiGarden.buildingD', 'mass_flow', mf_profile)

    optmodel.change_param('bbThor', 'pipe_type', 150)
    optmodel.change_param('bbThor', 'mass_flow', mf_profile_prod)
    optmodel.change_param('spWaterschei', 'pipe_type', 200)
    optmodel.change_param('spWaterschei', 'mass_flow', mf_profile)
    optmodel.change_param('spZwartbergNE', 'pipe_type', 125)
    optmodel.change_param('spZwartbergNE', 'mass_flow', mf_profile)

    # stor_design = {  # Thi and Tlo need to be compatible with delta_T of previous
    #     'Thi': 80 + 273.15,
    #     'Tlo': 60 + 273.15,
    #     'mflo_max': 110,
    #     'volume': 10,
    #     'ar': 1,
    #     'dIns': 0.3,
    #     'kIns': 0.024
    # }
    #
    # for i in stor_design:
    #     optmodel.change_param('waterscheiGarden.storage', i, stor_design[i])
    #
    # optmodel.change_init_type('waterscheiGarden.storage', 'heat_stor', 'fixedVal')
    # optmodel.change_state_bounds('waterscheiGarden.storage', 'heat_stor', 50, 0, False)
    # optmodel.change_param('waterscheiGarden.storage', 'heat_stor', 0)
    # optmodel.change_param('waterscheiGarden.storage', 'mass_flow', mf_profile)

    prod_design = {'efficiency': 0.95,
                   'PEF': 1,
                   'CO2': 0.178,  # based on HHV of CH4 (kg/KWh CH4)
                   'fuel_cost': 0.034,
                   # http://ec.europa.eu/eurostat/statistics-explained/index.php/Energy_price_statistics (euro/kWh CH4)
                   'Qmax': 10e6}

    optmodel.change_param('thorPark', 'mass_flow', mf_profile)

    for i in prod_design:
        optmodel.change_param('thorPark', i, prod_design[i])

    ##################################
    # Print parameters               #
    ##################################

    # optmodel.print_all_params()
    # optmodel.print_general_param('Te')
    # optmodel.print_comp_param('thorPark')
    # optmodel.print_comp_param('waterscheiGarden.storage')
    # optmodel.print_comp_param('waterscheiGarden.storage', 'kIns', 'volume')

    return optmodel

##################################
# Solve                          #
##################################

if __name__ == '__main__':
    optmodel = construct_model()
    optmodel.compile()
    optmodel.set_objective('energy')

    optmodel.model.OBJ_ENERGY.pprint()
    optmodel.model.OBJ_COST.pprint()
    optmodel.model.OBJ_CO2.pprint()

    optmodel.solve(tee=True, mipgap=0.01)

    ##################################
    # Collect result                 #
    ##################################

    print '\nWaterschei.buildingD'
    print 'Heat flow', optmodel.get_result('waterscheiGarden.buildingD', 'heat_flow')

    print '\nzwartbergNE.buildingD'
    print 'Heat flow', optmodel.get_result('zwartbergNE.buildingD', 'heat_flow')

    print '\nthorPark'
    print 'Heat flow', optmodel.get_result('thorPark', 'heat_flow')

    # print '\nStorage'
    # print 'Heat flow', optmodel.get_result('waterscheiGarden.storage', 'heat_flow')
    # print 'Mass flow', optmodel.get_result('waterscheiGarden.storage', 'mass_flow')
    # print 'Energy', optmodel.get_result('waterscheiGarden.storage', 'heat_stor')

    # -- Efficiency calculation --

    # Heat flows
    prod_hf = optmodel.get_result('thorPark', 'heat_flow')
    # storage_hf = optmodel.get_result('waterscheiGarden.storage', 'heat_flow')
    waterschei_hf = optmodel.get_result('waterscheiGarden.buildingD', 'heat_flow')
    zwartberg_hf = optmodel.get_result('zwartbergNE.buildingD', 'heat_flow')

    # storage_soc = optmodel.get_result('waterscheiGarden.storage', 'heat_stor')

    # Sum of heat flows
    prod_e = sum(prod_hf)
    # storage_e = sum(storage_hf)
    waterschei_e = sum(waterschei_hf)
    zwartberg_e = sum(zwartberg_hf)

    # Efficiency
    print '\nNetwork'
    print 'Efficiency', (waterschei_e + zwartberg_e) / prod_e * 100, '%'  #

    # Diameters
    # print '\nDiameters'
    # for i in ['bbThor', 'spWaterschei', 'spZwartbergNE']:  # ,
    #     print i, ': ', str(optmodel.components[i].get_diameter())

    # Pipe heat losses
    print '\nPipe heat losses'
    # print 'bbThor: ', optmodel.get_result('bbThor', 'heat_loss_tot')
    # print 'spWaterschei: ', optmodel.get_result('spWaterschei', 'heat_loss_tot')
    # print 'spZwartbergNE: ', optmodel.get_result('spZwartbergNE', 'heat_loss_tot')

    # Mass flows
    print '\nMass flows'
    print 'bbThor: ', optmodel.get_result('bbThor', 'mass_flow_tot')
    print 'spWaterschei: ', optmodel.get_result('spWaterschei', 'mass_flow_tot')
    print 'spZwartbergNE: ', optmodel.get_result('spZwartbergNE', 'mass_flow_tot')

    # Objectives
    print '\nObjective function'
    print 'Energy:', optmodel.get_objective('energy')
    print 'Cost:  ', optmodel.get_objective('cost')
    print 'Active:', optmodel.get_objective()

    fig, ax = plt.subplots()

    ax.hold(True)
    l1, = ax.plot(prod_hf)
    l3, = ax.plot([x + y + z for x, y, z in zip(waterschei_hf, storage_hf, zwartberg_hf, )])  # , )])  #
    ax.axhline(y=0, linewidth=2, color='k', linestyle='--')

    ax.set_title('Heat flows [W]')

    fig.legend((l1, l3),
               ('Producer',
                'Users and storage'),
               'lower center', ncol=3)
    fig.tight_layout()

    fig2 = plt.figure()

    # ax2 = fig2.add_subplot(111)
    # ax2.plot(storage_soc, label='Stored heat')
    # ax2.plot(np.asarray(storage_hf) * 3600, label="Charged heat")
    # ax2.axhline(y=0, linewidth=2, color='k', linestyle='--')
    # ax2.legend()
    # fig2.suptitle('Storage')
    # fig2.tight_layout()

    fig3 = plt.figure()

    ax3 = fig3.add_subplot(111)
    ax3.plot(waterschei_hf, label='Waterschei')
    ax3.plot(zwartberg_hf, label="Zwartberg")
    # ax3.plot(storage_hf, label='Storage')
    ax3.axhline(y=0, linewidth=1.5, color='k', linestyle='--')
    ax3.legend()
    ax3.set_ylabel('Heat Flow [W]')
    fig3.tight_layout()

    plt.show()
