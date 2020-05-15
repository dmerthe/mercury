import time
import datetime
import numbers
from ruamel.yaml import YAML
import re
import numpy as np
import pandas as pd

from mercury import instrumentation

yaml=YAML()

def convert_time(time_value):
    """

    :param time_value: (str/float) time value, possibly including units such as 'hours'
    :return:
    """
    if isinstance(time_value, numbers.Number):
        return time_value
    elif isinstance(time_value, str):
        # times can be specified in the runcard with units, such as minutes, hours or days, e.g.  "6 hours"
        value, unit = time_value.split(' ')
        value = float(value)
        return value * {
            'minutes': 60, 'minute': 60,
            'hours': 3600, 'hour': 3600,
            'days': 86400, 'day':86400
        }[unit]


def get_timestamp(path=None):
    """
    Generates a timestamp in the YYYYMMDD-HHmmss format

    :param path: (string) path to get timestamp from; if None, a new timestamp will be generated and returned
    :return: (string) the formatted timestamp
    """

    if path:
        timestamp_format = re.compile(r'\d\d\d\d\d\d\d\d-\d\d\d\d\d\d')
        timestamp_matches = timestamp_format.findall(path)
        if len(timestamp_matches) > 0:
            return timestamp_matches[-1]
    else:
        return time.strftime("%Y%m%d-%H%M%S", time.localtime())

def timestamp_path(path, timestamp=None):
    """

    :param path: (str) path to which the timestamp will be appended or updated
    :param timestamp: (string) if provided, this timestamp will be appended. If not provided, a new timestamp will be generated.
    :return: (str) timestamped path
    """

    already_timestamped = False

    if not timestamp:
        timestamp = get_timestamp()

    # separate extension
    full_name = '.'.join(path.split('.')[:-1])
    extension = '.' + path.split('.')[-1]

    # If there is already a timestamp, replace it
    # If there is not already a timestamp, append it

    timestamp_format = re.compile(r'\d\d\d\d\d\d\d\d-\d\d\d\d\d\d')
    timestamp_matches = timestamp_format.findall(path)

    if len(timestamp_matches) > 0:
        already_timestamped = True

    if already_timestamped:
        return '-'.join(full_name.split('-')[:-2]) + '-' + timestamp + extension
    else:
        return full_name + '-' + timestamp + extension


class Clock:
    """
    Clock for keeping time, capable of running splits and pausing
    """

    def __init__(self):
        self.start()

    def start(self):
        self.start_time = time.time()

        self.stop_time = None  # if paused, the time when the clock was paused
        self.total_stoppage = 0  # amount of stoppage time, or total time while paused

    def time(self):
        if not self.stop_time:
            return time.time() - self.start_time - self.total_stoppage
        else:
            return self.stop_time - self.start_time - self.total_stoppage

    def stop(self):
        if not self.stop_time:
            self.stop_time = time.time()

    def resume(self):
        if self.stop_time:
            self.total_stoppage += time.time() - self.stop_time
            self.stop_time = None


class MappedVariable:
    """
    A variable directly associated with a knob or meter of a connected instrument
    """

    def __init__(self, instrument, knob=None, meter=None):

        if knob is None and meter is None:
            raise TypeError('Need either a knob or meter specification!')

        self.instrument = instrument

        self.knob = knob
        if knob == 'None':
            self.knob = None

        self.meter = meter
        if meter == 'None':
            self.meter = None

    def set(self, value):

        if self.knob is None:
            raise TypeError("Cannot set this variable, because it has no associated knob!")

        self.instrument.set(self.knob, value)

    def get(self):

        if self.knob is None:
            raise TypeError("Get method is for knobs only!")

        return self.instrument.knob_values[self.knob]

    def measure(self, sample_number=1):

        if self.meter is None:
            raise TypeError("Cannot measure this variable, because it has no associated meter!")

        value = self.instrument.measure(self.meter, sample_number=sample_number)

        return value


class InstrumentSet:
    """
    Set of instruments to be used in an experiment, including presets, knob and meter specs and alarm protocols
    """

    # Alarm trigger classifications
    alarm_map = {
        'IS': lambda val, thres: val == thres,
        'NOT': lambda val, thres: val != thres,
        'GREATER': lambda val, thres: val > thres,
        'GEQ': lambda val, thres: val > thres,
        'LESS': lambda val, thres: val < thres,
        'LEQ': lambda val, thres: val <= thres,
    }

    def __init__(self, specs=None, variables=None, alarms=None, presets=None, postsets=None):

        self.instruments = {}  # Will contain a list of instrument instances from the instrumentation submodule
        if specs:
            self.connect(specs)

        self.mapped_variables = {}
        if variables:
            self.map_variables(variables)

        if alarms:
            self.alarms = { name: {**alarm, 'triggered': False} for name, alarm in alarms.items() }
        else:
            self.alarms = {}

        if presets:
            self.presets = presets
        else:
            self.presets = {}

        if postsets:
            self.postsets = postsets
        else:
            self.postsets = {}

        self.apply(self.presets)

    def connect(self, specs):
        """
        Establishes communications with instruments according to specs

        :param specs: (iterable) list or array, whose rows are 4-element instrument specifications, including name, kind, backend and address
        :return: None
        """

        for name, spec in specs.items():

            kind, backend, address = spec['kind'], spec['backend'], spec['address']

            if backend not in instrumentation.available_backends:
                raise instrumentation.ConnectionError(f'{backend} is not a valid instrument communication backend!')

            instrument = instrumentation.__dict__[kind](address, backend=backend.lower())
            instrument.name = name

            self.instruments[name] = instrument

    def map_variables(self, variables):

        for name, mapping in variables.items():

            instrument, knob, meter = mapping['instrument'], mapping['knob'], mapping['meter']
            self.mapped_variables.update({name: MappedVariable(self.instruments[instrument], knob=knob, meter=meter)})

    def disconnect(self):
        """
        Disconnects communications with all instruments

        :return: None
        """

        self.apply(self.postsets)

        for instrument in self.instruments.values():
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
                self.mapped_variables[knob_name].set(value)
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

        readings = {}

        if meters is None:
            return {name: var.measure() for name, var in self.mapped_variables.items() if var.meter}

        for meter in meters:

            if type(meter) is str:  # if meter is a mapped variable
                readings[meter] = self.mapped_variables[meter].measure()
            else:  # otherwise, the meter can be specified by the corresponding (instrument, meter) tuple
                instrument_name, meter_name = meter
                instrument = self.instruments[instrument_name]
                readings[meter] = instrument.measure(meter_name)

        self.check_alarms(readings)

        return readings

    def check_alarms(self, readings):
        """
        Checks alarms, as specified by the alarms attribute.

        :param readings: (dict) dictionary of readings
        :return: (dict) dictionary of alarms triggered (as keys) and protocols (as values)
        """

        for alarm, config in self.alarms.items():

            meter, condition, threshold = config['meter'], config['condition'], config['threshold']

            value = readings.get(meter, None)

            if value is None:
                continue

            alarm_triggered = self.alarm_map[condition](value, threshold)
            if alarm_triggered:
                self.alarms[alarm]['triggered'] = True


class Routine:
    """
    Base class for the routines.
    """

    def __init__(self, times, values, clock=None):

        self.times = times
        self.values = values
        try:
            self.values_iter = iter(values)  # for use in the Path and Sweep subclasses
        except TypeError:
            pass

        if clock:
            self.clock = clock
        else:
            self.clock = Clock()

    def start(self):
        self.clock.start()

    def __iter__(self):
        return self


class Hold(Routine):
    """
    Holds a value, given by the 'values' argument (1-element list or number), from the first time in 'times' to the second.

    """

    def __next__(self):

        try:
            if len(self.times) == 1:
                start = self.times[0]
                end = np.inf
            elif len(self.times) == 2:
                start, end = self.times[:2]
            else:
                raise IndexError("The times argument must be either a 1- or 2- element list, or a number!")
        except TypeError:
            start = self.times
            end = np.inf

        try:
            value = self.values[0]
        except TypeError:
            value = self.values

        now = self.clock.time()

        if start <= now <= end:
            return value


class Ramp(Routine):
    """
    Linearly ramps a value from the first value in 'values' to the second, from the first time in 'times' to the second.
    """

    def __next__(self):

        if len(self.times) == 1:
            start = self.times[0]
            end = np.inf
        elif len(self.times) == 2:
            start, end = self.times[:2]
        else:
            raise IndexError("The times argument must be either a 1- or 2-element list!")

        start_value, end_value = self.values

        now = self.clock.time()

        if start <= now <= end:
            return start_value + (end_value - start_value)*(now - start) / (end - start)


class Transit(Routine):
    """
    Sequentially and immediately passes a value once through the 'values' list argument, cutting it off at the single value of the 'times' argument.
    """

    def __next__(self):

        try:
            if len(self.times) == 1:
                end = self.times[0]
            else:
                raise IndexError("The times argument must be either a 1-element list, or a number!")
        except TypeError:
            end = self.times

        self.time = self.clock.time()

        if self.time <= end:
            return next(self.values_iter, None)


class Sweep(Routine):
    """
    Sequentially and cyclically sweeps a value through the 'values' list argument, starting at the first time in 'times' and ending at the last.
    """

    def __next__(self):

        if len(self.times) == 1:
            start = self.times[0]
            end = np.inf
        elif len(self.times) == 2:
            start, end = self.times[:2]
        else:
            raise IndexError("The times argument must be either a 1- or 2-element list!")

        now = self.clock.time()

        if start <= now <= end:
            try:
                return next(self.values_iter)
            except StopIteration:
                self.values_iter = iter(self.values)  # restart the sweep
                return next(self.values_iter)

class Schedule:
    """
    Schedule of settings to be applied to knobs, implemented as an iterable to allow for flexibility in combining different kinds of routines
    """

    def __init__(self, routines=None):
        """

        :param routines: (dict) dictionary of routine specifications (following the runcard yaml format).
        """

        self.clock = Clock()
        self.end_time = np.inf

        self.routines = {}
        if routines:
            self.add(routines)

    def add(self, routines):
        """
        Adds routines to the schedule, based on the given dictionary of specifications (following the runcard yaml format)

        :param routines: (dict) dictionary of routine specifications.
        :return: None
        """

        for name, spec in routines.items():
            kind, variable = spec['routine'], spec['variable']
            values = spec['values']

            times = []
            for time_value in spec['times']:
                times.append(convert_time(time_value))

            routine = {
                'Hold': Hold,
                'Ramp': Ramp,
                'Sweep': Sweep,
                'Transit': Transit
            }[kind](times, values, self.clock)

            self.routines.update({name: (variable, routine)})

    def start(self):
        self.clock.start()

    def stop(self):
        self.clock.stop()

    def resume(self):
        self.clock.resume()

    def __iter__(self):
        return self

    def __next__(self):

        output = {}
        for pair in self.routines.values():
            knob, routine = pair
            next_value = next(routine)
            output.update({knob: next_value})

        return output


class Experiment:

    def __init__(self, runcard):
        """

        :param runcard: (file) runcard file
        """

        self.clock = Clock()  # used for save timing
        self.clock.start()

        self.last_step = -np.inf  # time of last step taken
        self.last_save = -np.inf  # time of last save

        self.build_from(runcard)  # build experiment from runcard

        self.data = pd.DataFrame()  # Will contain history of knob settings and meter readings for the experiment.

        self.running = False
        self.finished = False  # flag for terminating the experiment
        self.followup = self.settings.get('follow-up', None).strip()  # What to do when the experiment ends

        # Make a list of follow-ups
        if self.followup in [None, 'None']:
            self.followup = [None]
        elif isinstance(self.followup, str):
            self.followup = [self.followup]

    def build_from(self, runcard):
        """
        Populates the experiment attributes from the given runcard.

        :param runcard: (file) runcard in the form of a binary file object.
        :return: None
        """
        runcard_dict = yaml.load(runcard)
        self.runcard = runcard_dict
        self.description = runcard_dict["Description"]

        self.instruments = InstrumentSet(
            runcard_dict['Instruments'],
            runcard_dict['Variables'],
            runcard_dict['Alarms'],
            runcard_dict['Presets'],
            runcard_dict['Postsets']
        )

        self.settings = runcard_dict['Experiment Settings']
        self.plotting = runcard_dict['Plotting']
        self.schedule = Schedule(runcard_dict['Schedule'])

    def save(self, save_now=False):
        """

        :param save_now: (bool/str) If False, saves will only occur at a maximum frequency defined by the 'save interval' experimt setting. Otherwise, experiment data is saved immediately.
        :return: None
        """

        now = self.clock.time()
        save_interval = self.settings.get('save interval', 60)

        if now >= self.last_save + save_interval or save_now:
            self.data.to_csv(timestamp_path('data.csv'))
            self.last_save = self.clock.time()

    def __iter__(self):
        return self

    def __next__(self):

        # Stop if finished
        if self.finished:
            self.running = False
            self.save('now')
            self.schedule.clock.stop()
            self.instruments.disconnect()
            raise StopIteration

        # On first iteration, save the runcard of executed experiment and start the schedule clock
        if not self.running:
            name = self.description.get('name', 'experiment')
            with open(timestamp_path(name + '_runcard.yaml'), 'w') as runcard_file:
                yaml.dump(self.runcard, runcard_file)

            self.schedule.clock.start()  # start the schedule clock
            self.running = True

        # Flag for termination if time has exceeded experiment duration
        duration = convert_time(self.settings['duration'])
        if self.schedule.clock.time() > duration:
            self.finished = True

        # Flag for termination if any alarms have been raised
        for alarm in self.instruments.alarms.values():
            if alarm['triggered']:
                self.followup.insert(0, alarm['protocol'])
                self.finished = True

        # Make sure time is right for next step
        now = self.schedule.clock.time()
        step_interval = self.settings.get('step interval', 0)
        if now < self.last_step + step_interval:
            time.sleep(self.last_step + step_interval - now)

        self.last_step = self.schedule.clock.time()

        # Take the next step in the experiment
        configuration = next(self.schedule)

        # Get previously set knob values if no corresponding routines are running
        for knob, value in configuration.items():
            if value is None:
                configuration[knob] = self.instruments.mapped_variables[knob].get()

        state = configuration  # will contain knob values + meter readings + schedule time

        self.instruments.apply(configuration)
        readings = self.instruments.read()
        state.update(readings)

        times = {'Total Time': self.clock.time(), 'Schedule Time': self.schedule.clock.time()}
        state.update(times)

        state = pd.Series(state, name = datetime.datetime.now())
        self.data = self.data.append(state)

        self.save()

        return state
