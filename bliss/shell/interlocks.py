from bliss import global_map
from bliss.common import tango
from bliss.common.interlocks import __find_wagos, interlock_state
from prompt_toolkit import print_formatted_text, HTML


def interlock_show(*instances):
    """Displays interlocks configuration
    Made for Wagos, but intended to be used in future for other
    kind of interlocks

    Args: any number of interlock instances, if no one is given
          it will be shown for any known instance
    """
    from bliss.controllers.wago.interlocks import interlock_show as _interlock_show
    from bliss.controllers.wago.wago import MissingFirmware
    from bliss.controllers.wago.interlocks import (
        interlock_download as _interlock_download
    )
    from bliss.controllers.wago.interlocks import (
        interlock_compare as _interlock_compare
    )

    wagos = __find_wagos()

    if not len(instances):
        instances = ()
        instances += wagos
        # eventual others intances

    if len(instances) == 0:
        print("No instance found")
        return

    names = [instance.name for instance in instances]
    print_formatted_text(
        HTML(f"Currently configured interlocks: <violet>{' '.join(names)}</violet>\n")
    )

    for instance in instances:
        # Printing intelocks info for every Wago"""

        if instance in wagos:
            wago = instance
            on_plc, on_beacon = False, False

            print_formatted_text(
                HTML(f"Interlocks on <violet>{instance.name}</violet>\n")
            )
            try:
                interlocks_on_plc = _interlock_download(
                    wago.controller, wago.modules_config
                )
                on_plc = True
            except (MissingFirmware, tango.DevFailed):
                print("Interlock Firmware is not present in the PLC")

            try:
                wago._interlocks_on_beacon
                on_beacon = True
            except AttributeError:
                print("Interlock configuration is not present in Beacon")

            if on_beacon and on_plc:
                # if configuration is present on both beacon and plc
                are_equal, messages = _interlock_compare(
                    wago._interlocks_on_beacon, interlocks_on_plc
                )
                if are_equal:
                    print_formatted_text(HTML("<green>On PLC:</green>"))
                    print(_interlock_show(wago.name, interlocks_on_plc))
                else:
                    print_formatted_text(HTML("<green>On PLC:</green>"))
                    print(_interlock_show(wago.name, interlocks_on_plc))
                    print_formatted_text(HTML("\n<green>On Beacon:</green>"))
                    print(_interlock_show(wago.name, wago._interlocks_on_beacon))
                    print("There are configuration differences:")
                    for line in messages:
                        print(line)
            else:
                if on_plc:
                    print_formatted_text(HTML("<green>On PLC:</green>"))
                    print(_interlock_show(wago.name, interlocks_on_plc))
                if on_beacon:
                    print_formatted_text(HTML("\n<green>On Beacon:</green>"))
                    print(_interlock_show(wago.name, wago._interlocks_on_beacon))
