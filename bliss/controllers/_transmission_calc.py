"""

Datafile example for tunable energy:
First column is the energy, next columns are the corresponding transmission factor for each attenuator blade;
it is important to have attenuators indexes as comments like this:

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

import os.path
import types

ATTENUATION_TABLE = []
ALL_ATTENUATION = {}


def _readArrayFromFile(datafile):
    global MIN_ATT_INDEX
    global MAX_ATT_INDEX

    try:
        f = open(datafile)

        array = []
        variablesToDeclare = []
        for line in f:
            if not line.startswith("#"):
                array.append(map(float, line.split()))
            else:
                variablesToDeclare.append(line[1:])
    except:
        return []
    else:
        variablesDeclaration = "".join(variablesToDeclare)
        exec (variablesDeclaration) in globals()

        return array


def _getCombinations(items, n):
    """Return an iterator for lazy evaluation of all the possible unique combinations of 'n' elements in 'items'."""
    if n == 0:
        yield []
    else:
        for i in xrange(len(items)):
            for cc in _getCombinations(items[i + 1 :], n - 1):
                yield [items[i]] + cc


def loadAttenuationTable(fname):
    global ATTENUATION_TABLE, ALL_ATTENUATION

    ATTENUATION_TABLE = _readArrayFromFile(fname)
    ALL_ATTENUATION = {}


def selectEnergy(egy, att_array, precision=0.25):
    for egy_array in att_array:
        if abs(egy_array[0] - egy) <= precision:
            return egy_array

    return []


def getExactAttenuation(transmitted_rate, egy_array):
    if len(egy_array) > 0:
        for i, j in enumerate(egy_array):
            if j == transmitted_rate:
                return (j, [i])


def getAttenuatorsCombinations(egy_array):
    if (
        len(egy_array) == 0
        or len(egy_array) < MIN_ATT_INDEX
        or len(egy_array) < MAX_ATT_INDEX
    ):
        return []
    if egy_array[0] in ALL_ATTENUATION:
        return ALL_ATTENUATION[egy_array[0]]

    allAttenuatorsCombinations = []
    allIndexes = range(MIN_ATT_INDEX, MAX_ATT_INDEX + 1)
    for i in range(MAX_ATT_INDEX - MIN_ATT_INDEX + 1):
        for allAttenuatorCombination in _getCombinations(allIndexes, i + 1):
            allAttenuatorsCombinations.append(
                (
                    reduce(
                        lambda x, y: x * y / 100,
                        [egy_array[j] for j in allAttenuatorCombination],
                    ),
                    allAttenuatorCombination,
                )
            )
    ALL_ATTENUATION[egy_array[0]] = allAttenuatorsCombinations  # store list
    return allAttenuatorsCombinations


def getAttenuation(egy, transmitted_rate, fname):
    if transmitted_rate > 100:
        print "Transmission must be between 0 and 100"
        return [100, []]

    if len(ATTENUATION_TABLE) == 0:
        loadAttenuationTable(fname)

    egy_array = selectEnergy(egy, ATTENUATION_TABLE)
    # first check if there is no exact attenuation in the table we are asking for
    exact_attenuation = getExactAttenuation(transmitted_rate, egy_array)
    if exact_attenuation is not None:
        return [exact_attenuation[0], [exact_attenuation[1][0] - MIN_ATT_INDEX]]

    allAttCombinations = [
        (abs((x[0]) - transmitted_rate), x[1])
        for x in getAttenuatorsCombinations(egy_array)
    ]

    try:
        attCombination = min(allAttCombinations)[1]
        # print attCombination
    except ValueError:
        attCombination = []
        attFactor = 0
    else:
        attFactor = reduce(
            lambda x, y: x * y / 100, [egy_array[i] for i in attCombination]
        )

    resultList = []
    resultList.insert(0, attFactor)
    resultList.append([x - MIN_ATT_INDEX for x in attCombination])
    return resultList


def getAttenuationFactor(egy, attCombination, fname):
    # attCombination must be a dictionary of attenuators combinations
    # (like it is returned by getAttenuation for key 'attCombination')
    # or a string with attenuators indexes separated by spaces
    if len(ATTENUATION_TABLE) == 0:
        loadAttenuationTable(fname)
    egy_array = selectEnergy(egy, ATTENUATION_TABLE)
    if len(egy_array) == 0:
        # there is no corresponding energy !
        return -1

    if type(attCombination) == types.DictType:
        return reduce(
            lambda x, y: x * y / 100,
            [egy_array[i + MIN_ATT_INDEX] for i in attCombination.itervalues()],
        )
    elif type(attCombination) == types.StringType:
        return reduce(
            lambda x, y: x * y / 100,
            [egy_array[int(i) + MIN_ATT_INDEX] for i in attCombination.split()],
        )
    else:
        return -1


if __name__ == "__main__":

    def printUsage():
        print "Usage:  %s ",
        print "-t energy transmission fname"
        print "\tor\nUsage:  %s ",
        print "-a energy attenuator_position(s)_string fname"
        sys.exit(0)

    import os
    import sys

    if len(sys.argv) < 4:
        printUsage()

    egy = float(sys.argv[2])
    try:
        fname = sys.argv[4]
    except:
        fname = None

    if len(ATTENUATION_TABLE) == 0:
        loadAttenuationTable(fname)

    egy_array = selectEnergy(egy, ATTENUATION_TABLE)

    if sys.argv[1] == "-t":
        transm = float(sys.argv[3])
        abb = getAttenuation(egy, transm, fname)
        print " Table: ", abb
        print " result: transmission ", abb[0], "attenuators ", abb[1:]
    elif sys.argv[1] == "-a":
        attstr = sys.argv[3]
        print "transmission: %f %%" % getAttenuationFactor(egy, attstr, fname)
    else:
        printUsage()

    sys.exit(0)
