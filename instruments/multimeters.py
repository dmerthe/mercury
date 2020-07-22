from mercury.instruments.basics import *

class Keithley2110(Instrument):
    """
    Keithley 2110 digital multimeter instrument
    """

    name = "Keithley2110"

    knobs = (
        'voltage range',
        'current range'
    )

    meters = (
        'voltage',
        'current',
        'temperature'
    )

    def __init__(self, address, backend='visa', meter='current', voltage_range = None, current_range = None):

        self.address = address
        self.backend = backend

        self.knob_values = {knob: None for knob in Keithley2110.knobs}

        self.meter = meter

        self.connect()

        if voltage_range:
            self.set_voltage_range(voltage_range)
        else:
            self.set_voltage_range('AUTO')

        if current_range:
            self.set_current_range(current_range)
        else:
            self.set_current_range('AUTO')

    def set_voltage_range(self, voltage_range):

        allowed_voltage_ranges = (0.1, 1, 10, 100, 1000, 'AUTO')

        if voltage_range not in allowed_voltage_ranges:
            # Find nearest encapsulating voltage range
            try:
                nearest = np.argwhere( voltage_range <= np.array(allowed_voltage_ranges[:-1]) ).flatten()[0]
            except IndexError:
                nearest = -1

            self.knob_values['voltage range'] = allowed_voltage_ranges[nearest]

            Warning(f'Given voltage range not an option, setting to {allowed_voltage_ranges[nearest]} V instead')
        else:
            self.knob_values['voltage range'] = voltage_range

        if self.knob_values['voltage range'] == 'AUTO':
            self.write('VOLT:RANG:AUTO')
        else:
            self.write('VOLT:RANG %.2e' % self.knob_values['voltage range'])

    def set_current_range(self, current_range):

        allowed_current_ranges = (0.01, 0.1, 1, 3, 10, 'AUTO')

        if current_range not in allowed_current_ranges:
            # Find nearest encapsulating current range
            nearest = np.argwhere( current_range <= np.array(allowed_current_ranges[:-1]) ).flatten()[0]

            self.knob_values['current range'] = allowed_current_ranges[nearest]

            Warning(f'Given current range not an option, setting to {allowed_current_ranges[nearest]} A instead')
        else:
            self.knob_values['current range'] = current_range

        if self.knob_values['current range'] == 'AUTO':
            self.write('CURR:RANG:AUTO')
        else:
            self.write('CURR:RANG %.2e' % self.knob_values['current range'])

    def measure_voltage(self):

        if self.meter != 'voltage':
            self.write('FUNC "VOLT"')

        return float(self.query('READ?'))

    def measure_current(self):

        if self.meter != 'current':
            self.write('FUNC "CURR"')

        return float(self.query('READ?'))

    def measure_temperature(self):

        if self.meter != 'temperature':
            self.write('FUNC "TCO"')

        return float(self.query('READ?'))
