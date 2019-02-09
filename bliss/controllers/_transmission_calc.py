"""

Datafile example for tunable energy:
First column is the energy, next columns are the corresponding transmission
factors for each attenuator blade;
There should be attenuators indexes as comments like this:

#MIN_ATT_INDEX = 1
#MAX_ATT_INDEX = 13
#
20.0100  100      100      100       94.4431  94.4431  77.7768  66.6651  94.4431  77.7768  55.5558  38.8872  11.1093  11.1093
19.4979  100      100      100      100       86.3638  77.2724  63.6362  86.3638  77.2724  50       31.8172   9.0896   9.0896
18.9986  100      100      100       96.1545  92.3073  84.6147  57.6927  88.4618  84.6147  46.1529  34.6147   7.6911   7.6911
...

Datafile example for fixed energy:

#MIN_ATT_INDEX = 1
#MAX_ATT_INDEX = 9
#
12.812 100.00 72.00 92.00 3.50 18.00 30.00 42.70 58.18 68.0

"""

from functools import reduce

ATTENUATION_TABLE = []
ALL_ATTENUATION = {}


def _read_array_from_file(datafile):
    global MIN_ATT_INDEX
    global MAX_ATT_INDEX

    with open(datafile) as f:
        array = []
        variables_to_declare = []
        for line in f:
            if line.startswith("#"):
                variables_to_declare.append(line[1:])
            else:
                array.append(list(map(float, line.split())))
        variables_declaration = "".join(variables_to_declare)
        exec((variables_declaration), globals())

    return array


def _get_combinations(items, n):
    """Return an iterator for lazy evaluation of all the possible unique combinations of 'n' elements in 'items'."""
    if n == 0:
        yield []
    else:
        for i in range(len(items)):
            for cc in _get_combinations(items[i + 1 :], n - 1):
                yield [items[i]] + cc


def load_attenuation_table(fname):
    global ATTENUATION_TABLE, ALL_ATTENUATION

    ATTENUATION_TABLE = _read_array_from_file(fname)
    ALL_ATTENUATION = {}


def select_energy(egy, att_array, precision=0.25):
    for egy_array in att_array:
        if abs(egy_array[0] - egy) <= precision:
            return egy_array

    return []


def get_exact_attenuation(transmission_factor, egy_array):
    if len(egy_array) > 0:
        for i, j in enumerate(egy_array):
            if j == transmission_factor:
                return (j, [i])


def get_attenuator_combinations(egy_array):
    if (
        len(egy_array) == 0
        or len(egy_array) < MIN_ATT_INDEX
        or len(egy_array) < MAX_ATT_INDEX
    ):
        return []
    if egy_array[0] in ALL_ATTENUATION:
        return ALL_ATTENUATION[egy_array[0]]

    all_attenuator_combinations = []
    allIndexes = list(range(MIN_ATT_INDEX, MAX_ATT_INDEX + 1))
    for i in range(MAX_ATT_INDEX - MIN_ATT_INDEX + 1):
        for _combination in _get_combinations(allIndexes, i + 1):
            all_attenuator_combinations.append(
                (
                    reduce(
                        lambda x, y: x * y / 100, [egy_array[j] for j in _combination]
                    ),
                    _combination,
                )
            )
    ALL_ATTENUATION[egy_array[0]] = all_attenuator_combinations  # store list
    return all_attenuator_combinations


def get_attenuation(egy, transmission_factor, fname):
    if transmission_factor > 100:
        print("Transmission must be between 0 and 100")
        return [100, []]

    if len(ATTENUATION_TABLE) == 0:
        load_attenuation_table(fname)

    egy_array = select_energy(egy, ATTENUATION_TABLE)

    # check if there is no exact attenuation in the table we are asking for
    exact_attenuation = get_exact_attenuation(transmission_factor, egy_array)
    if exact_attenuation:
        return [exact_attenuation[0], [exact_attenuation[1][0] - MIN_ATT_INDEX]]

    all_att_combinations = [
        (abs((x[0]) - transmission_factor), x[1])
        for x in get_attenuator_combinations(egy_array)
    ]

    try:
        att_combination = min(all_att_combinations)[1]
        # print(att_combination)
    except ValueError:
        att_combination = []
        att_factor = 0
    else:
        att_factor = reduce(
            lambda x, y: x * y / 100, [egy_array[i] for i in att_combination]
        )

    result_list = []
    result_list.insert(0, att_factor)
    result_list.append([x - MIN_ATT_INDEX for x in att_combination])
    return result_list


def get_transmission_factor(egy, att_combination, fname):
    """ Calculate the attenuation factor
    Args:
        att_combination(dict or str): dictionary of attenuator combinations
          (like it is returned by get_attenuation for key 'att_combination')
          or string with attenuator indexes separated by spaces
        fname (str): file name with the transmission factors
    Returns:
        (float): calculater transmission factor (0-100)
    """
    if len(ATTENUATION_TABLE) == 0:
        load_attenuation_table(fname)
    egy_array = select_energy(egy, ATTENUATION_TABLE)
    if len(egy_array) == 0:
        # there is no corresponding energy !
        return -1

    if isinstance(att_combination, dict):
        return reduce(
            lambda x, y: x * y / 100,
            [egy_array[i + MIN_ATT_INDEX] for i in att_combination.values()],
        )
    elif isinstance(att_combination, str):
        return reduce(
            lambda x, y: x * y / 100,
            [egy_array[int(i) + MIN_ATT_INDEX] for i in att_combination.split()],
        )
    else:
        return -1


if __name__ == "__main__":

    def print_usage():
        print("Usage:  %s ", end=" ")
        print("-t energy transmission fname")
        print("\tor\nUsage:  %s ", end=" ")
        print("-a energy attenuator_position(s)_string fname")
        sys.exit(0)

    import os
    import sys

    if len(sys.argv) < 4:
        print_usage()

    egy = float(sys.argv[2])
    try:
        fname = sys.argv[4]
    except:
        fname = None

    if len(ATTENUATION_TABLE) == 0:
        load_attenuation_table(fname)

    egy_array = select_energy(egy, ATTENUATION_TABLE)

    if sys.argv[1] == "-t":
        transm = float(sys.argv[3])
        abb = get_attenuation(egy, transm, fname)
        print(" Table: ", abb)
        print(" result: transmission ", abb[0], "attenuators ", abb[1:])
    elif sys.argv[1] == "-a":
        attstr = sys.argv[3]
        print("transmission: %f %%" % get_transmission_factor(egy, attstr, fname))
    else:
        printUsage()

    sys.exit(0)
