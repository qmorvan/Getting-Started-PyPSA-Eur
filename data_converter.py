#---
# PyPSA to Matpower like data converter program
#---
"""
This program is based on the Matpower file-structure, even though it differs a little bit (cf. https://matpower.org/docs/ref/matpower5.0/caseformat.html)

Input:
 - .nc file (PyPSA network)

Output:
 - bus_data.csv
    By column: 
     - bus -> bus id
     - type -> 1 PQ bus / 2 PV bus / 3 reference bus, i.e. theta-V / 4 isolated bus
     - Pd -> active power demand (MW)
     - Qd -> reactive power demand (MVAR)
     - Gs -> shunt conductance (MW demanded @ V = 1 pu)
     - Bs -> shunt susceptance (MWAR demanded @ V = 1 pu)
     - area -> area number (>= 1)
     - Vm -> nominal voltage magnitude (pu)
     - Va -> nominal voltage angle (deg)
     - baseKV -> base voltage (kV)
     - zone -> zone 
     - Vmax -> maximum voltage magnitude
     - Vmin -> minimum voltage magnitude
 - generator_data.csv
    By column:
     - bus -> bus id
     - Pg -> current active power output (MW)
     - Qg -> current reactive power output (MVAR)
     - Qmax -> maximum reactive power output (MVAR)
     - Qmin -> minimum reactibve power output (MVAR)
     - Vg -> voltage magnitude setpoint (pu)
     - mBase -> MVA base of the machine (defeault to baseMVA)
     - status -> active (> 0) or inactive (<= 0), or more sofisticated (but respecting > / <= 0)
     - Pmax -> maximum active power output (MW)
     - Pmin -> minimum active power output (MW)
     + Pc1 -> lower real power output of PQ capability curve (MW)
     + Pc2 -> upper real power output of PQ capability curve (MW)
     + Qc1min -> minimum reactive power output at Pc1 (MVAr)
     + Qc1max -> maximum reactive power output at Pc1 (MVAr)
     + Qc2min -> minimum reactive power output at Pc2 (MVAr)
     + Qc2max -> maximum reactive power output at Pc2 (MVAr)
     + Rfollow -> ramp rate for load following/AGC (MW/min)
     + R10 -> ramp rate for 10 minute reserves (MW)
     + R30 -> ramp rate for 30 minute reserves (MW)
     + Rreact -> ramp rate for reactive power (2 sec timescale) (MVAr/min)
     + apf, area participation factor (distributes the area control error (ACE), i.e. how much to contribute for correcting frequency deviations, tie-line power flow errors, etc.
                                       APF is used in AGC to determine how to react to disturbances.)
 - line_data.csv
    By column:
     - fbus -> from bus id
     - tbus -> to bus id
     - r -> resistance (pu)
     - x -> reactance (pu)
     - b -> susceptance (pu)
     - rateA -> long term rating A (MVA)
     - rateB -> short term rating B (MVA)
     - rateC -> emergency rating C (MVA)
     - ratio -> transformer off nominal turn ratio (/!\\ 0 for lines)
     - angle -> transformer phase shift angle (/!\\ 0 for lines)
     - status -> active (1) or inactive (0)
     - angmin -> minimum angle difference (deg) -> angles are defined as Vfrom - Vto
     - angmax -> maximum angle difference (deg)
 - cost_data.csv
    By column:
     - model -> wether it's piecewise linear (1) or polynomial (2)
     - startup -> startup cost
     - shutdown -> shutdown cost
     - n -> number of levels (piecewise) or coefficients (polynomial)
     ~ corresponding number of columns for describing the model.
        -> piecewise: p0; f0; p1; f1; etc. (from low-generation to high generation)
        -> polynomial: cn+1; cn; ... ; c0

/!\\ coefficients c2; c1; c0 of a polynomial cost function may be integrated within the generator_data.csv file as additional columns,
for the sake of simplicity and compatibility.
"""

#-_-_-_-_-_
# input information:
input_path = "C:\\Users\\Quentin\\OneDrive - INSA Lyon\\Madrid\\Files\\PyPSA-database\\pypsa_data\\pypsa_eur\\spain_low.nc"   # to the .nc file
output_folder = "C:\\Users\\Quentin\\Desktop"
# output_folder = "C:\\Users\\Quentin\\OneDrive - INSA Lyon\\Madrid\\Files\\PyPSA-database\\tempo\\test_results"    # to the folder where tp place the results

baseMVA = 100    #MVAR
baseV = 380    #kV    /!\ if all lines do not share the same voltage level, then the bus_data section should be modified

create_cost_data_file = False    # whether to create the cost_data.csv file or to add c2, c1 and c0 to the generator_data.csv file

net_demand = False    # whether to compute net demand and remove renewables from the powerplants (True) or to create generator_data{date_time}.csv files that include renewables' with their forcast capacities allowing more accurate computation of LMPs
maximum_line_angle = 30    #deg
rateB_over_A = 1.25    # multiplier to estimate rateB from rateA
rateC_over_A = 1.75    # multiplier to estimate rateC from rateA
#-_-_-_-_-_


#--- imports
import os    # file manager
import pandas as pd    # data handling and exports
import pypsa    # loading and manipulating the input data

#--- initialisation
case = os.path.splitext(os.path.basename(input_path))[0]    #name of the study case
output_path = output_folder + "/" + case

if not os.path.exists(output_path):    # checks whether the output folder already exists
    os.makedirs(output_path)
    print(f"Directory succesfully created at {output_path}")
else:
    print(f"Existing directory at {output_path} ; Continuing anyways.")
if not os.path.exists(output_path + "/series"):    # checks whether the output folder/series already exists (for series bus_data.csv files)
    os.makedirs(output_path + "/series")

n = pypsa.Network(input_path)    # loading the PyPSA network
n.calculate_dependent_values()    # some network related values require to be computed
baseZ = pow(baseV, 2) / baseMVA    # base impedance

# looking for isolated buses
sub_networks = {}    
for bus in n.buses.index:
    if bus[2] not in sub_networks.keys():    # PyPSA buses are built as follows: 'ES1 11' -> one can read it as the 11 bus from the 1 subnetwork (it starts at 0)
        sub_networks[bus[2]] = []
    sub_networks[bus[2]].append(bus)
size_record = -1
sub_network_record = ""
for sub_network, buses in sub_networks.items():    # we only keep the bigger subnetwork
    if len(buses) > size_record:
        sub_network_record = sub_network
        size_record = len(buses)
buses = sub_networks[sub_network_record]    # only one interconnected group of buses is kept
print(f"Number of isolated buses: {len(n.buses.index) - size_record}. If any, they won't be considered.")

    # bus map since bus id are required as int
bus_map = dict()
for i in range(len(buses)):
    bus_map[buses[i]] = i + 1

#--- bus
bus_data = pd.DataFrame(columns=['bus', 'type', 'Pd', 'Qd', 'Gs', 'Bs', 'area', 'Vm', 'Va', 'baseKV', 'zone', 'Vmax', 'Vmin'])    # create a dataframe for storing all the parameters
bus_data = bus_data.set_index("bus")

# type
type_dict = {"PQ":1, "PV":2, "Slack":3}    # plus island:4
for bus in buses:
    bus_data.loc[bus_map[bus], "type"] = type_dict[n.buses.loc[bus, "control"]]    # type
if len(bus_data.query("type == 3").type) > 1:
    print("More than one slack bus detected, only one will be kept. (other converted to 'PQ')")
    bus_data.loc[bus_data.query("type == 3").type.iloc[1:].index, "type"] = 1
elif len(bus_data.query("type == 3").type) != 1:
    print("ERROR - no slack bus found.")

# default values for every buses:
bus_data.loc[:, "Gs"] = 0
bus_data.loc[:, "Bs"] = 0
bus_data.loc[:, "area"] = 1
bus_data.loc[:, "Vm"] = 1    #/!\ if all lines do share the same voltage level = baseV
bus_data.loc[:, "Va"] = 0
bus_data.loc[:, "baseKV"] = baseV
bus_data.loc[:, "zone"] = 1
bus_data.loc[:, "Vmax"] = 1.1    #/!\ if all lines do share the same voltage level = baseV
bus_data.loc[:, "Vmin"] = 0.9    #/!\ if all lines do share the same voltage level = baseV

# Pd, Qd and saving to csv.    /!\ here we compute the net power demand, subtracting all renewables generation. It has no big implications since they would certainly be dispatch by the DCOPF algo, appart from falsing all LMPs :(
for date_time in n.snapshots:
    bus_data_temp = bus_data.copy()
    if len(n.loads_t["q"].columns) == len(n.snapshots):
        if net_demand:
            for bus in buses:
                bus_data_temp.loc[bus_map[bus], "Qd"] = n.loads_t["q_set"].loc[date_time, bus] - n.generators_t["q"].loc[date_time, n.generators.query(f"carrier in ['ror', 'solar-hsat', 'solar', 'onwind', 'offwind-ac', 'offwind-dc', 'offwind-float'] and bus == '{bus}'").index].sum()
        else:
            for bus in buses:
                bus_data_temp.loc[bus_map[bus], "Qd"] = n.loads_t["q_set"].loc[date_time, bus]
    else:
        bus_data_temp.loc[:, "Qd"] = 0
    if net_demand:
        for bus in buses:   
            bus_data_temp.loc[bus_map[bus], "Pd"] = n.loads_t["p_set"].loc[date_time, bus] - n.generators_t["p"].loc[date_time, n.generators.query(f"carrier in ['ror', 'solar-hsat', 'solar', 'onwind', 'offwind-ac', 'offwind-dc', 'offwind-float'] and bus == '{bus}'").index].sum()
    else:
        for bus in buses:   
            bus_data_temp.loc[bus_map[bus], "Pd"] = n.loads_t["p_set"].loc[date_time, bus]
    bus_data_temp.to_csv(output_path + "/series/bus_data_" + str(date_time)[:10] + "_" + str(date_time)[11:13] + ".csv", sep=";")

# generators
generator_data = pd.DataFrame(columns=['genID', 'bus', 'Pg', 'Qg', 'Qmax', 'Qmin', 'Vg', 'mBase', 'status', 'Pmax', 'Pmin', 'Pc1', 'Pc2', 'Qc1min', 'Qc1max', 'Qc2min', 'Qc2max', 'Rfollow', 'R10', 'R30', 'Rreact', 'apf'])
generator_data = generator_data.set_index('genID')
    #/!\ in the end there should not be the gen id in the file, to be removed when exporting to .csv

dic_true_to_1 = {True:1, False:0}    # n.generators.active is True or False, while status requires 1 or 0 respectively. This way we can convert the two basis easily
    #conventional generators

for gen in n.generators.query(f"carrier in ['CCGT', 'oil', 'lignite', 'coal', 'nuclear', 'biomass'] and bus in {buses}").index:    # only keeping conventional generators.
    generator_data.loc[gen, "bus"] = bus_map[n.generators.loc[gen, "bus"]]
    generator_data.loc[gen, "Pg"] = n.generators.loc[gen, "p_set"]
    generator_data.loc[gen, "Qg"] = n.generators.loc[gen, "q_set"]
    generator_data.loc[gen, "Pmax"] = n.generators.loc[gen, "p_nom"] * n.generators.loc[gen, "p_max_pu"]
    generator_data.loc[gen, "Pmin"] = n.generators.loc[gen, "p_nom"] * n.generators.loc[gen, "p_min_pu"]
    generator_data.loc[gen, "status"] = dic_true_to_1[n.generators.loc[gen, "active"]]    # converts true to 1 and False to 0
    if not create_cost_data_file:    # in case one wants to not use cost_data.csv file and store everything into the generator's one
        generator_data.loc[gen, "c2"] = n.generators.loc[gen, "marginal_cost_quadratic"]
        generator_data.loc[gen, "c1"] = n.generators.loc[gen, "marginal_cost"]
    #hydro
for gen in n.storage_units.query(f"carrier in ['hydro'] and bus in {buses}").index:    # very similar to the conventional generators one but with hydro.    /!\ It not perfect since hydro has limited capacities and has a wheather and time dependent refill but it is ok for single period optimization.
    generator_data.loc[gen, "bus"] = bus_map[n.storage_units.loc[gen, "bus"]]
    generator_data.loc[gen, "Pg"] = n.storage_units.loc[gen, "p_set"]
    generator_data.loc[gen, "Qg"] = n.storage_units.loc[gen, "q_set"]
    generator_data.loc[gen, "Pmax"] = n.storage_units.loc[gen, "p_nom"] * n.storage_units.loc[gen, "p_max_pu"]
    generator_data.loc[gen, "Pmin"] = n.storage_units.loc[gen, "p_nom"] * n.storage_units.loc[gen, "p_min_pu"]
    generator_data.loc[gen, "status"] = dic_true_to_1[n.storage_units.loc[gen, "active"]]    # converts true to 1 and false to 0
    if not create_cost_data_file:
        generator_data.loc[gen, "c2"] = n.storage_units.loc[gen, "marginal_cost_quadratic"]
        generator_data.loc[gen, "c1"] = n.storage_units.loc[gen, "marginal_cost"]

if net_demand:
    # default values for every generator:
    generator_data.loc[:, "Qmax"] = generator_data.loc[:, "Pmax"]    # UNKNOWN - we set reactive power limits based on the active ones.
    generator_data.loc[:, "Qmin"] = - generator_data.loc[:, "Pmax"]
    generator_data.loc[:, "Vg"] = 1    #/!\ if all lines do share the same voltage level = baseV, otherwise check the voltage level of the bus
    generator_data.loc[:, "mBase"] = baseMVA    # we use the same base reference for apparent power as the global one
    if not create_cost_data_file:
        generator_data.loc[:, "c0"] = 0
    generator_data.to_csv(output_path + '/generator_data.csv', sep=";", index=False)    # be carefull not to save the index
else:    # including all renewables as dispatchable powerplants, thus having one .csv file per snapshot
    for date_time in n.snapshots:
        generator_data_temp = generator_data.copy()    # for having aversion per snapshot
        for gen in n.generators.query(f"carrier in ['ror', 'solar-hsat', 'solar', 'onwind', 'offwind-ac', 'offwind-dc', 'offwind-float'] and bus in {buses} and p_nom > 0").index:
            generator_data_temp.loc[gen, "bus"] = bus_map[n.generators.loc[gen, "bus"]]
            generator_data_temp.loc[gen, "Pg"] = n.generators.loc[gen, "p_set"]
            generator_data_temp.loc[gen, "Qg"] = n.generators.loc[gen, "q_set"]
            generator_data_temp.loc[gen, "Pmax"] = n.generators_t["p"].loc[date_time, gen]
            generator_data_temp.loc[gen, "Pmin"] = n.generators.loc[gen, "p_nom"] * n.generators.loc[gen, "p_min_pu"]
            generator_data_temp.loc[gen, "status"] = dic_true_to_1[n.generators.loc[gen, "active"]]
            if not create_cost_data_file:
                generator_data_temp.loc[gen, "c2"] = n.generators.loc[gen, "marginal_cost_quadratic"]
                generator_data_temp.loc[gen, "c1"] = n.generators.loc[gen, "marginal_cost"]
        # default values for every generator:
        generator_data_temp.loc[:, "Qmax"] = generator_data_temp.loc[:, "Pmax"]    # UNKNOWN - we set reactive power limits based on the active ones.
        generator_data_temp.loc[:, "Qmin"] = - generator_data_temp.loc[:, "Pmax"]
        generator_data_temp.loc[:, "Vg"] = 1    #/!\ if all lines do share the same voltage level = baseV, otherwise check the voltage level of the bus
        generator_data_temp.loc[:, "mBase"] = baseMVA    # we use the same base reference for apparent power as the global one
        if not create_cost_data_file:
            generator_data_temp.loc[:, "c0"] = 0
        generator_data_temp.to_csv(output_path + "/series/generator_data_" + str(date_time)[:10] + "_" + str(date_time)[11:13] + ".csv", sep=";", index=False)

# line
line_data = pd.DataFrame(columns=['lineID', 'fbus', 'tbus', 'r', 'x', 'b', 'rateA', 'rateB', 'rateC', 'ratio', 'angle', 'status', 'angmin', 'angmax'])
line_data = line_data.set_index('lineID')
    #/!\ in the end there should not be the gen id in the file, to be removed when exporting to .csv

for line in n.lines.query(f"bus0 in {buses}").index:
    line_data.loc[line, "fbus"] = bus_map[n.lines.loc[line, "bus0"]]
    line_data.loc[line, "tbus"] = bus_map[n.lines.loc[line, "bus1"]]
    line_data.loc[line, "r"] = n.lines.loc[line, "r"] / baseZ    # converting in pu
    line_data.loc[line, "x"] = n.lines.loc[line, "x"] / baseZ    # converting in pu
    line_data.loc[line, "b"] = n.lines.loc[line, "b"] * baseZ    # converting in pu
    line_data.loc[line, "rateA"] = n.lines.loc[line, "s_nom"]
    line_data.loc[line, "status"] = dic_true_to_1[n.lines.loc[line, "active"]]

    # default values for every generator:
line_data.loc[:, ["rateB"]] = line_data.loc[:, "rateA"] * rateB_over_A
line_data.loc[:, ["rateC"]] = line_data.loc[:, "rateA"] * rateC_over_A
line_data.loc[:, "ratio"] = 0
line_data.loc[:, "angle"] = 0
line_data.loc[:, "angmin"] = - maximum_line_angle
line_data.loc[:, "angmax"] = maximum_line_angle

line_data.to_csv(output_path + '/line_data.csv', sep=";", index=False)
