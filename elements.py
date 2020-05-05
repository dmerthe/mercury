import time
import numpy as np
from pandas import DataFrame
from scipy.interpolate import interp1d

import instrumentation

class Clock:
    """
    Clock for keeping time, capable of running splits and pausing
    """

    def __init__(self):
        self.start_clock()

    def start_clock(self):
        self.start = time.time()
        self.split_start = time.time()

        self.pause_time = None  # if paused, the time when the clock was paused

        self.total_stoppage = 0
        self.split_stoppage = 0

    def start_split(self):
        self.split_stoppage = 0
        self.split_start = time.time()

    def split_time(self):
        if not self.pause_time:
            return time.time() - self.split_start - self.split_stoppage
        else:
            return self.pause_time - self.split_start - self.split_stoppage

    def total_time(self):
        if not self.pause_time:
            return time.time() - self.start - self.total_stoppage
        else:
            return self.pause_time - self.start - self.total_stoppage

    def pause(self):
        if not self.pause_time:
            self.pause_time = time.time()

    def resume(self):
        if self.pause_time:
            self.total_stoppage += time.time() - self.pause_time
            self.split_stoppage += time.time() - self.pause_time
            self.pause_time = None

class MappedVariable:
    """
    A variable directly associated with a knob or meter of a connected instrument
    """

    def __init__(self, instrument, knob=None, meter=None):

        if knob is None and meter is None:
            raise TypeError('Need either a knob or meter specification!')

        self.instrument = instrument
        self.knobs = knob
        self.meter = meter

    def set(self, value):

        if self.knob is None:
            raise TypeError("Cannot set this variable, because it has no associated knob!")

        self.instrument.set(self.knob, value)

    def measure(self, sample_number=1):

        if self.meter is None:
            raise TypeError("Cannot measure this variable, because it has no associated meter!")

        value = self.instrument.measure(self.meter, sample_number=sample_number)

        return value


class InstrumentSet:
    """
    Set of instruments to be used in an experiment, including presets, knob and meter specs and alarm protocols
    """

    def __init__(self, specs=None, mapped_vars=None, alarms=None, presets=None, postsets=None):

        self.instruments = {}  # Will contain a list of instrument instances from the instrumentation submodule

        if specs:
            self.connect(specs)

        if mapped_vars:
            self.mapped_vars = mapped_vars
        else:
            self.mapped_vars = {}

        if alarms:
            self.alarms = alarms
        else:
            self.alarms = []

        if presets:
            self.presets = presets
        else:
            self.presets = {}

        if postsets:
            self.postsets = postsets
        else:
            self.postsets = {}

    def connect(self, specs):
        """
        Establishes communications with instruments according to specs

        :param specs: (iterable) list or array, whose rows are 4-element instrument specifications, including name, kind, backend and address
        :return: None
        """

        for spec in specs:

            name, kind, backend, address = spec

            if backend not in instrumentation.available_backends:
                raise instrumentation.ConnectionError(f'{backend} is not a valid instrument communication backend!')

            instrument = instrumentation.__dict__[kind](address, backend=backend.lower())
            instrument.name = name

            self.instruments[name] = instrument

        self.apply(self.presets)

    def disconnect(self):
        """
        Disconnects communications with all instruments

        :return: None
        """

        self.apply(postsets)

        for instrument in self.instruments:
            instrument.disconnect()

        self.instruments = []


    def apply(self, knob_settings):
        """
        Apply settings to knobs of the instruments

        :param knob_settings: (dict) dictionary of knob settings in the form, knob_name: value
        :return: None

        To set a mapped variable knob, simply use its name here. Otherwise, set the knob_name to a 2-element tuple of the form (instrument_name, knob_name).
        """

        for knob_name, value in knob_settings.items():

            if type(knob_name) is str:  # for mapped variables
                self.mapped_vars[knob_name].set(value)
            else:  # for unmapped variables
                instrument_name, knob_name = knob_name
                instrument = self.instruments[instrument_name]
                instrument.set(knob_name, value)

    def read(self, meters=None):
        """
        Read meters of the instruments.

        :param meters: (list) list of meters to be read; if unspecified, this method measures and returns all mapped variable meter values.
        :return: (dictionary) dictionary of measured values in the form, meter_name: value
        """

        if meters is None:
            return {name: var.measure() for name, var in self.mapped_vars if var.meter}


        readings = {}

        for meter in meters:

            if type(meter) is str:
                readings[meter] = self.mapped_vars[meter].measure()
            else:
                instrument_name, meter_name = meter
                instrument = self.instruments[instrument_name]
                readings[meter] = instrument.measure(meter_name)

        return readings

class HoldRoutine:

    def __init__(self, value, start, end, clock=None):
        self.value = value
        self.start = start
        self.end = end

        if clock:
            self.clock = clock
        else:
            self.clock = Clock()
            self.clock.start_clock()

        self.time = -np.inf

    def __iter__(self):
        return self

    def __next__(self):

        self.time = self.clock.total_time()

        if self.start <= self.time <= self.end:
            return value

class RampRoutine:

    def __init__(self, start_value, end_value, start, end, clock=None):

        self.start_value = start_value
        self.end_value = end_value
        self.start = start
        self.end = end

        if clock:
            self.clock = clock
        else:
            self.clock = Clock()
            self.clock.start_clock()

        self.time = -np.inf

    def __iter__(self):
        return self

    def __next__(self):

        self.time = self.clock.total_time()

        if self.start <= self.time <= self.end:
            return start_value + (end_value - start_value)*(self.time - self.start) / (self.end - self.start)

class SweepRoutine:

    def __init__(self, values, start, end, clock=None):

        self.values = values
        self.values_iter = iter(values)
        self.start = start
        self.end = end

        if clock:
            self.clock = clock
        else:
            self.clock = Clock()
            self.clock.start_clock()

        self.time = -np.inf

    def __iter__(self):
        return self

    def __next__(self):

        self.time = self.clock.total_time()

        if self.start <= self.time <= self.end:
            try:
                return next(self.values_iter)
            except StopIteration:
                self.values_iter = iter(self.values)
                return next(self.values_iter)

class PathRoutine:

    def __init__(self, values, start, end=None, clock=None):

        self.values = values
        self.values_iter = iter(values)
        self.start = start

        if end:
            self.end = end
        else:
            self.end = np.inf

        if clock:
            self.clock = clock
        else:
            self.clock = Clock()
            self.clock.start_clock()

        self.time = -np.inf

    def __iter__(self):
        return self

    def __next__(self):

        self.time = self.clock.total_time()

        if self.time <= self.end:
            try:
                return next(self.values_iter)
            except StopIteration:
                return None


class Schedule:
    """
    Schedule of settings to be applied to knobs, implemented as an iterable to allow for flexibility in combining different kinds of routines
    """

    def __init__(self, routines=None):

        self.clock = Clock()

        if routines:
            self.routines = routines
        else:
            self.routines = {}

    def add(self, routine):
        pass

    def __iter__(self):
        return self

    def __next__(self):

        for routine in self.routines:
            pass



class Runcard:

    def __init__(self):
        pass

    def load(self, path=None):
        pass

    def save(self):
        pass

class Experiment:

    def __init__(self, runcard=None):

        if runcard:
            self.from_runcard(runcard)
        else:
            self.empty()

    def empty(self):
        self.header = {}
        self.instruments = InstrumentSet()
        self.schedule = Schedule()
        self.record = DataFrame()

    def from_runcard(self, runcard):
        pass

    def to_runcard(self, runcard):
        pass

    def run(self, plot_interval=10):

        gui = ExperimentGUI()

        self.instruments.initialize()

        for configuration in self.schedule:

            self.instruments.apply(configuration)
            readings = self.instruments.read()

            self.record = self.record.append(configuretion + readings, ignore_index=True)

        instruments.finalize()
