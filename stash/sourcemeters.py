import pandas as pd

from mercury.stash.basics import *
#from mercury.misc import *

class Keithley2400(Instrument, GPIBDevice):

    """
    Keithley 2400 Sourcemeter, a 20 W power supply and picoammeter
    """

    name = 'Keithley2400'

    # Tuple of available knobs; for every knob there should be a set_knob method below
    knobs = (
        'voltage',
        'fast voltages',
        'current',
        'voltage range',
        'current range',
        'nplc',
        'delay'
    )

    # Tuple of available meters; for every meter there should be a measure_meter method below
    meters = (
        'voltage',
        'current',
        'fast currents'
    )

    def __init__(self, address, current_range = 100e-3, voltage_range = 200, delay = 0.1, backend = 'visa', source='voltage', meter='current', nplc = 0.1):

        self.address = address
        self.backend = backend

        self.knob_values = {knob:None for knob in Keithley2400.knobs}

        self.fast_voltages = None  # Used for fast IV sweeps
        self.meter = meter
        self.source = source
        self.nplc = nplc
        self.connect()

        self.reset()
        self.set_nplc(nplc)
        self.set_delay(delay)
        self.set_voltage_range(voltage_range)
        self.set_current_range(current_range)
        self.set_source(source)
        self.set_meter(meter)
        self.output_on()

    def set_source(self, variable):

        if variable in ['voltage','current']:
            self.source = variable
        else:
            raise SetError('source must be either "current" or "voltage"')

        if variable == 'voltage':

            self.write(':SOUR:FUNC VOLT')
            self.set_voltage_range(self.voltage_range)

            self.knob_values['current'] = None

        if variable == 'current':

            self.write(':SOUR:FUNC CURR')
            self.set_current_range(self.current_range)

            self.knob_values['voltage'] = None

    def set_meter(self,variable):

        self.meter = variable

        if variable == 'voltage':

            self.write(':SENS:FUNC "VOLT"')
            self.write(':SENS:VOLT:RANG %.2E' % self.voltage_range)
            self.write(':FORM:ELEM VOLT')

        if variable == 'current':

            self.write(':SENS:FUNC "CURR"')
            self.write(':SENS:CURR:RANG %.2E' % self.current_range)
            self.write(':FORM:ELEM CURR')

    def output_on(self):

        self.write(':OUTP ON')

    def output_off(self):

        self.write(':OUTP OFF')

    def measure_voltage(self):

        if self.meter != 'voltage':
            self.set_meter('voltage')

        return float(self.query(':READ?').strip())

    def measure_current(self):

        if self.meter != 'current':
            self.set_meter('current')

        return float(self.query(':READ?').strip())

    def set_voltage(self, voltage):

        if self.source != 'voltage':
            Warning(f'Switching sourcing mode!')
            self.set_source('voltage')
            self.output_on()  # output if automatically shut off when the source mode is changed

        self.write(':SOUR:VOLT:LEV %.2E' % voltage)

        self.knob_values['voltage'] = voltage

    def set_current(self, current):

        if self.source != 'current':
            Warning(f'Switching sourcing mode!')
            self.set_source('current')
            self.output_on()  # output if automatically shut off when the source mode is changed

        self.write(':SOUR:CURR:LEV %.2E' % current)

        self.knob_values['current'] = current

    def set_voltage_range(self, voltage_range):

        allowed_voltage_ranges = (0.2, 2, 20, 200, 'AUTO') # allowable voltage ranges

        if voltage_range not in allowed_voltage_ranges:
            # Find nearest encapsulating voltage range
            try:
                nearest = np.argwhere( voltage_range <= np.array(allowed_voltage_ranges[:-1]) ).flatten()[0]
            except IndexError:
                nearest = -1

            self.voltage_range = allowed_voltage_ranges[nearest]

            Warning(f'Given voltage range not an option, setting to {allowed_voltage_ranges[nearest]} V instead')

        else:
            self.voltage_range = voltage_range

        if self.source == 'voltage':
            self.write(':SOUR:VOLT:RANG %.2E' % self.voltage_range)
        else:
            self.write(':SENS:VOLT:PROT %.2E' % self.voltage_range)
            self.write(':SENS:VOLT:RANG %.2E' % self.voltage_range)

        self.knob_values['voltage range'] = voltage_range

    def set_current_range(self, current_range):

        allowed_current_ranges = (1e-6, 10e-6, 100e-6, 1e-3, 10e-3, 100e-3, 1, 'AUTO')

        if current_range not in allowed_current_ranges:
            # Find nearest encapsulating current range
            nearest = np.argwhere( current_range <= np.array(allowed_current_ranges[:-1]) ).flatten()[0]

            self.current_range = allowed_current_ranges[nearest]

            Warning(f'Given current range not an option, setting to {allowed_current_ranges[nearest]} A instead')

        else:
            self.current_range = current_range

        if self.source == 'current':
            self.write(':SOUR:CURR:RANG %.2E' % self.current_range)
        else:
            self.write(':SENS:CURR:PROT %.2E' % self.current_range)
            self.write(':SENS:CURR:RANG %.2E' % self.current_range)

        self.knob_values['current range'] = current_range

    def set_nplc(self, nplc):

        if self.meter == 'current':
            self.write(':SENS:CURR:NPLC %.2E' % nplc)
        elif self.meter == 'voltage':
            self.write(':SENS:VOLT:NPLC %.2E' % nplc)

        self.knob_values['nplc'] = nplc

    def set_delay(self, delay):

        self.delay = delay
        self.knob_values['delay'] = delay

    def set_fast_voltages(self, *args):

        if len(args) == 0:
            filedialog = importlib.import_module('tkinter.filedialog')
            path = filedialog.askopenfilename(title="Select CSV File with Fast IV Voltages")
        else:
            path = args[0]

        self.knob_values['fast voltages'] = path

        fast_iv_data = pd.read_csv(path, engine='python')

        self.fast_voltages = fast_iv_data['VOLTAGE']

    def measure_fast_currents(self):

        try:
            self.fast_voltages
        except AttributeError:
            raise MeasurementError('Fast IV sweep voltages have not been set!')

        if len(self.fast_voltages) == 0:
            raise MeasurementError('Fast IV sweep voltages have not been set!')

        self.write(':SOUR:VOLT:MODE LIST')

        path = self.knob_values['fast voltages']

        if not path:
            raise MeasurementError('File path for fast IV sweep voltages have not been stored!')

        list_length = len(self.fast_voltages)

        if list_length > 100:
            sub_lists = [self.fast_voltages[i*100:(i+1)*100] for i in range(list_length // 100)]
        else:
            sub_lists = []

        if list_length % 100 > 0:
            sub_lists.append(self.fast_voltages[-(list_length % 100):])

        current_list = []

        self.connection.timeout = float('inf')  # the response times can be long

        for voltage_list in sub_lists:

            voltage_str = ', '.join(['%.4E' % voltage for voltage in voltage_list])
            self.write(':SOUR:LIST:VOLT ' + voltage_str)
            self.write(':TRIG:COUN %d' % len(voltage_list))

            raw_response = self.query(':READ?').strip()
            current_list += [float(current_str) for current_str in raw_response.split(',')]

        self.connection.timeout = 1000  # put it back

        # Save data to same path
        timestamp = get_timestamp()
        fast_iv_data = pd.read_csv(path)
        fast_iv_data[f'CURRENT-{timestamp}'] = current_list
        fast_iv_data.to_csv(path, index=False)

        self.write(':SOUR:VOLT:MODE FIX')
        #self.write(':TRIG:COUN 1')

        return f'CURRENT-{timestamp}'


class Keithley2651A(Instrument, GPIBDevice):

    """
    Keithley 2651A High Power Sourcemeter, a 200 W power supply and microammeter
    """

    name = 'Keithley2651A'

    # Tuple of available knobs; for every knob there should be a set_knob method below
    knobs = (
        'voltage',
        'fast voltages',
        'current',
        'voltage range',
        'current range',
        'nplc'
    )

    # Tuple of available meters; for every meter there should be a measure_meter method below
    meters = (
        'voltage',
        'current',
        'fast currents'
    )

    def __init__(self, address, current_range = 5, voltage_range = 40, delay = 0.1, backend = 'visa', source='voltage', meter='current', nplc = 0.1):

        self.address = address
        self.backend = backend

        self.delay = delay

        self.knob_values = {knob: None for knob in Keithley2400.knobs}

        self.source = source
        self.meter = meter

        self.fast_voltages = None  # Used for fast IV sweeps

        self.voltage_range = voltage_range
        self.current_range = current_range

        self.nplc = nplc

        self.connect()

        self.reset()
        self.set_nplc(nplc)
        self.set_voltage_range(voltage_range)
        self.set_current_range(current_range)
        self.set_source(source)
        self.set_meter(meter)
        self.output_on()

    def set_source(self, variable):

        if variable in ['voltage','current']:
            self.source = variable
        else:
            raise SetError('source must be either "current" or "voltage"')

        if variable == 'voltage':

            self.write('smua.source.func =  smua.OUTPUT_DCVOLTS')
            self.set_voltage_range(self.voltage_range)

            self.knob_values['current'] = None

        if variable == 'current':

            self.write('smua.source.func = smua.OUTPUT_DCAMPS')
            self.set_current_range(self.current_range)

            self.knob_values['voltage'] = None

    def set_meter(self,variable):

        self.meter = variable

        if variable == 'current':
            self.write('display.smua.measure.func = display.MEASURE_DCAMPS')

        if variable == 'voltage':
            self.write('display.smua.measure.func = display.MEASURE_DCVOLTS')

        # This sourcemeter does not require specifying the meter before taking a measurement

    def output_on(self):

        self.write('smua.source.output = smua.OUTPUT_ON')

    def output_off(self):

        self.write('smua.source.output = smua.OUTPUT_OFF')

    def measure_voltage(self):

        if self.meter != 'voltage':
            self.set_meter('voltage')

        return float(self.query('print(smua.measure.v())').strip())

    def measure_current(self):

        if self.meter != 'current':
            self.set_meter('current')

        return float(self.query('print(smua.measure.i())').strip())

    def set_voltage(self, voltage):

        if self.source != 'voltage':
            Warning(f'Switching sourcing mode!')
            self.set_source('voltage')
            self.output_on()  # output if automatically shut off when the source mode is changed

        self.write(f'smua.source.levelv = {voltage}')

        self.knob_values['voltage'] = voltage

    def set_current(self, current):

        if self.source != 'current':
            Warning(f'Switching sourcing mode!')
            self.set_source('current')
            self.output_on()  # output if automatically shut off when the source mode is changed

        self.write(f'smua.source.leveli = {current}')

        self.knob_values['current'] = current

    def set_voltage_range(self, voltage_range):

        if voltage_range == 'auto':
            self.write('smua.source.autorangev = smua.AUTORANGE_ON')
        else:
            self.write(f'smua.source.rangev = {voltage_range}')
            self.write(f'smua.source.limitv = {voltage_range}')

        self.knob_values['voltage range'] = voltage_range

    def set_current_range(self, current_range):

        if current_range == 'auto':
            self.write('smua.source.autorangei = smua.AUTORANGE_ON')
        else:
            self.write(f'smua.source.rangei = {current_range}')
            self.write(f'smua.source.limiti = {current_range}')

        self.knob_values['current range'] = current_range

    def set_nplc(self, nplc):

        self.write(f'smua.measure.nplc = {nplc}')

        self.knob_values['nplc'] = nplc

    def set_fast_voltages(self, *args):

        if len(args) == 0:
            filedialog = importlib.import_module('tkinter.filedialog')
            path = filedialog.askopenfilename(title="Select CSV File with Fast IV Voltages")
        else:
            path = args[0]

        self.knob_values['fast voltages'] = path

        fast_iv_data = pd.read_csv(path, engine='python')

        self.fast_voltages = fast_iv_data['VOLTAGE']

    def measure_fast_currents(self):

        try:
            self.fast_voltages
        except AttributeError:
            raise MeasurementError('Fast IV sweep voltages have not been set!')

        if len(self.fast_voltages) == 0:
            raise MeasurementError('Fast IV sweep voltages have not been set!')

        path = self.knob_values['fast voltages']

        if not path:
            raise MeasurementError('File path for fast IV sweep voltages have not been stored!')

        list_length = len(self.fast_voltages)

        if list_length > 100:
            sub_lists = [self.fast_voltages[i*100:(i+1)*100] for i in range(list_length // 100)]
        else:
            sub_lists = []

        if list_length % 100 > 0:
            sub_lists.append(self.fast_voltages[-(list_length % 100):])

        current_list = []

        self.connection.timeout = float('inf')  # the response times can be long

        for voltage_list in sub_lists:

            voltage_str = ', '.join([f'{voltage}' for voltage in voltage_list])
            self.write('vlist = {%s}' % voltage_str)
            self.write(f'SweepVListMeasureI(smua, vlist, {0.01}, {len(voltage_list)})')

            raw_response = self.query(f'printbuffer(1, {len(voltage_list)}, smua.nvbuffer1)').strip()
            current_list += [float(current_str) for current_str in raw_response.split(',')]

        self.connection.timeout = 1000  # put it back

        # Save data to same path
        timestamp = get_timestamp()
        fast_iv_data = pd.read_csv(path)
        fast_iv_data[f'CURRENT-{timestamp}'] = current_list
        fast_iv_data.to_csv(path, index=False)

        return f'CURRENT-{timestamp}'
